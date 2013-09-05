/* RPC extension for IP connection matching, Version 2.2
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
 * (c) 2004,2005 by David Stes <stes@pandora.be>
 *	- upgraded to 2.6.12+ conntrack module api
 *      - upgraded to 2.6.13 api
 *
 * ipt_rpc.c,v 2.2 2003/01/12 18:30:00
 *
 *	This program is free software; you can redistribute it and/or
 *	modify it under the terms of the GNU General Public License
 *	as published by the Free Software Foundation; either version
 *	2 of the License, or (at your option) any later version.
 **
 *	Module load syntax:
 *	insmod ipt_rpc.o ports=port1,port2,...port<MAX_PORTS>
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
#include <linux/skbuff.h>
#include <linux/list.h>
#include <linux/udp.h>
#include <linux/tcp.h>
#include <linux/netfilter_ipv4/ip_conntrack.h>
#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ip_conntrack_rpc.h>
#include <linux/netfilter_ipv4/ipt_rpc.h>

#define MAX_PORTS 8
static int ports[MAX_PORTS];
static int ports_n_c = 0;

#ifdef MODULE_PARM
module_param_array(ports, int, &ports_n_c, 0400);
MODULE_PARM_DESC(ports, "port numbers (TCP/UDP) of RPC portmapper servers");
#endif

MODULE_AUTHOR("Marcelo Barbosa Lima <marcelo.lima@dcc.unicamp.br>");
MODULE_DESCRIPTION("RPC connection matching module");
MODULE_LICENSE("GPL");

#define PRINTK(format, args...) printk(KERN_DEBUG "ipt_rpc: " \
					format, ## args)

#if 0
#define DEBUGP(format, args...) printk(KERN_DEBUG "ipt_rpc: " \
					format, ## args)
#else
#define DEBUGP(format, args...)
#endif

/* EXPORT_NO_SYMBOLS; */

/* vars from ip_conntrack_rpc_tcp */
extern struct list_head request_p_list_tcp;
extern struct module *ip_conntrack_rpc_tcp;

/* vars from ip_conntrack_rpc_udp */
extern struct list_head request_p_list_udp;
extern struct module *ip_conntrack_rpc_udp;

extern rwlock_t ipct_rpc_tcp_lock;
extern rwlock_t ipct_rpc_udp_lock;

#define ASSERT_READ_LOCK(x)
#define ASSERT_WRITE_LOCK(x)

#if 0
#define ASSERT_READ_LOCK(x)					\
do {								\
	if (x == &request_p_list_udp)				\
		MUST_BE_READ_LOCKED(&ipct_rpc_udp_lock);	\
	else if (x == &request_p_list_tcp)			\
		MUST_BE_READ_LOCKED(&ipct_rpc_tcp_lock);	\
} while (0)

#define ASSERT_WRITE_LOCK(x)					\
do {								\
	if (x == &request_p_list_udp)				\
		MUST_BE_WRITE_LOCKED(&ipct_rpc_udp_lock);	\
	else if (x == &request_p_list_tcp)			\
		MUST_BE_WRITE_LOCKED(&ipct_rpc_tcp_lock);	\
} while (0)
#endif

#include <linux/netfilter_ipv4/listhelp.h>

const int IPT_RPC_CHAR_LEN = 11;

static int k_atoi(char *string)
{
	unsigned int result = 0;
	int maxoctet = IPT_RPC_CHAR_LEN;

	for ( ; *string != 0 && maxoctet != 0; maxoctet--, string++) {
		if (*string < 0)
			return(0);
		if (*string == 0)
			break;
		if (*string < 48 || *string > 57) {
			return(0);
		}
		result = result * 10 + ( *string - 48 );
	}
	return(result);
}


static int match_rpcs(char *c_procs, int i_procs, int proc)
{
	int   proc_ctr;
	char *proc_ptr;
	unsigned int proc_num;

	DEBUGP("entered match_rpcs [%i] [%i] ..\n", i_procs, proc);

	if (i_procs == -1)
		return 1;

	for (proc_ctr=0; proc_ctr <= i_procs; proc_ctr++) {

		proc_ptr = c_procs;
		proc_ptr += proc_ctr * IPT_RPC_CHAR_LEN;
		proc_num = k_atoi(proc_ptr);

		if (proc_num == proc)
			return 1;
	}

	return 0;
}


static int check_rpc_packet(const u_int32_t *data, const void *matchinfo,
			int *hotdrop, int dir, struct ip_conntrack *ct,
			int offset, struct list_head request_p_list)
{
	const struct ipt_rpc_info *rpcinfo = matchinfo;
	struct request_p *req_p;
	u_int32_t xid;


	/* Get XID */
	xid = *data;

 	/* This does sanity checking on RPC payloads,
	 * and permits only the RPC "get port" (3)
	 * in authorised procedures in client
	 * communications with the portmapper.
	 */

	data += 5;

	/* Get RPC requestor */
	if (IXDR_GET_INT32(data) != 3) {
		DEBUGP("RPC packet contains an invalid (non \"get\") requestor. [skip]\n");
		if(rpcinfo->strict == 1)
			*hotdrop = 1;
		return 0;
	}
	DEBUGP("RPC packet contains a \"get\" requestor. [cont]\n");

	data++;

	/* Jump Credentials and Verfifier */
	data = data + IXDR_GET_INT32(data) + 2;
	data = data + IXDR_GET_INT32(data) + 2;

	/* Get RPC procedure */
	if (match_rpcs((char *)&rpcinfo->c_procs,
	    rpcinfo->i_procs, IXDR_GET_INT32(data)) == 0) {
		DEBUGP("RPC packet contains illegal procedure request [%u]. [drop]\n",
			(unsigned int)IXDR_GET_INT32(data));

		/* If the RPC conntrack half entry already exists .. */

		switch (ct->tuplehash[0].tuple.dst.protonum) {
			case IPPROTO_UDP:
				write_lock_bh(&ipct_rpc_udp_lock);
			case IPPROTO_TCP:
				write_lock_bh(&ipct_rpc_tcp_lock);
		}
		req_p = LIST_FIND(&request_p_list, request_p_cmp,
				  struct request_p *, xid,
				  ct->tuplehash[dir].tuple.src.ip,
				  ct->tuplehash[dir].tuple.src.u.all);

		if (req_p) {
			DEBUGP("found req_p for xid=%u proto=%u %u.%u.%u.%u:%u\n",
				xid, ct->tuplehash[dir].tuple.dst.protonum,
				NIPQUAD(ct->tuplehash[dir].tuple.src.ip),
				ntohs(ct->tuplehash[dir].tuple.src.u.all));

			/* .. remove it */
			if (del_timer(&req_p->timeout))
				req_p->timeout.expires = 0;

       			LIST_DELETE(&request_p_list, req_p);
			DEBUGP("RPC req_p removed. [done]\n");

		} else {
			DEBUGP("no req_p found for xid=%u proto=%u %u.%u.%u.%u:%u\n",
				xid, ct->tuplehash[dir].tuple.dst.protonum,
				NIPQUAD(ct->tuplehash[dir].tuple.src.ip),
				ntohs(ct->tuplehash[dir].tuple.src.u.all));

		}
		switch (ct->tuplehash[0].tuple.dst.protonum) {
			case IPPROTO_UDP:
				write_unlock_bh(&ipct_rpc_udp_lock);
			case IPPROTO_TCP:
				write_unlock_bh(&ipct_rpc_tcp_lock);
		}

		if(rpcinfo->strict == 1)
			*hotdrop = 1;
		return 0;
	}

	DEBUGP("RPC packet contains authorised procedure request [%u]. [match]\n",
		(unsigned int)IXDR_GET_INT32(data));
	return (1 && (!offset));
}



/* static int match(const struct sk_buff *skb, const struct net_device *in,
		 const struct net_device *out, const void *matchinfo,
		 int offset, const void *hdr, u_int16_t datalen, int *hotdrop)
*/
static int match(const struct sk_buff *skb, const struct net_device *in,
		 const struct net_device *out, const void *matchinfo,
		 int offset, int *hotdrop)
{
	struct ip_conntrack *ct;
	enum ip_conntrack_info ctinfo;
	const u_int32_t *data;
	enum ip_conntrack_dir dir;
	const struct tcphdr *tcp;
	const struct ipt_rpc_info *rpcinfo = matchinfo;
	int port, portsok;
	int tval;
	struct iphdr *ip; /* stes */
        void *hdr; /* stes */
        u_int16_t datalen; /* stes */

	/* Initialization stes - see 2.4 ip_tables.c ipt_do_table() */
	ip = skb->nh.iph;
	hdr = (u_int32_t *)ip + ip->ihl;
	datalen = skb->len - ip->ihl * 4;

	DEBUGP("new packet to evaluate ..\n");

	ct = ip_conntrack_get((struct sk_buff *)skb, &ctinfo);
	if (!ct) {
		DEBUGP("no ct available [skip]\n");
		return 0;
	}

	DEBUGP("ct detected. [cont]\n");
	dir = CTINFO2DIR(ctinfo);

	/* we only want the client to server packets for matching */
	if (dir != IP_CT_DIR_ORIGINAL)
		return 0;

	/* This does sanity checking on UDP or TCP packets,
	 * like their respective modules.
	 */

	switch (ct->tuplehash[0].tuple.dst.protonum) {

		case IPPROTO_UDP:
			DEBUGP("PROTO_UDP [cont]\n");
			if (offset == 0 && datalen < sizeof(struct udphdr)) {
				DEBUGP("packet does not contain a complete header. [drop]\n");
				return 0;
			}

			for (port=0,portsok=0; port <= ports_n_c; port++) {
				if (ntohs(ct->tuplehash[dir].tuple.dst.u.all) == ports[port]) {
					portsok++;
					break;
				}
			}
			if (portsok == 0) {
				DEBUGP("packet is not destined for a portmapper [%u]. [skip]\n",
					ntohs(ct->tuplehash[dir].tuple.dst.u.all));
				return 0;
			}

			if ((datalen - sizeof(struct udphdr)) != 56) {
				DEBUGP("packet length is not correct for RPC content. [skip]\n");
				if (rpcinfo->strict == 1)
					*hotdrop = 1;
				return 0;
			}
			DEBUGP("packet length is correct. [cont]\n");

			/* Get to the data */
			data = (const u_int32_t *)hdr + 2;

			/* Check the RPC data */
			tval = check_rpc_packet(data, matchinfo, hotdrop,
						dir, ct, offset,
						request_p_list_udp);

			return tval;
			
		
		case IPPROTO_TCP:
			DEBUGP("PROTO_TCP [cont]\n");
			if (offset == 0 && datalen < sizeof(struct tcphdr)) {
				DEBUGP("packet does not contain a complete header. [drop]\n");
				return 0;
			}
	
			for (port=0,portsok=0; port <= ports_n_c; port++) {
				if (ntohs(ct->tuplehash[dir].tuple.dst.u.all) == ports[port]) {
					portsok++;
					break;
				}
			}
			if (portsok == 0) {
				DEBUGP("packet is not destined for a portmapper [%u]. [skip]\n",
					ntohs(ct->tuplehash[dir].tuple.dst.u.all));
				return 0;
			}

			tcp = hdr;
			if (datalen == (tcp->doff * 4)) {
				DEBUGP("packet does not contain any data. [match]\n");
				return (1 && (!offset));
			}

			/* Tests if packet len is ok */
			if ((datalen - (tcp->doff * 4)) != 60) {
				DEBUGP("packet length is not correct for RPC content. [skip]\n");
				if(rpcinfo->strict == 1)
					*hotdrop = 1;
				return 0;
			}
			DEBUGP("packet length is correct. [cont]\n");

			/* Get to the data */
			data = (const u_int32_t *)tcp + tcp->doff + 1;	

			/* Check the RPC data */
			tval = check_rpc_packet(data, matchinfo, hotdrop,
						dir, ct, offset,
						request_p_list_tcp);

			return tval;

	}

	DEBUGP("transport protocol=%u, is not supported [skip]\n",
		ct->tuplehash[0].tuple.dst.protonum);
	return 0;
}


static int checkentry(const char *tablename, const struct ipt_ip *ip, void *matchinfo,
		   unsigned int matchsize, unsigned int hook_mask)
{
	if (hook_mask
	    & ~((1 << NF_IP_PRE_ROUTING) | (1 << NF_IP_FORWARD) | (1 << NF_IP_POST_ROUTING)
		| (1 << NF_IP_LOCAL_IN) | (1 << NF_IP_LOCAL_OUT))) {
		printk("ipt_rpc: only valid for PRE_ROUTING, FORWARD, POST_ROUTING, LOCAL_IN and/or LOCAL_OUT targets.\n");
		return 0;
	}

	if (matchsize != IPT_ALIGN(sizeof(struct ipt_rpc_info)))
		return 0;

	return 1;
}

static struct ipt_match rpc_match = {
        .name           = "rpc",
        .match          = &match,
        .checkentry     = &checkentry,
        .me             = THIS_MODULE,
};

static int __init init(void)
{
	int port;

	/* If no port given, default to standard RPC port */
	if (ports[0] == 0)
		ports[0] = RPC_PORT;

	PRINTK("registering match [%s] for;\n", rpc_match.name);
	for (port = 0; (port < MAX_PORTS) && ports[port]; port++) {
		PRINTK("  port %i (UDP|TCP);\n", ports[port]);
		ports_n_c++;
	}
	
	return ipt_register_match(&rpc_match);
}


static void fini(void)
{
	DEBUGP("unregistering match\n");
	ipt_unregister_match(&rpc_match);
}


module_init(init);
module_exit(fini);

