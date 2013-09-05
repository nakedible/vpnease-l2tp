/* PT for IP connection tracking. */
#include <linux/config.h>
#include <linux/module.h>
#include <linux/netfilter.h>
#include <linux/ip.h>
#include <linux/ctype.h>
#include <net/checksum.h>
#include <net/udp.h>

#include <linux/netfilter_ipv4/lockhelp.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_dtx8.h>

DECLARE_LOCK(ip_dtx8_lock);
struct module *ip_conntrack_dtx8 = THIS_MODULE;

/*
** Parameters passed from insmod.
** insmod dtx8.o outport=100,200 inport=300,400 outproto=t inproto=t
**
*/

static int ports[MAXDTX8_PORTS];
static int ports_c;


#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif


/* FIXME: This should be in userspace.  Later. */
static int help(const struct iphdr *iph, size_t len,
		struct ip_conntrack *ct,
		enum ip_conntrack_info ctinfo)
{
	int dir = CTINFO2DIR(ctinfo);
	struct tcphdr *tcph = (void *)iph + iph->ihl * 4;
        struct ip_conntrack_expect exp;
	int i;


	if ( ctinfo != IP_CT_NEW)
		return NF_ACCEPT;
	if ( dir != 0)
		return NF_ACCEPT;
	DEBUGP("dtx8_help: Conntrackinfo = %u dir=%d\n", ctinfo,dir);
        DEBUGP("");
        DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple);
        DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_REPLY].tuple);
	LOCK_BH(&ip_dtx8_lock);

	for(i = DTX8MIN; i <= DTX8MAX; i++) {
            memset(&exp, 0, sizeof(exp));
            exp.tuple = ct->tuplehash[IP_CT_DIR_REPLY].tuple;
            exp.tuple.dst.u.udp.port = htons(i);
            exp.tuple.dst.protonum = IPPROTO_UDP;
            exp.mask.src.ip = 0xffffffff;
            exp.mask.dst.ip = 0xffffffff;
            exp.mask.dst.u.udp.port = 0xffff;
            exp.mask.dst.protonum = 0xffff;
            exp.expectfn = NULL;
            exp.seq = ntohl(tcph->seq);

            DEBUGP("expect: ");
            DUMP_TUPLE(&exp.tuple);
            DUMP_TUPLE(&exp.mask);
            ip_conntrack_expect_related(ct, &exp);
	}
	UNLOCK_BH(&ip_dtx8_lock);
        return NF_ACCEPT;
}

static struct ip_conntrack_helper dtx8[MAXDTX8_PORTS];

/* Not __exit: called from init() */
static void fini(void)
{
	int i;
	for (i = 0; (i < MAXDTX8_PORTS) && ports[i]; i++) {
		DEBUGP("ip_conntrack_dtx8: unregistering helper for port %d\n",
				ports[i]);
		ip_conntrack_helper_unregister(&dtx8[i]);
	}
}

static int __init init(void)
{
	int i, ret;

	if (ports[0] == 0)
		ports[0] =DTX8INITIAL;

	for (i = 0; (i < MAXDTX8_PORTS) && ports[i]; i++) {
		memset(&dtx8[i], 0, sizeof(struct ip_conntrack_helper));
		dtx8[i].tuple.src.u.udp.port = htons(ports[i]);
	        dtx8[i].tuple.dst.protonum = IPPROTO_TCP;
		dtx8[i].mask.src.u.udp.port = 0xFFFF;
	     // dtx8[i].mask.dst.protonum = 0xFFFF;
		dtx8[i].mask.dst.protonum = 0;
		dtx8[i].max_expected = DTX8MAXEXPECTED;
             // dtx8[i].timeout = 0;
	     // dtx8[i].flags = IP_CT_HELPER_F_REUSE_EXPECT;
             // dtx8[i].me = ip_conntrack_dtx8;
		dtx8[i].help = help;

		DEBUGP("ip_conntrack_dtx8: registering helper for port %d\n", 
				ports[i]);
		ret = ip_conntrack_helper_register(&dtx8[i]);

		if (ret) {
		  fini();
	  printk("ip_conntrack_dtx8: registering helper for port FAILED  \n"); 
		  return ret;
		}
		ports_c++;
	}
	return 0;
}


MODULE_LICENSE("GPL");

EXPORT_SYMBOL(ip_dtx8_lock);
module_init(init);
module_exit(fini);
