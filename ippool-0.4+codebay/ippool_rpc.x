/* -*- c -*- */

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
 * NOTE: APPLICATIONS USING THIS INTERFACE OR DERIVED FILES THEREOF MUST
 *       EITHER BE LICENSED UNDER GPL OR UNDER AN PPP COMMERCIAL LICENSE.
 *	 FROM KATALIX SYSTEMS LIMITED.
 *
 *****************************************************************************/

/*
 * IP Ippool application interface definition.
 *
 * ippoold is controlled using RPC. This file specifies the
 * interface.  Use it to generate RPC C code using rpcgen or other
 * tools to generate code for other environments such as Java.
 *
 * Unfortunately, the RPC IDL does not support the '<<' bitshift
 * operator often used in C and Java. Therefore, bitmask definitions
 * had to be manually calculated and specified in decimal here.
 *
 * RPC unions are avoided as much as possible because the generated
 * types can be cumbersome to use. Structures are shared by many 
 * create, modify and get operations, even though some fields in the
 * structures are unused for some operations.
 *
 * Fields are read-write, unless they are marked create-only or
 * read-only. All fields can be read.
 */

const IPPOOL_APP_COPYRIGHT_INFO		= "(c) Copyright 2004";
const IPPOOL_APP_VENDOR_INFO		= "Katalix Systems Ltd.";
const IPPOOL_APP_MAJOR_VERSION		= 0;
const IPPOOL_APP_MINOR_VERSION		= 3;

/*****************************************************************************
 * Types shared by several data structures
 *****************************************************************************/

/* TYPE: IP address
 * Fakes the standard sockaddr_in type.
 */
struct ippool_api_ip_addr {
	uint32_t			s_addr;
};

/*****************************************************************************
 * Application:-
 * TYPE: struct ippool_api_app_msg_data
 * USE:  to retrieve build and version info
 *****************************************************************************/

struct ippool_api_app_msg_data {
	string 				build_date<16>;
	string 				build_time<16>;
	int 				major;
	int 				minor;	
	uint32_t			cookie;
	int				patches<>;
};

/*****************************************************************************
 * IP pools
 * TYPE: struct ippool_api_pool_msg_data
 * USE:  create/delete/modify/get ip pools
 * TYPE: struct ippool_api_pool_list_msg_data
 * USE:  list ip pools
 * TYPE: struct ippool_api_addrblock
 * USE:  reserve/unreserve blocks of addresses
 * TYPE: struct ippool_api_alloc_msg_data
 * USE:  address allocate request
 *****************************************************************************/

/* Default parameter values */
const IPPOOL_API_DEFAULT_MAX_ADDRS 		= 0;		/* unlimited */
const IPPOOL_API_DEFAULT_NETMASK 		= 0xffffff00;	/* class C */

struct ippool_api_stats {
	unsigned long				num_allocs;
	unsigned long				num_frees;
	unsigned long				num_alloc_fails;
};

struct ippool_api_addrblock {
	struct ippool_api_ip_addr		first_addr;
	int					num_addrs;
	struct ippool_api_ip_addr		netmask;	/* for deriving boundaries of block */
};

struct ippool_api_addr_alloc_msg_data {
	int					result_code;
	struct ippool_api_ip_addr		addr;
};

const IPPOOL_API_FLAG_TRACE	 		= 1;
const IPPOOL_API_FLAG_DRAIN 			= 2;
const IPPOOL_API_FLAG_MAX_ADDRS 		= 4;
const IPPOOL_API_FLAG_NETMASK 			= 8;
const IPPOOL_API_FLAG_ADDR_BLOCK 		= 16;

struct ippool_api_pool_msg_data {
	string					pool_name<>;
	int					result_code;	/* read-only - status of request */
	uint32_t				flags;		/* which fields are set? */
	int					trace;
	bool					drain;		/* prevent further address allocations but allow free */
	int					max_addrs;	/* max number of addresses, 0=unlimited */
	struct ippool_api_addrblock		addr_block<>;	/* array of configured address blocks. */
	int					num_addrs;	/* read-only - total number of addresses assigned to pool */
	int					num_avail;	/* read-only - number of addresses available */
	struct ippool_api_stats 		stats;		/* read-only */
	struct ippool_api_addrblock		avail_block<>;	/* read-only - array of address blocks available for use */
	struct ippool_api_addrblock		rsvd_block<>;	/* read-only - array of address blocks reserved by operator */
};

struct ippool_api_pool_list_entry {
	string					pool_name<>;
	struct ippool_api_pool_list_entry	*next;
};

struct ippool_api_pool_list_msg_data {
	int					result;
	int					num_pools;
	struct ippool_api_pool_list_entry	*pools;
};


/*****************************************************************************
 * API definition
 *****************************************************************************/

program IPPOOL_PROG {
	version IPPOOL_VERSION {
		struct ippool_api_app_msg_data IPPOOL_APP_INFO_GET(void) = 1;
		int IPPOOL_CREATE(struct ippool_api_pool_msg_data params) = 2;
		int IPPOOL_DELETE(string pool_name) = 3;
		int IPPOOL_MODIFY(struct ippool_api_pool_msg_data params) = 4;
		struct ippool_api_pool_msg_data IPPOOL_GET(string pool_name) = 5;
		struct ippool_api_pool_list_msg_data IPPOOL_LIST(void) = 6;
		int IPPOOL_ADDRBLOCK_ADD(string pool_name, struct ippool_api_addrblock addr) = 7;
		int IPPOOL_ADDRBLOCK_REMOVE(string pool_name, struct ippool_api_addrblock addr) = 8;
		int IPPOOL_ADDRBLOCK_RESERVE(string pool_name, struct ippool_api_addrblock addr) = 9;
		int IPPOOL_ADDRBLOCK_UNRESERVE(string pool_name, struct ippool_api_addrblock addr) = 10;
		struct ippool_api_addr_alloc_msg_data IPPOOL_ADDR_ALLOC(string pool_name) = 11;
		int IPPOOL_ADDR_FREE(string pool_name, struct ippool_api_ip_addr addr) = 12;
		int IPPOOL_TEST_LOG(string) = 99;
	} = 1;			/* version 1 */
} = 300775;			/* official number registered at rpc@sun.com */

