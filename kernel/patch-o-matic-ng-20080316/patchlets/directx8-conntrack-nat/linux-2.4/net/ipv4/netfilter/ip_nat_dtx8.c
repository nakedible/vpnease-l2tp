/*
 *
 *
 */

#include <linux/module.h>
#include <linux/netfilter_ipv4.h>
#include <linux/ip.h>
#include <linux/udp.h>
#include <net/udp.h>

#include <linux/netfilter.h>
#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_dtx8.h>
#include <linux/netfilter_ipv4/ip_nat_helper.h>
#include <linux/netfilter_ipv4/ip_nat_rule.h>

MODULE_AUTHOR("Eddie Shi <eddieshi@broadcom.com>");
MODULE_DESCRIPTION("Netfilter NAT helper for DirectX8");
MODULE_LICENSE("GPL");

static int ports[MAXDTX8_PORTS];
static int ports_c = 0;
#ifdef MODULE_PARM
MODULE_PARM(ports,"1-" __MODULE_STRING(MAXDTX8_PORTS) "i");
MODULE_PARM_DESC(ports, "port numbers of dtx8");
#endif

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif
static unsigned int 
help(struct ip_conntrack *ct,
	      struct ip_conntrack_expect *exp,
	      struct ip_nat_info *info,
	      enum ip_conntrack_info ctinfo,
	      unsigned int hooknum,
	      struct sk_buff **pskb)
{
	int dir = CTINFO2DIR(ctinfo);
	//struct iphdr *iph = (*pskb)->nh.iph;
	//struct udphdr *udph = (void *)iph + iph->ihl * 4;
	struct ip_conntrack_tuple repl;

	DEBUGP("............... dtx8 hooknum=%d\n",hooknum);
	if (!((hooknum == NF_IP_POST_ROUTING && dir == IP_CT_DIR_ORIGINAL)
	      || (hooknum == NF_IP_PRE_ROUTING && dir == IP_CT_DIR_REPLY))) {
	DEBUGP(" dtx8 hooknum=%d return NF_ACCEPT\n",hooknum);
		return NF_ACCEPT;
	}

	if (!exp) {
		printk("no conntrack expectation to modify\n");
		DEBUGP("no conntrack expectation to modify\n");
		return NF_ACCEPT;
	}

	DEBUGP(" dtx8 .....................\n");
	repl = ct->tuplehash[IP_CT_DIR_REPLY].tuple;
	repl.dst.u.udp.port = exp->tuple.dst.u.udp.port;
	repl.dst.protonum = IPPROTO_UDP;
	DEBUGP(" dtx8 repl.dstport=%d\n",htons(repl.dst.u.udp.port));
	DEBUGP("\n");
	DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple);
	DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_REPLY].tuple);

	DEBUGP("expecting:\n ");
	DUMP_TUPLE(&repl);
	DUMP_TUPLE(&exp->mask);
DEBUGP("dtx8:calling ip_conntrack_change_expect \n"); 
	ip_conntrack_change_expect(exp, &repl);

	return NF_ACCEPT;
}

static unsigned int 
dtx8_nat_expected(struct sk_buff **pskb,
		  unsigned int hooknum,
		  struct ip_conntrack *ct, 
		  struct ip_nat_info *info) 
{
	const struct ip_conntrack *master = ct->master->expectant;
	const struct ip_conntrack_tuple *orig = 
			&master->tuplehash[IP_CT_DIR_ORIGINAL].tuple;
	struct ip_nat_multi_range mr;

	DEBUGP("dtx8_nat_expected hooknum=%d\n",hooknum);
	IP_NF_ASSERT(info);
	IP_NF_ASSERT(master);
	IP_NF_ASSERT(!(info->initialized & (1 << HOOK2MANIP(hooknum))));

	mr.rangesize = 1;
	mr.range[0].flags = IP_NAT_RANGE_MAP_IPS;

#if 1
	//const struct ip_conntrack_tuple *repl =
	//		&master->tuplehash[IP_CT_DIR_REPLY].tuple;
	//struct iphdr *iph = (*pskb)->nh.iph;
	//struct udphdr *udph = (void *)iph + iph->ihl*4;
#endif
	if (HOOK2MANIP(hooknum) == IP_NAT_MANIP_SRC) {
		mr.range[0].min_ip = mr.range[0].max_ip = orig->dst.ip; 
		DEBUGP("MANIPSRC:orig: %u.%u.%u.%u:%u <-> %u.%u.%u.%u:%u "
			"newsrc: %u.%u.%u.%u\n",
                        NIPQUAD((*pskb)->nh.iph->saddr), ntohs(udph->source),
			NIPQUAD((*pskb)->nh.iph->daddr), ntohs(udph->dest),
			NIPQUAD(orig->dst.ip));
	} else {
		mr.range[0].min_ip = mr.range[0].max_ip = orig->src.ip;
		mr.range[0].min.udp.port = mr.range[0].max.udp.port = 
							orig->src.u.udp.port;
		//eshi mr.range[0].flags |= IP_NAT_RANGE_PROTO_SPECIFIED;

		DEBUGP("MANIPDST:orig: %u.%u.%u.%u:%u <-> %u.%u.%u.%u:%u "
			"newdst: %u.%u.%u.%u:%u\n",
                        NIPQUAD((*pskb)->nh.iph->saddr), ntohs(udph->source),
                        NIPQUAD((*pskb)->nh.iph->daddr), ntohs(udph->dest),
                        NIPQUAD(orig->src.ip), ntohs(orig->src.u.udp.port));
	}

DEBUGP("dtx8_nat_expected:calling ip_nat_setup_info\n"); 
	return ip_nat_setup_info(ct,&mr,hooknum);
}

static struct ip_nat_helper dtx8[MAXDTX8_PORTS];
static char dtx8_names[MAXDTX8_PORTS][10];

static void fini(void)
{
	int i;

	for (i = 0 ; i < ports_c; i++) {
		DEBUGP("unregistering helper for port %d\n", ports[i]);
		ip_nat_helper_unregister(&dtx8[i]);
	}
}

static int __init init(void)
{
	int i, ret=0;
	char *tmpname;

	if (!ports[0])
		ports[0] = DTX8INITIAL;

	for (i = 0 ; (i < MAXDTX8_PORTS) && ports[i] ; i++) {
		memset(&dtx8[i], 0, sizeof(struct ip_nat_helper));

		dtx8[i].tuple.src.u.tcp.port = htons(ports[i]);
		dtx8[i].tuple.dst.protonum = IPPROTO_TCP;
		dtx8[i].mask.src.u.tcp.port = 0xFFFF;
		dtx8[i].mask.dst.protonum = 0xFFFF;
		dtx8[i].help = help;
		//dtx8[i].flags = 0;
		//dtx8[i].me = THIS_MODULE;
		dtx8[i].expect = dtx8_nat_expected;

		tmpname = &dtx8_names[i][0];
		if (ports[i] == DTX8INITIAL)
			sprintf(tmpname, "dtx8");
		else
			sprintf(tmpname, "dtx8-%d", i);
		dtx8[i].name = tmpname;
		
		DEBUGP("ip_nat_dtx8: registering for port %d: name %s\n",
			ports[i], dtx8[i].name);
		ret = ip_nat_helper_register(&dtx8[i]);

		if (ret) {
			printk("ip_nat_dtx8: unable to register for port %d\n",
				ports[i]);
			fini();
			return ret;
		}
		ports_c++;
	}
	return ret;
}

module_init(init);
module_exit(fini);
