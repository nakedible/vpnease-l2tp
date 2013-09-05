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
 *
 * Modifications:
 * 2005-02-13 Harald Welte <laforge@netfilter.org>
 * 	- update to 2.6.x API
 * 	- update to post 2.6.11 helper infrastructure
 * 	- use c99 structure initializers
 * 	- explicitly allocate expectation
 *
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
module_param(talk, int, 0400);
MODULE_PARM_DESC(talk, "support (old) talk protocol");
module_param(ntalk, int, 0400);
MODULE_PARM_DESC(ntalk, "support ntalk protocol");
module_param(ntalk2, int, 0400);
MODULE_PARM_DESC(ntalk2, "support ntalk2 protocol");

static char talk_buffer[65536];
static DECLARE_LOCK(talk_buffer_lock);

unsigned int (*ip_nat_talk_resp_hook)(struct sk_buff **pskb,
				      struct ip_conntrack_expect *exp,
				      u_char type,
				      u_char answer,
				      struct talk_addr *addr);
EXPORT_SYMBOL_GPL(ip_nat_talk_resp_hook);

unsigned int (*ip_nat_talk_msg_hook)(struct sk_buff **pskb,
				     struct ip_conntrack *ct,
				     u_char type,
				     struct talk_addr *addr,
				     struct talk_addr *ctl_addr);
EXPORT_SYMBOL_GPL(ip_nat_talk_msg_hook);

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif

void ip_ct_talk_expect(struct ip_conntrack *ct,
		       struct ip_conntrack_expect *exp);
void ip_ct_ntalk_expect(struct ip_conntrack *ct,
			struct ip_conntrack_expect *exp);

static void (*talk_expectfn[2])(struct ip_conntrack *ct,
				struct ip_conntrack_expect *exp) = {
					ip_ct_talk_expect,
					ip_ct_ntalk_expect };

static int talk_help_response(struct sk_buff **pskb,
		              struct ip_conntrack *ct,
		              enum ip_conntrack_info ctinfo,
		              int talk_port,
		              u_char mode,
		              u_char type,
		              u_char answer,
		              struct talk_addr *addr)
{
	int ret;
	int dir = CTINFO2DIR(ctinfo);
	struct ip_conntrack_expect *exp;
	u_int16_t exp_talk_port;

	DEBUGP("ip_ct_talk_help_response: %u.%u.%u.%u:%u, type %d answer %d\n",
		NIPQUAD(addr->ta_addr), ntohs(addr->ta_port),
		type, answer);

	if (!(answer == SUCCESS && type == mode))
		return NF_ACCEPT;
	
	exp = ip_conntrack_expect_alloc();
	if (exp == NULL) {
		return NF_DROP;
	}
	
	if (type == ANNOUNCE) {

		DEBUGP("ip_ct_talk_help_response: ANNOUNCE\n");

		/* update the talk info */
		exp_talk_port = htons(talk_port);

		/* expect callee client -> caller server message */
		exp->tuple = ((struct ip_conntrack_tuple)
			{ { ct->tuplehash[dir].tuple.src.ip,
			    { 0 } },
			  { ct->tuplehash[dir].tuple.dst.ip,
			    { .udp = { htons(talk_port) } },
			    IPPROTO_UDP }});
		exp->mask = ((struct ip_conntrack_tuple)
			{ { 0xFFFFFFFF, { 0 } },
			  { 0xFFFFFFFF, { .tcp = { 0xFFFF } }, 0xFF }});
		
		exp->expectfn = talk_expectfn[talk_port - TALK_PORT];
		exp->master = ct;

		DEBUGP("ip_ct_talk_help_response: callee client "
		       "%u.%u.%u.%u:%u -> caller daemon %u.%u.%u.%u:%u!\n",
		       NIPQUAD(exp->tuple.src.ip), 
		       ntohs(exp->tuple.src.u.udp.port),
		       NIPQUAD(exp->tuple.dst.ip), 
		       ntohs(exp->tuple.dst.u.udp.port));

		if (ip_nat_talk_resp_hook)
			ret = ip_nat_talk_resp_hook(pskb, exp, type, answer, 
						    addr);
		else if (ip_conntrack_expect_related(exp) != 0) {
			ip_conntrack_expect_free(exp);
			ret = NF_DROP;
		}
	} else if (type == LOOK_UP) {

		DEBUGP("ip_ct_talk_help_response: LOOK_UP\n");

		/* update the talk info */
		exp_talk_port = addr->ta_port;

		/* expect callee client -> caller client connection */
		exp->tuple = ((struct ip_conntrack_tuple)
			{ { ct->tuplehash[!dir].tuple.src.ip,
			    { 0 } },
			  { addr->ta_addr,
			    { addr->ta_port },
			    IPPROTO_TCP }});
		exp->mask = ((struct ip_conntrack_tuple)
			{ { 0xFFFFFFFF, { 0 } },
			  { 0xFFFFFFFF, { 0xFFFF }, 0xFF }});
		exp->expectfn = NULL;
		exp->master = ct;

		DEBUGP("ip_ct_talk_help_response: callee client "
		       "%u.%u.%u.%u:%u -> caller client %u.%u.%u.%u:%u!\n",
		       NIPQUAD(exp->tuple.src.ip),
		       ntohs(exp->tuple.src.u.tcp.port),
		       NIPQUAD(exp->tuple.dst.ip),
		       ntohs(exp->tuple.dst.u.tcp.port));

		if (ip_nat_talk_resp_hook)
			ret = ip_nat_talk_resp_hook(pskb, exp, type, answer, 
						    addr);
		else if (ip_conntrack_expect_related(exp) != 0) {
			ip_conntrack_expect_free(exp);
			ret = NF_DROP;
		}
	}
		    
	return NF_ACCEPT;
}

/* FIXME: This should be in userspace.  Later. */
static int talk_help(struct sk_buff **pskb,
		     struct ip_conntrack *ct,
		     enum ip_conntrack_info ctinfo,
		     int talk_port,
		     u_char mode)
{
	int ret;
	unsigned int dataoff;
	struct udphdr _udph, *uh;
	char *tb_ptr, *data;
	//struct udphdr *udph = (void *)iph + iph->ihl * 4;
	//const char *data = (const char *)udph + sizeof(struct udphdr);
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
	uh = skb_header_pointer(*pskb, (*pskb)->nh.iph->ihl*4,
				sizeof(_udph), &_udph);
	if (uh == NULL) {
		DEBUGP("ip_ct_talk_help: short for udph\n");
		return NF_ACCEPT;
	}

	udplen = (*pskb)->len - (*pskb)->nh.iph->ihl*4;
	dataoff = (*pskb)->nh.iph->ihl*4 + sizeof(_udph);
	if (dataoff >= (*pskb)->len)
		return NF_ACCEPT;

	LOCK_BH(&talk_buffer_lock);
	tb_ptr = skb_header_pointer(*pskb, dataoff,
				    (*pskb)->len - dataoff, talk_buffer);
	BUG_ON(tb_ptr == NULL);

	data = tb_ptr;
	
	DEBUGP("ip_ct_talk_help: %u.%u.%u.%u:%u->%u.%u.%u.%u:%u\n",
		NIPQUAD(iph->saddr), ntohs(udph->source), NIPQUAD(iph->daddr), ntohs(udph->dest));

	if (dir == IP_CT_DIR_ORIGINAL && ip_nat_talk_msg_hook) {
		if (talk_port == TALK_PORT) {
			if (udplen == sizeof(struct udphdr) + 
					sizeof(struct talk_msg)) {
				struct talk_msg *tm = (struct talk_msg *)data;
				return ip_nat_talk_msg_hook(pskb, ct, tm->type,
						&tm->addr, &tm->ctl_addr);
			}
		} else {
			if (ntalk &&
			    udplen == sizeof(struct udphdr) +
			    		sizeof(struct ntalk_msg) &&
			    ((struct ntalk_msg *)data)->vers == NTALK_VERSION){
				struct ntalk_msg *tm = (struct ntalk_msg *)data;
				return ip_nat_talk_msg_hook(pskb, ct, tm->type,
						&tm->addr, &tm->ctl_addr);
			} else if (ntalk2 &&
				   udplen >= sizeof(struct udphdr) +
				   		sizeof(struct ntalk2_msg) &&
				   ((struct ntalk2_msg *)data)->vers == NTALK2_VERSION &&
				   udplen == sizeof(struct udphdr)
				   	     + sizeof(struct ntalk2_msg)
					     + ((struct ntalk2_msg *)data)->extended) {
				struct ntalk2_msg *tm = (struct ntalk2_msg *)data;
				return ip_nat_talk_msg_hook(pskb, ct, tm->type,
						&tm->addr, &tm->ctl_addr);
			}
		}
		return NF_ACCEPT;
	}
		
	/* only DIR_REPLY */
	if (talk_port == TALK_PORT
	    && udplen == sizeof(struct udphdr) + sizeof(struct talk_response))
		ret = talk_help_response(pskb, ct, ctinfo, talk_port, mode,
					  ((struct talk_response *)data)->type, 
					  ((struct talk_response *)data)->answer,
					  &(((struct talk_response *)data)->addr));
	else if (talk_port == NTALK_PORT
	 	  && ntalk
		  && udplen == sizeof(struct udphdr) + sizeof(struct ntalk_response)
		  && ((struct ntalk_response *)data)->vers == NTALK_VERSION)
		ret = talk_help_response(pskb, ct, ctinfo, talk_port, mode,
					  ((struct ntalk_response *)data)->type, 
					  ((struct ntalk_response *)data)->answer,
					  &(((struct ntalk_response *)data)->addr));
	else if (talk_port == NTALK_PORT
		 && ntalk2
		 && udplen >= sizeof(struct udphdr) + sizeof(struct ntalk2_response)
		 && ((struct ntalk2_response *)data)->vers == NTALK2_VERSION)
		ret = talk_help_response(pskb, ct, ctinfo, talk_port, mode,
					  ((struct ntalk2_response *)data)->type, 
					  ((struct ntalk2_response *)data)->answer,
					  &(((struct ntalk2_response *)data)->addr));
	else {
		DEBUGP("ip_ct_talk_help: not ntalk/ntalk2 response, datalen %u != %u or %u + max 256\n", 
		       (unsigned)udplen - sizeof(struct udphdr), 
		       sizeof(struct ntalk_response), sizeof(struct ntalk2_response));
		ret = NF_ACCEPT;
	}
	UNLOCK_BH(&talk_buffer_lock);
	return ret;
}

static int lookup_help(struct sk_buff **pskb,
		       struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(pskb, ct, ctinfo, TALK_PORT, LOOK_UP);
}

static int lookup_nhelp(struct sk_buff **pskb,
		        struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(pskb, ct, ctinfo, NTALK_PORT, LOOK_UP);
}

static struct ip_conntrack_helper lookup_helpers[2] = { 
	{ 
		.name		= "talk-lookup",
		.max_expected	= 1,
		.timeout	= 4 * 60,
		.tuple		= {
				.src.u.udp.port = __constant_htons(TALK_PORT),
				.dst.protonum	= IPPROTO_UDP,
			},
		.mask		= {
				.src.u.udp.port	= 0xffff,
				.dst.protonum	= 0xff,
			},
		.help		= &lookup_help,
	},
	{
		.name		= "ntalk-lookup",
		.max_expected	= 1,
		.timeout	= 4 * 60,
		.tuple		= {
				.src.u.udp.port = __constant_htons(NTALK_PORT),
				.dst.protonum	= IPPROTO_UDP,
			},
		.mask		= {
				.src.u.udp.port = 0xffff,
				.dst.protonum	= 0xff,
			},
		.help		= &lookup_nhelp,
	},
};

void ip_ct_talk_expect(struct ip_conntrack *ct,
		       struct ip_conntrack_expect *exp)
{
	DEBUGP("ip_conntrack_talk: calling talk_expectfn for ct %p\n", ct);
	WRITE_LOCK(&ip_conntrack_lock);
	ct->helper = &lookup_helpers[0];
	WRITE_UNLOCK(&ip_conntrack_lock);
}

void ip_ct_ntalk_expect(struct ip_conntrack *ct,
		        struct ip_conntrack_expect *exp)
{
	DEBUGP("ip_conntrack_talk: calling ntalk_expectfn for ct %p\n", ct);
	WRITE_LOCK(&ip_conntrack_lock);
	ct->helper = &lookup_helpers[1];
	WRITE_UNLOCK(&ip_conntrack_lock);
}

static int help(struct sk_buff **pskb,
		struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(pskb, ct, ctinfo, TALK_PORT, ANNOUNCE);
}

static int nhelp(struct sk_buff **pskb,
		 struct ip_conntrack *ct, enum ip_conntrack_info ctinfo)
{
	return talk_help(pskb, ct, ctinfo, NTALK_PORT, ANNOUNCE);
}

static struct ip_conntrack_helper talk_helpers[2] = { 
	{ 
		.name 		= "talk",
		.help		= &help,
		.me		= THIS_MODULE,
		.max_expected	= 1,
		.timeout	= 4 * 60,	/* 4 minutes */
		.tuple		= {
				.src.u.udp.port	= __constant_htons(TALK_PORT),
				.dst.protonum	= IPPROTO_UDP,
			},
		.mask		= {
				.src.u.udp.port	= 0xffff,
				.dst.protonum	= 0xff,
			},
	},
	{
		.name		= "ntalk",
		.help		= &nhelp,
		.me		= THIS_MODULE,
		.max_expected	= 1,
		.timeout	= 4 * 60,	/* 4 minutes */
		.tuple		= {
				.src.u.udp.port = __constant_htons(NTALK_PORT),
				.dst.protonum	= IPPROTO_UDP,
			},
		.mask		= {
				.src.u.udp.port	= 0xffff,
				.dst.protonum	= IPPROTO_UDP,
			},
	},
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

module_init(init);
module_exit(fini);
