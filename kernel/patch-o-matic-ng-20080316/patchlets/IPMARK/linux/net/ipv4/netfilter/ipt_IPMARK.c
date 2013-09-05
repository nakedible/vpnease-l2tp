#include <linux/module.h>
#include <linux/skbuff.h>
#include <linux/ip.h>
#include <net/checksum.h>

#include <linux/netfilter_ipv4/ip_tables.h>
#include <linux/netfilter_ipv4/ipt_IPMARK.h>

MODULE_AUTHOR("Grzegorz Janoszka <Grzegorz@Janoszka.pl>");
MODULE_DESCRIPTION("IP tables IPMARK: mark based on ip address");
MODULE_LICENSE("GPL");

static unsigned int
target(struct sk_buff **pskb,
       unsigned int hooknum,
       const struct net_device *in,
       const struct net_device *out,
       const void *targinfo,
       void *userinfo)
{
	const struct ipt_ipmark_target_info *ipmarkinfo = targinfo;
	struct iphdr *iph = (*pskb)->nh.iph;
	unsigned long mark;

	if (ipmarkinfo->addr == IPT_IPMARK_SRC)
		mark = (unsigned long) ntohl(iph->saddr);
	else
		mark = (unsigned long) ntohl(iph->daddr);

	mark &= ipmarkinfo->andmask;
	mark |= ipmarkinfo->ormask;
	
	if ((*pskb)->nfmark != mark) {
		(*pskb)->nfmark = mark;
		(*pskb)->nfcache |= NFC_ALTERED;
	}
	return IPT_CONTINUE;
}

static int
checkentry(const char *tablename,
	   const struct ipt_entry *e,
           void *targinfo,
           unsigned int targinfosize,
           unsigned int hook_mask)
{
	if (targinfosize != IPT_ALIGN(sizeof(struct ipt_ipmark_target_info))) {
		printk(KERN_WARNING "IPMARK: targinfosize %u != %Zu\n",
		       targinfosize,
		       IPT_ALIGN(sizeof(struct ipt_ipmark_target_info)));
		return 0;
	}

	if (strcmp(tablename, "mangle") != 0) {
		printk(KERN_WARNING "IPMARK: can only be called from \"mangle\" table, not \"%s\"\n", tablename);
		return 0;
	}

	return 1;
}

static struct ipt_target ipt_ipmark_reg = { 
	.name = "IPMARK",
	.target = target,
	.checkentry = checkentry,
	.me = THIS_MODULE
};

static int __init init(void)
{
	return ipt_register_target(&ipt_ipmark_reg);
}

static void __exit fini(void)
{
	ipt_unregister_target(&ipt_ipmark_reg);
}

module_init(init);
module_exit(fini);
