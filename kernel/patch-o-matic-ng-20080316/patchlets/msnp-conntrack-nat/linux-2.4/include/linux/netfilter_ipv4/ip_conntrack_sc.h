#ifndef _IP_CONNTRACK_SC_H
#define _IP_CONNTRACK_SC_H
/* MSNP tracking. */

#ifdef __KERNEL__

#include <linux/netfilter_ipv4/lockhelp.h>

/* Protects sc part of conntracks */
DECLARE_LOCK_EXTERN(ip_sc_lock);

#endif

/* MSNP Data. This struct for Messenger 5.0 */
#if 0
struct sc_ip_port_data
{
	/* internal ip */
	u_int32_t	ip;
	/* Port */
	u_int16_t	port;
	u_int8_t	level;
	struct ip_conntrack *master;
	struct ip_conntrack *ct;
	struct sc_ip_port_data *next;
};
#endif

/* We record seq number and length of sc ip/port text here: all in
   host order. */
struct ip_ct_sc_expect
{
	/* This tells NAT that this is an sc connection */
	int is_sc;
	u_int32_t seq;
	/* 0 means not found yet */
	u_int32_t len;
	/* Port that was to be used */
	u_int16_t port;
};

/* This structure exists only once per master */
struct ip_ct_sc_master {
	/* Next valid seq position for cmd matching after newline */
	u_int32_t seq_aft_nl[IP_CT_DIR_MAX];
	/* 0 means seq_match_aft_nl not set */
	int seq_aft_nl_set[IP_CT_DIR_MAX];
};

#endif /* _IP_CONNTRACK_SC_H */
