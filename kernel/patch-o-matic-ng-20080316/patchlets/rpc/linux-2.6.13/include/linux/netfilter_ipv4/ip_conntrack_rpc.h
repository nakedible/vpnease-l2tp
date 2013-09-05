/* RPC extension for IP connection tracking, Version 2.2
 * (C) 2000 by Marcelo Barbosa Lima <marcelo.lima@dcc.unicamp.br>
 *	- original rpc tracking module
 *	- "recent" connection handling for kernel 2.3+ netfilter
 *
 * (C) 2001 by Rusty Russell <rusty@rustcorp.com.au>
 *	- upgraded conntrack modules to oldnat api - kernel 2.4.0+
 *
 * (C) 2002 by Ian (Larry) Latter <Ian.Latter@mq.edu.au>
 *	- upgraded conntrack modules to newnat api - kernel 2.4.20+
 *	- extended matching to support filtering on procedures
 *
 * (C) 2005 by David Stes <stes@pandora.be>
 *      - upgraded to 2.6.13 API
 *
 * ip_conntrack_rpc.h,v 2.2 2003/01/12 18:30:00
 *
 *	This program is free software; you can redistribute it and/or
 *	modify it under the terms of the GNU General Public License
 *	as published by the Free Software Foundation; either version
 *	2 of the License, or (at your option) any later version.
 **
 */

#include <asm/param.h>
#include <linux/sched.h>
#include <linux/timer.h>
#include <linux/stddef.h>
#include <linux/list.h>

#include <linux/netfilter_ipv4/ip_conntrack_helper.h>

#ifndef _IP_CONNTRACK_RPC_H
#define _IP_CONNTRACK_RPC_H

#define RPC_PORT       111


/* Datum in RPC packets are encoded in XDR */
#define IXDR_GET_INT32(buf) ((u_int32_t) ntohl((uint32_t)*buf))

/* Fast timeout, to deny DoS atacks */
#define EXP (60 * HZ)

/* Normal timeouts */
#define EXPIRES (180 * HZ)

/* For future conections RPC, using client's cache bindings
 * I'll use ip_conntrack_lock to lock these lists	*/

/* This identifies each request and stores protocol */
struct request_p {
	struct list_head list;

	u_int32_t xid;   
	u_int32_t ip;
	u_int16_t port;
	
	/* Protocol */
	u_int16_t proto;

	struct timer_list timeout;
};

static inline int request_p_cmp(const struct request_p *p, u_int32_t xid, 
				u_int32_t ip, u_int32_t port) {
	return (p->xid == xid && p->ip == ip && p->port);

}

#endif /* _IP_CONNTRACK_RPC_H */
