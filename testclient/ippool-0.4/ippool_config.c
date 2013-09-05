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
 * Command Line Interface for ippoold.
 * Command syntax is defined in a syntax table near the bottom of this file.
 * The guts of the CLI is implemented in a library.
 */

#include <stdio.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <unistd.h>
#include <rpc/rpc.h>
#include <signal.h>

#include "usl.h"
#include "cli_api.h"

#include "ippool_private.h"
#include "ippool_rpc.h"

static int opt_quiet;
static int interactive = 0;

static CLIENT *cl;
static char server[48];
static char *ippool_histfile = NULL;
static int ippool_histfile_maxsize = -1;

#define IPPOOL_ACT_DECLARATIONS(_max_args, _ids_type, _clnt_res_type)				\
	struct cli_node *args[_max_args];							\
	char *arg_values[_max_args];								\
	int num_args = _max_args;								\
	int arg;										\
	int result;										\
	_ids_type arg_id;									\
	_clnt_res_type clnt_res;

#define IPPOOL_ACT_BEGIN()										\
	result = cli_find_args(argc, argv, node, &args[0], &arg_values[0], &num_args);		\
	if (result == 0) {									\
		for (arg = 0; arg < num_args; arg++) {						\
			if (args[arg] && args[arg]->arg) {					\
				arg_id = args[arg]->arg->id;

#define IPPOOL_ACT_END()										\
			}									\
		}										\
	} else {										\
		/* tell caller which arg failed */						\
		*arg_num = num_args;								\
		result = -EINVAL;								\
		goto out;									\
	}


#define IPPOOL_ACT_PARSE_ARG(_arg_node, _arg_value, _field, _flag_var, _flag)			\
	result = _arg_node->arg->parser(_arg_node, _arg_value, &_field);			\
	if (result < 0) {									\
		goto out;									\
	}											\
	_flag_var |= _flag;

static int ippool_name_compare(const void *name1, const void *name2)
{
	char *my_name1 = *((char **) name1);
	char *my_name2 = *((char **) name2);

	return strcmp(my_name1, my_name2);
}

/*****************************************************************************
 * server ...
 *****************************************************************************/

#define ARG(id, name, flag, type, doc) \
	{ name, { IPPOOL_SERVER_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#define FLG(id, name, doc) \
	{ name, { IPPOOL_SERVER_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	IPPOOL_SERVER_ARGID_NAME,
} ippool_server_arg_ids_t;

static struct cli_arg_entry ippool_args_server_modify[] = {
	ARG(NAME, 		"name", 		0, 	string,	"IP address or hostname of IPPOOL daemon to attach to. Default=localhost."),
	{ NULL, },
};

static void ippool_set_prompt(char *server_name)
{
	static char prompt[48];

	snprintf(prompt, sizeof(prompt), "ippool-%s", server_name);
	cli_set_prompt(prompt);
}


static int ippool_act_server_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *server_name = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_server_arg_ids_t, int);

	clnt_res = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_SERVER_ARGID_NAME:
			server_name = arg_values[arg];
			break;
		}
	} IPPOOL_ACT_END();

	if (server_name == NULL) {
		fprintf(stderr, "Required name argument is missing.\n");
		goto out;
	}
	if (strcmp(server_name, &server[0])) {
		strncpy(&server[0], server_name, sizeof(server));

		clnt_destroy(cl);
		cl = clnt_create(server, IPPOOL_PROG, IPPOOL_VERSION, "udp");
		if (cl == NULL) {
			clnt_pcreateerror(server);
			exit(1);
		}

		ippool_set_prompt(server_name);
	}

out:
	return 0;
}

static int ippool_act_server_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	printf("Connected to server: %s\n", server);
	return 0;
}

/*****************************************************************************
 * system ...
 *****************************************************************************/

static int ippool_act_exit(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	exit(0);
}

static int ippool_act_help(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	cli_show_help();
	return 0;
}

static int ippool_act_system_show_version(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct ippool_api_app_msg_data app;
	int result;

	memset(&app, 0, sizeof(app));
	result = ippool_app_info_get_1(&app, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	printf("IpPool V%d.%d, built %s [%s],\n\t%s %s\n",
	       app.major, app.minor, app.build_date, app.build_time,
	       IPPOOL_APP_COPYRIGHT_INFO, IPPOOL_APP_VENDOR_INFO);
	if (app.patches.patches_len > 0) {
		int patch;
		printf("  Patches: ");
		for (patch = 0; patch < app.patches.patches_len; patch++) {
			printf("%d ", app.patches.patches_val[patch]);
		}
		printf("\n");
	}
	if (app.cookie != IPPOOL_APP_COOKIE) {
		printf("*** WARNING: CONTROL APPLICATION AND DAEMON ARE OUT OF SYNC. ***\n");
		printf("*** UNDEFINED BEHAVIOR MAY RESULT. REINSTALL TO FIX.         ***\n\n");
	}

out:
	return result;
}

/*****************************************************************************
 * IP Pools
 *****************************************************************************/

typedef enum {
	IPPOOL_ARGID_POOL_NAME,
	IPPOOL_ARGID_TRACE,
	IPPOOL_ARGID_DRAIN,
	IPPOOL_ARGID_MAX_ADDRS,
	IPPOOL_ARGID_NETMASK,
	IPPOOL_ARGID_FIRST_ADDR,
	IPPOOL_ARGID_ADDR,
	IPPOOL_ARGID_NUM_ADDRS,
} ippool_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { IPPOOL_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { IPPOOL_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

/* Paremeters for Create and Modify operations */
#define IPPOOL_MODIFY_ARGS 																\
	ARG(TRACE,		"trace",		0,	bool,	"Pool trace control. Default: OFF."),							\
	ARG(DRAIN,		"drain",		0,	bool,	"Drain pool (disable further allocations). Default: OFF."),				\
	ARG(MAX_ADDRS,		"max_addrs",		0,	uint32,	"Maximum number of addresses contained in pool. Default = 0 (unlimited)")		\

static struct cli_arg_entry ipppool_args_create[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(NETMASK,		"netmask",		0,	ipaddr,	"IP netmask for pool addresses. Default: 255.255.0.0."),
	ARG(FIRST_ADDR,		"first_addr",		0,	ipaddr, "First address in the pool"),
        ARG(NUM_ADDRS,		"num_addrs",		0,	uint32,	"Number of addresses in the pool. Default: 250"),
	IPPOOL_MODIFY_ARGS,
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_delete[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_modify[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	IPPOOL_MODIFY_ARGS,							 								\
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_show[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_addrblock_add[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(NETMASK,		"netmask",		0,	ipaddr,	"IP netmask for address block. Default: 255.255.255.0."),
	ARG(FIRST_ADDR,		"first_addr",		0,	ipaddr, "First address in the block"),
        ARG(NUM_ADDRS,		"num_addrs",		0,	uint32,	"Number of addresses in the block. Default: 250"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_addrblock_remove[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(NETMASK,		"netmask",		0,	ipaddr,	"IP netmask for address block. Default: 255.255.0.0."),
	ARG(FIRST_ADDR,		"first_addr",		0,	ipaddr, "First address in the block"),
        ARG(NUM_ADDRS,		"num_addrs",		0,	uint32,	"Number of addresses in the block. Default: 250"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_addrblock_reserve[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(FIRST_ADDR,		"first_addr",		0,	ipaddr, "First address in the block"),
        ARG(NUM_ADDRS,		"num_addrs",		0,	uint32,	"Number of addresses in the block. Default: 250"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_addrblock_unreserve[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(FIRST_ADDR,		"first_addr",		0,	ipaddr, "First address in the block"),
        ARG(NUM_ADDRS,		"num_addrs",		0,	uint32,	"Number of addresses in the block. Default: 250"),
	{ NULL, },
};

#ifdef IPPOOL_TEST

static struct cli_arg_entry ipppool_args_addr_alloc[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	{ NULL, },
};

static struct cli_arg_entry ipppool_args_addr_free[] = {
	ARG(POOL_NAME,		"pool_name",		0,	string,	"Name of ip pool"),
	ARG(ADDR,		"addr",			0,	ipaddr, "Address to be returned to pool"),
	{ NULL, },
};

#endif /* IPPOOL_TEST */

static int ippool_parse_arg(ippool_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct ippool_api_pool_msg_data *msg)
{
	int result = -EINVAL;

	if (arg_value == NULL) {
		arg_value = "";
	}

	switch (arg_id) {
	case IPPOOL_ARGID_POOL_NAME:
		msg->pool_name = strdup(arg_value);
		if (msg->pool_name == NULL) {
			result = -ENOMEM;
			goto out;
		}
		break;
	case IPPOOL_ARGID_TRACE:
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->trace, msg->flags, IPPOOL_API_FLAG_TRACE);
		break;
	case IPPOOL_ARGID_DRAIN:
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->drain, msg->flags, IPPOOL_API_FLAG_DRAIN);
		break;
	case IPPOOL_ARGID_MAX_ADDRS:
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->max_addrs, msg->flags, IPPOOL_API_FLAG_MAX_ADDRS);
		break;
	case IPPOOL_ARGID_FIRST_ADDR:
		if (msg->addr_block.addr_block_len == 0) {
			msg->addr_block.addr_block_val = calloc(1, sizeof(struct ippool_api_addrblock));
			if (msg->addr_block.addr_block_val == NULL) {
				result = -ENOMEM;
				goto out;
			}
		}
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->addr_block.addr_block_val[0].first_addr, msg->flags, IPPOOL_API_FLAG_ADDR_BLOCK);
		msg->addr_block.addr_block_len = 1;
		break;
	case IPPOOL_ARGID_NUM_ADDRS:
		if (msg->addr_block.addr_block_len == 0) {
			msg->addr_block.addr_block_val = calloc(1, sizeof(struct ippool_api_addrblock));
			if (msg->addr_block.addr_block_val == NULL) {
				result = -ENOMEM;
				goto out;
			}
		}
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->addr_block.addr_block_val[0].num_addrs, msg->flags, IPPOOL_API_FLAG_ADDR_BLOCK);
		msg->addr_block.addr_block_len = 1;
		break;
	case IPPOOL_ARGID_NETMASK:
		if (msg->addr_block.addr_block_len == 0) {
			msg->addr_block.addr_block_val = calloc(1, sizeof(struct ippool_api_addrblock));
			if (msg->addr_block.addr_block_val == NULL) {
				result = -ENOMEM;
				goto out;
			}
		}
		IPPOOL_ACT_PARSE_ARG(arg, arg_value, msg->addr_block.addr_block_val[0].netmask, msg->flags, IPPOOL_API_FLAG_NETMASK);
		msg->addr_block.addr_block_len = 1;
		break;
		/* invalid for pool create/modify */
	case IPPOOL_ARGID_ADDR:
		result = -EINVAL;
		goto out;
	}

	result = 0;

out:
	return result;
}

static int ippool_act_ip_pool_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct ippool_api_pool_msg_data msg = { 0, };
	IPPOOL_ACT_DECLARATIONS(40, ippool_arg_ids_t, int);

	IPPOOL_ACT_BEGIN() {
		result = ippool_parse_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} IPPOOL_ACT_END();

	if (msg.pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created pool %s\n", msg.pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_arg_ids_t, int);

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_delete_1(pool_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Deleted pool %s\n", pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct ippool_api_pool_msg_data msg = { 0, };
	IPPOOL_ACT_DECLARATIONS(40, ippool_arg_ids_t, int);

	IPPOOL_ACT_BEGIN() {
		result = ippool_parse_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} IPPOOL_ACT_END();

	if (msg.pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified pool %s\n", msg.pool_name);
	}

out:
	return result;
}

static void ippool_act_ip_pool_addrblock_show(struct ippool_api_addrblock *block, int num_blocks, int brief)
{
	int block_index;
	struct in_addr ip_addr;
	char ip1[16];
	char ip2[16];

	for (block_index = 0; block_index < num_blocks; block_index++) {
		ip_addr.s_addr = block->first_addr.s_addr;
		strcpy(&ip1[0], inet_ntoa(ip_addr));
		ip_addr.s_addr = htonl(ntohl(ip_addr.s_addr) + block->num_addrs - 1);
		strcpy(&ip2[0], inet_ntoa(ip_addr));
		printf("    base %s thru %s", ip1, ip2);
		if (!brief) {
			ip_addr.s_addr = block->netmask.s_addr;
			printf(" (size %d), netmask %s", block->num_addrs, inet_ntoa(ip_addr));
		}
		printf("\n");
		block++;
	}
}

static int ippool_act_ip_pool_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_arg_ids_t, struct ippool_api_pool_msg_data);

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = ippool_get_1(pool_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	result = 0;
	printf("IP pool %s:-\n", clnt_res.pool_name);
	printf("  max pool size: %d%s\n",
	       clnt_res.max_addrs, (clnt_res.max_addrs == 0) ? " (unlimited)" : "");
	printf("  debug messages: %s, drain: %s\n",
	       clnt_res.trace ? "YES" : "NO", clnt_res.drain ? "YES" : "NO");
	printf("  address blocks:-\n");
	if (clnt_res.addr_block.addr_block_len > 0) {
		ippool_act_ip_pool_addrblock_show(clnt_res.addr_block.addr_block_val, clnt_res.addr_block.addr_block_len, 0);
	} else {
		printf("    none\n");
	}
	if (clnt_res.rsvd_block.rsvd_block_len > 0) {
		printf("  reserved address blocks:-\n");
		ippool_act_ip_pool_addrblock_show(clnt_res.rsvd_block.rsvd_block_val, clnt_res.rsvd_block.rsvd_block_len, 0);
	}
	printf("  total addresses: %d, available: %d\n",
	       clnt_res.num_addrs, clnt_res.num_avail);
	printf("  pool use statistics:-\n");
	printf("    allocs: %lu, frees: %lu, alloc_fails: %lu\n",
	       clnt_res.stats.num_allocs, clnt_res.stats.num_frees, clnt_res.stats.num_alloc_fails);

	if (clnt_res.avail_block.avail_block_len > 0) {
		printf("  available address blocks:-\n");
		ippool_act_ip_pool_addrblock_show(clnt_res.avail_block.avail_block_val, clnt_res.avail_block.avail_block_len, 1);
	}

	printf("\n");

out:
	return result;
}

static int ippool_act_ip_pool_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct ippool_api_pool_list_msg_data clnt_res;
	struct ippool_api_pool_list_entry *walk;
	int result;
	const char **pool_names;
	int index;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = ippool_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.num_pools > 0) {
		pool_names = calloc(clnt_res.num_pools, sizeof(pool_names[0]));
		if (pool_names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", strerror(ENOMEM));
			goto out;
		}
	
		walk = clnt_res.pools;
		for (index = 0; index < clnt_res.num_pools; index++) {
			if ((walk == NULL) || (walk->pool_name[0] == '\0')) {
				break;
			}
			pool_names[index] = walk->pool_name;
			walk = walk->next;
		}	

		/* Sort the pool names */
		qsort(&pool_names[0], index, sizeof(pool_names[0]), ippool_name_compare);

		for (index = 0; index < clnt_res.num_pools; index++) {
			printf("\t%s\n", pool_names[index]);
		}

		free(pool_names);
	}

	result = 0;

out:
	return result;
}

static int ippool_act_ip_pool_addrblock_add(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	struct ippool_api_addrblock msg = { { 0, } };
	IPPOOL_ACT_DECLARATIONS(10, ippool_arg_ids_t, int);
	int flags = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		case IPPOOL_ARGID_FIRST_ADDR:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.first_addr, flags, 0);
			break;
		case IPPOOL_ARGID_NETMASK:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.netmask, flags, 0);
			break;
		case IPPOOL_ARGID_NUM_ADDRS:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.num_addrs, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addrblock_add_1(pool_name, msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Added address block to pool %s\n", pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_addrblock_remove(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	struct ippool_api_addrblock msg = { { 0, } };
	IPPOOL_ACT_DECLARATIONS(10, ippool_arg_ids_t, int);
	int flags = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		case IPPOOL_ARGID_FIRST_ADDR:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.first_addr, flags, 0);
			break;
		case IPPOOL_ARGID_NETMASK:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.netmask, flags, 0);
			break;
		case IPPOOL_ARGID_NUM_ADDRS:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.num_addrs, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addrblock_remove_1(pool_name, msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Removed address block from pool %s\n", pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_addrblock_reserve(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	struct ippool_api_addrblock msg = { { 0, } };
	IPPOOL_ACT_DECLARATIONS(10, ippool_arg_ids_t, int);
	int flags = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		case IPPOOL_ARGID_FIRST_ADDR:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.first_addr, flags, 0);
			break;
		case IPPOOL_ARGID_NUM_ADDRS:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.num_addrs, flags, 0);
			break;
		case IPPOOL_ARGID_NETMASK:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.netmask, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addrblock_reserve_1(pool_name, msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Reserved address block in pool %s\n", pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_addrblock_unreserve(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	struct ippool_api_addrblock msg = { { 0, } };
	IPPOOL_ACT_DECLARATIONS(10, ippool_arg_ids_t, int);
	int flags = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		case IPPOOL_ARGID_FIRST_ADDR:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.first_addr, flags, 0);
			break;
		case IPPOOL_ARGID_NUM_ADDRS:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.num_addrs, flags, 0);
			break;
		case IPPOOL_ARGID_NETMASK:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.netmask, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addrblock_unreserve_1(pool_name, msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Unreserved address block in pool %s\n", pool_name);
	}

out:
	return result;
}

#ifdef IPPOOL_TEST

static int ippool_act_ip_pool_addr_alloc(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	IPPOOL_ACT_DECLARATIONS(10, ippool_arg_ids_t, struct ippool_api_addr_alloc_msg_data);

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addr_alloc_1(pool_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}
	if (!opt_quiet) {
		struct in_addr ip;
		ip.s_addr = clnt_res.addr.s_addr;
		fprintf(stderr, "Allocated address %s from pool %s\n", inet_ntoa(ip), pool_name);
	}

out:
	return result;
}

static int ippool_act_ip_pool_addr_free(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *pool_name = NULL;
	struct ippool_api_ip_addr msg = { INADDR_ANY, };
	IPPOOL_ACT_DECLARATIONS(40, ippool_arg_ids_t, int);
	int flags = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_ARGID_POOL_NAME:
			pool_name = arg_values[arg];
			break;
		case IPPOOL_ARGID_ADDR:
			IPPOOL_ACT_PARSE_ARG(args[arg], arg_values[arg], msg, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END();

	if (pool_name == NULL) {
		fprintf(stderr, "Required pool_name argument missing\n");
		result = -EINVAL;
		goto out;
	}
	if (msg.s_addr == INADDR_ANY) {
		fprintf(stderr, "Required addr argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_addr_free_1(pool_name, msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Returned address to pool %s\n", pool_name);
	}

out:
	return result;
}

#endif /* IPPOOL_TEST */

/*****************************************************************************
 * config save/restore
 *****************************************************************************/

#define Y_OR_N(_var) (_var) ? "yes" : "no"

#undef ARG
#undef FLG

#define ARG(id, name, flag, type, doc) \
	{ name, { IPPOOL_CONFIG_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#define FLG(id, name, doc) \
	{ name, { IPPOOL_CONFIG_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	IPPOOL_CONFIG_ARGID_FILENAME,
} ippool_config_arg_ids_t;

static struct cli_arg_entry ippool_args_config[] = {
	ARG(FILENAME, 		"file", 		0, 	string,	"Filename for save/restore operation."),
	{ NULL, },
};

static int ippool_config_get_line(char *buffer, int buf_size, FILE *file)
{
	int count = 0;

	buffer = fgets(buffer, buf_size, file);
	if (buffer == NULL) {
		return -1;
	}
	count = strlen(buffer);
	if (count > 0) {
		/* strip cr at end of line */
		count--;
		buffer[count] = '\0';
	}
	
	return count;
}

static int ippool_config_restore(const char *file_name)
{
	int result = 0;
	FILE *file = NULL;
	char *buffer = NULL;
	int count;
	char *cmd[] = { NULL, };

	if (file_name == NULL) {
		result = -EINVAL;
		goto out;
	}

	buffer = malloc(4000);
	if (buffer == NULL) {
		result = -ENOMEM;
		goto out;
	}
	cmd[0] = buffer;

	/* Open the input stream */
	
	file = fopen(file_name, "r");
	if (file == NULL) {
		fprintf(stderr, "Failed to open input file %s: %m\n", file_name);
		result = -errno;
		goto out;
	}

	/* Read line into our input buffer. If a newline is escaped with a '\\',
	 * continue reading next line into buffer.
	 * Ignore lines beginning with '#'.
	 * Ignore blank lines.
	 */
	count = 0;
	for (;;) {
		int chars_read;

		chars_read = ippool_config_get_line(buffer + count, 4000 - count, file);
		if (chars_read == 0) {
			/* blank line */
			if (count > 0) goto got_command;
			continue;
		}
		if (chars_read < 0) {
			/* end of input */
			break;
		}
		if ((count == 0) && (buffer[0] == '#')) {
			/* comment line */
			if (count > 0) goto got_command;
			continue;
		}
		count += chars_read;
		if (buffer[count - 1] == '\\') {
			/* line is continued on next */
			count--;
			buffer[count] = '\0';
			continue;
		}

	got_command:
		/* replay the command  */
		result = cli_execute(1, cmd);
		if (result < 0) {
			fprintf(stderr, "Command replay at command:\n");
			fprintf(stderr, "%s\n", buffer);
			fprintf(stderr, "Aborting.\n");
			result = 0;
			goto out;
		}

		/* get ready for next line */
		count = 0;
	}

out:
	if (buffer != NULL) {
		free(buffer);
	}
	if (file != NULL) {
		fclose(file);
	}

	return result;
}

static void ippool_config_dump(FILE *file, struct ippool_api_pool_msg_data *cfg)
{
	int block;

	fprintf(file, "pool create pool_name=%s \\\n", cfg->pool_name);
	if (cfg->flags & IPPOOL_API_FLAG_MAX_ADDRS) {
		fprintf(file, "\tmax_addrs=%d \\\n", cfg->max_addrs);
	}
	if (cfg->flags & IPPOOL_API_FLAG_TRACE) {
		fprintf(file, "\ttrace=%s \\\n", Y_OR_N(cfg->trace));
	}
	if (cfg->flags & IPPOOL_API_FLAG_DRAIN) {
		fprintf(file, "\tdrain=%s \\\n", Y_OR_N(cfg->drain));
	}
	fprintf(file, "\n");
	
	if (cfg->addr_block.addr_block_len > 0) {
		struct in_addr addr;
		for (block = 0; block < cfg->addr_block.addr_block_len; block++) {
			addr.s_addr = cfg->addr_block.addr_block_val[block].first_addr.s_addr;
			fprintf(file, "pool address add pool_name=%s first_addr=%s num_addrs=%d \\\n",
				cfg->pool_name, inet_ntoa(addr),
				cfg->addr_block.addr_block_val[block].num_addrs);
			addr.s_addr = cfg->addr_block.addr_block_val[block].netmask.s_addr;
			if (addr.s_addr != INADDR_ANY) {
				fprintf(file, "\tnetmask=%s\n", inet_ntoa(addr));
			} else {
				fprintf(file, "\n");;
			}
		}
	}

	if (cfg->rsvd_block.rsvd_block_len > 0) {
		struct in_addr addr;
		for (block = 0; block < cfg->rsvd_block.rsvd_block_len; block++) {
			addr.s_addr = cfg->rsvd_block.rsvd_block_val[block].first_addr.s_addr;
			fprintf(file, "pool address reserve pool_name=%s first_addr=%s num_addrs=%d \\\n",
				cfg->pool_name, inet_ntoa(addr),
				cfg->rsvd_block.rsvd_block_val[block].num_addrs);
			addr.s_addr = cfg->rsvd_block.rsvd_block_val[block].netmask.s_addr;
			if (addr.s_addr != INADDR_ANY) {
				fprintf(file, "\tnetmask=%s\n", inet_ntoa(addr));
			} else {
				fprintf(file, "\n");;
			}
		}
	}
}

static int ippool_config_save(const char *file_name)
{
	struct ippool_api_pool_msg_data ip_pool;
	struct ippool_api_pool_list_msg_data ip_pool_list;
	struct ippool_api_pool_list_entry *ippwalk;
	int index;
	char **names;
	int result = 0;
	FILE *file;

	/* Open the output stream */
	
	if (file_name != NULL) {
		file = fopen(file_name, "w");
		if (file == NULL) {
			fprintf(stderr, "Failed to open output file %s: %m\n", file_name);
			result = -errno;
			goto out;
		}
	} else {
		file = stdout;
	}

	fprintf(file, "\n# ip pools\n");
	memset(&ip_pool_list, 0, sizeof(ip_pool_list));
	result = ippool_list_1(&ip_pool_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (ip_pool_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-ip_pool_list.result));
		result = ip_pool_list.result;
		goto out;
	}

	if (ip_pool_list.num_pools > 0) {
		names = calloc(ip_pool_list.num_pools, sizeof(names[0]));
		if (names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", strerror(ENOMEM));
			goto out;
		}
	
		ippwalk = ip_pool_list.pools;
		for (index = 0; index < ip_pool_list.num_pools; index++) {
			if ((ippwalk == NULL) || (ippwalk->pool_name[0] == '\0')) {
				break;
			}
			names[index] = ippwalk->pool_name;
			ippwalk = ippwalk->next;
		}	

		/* Sort the pool names */
		qsort(&names[0], index, sizeof(names[0]), ippool_name_compare);

		for (index = 0; index < ip_pool_list.num_pools; index++) {
			memset(&ip_pool, 0, sizeof(ip_pool));
			result = ippool_get_1(names[index], &ip_pool, cl);
			if (result != RPC_SUCCESS) {
				clnt_perror(cl, server);
				result = -EAGAIN;
				goto out_pool;
			}

			if (ip_pool.result_code < 0) {
				continue;
			}

			ippool_config_dump(file, &ip_pool);
		}

	out_pool:
		free(names);
	}

out:
	if (file != NULL) {
		fflush(file);
		fclose(file);
	}

	return result;
}

static int ippool_act_config_save(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *file_name = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_config_arg_ids_t, int);
	int ret = 0;

	clnt_res = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_CONFIG_ARGID_FILENAME:
			file_name = arg_values[arg];
			break;
		}
	} IPPOOL_ACT_END();

	ret = ippool_config_save(file_name);

out:
	return ret;
}

static int ippool_act_config_restore(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *file_name = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_config_arg_ids_t, int);
	int ret = 0;

	clnt_res = 0;

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_CONFIG_ARGID_FILENAME:
			file_name = arg_values[arg];
			break;
		}
	} IPPOOL_ACT_END();

	if (file_name == NULL) {
		fprintf(stderr, "Required file_name argument is missing.\n");
		exit(1);
	}

	ret = ippool_config_restore(file_name);

out:
	return ret;
}


/*****************************************************************************
 * Test/debug functions
 *****************************************************************************/

#ifdef IPPOOL_TEST

#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { IPPOOL_TEST_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { IPPOOL_TEST_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	IPPOOL_TEST_ARGID_LOG_MESSAGE,
} ippool_test_arg_ids_t;

static struct cli_arg_entry ippool_args_test_log[] = {
	ARG(LOG_MESSAGE,	"message",		0,	string,	"Send a message to the IPPOOL service log file."),
	{ NULL, },
};

static int ippool_act_test_log(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *message = NULL;
	IPPOOL_ACT_DECLARATIONS(4, ippool_test_arg_ids_t, int);

	IPPOOL_ACT_BEGIN() {
		switch (arg_id) {
		case IPPOOL_TEST_ARGID_LOG_MESSAGE:
			message = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} IPPOOL_ACT_END()

	if (message == NULL) {
		fprintf(stderr, "Required message argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = ippool_test_log_1(message, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", strerror(-clnt_res));
		result = -clnt_res;
		goto out;
	}

out:
	return 0;
}

#endif /* IPPOOL_TEST */

/*****************************************************************************
 * Syntax tree
 *****************************************************************************/

static struct cli_node_entry cmds[] = {
	{ 0, CLI_NODE_TYPE_COMMAND, "exit", "exit application", ippool_act_exit },
	{ 0, CLI_NODE_TYPE_COMMAND, "quit", "exit application", ippool_act_exit },
	{ 0, CLI_NODE_TYPE_COMMAND, "help", "display help information", ippool_act_help },
	{ 0, CLI_NODE_TYPE_KEYWORD, "config", "configuration save/restore", },
	{ 1, CLI_NODE_TYPE_COMMAND, "save", "save configuration", ippool_act_config_save, &ippool_args_config[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "restore", "restore configurationfrom file", ippool_act_config_restore, &ippool_args_config[0], },
	{ 0, CLI_NODE_TYPE_KEYWORD, "server", "server configuration", },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify server parameters", ippool_act_server_modify, &ippool_args_server_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show server parameters", ippool_act_server_show, },
	{ 0, CLI_NODE_TYPE_COMMAND, "version", "show system version", ippool_act_system_show_version },
	{ 0, CLI_NODE_TYPE_KEYWORD, "pool", "pool commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "create", "create a new ip pool", ippool_act_ip_pool_create, &ipppool_args_create[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "delete", "delete an ip pool", ippool_act_ip_pool_delete, &ipppool_args_delete[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify an ip pool", ippool_act_ip_pool_modify, &ipppool_args_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show an ip pool", ippool_act_ip_pool_show, &ipppool_args_show[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "list", "list all ip pools", ippool_act_ip_pool_list },
	{ 1, CLI_NODE_TYPE_KEYWORD, "address", "ip pool address commands" },
	{ 2, CLI_NODE_TYPE_COMMAND, "add", "add a block of addresses to pool", ippool_act_ip_pool_addrblock_add, &ipppool_args_addrblock_add[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "remove", "remove a block of addresses from pool", ippool_act_ip_pool_addrblock_remove, &ipppool_args_addrblock_remove[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "reserve", "reserve a block of addresses", ippool_act_ip_pool_addrblock_reserve, &ipppool_args_addrblock_reserve[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "unreserve", "unreserve a block of addresses", ippool_act_ip_pool_addrblock_unreserve, &ipppool_args_addrblock_unreserve[0], },
#ifdef IPPOOL_TEST
	{ 2, CLI_NODE_TYPE_COMMAND, "allocate", "allocate an address", ippool_act_ip_pool_addr_alloc, &ipppool_args_addr_alloc[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "free", "free an address (return to pool)", ippool_act_ip_pool_addr_free, &ipppool_args_addr_free[0], },
	{ 0, CLI_NODE_TYPE_KEYWORD, "test", "test commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "log", "test messages", ippool_act_test_log, &ippool_args_test_log[0], },
#endif /* IPPOOL_TEST */
	{ 0, CLI_NODE_TYPE_END, NULL, },
};

/*****************************************************************************
 * Application init and cleanup
 *****************************************************************************/

static void cleanup(void)
{
	clnt_destroy(cl);
	if (interactive) {
		cli_write_history_file(ippool_histfile, ippool_histfile_maxsize);
	}
}

int main(int argc, char *argv[])
{
	int result;
	int opt;
	int arg = 1;
	static char *exit_cmd[] = { "exit", NULL };
	char *hist_size;

	strcpy(server, "localhost");

	cli_init("ippool");
	result = cli_add_commands(&cmds[0]);
	if (result < 0) {
		fprintf(stderr, "Application initialization error.\n");
		return result;
	}

	cl = clnt_create(server, IPPOOL_PROG, IPPOOL_VERSION, "udp");
	if (cl == NULL) {
		clnt_pcreateerror(server);
		exit(1);
	}
	atexit(cleanup);

	opterr = 0;		/* no error messages please */

	opt = getopt(argc, argv, "qR:");
	switch (opt) {
	case 'q':
		opt_quiet = 1;
		arg++;
		break;
	case 'R':
		strncpy(server, optarg, sizeof(server));
		arg += 2;
		ippool_set_prompt(server);
		break;
	default:
		break;
	}

	/* If user supplied arguments, send them to the CLI now and immediately exit.
	 */
	if (argc > arg) {
		(void) cli_execute(argc - arg, &argv[arg]);
		(void) cli_execute(1, exit_cmd);
	} else {
		/* interactive mode */
		interactive = 1;
		ippool_histfile = getenv("IPPOOL_HISTFILE");
		if (ippool_histfile == NULL) {
			ippool_histfile = "~/.ippool_history";
		}
		hist_size = getenv("IPPOOL_HISTFILESIZE");
		if (hist_size != NULL) {
			ippool_histfile_maxsize = strtoul(hist_size, NULL, 0);
		}

		cli_read_history_file(ippool_histfile);
		cli_run();
	}

	return 0;
}
