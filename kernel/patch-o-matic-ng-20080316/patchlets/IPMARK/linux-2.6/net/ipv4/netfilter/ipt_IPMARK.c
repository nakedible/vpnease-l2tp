#include <linux/module.h>
#include <linux/skbuff.h>
#include <linux/version.h>
#include <linux/ip.h>
#include <net/checksum.h>

#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ipt_IPMARK.h>

MODULE_AUTHOR("Grzegorz Janoszka <Grzegorz@Janoszka.pl>");
MODULE_DESCRIPTION("IP tables IPMARK: mark based on ip address");
MODULE_LICENSE("GPL");

static unsigned int
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,24)
target(struct sk_buff *skb,
#else
target(struct sk_buff **pskb,
#endif
       const struct net_device *in,
       const struct net_device *out,
       unsigned int hooknum,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
       const struct xt_target *target,
#endif
#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,19)
       const void *targinfo,
       void *userinfo)
#else
       const void *targinfo)
#endif
{
	const struct ipt_ipmark_target_info *ipmarkinfo = targinfo;
#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,24)
	struct sk_buff *skb = *pskb;
#endif

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,22)
	struct iphdr *iph = ip_hdr(skb);
#else
	struct iphdr *iph = skb->nh.iph;
#endif
	unsigned long mark;

	if (ipmarkinfo->addr == IPT_IPMARK_SRC)
		mark = (unsigned long) ntohl(iph->saddr);
	else
		mark = (unsigned long) ntohl(iph->daddr);

	mark &= ipmarkinfo->andmask;
	mark |= ipmarkinfo->ormask;

#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,20)
	if (skb->nfmark != mark)
		skb->nfmark = mark;
#else
	if (skb->mark != mark)
		skb->mark = mark;
#endif
	return IPT_CONTINUE;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,24)
static bool
#else
static int
#endif
checkentry(const char *tablename,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,16)
	   const void *e,
#else
	   const struct ipt_entry *e,
#endif
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
	   const struct xt_target *target,
#endif
           void *targinfo,
#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,19)
           unsigned int targinfosize,
#endif
           unsigned int hook_mask)
{

#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,17)
	if (targinfosize != IPT_ALIGN(sizeof(struct ipt_ipmark_target_info))) {
		printk(KERN_WARNING "IPMARK: targinfosize %u != %Zu\n",
		       targinfosize,
		       IPT_ALIGN(sizeof(struct ipt_ipmark_target_info)));
		return 0;
	}
#endif

	if (strcmp(tablename, "mangle") != 0) {
		printk(KERN_WARNING "IPMARK: can only be called from \"mangle\" table, not \"%s\"\n", tablename);
		return 0;
	}

	return 1;
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
static struct xt_target ipt_ipmark_reg = {
#else
static struct ipt_target ipt_ipmark_reg = { 
#endif
	.name		= "IPMARK",
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
	.family		= AF_INET,
#endif
	.target		= target,
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,17)
	.targetsize	= sizeof(struct ipt_ipmark_target_info),
#endif
	.checkentry	= checkentry,
	.me		= THIS_MODULE
};

static int __init init(void)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
	return xt_register_target(&ipt_ipmark_reg);
#else
	return ipt_register_target(&ipt_ipmark_reg);
#endif
}

static void __exit fini(void)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(2,6,21)
	xt_unregister_target(&ipt_ipmark_reg);
#else
	ipt_unregister_target(&ipt_ipmark_reg);
#endif
}

module_init(init);
module_exit(fini);
