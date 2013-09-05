/* 
 * talk extension for IP connection tracking. 
 * Jozsef Kadlecsik <kadlec@blackhole.kfki.hu>
 *
 *      This program is free software; you can redistribute it and/or
 *      modify it under the terms of the GNU General Public License
 *      as published by the Free Software Foundation; either version
 *      2 of the License, or (at your option) any later version.
 **
 *     Module load syntax:
 *     insmod ip_nat_talk.o talk=[0|1] ntalk=[0|1] ntalk2=[01]
 *
 *		talk=[0|1]	disable|enable old talk support
 *	       ntalk=[0|1]	disable|enable ntalk support
 *	      ntalk2=[0|1]	disable|enable ntalk2 support
 *
 *     The default is talk=1 ntalk=1 ntalk2=1
 *
 *     The helper does not support simultaneous talk requests.
 **
 *
 *		ASCII art on talk protocols
 *	
 *	
 *	caller server		    callee server
 *		|     \	          /
 *		|	\       /
 *		|	  \   /
 *		|	    /  
 *	 	|	  /   \
 *	      2 |     1 /       \ 3
 *	caller client  ----------- callee client
 *	               		 4
 *
 *	1. caller client <-> callee server: LOOK_UP, then ANNOUNCE invitation 
 *    ( 2. caller client <-> caller server: LEAVE_INVITE to server )
 *	3. callee client <-> caller server: LOOK_UP invitation
 *	4. callee client <-> caller client: talk data channel
 *
 * [1]: M. Hunter, talk: a historical protocol for interactive communication
 *      draft-hunter-talk-00.txt
 * [2]: D.B. Chapman, E.D. Zwicky: Building Internet Firewalls (O'Reilly)	
 */
#include <linux/config.h>
#include <linux/module.h>
#include <linux/netfilter.h>
#include <linux/ip.h>
#include <net/checksum.h>
#include <net/udp.h>

#include <linux/netfilter_ipv4/lockhelp.h>
#include <linux/netfilter_ipv4/ip_conntrack.h>
#include <linux/netfilter_ipv4/ip_conntrack_core.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_talk.h>

/* Default all talk protocols are supported */
static int talk = 1;
static int ntalk = 1;
static int ntalk2 = 1;
MODULE_AUTHOR("Jozsef Kadlecsik <kadlec@blackhole.kfki.hu>");
MODULE_DESCRIPTION("talk connection tracking module");
MODULE_LICENSE("GPL");
#ifdef MODULE_PARM
MODULE_PARM(talk, "i");
MODULE_PARM_DESC(talk, "support (old) talk protocol");
MODULE_PARM(ntalk, "i");
MODULE_PARM_DESC(ntalk, "support ntalk protocol");
MODULE_PARM(ntalk2, "i");
MODULE_PARM_DESC(ntalk2, "support ntalk2 protocol");
#endif

DECLARE_LOCK(ip_talk_lock);
struct module *ip_conntrack_talk = THIS_MODULE;

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif

static int talk_expect(struct ip_conntrack *ct);
static int ntalk_expect(struct ip_conntrack *ct);

static int (*talk_expectfn[2])(struct ip_conntrack *ct) = {talk_expect, ntalk_expect};

static int talk_help_response(const struct iphdr *iph, size_t len,
		              struct ip_conntrack *ct,
		              enum ip_conntrack_info ctinfo,
		              int talk_port,
		              u_char mode,
		              u_char type,
		              u_char answer,
		              struct talk_addr *addr)
{
	int dir = CTINFO2DIR(ctinfo);
	struct ip_conntrack_expect expect, *exp = &expect;
	struct ip_ct_talk_expect *exp_talk_info = &exp->help.exp_talk_info;

	DEBUGP("ip_ct_talk_help_response: %u.%u.%u.%u:%u, type %d answer %d\n",
		NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
		type, answer);

	if (!(answer == SUCCESS && type == mode))
		return NF_ACCEPT;
	
	memset(&expect, 0, sizeof(expect));
	
	if (type == ANNOUNCE) {

		DEBUGP("ip_ct_talk_help_response: ANNOUNCE\n");

		/* update the talk info */
		LOCK_BH(&ip_talk_lock);
		exp_talk_info->port = htons(talk_port);

		/* expect callee client -> caller server message */
		exp->tuple = ((struct ip_conntrack_tuple)
			{ { ct->tuplehash[dir].tuple.src.ip,
			    { 0 } },
			  { ct->tuplehash[dir].tuple.dst.ip,
			    { .tcp = { htons(talk_port) } },
			    IPPROTO_UDP }});
		exp->mask = ((struct ip_conntrack_tuple)
			{ { 0xFFFFFFFF, { 0 } },
			  { 0xFFFFFFFF, { .tcp = { 0xFFFF } }, 0xFFFF }});
		
		exp->expectfn = talk_expectfn[talk_port - TALK_PORT];

		DEBUGP("ip_ct_talk_help_response: callee client %u.%u.%u.%u:%u -> caller daemon %u.%u.%u.%u:%u!\n",
		       NIPQUAD(exp->tuple.src.ip), ntohs(exp->tuple.src.u.udp.port),
		       NIPQUAD(exp->tuple.dst.ip), ntohs(exp->tuple.dst.u.udp.port));

		/* Ignore failure; should only happen with NAT */
		ip_conntrack_expect_related(ct, &expect);
		UNLOCK_BH(&ip_talk_lock);
	}
	if (type == LOOK_UP) {

		DEBUGP("ip_ct_talk_help_response: LOOK_UP\n");

		/* update the talk info */
		LOCK_BH(&ip_talk_lock);
		exp_talk_info->port = addr->ta_port;

		/* expect callee client -> caller client connection */
		exp->tuple = ((struct ip_conntrack_tuple)
			{ { ct->tuplehash[!dir].tuple.src.ip,
			    { 0 } },
			  { addr->ta_addr,
			    { addr->ta_port },
			    IPPROTO_TCP }});
		exp->mask = ((struct ip_conntrack_tuple)
			{ { 0xFFFFFFFF, { 0 } },
			  { 0xFFFFFFFF, { 0xFFFF }, 0xFFFF }});
		
		exp->expectfn = NULL;
		
		DEBUGP("ip_ct_talk_help_response: callee client %u.%u.%u.%u:%u -> caller client %u.%u.%u.%u:%u!\n",
		       NIPQUAD(exp->tuple.src.ip), ntohs(exp->tuple.src.u.tcp.port),
		       NIPQUAD(exp->tuple.dst.ip), ntohs(exp->tuple.dst.u.tcp.port));

		/* Ignore failure; should only happen with NAT */
		ip_conntrack_expect_related(ct, &expect);
		UNLOCK_BH(&ip_talk_lock);
	}
		    
	return NF_ACCEPT;
}

/* FIXME: This should be in userspace.  Later. */
static int talk_help(const struct iphdr *iph, size_t len,
		     struct ip_conntrack *ct,
		     enum ip_conntrack_info ctinfo,
		     int talk_port,
		     u_char mode)
{
	struct udphdr *udph = (void *)iph + iph->ihl * 4;
	const char *data = (const char *)udph + sizeof(struct udphdr);
	int dir = CTINFO2DIR(ctinfo);
	size_t udplen;

	DEBUGP("ip_ct_talk_help: help entered\n");

	/* Until there's been traffic both ways, don't look in packets. */
	if (ctinfo != IP_CT_ESTABLISHED
	    && ctinfo != IP_CT_ESTABLISHED + IP_CT_IS_REPLY) {
		DEBUGP("ip_ct_talk_help: Conntrackinfo = %u\n", ctinfo);
		return NF_ACCEPT;
	}

	/* Not whole UDP header? */
	udplen = len - iph->ihl * 4;
	if (udplen < sizeof(struct udphdr)) {
		DEBUGP("ip_ct_talk_help: too short for udph, udplen = %u\n", (unsigned)udplen);
		return NF_ACCEPT;
	}

	/* Checksum invalid?  Ignore. */
	/* FIXME: Source route IP option packets --RR */
	if (csum_tcpudp_magic(iph->saddr, iph->daddr, udplen, IPPROTO_UDP,
			      csum_partial((char *)udph, udplen, 0))) {
		DEBUGP("ip_ct_talk_help: bad csum: %p %u %u.%u.%u.%u %u.%u.%u.%u\n",
		       udph, udplen, NIPQUAD(iph->saddr),
		       NIPQUAD(iph->daddr));
		return NF_ACCEPT;
	}
	
	DEBUGP("ip_ct_talk_help: %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
		NIPQUAD(iph->saddr), ntohs(udph->source), NIPQUAD(iph->daddr), ntohs(udph->dest));

	if (dir == IP_CT_DIR_ORIGINAL)
		return NF_ACCEPT;
		
	if (talk_port == TALK_PORT
	    && udplen == sizeof(struct udphdr) + sizeof(struct talk_response))
		return talk_help_response(iph, len, ct, ctinfo, talk_port, mode,
					  ((struct talk_response *)data)->type, 
					  ((struct talk_response *)data)->answer,
					  &(((struct talk_response *)data)->addr));
	else if (talk_port == NTALK_PORT
	 	  && ntalk
		  && udplen == sizeof(struct udphdr) + sizeof(struct ntalk_response)
		  && ((struct ntalk_response *)data)->vers == NTALK_VERSION)
		return talk_help_response(iph, len, ct, ctinfo, talk_port, mode,
					  ((struct ntalk_response *)data)->type, 
					  ((struct ntalk_response *)data)->answer,
					  &(((struct ntalk_response *)data)->addr));
	else if (talk_port == NTALK_PORT
		 && ntalk2
		 && udplen >= sizeof(struct udphdr) + sizeof(struct ntalk2_response)
		 && ((struct ntalk2_response *)data)->vers == NTALK2_VERSION)
		return talk_help_response(iph, len, ct, ctinfo, talk_port, mode,
					  ((struct ntalk2_response *)data)->type, 
					  ((struct ntalk2_response *)data)->answer,
					  &(((struct ntalk2_response *)data)->addr));
	else {
		DEBUGP("ip_ct_talk_help: not ntalk/ntalk2 response, datalen %u != %u or %u + max 256\n", 
		       (unsigned)udplen - sizeof(struct udphdr), 
		       sizeof(struct ntalk_response), sizeof(struct ntalk2_response));
		return NF_ACCEPT;
	}
}

static int lookup_help(const struct iphdr *iph, size_t len,
		       struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(iph, len, ct, ctinfo, TALK_PORT, LOOK_UP);
}

static int lookup_nhelp(const struct iphdr *iph, size_t len,
		        struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(iph, len, ct, ctinfo, NTALK_PORT, LOOK_UP);
}

static struct ip_conntrack_helper lookup_helpers[2] = 
	{ { { NULL, NULL },
	    "talk",					/* name */
	    0,						/* flags */
	    NULL,					/* module */
	    1,						/* max_expected */
	    240,					/* timeout */
            { { 0, { __constant_htons(TALK_PORT) } },	/* tuple */
	      { 0, { 0 }, IPPROTO_UDP } },
	    { { 0, { 0xFFFF } },			/* mask */
	      { 0, { 0 }, 0xFFFF } },
	    lookup_help },				/* helper */
          { { NULL, NULL },
            "ntalk",					/* name */
	    0,						/* flags */
	    NULL,					/* module */
	    1,						/* max_expected */
	    240,					/* timeout */
	    { { 0, { __constant_htons(NTALK_PORT) } },	/* tuple */
	      { 0, { 0 }, IPPROTO_UDP } },
	    { { 0, { 0xFFFF } },			/* mask */
	      { 0, { 0 }, 0xFFFF } },
    	    lookup_nhelp }				/* helper */
        };

static int talk_expect(struct ip_conntrack *ct)
{
	DEBUGP("ip_conntrack_talk: calling talk_expectfn for ct %p\n", ct);
	WRITE_LOCK(&ip_conntrack_lock);
	ct->helper = &lookup_helpers[0];
	WRITE_UNLOCK(&ip_conntrack_lock);
	 
	return NF_ACCEPT;       /* unused */
}

static int ntalk_expect(struct ip_conntrack *ct)
{
	DEBUGP("ip_conntrack_talk: calling ntalk_expectfn for ct %p\n", ct);
	WRITE_LOCK(&ip_conntrack_lock);
	ct->helper = &lookup_helpers[1];
	WRITE_UNLOCK(&ip_conntrack_lock);
	 
	return NF_ACCEPT;       /* unused */
}

static int help(const struct iphdr *iph, size_t len,
		struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(iph, len, ct, ctinfo, TALK_PORT, ANNOUNCE);
}

static int nhelp(const struct iphdr *iph, size_t len,
		 struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(iph, len, ct, ctinfo, NTALK_PORT, ANNOUNCE);
}

static struct ip_conntrack_helper talk_helpers[2] = 
	{ { { NULL, NULL },
	    "talk",					/* name */
	    0,						/* flags */
	    THIS_MODULE,				/* module */
	    1,						/* max_expected */
	    240,					/* timeout */
	    { { 0, { __constant_htons(TALK_PORT) } },	/* tuple */
 	      { 0, { 0 }, IPPROTO_UDP } },
	    { { 0, { 0xFFFF } },			/* mask */
	      { 0, { 0 }, 0xFFFF } },
	    help },					/* helper */
          { { NULL, NULL },
	    "ntalk",					/* name */
	    0,						/* flags */
	    THIS_MODULE,				/* module */
	    1,						/* max_expected */
	    240,					/* timeout */
	    { { 0, { __constant_htons(NTALK_PORT) } },	/* tuple */
	      { 0, { 0 }, IPPROTO_UDP } },
	    { { 0, { 0xFFFF } },			/* mask */
	      { 0, { 0 }, 0xFFFF } },
	    nhelp }					/* helper */
	};

static int __init init(void)
{
	if (talk > 0)
		ip_conntrack_helper_register(&talk_helpers[0]);
	if (ntalk > 0 || ntalk2 > 0)
		ip_conntrack_helper_register(&talk_helpers[1]);
		
	return 0;
}

static void __exit fini(void)
{
	if (talk > 0)
		ip_conntrack_helper_unregister(&talk_helpers[0]);
	if (ntalk > 0 || ntalk2 > 0)
		ip_conntrack_helper_unregister(&talk_helpers[1]);
}

EXPORT_SYMBOL(ip_talk_lock);

module_init(init);
module_exit(fini);
