/* Window Media connection tracking. */
#include <linux/config.h>
#include <linux/module.h>
#include <linux/netfilter.h>
#include <linux/ip.h>
#include <linux/ctype.h>
#include <net/checksum.h>
#include <net/udp.h>

#include <linux/netfilter_ipv4/lockhelp.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_wm.h>

DECLARE_LOCK(ip_wm_lock);
struct module *ip_conntrack_wm = THIS_MODULE;

/*
** Parameters passed from insmod.
** insmod ip_conntrack_wm.o 
**
*/
#if 0
static int outport[2];
static int inport[2];
static char *outproto="t";
static char *inproto="t";

MODULE_PARM(outport,"2i");
MODULE_PARM(inport,"2i");
MODULE_PARM(outproto,"s");
MODULE_PARM(inproto,"s");
#endif

static int ports[MAXWM_PORTS];
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

	/*
	** We only do this for the new packet 
        */
//	printk("wm_help: Conntrackinfo = %u dir=%d\n", ctinfo,dir);
	if ( ctinfo != IP_CT_NEW)
		return NF_ACCEPT;
	if ( dir != 0)
		return NF_ACCEPT;
        //DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple);
        //DUMP_TUPLE(&ct->tuplehash[IP_CT_DIR_REPLY].tuple);

	LOCK_BH(&ip_wm_lock);
	//for(i = WMMIN; i <= WMMIN; i++) {
	for(i = WMMIN; i <= WMMAX; i++) {
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

            DEBUGP("wm_help: expect: ");
            DUMP_TUPLE(&exp.tuple);
            DUMP_TUPLE(&exp.mask);
            ip_conntrack_expect_related(ct, &exp);
	}
	UNLOCK_BH(&ip_wm_lock);
        return NF_ACCEPT;
}

static struct ip_conntrack_helper wm[MAXWM_PORTS];

/* Not __exit: called from init() */
static void fini(void)
{
	int i;
	for (i = 0; (i < MAXWM_PORTS) && ports[i]; i++) {
		DEBUGP("ip_conntrack_wm: unregistering helper for port %d\n",
				ports[i]);
		ip_conntrack_helper_unregister(&wm[i]);
	}
}

static int __init init(void)
{
	int i, ret;

	if (ports[0] == 0)
		ports[0] =WMINITIAL;

	for (i = 0; (i < MAXWM_PORTS) && ports[i]; i++) {
		memset(&wm[i], 0, sizeof(struct ip_conntrack_helper));
		wm[i].tuple.src.u.tcp.port = htons(ports[i]);
		wm[i].tuple.dst.protonum = IPPROTO_TCP;
		wm[i].mask.src.u.tcp.port = 0xFFFF;
/*eshi*/
		wm[i].mask.dst.protonum = 0xFFFF;
		wm[i].max_expected = WMMAXEXPECTED;
             //   wm[i].timeout = 0;
//                wm[i].flags = IP_CT_HELPER_F_REUSE_EXPECT;
                //wm[i].me = ip_conntrack_wm;
		wm[i].help = help;

		DEBUGP("ip_conntrack_wm: registering helper for port %d\n", 
				ports[i]);
		ret = ip_conntrack_helper_register(&wm[i]);

		if (ret) {
		  fini();
	  printk("ip_conntrack_wm: registering helper for port FAILED  \n"); 
		  return ret;
		}
		ports_c++;
	}
	return 0;
}


MODULE_LICENSE("GPL");

EXPORT_SYMBOL(ip_wm_lock);
module_init(init);
module_exit(fini);
