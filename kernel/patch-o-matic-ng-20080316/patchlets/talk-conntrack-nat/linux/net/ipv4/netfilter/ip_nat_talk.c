/* 
 * talk extension for UDP NAT alteration. 
 * Jozsef Kadlecsik <kadlec@blackhole.kfki.hu>
 *
 *      This program is free software; you can redistribute it and/or
 *      modify it under the terms of the GNU General Public License
 *      as published by the Free Software Foundation; either version
 *      2 of the License, or (at your option) any later version.
 **
 *     Module load syntax:
 *     insmod ip_nat_talk.o talk=[0|1] ntalk=[0|1] ntalk2=[0|1]
 *
 *		talk=[0|1]	disable|enable old talk support
 *	       ntalk=[0|1]	disable|enable ntalk support
 *	      ntalk2=[0|1]	disable|enable ntalk2 support
 *
 *     The default is talk=1 ntalk=1 ntalk2=1
 *
 *  
 */
#include <linux/module.h>
#include <linux/netfilter_ipv4.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <linux/kernel.h>
#include <net/tcp.h>
#include <net/udp.h>

#include <linux/netfilter_ipv4/ip_nat.h>
#include <linux/netfilter_ipv4/ip_nat_helper.h>
#include <linux/netfilter_ipv4/ip_nat_rule.h>
#include <linux/netfilter_ipv4/ip_conntrack_talk.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>

/* Default all talk protocols are supported */
static int talk   = 1;
static int ntalk  = 1;
static int ntalk2 = 1;
MODULE_AUTHOR("Jozsef Kadlecsik <kadlec@blackhole.kfki.hu>");
MODULE_DESCRIPTION("talk network address translation module");
#ifdef MODULE_PARM
MODULE_PARM(talk, "i");
MODULE_PARM_DESC(talk, "support (old) talk protocol");
MODULE_PARM(ntalk, "i");
MODULE_PARM_DESC(ntalk, "support ntalk protocol");
MODULE_PARM(ntalk2, "i");
MODULE_PARM_DESC(ntalk2, "support ntalk2 protocol");
#endif

#if 0
#define DEBUGP printk
#define IP_NAT_TALK_DEBUG
#else
#define DEBUGP(format, args...)
#endif

/* FIXME: Time out? --RR */

static int
mangle_packet(struct sk_buff **pskb,
	      struct ip_conntrack *ct,
	      u_int32_t newip,
	      u_int16_t port,
	      struct talk_addr *addr,
	      struct talk_addr *ctl_addr)
{
	struct iphdr *iph = (*pskb)->nh.iph;
	struct udphdr *udph = (void *)iph + iph->ihl * 4;
	size_t udplen = (*pskb)->len - iph->ihl * 4;

	/* Fortunately talk sends a structure with the address and
	   port in it. The size of the packet won't change. */

	if (ctl_addr == NULL) {
		/* response */
		if (addr->ta_addr == INADDR_ANY)
			return 1;
		DEBUGP("ip_nat_talk_mangle_packet: response orig %u.%u.%u.%u:%u, inserting %u.%u.%u.%u:%u\n", 
		       NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
		       NIPQUAD(newip), ntohs(port));
		addr->ta_addr = newip;
		addr->ta_port = port;
	} else {
		/* message */
		if (addr->ta_addr != INADDR_ANY) {
			/* Change address inside packet to match way we're mapping
			   this connection. */
			DEBUGP("ip_nat_talk_mangle_packet: message orig addr %u.%u.%u.%u:%u, inserting %u.%u.%u.%u:%u\n", 
			       NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
			       NIPQUAD(ct->tuplehash[IP_CT_DIR_REPLY].tuple.dst.ip), 
			       ntohs(addr->ta_port));
			addr->ta_addr = ct->tuplehash[IP_CT_DIR_REPLY].tuple.dst.ip;
		}
		DEBUGP("ip_nat_talk_mangle_packet: message orig ctl_addr %u.%u.%u.%u:%u, inserting %u.%u.%u.%u:%u\n", 
		       NIPQUAD(ctl_addr->ta_addr), ntohs(ctl_addr->ta_port),
		       NIPQUAD(newip), ntohs(port));
		ctl_addr->ta_addr = newip;
		ctl_addr->ta_port = port;
	}

	/* Fix checksums */
	(*pskb)->csum = csum_partial((char *)udph + sizeof(struct udphdr), udplen - sizeof(struct udphdr), 0);
	udph->check = 0;
	udph->check = csum_tcpudp_magic(iph->saddr, iph->daddr, udplen, IPPROTO_UDP,
				        csum_partial((char *)udph, sizeof(struct udphdr), (*pskb)->csum));
		
	ip_send_check(iph);
	return 1;
}

static int talk_help_msg(struct ip_conntrack *ct,
			 struct sk_buff **pskb,
		         u_char type,
		         struct talk_addr *addr,
		         struct talk_addr *ctl_addr)
{
	u_int32_t newip;
	u_int16_t port;
	
	unsigned int verdict = NF_ACCEPT;

	DEBUGP("ip_nat_talk_help_msg: addr: %u.%u.%u.%u:%u, ctl_addr: %u.%u.%u.%u:%u, type %d\n",
		NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
		NIPQUAD(ctl_addr->ta_addr), ntohs(ctl_addr->ta_port),
		type);

	/* Change address inside packet to match way we're mapping
	   this connection. */
	newip = ct->tuplehash[IP_CT_DIR_REPLY].tuple.dst.ip;
	port  = ct->tuplehash[IP_CT_DIR_REPLY].tuple.dst.u.udp.port;
	DEBUGP("ip_nat_talk_help_msg: inserting: %u.%u.%u.%u:%u\n",
		NIPQUAD(newip), ntohs(port));

	if (!mangle_packet(pskb, ct, newip, port, addr, ctl_addr))
		verdict = NF_DROP;

	return verdict;
}

static int talk_help_response(struct ip_conntrack *ct,
			      struct ip_conntrack_expect *exp,
			      struct sk_buff **pskb,
		              u_char type,
		              u_char answer,
		              struct talk_addr *addr)
{
	u_int32_t newip;
	u_int16_t port;
	struct ip_conntrack_tuple t;
	struct ip_ct_talk_expect *ct_talk_info;

	DEBUGP("ip_nat_talk_help_response: addr: %u.%u.%u.%u:%u, type %d answer %d\n",
		NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
		type, answer);
	
	LOCK_BH(&ip_talk_lock);
	ct_talk_info = &exp->help.exp_talk_info;

	if (!(answer == SUCCESS 
	      && (type == LOOK_UP || type == ANNOUNCE)
	      && exp != NULL)) {
		UNLOCK_BH(&ip_talk_lock);
		return NF_ACCEPT;
	}
		
	DEBUGP("ip_nat_talk_help_response: talkinfo port %u (%s)\n", 
		ntohs(ct_talk_info->port), 
		type == LOOK_UP ? "LOOK_UP" : "ANNOUNCE");

	/* Change address inside packet to match way we're mapping
	   this connection. */
	newip = ct->tuplehash[type == LOOK_UP ? IP_CT_DIR_ORIGINAL : 
						IP_CT_DIR_REPLY].tuple.dst.ip;
	/* We can read expect here without conntrack lock, since it's
	   only set in ip_conntrack_talk , with ip_talk_lock held
	   writable */ 
	t = exp->tuple;
	t.dst.ip = newip;

	/* Try to get same port: if not, try to change it. */
	for (port = ntohs(ct_talk_info->port); port != 0; port++) {
		if (type == LOOK_UP)
			t.dst.u.tcp.port = htons(port);
		else
			t.dst.u.udp.port = htons(port);

		if (ip_conntrack_change_expect(exp, &t) == 0) {
			DEBUGP("ip_nat_talk_help_response: using %u.%u.%u.%u:%u\n", NIPQUAD(newip), port);
			break;
		}
	}
	UNLOCK_BH(&ip_talk_lock);

	if (port == 0 || !mangle_packet(pskb, ct, newip, htons(port), addr, NULL))
		return NF_DROP;
	
	return NF_ACCEPT;
}

static unsigned int talk_help(struct ip_conntrack *ct,
			      struct ip_conntrack_expect *exp,
			      struct ip_nat_info *info,
			      enum ip_conntrack_info ctinfo,
			      unsigned int hooknum,
			      struct sk_buff **pskb,
			      int talk_port)
{
	struct iphdr *iph = (*pskb)->nh.iph;
	struct udphdr *udph = (void *)iph + iph->ihl * 4;
	unsigned int udplen = (*pskb)->len - iph->ihl * 4;
	char *data = (char *)udph + sizeof(struct udphdr);
	int dir;

	/* Only mangle things once: original direction in POST_ROUTING
	   and reply direction on PRE_ROUTING. */
	dir = CTINFO2DIR(ctinfo);
	if (!((hooknum == NF_IP_POST_ROUTING && dir == IP_CT_DIR_ORIGINAL)
	      || (hooknum == NF_IP_PRE_ROUTING && dir == IP_CT_DIR_REPLY))) {
		DEBUGP("ip_nat_talk_help: Not touching dir %s at hook %s\n",
		       dir == IP_CT_DIR_ORIGINAL ? "ORIG" : "REPLY",
		       hooknum == NF_IP_POST_ROUTING ? "POSTROUTING"
		       : hooknum == NF_IP_PRE_ROUTING ? "PREROUTING"
		       : hooknum == NF_IP_LOCAL_OUT ? "OUTPUT" : "???");
		return NF_ACCEPT;
	}
	DEBUGP("ip_nat_talk_help: dir %s at hook %s, %u.%u.%u.%u:%u->%u.%u.%u.%u:%u, talk port %d\n",
	       dir == IP_CT_DIR_ORIGINAL ? "ORIG" : "REPLY",
	       hooknum == NF_IP_POST_ROUTING ? "POSTROUTING"
	       : hooknum == NF_IP_PRE_ROUTING ? "PREROUTING"
	       : hooknum == NF_IP_LOCAL_OUT ? "OUTPUT" : "???",
	       NIPQUAD(iph->saddr), ntohs(udph->source),
	       NIPQUAD(iph->daddr), ntohs(udph->dest),
	       talk_port);

	/* Because conntrack does not drop packets, checking must be repeated here... */
	if (talk_port == TALK_PORT) {
		if (dir == IP_CT_DIR_ORIGINAL
		    && udplen == sizeof(struct udphdr) + sizeof(struct talk_msg))
			return talk_help_msg(ct, pskb,
					     ((struct talk_msg *)data)->type, 
					     &(((struct talk_msg *)data)->addr),
					     &(((struct talk_msg *)data)->ctl_addr));
		else if (dir == IP_CT_DIR_REPLY
			 && udplen == sizeof(struct udphdr) + sizeof(struct talk_response))
			return talk_help_response(ct, exp, pskb,
						  ((struct talk_response *)data)->type, 
						  ((struct talk_response *)data)->answer,
						  &(((struct talk_response *)data)->addr));
		else {	
			DEBUGP("ip_nat_talk_help: not talk %s, datalen %u != %u\n",
			       dir == IP_CT_DIR_ORIGINAL ? "message" : "response", 
			       (unsigned)udplen - sizeof(struct udphdr), 
			       dir == IP_CT_DIR_ORIGINAL ? sizeof(struct talk_msg) : sizeof(struct talk_response));
			return NF_DROP;
		}
	} else {
		if (dir == IP_CT_DIR_ORIGINAL) {
			if (ntalk
			    && udplen == sizeof(struct udphdr) + sizeof(struct ntalk_msg)
			    && ((struct ntalk_msg *)data)->vers == NTALK_VERSION)
				return talk_help_msg(ct, pskb,
						     ((struct ntalk_msg *)data)->type, 
						     &(((struct ntalk_msg *)data)->addr),
						     &(((struct ntalk_msg *)data)->ctl_addr));
			else if (ntalk2
			    	 && udplen >= sizeof(struct udphdr) + sizeof(struct ntalk2_msg)
			    	 && ((struct ntalk2_msg *)data)->vers == NTALK2_VERSION
			    	 && udplen == sizeof(struct udphdr) 
			    	 	      + sizeof(struct ntalk2_msg) 
			    	 	      + ((struct ntalk2_msg *)data)->extended)
				return talk_help_msg(ct, pskb,
						     ((struct ntalk2_msg *)data)->type, 
						     &(((struct ntalk2_msg *)data)->addr),
						     &(((struct ntalk2_msg *)data)->ctl_addr));
			else {
				DEBUGP("ip_nat_talk_help: not ntalk/ntalk2 message, datalen %u != %u or %u + max 256\n", 
				       (unsigned)udplen - sizeof(struct udphdr), 
				       sizeof(struct ntalk_msg), sizeof(struct ntalk2_msg));
				return NF_DROP;
			}
		} else {
			if (ntalk
			    && udplen == sizeof(struct udphdr) + sizeof(struct ntalk_response)
			    && ((struct ntalk_response *)data)->vers == NTALK_VERSION)
				return talk_help_response(ct, exp, pskb,
							  ((struct ntalk_response *)data)->type, 
							  ((struct ntalk_response *)data)->answer,
							  &(((struct ntalk_response *)data)->addr));
			else if (ntalk2
			    	 && udplen >= sizeof(struct udphdr) + sizeof(struct ntalk2_response)
			    	 && ((struct ntalk2_response *)data)->vers == NTALK2_VERSION)
				return talk_help_response(ct, exp, pskb,
							  ((struct ntalk2_response *)data)->type, 
							  ((struct ntalk2_response *)data)->answer,
							  &(((struct ntalk2_response *)data)->addr));
			else {
				DEBUGP("ip_nat_talk_help: not ntalk/ntalk2 response, datalen %u != %u or %u + max 256\n", 
				       (unsigned)udplen - sizeof(struct udphdr), 
				       sizeof(struct ntalk_response), sizeof(struct ntalk2_response));
				return NF_DROP;
			}
		}
	}
}

static unsigned int help(struct ip_conntrack *ct,
			 struct ip_conntrack_expect *exp,
			 struct ip_nat_info *info,
			 enum ip_conntrack_info ctinfo,
			 unsigned int hooknum,
			 struct sk_buff **pskb)
{
	return talk_help(ct, exp, info, ctinfo, hooknum, pskb, TALK_PORT);
}

static unsigned int nhelp(struct ip_conntrack *ct,
			  struct ip_conntrack_expect *exp,
			  struct ip_nat_info *info,
			  enum ip_conntrack_info ctinfo,
			  unsigned int hooknum,
			  struct sk_buff **pskb)
{
	return talk_help(ct, exp, info, ctinfo, hooknum, pskb, NTALK_PORT);
}

static unsigned int
talk_nat_expected(struct sk_buff **pskb,
		  unsigned int hooknum,
		  struct ip_conntrack *ct,
		  struct ip_nat_info *info);

static struct ip_nat_helper talk_helpers[2] = 
	{ { { NULL, NULL },
            "talk",					/* name */
            IP_NAT_HELPER_F_ALWAYS, 			/* flags */
            THIS_MODULE,				/* module */
            { { 0, { .udp = { __constant_htons(TALK_PORT) } } }, /* tuple */
              { 0, { 0 }, IPPROTO_UDP } },
            { { 0, { .udp = { 0xFFFF } } },		/* mask */
              { 0, { 0 }, 0xFFFF } },
            help, 					/* helper */
            talk_nat_expected },			/* expectfn */
	  { { NULL, NULL },
            "ntalk", 					/* name */
            IP_NAT_HELPER_F_ALWAYS, 			/* flags */
            THIS_MODULE,					/* module */
            { { 0, { .udp = { __constant_htons(NTALK_PORT) } } }, /* tuple */
              { 0, { 0 }, IPPROTO_UDP } },
            { { 0, { .udp = { 0xFFFF } } },		/* mask */
              { 0, { 0 }, 0xFFFF } },
            nhelp, 					/* helper */
            talk_nat_expected }				/* expectfn */
	};
          
static unsigned int
talk_nat_expected(struct sk_buff **pskb,
		  unsigned int hooknum,
		  struct ip_conntrack *ct,
		  struct ip_nat_info *info)
{
	struct ip_nat_multi_range mr;
	u_int32_t newdstip, newsrcip, newip;
	u_int16_t port;
	unsigned int ret;
	
	struct ip_conntrack *master = master_ct(ct);

	IP_NF_ASSERT(info);
	IP_NF_ASSERT(master);

	IP_NF_ASSERT(!(info->initialized & (1<<HOOK2MANIP(hooknum))));

	DEBUGP("ip_nat_talk_expected: We have a connection!\n");

	LOCK_BH(&ip_talk_lock);
	port = ct->master->help.exp_talk_info.port;
	UNLOCK_BH(&ip_talk_lock);

	DEBUGP("ip_nat_talk_expected: dir %s at hook %s, ct %p, master %p\n",
	       CTINFO2DIR((*pskb)->nfct - ct->infos) == IP_CT_DIR_ORIGINAL ? "ORIG" : "REPLY",
	       hooknum == NF_IP_POST_ROUTING ? "POSTROUTING"
	       : hooknum == NF_IP_PRE_ROUTING ? "PREROUTING"
	       : hooknum == NF_IP_LOCAL_OUT ? "OUTPUT" : "???",
	       ct, master);

	if (ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.dst.protonum == IPPROTO_UDP) {
		/* Callee client -> caller server */
#ifdef IP_NAT_TALK_DEBUG
		struct iphdr *iph = (*pskb)->nh.iph;
		struct udphdr *udph = (void *)iph + iph->ihl * 4;

		DEBUGP("ip_nat_talk_expected: UDP %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
		       NIPQUAD(iph->saddr), ntohs(udph->source),
		       NIPQUAD(iph->daddr), ntohs(udph->dest));
#endif
		newdstip = master->tuplehash[IP_CT_DIR_ORIGINAL].tuple.src.ip;
		newsrcip = master->tuplehash[IP_CT_DIR_ORIGINAL].tuple.dst.ip;
		DEBUGP("ip_nat_talk_expected: callee client -> caller server, newsrc: %u.%u.%u.%u, newdst: %u.%u.%u.%u\n",
		       NIPQUAD(newsrcip), NIPQUAD(newdstip));
	} else {
		/* Callee client -> caller client */
#ifdef IP_NAT_TALK_DEBUG
		struct iphdr *iph = (*pskb)->nh.iph;
		struct tcphdr *tcph = (void *)iph + iph->ihl * 4;

		DEBUGP("ip_nat_talk_expected: TCP %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
		       NIPQUAD(iph->saddr), ntohs(tcph->source),
		       NIPQUAD(iph->daddr), ntohs(tcph->dest));
#endif
		newdstip = master->tuplehash[IP_CT_DIR_REPLY].tuple.src.ip;
		newsrcip = master->tuplehash[IP_CT_DIR_REPLY].tuple.dst.ip;
		DEBUGP("ip_nat_talk_expected: callee client -> caller client, newsrc: %u.%u.%u.%u, newdst: %u.%u.%u.%u\n",
		       NIPQUAD(newsrcip), NIPQUAD(newdstip));
	}
	if (HOOK2MANIP(hooknum) == IP_NAT_MANIP_SRC)
		newip = newsrcip;
	else
		newip = newdstip;

	DEBUGP("ip_nat_talk_expected: IP to %u.%u.%u.%u, port %u\n", NIPQUAD(newip), ntohs(port));

	mr.rangesize = 1;
	/* We don't want to manip the per-protocol, just the IPs... */
	mr.range[0].flags = IP_NAT_RANGE_MAP_IPS;
	mr.range[0].min_ip = mr.range[0].max_ip = newip;
	
	/* ... unless we're doing a MANIP_DST, in which case, make
	   sure we map to the correct port */
	if (HOOK2MANIP(hooknum) == IP_NAT_MANIP_DST) {
		mr.range[0].flags |= IP_NAT_RANGE_PROTO_SPECIFIED;
		mr.range[0].min = mr.range[0].max
			= ((union ip_conntrack_manip_proto)
				{ .udp = { port } });
	}
	ret = ip_nat_setup_info(ct, &mr, hooknum);

	if (ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.dst.protonum == IPPROTO_UDP) {
		DEBUGP("talk_expected: setting NAT helper for %p\n", ct);
		/* NAT expectfn called with ip_nat_lock write-locked */
		info->helper = &talk_helpers[htons(port) - TALK_PORT];
	}
	return ret;
}

static int __init init(void)
{
	int ret = 0;

	if (talk > 0) {
		ret = ip_nat_helper_register(&talk_helpers[0]);

		if (ret != 0)
			return ret;
	}
	if (ntalk > 0 || ntalk2 > 0) {
		ret = ip_nat_helper_register(&talk_helpers[1]);

		if (ret != 0 && talk > 0)
			ip_nat_helper_unregister(&talk_helpers[0]);
	}
	return ret;
}

static void __exit fini(void)
{
	if (talk > 0)
		ip_nat_helper_unregister(&talk_helpers[0]);
	if (ntalk > 0 || ntalk2 > 0)
		ip_nat_helper_unregister(&talk_helpers[1]);
}

module_init(init);
module_exit(fini);
