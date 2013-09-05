/* MSNP extension for TCP NAT alteration. */
#include <linux/module.h>
#include <linux/netfilter_ipv4.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/udp.h>
#include <net/tcp.h>
#include <linux/netfilter_ipv4/ip_nat.h>
#include <linux/netfilter_ipv4/ip_nat_helper.h>
#include <linux/netfilter_ipv4/ip_nat_rule.h>
#include <linux/netfilter_ipv4/ip_conntrack_sc.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif

static int ports;

#ifdef MODULE_PARM
MODULE_PARM(ports, "1-" __MODULE_STRING(MAX_PORTS) "i");
#endif

DECLARE_LOCK_EXTERN(ip_sc_lock);

/* FIXME: Time out? --RR */
static struct sc_ip_port_data *sc_list={0};


void open_sc_socket(unsigned long data)
{ 
	struct socket *sock; 
	struct sockaddr_in addr; 
	int error; 
	char *kdata = (char *)data;
	
	struct msghdr   msg; 
	struct iovec    iov;
			   				
	error = sock_create(PF_INET, SOCK_DGRAM, IPPROTO_UDP, &sock); 
	if (error<0) { 
		printk("error during socket create\n"); 
		goto EXIT; 
	} 

	addr.sin_family		= AF_INET; 
	addr.sin_addr.s_addr	= 0x7f000001; 
	addr.sin_port		= 38231; 
	error = sock->ops->connect(sock, (struct sockaddr*)&addr, sizeof(addr), O_RDWR); 
	if (error<0) { 
		printk("error during socket connect\n"); 
		goto EXIT; 
	} 
	msg.msg_name     = NULL; 
	msg.msg_namelen  = 0; 
	msg.msg_iov      = &iov;
       	msg.msg_iovlen   = 1; 
	msg.msg_control  = NULL; 
	msg.msg_controllen = 0; 
	msg.msg_flags    = MSG_NOSIGNAL;
	iov.iov_base = kdata; 
       	iov.iov_len = strlen(kdata); 
	error = sock_sendmsg(sock, &msg, sizeof(msg)); 
	if (error<0) { 
		printk("error during socket sendmsg\n"); 
		goto EXIT; 
	} 
	DEBUGP("socket sendmsg ok\n");

EXIT:	    
	sock_release(sock);

}

static int
mangle_packet(struct sk_buff **pskb,
		     u_int32_t newip,
		     unsigned int matchoff,
		     unsigned int matchlen,
		     struct ip_conntrack *ct,
		     enum ip_conntrack_info ctinfo)
{
	unsigned char buffer[4];

	MUST_BE_LOCKED(&ip_sc_lock);

	*((u_int32_t *)(buffer)) = htonl(newip);

	DEBUGP("calling ip_nat_mangle_tcp_packet\n");

	return ip_nat_mangle_tcp_packet(pskb, ct, ctinfo, matchoff, matchlen, buffer, 4);
}

struct tq_struct jiq_task;
char task_data[64];
static int sc_data_fixup(const struct ip_ct_sc_expect *exp_sc_info,
			  struct ip_conntrack *ct,
			  unsigned int datalen,
			  struct sk_buff **pskb,
			  enum ip_conntrack_info ctinfo)
{
	u_int32_t newip;
	struct iphdr *iph = (*pskb)->nh.iph;
	struct tcphdr *tcph = (void *)iph + iph->ihl*4;
	u_int16_t port, new_port;
	struct ip_conntrack_tuple tuple;
	struct sc_ip_port_data *list_t=sc_list;
	int ret=0;
	/* Don't care about source port */
	const struct ip_conntrack_tuple mask
		= { { 0xFFFFFFFF, { 0xFFFFFFFF } },
	    	    { 0x0, { 0xFFFF }, 0xFFFF } };

	memset(&tuple, 0, sizeof(tuple));
	MUST_BE_LOCKED(&ip_sc_lock);
#if 0
	DEBUGP("SC_NAT: seq %u + %u in %u + %u\n",
	       exp_sc_info->seq, exp_sc_info->len, ntohl(tcph->seq), datalen);
#endif

	/* Change address inside packet to match way we're mapping
	   this connection. */
	newip = ct->tuplehash[IP_CT_DIR_REPLY].tuple.dst.ip;

	DEBUGP("sc_data_fixup: %u.%u.%u.%u->%u.%u.%u.%u\n", NIPQUAD(ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.src.ip), NIPQUAD(ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.dst.ip));
	/* Expect something from server->client */
	tuple.src.ip = ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.src.ip;
	tuple.dst.protonum = IPPROTO_UDP;

	jiq_task.routine = open_sc_socket; 
	memset(task_data, 0, 64);
	sprintf(task_data,"IP:%u.%u.%u.%uPORT:%dEND",NIPQUAD(ct->tuplehash[IP_CT_DIR_ORIGINAL].tuple.src.ip), port);
	jiq_task.data = (void *)task_data;
	schedule_task(&jiq_task);

	if (!mangle_packet(pskb, newip, exp_sc_info->seq - ntohl(tcph->seq), exp_sc_info->len, ct, ctinfo))
		return 0;

	return 1;
}

static unsigned int help(struct ip_conntrack *ct,
         		 struct ip_conntrack_expect *exp,
			 struct ip_nat_info *info,
			 enum ip_conntrack_info ctinfo,
			 unsigned int hooknum,
			 struct sk_buff **pskb)
{
	struct iphdr *iph = (*pskb)->nh.iph;
	struct tcphdr *tcph = (void *)iph + iph->ihl*4;
	unsigned int datalen;
	int dir;
	int score;
	struct ip_ct_sc_expect *exp_sc_info = &exp->help.exp_sc_info;

	/* Only mangle things once: original direction in POST_ROUTING
	   and reply direction on PRE_ROUTING. */
	dir = CTINFO2DIR(ctinfo);
	DEBUGP("nat_sc: help()\n");
	
#if 0
	if (!((hooknum == NF_IP_POST_ROUTING && dir == IP_CT_DIR_REPLY)
	      || (hooknum == NF_IP_PRE_ROUTING && dir == IP_CT_DIR_ORIGINAL))) {
#if 1
		DEBUGP("nat_sc: Not touching dir %s at hook %s\n",
		       dir == IP_CT_DIR_ORIGINAL ? "ORIG" : "REPLY",
		       hooknum == NF_IP_POST_ROUTING ? "POSTROUTING"
		       : hooknum == NF_IP_PRE_ROUTING ? "PREROUTING"
		       : hooknum == NF_IP_LOCAL_OUT ? "OUTPUT" : "???");
#endif
		return NF_ACCEPT;
	}
#endif

	datalen = (*pskb)->len - iph->ihl * 4 - tcph->doff * 4;
	score = 0;
	LOCK_BH(&ip_sc_lock);
	
	if (exp_sc_info->len) {
		/* If it's in the right range... */
		score += between(exp_sc_info->seq, ntohl(tcph->seq),
				 ntohl(tcph->seq) + datalen);
		score += between(exp_sc_info->seq + exp_sc_info->len,
				 ntohl(tcph->seq),
				 ntohl(tcph->seq) + datalen);
		if (score == 1) {
			/* Half a match?  This means a partial retransmisison.
			   It's a cracker being funky. */
			if (net_ratelimit()) {
				printk("SC_NAT: partial packet %u/%u in %u/%u\n",
				       exp_sc_info->seq, exp_sc_info->len,
				       ntohl(tcph->seq),
				       ntohl(tcph->seq) + datalen);
			}
			UNLOCK_BH(&ip_sc_lock);
			return NF_DROP;
		} else if (score == 2) {
			if (!sc_data_fixup(exp_sc_info, ct, datalen, pskb, ctinfo)) {
				UNLOCK_BH(&ip_sc_lock);
				return NF_DROP;
			}
			/* skb may have been reallocated */
			iph = (*pskb)->nh.iph;
			tcph = (void *)iph + iph->ihl*4;
		}
	}

	UNLOCK_BH(&ip_sc_lock);
	
	DEBUGP("nat_sc: ip_nat_seq_adjust()\n");
	ip_nat_seq_adjust(*pskb, ct, ctinfo);

	return NF_ACCEPT;
}

static struct ip_nat_helper sc;
static char sc_names[7];

/* Not __exit: called from init() */
static void fini(void) {
	DEBUGP("ip_nat_sc: unregistering port %d\n", ports);
	ip_nat_helper_unregister(&sc);
}

static int __init init(void) {
	int ret;
	char *tmpname;

	if (ports == 0)
		ports = 6112;

	memset(&sc, 0, sizeof(struct ip_nat_helper));

	sc.tuple.dst.protonum = IPPROTO_TCP;
	sc.tuple.src.u.udp.port = htons(ports);
	sc.mask.dst.protonum = 0xFFFF;
	sc.mask.src.u.tcp.port = 0xFFFF;
	sc.help = help;

	tmpname = &sc_names[0];
	sprintf(tmpname, "sc");
	sc.name = tmpname;

	DEBUGP("ip_nat_sc: Trying to register for port %d\n", ports);
	ret = ip_nat_helper_register(&sc);

	if (ret) {
		printk("ip_nat_sc: error registering helper for port %d\n", ports);
		fini();
		return ret;
	}

	return ret;
}

module_init(init);
module_exit(fini);
