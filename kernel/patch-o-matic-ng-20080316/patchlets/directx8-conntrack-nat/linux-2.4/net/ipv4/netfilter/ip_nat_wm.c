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
#include <linux/netfilter_ipv4/ip_conntrack_wm.h>
#include <linux/netfilter_ipv4/ip_nat_helper.h>
#include <linux/netfilter_ipv4/ip_nat_rule.h>

//DECLARE_LOCK_EXTERN(ip_wm_lock);
MODULE_AUTHOR("Eddie Shi <eddieshi@broadcom.com>");
MODULE_DESCRIPTION("Netfilter NAT helper for DirectX8");
MODULE_LICENSE("GPL");

static int ports[MAXWM_PORTS];
static int ports_c = 0;
#ifdef MODULE_PARM
MODULE_PARM(ports,"1-" __MODULE_STRING(MAXWM_PORTS) "i");
MODULE_PARM_DESC(ports, "port numbers of wm");
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

//	printk("............... wm_nat_help hooknum=%d\n",hooknum);
	if (!((hooknum == NF_IP_POST_ROUTING && dir == IP_CT_DIR_ORIGINAL)
	      || (hooknum == NF_IP_PRE_ROUTING && dir == IP_CT_DIR_REPLY))) {
	DEBUGP(" wmnat hooknum=%d return NF_ACCEPT\n",hooknum);
		return NF_ACCEPT;
	}

	if (!exp) {
//		printk("no conntrack expectation to modify\n");
		DEBUGP("no conntrack expectation to modify\n");
		return NF_ACCEPT;
	}

	DEBUGP(" wm_nat_help.....................\n");
	repl = ct->tuplehash[IP_CT_DIR_REPLY].tuple;
	repl.dst.u.udp.port = exp->tuple.dst.u.udp.port;
	repl.dst.protonum = IPPROTO_UDP;
//	printk(" wm_nat_help repl.dstport=%d\n",htons(repl.dst.u.udp.port));
	DEBUGP("\n");
	DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple);
	DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_REPLY].tuple);

	DEBUGP("expecting:\n ");
	DUMP_TUPLE(&repl);
	DUMP_TUPLE(&exp->mask);
//printk("wm_nat:calling ip_conntrack_change_expect \n"); 
	ip_conntrack_change_expect(exp, &repl);

	return NF_ACCEPT;
}

static unsigned int 
wm_nat_expected(struct sk_buff **pskb,
		  unsigned int hooknum,
		  struct ip_conntrack *ct, 
		  struct ip_nat_info *info) 
{
	const struct ip_conntrack *master = ct->master->expectant;
	const struct ip_conntrack_tuple *orig = 
			&master->tuplehash[IP_CT_DIR_ORIGINAL].tuple;
	struct ip_nat_multi_range mr;

//	printk("wm_nat_expected hooknum=%d\n",hooknum);
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

DEBUGP("wm_nat_expected:calling ip_nat_setup_info\n"); 
	return ip_nat_setup_info(ct,&mr,hooknum);
}

static struct ip_nat_helper wm[MAXWM_PORTS];
static char wm_names[MAXWM_PORTS][10];

static void fini(void)
{
	int i;

	for (i = 0 ; i < ports_c; i++) {
		DEBUGP("unregistering helper for port %d\n", ports[i]);
		ip_nat_helper_unregister(&wm[i]);
	}
}

static int __init init(void)
{
	int i, ret=0;
	char *tmpname;

	if (!ports[0])
		ports[0] = WMINITIAL;

	for (i = 0 ; (i < MAXWM_PORTS) && ports[i] ; i++) {
		memset(&wm[i], 0, sizeof(struct ip_nat_helper));

		wm[i].tuple.src.u.tcp.port = htons(ports[i]);
		wm[i].tuple.dst.protonum = IPPROTO_TCP;
		wm[i].mask.src.u.tcp.port = 0xFFFF;
/*eshi*/
		wm[i].mask.dst.protonum = 0xFFFF;
		wm[i].help = help;
		//wm[i].flags = 0;
		//wm[i].me = THIS_MODULE;
		wm[i].expect = wm_nat_expected;

		tmpname = &wm_names[i][0];
		if (ports[i] == WMINITIAL)
			sprintf(tmpname, "wm");
		else
			sprintf(tmpname, "wm-%d", i);
		wm[i].name = tmpname;
		
		DEBUGP("ip_nat_wm: registering for port %d: name %s\n",
			ports[i], wm[i].name);
		ret = ip_nat_helper_register(&wm[i]);

		if (ret) {
			printk("ip_nat_wm: unable to register for port %d\n",
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
