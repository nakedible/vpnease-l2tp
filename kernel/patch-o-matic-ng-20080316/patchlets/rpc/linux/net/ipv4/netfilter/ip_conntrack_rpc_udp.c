/* RPC extension for IP (UDP) connection tracking, Version 2.2
 * (C) 2000 by Marcelo Barbosa Lima <marcelo.lima@dcc.unicamp.br>
 *	- original rpc tracking module
 *	- "recent" connection handling for kernel 2.3+ netfilter
 *
 * (C) 2001 by Rusty Russell <rusty@rustcorp.com.au>
 *	- upgraded conntrack modules to oldnat api - kernel 2.4.0+
 *
 * (C) 2002,2003 by Ian (Larry) Latter <Ian.Latter@mq.edu.au>
 *	- upgraded conntrack modules to newnat api - kernel 2.4.20+
 *	- extended matching to support filtering on procedures
 *
 * ip_conntrack_rpc_udp.c,v 2.2 2003/01/12 18:30:00
 *
 *	This program is free software; you can redistribute it and/or
 *	modify it under the terms of the GNU General Public License
 *	as published by the Free Software Foundation; either version
 *	2 of the License, or (at your option) any later version.
 **
 *	Module load syntax:
 *	insmod ip_conntrack_rpc_udp.o ports=port1,port2,...port<MAX_PORTS>
 *
 *	Please give the ports of all RPC servers you wish to connect to.
 *	If you don't specify ports, the default will be port 111.
 **
 *	Note to all:
 *
 *	RPCs should not be exposed to the internet - ask the Pentagon;
 *
 *	  "The unidentified crackers pleaded guilty in July to charges
 *	   of juvenile delinquency stemming from a string of Pentagon
 *	   network intrusions in February.
 *
 *	   The youths, going by the names TooShort and Makaveli, used
 *	   a common server security hole to break in, according to
 *	   Dane Jasper, owner of the California Internet service
 *	   provider, Sonic. They used the hole, known as the 'statd'
 *	   exploit, to attempt more than 800 break-ins, Jasper said."
 *
 *	From: Wired News; "Pentagon Kids Kicked Off Grid" - Nov 6, 1998
 *	URL:  http://www.wired.com/news/politics/0,1283,16098,00.html
 **
 */

#include <linux/module.h>
#include <linux/netfilter.h>
#include <linux/ip.h>
#include <net/checksum.h>
#include <net/udp.h>

#include <asm/param.h>
#include <linux/sched.h>
#include <linux/timer.h>
#include <linux/stddef.h>
#include <linux/list.h>

#include <linux/netfilter_ipv4/lockhelp.h>
#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_rpc.h>

#define MAX_PORTS 8
static int ports[MAX_PORTS];
static int ports_n_c = 0;

#ifdef MODULE_PARM
MODULE_PARM(ports, "1-" __MODULE_STRING(MAX_PORTS) "i");
MODULE_PARM_DESC(ports, "port numbers (TCP/UDP) of RPC portmapper servers");
#endif

MODULE_AUTHOR("Marcelo Barbosa Lima <marcelo.lima@dcc.unicamp.br>");
MODULE_DESCRIPTION("RPC UDP connection tracking module");
MODULE_LICENSE("GPL");

#if 0
#define DEBUGP(format, args...) printk(KERN_DEBUG "ip_conntrack_rpc_udp: " \
					format, ## args)
#else
#define DEBUGP(format, args...)
#endif

DECLARE_RWLOCK(ipct_rpc_udp_lock);
#define ASSERT_READ_LOCK(x) MUST_BE_READ_LOCKED(&ipct_rpc_udp_lock)
#define ASSERT_WRITE_LOCK(x) MUST_BE_WRITE_LOCKED(&ipct_rpc_udp_lock)
#include <linux/netfilter_ipv4/listhelp.h>

/* For future conections RPC, using client's cache bindings
 * I'll use ip_conntrack_lock to lock these lists           */

LIST_HEAD(request_p_list_udp);


static void delete_request_p(unsigned long request_p_ul)
{
	struct request_p *p = (void *)request_p_ul;
	
	WRITE_LOCK(&ipct_rpc_udp_lock);
	LIST_DELETE(&request_p_list_udp, p);
	WRITE_UNLOCK(&ipct_rpc_udp_lock);
	kfree(p);
	return;
}


static void req_cl(struct request_p * r)
{
	WRITE_LOCK(&ipct_rpc_udp_lock);
	del_timer(&r->timeout);
	LIST_DELETE(&request_p_list_udp, r);
	WRITE_UNLOCK(&ipct_rpc_udp_lock);
	kfree(r);
	return;
}


static void clean_request(struct list_head *list)
{
	struct list_head *first = list->prev;
	struct list_head *temp = list->next;
	struct list_head *aux;

	if (list_empty(list))
		return;

	while (first != temp) {
		aux = temp->next;
		req_cl((struct request_p *)temp);
		temp = aux;	
	}
	req_cl((struct request_p *)temp);
	return;
}


static void alloc_request_p(u_int32_t xid, u_int16_t proto, u_int32_t ip,
		     u_int16_t port)
{
	struct request_p *req_p;
        
	/* Verifies if entry already exists */
	WRITE_LOCK(&ipct_rpc_udp_lock);
	req_p = LIST_FIND(&request_p_list_udp, request_p_cmp,
		struct request_p *, xid, ip, port);

	if (req_p) {
		/* Refresh timeout */
		if (del_timer(&req_p->timeout)) {
			req_p->timeout.expires = jiffies + EXP;
			add_timer(&req_p->timeout);	
		} 
		WRITE_UNLOCK(&ipct_rpc_udp_lock);
		return;	

	}
	WRITE_UNLOCK(&ipct_rpc_udp_lock);
	
	/* Allocate new request_p */
	req_p = (struct request_p *) kmalloc(sizeof(struct request_p), GFP_ATOMIC);
	if (!req_p) {
 		DEBUGP("can't allocate request_p\n");
		return;			
	}
	*req_p = ((struct request_p) {{ NULL, NULL }, xid, ip, port, proto, 
		{ { NULL, NULL }, jiffies + EXP, (unsigned long)req_p,
			NULL }}); 
      
	/* Initialize timer */
	init_timer(&req_p->timeout);
	req_p->timeout.function = delete_request_p;
	add_timer(&req_p->timeout); 

	/* Put in list */
	WRITE_LOCK(&ipct_rpc_udp_lock);
	list_prepend(&request_p_list_udp, req_p);
	WRITE_UNLOCK(&ipct_rpc_udp_lock); 
	return; 

}


static int check_rpc_packet(const u_int32_t *data,
			int dir, struct ip_conntrack *ct,
			struct list_head request_p_list)
{
	struct request_p *req_p;
	u_int32_t xid;
	struct ip_conntrack_expect expect, *exp = &expect;

	/* Translstion's buffer for XDR */
	u_int16_t port_buf;


	/* Get XID */
	xid = *data;

 	/* This does sanity checking on RPC payloads,
	 * and permits only the RPC "get port" (3)
	 * in authorised procedures in client
	 * communications with the portmapper.
	 */

	/* perform direction dependant RPC work */
	if (dir == IP_CT_DIR_ORIGINAL) {

		data += 5;

		/* Get RPC requestor */
		if (IXDR_GET_INT32(data) != 3) {
			DEBUGP("RPC packet contains an invalid (non \"get\") requestor. [skip]\n");
			return NF_ACCEPT;
		}
		DEBUGP("RPC packet contains a \"get\" requestor. [cont]\n");

		data++;

		/* Jump Credentials and Verfifier */
		data = data + IXDR_GET_INT32(data) + 2;
		data = data + IXDR_GET_INT32(data) + 2;

		/* Get RPC procedure */
		DEBUGP("RPC packet contains procedure request [%u]. [cont]\n",
			(unsigned int)IXDR_GET_INT32(data));

		/* Get RPC protocol and store against client parameters */
		data = data + 2;
		alloc_request_p(xid, IXDR_GET_INT32(data), ct->tuplehash[dir].tuple.src.ip,
				ct->tuplehash[dir].tuple.src.u.all);

		DEBUGP("allocated RPC req_p for xid=%u proto=%u %u.%u.%u.%u:%u\n",
			xid, IXDR_GET_INT32(data),
			NIPQUAD(ct->tuplehash[dir].tuple.src.ip),
			ntohs(ct->tuplehash[dir].tuple.src.u.all));

		DEBUGP("allocated RPC request for protocol %u. [done]\n",
			(unsigned int)IXDR_GET_INT32(data));

	} else {

		/* Check for returning packet's stored counterpart */
		req_p = LIST_FIND(&request_p_list_udp, request_p_cmp,
				  struct request_p *, xid,
				  ct->tuplehash[!dir].tuple.src.ip,
				  ct->tuplehash[!dir].tuple.src.u.all);

		/* Drop unexpected packets */
		if (!req_p) {
			DEBUGP("packet is not expected. [skip]\n");
			return NF_ACCEPT;
		}

		/* Verifies if packet is really an RPC reply packet */
		data++;
		if (IXDR_GET_INT32(data) != 1) {
			DEBUGP("packet is not a valid RPC reply. [skip]\n");
			return NF_ACCEPT;
		}

		/* Is status accept? */
		data++;
		if (IXDR_GET_INT32(data)) {
			DEBUGP("packet is not an RPC accept. [skip]\n");
			return NF_ACCEPT;
		}

		/* Get Verifier length. Jump verifier */
		data++;
		data = data + IXDR_GET_INT32(data) + 2;

		/* Is accpet status "success"? */
		if (IXDR_GET_INT32(data)) {
			DEBUGP("packet is not an RPC accept status of success. [skip]\n");
			return NF_ACCEPT;
		}

		/* Get server port number */	  
		data++;
		port_buf = (u_int16_t) IXDR_GET_INT32(data);

		/* If a packet has made it this far then it deserves an
		 * expectation ...  if port == 0, then this service is 
		 * not going to be registered.
		 */
		if (port_buf) {
			DEBUGP("port found: %u\n", port_buf);

			memset(&expect, 0, sizeof(expect));

			/* Watch out, Radioactive-Man! */
			exp->tuple.src.ip = ct->tuplehash[!dir].tuple.src.ip;
			exp->tuple.dst.ip = ct->tuplehash[!dir].tuple.dst.ip;
			exp->mask.src.ip = 0xffffffff;
			exp->mask.dst.ip = 0xffffffff;

			switch (req_p->proto) {
				case IPPROTO_UDP:
					exp->tuple.src.u.udp.port = 0;
					exp->tuple.dst.u.udp.port = htons(port_buf);
					exp->tuple.dst.protonum = IPPROTO_UDP;
					exp->mask.src.u.udp.port = 0;
					exp->mask.dst.u.udp.port = htons(0xffff);
					exp->mask.dst.protonum = 0xffff;
					break;

				case IPPROTO_TCP:
					exp->tuple.src.u.tcp.port = 0;
					exp->tuple.dst.u.tcp.port = htons(port_buf);
					exp->tuple.dst.protonum = IPPROTO_TCP;
					exp->mask.src.u.tcp.port = 0;
					exp->mask.dst.u.tcp.port = htons(0xffff);
					exp->mask.dst.protonum = 0xffff;
					break;
			}
			exp->expectfn = NULL;

			ip_conntrack_expect_related(ct, &expect);

			DEBUGP("expect related ip   %u.%u.%u.%u:0-%u.%u.%u.%u:%u proto=%u\n",
				NIPQUAD(exp->tuple.src.ip),
				NIPQUAD(exp->tuple.dst.ip),
				port_buf, req_p->proto);

			DEBUGP("expect related mask %u.%u.%u.%u:0-%u.%u.%u.%u:65535 proto=%u\n",
				NIPQUAD(exp->mask.src.ip),
				NIPQUAD(exp->mask.dst.ip),
				exp->mask.dst.protonum);

		}

		req_cl(req_p);

		DEBUGP("packet evaluated. [expect]\n");
		return NF_ACCEPT;
	}

	return NF_ACCEPT;

}


/* RPC UDP helper */
static int help(const struct iphdr *iph, size_t len,
		struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	struct udphdr *udph = (void *) iph + iph->ihl * 4;
	const u_int32_t *data = (const u_int32_t *)udph + 2;
	size_t udplen = len - iph->ihl * 4;
	int dir = CTINFO2DIR(ctinfo);
	int crp_ret;

	/* Checksum */
	const u_int16_t *chsm = (const u_int16_t *)udph + 3;


	DEBUGP("new packet to evaluate ..\n");

	/* Not whole UDP header? */
	if (udplen < sizeof(struct udphdr)) {
		DEBUGP("UDP header length is; udplen=%u ..\n", (unsigned) udplen);
		DEBUGP("packet does not contain a complete UDP header. [skip]\n");
		return NF_ACCEPT;
	}

	/* FIXME: Source route IP option packets --RR */
	if (*chsm) {
		if (csum_tcpudp_magic(iph->saddr, iph->daddr, udplen, IPPROTO_UDP,
		    csum_partial((char *)udph, udplen, 0))) {
			DEBUGP("[note: failure to get past this error may indicate source routing]\n");
			DEBUGP("packet contains a bad checksum. [skip]\n");
			return NF_ACCEPT;
		   } 
	}

	/* perform direction dependant protocol work */
	if (dir == IP_CT_DIR_ORIGINAL) {

		DEBUGP("packet is from the initiator. [cont]\n");

		/* Tests if packet len is ok */
		if ((udplen - sizeof(struct udphdr)) != 56) {
			DEBUGP("packet length is not correct. [skip]\n");
			return NF_ACCEPT;
		}

	} else {

		DEBUGP("packet is from the receiver. [cont]\n");

		/* Until there's been traffic both ways, don't look in packets. */
		if (ctinfo != IP_CT_ESTABLISHED + IP_CT_IS_REPLY) {
			DEBUGP("connection tracking state is; ctinfo=%u ..\n", ctinfo);
			DEBUGP("[note: failure to get past this error may indicate asymmetric routing]\n");
			DEBUGP("packet is not yet part of a two way stream. [skip]\n");
			return NF_ACCEPT;
		}

		/* Tests if packet len is ok */
			if ((udplen - sizeof(struct udphdr)) != 28) {
			DEBUGP("packet length is not correct. [skip]\n");
			return NF_ACCEPT;
		}

	}

	/* Get to the data */
	/* udp *data == *correct */

	/* Check the RPC data */
	crp_ret = check_rpc_packet(data, dir, ct, request_p_list_udp);

	return crp_ret;

}


static struct ip_conntrack_helper rpc_helpers[MAX_PORTS];
static char rpc_names[MAX_PORTS][10];

static void fini(void);

static int __init init(void)
{
	int port, ret;
	char *tmpname;

	/* If no port given, default to standard RPC port */
	if (ports[0] == 0)
		ports[0] = RPC_PORT;

	for (port = 0; (port < MAX_PORTS) && ports[port]; port++) {
		memset(&rpc_helpers[port], 0, sizeof(struct ip_conntrack_helper));

		tmpname = &rpc_names[port][0];
		if (ports[port] == RPC_PORT)
			sprintf(tmpname, "rpc");
		else
			sprintf(tmpname, "rpc-%d", ports[port]);
		rpc_helpers[port].name = tmpname;

		rpc_helpers[port].me = THIS_MODULE;
		rpc_helpers[port].max_expected = 1;
		rpc_helpers[port].flags = IP_CT_HELPER_F_REUSE_EXPECT;
		rpc_helpers[port].timeout = 0;

		rpc_helpers[port].tuple.dst.protonum = IPPROTO_UDP;
		rpc_helpers[port].mask.dst.protonum = 0xffff;

		/* RPC can come from ports 0:65535 to ports[port] (111) */
		rpc_helpers[port].tuple.src.u.udp.port = htons(ports[port]);
		rpc_helpers[port].mask.src.u.udp.port = htons(0xffff);
		rpc_helpers[port].mask.dst.u.udp.port = htons(0x0);

		rpc_helpers[port].help = help;

		DEBUGP("registering helper for port #%d: %d/UDP\n", port, ports[port]);
		DEBUGP("helper match ip   %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
			NIPQUAD(rpc_helpers[port].tuple.dst.ip),
			ntohs(rpc_helpers[port].tuple.dst.u.udp.port),
			NIPQUAD(rpc_helpers[port].tuple.src.ip),
			ntohs(rpc_helpers[port].tuple.src.u.udp.port));
		DEBUGP("helper match mask %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
			NIPQUAD(rpc_helpers[port].mask.dst.ip),
			ntohs(rpc_helpers[port].mask.dst.u.udp.port),
			NIPQUAD(rpc_helpers[port].mask.src.ip),
			ntohs(rpc_helpers[port].mask.src.u.udp.port));

		ret = ip_conntrack_helper_register(&rpc_helpers[port]);

		if (ret) {
			printk("ERROR registering port %d\n",
				ports[port]);
			fini();
			return -EBUSY;
		}
		ports_n_c++;
	}
	return 0;
}


/* This function is intentionally _NOT_ defined as __exit, because 
 * it is needed by the init function */
static void fini(void)
{
	int port;

	DEBUGP("cleaning request list\n");
	clean_request(&request_p_list_udp);

	for (port = 0; (port < ports_n_c) && ports[port]; port++) {
		DEBUGP("unregistering port %d\n", ports[port]);
		ip_conntrack_helper_unregister(&rpc_helpers[port]);
	}
}


module_init(init);
module_exit(fini);

struct module *ip_conntrack_rpc_udp = THIS_MODULE;
EXPORT_SYMBOL(request_p_list_udp);
EXPORT_SYMBOL(ip_conntrack_rpc_udp);
EXPORT_SYMBOL(ipct_rpc_udp_lock);

