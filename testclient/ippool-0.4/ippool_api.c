/*****************************************************************************
 * Copyright (C) 2004 Katalix Systems Ltd
 * 
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
 *
 *****************************************************************************/

/*
 * Configuration and management interface for ippoold.
 * Each module implements the required RPC xxx_1_svc() callbacks which
 * are called directly by the RPC library.
 */

#include <net/ethernet.h>

#include "usl.h"

#include "ippool_private.h"
#include "ippool_rpc.h"

static SVCXPRT	*ippool_rpc_xprt;

extern void ippool_prog_1(struct svc_req *rqstp, register SVCXPRT *transp);

/*****************************************************************************
 * XDR result cleanup.
 * The RPC XDR mechanism provides one entry point xxx_prog_1_free_result()
 * for the application to free data that was allocated for RPC. Since we
 * malloc all strings and variable length data, we must free it here. For
 * clarity, we use a separate function per XDR type.
 *
 * NOTE: when new XDR types are added to ippool_rpc.x, additional 
 * ippool_api_xdr_free_xxx() routines must be added here.
 *****************************************************************************/

static void ippool_api_xdr_free_app_msg_data(caddr_t addr)
{
	struct ippool_api_app_msg_data *msg = (void *) addr;

	if (msg->build_date != NULL) free(msg->build_date);
	if (msg->build_time != NULL) free(msg->build_time);
	if (msg->patches.patches_val != NULL) free(msg->patches.patches_val);
}

static void ippool_api_xdr_free_pool_msg_data(caddr_t addr)
{
	struct ippool_api_pool_msg_data *msg = (void *) addr;

	if (msg->pool_name != NULL) free(msg->pool_name);
	if ((msg->addr_block.addr_block_len > 0) && (msg->addr_block.addr_block_val != NULL)) free(msg->addr_block.addr_block_val);
	if ((msg->avail_block.avail_block_len > 0) && (msg->avail_block.avail_block_val != NULL)) free(msg->avail_block.avail_block_val);
	if ((msg->rsvd_block.rsvd_block_len > 0) && (msg->rsvd_block.rsvd_block_val != NULL)) free(msg->rsvd_block.rsvd_block_val);
}

static void ippool_api_xdr_free_pool_list_msg_data(caddr_t addr)
{
	struct ippool_api_pool_list_msg_data *msg = (void *) addr;
	struct ippool_api_pool_list_entry *entry = msg->pools;
	struct ippool_api_pool_list_entry *tmpe;

	while (entry != NULL) {
		tmpe = entry->next;
		if (entry->pool_name != NULL) free(entry->pool_name);
		free(entry);
		entry = tmpe;
	}
}

static void ippool_api_xdr_free_null(caddr_t addr)
{
}

struct ippool_api_xdr_free_entry {
	xdrproc_t xdr_proc;
	void (*free_fn)(caddr_t addr);
};

/* Lookup table for matching XDR proc function pointers to the above _free() functions.
 */
static const struct ippool_api_xdr_free_entry ippool_api_xdr_free_table[] = {
	{ (xdrproc_t) xdr_ippool_api_app_msg_data, 			ippool_api_xdr_free_app_msg_data },
	{ (xdrproc_t) xdr_ippool_api_ip_addr,				ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_ippool_api_pool_msg_data, 			ippool_api_xdr_free_pool_msg_data },
	{ (xdrproc_t) xdr_ippool_api_pool_list_msg_data, 		ippool_api_xdr_free_pool_list_msg_data },
	{ (xdrproc_t) xdr_ippool_api_stats, 				ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_ippool_api_addrblock, 			ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_ippool_api_addr_alloc_msg_data,		ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_ippool_api_pool_list_entry, 			ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_void,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_short,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_short,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_int,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_int,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_long,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_long,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_hyper,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_hyper,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_longlong_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_longlong_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_int8_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_uint8_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_int16_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_uint16_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_int32_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_uint32_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_int64_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_uint64_t,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_bool,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_enum,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_array,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_bytes,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_opaque,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_string,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_union,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_char,						ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_u_char,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_vector,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_float,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_double,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_reference,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_pointer,					ippool_api_xdr_free_null },
	{ (xdrproc_t) xdr_wrapstring,					ippool_api_xdr_free_null },
	{ NULL, 							NULL }
};

/* This function is called by the RPC mechanism to free memory 
 * allocated when sending RPC messages. We are passed a pointer
 * to the XDR parse function so we use that to derive the type 
 * of the structure to be freed. We use a lookup table and separate
 * free() functions per structure type because a switch() statement
 * can't be used to case on pointers and an if-then-else block
 * was error-prone.
 */
int ippool_prog_1_freeresult (SVCXPRT *xprt, xdrproc_t proc, caddr_t addr)
{
	const struct ippool_api_xdr_free_entry *entry = &ippool_api_xdr_free_table[0];

	while (entry->xdr_proc != NULL) {
		if (entry->xdr_proc == proc) {
			(*entry->free_fn)(addr);
			return TRUE;
		}
		entry++;
	}

	ippool_log(LOG_ERR, "Unimplemented XDR free_result() proc: %p", proc);
	return FALSE;
}

/* Come here when an RPC message is received. We dispatch to the RPC
 * library which does all the hard work.
 */
static void ippool_api_rpc_msg(int fd, void *arg)
{
	fd_set fds;

	FD_ZERO(&fds);
	FD_SET(fd, &fds);
	svc_getreqset(&fds);
}

/* Server callback to check that the request comes from an allowed IP
 * address.  A call to here is inserted in the rpcgen-generated
 * server-side dispatch code by the build process.
 */
int ippool_api_rpc_check_request(SVCXPRT *xprt)
{
	/* If remote RPC is not enabled and the request is from a 
	 * non-loopback interface, reject the request.
	 */
	if ((!ippool_opt_remote_rpc) &&
	    ((xprt->xp_raddr.sin_addr.s_addr != htonl(INADDR_LOOPBACK)) &&
	     (xprt->xp_raddr.sin_addr.s_addr != htonl(INADDR_ANY)))) {
		if (ippool_opt_debug) {
			ippool_log(LOG_ERR, "Rejecting RPC request from %s", inet_ntoa(xprt->xp_raddr.sin_addr));
		}
		svcerr_auth(xprt, AUTH_TOOWEAK);
		return -EPERM;
	}

	return 0;
}

/*****************************************************************************
 * Init and cleanup
 *****************************************************************************/

void ippool_api_init(void)
{
	int result;

	/* Register RPC interface */
	ippool_rpc_xprt = svcudp_create(RPC_ANYSOCK);
	if (ippool_rpc_xprt == NULL) {
		ippool_log(LOG_ERR, "unable to register with RPC");
		exit(1);
	}
	result = usl_fd_add_fd(ippool_rpc_xprt->xp_sock, ippool_api_rpc_msg, ippool_rpc_xprt);
	if (result < 0) {
		ippool_log(LOG_ERR, "unable to register RPC handler");
		exit(1);
	}
	svc_unregister(IPPOOL_PROG, IPPOOL_VERSION);
	result = svc_register(ippool_rpc_xprt, IPPOOL_PROG, IPPOOL_VERSION, ippool_prog_1, IPPROTO_UDP);
	if (result == 0) {	/* UNIX is nice and consistent about error codes ;-) */
		ippool_log(LOG_ERR, "unable to register RPC program");
		exit(1);		
	}
}

void ippool_api_cleanup(void)
{
	if (ippool_rpc_xprt != NULL) {
		svc_unregister(IPPOOL_PROG, IPPOOL_VERSION);
	}
}
