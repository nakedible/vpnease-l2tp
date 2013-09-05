/* MSNP extension for IP connection tracking. */
#include <linux/module.h>
#include <linux/netfilter.h>
#include <linux/ip.h>
#include <linux/ctype.h>
#include <net/checksum.h>
#include <net/tcp.h>

#include <linux/netfilter_ipv4/lockhelp.h>
#include <linux/netfilter_ipv4/ip_conntrack_helper.h>
#include <linux/netfilter_ipv4/ip_conntrack_sc.h>

DECLARE_LOCK(ip_sc_lock);
struct module *ip_conntrack_sc = THIS_MODULE;

#define SC_PORT 6112
static int ports;

static int loose = 0;
MODULE_PARM(loose, "i");

#if 0
#define DEBUGP printk
#else
#define DEBUGP(format, args...)
#endif

/* Return 1 for match, 0 for accept, -1 for partial. */
static int find_pattern_sc(const char *data, size_t dlen,
			unsigned int *numoff,
			unsigned int *numlen,
			u_int32_t array[3])
{
	unsigned char *p_data=(unsigned char*)data;
	// found pattern
	if(dlen>23 && (*(p_data) == 0xff) && (*(p_data+1)== 0x09) && (*(p_data+4)==0x01) && (*(p_data+5)==0x00) && (*(p_data+20)==*((unsigned char *)&array[2])) && (*(p_data+21)==*(((unsigned char *)&array[2])+1)) && (*(p_data+22)==*(((unsigned char *)&array[2])+2)) && (*(p_data+23)==*(((unsigned char *)&array[2])+3)))
	{
		DEBUGP("SC :Match! 0xff 09 01 00 ip\n");
		array[0]=ntohl(*((u_int32_t *)(data+20)));
		array[1]=SC_PORT;
	
		*numoff = 20;
		*numlen = 4;
	
	}else if ( dlen > 28 && (*(p_data) == 0xff) && (*(p_data+1) == 0x50) && (*(p_data+24)==*((unsigned char *)&array[2])) && (*(p_data+25)==*(((unsigned char *)&array[2])+1)) && (*(p_data+26)==*(((unsigned char *)&array[2])+2)) && (*(p_data+27)==*(((unsigned char *)&array[2])+3)))
	{
		DEBUGP("SC :Match! 0xff 50 ip\n");
		array[0]=ntohl(*((u_int32_t *)(data+24)));
		array[1]=SC_PORT;

		*numoff = 24;
		*numlen = 4;
	
	}
	else
	{
		DEBUGP("SC :No Match %X %X %X %X ip: %X %X %X %X\n",*(p_data),*(p_data+1),*(p_data+4),*(p_data+5),*(p_data+24),*(p_data+25),*(p_data+26),*(p_data+27));
		return 0;	/* No match */
	}
	
	DEBUGP("SC:Match succeeded! address=%X port=%X\n",array[0],array[1]);
	return 1;
}


/* FIXME: This should be in userspace.  Later. */
static int help(const struct iphdr *iph, size_t len,
		struct ip_conntrack *ct,
		enum ip_conntrack_info ctinfo)
{
	/* tcplen not negative guaranteed by ip_conntrack_tcp.c */
	struct tcphdr *tcph = (void *)iph + iph->ihl * 4;
	const char *data = (const char *)tcph + tcph->doff * 4;
	unsigned int tcplen = len - iph->ihl * 4;
	unsigned int datalen = tcplen - tcph->doff * 4;
	u_int32_t old_seq_aft_nl=0;
	int old_seq_aft_nl_set=0;
	u_int32_t array[3] = { 0 };
	int dir = CTINFO2DIR(ctinfo);
	unsigned int matchlen, matchoff;
	struct ip_ct_sc_master *ct_sc_info = &ct->help.ct_sc_info;
	struct ip_conntrack_expect expect, *exp = &expect;
	struct ip_ct_sc_expect *exp_sc_info = &exp->help.exp_sc_info;

#if 1
	int i;
	DEBUGP("\n\ndatalen=%d ", datalen);
	for(i=0;i<(datalen>10?10:datalen);i++) {
		DEBUGP("[%02x] ", *(data+i));
	}
	DEBUGP("\n");
#endif

	/* Until there's been traffic both ways, don't look in packets. */
	if (ctinfo != IP_CT_ESTABLISHED
	    && ctinfo != IP_CT_ESTABLISHED+IP_CT_IS_REPLY) {
		DEBUGP("conntrack_sc: Conntrackinfo = %u\n", ctinfo);
		return NF_ACCEPT;
	}

	/* Not whole TCP header? */
	if (tcplen < sizeof(struct tcphdr) || tcplen < tcph->doff*4) {
		DEBUGP("conntrack_sc: tcplen = %u\n", (unsigned)tcplen);
		return NF_ACCEPT;
	}

	/* Checksum invalid?  Ignore. */
	/* FIXME: Source route IP option packets --RR */
	if (tcp_v4_check(tcph, tcplen, iph->saddr, iph->daddr, csum_partial((char *)tcph, tcplen, 0))) {
		DEBUGP("conntrack_sc: bad csum: %p %u %u.%u.%u.%u %u.%u.%u.%u\n",
		       tcph, tcplen, NIPQUAD(iph->saddr), NIPQUAD(iph->daddr));
		return NF_ACCEPT;
	}

	LOCK_BH(&ip_sc_lock);
	old_seq_aft_nl = ct_sc_info->seq_aft_nl[dir];
	old_seq_aft_nl_set = ct_sc_info->seq_aft_nl_set[dir];

	if (datalen > 0) {
		DEBUGP("conntrack_sc: datalen %u ends in \\n\n", datalen);
		if (!old_seq_aft_nl_set || after(ntohl(tcph->seq) + datalen, old_seq_aft_nl)) {
			ct_sc_info->seq_aft_nl[dir] = ntohl(tcph->seq) + datalen;
			ct_sc_info->seq_aft_nl_set[dir] = 1;
		}
	}
	
	UNLOCK_BH(&ip_sc_lock);

	if(!old_seq_aft_nl_set || (ntohl(tcph->seq) != old_seq_aft_nl)) {
		DEBUGP("ip_conntrack_sc_help: wrong seq pos %s(%u)(%u)\n", old_seq_aft_nl_set ? "":"(UNSET) ", old_seq_aft_nl, ntohl(tcph->seq));
		return NF_ACCEPT;
	}

#if 0
	if(dir !=IP_CT_DIR_ORIGINAL){
		return NF_ACCEPT;
	}
#endif

	array[2] = ct->tuplehash[dir].tuple.src.ip;

	if( !find_pattern_sc(data, datalen, &matchoff, &matchlen, array)) {
		/* No Match */
		return NF_ACCEPT;
	}

	memset(&expect, 0, sizeof(struct ip_conntrack_expect));

	/* Update the sc info */
	LOCK_BH(&ip_sc_lock);

	exp_sc_info->is_sc = SC_PORT;
	exp_sc_info->seq = ntohl(tcph->seq) + matchoff;
	exp_sc_info->len = matchlen;
	exp_sc_info->port = array[1];

	DEBUGP("conntrack_sc: match `%.*s' (%u bytes at %u)\n", (int)matchlen, data + matchoff, matchlen, ntohl(tcph->seq) + matchoff);

	exp->seq = ntohl(tcph->seq) + matchoff;
	exp->tuple = ((struct ip_conntrack_tuple)
		{ { ct->tuplehash[!dir].tuple.src.ip,
		    { 0 } },
		  { htonl(array[0]),
		    { htons(array[1]) },
		    IPPROTO_TCP }});

	exp->mask = ((struct ip_conntrack_tuple)
		{ { 0x0, { 0 } },
		  { 0xFFFFFFFF, { 0xFFFF }, 0xFFFF }});

	exp->expectfn = NULL;

	ip_conntrack_expect_related(ct, exp);
	UNLOCK_BH(&ip_sc_lock);

	return NF_ACCEPT;
}

static struct ip_conntrack_helper sc;

/* Not __exit: called from init() */
static void fini(void) {
	DEBUGP("ip_ct_sc: unregistering helper for port %d\n", SC_PORT);
	ip_conntrack_helper_unregister(&sc);
}

static int __init init(void) {
	ports = SC_PORT;

	memset(&sc, 0, sizeof(struct ip_conntrack_helper));
	sc.tuple.src.u.tcp.port = htons(ports);
	sc.tuple.dst.protonum = IPPROTO_TCP;
	sc.mask.src.u.tcp.port = 0xFFFF;
	sc.mask.dst.protonum = 0xFFFF;
	sc.help = help;
	DEBUGP("ip_ct_sc: registering helper for port %d\n", SC_PORT);
	return ip_conntrack_helper_register(&sc);
}

module_init(init);
module_exit(fini);
