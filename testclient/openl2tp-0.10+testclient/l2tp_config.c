/*****************************************************************************
 * Copyright (C) 2004,2005,2006 Katalix Systems Ltd
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
 * Command Line Interface for OpenL2TP.
 * This started out as a quick hack but just grew and grew. There's duplicate
 * code and memory leaks all over the place.
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

#include "l2tp_private.h"
#include "l2tp_rpc.h"

static char *empty_string = "";

static int opt_quiet;
static int interactive = 0;

static CLIENT *cl;
static char server[48];
static char *l2tp_histfile = NULL;
static int l2tp_histfile_maxsize = -1;

#define L2TP_ACT_DECLARATIONS(_max_args, _ids_type, _clnt_res_type)				\
	struct cli_node *args[_max_args];							\
	char *arg_values[_max_args];								\
	int num_args = _max_args;								\
	int arg;										\
	int result;										\
	_ids_type arg_id;									\
	_clnt_res_type clnt_res;

#define L2TP_ACT_BEGIN()									\
	result = cli_find_args(argc, argv, node, &args[0], &arg_values[0], &num_args);		\
	if (result == 0) {									\
		for (arg = 0; arg < num_args; arg++) {						\
			if (args[arg] && args[arg]->arg) {					\
				arg_id = args[arg]->arg->id;

#define L2TP_ACT_END()										\
			}									\
		}										\
	} else {										\
		/* tell caller which arg failed */						\
		*arg_num = num_args;								\
		result = -EINVAL;								\
		goto out;									\
	}


#define L2TP_ACT_PARSE_ARG(_arg_node, _arg_value, _field, _flag_var, _flag)			\
	result = _arg_node->arg->parser(_arg_node, _arg_value, &_field);			\
	if (result < 0) {									\
		goto out;									\
	}											\
	_flag_var |= _flag;


#define L2TP_ACT_PARSE_ARG_FLAG(_arg_node, _arg_value, _field, _field_flag, _flag_var, _flag)    \
        {                                                                                        \
	  int v;                                                                                 \
 	  result = _arg_node->arg->parser(_arg_node, _arg_value, &v);			         \
   	  if (result < 0) {									 \
		goto out;									 \
	  }											 \
          if (v) {                                                                               \
            _field |= _field_flag;                                                               \
          } else {                                                                               \
            _field &= ~_field_flag;                                                              \
          }                                                                                      \
  	  _flag_var |= _flag;                                                                    \
	}


#define L2TP_ACT_PARSE_ARG_FLAG_NEG(_arg_node, _arg_value, _field, _field_flag, _flag_var, _flag) \
        {                                                                                         \
	  int v;                                                                                  \
 	  result = _arg_node->arg->parser(_arg_node, _arg_value, &v);		 	          \
   	  if (result < 0) {							 		  \
		goto out;								  	  \
	  }											  \
          if (v) {                                                                                \
            _field &= ~_field_flag;                                                               \
          } else {                                                                                \
            _field |= _field_flag;                                                                \
          }                                                                                       \
  	  _flag_var |= _flag;                                                                     \
	}


static void print_trace_flags(int trace_flags, const char *pfx)
{
	printf("%s  trace flags:%s%s%s%s%s%s%s%s%s%s%s%s\n",
	       pfx ? pfx : "",
	       (trace_flags & L2TP_DEBUG_PROTOCOL) ? " PROTOCOL" : "",
	       (trace_flags & L2TP_DEBUG_FSM) ? " FSM" : "",
	       (trace_flags & L2TP_DEBUG_API) ? " API" : "",
	       (trace_flags & L2TP_DEBUG_AVP) ? " AVP" : "",
	       (trace_flags & L2TP_DEBUG_AVP_HIDE) ? " AVPHIDE" : "",
	       (trace_flags & L2TP_DEBUG_AVP_DATA) ? " AVPDATA" : "",
	       (trace_flags & L2TP_DEBUG_FUNC) ? " FUNC" : "",
	       (trace_flags & L2TP_DEBUG_XPRT) ? " XPRT" : "",
	       (trace_flags & L2TP_DEBUG_DATA) ? " DATA" : "",
	       (trace_flags & L2TP_DEBUG_PPP) ? " PPP" : "",
	       (trace_flags & L2TP_DEBUG_SYSTEM) ? " SYSTEM" : "",
	       (trace_flags == 0) ? " NONE" : "");
}

/*****************************************************************************
 * server ...
 *****************************************************************************/

#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_SERVER_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#define FLG(id, name, doc) \
	{ name, { L2TP_SERVER_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	L2TP_SERVER_ARGID_NAME,
} l2tp_server_arg_ids_t;

static struct cli_arg_entry l2tp_args_server_modify[] = {
	ARG(NAME, 		"name", 		0, 	string,	"IP address or hostname of L2TP daemon to attach to. Default=localhost."),
	{ NULL, },
};

static void l2tp_set_prompt(char *server_name)
{
	static char prompt[48];

	snprintf(prompt, sizeof(prompt), "l2tp-%s", server_name);
	cli_set_prompt(prompt);
}


static int l2tp_act_server_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *server_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_server_arg_ids_t, int);

	clnt_res = 0;

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SERVER_ARGID_NAME:
			server_name = arg_values[arg];
			break;
		}
	} L2TP_ACT_END();

	if (server_name == NULL) {
		fprintf(stderr, "Required name argument is missing.\n");
		goto out;
	}
	if (strcmp(server_name, &server[0])) {
		strncpy(&server[0], server_name, sizeof(server));

		clnt_destroy(cl);
		cl = clnt_create(server, L2TP_PROG, L2TP_VERSION, "tcp");
		if (cl == NULL) {
			clnt_pcreateerror(server);
			exit(1);
		}

		l2tp_set_prompt(server_name);
	}

out:
	return 0;
}

static int l2tp_act_server_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	printf("Connected to server: %s\n", server);
	return 0;
}

/*****************************************************************************
 * system ...
 *****************************************************************************/

#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_SYSTEM_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_SYSTEM_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	L2TP_SYSTEM_ARGID_TRACE_FLAGS,
	L2TP_SYSTEM_ARGID_MAX_TUNNELS,
	L2TP_SYSTEM_ARGID_MAX_SESSIONS,
	L2TP_SYSTEM_ARGID_DRAIN_TUNNELS,
	L2TP_SYSTEM_ARGID_TUNNEL_ESTTO,
	L2TP_SYSTEM_ARGID_TUNNEL_PERSIST_PENDTO,
	L2TP_SYSTEM_ARGID_SESSION_ESTTO,
	L2TP_SYSTEM_ARGID_DENY_LOCAL_TUNNEL_CREATES,
	L2TP_SYSTEM_ARGID_DENY_REMOTE_TUNNEL_CREATES,
	L2TP_SYSTEM_ARGID_RESET_STATISTICS,
} l2tp_system_arg_ids_t;

static struct cli_arg_entry l2tp_args_system_modify[] = {
	ARG(TRACE_FLAGS, 		"trace_flags", 		0, 	uint32,	"Default trace flags to use if not otherwise overridden."),
	ARG(MAX_TUNNELS, 		"max_tunnels", 		0, 	uint32,	"Maximum number of tunnels permitted. Default=0 (no limit)."),
	ARG(MAX_SESSIONS, 		"max_sessions", 	0, 	uint32,	"Maximum number of sessions permitted. Default=0 (no limit)."),
	ARG(DRAIN_TUNNELS,		"drain_tunnels",	0, 	bool, 	"Enable the draining of existing tunnels (prevent new tunnels "
	    									"from being created."),
	ARG(TUNNEL_ESTTO, 		"tunnel_establish_timeout", 0, 	uint32,	"Timeout for tunnel establishment. Default=120 seconds.."),
	ARG(SESSION_ESTTO, 		"session_establish_timeout", 0, uint32,	"Timeout for session establishment. Default=120 seconds.."),
	ARG(TUNNEL_PERSIST_PENDTO,	"tunnel_persist_pend_timeout", 0, uint32, "Timeout to hold persistent tunnels before retrying. Default=300 seconds.."),
	ARG(DENY_LOCAL_TUNNEL_CREATES,	"deny_local_tunnel_creates", 0,	bool,	"Deny the creation of new tunnels by local request."),
	ARG(DENY_REMOTE_TUNNEL_CREATES,	"deny_remote_tunnel_creates", 0, bool,	"Deny the creation of new tunnels by remote peers."),
	FLG(RESET_STATISTICS,		"reset_statistics", 			"Reset statistics."),
	{ NULL, },
};


static int l2tp_act_exit(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	exit(0);
}

static int l2tp_act_help(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	cli_show_help();
	return 0;
}

static int l2tp_act_system_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	cli_bool_t bool_arg;
	struct l2tp_api_system_msg_data msg = { { 0, } };
	L2TP_ACT_DECLARATIONS(10, l2tp_system_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SYSTEM_ARGID_TRACE_FLAGS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.trace_flags, msg.config.flags, L2TP_API_CONFIG_FLAG_TRACE_FLAGS);
			break;
		case L2TP_SYSTEM_ARGID_DRAIN_TUNNELS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, msg.config.flags, L2TP_API_CONFIG_FLAG_DRAIN_TUNNELS);
			msg.config.drain_tunnels = bool_arg;
			break;
		case L2TP_SYSTEM_ARGID_MAX_TUNNELS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.max_tunnels, msg.config.flags, L2TP_API_CONFIG_FLAG_MAX_TUNNELS);
			break;
		case L2TP_SYSTEM_ARGID_MAX_SESSIONS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.max_sessions, msg.config.flags, L2TP_API_CONFIG_FLAG_MAX_SESSIONS);
			break;
		case L2TP_SYSTEM_ARGID_TUNNEL_ESTTO:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.tunnel_establish_timeout, msg.config.flags, 
					   L2TP_API_CONFIG_FLAG_TUNNEL_ESTABLISH_TIMEOUT);
			break;
		case L2TP_SYSTEM_ARGID_SESSION_ESTTO:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.session_establish_timeout, msg.config.flags, 
					   L2TP_API_CONFIG_FLAG_SESSION_ESTABLISH_TIMEOUT);
			break;
		case L2TP_SYSTEM_ARGID_TUNNEL_PERSIST_PENDTO:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.tunnel_persist_pend_timeout, msg.config.flags, 
					   L2TP_API_CONFIG_FLAG_TUNNEL_PERSIST_PEND_TIMEOUT);
			break;
 		case L2TP_SYSTEM_ARGID_DENY_LOCAL_TUNNEL_CREATES:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.deny_local_tunnel_creates, msg.config.flags, 
					   L2TP_API_CONFIG_FLAG_DENY_LOCAL_TUNNEL_CREATES);
			break;
		case L2TP_SYSTEM_ARGID_DENY_REMOTE_TUNNEL_CREATES:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.config.deny_remote_tunnel_creates, msg.config.flags, 
					   L2TP_API_CONFIG_FLAG_DENY_REMOTE_TUNNEL_CREATES);
			break;
		case L2TP_SYSTEM_ARGID_RESET_STATISTICS:
			msg.config.flags |= L2TP_API_CONFIG_FLAG_RESET_STATISTICS;
			break;
		}
	} L2TP_ACT_END();

	result = l2tp_system_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		exit(1);
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		return 0;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified system config\n");
	}

out:
	return 0;
}

static int l2tp_act_system_show_version(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_app_msg_data app;
	int result;

	memset(&app, 0, sizeof(app));
	result = l2tp_app_info_get_1(&app, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	printf("OpenL2TP V%d.%d, built %s [%s],\n\t%s %s\n",
	       app.major, app.minor, app.build_date, app.build_time,
	       L2TP_APP_COPYRIGHT_INFO, L2TP_APP_VENDOR_INFO);
	if (app.patches.patches_len > 0) {
		int patch;
		printf("  Patches: ");
		for (patch = 0; patch < app.patches.patches_len; patch++) {
			printf("%d ", app.patches.patches_val[patch]);
		}
		printf("\n");
	}
	if (app.cookie != L2TP_APP_COOKIE) {
		printf("*** WARNING: CONTROL APPLICATION AND DAEMON ARE OUT OF SYNC. ***\n");
		printf("*** UNDEFINED BEHAVIOR MAY RESULT. REINSTALL TO FIX.         ***\n\n");
	}

out:
	return result;
}

static int l2tp_act_system_show_config(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_app_msg_data app;
	struct l2tp_api_system_msg_data sys;
	int result;

	memset(&app, 0, sizeof(app));
	result = l2tp_app_info_get_1(&app, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	memset(&sys, 0, sizeof(sys));
	result = l2tp_system_get_1(&sys, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (app.cookie != L2TP_APP_COOKIE) {
		printf("*** WARNING: CONTROL APPLICATION AND DAEMON ARE OUT OF SYNC. ***\n");
		printf("*** UNDEFINED BAHAVIOR MAY RESULT. REINSTALL TO FIX.         ***\n\n");
	}

	printf("L2TP configuration:\n");
	printf("  UDP port: %hu\n", sys.config.udp_port);
	printf("  max tunnels: %u%s, max sessions: %u%s\n", 
	       sys.config.max_tunnels, sys.config.max_tunnels == 0 ? " (unlimited)" : "",
	       sys.config.max_sessions, sys.config.max_sessions == 0 ? " (unlimited)" : "");
	printf("  drain tunnels: %s\n", sys.config.drain_tunnels ? "YES" : "NO");
	printf("  tunnel establish timeout: %hu seconds%s\n", 
	       sys.config.tunnel_establish_timeout, sys.config.tunnel_establish_timeout == 0 ? " (unlimited)" : "");
	printf("  session establish timeout: %hu seconds%s\n", 
	       sys.config.session_establish_timeout, sys.config.session_establish_timeout == 0 ? " (unlimited)" : "");
	printf("  tunnel persist pend timeout: %hu seconds\n", sys.config.tunnel_persist_pend_timeout);
	printf("  deny local tunnel creation: %s, deny remote tunnel creation: %s\n",
	       sys.config.deny_local_tunnel_creates ? "YES" : "NO", sys.config.deny_remote_tunnel_creates ? "YES" : "NO");
	print_trace_flags(sys.config.trace_flags, NULL);

out:
	return result;
}

static int l2tp_act_system_show_status(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_system_msg_data sys;
	int result;

	memset(&sys, 0, sizeof(sys));
	result = l2tp_system_get_1(&sys, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	printf("L2TP service status:-\n");
	printf("  tunnels: %u, sessions: %u\n",
	       sys.status.num_tunnels, sys.status.num_sessions);

out:
	return result;
}

static int l2tp_act_system_show_stats(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_system_msg_data sys;
	int result;
	int type;
	static const char *msg_names[] = {
		"ILLEGAL", "SCCRQ", "SCCRP", "SCCCN", "STOPCCN", "RESERVED1", "HELLO",
		"OCRQ", "OCRP", "OCCN", "ICRQ", "ICRP", "ICCN", "RESERVED2",
		"CDN", "WEN", "SLI" 
	};

	memset(&sys, 0, sizeof(sys));
	result = l2tp_system_get_1(&sys, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	printf("L2TP counters:-\n");
	printf("  Total messages sent: %u, received: %u, retransmitted: %u\n",
	       sys.status.stats.total_sent_control_frames, sys.status.stats.total_rcvd_control_frames,
	       sys.status.stats.total_retransmitted_control_frames);
	printf("    illegal: %u, unsupported: %u, ignored AVPs: %u, vendor AVPs: %u\n",
	       sys.status.stats.illegal_messages, sys.status.stats.unsupported_messages,
	       sys.status.stats.ignored_avps, sys.status.stats.vendor_avps);
	printf("  Setup failures: tunnels: %u, sessions: %u\n", 
	       sys.status.stats.tunnel_setup_failures, sys.status.stats.session_setup_failures);
	printf("  Resource failures: control frames: %u, peers: %u\n"
	       "    tunnels: %u, sessions: %u, ppp: %u\n",
	       sys.status.stats.no_control_frame_resources,
	       sys.status.stats.no_peer_resources,
	       sys.status.stats.no_tunnel_resources,
	       sys.status.stats.no_session_resources,
	       sys.status.stats.no_ppp_resources);
	printf("  Limit exceeded errors: tunnels: %u, sessions: %u\n", 
	       sys.status.stats.too_many_tunnels, sys.status.stats.too_many_sessions);
	printf("  Frame errors: short frames: %u, wrong version frames: %u\n"
	       "     unexpected data frames: %u, bad frames: %u\n",
	       sys.status.stats.short_frames, sys.status.stats.wrong_version_frames,
	       sys.status.stats.unexpected_data_frames, sys.status.stats.bad_rcvd_frames);
	printf("  Internal: authentication failures: %u, message encode failures: %u\n"
	       "     no matching tunnel discards: %u, mismatched tunnel ids: %u\n"
	       "     no matching session_discards: %u, mismatched session ids: %u\n"
	       "     total control frame send failures: %u, event queue fulls: %u\n\n",
	       sys.status.stats.auth_fails, sys.status.stats.encode_message_fails,
	       sys.status.stats.no_matching_tunnel_id_discards, sys.status.stats.mismatched_tunnel_ids,
	       sys.status.stats.no_matching_session_id_discards, sys.status.stats.mismatched_session_ids,
	       sys.status.stats.total_control_frame_send_fails, sys.status.stats.event_queue_full_errors);

	printf("  Message counters:-\n");
	printf("%16s %16s %16s %16s\n", "Message", "RX Good", "RX Bad", "TX");
	for (type = 0; type < sys.status.stats.messages.messages_len; type++) {
		if (type == L2TP_API_MSG_TYPE_COUNT) {
			break;
		}
		printf("%16s %16u %16u %16u\n", msg_names[type], sys.status.stats.messages.messages_val[type].rx,
		       sys.status.stats.messages.messages_val[type].rx_bad, sys.status.stats.messages.messages_val[type].tx);
	}

out:
	return result;
}

/*****************************************************************************
 * Tunnel...
 *****************************************************************************/

typedef enum {
	L2TP_TUNNEL_ARGID_TRACE_FLAGS,
	L2TP_TUNNEL_ARGID_AUTH_MODE,
	L2TP_TUNNEL_ARGID_HIDE_AVPS,
	L2TP_TUNNEL_ARGID_UDP_CSUMS,
	L2TP_TUNNEL_ARGID_DO_PMTU_DISCOVERY,
	L2TP_TUNNEL_ARGID_PERSIST,
	L2TP_TUNNEL_ARGID_MTU,
	L2TP_TUNNEL_ARGID_HELLO_TIMEOUT,
	L2TP_TUNNEL_ARGID_MAX_RETRIES,
	L2TP_TUNNEL_ARGID_RX_WINDOW_SIZE,
	L2TP_TUNNEL_ARGID_TX_WINDOW_SIZE,
	L2TP_TUNNEL_ARGID_RETRY_TIMEOUT,
	L2TP_TUNNEL_ARGID_IDLE_TIMEOUT,
	L2TP_TUNNEL_ARGID_DEST_IPADDR,
	L2TP_TUNNEL_ARGID_CONFIG_ID,
	L2TP_TUNNEL_ARGID_SRC_IPADDR,
	L2TP_TUNNEL_ARGID_OUR_UDP_PORT,
	L2TP_TUNNEL_ARGID_PEER_UDP_PORT,
	L2TP_TUNNEL_ARGID_PROFILE_NAME,
	L2TP_TUNNEL_ARGID_USE_TIEBREAKER,
	L2TP_TUNNEL_ARGID_ALLOW_PPP_PROXY,
	L2TP_TUNNEL_ARGID_FRAMING_CAP,
	L2TP_TUNNEL_ARGID_BEARER_CAP,
	L2TP_TUNNEL_ARGID_HOST_NAME,
	L2TP_TUNNEL_ARGID_SECRET,
	L2TP_TUNNEL_ARGID_TUNNEL_ID,
	L2TP_TUNNEL_ARGID_MAX_SESSIONS,
	L2TP_TUNNEL_ARGID_TUNNEL_NAME,
	L2TP_TUNNEL_ARGID_PEER_PROFILE_NAME,
	L2TP_TUNNEL_ARGID_SESSION_PROFILE_NAME,
	L2TP_TUNNEL_ARGID_PPP_PROFILE_NAME,
	L2TP_TUNNEL_ARGID_INTERFACE_NAME,
	L2TP_TUNNEL_ARGID_SHOW_CONFIG,
	L2TP_TUNNEL_ARGID_SHOW_TRANSPORT,
} l2tp_tunnel_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_TUNNEL_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_TUNNEL_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

/* Paremeters for Create and Modify operations */
#define L2TP_TUNNEL_MODIFY_ARGS 															\
	ARG(TRACE_FLAGS, 	"trace_flags", 		0, 	int32, 	"Trace flags, for debugging network problems"),					\
	ARG(UDP_CSUMS,		"use_udp_checksums",	0,	bool,	"Use UDP checksums in data frames. Default: ON"),				\
	ARG(PERSIST,		"persist",		0,	bool,	"Persist (recreate automatically if tunnel fails). Default: OFF"),		\
	ARG(HELLO_TIMEOUT,	"hello_timeout",	0,	int32,	("Set timeout used for periodic L2TP Hello messages (in seconds). "		\
									 "Default: 0 (no hello messages are generated.")),				\
	ARG(MAX_RETRIES,	"max_retries",		0,	int32,	"Maximum transmit retries before assuming tunnel failure."),			\
	ARG(RETRY_TIMEOUT,	"retry_timeout",	0,	int32,	"Retry timeout - initial delay between retries."),				\
	ARG(IDLE_TIMEOUT,	"idle_timeout",		0,	int32,	"Idle timeout - automatically delete tunnel if no sessions."),			\
	ARG(MAX_SESSIONS,	"max_sessions",		0,	int32,	"Maximum number of sessions allowed on tunnel. Default=0 (limited only "	\
	    								"by max_sessions limit in system parameters)."),				\
	ARG(MTU,		"mtu",			0,	int32,	"MTU for all sessions in tunnel. Default: 1460."),				\
	ARG(PEER_PROFILE_NAME,	"peer_profile_name",	0,	string,	("Name of peer profile which will be used for default values of the " 		\
									 "tunnel's parameters.")),							\
	ARG(SESSION_PROFILE_NAME, "session_profile_name", 0,	string,	("Name of session profile which will be used for default values of the " 	\
									 "tunnel's session parameters.")),						\
	ARG(PPP_PROFILE_NAME,	"ppp_profile_name",	0,	string,	("Name of ppp profile which will be used for default values of the " 		\
									 "tunnel's session PPP parameters.")),						\
	ARG(INTERFACE_NAME,	"interface_name",	0,	string,	("Name of system interface for the tunnel. Default: l2tpN where N is tunnel_id.")) \

/* Paremeters for Create operations */
#define L2TP_TUNNEL_CREATE_ARGS 															\
	ARG(SRC_IPADDR,		"src_ipaddr",		0,	ipaddr,	"Source IP address"),								\
	ARG(PEER_UDP_PORT,	"peer_udp_port",	0,	uint16,	"UDP port number with which to contact peer L2TP server. Default: 1701"),	\
	ARG(OUR_UDP_PORT,	"our_udp_port",		0,	uint16,	"Local UDP port number with which to contact peer L2TP server. "		\
									"Default: autogenerated"),							\
	ARG(USE_TIEBREAKER,	"use_tiebreaker",	0,	bool,	"Enable use of a tiebreaker when setting up the tunnel. Default: ON"),		\
	ARG(ALLOW_PPP_PROXY,	"allow_ppp_proxy",	0,	bool,	"Allow PPP proxy"),								\
	ARG(FRAMING_CAP,	"framing_caps",		0,	string,	("Framing capabilities:-\n"							\
									 "none, sync, async, any")),								\
	ARG(BEARER_CAP,		"bearer_caps",		0,	string,	("Bearer capabilities:-\n"							\
									 "none, digital, analog, any")),								\
	ARG(HOST_NAME,		"host_name",		0,	string,	"Name to advertise to peer when setting up the tunnel."),			\
	ARG(SECRET,		"secret",		0,	string,	("Optional secret which is shared with tunnel peer. Must be specified when "	\
									 "hide_avps is enabled.")),							\
	ARG(AUTH_MODE,		"auth_mode",		0,	string, ("Tunnel authentication mode:-\n"						\
									 "none      - no authentication, unless secret is given\n"			\
									 "simple    - check peer hostname\n"						\
									 "challenge - require tunnel secret\n")),					\
	ARG(HIDE_AVPS,		"hide_avps",		0,	bool,	"Hide AVPs. Default OFF"),							\
	ARG(RX_WINDOW_SIZE,	"rx_window_size",	0,	uint16,	"Rx window size"),								\
	ARG(TX_WINDOW_SIZE,	"tx_window_size",	0,	uint16,	"Tx window size"),								\
	ARG(DO_PMTU_DISCOVERY,	"do_pmtu_discovery",	0,	bool,	"Do Path MTU Discovery. Default: OFF")						\


#define L2TP_TUNNEL_ID_ARGS																\
	ARG(TUNNEL_ID,		"tunnel_id",		0,	uint16,	"Tunnel ID of tunnel."),							\
	ARG(TUNNEL_NAME,	"tunnel_name",		0,	string,	"Administrative name of tunnel.")						\

static struct cli_arg_entry l2tp_args_tunnel_create[] = {
	ARG(DEST_IPADDR,	"dest_ipaddr",		0,	ipaddr,	"Destination IP address"),
	ARG(CONFIG_ID,		"config_id",		0,	uint32,	("Optional configuration id, used to uniquify a tunnel when there is more "
									 "the one tunnel between the same two IP addresses")),
	ARG(TUNNEL_NAME,	"tunnel_name",		0,	string,	"Administrative name of tunnel."),
#ifdef L2TP_TEST
	ARG(TUNNEL_ID,		"tunnel_id",		0,	uint16,	"Optional tunnel id of new tunnel. Usually auto-generated. For testing only."),
#endif
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of tunnel profile which will be used for default values of this "
									 "tunnel's parameters.")),
	L2TP_TUNNEL_CREATE_ARGS,
	L2TP_TUNNEL_MODIFY_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_delete[] = {
	L2TP_TUNNEL_ID_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_modify[] = {
	L2TP_TUNNEL_ID_ARGS,
	L2TP_TUNNEL_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_show[] = {
	L2TP_TUNNEL_ID_ARGS,
	FLG(SHOW_CONFIG,	"config",				"Display only tunnel configuration/status information."),
	FLG(SHOW_TRANSPORT,	"transport",				"Display only tunnel transport information."),
	{ NULL, },
};

static int l2tp_parse_tunnel_arg(l2tp_tunnel_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_tunnel_msg_data *msg)
{
	int result = -EINVAL;

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_TUNNEL_ARGID_PROFILE_NAME:
		OPTSTRING(msg->tunnel_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->tunnel_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->tunnel_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_TRACE_FLAGS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->trace_flags, msg->flags, L2TP_API_TUNNEL_FLAG_TRACE_FLAGS);
		break;
	case L2TP_TUNNEL_ARGID_AUTH_MODE:
		if (strcasecmp(arg_value, "none") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_NONE;
		} else if (strcasecmp(arg_value, "simple") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_SIMPLE;
		} else if (strcasecmp(arg_value, "challenge") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE;
		} else {
			fprintf(stderr, "Bad authmode %s: expecting none|simple|challenge\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_FLAG_AUTH_MODE;
		break;
	case L2TP_TUNNEL_ARGID_MAX_SESSIONS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_sessions, msg->flags, L2TP_API_TUNNEL_FLAG_MAX_SESSIONS);
		break;
	case L2TP_TUNNEL_ARGID_HIDE_AVPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->hide_avps, msg->flags, L2TP_API_TUNNEL_FLAG_HIDE_AVPS);
		break;
	case L2TP_TUNNEL_ARGID_UDP_CSUMS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_udp_checksums, msg->flags, L2TP_API_TUNNEL_FLAG_USE_UDP_CHECKSUMS);
		break;
	case L2TP_TUNNEL_ARGID_PERSIST:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->persist, msg->flags, L2TP_API_TUNNEL_FLAG_PERSIST);
		break;
	case L2TP_TUNNEL_ARGID_DO_PMTU_DISCOVERY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->do_pmtu_discovery, msg->flags, L2TP_API_TUNNEL_FLAG_DO_PMTU_DISCOVERY);
		break;
	case L2TP_TUNNEL_ARGID_MTU:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->mtu, msg->flags, L2TP_API_TUNNEL_FLAG_MTU);
		break;
	case L2TP_TUNNEL_ARGID_HELLO_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->hello_timeout, msg->flags, L2TP_API_TUNNEL_FLAG_HELLO_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_MAX_RETRIES:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_retries, msg->flags, L2TP_API_TUNNEL_FLAG_MAX_RETRIES);
		break;
	case L2TP_TUNNEL_ARGID_RX_WINDOW_SIZE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->rx_window_size, msg->flags, L2TP_API_TUNNEL_FLAG_RX_WINDOW_SIZE);
		break;
	case L2TP_TUNNEL_ARGID_TX_WINDOW_SIZE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->tx_window_size, msg->flags, L2TP_API_TUNNEL_FLAG_TX_WINDOW_SIZE);
		break;
	case L2TP_TUNNEL_ARGID_RETRY_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->retry_timeout, msg->flags, L2TP_API_TUNNEL_FLAG_RETRY_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_IDLE_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->idle_timeout, msg->flags, L2TP_API_TUNNEL_FLAG_IDLE_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_DEST_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_addr, msg->flags, L2TP_API_TUNNEL_FLAG_PEER_ADDR);
		break;
	case L2TP_TUNNEL_ARGID_CONFIG_ID:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->config_id, msg->flags, L2TP_API_TUNNEL_FLAG_CONFIG_ID);
		break;
	case L2TP_TUNNEL_ARGID_SRC_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->our_addr, msg->flags, L2TP_API_TUNNEL_FLAG_OUR_ADDR);
		break;
	case L2TP_TUNNEL_ARGID_OUR_UDP_PORT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->our_udp_port, msg->flags, L2TP_API_TUNNEL_FLAG_OUR_UDP_PORT);
		break;
	case L2TP_TUNNEL_ARGID_PEER_UDP_PORT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_udp_port, msg->flags, L2TP_API_TUNNEL_FLAG_PEER_UDP_PORT);
		break;
	case L2TP_TUNNEL_ARGID_USE_TIEBREAKER:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_tiebreaker, msg->flags, L2TP_API_TUNNEL_FLAG_USE_TIEBREAKER);
		break;
	case L2TP_TUNNEL_ARGID_ALLOW_PPP_PROXY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->allow_ppp_proxy, msg->flags, L2TP_API_TUNNEL_FLAG_ALLOW_PPP_PROXY);
		break;
	case L2TP_TUNNEL_ARGID_FRAMING_CAP:
		if (strcasecmp(arg_value, "sync") == 0) {
			msg->framing_cap_sync = TRUE;
			msg->framing_cap_async = FALSE;
		} else if (strcasecmp(arg_value, "async") == 0) {
			msg->framing_cap_sync = FALSE;
			msg->framing_cap_async = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->framing_cap_sync = TRUE;
			msg->framing_cap_async = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->framing_cap_sync = FALSE;
			msg->framing_cap_async = FALSE;
		} else {
			fprintf(stderr, "Bad framing capabilities %s: expecting none|sync|async|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_FLAG_FRAMING_CAP;
		break;
	case L2TP_TUNNEL_ARGID_BEARER_CAP:
		if (strcasecmp(arg_value, "digital") == 0) {
			msg->bearer_cap_digital = TRUE;
			msg->bearer_cap_analog = FALSE;
		} else if (strcasecmp(arg_value, "analog") == 0) {
			msg->bearer_cap_digital = FALSE;
			msg->bearer_cap_analog = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->bearer_cap_digital = TRUE;
			msg->bearer_cap_analog = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->bearer_cap_digital = FALSE;
			msg->bearer_cap_analog = FALSE;
		} else {
			fprintf(stderr, "Bad bearer capabilities %s: expecting none|digital|analog|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_FLAG_BEARER_CAP;
		break;
	case L2TP_TUNNEL_ARGID_HOST_NAME:
		OPTSTRING(msg->host_name) = strdup(arg_value);
		if (OPTSTRING(msg->host_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->host_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_HOST_NAME;
		break;
	case L2TP_TUNNEL_ARGID_SECRET:
		OPTSTRING(msg->secret) = strdup(arg_value);
		if (OPTSTRING(msg->secret) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->secret.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_SECRET;
		break;
	case L2TP_TUNNEL_ARGID_TUNNEL_ID:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->tunnel_id, msg->flags, L2TP_API_TUNNEL_FLAG_TUNNEL_ID);
		break;
	case L2TP_TUNNEL_ARGID_TUNNEL_NAME:
		OPTSTRING(msg->tunnel_name) = strdup(arg_value);
		if (OPTSTRING(msg->tunnel_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->tunnel_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_TUNNEL_NAME;
		break;
	case L2TP_TUNNEL_ARGID_PEER_PROFILE_NAME:
		OPTSTRING(msg->peer_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->peer_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->peer_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_PEER_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_SESSION_PROFILE_NAME:
		OPTSTRING(msg->session_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->session_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->session_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_SESSION_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_PPP_PROFILE_NAME:
		OPTSTRING(msg->ppp_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->ppp_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->ppp_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_FLAG_PPP_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_INTERFACE_NAME:
		OPTSTRING(msg->interface_name) = strdup(arg_value);
		if (OPTSTRING(msg->interface_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->interface_name.valid = 1;
		msg->flags2 |= L2TP_API_TUNNEL_FLAG_INTERFACE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_SHOW_CONFIG:
	case L2TP_TUNNEL_ARGID_SHOW_TRANSPORT:
		break;
	}

	result = 0;

out:
	return result;
}

static int l2tp_act_tunnel_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_msg_data msg = {0,0, };
	L2TP_ACT_DECLARATIONS(60, l2tp_tunnel_arg_ids_t, int);

	msg.our_udp_port = 1701;
	msg.our_addr.s_addr = INADDR_ANY;
	
	L2TP_ACT_BEGIN() {
		result = l2tp_parse_tunnel_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	result = l2tp_tunnel_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created tunnel %hu\n", clnt_res & 0xffff);
	}

out:
	return result;
}

static int l2tp_act_tunnel_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	uint16_t tunnel_id = 0;
	optstring tunnel_name = { 0, };
	int flags;
	L2TP_ACT_DECLARATIONS(4, l2tp_tunnel_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TUNNEL_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], tunnel_id, flags, L2TP_API_TUNNEL_FLAG_TUNNEL_ID);
			break;
		case L2TP_TUNNEL_ARGID_TUNNEL_NAME:
			OPTSTRING(tunnel_name) = strdup(arg_values[arg]);
			if (OPTSTRING(tunnel_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			tunnel_name.valid = 1;
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if ((tunnel_id == 0) && (tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_tunnel_delete_1(tunnel_id, tunnel_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		if (tunnel_id != 0) {
			fprintf(stderr, "Deleted tunnel %hu\n", tunnel_id);
		} else {
			fprintf(stderr, "Deleted tunnel %s\n", OPTSTRING_PTR(tunnel_name));
		}
	}

out:
	return result;
}

static int l2tp_act_tunnel_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_tunnel_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_tunnel_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if ((msg.tunnel_id == 0) && (msg.tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_tunnel_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		if (msg.tunnel_id != 0) {
			fprintf(stderr, "Modified tunnel %hu\n", msg.tunnel_id);
		} else {
			fprintf(stderr, "Modified tunnel %s\n", OPTSTRING_PTR(msg.tunnel_name));
		}
	}

out:
	return result;
}

static int l2tp_act_tunnel_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	uint16_t tunnel_id = 0;
	optstring tunnel_name = { 0, };
	int flags;
	L2TP_ACT_DECLARATIONS(8, l2tp_tunnel_arg_ids_t, struct l2tp_api_tunnel_msg_data);
	int show_config_only = FALSE;
	int show_transport_only = FALSE;

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TUNNEL_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], tunnel_id, flags, L2TP_API_TUNNEL_FLAG_TUNNEL_ID);
			break;
		case L2TP_TUNNEL_ARGID_TUNNEL_NAME:
			OPTSTRING(tunnel_name) = strdup(arg_values[arg]);
			if (OPTSTRING(tunnel_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			tunnel_name.valid = 1;
			break;
		case L2TP_TUNNEL_ARGID_SHOW_CONFIG:
			show_config_only = TRUE;
			break;
		case L2TP_TUNNEL_ARGID_SHOW_TRANSPORT:
			show_transport_only = TRUE;
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if ((tunnel_id == 0) && (tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_tunnel_get_1(tunnel_id, tunnel_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	result = 0;
	if (clnt_res.result_code == 0) {
		char our_ip[16];
		char peer_ip[16];
		char idstr[32];
		char *ip;
		struct in_addr ip_addr;

		ip_addr.s_addr = clnt_res.peer_addr.s_addr;
		ip = inet_ntoa(ip_addr);
		strcpy(peer_ip, ip);
		ip_addr.s_addr = clnt_res.our_addr.s_addr;
		ip = inet_ntoa(ip_addr);
		strcpy(our_ip, ip);
		idstr[0] = '\0';
		if (clnt_res.config_id != 1) {
			sprintf(&idstr[0], ", config_id %d", clnt_res.config_id);
		}
		printf("Tunnel %hu, from %s to %s%s:-\n",
		       clnt_res.tunnel_id, our_ip, peer_ip, idstr);
		printf("  state: %s\n", OPTSTRING_PTR(clnt_res.state));
		if (!show_transport_only) {
			if (OPTSTRING_PTR(clnt_res.create_time) != NULL) {
				printf("  created at: %s", OPTSTRING(clnt_res.create_time));
			}
			if (OPTSTRING_PTR(clnt_res.tunnel_name) != NULL) {
				printf("  administrative name: '%s'\n", OPTSTRING(clnt_res.tunnel_name));
			}
			if (OPTSTRING_PTR(clnt_res.interface_name) != NULL) {
				printf("  interface name: %s\n", OPTSTRING(clnt_res.interface_name));
			}
			printf("  created by admin: %s, tunnel mode: %s%s\n", 
			       (clnt_res.created_by_admin) ? "YES" : "NO",
			       (clnt_res.mode == L2TP_API_TUNNEL_MODE_LAC) ? "LAC" : "LNS",
			       (clnt_res.created_by_admin && clnt_res.persist) ? ", persist: YES" : "");
			if (OPTSTRING_PTR(clnt_res.host_name) != NULL) {
				printf("  local host name: %s\n", OPTSTRING(clnt_res.host_name));
			}
			printf("  peer tunnel id: %d, host name: %s\n", clnt_res.peer_tunnel_id,
			       (OPTSTRING_PTR(clnt_res.peer.host_name) == NULL) ? "NOT SET" : OPTSTRING(clnt_res.peer.host_name));
			printf("  UDP ports: local %hu, peer %hu\n",
			       clnt_res.our_udp_port, clnt_res.peer_udp_port);
			printf("  authorization mode: %s%s, hide AVPs: %s, allow PPP proxy: %s\n",
			       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_NONE) ? "NONE" :
			       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_SIMPLE) ? "SIMPLE" :
			       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE) ? "CHALLENGE" : "??",
			       (clnt_res.stats.using_ipsec) ? "/IPSEC" : "",
			       (clnt_res.hide_avps) ? "ON" : "OFF",
			       (clnt_res.allow_ppp_proxy) ? "ON" : "OFF");
			if (OPTSTRING_PTR(clnt_res.secret) != NULL) {
				printf("  tunnel secret: '%s'\n", OPTSTRING(clnt_res.secret));
			}
			printf("  session limit: %d, session count: %d\n",
			       clnt_res.max_sessions, clnt_res.num_sessions);
			printf("  tunnel profile: %s, peer profile: %s\n", 
			       OPTSTRING_PTR(clnt_res.tunnel_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.tunnel_profile_name),
			       OPTSTRING_PTR(clnt_res.peer_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.peer_profile_name));
			printf("  session profile: %s, ppp profile: %s\n",
			       OPTSTRING_PTR(clnt_res.session_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.session_profile_name),
			       OPTSTRING_PTR(clnt_res.ppp_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.ppp_profile_name));
			printf("  hello timeout: %d, retry timeout: %d, idle timeout: %d\n",
			       clnt_res.hello_timeout, clnt_res.retry_timeout, clnt_res.idle_timeout);
			printf("  rx window size: %d, tx window size: %d, max retries: %d\n",
			       clnt_res.rx_window_size, clnt_res.tx_window_size, clnt_res.max_retries);
			printf("  use udp checksums: %s\n", (clnt_res.use_udp_checksums) ? "ON" : "OFF");
			printf("  do pmtu discovery: %s, mtu: %d\n", (clnt_res.do_pmtu_discovery) ? "ON" : "OFF", clnt_res.mtu);
			printf("  framing capability:%s%s%s, bearer capability:%s%s%s\n",
			       ((clnt_res.framing_cap_sync == 0) && (clnt_res.framing_cap_async == 0)) ? " NONE" : "",
			       (clnt_res.framing_cap_sync) ? " SYNC" : "",
			       (clnt_res.framing_cap_async) ? " ASYNC" : "",
			       ((clnt_res.bearer_cap_digital == 0) && (clnt_res.bearer_cap_analog == 0)) ? " NONE" : "",
			       (clnt_res.bearer_cap_digital) ? " DIGITAL" : "",
			       (clnt_res.bearer_cap_analog) ? " ANALOG" : "");
			printf("  use tiebreaker: %s\n", (clnt_res.use_tiebreaker) ? "ON" : "OFF");
			if (clnt_res.tiebreaker.tiebreaker_len == 8) {
				printf("  tiebreaker: %02x %02x %02x %02x %02x %02x %02x %02x\n",
				       clnt_res.tiebreaker.tiebreaker_val[0], clnt_res.tiebreaker.tiebreaker_val[1], 
				       clnt_res.tiebreaker.tiebreaker_val[2], clnt_res.tiebreaker.tiebreaker_val[3], 
				       clnt_res.tiebreaker.tiebreaker_val[4], clnt_res.tiebreaker.tiebreaker_val[5], 
				       clnt_res.tiebreaker.tiebreaker_val[6], clnt_res.tiebreaker.tiebreaker_val[7]);
			}
			if ((clnt_res.result_code_result != 0) || (clnt_res.result_code_error != 0)) {
				printf("  local error information:-\n");
				printf("    result code: %hu, error code: %hu\n", 
				       clnt_res.result_code_result, clnt_res.result_code_error);
				if (OPTSTRING_PTR(clnt_res.result_code_message) != NULL) {
					printf("    error message: %s\n", OPTSTRING(clnt_res.result_code_message));
				}
			}
			if ((clnt_res.peer.result_code_result != 0) || (clnt_res.peer.result_code_error != 0)) {
				printf("  last error information from peer:-\n");
				printf("    result code: %hu, error code: %hu\n", 
				       clnt_res.peer.result_code_result, clnt_res.peer.result_code_error);
				if (OPTSTRING_PTR(clnt_res.peer.result_code_message) != NULL) {
					printf("    last error message: %s\n", OPTSTRING(clnt_res.peer.result_code_message));
				}
			}
			print_trace_flags(clnt_res.trace_flags, NULL);
			if (OPTSTRING_PTR(clnt_res.peer.vendor_name) != NULL) {
				printf("  peer vendor name: %s\n", OPTSTRING(clnt_res.peer.vendor_name));
			}
			printf("  peer protocol version: %d.%d, firmware %u\n",
			       clnt_res.peer.protocol_version_ver, clnt_res.peer.protocol_version_rev,
			       clnt_res.peer.firmware_revision);
			printf("  peer framing capability:%s%s%s\n",
			       ((clnt_res.peer.framing_cap_sync == 0) && (clnt_res.peer.framing_cap_async == 0)) ? " NONE" : "",
			       (clnt_res.peer.framing_cap_sync) ? " SYNC" : "",
			       (clnt_res.peer.framing_cap_async) ? " ASYNC" : "");
			printf("  peer bearer capability:%s%s%s\n",
			       ((clnt_res.peer.bearer_cap_digital == 0) && (clnt_res.peer.bearer_cap_analog == 0)) ? " NONE" : "",
			       (clnt_res.peer.bearer_cap_digital) ? " DIGITAL" : "",
			       (clnt_res.peer.bearer_cap_analog) ? " ANALOG" : "");
			printf("  peer rx window size: %hu\n", clnt_res.peer.rx_window_size);
			if ((clnt_res.actual_tx_window_size > 0) && (clnt_res.tx_window_size != clnt_res.actual_tx_window_size)) {
				printf("  negotiated tx window size: %hu\n", clnt_res.actual_tx_window_size);
			}
			if (clnt_res.peer.tiebreaker.tiebreaker_len == 8) {
				printf("  peer tiebreaker: %02x %02x %02x %02x %02x %02x %02x %02x\n",
				       clnt_res.peer.tiebreaker.tiebreaker_val[0], clnt_res.peer.tiebreaker.tiebreaker_val[1], 
				       clnt_res.peer.tiebreaker.tiebreaker_val[2], clnt_res.peer.tiebreaker.tiebreaker_val[3], 
				       clnt_res.peer.tiebreaker.tiebreaker_val[4], clnt_res.peer.tiebreaker.tiebreaker_val[5], 
				       clnt_res.peer.tiebreaker.tiebreaker_val[6], clnt_res.peer.tiebreaker.tiebreaker_val[7]);
			}
		}
		if (!show_config_only) {
			printf("  Transport status:-\n");
			printf("    ns/nr: %hu/%hu, peer %hu/%hu\n"
			       "    cwnd: %hu, ssthresh: %hu, congpkt_acc: %hu\n",
			       clnt_res.stats.ns, clnt_res.stats.nr, clnt_res.stats.peer_nr, clnt_res.stats.peer_ns, 
			       clnt_res.stats.cwnd, clnt_res.stats.ssthresh, clnt_res.stats.congpkt_acc);
			printf("  Transport statistics:-\n");
			printf("    out-of-sequence control/data discards: %llu/%llu\n", 
			       clnt_res.stats.control_rx_oos_discards, clnt_res.stats.data_rx_oos_discards);
			printf("    zlbs tx/txfail/rx: %u/%u/%u\n", clnt_res.stats.tx_zlbs,
			       clnt_res.stats.tx_zlb_fails, clnt_res.stats.rx_zlbs);
			printf("    retransmits: %u, duplicate pkt discards: %u, data pkt discards: %u\n", 
			       clnt_res.stats.retransmits, clnt_res.stats.duplicate_pkt_discards, 
			       clnt_res.stats.data_pkt_discards);
			printf("    hellos tx/txfail/rx: %u/%u/%u\n", clnt_res.stats.tx_hellos,
			       clnt_res.stats.tx_hello_fails, clnt_res.stats.rx_hellos);
			printf("    control rx packets: %llu, rx bytes: %llu\n", clnt_res.stats.control_rx_packets, clnt_res.stats.control_rx_bytes);
			printf("    control tx packets: %llu, tx bytes: %llu\n", clnt_res.stats.control_tx_packets, clnt_res.stats.control_tx_bytes);
			if (clnt_res.stats.control_rx_oos_packets > 0) {
				printf("    control rx out-of-sequence packets: %llu\n", clnt_res.stats.control_rx_oos_packets);
			}
			printf("    data rx packets: %llu, rx bytes: %llu, rx errors: %llu\n", clnt_res.stats.data_rx_packets, clnt_res.stats.data_rx_bytes, clnt_res.stats.data_rx_errors);
			printf("    data tx packets: %llu, tx bytes: %llu, tx errors: %llu\n", clnt_res.stats.data_tx_packets, clnt_res.stats.data_tx_bytes, clnt_res.stats.data_tx_errors);
			if (clnt_res.stats.data_rx_oos_packets > 0) {
				printf("    data rx out-of-sequence packets: %llu\n", clnt_res.stats.data_rx_oos_packets);
			}
			if (clnt_res.created_by_admin) {
				printf("    establish retries: %d\n", clnt_res.num_establish_retries);
			}
		}
	} else {
		fprintf(stderr, "get tunnel failed: %s\n", l2tp_strerror(-clnt_res.result_code));
	}

out:
	return result;
}

static int l2tp_id_compare(const void *id1, const void *id2)
{
	uint16_t my_id1 = *(uint16_t *) id1;
	uint16_t my_id2 = *(uint16_t *) id2;

	return ((my_id1 > my_id2) ? 1 :
		(my_id1 < my_id2) ? -1 : 0);
}

static int l2tp_name_compare(const void *name1, const void *name2)
{
	char *my_name1 = *((char **) name1);
	char *my_name2 = *((char **) name2);

	return strcmp(my_name1, my_name2);
}

static int l2tp_act_tunnel_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_msg_data config;
	int id;
	int num_tunnels;
	struct l2tp_api_tunnel_list_msg_data clnt_res;
	int result;

  	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_tunnel_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	num_tunnels = clnt_res.tunnel_ids.tunnel_ids_len;

	if (num_tunnels > 0) {
		/* Sort the list of tunnel_ids */
		qsort(&clnt_res.tunnel_ids.tunnel_ids_val[0], num_tunnels, 
		      sizeof(clnt_res.tunnel_ids.tunnel_ids_val[0]), l2tp_id_compare);
		printf("%c %6s %16s %16s %8s %8s %16s\n", ' ', "TunId", "Peer", "Local", "PeerTId", "ConfigId", "State");
	}
	for (id = 0; id < num_tunnels; id++) {
		char peer_ip[16];
		char our_ip[16];
		char *ip;
		struct in_addr ip_addr;
		optstring tunnel_name = { 0, };

		memset(&config, 0, sizeof(config));
		result = l2tp_tunnel_get_1(clnt_res.tunnel_ids.tunnel_ids_val[id], tunnel_name, &config, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (config.result_code < 0) {
			continue;
		}
		ip_addr.s_addr = config.peer_addr.s_addr;
		ip = inet_ntoa(ip_addr);
		strcpy(&peer_ip[0], ip);
		ip_addr.s_addr = config.our_addr.s_addr;
		ip = inet_ntoa(ip_addr);
		strcpy(&our_ip[0], ip);
		printf("%c %6d %16s %16s %8d %8d %16s\n", 
		       config.created_by_admin ? ' ' : '*',
		       config.tunnel_id, peer_ip, our_ip, config.peer_tunnel_id, config.config_id, OPTSTRING(config.state));
		if (OPTSTRING(config.state) != NULL) free(OPTSTRING(config.state));
		if (OPTSTRING(config.host_name) != NULL) free(OPTSTRING(config.host_name));
		if (OPTSTRING(config.secret) != NULL) free(OPTSTRING(config.secret));
		if (OPTSTRING(config.tunnel_name) != NULL) free(OPTSTRING(config.tunnel_name));
		if (OPTSTRING(config.tunnel_profile_name) != NULL) free(OPTSTRING(config.tunnel_profile_name));
		if (config.tiebreaker.tiebreaker_val != NULL) free(config.tiebreaker.tiebreaker_val);
		if (OPTSTRING(config.result_code_message) != NULL) free(OPTSTRING(config.result_code_message));
		if (OPTSTRING(config.peer.host_name) != NULL) free(OPTSTRING(config.peer.host_name));
		if (OPTSTRING(config.peer.vendor_name) != NULL) free(OPTSTRING(config.peer.vendor_name));
		if (OPTSTRING(config.peer.result_code_message) != NULL) free(OPTSTRING(config.peer.result_code_message));
		if (config.peer.tiebreaker.tiebreaker_val != NULL) free(config.peer.tiebreaker.tiebreaker_val);
	}	

out:
	return 0;
}

/*****************************************************************************
 * Tunnel profiles
 *****************************************************************************/

static struct cli_arg_entry l2tp_args_tunnel_profile_create[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of tunnel profile")),							\
	ARG(DEST_IPADDR,	"dest_ipaddr",		0,	ipaddr,	"Destination IP address"),							\
	L2TP_TUNNEL_CREATE_ARGS,															\
	L2TP_TUNNEL_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_profile_delete[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of tunnel profile")),							\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_profile_modify[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of tunnel profile")),							\
	ARG(DEST_IPADDR,	"dest_ipaddr",		0,	ipaddr,	"Destination IP address"),							\
	L2TP_TUNNEL_CREATE_ARGS,															\
	L2TP_TUNNEL_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_tunnel_profile_show[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of tunnel profile")),							\
	{ NULL, },
};

static int l2tp_parse_tunnel_profile_arg(l2tp_tunnel_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_tunnel_profile_msg_data *msg)
{
	int result = -EINVAL;

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_TUNNEL_ARGID_PROFILE_NAME:
		msg->profile_name = strdup(arg_value);
		if (msg->profile_name == NULL) {
			result = -ENOMEM;
			goto out;
		}
		break;
	case L2TP_TUNNEL_ARGID_TRACE_FLAGS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->trace_flags, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_TRACE_FLAGS);
		break;
	case L2TP_TUNNEL_ARGID_AUTH_MODE:
		if (strcasecmp(arg_value, "none") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_NONE;
		} else if (strcasecmp(arg_value, "simple") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_SIMPLE;
		} else if (strcasecmp(arg_value, "challenge") == 0) {
			msg->auth_mode = L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE;
		} else {
			fprintf(stderr, "Bad authmode %s: expecting none|simple|challenge\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_AUTH_MODE;
		break;
	case L2TP_TUNNEL_ARGID_MAX_SESSIONS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_sessions, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_MAX_SESSIONS);
		break;
	case L2TP_TUNNEL_ARGID_HIDE_AVPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->hide_avps, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_HIDE_AVPS);
		break;
	case L2TP_TUNNEL_ARGID_UDP_CSUMS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_udp_checksums, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_USE_UDP_CHECKSUMS);
		break;
	case L2TP_TUNNEL_ARGID_DO_PMTU_DISCOVERY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->do_pmtu_discovery, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_DO_PMTU_DISCOVERY);
		break;
	case L2TP_TUNNEL_ARGID_MTU:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->mtu, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_MTU);
		break;
	case L2TP_TUNNEL_ARGID_HELLO_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->hello_timeout, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_HELLO_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_MAX_RETRIES:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_retries, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_MAX_RETRIES);
		break;
	case L2TP_TUNNEL_ARGID_RX_WINDOW_SIZE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->rx_window_size, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_RX_WINDOW_SIZE);
		break;
	case L2TP_TUNNEL_ARGID_TX_WINDOW_SIZE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->tx_window_size, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_TX_WINDOW_SIZE);
		break;
	case L2TP_TUNNEL_ARGID_RETRY_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->retry_timeout, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_RETRY_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_IDLE_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->idle_timeout, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_IDLE_TIMEOUT);
		break;
	case L2TP_TUNNEL_ARGID_DEST_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_addr, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_PEER_ADDR);
		break;
	case L2TP_TUNNEL_ARGID_SRC_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->our_addr, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_OUR_ADDR);
		break;
	case L2TP_TUNNEL_ARGID_OUR_UDP_PORT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->our_udp_port, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_OUR_UDP_PORT);
		break;
	case L2TP_TUNNEL_ARGID_PEER_UDP_PORT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_udp_port, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_PEER_UDP_PORT);
		break;
	case L2TP_TUNNEL_ARGID_USE_TIEBREAKER:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_tiebreaker, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_USE_TIEBREAKER);
		break;
	case L2TP_TUNNEL_ARGID_ALLOW_PPP_PROXY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->allow_ppp_proxy, msg->flags, L2TP_API_TUNNEL_PROFILE_FLAG_ALLOW_PPP_PROXY);
		break;
	case L2TP_TUNNEL_ARGID_FRAMING_CAP:
		if (strcasecmp(arg_value, "sync") == 0) {
			msg->framing_cap_sync = TRUE;
			msg->framing_cap_async = FALSE;
		} else if (strcasecmp(arg_value, "async") == 0) {
			msg->framing_cap_sync = FALSE;
			msg->framing_cap_async = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->framing_cap_sync = TRUE;
			msg->framing_cap_async = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->framing_cap_sync = FALSE;
			msg->framing_cap_async = FALSE;
		} else {
			fprintf(stderr, "Bad framing capabilities %s: expecting none|sync|async|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_FRAMING_CAP;
		break;
	case L2TP_TUNNEL_ARGID_BEARER_CAP:
		if (strcasecmp(arg_value, "digital") == 0) {
			msg->bearer_cap_digital = TRUE;
			msg->bearer_cap_analog = FALSE;
		} else if (strcasecmp(arg_value, "analog") == 0) {
			msg->bearer_cap_digital = FALSE;
			msg->bearer_cap_analog = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->bearer_cap_digital = TRUE;
			msg->bearer_cap_analog = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->bearer_cap_digital = FALSE;
			msg->bearer_cap_analog = FALSE;
		} else {
			fprintf(stderr, "Bad bearer capabilities %s: expecting none|digital|analog|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_BEARER_CAP;
		break;
	case L2TP_TUNNEL_ARGID_HOST_NAME:
		OPTSTRING(msg->host_name) = strdup(arg_value);
		if (OPTSTRING(msg->host_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->host_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_HOST_NAME;
		break;
	case L2TP_TUNNEL_ARGID_SECRET:
		OPTSTRING(msg->secret) = strdup(arg_value);
		if (OPTSTRING(msg->secret) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->secret.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_SECRET;
		break;
	case L2TP_TUNNEL_ARGID_PEER_PROFILE_NAME:
		OPTSTRING(msg->peer_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->peer_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->peer_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_PEER_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_SESSION_PROFILE_NAME:
		OPTSTRING(msg->session_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->session_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->session_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_SESSION_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_PPP_PROFILE_NAME:
		OPTSTRING(msg->ppp_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->ppp_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->ppp_profile_name.valid = 1;
		msg->flags |= L2TP_API_TUNNEL_PROFILE_FLAG_PPP_PROFILE_NAME;
		break;
	case L2TP_TUNNEL_ARGID_CONFIG_ID:
	case L2TP_TUNNEL_ARGID_TUNNEL_ID:
	case L2TP_TUNNEL_ARGID_TUNNEL_NAME:
	case L2TP_TUNNEL_ARGID_INTERFACE_NAME:
	case L2TP_TUNNEL_ARGID_SHOW_CONFIG:
	case L2TP_TUNNEL_ARGID_SHOW_TRANSPORT:
	case L2TP_TUNNEL_ARGID_PERSIST:
		/* not valid for tunnel profiles */
		result = -EINVAL;
		goto out;
	}

	result = 0;

out:
	return result;
}

static int l2tp_act_tunnel_profile_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_tunnel_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_tunnel_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_tunnel_profile_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created tunnel profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_tunnel_profile_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_tunnel_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TUNNEL_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_tunnel_profile_delete_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Deleted tunnel profile %s\n", profile_name);
	}

out:
	return result;
}

static int l2tp_act_tunnel_profile_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_tunnel_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_tunnel_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_tunnel_profile_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified tunnel profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_tunnel_profile_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	char str[16];
	L2TP_ACT_DECLARATIONS(4, l2tp_tunnel_arg_ids_t, struct l2tp_api_tunnel_profile_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TUNNEL_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_tunnel_profile_get_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	printf("Tunnel profile %s\n", clnt_res.profile_name);
	if (OPTSTRING_PTR(clnt_res.host_name) != NULL) {
		printf("  l2tp host name: %s\n", OPTSTRING(clnt_res.host_name));
	}
	if (clnt_res.our_addr.s_addr != 0) {
		struct in_addr ip;
		ip.s_addr = clnt_res.our_addr.s_addr;
		strcpy(&str[0], inet_ntoa(ip));
		printf("  local IP address: %s\n", str);
	}
	if (clnt_res.our_udp_port != 0) {
		printf("  local UDP port: %hu\n", clnt_res.our_udp_port);
	}
	if (clnt_res.peer_addr.s_addr != 0) {
		struct in_addr ip;
		ip.s_addr = clnt_res.peer_addr.s_addr;
		strcpy(&str[0], inet_ntoa(ip));
		printf("  peer IP address: %s\n", str);
	}
	if (clnt_res.peer_udp_port != 0) {
		printf("  peer UDP port: %hu\n", clnt_res.peer_udp_port);
	}
	printf("  authorization mode %s, hide AVPs %s, allow PPP proxy %s\n",
	       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_NONE) ? "NONE" :
	       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_SIMPLE) ? "SIMPLE" :
	       (clnt_res.auth_mode == L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE) ? "CHALLENGE" : "??",
	       (clnt_res.hide_avps) ? "ON" : "OFF",
	       (clnt_res.allow_ppp_proxy) ? "ON" : "OFF");
	if (OPTSTRING(clnt_res.secret) != NULL) {
		printf("  tunnel secret: '%s'\n", OPTSTRING(clnt_res.secret));
	}
	printf("  hello timeout %d, retry timeout %d, idle timeout %d\n",
	       clnt_res.hello_timeout, clnt_res.retry_timeout, clnt_res.idle_timeout);
	printf("  rx window size %d, tx window size %d, max retries %d\n",
	       clnt_res.rx_window_size, clnt_res.tx_window_size, clnt_res.max_retries);
	printf("  use UDP checksums: %s\n", (clnt_res.use_udp_checksums) ? "ON" : "OFF");
	printf("  do pmtu discovery: %s, mtu: %d\n", (clnt_res.do_pmtu_discovery) ? "ON" : "OFF", clnt_res.mtu);
	printf("  framing capability: %s%s%s\n",
	       ((clnt_res.framing_cap_sync == 0) && (clnt_res.framing_cap_async == 0)) ? "NONE " : "",
	       (clnt_res.framing_cap_sync) ? "SYNC " : "",
	       (clnt_res.framing_cap_async) ? "ASYNC " : "");
	printf("  bearer capability: %s%s%s\n",
	       ((clnt_res.bearer_cap_digital == 0) && (clnt_res.bearer_cap_analog == 0)) ? "NONE " : "",
	       (clnt_res.bearer_cap_digital) ? "DIGITAL " : "",
	       (clnt_res.bearer_cap_analog) ? "ANALOG " : "");
	printf("  use tiebreaker: %s\n", (clnt_res.use_tiebreaker) ? "ON" : "OFF");
	if (clnt_res.max_sessions != 0) {
		printf("  max sessions: %d\n", clnt_res.max_sessions);
	}
	printf("  peer profile: %s\n", OPTSTRING_PTR(clnt_res.peer_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.peer_profile_name));
	printf("  session profile: %s\n", OPTSTRING_PTR(clnt_res.session_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.session_profile_name));
	printf("  ppp profile: %s\n", OPTSTRING_PTR(clnt_res.ppp_profile_name) == NULL ? "NOT SET" : OPTSTRING(clnt_res.ppp_profile_name));
	print_trace_flags(clnt_res.trace_flags, NULL);
	printf("  use count: %d\n", clnt_res.use_count);
	printf("\n");

out:
	return result;
}

static int l2tp_act_tunnel_profile_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_tunnel_profile_list_msg_data clnt_res;
	struct l2tp_api_tunnel_profile_list_entry *walk;
	int result;
	const char **profile_names;
	int index;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_tunnel_profile_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.num_profiles > 0) {
		profile_names = calloc(clnt_res.num_profiles, sizeof(profile_names[0]));
		if (profile_names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(ENOMEM));
			goto out;
		}
	
		walk = clnt_res.profiles;
		for (index = 0; index < clnt_res.num_profiles; index++) {
			if ((walk == NULL) || (walk->profile_name[0] == '\0')) {
				break;
			}
			profile_names[index] = walk->profile_name;
			walk = walk->next;
		}	

		/* Sort the profile names */
		qsort(&profile_names[0], index, sizeof(profile_names[0]), l2tp_name_compare);

		for (index = 0; index < clnt_res.num_profiles; index++) {
			printf("\t%s\n", profile_names[index]);
		}

		free(profile_names);
	}

	result = 0;

out:
	return result;
}

/*****************************************************************************
 * Sessions
 *****************************************************************************/

typedef enum {
	L2TP_SESSION_ARGID_TUNNEL_NAME,
	L2TP_SESSION_ARGID_TUNNEL_ID,
	L2TP_SESSION_ARGID_SESSION_ID,
	L2TP_SESSION_ARGID_TRACE_FLAGS,
	L2TP_SESSION_ARGID_PROFILE_NAME,
	L2TP_SESSION_ARGID_PPP_PROFILE_NAME,
	L2TP_SESSION_ARGID_SEQUENCING_REQUIRED,
	L2TP_SESSION_ARGID_USE_SEQUENCE_NUMBERS,
	L2TP_SESSION_ARGID_REORDER_TIMEOUT,
	L2TP_SESSION_ARGID_SESSION_TYPE,
	L2TP_SESSION_ARGID_PRIV_GROUP_ID,
	L2TP_SESSION_ARGID_SESSION_NAME,
	L2TP_SESSION_ARGID_INTERFACE_NAME,
	L2TP_SESSION_ARGID_USER_NAME,
	L2TP_SESSION_ARGID_USER_PASSWORD,
	L2TP_SESSION_ARGID_FRAMING_TYPE,
	L2TP_SESSION_ARGID_BEARER_TYPE,
	L2TP_SESSION_ARGID_MINIMUM_BPS,
	L2TP_SESSION_ARGID_MAXIMUM_BPS,
	L2TP_SESSION_ARGID_CONNECT_SPEED,
	L2TP_SESSION_ARGID_USE_PPP_PROXY,
	L2TP_SESSION_ARGID_PROXY_AUTH_TYPE,
	L2TP_SESSION_ARGID_PROXY_AUTH_NAME,
	L2TP_SESSION_ARGID_PROXY_AUTH_CHALLENGE,
	L2TP_SESSION_ARGID_PROXY_AUTH_RESPONSE,
	L2TP_SESSION_ARGID_CALLING_NUMBER,
	L2TP_SESSION_ARGID_CALLED_NUMBER,
	L2TP_SESSION_ARGID_SUB_ADDRESS,
	L2TP_SESSION_ARGID_INITIAL_RCVD_LCP_CONFREQ,
	L2TP_SESSION_ARGID_LAST_SENT_LCP_CONFREQ,
	L2TP_SESSION_ARGID_LAST_RCVD_LCP_CONFREQ,
} l2tp_session_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_SESSION_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_SESSION_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

/* Paremeters for Create and Modify operations */
#define L2TP_SESSION_MODIFY_ARGS	\
	ARG(TRACE_FLAGS, 		"trace_flags", 		0, 	uint32,	"Trace flags, for debugging network problems"),				\
	ARG(SEQUENCING_REQUIRED,	"sequencing_required",	0, 	bool, 	"The use of sequence numbers in the data channel is mandatory."),	\
	ARG(USE_SEQUENCE_NUMBERS,	"use_sequence_numbers",	0, 	bool, 	"Enable sequence numbers in the data channel if peer supports them."),	\
	ARG(REORDER_TIMEOUT,		"reorder_timeout",	0, 	uint32, "Timeout to wait for out-of-sequence packets before discarding.")	\


#define L2TP_SESSION_ID_ARGS 																\
	ARG(TUNNEL_ID,			"tunnel_id",		0,	uint16,	"Tunnel ID in which session exists."),					\
	ARG(TUNNEL_NAME,		"tunnel_name",		0,	string,	"Administrative name of tunnel in which session exists."),		\
	ARG(SESSION_ID,			"session_id",		0,	uint16,	"Session ID of session."),						\
	ARG(SESSION_NAME,			"session_name",		0,	string,	"Administrative name of session")					\

static struct cli_arg_entry l2tp_args_session_create[] = {
	ARG(TUNNEL_ID,			"tunnel_id",		0,	uint16,	"Tunnel ID in which to create session."),
	ARG(TUNNEL_NAME,		"tunnel_name",		0,	string,	"Administrative name of tunnel in which session to create session."),	\
	ARG(SESSION_NAME,		"session_name",		0,	string,	"Administrative name of session"),
#ifdef L2TP_TEST
	ARG(SESSION_ID,			"session_id",		0,	uint16,	"Session ID of session, usually auto-generated. For testing only."),
#endif
	ARG(PROFILE_NAME,		"profile_name",		0,	string,	("Name of session profile")), 
	ARG(PPP_PROFILE_NAME,		"ppp_profile_name",	0,	string,	("Name of ppp profile to use for PPP parameters")),
	L2TP_SESSION_MODIFY_ARGS,
	ARG(SESSION_TYPE,		"session_type",		0,	string,	"Session type: LAC/LNS incoming/outgoing"),
	ARG(PRIV_GROUP_ID,		"priv_group_id",	0,	string,	"Private group ID, used to separate this session into a named administrative group"),
	ARG(INTERFACE_NAME,		"interface_name",	0,	string,	"PPP interface name.Default: pppN"),
	ARG(USER_NAME,			"user_name",		0,	string,	"PPP user name"),
	ARG(USER_PASSWORD,		"user_password",	0,	string,	"PPP user password"),
	ARG(FRAMING_TYPE,		"framing_type",		0,	string,	"Framing type: sync, async or any. Default: any (derive from tunnel)"),
	ARG(BEARER_TYPE,		"bearer_type",		0,	string,	"Bearer type: none, digital, analog, any. Default: any (derive from tunnel)"),
	ARG(MINIMUM_BPS,		"minimum_bps",		0,	uint32,	"Minimum bits/sec acceptable. Default: 0"),
	ARG(MAXIMUM_BPS,		"maximum_bps",		0,	uint32,	"Maximum bits/sec required. Default: no limit"),
	ARG(CONNECT_SPEED,		"connect_speed",	0,	string,	"Specified as speed[:txspeed], indicates connection speeds."),
#ifdef L2TP_TEST
	ARG(USE_PPP_PROXY,		"use_ppp_proxy",	0,	bool,	""),
	ARG(PROXY_AUTH_TYPE,		"proxy_auth_type",	0,	int32,	""),
	ARG(PROXY_AUTH_NAME,		"proxy_auth_name",	0,	string,	""),
	ARG(PROXY_AUTH_CHALLENGE,	"proxy_auth_challenge",	0,	hex,	""),
	ARG(PROXY_AUTH_RESPONSE,	"proxy_auth_response",	0,	hex,	""),
	ARG(CALLING_NUMBER,		"calling_number",	0,	string,	""),
	ARG(CALLED_NUMBER,		"called_number",	0,	string,	""),
	ARG(SUB_ADDRESS,		"sub_address",		0,	string,	""),
	ARG(INITIAL_RCVD_LCP_CONFREQ,	"initial_rcvd_lcp_confreq", 0, hex,	""),
	ARG(LAST_SENT_LCP_CONFREQ,	"last_sent_lcp_confreq", 0,	hex,	""),
	ARG(LAST_RCVD_LCP_CONFREQ,	"last_rcvd_lcp_confreq", 0,	hex,	""),
#endif /* L2TP_TEST */
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_delete[] = {
	L2TP_SESSION_ID_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_modify[] = {
	L2TP_SESSION_ID_ARGS,
	L2TP_SESSION_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_show[] = {
	L2TP_SESSION_ID_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_list[] = {
	ARG(TUNNEL_ID,			"tunnel_id",		0,	uint16,	"Tunnel ID in which to list sessions."),				\
	ARG(TUNNEL_NAME,		"tunnel_name",		0,	string,	"Administrative name of tunnel to list."),				\
	{ NULL, },
};

static int l2tp_parse_session_arg(l2tp_session_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_session_msg_data *msg)
{
	int result = -EINVAL;
	int ints[2];
	int num_matches;

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_SESSION_ARGID_TUNNEL_NAME:
		OPTSTRING(msg->tunnel_name) = strdup(arg_value);
		if (OPTSTRING(msg->tunnel_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->tunnel_name.valid = 1;
		break;
	case L2TP_SESSION_ARGID_TUNNEL_ID:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->tunnel_id, msg->flags, 0);
		break;
	case L2TP_SESSION_ARGID_SESSION_ID:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->session_id, msg->flags, 0);
		break;
	case L2TP_SESSION_ARGID_TRACE_FLAGS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->trace_flags, msg->flags, L2TP_API_SESSION_FLAG_TRACE_FLAGS);
		break;
	case L2TP_SESSION_ARGID_PROFILE_NAME:
		OPTSTRING(msg->profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->profile_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_PROFILE_NAME;
		break;
	case L2TP_SESSION_ARGID_PPP_PROFILE_NAME:
		OPTSTRING(msg->ppp_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->ppp_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->ppp_profile_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_PPP_PROFILE_NAME;
		break;
	case L2TP_SESSION_ARGID_SEQUENCING_REQUIRED:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->sequencing_required, msg->flags, L2TP_API_SESSION_FLAG_SEQUENCING_REQUIRED);
		break;
	case L2TP_SESSION_ARGID_USE_SEQUENCE_NUMBERS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_sequence_numbers, msg->flags, L2TP_API_SESSION_FLAG_USE_SEQUENCE_NUMBERS);
		break;
	case L2TP_SESSION_ARGID_REORDER_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->reorder_timeout, msg->flags, L2TP_API_SESSION_FLAG_REORDER_TIMEOUT);
		break;
	case L2TP_SESSION_ARGID_SESSION_TYPE:
		if (strcasecmp(arg_value, "laic") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LAIC;
		} else if (strcasecmp(arg_value, "laoc") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LAOC;
		} else if (strcasecmp(arg_value, "lnic") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LNIC;
		} else if (strcasecmp(arg_value, "lnoc") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LNOC;
		} else {
			fprintf(stderr, "Bad session type %s: expecting laic|laoc|lnic|lnoc\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_FLAG_SESSION_TYPE;
		break;
	case L2TP_SESSION_ARGID_PRIV_GROUP_ID:
		OPTSTRING(msg->priv_group_id) = strdup(arg_value);
		if (OPTSTRING(msg->priv_group_id) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->priv_group_id.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_PRIV_GROUP_ID;
		break;
	case L2TP_SESSION_ARGID_SESSION_NAME:
		OPTSTRING(msg->session_name) = strdup(arg_value);
		if (OPTSTRING(msg->session_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->session_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_SESSION_NAME;
		break;
	case L2TP_SESSION_ARGID_INTERFACE_NAME:
		OPTSTRING(msg->interface_name) = strdup(arg_value);
		if (OPTSTRING(msg->interface_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->interface_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_INTERFACE_NAME;
		break;
	case L2TP_SESSION_ARGID_USER_NAME:
		OPTSTRING(msg->user_name) = strdup(arg_value);
		if (OPTSTRING(msg->user_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->user_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_USER_NAME;
		break;
	case L2TP_SESSION_ARGID_USER_PASSWORD:
		OPTSTRING(msg->user_password) = strdup(arg_value);
		if (OPTSTRING(msg->user_password) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->user_password.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_USER_PASSWORD;
		break;
	case L2TP_SESSION_ARGID_FRAMING_TYPE:
		if (strcasecmp(arg_value, "sync") == 0) {
			msg->framing_type_sync = TRUE;
			msg->framing_type_async = FALSE;
		} else if (strcasecmp(arg_value, "async") == 0) {
			msg->framing_type_sync = FALSE;
			msg->framing_type_async = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->framing_type_sync = TRUE;
			msg->framing_type_async = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->framing_type_sync = FALSE;
			msg->framing_type_async = FALSE;
		} else {
			fprintf(stderr, "Bad framing type %s: expecting none|sync|async|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_FLAG_FRAMING_TYPE;
		break;
	case L2TP_SESSION_ARGID_BEARER_TYPE:
		if (strcasecmp(arg_value, "digital") == 0) {
			msg->bearer_type_digital = TRUE;
			msg->bearer_type_analog = FALSE;
		} else if (strcasecmp(arg_value, "analog") == 0) {
			msg->bearer_type_digital = FALSE;
			msg->bearer_type_analog = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->bearer_type_digital = TRUE;
			msg->bearer_type_analog = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->bearer_type_digital = FALSE;
			msg->bearer_type_analog = FALSE;
		} else {
			fprintf(stderr, "Bad bearer type %s: expecting none|digital|analog|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_FLAG_BEARER_TYPE;
		break;
	case L2TP_SESSION_ARGID_MINIMUM_BPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->minimum_bps, msg->flags, L2TP_API_SESSION_FLAG_MINIMUM_BPS);
		break;
	case L2TP_SESSION_ARGID_MAXIMUM_BPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->maximum_bps, msg->flags, L2TP_API_SESSION_FLAG_MAXIMUM_BPS);
		break;
	case L2TP_SESSION_ARGID_CONNECT_SPEED:
		num_matches = sscanf(arg_value, "%d:%d", &ints[0], &ints[1]);
		if (num_matches >= 1) {
			msg->rx_connect_speed = ints[0];
			msg->tx_connect_speed = ints[0];
			if (num_matches == 2) {
				msg->tx_connect_speed = ints[1];
			}
			msg->flags |= L2TP_API_SESSION_FLAG_CONNECT_SPEED;
		} else {
			fprintf(stderr, "Expecting connect_speed[:tx_connect_speed]\n");
			goto out;
		}
		break;
#ifdef L2TP_TEST
		/* It is useful to fake these parameters using the CLI for testing.
		 * These parameters would only be used by an automated PPP call
		 * application, such as a BRAS. 
		 */ 
	case L2TP_SESSION_ARGID_USE_PPP_PROXY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_ppp_proxy, msg->flags, L2TP_API_SESSION_FLAG_USE_PPP_PROXY);
		break;
	case L2TP_SESSION_ARGID_PROXY_AUTH_TYPE:
		if (strcasecmp(arg_value, "text") == 0) {
			msg->proxy_auth_type = L2TP_API_SESSION_PROXY_AUTH_TYPE_PLAIN_TEXT;
		} else if (strcasecmp(arg_value, "chap") == 0) {
			msg->proxy_auth_type = L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_CHAP;
		} else if (strcasecmp(arg_value, "pap") == 0) {
			msg->proxy_auth_type = L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_PAP;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->proxy_auth_type = L2TP_API_SESSION_PROXY_AUTH_TYPE_NO_AUTH;
		} else if (strcasecmp(arg_value, "mschap") == 0) {
			msg->proxy_auth_type = L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_MSCHAPV1;
		} else {
			fprintf(stderr, "Bad auth type %s: expecting none|text|chap|pap|mschap\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_FLAG_PROXY_AUTH_TYPE;
		break;
	case L2TP_SESSION_ARGID_PROXY_AUTH_NAME:
		OPTSTRING(msg->proxy_auth_name) = strdup(arg_value);
		if (OPTSTRING(msg->proxy_auth_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->proxy_auth_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_PROXY_AUTH_NAME;
		break;
	case L2TP_SESSION_ARGID_PROXY_AUTH_CHALLENGE:
		msg->proxy_auth_challenge.proxy_auth_challenge_len = strlen(arg_value) / 2;
		msg->proxy_auth_challenge.proxy_auth_challenge_val = malloc(msg->proxy_auth_challenge.proxy_auth_challenge_len + 2 /* slack */);
		if (msg->proxy_auth_challenge.proxy_auth_challenge_val == NULL) {
			result = -ENOMEM;
			goto out;
		}
		result = cli_arg_parse_hex(arg, arg_value, msg->proxy_auth_challenge.proxy_auth_challenge_val);
		if (result < 0) {
			goto out;
		}
		msg->flags |= L2TP_API_SESSION_FLAG_PROXY_AUTH_CHALLENGE;
		break;
	case L2TP_SESSION_ARGID_PROXY_AUTH_RESPONSE:
		msg->proxy_auth_response.proxy_auth_response_len = strlen(arg_value) / 2;
		msg->proxy_auth_response.proxy_auth_response_val = malloc(msg->proxy_auth_response.proxy_auth_response_len + 2 /* slack */);
		if (msg->proxy_auth_response.proxy_auth_response_val == NULL) {
			result = -ENOMEM;
			goto out;
		}
		result = cli_arg_parse_hex(arg, arg_value, msg->proxy_auth_response.proxy_auth_response_val);
		if (result < 0) {
			goto out;
		}
		msg->flags |= L2TP_API_SESSION_FLAG_PROXY_AUTH_RESPONSE;
		break;
	case L2TP_SESSION_ARGID_CALLING_NUMBER:
		OPTSTRING(msg->calling_number) = strdup(arg_value);
		if (OPTSTRING(msg->calling_number) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->calling_number.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_CALLING_NUMBER;
		break;
	case L2TP_SESSION_ARGID_CALLED_NUMBER:
		OPTSTRING(msg->called_number) = strdup(arg_value);
		if (OPTSTRING(msg->called_number) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->called_number.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_CALLED_NUMBER;
		break;
	case L2TP_SESSION_ARGID_SUB_ADDRESS:
		OPTSTRING(msg->sub_address) = strdup(arg_value);
		if (OPTSTRING(msg->sub_address) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->sub_address.valid = 1;
		msg->flags |= L2TP_API_SESSION_FLAG_SUB_ADDRESS;
		break;
	case L2TP_SESSION_ARGID_INITIAL_RCVD_LCP_CONFREQ:
		msg->initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_len = strlen(arg_value) / 2;
		msg->initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_val = malloc(msg->initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_len + 2 /* slack */);
		if (msg->initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_val == NULL) {
			result = -ENOMEM;
			goto out;
		}
		result = cli_arg_parse_hex(arg, arg_value, msg->initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_val);	
		if (result < 0) {
			goto out;
		}
		msg->flags |= L2TP_API_SESSION_FLAG_INITIAL_RCVD_LCP_CONFREQ;
		break;
	case L2TP_SESSION_ARGID_LAST_SENT_LCP_CONFREQ:
		msg->last_sent_lcp_confreq.last_sent_lcp_confreq_len = strlen(arg_value) / 2;
		msg->last_sent_lcp_confreq.last_sent_lcp_confreq_val = malloc(msg->last_sent_lcp_confreq.last_sent_lcp_confreq_len + 2 /* slack */);
		if (msg->last_sent_lcp_confreq.last_sent_lcp_confreq_val == NULL) {
			result = -ENOMEM;
			goto out;
		}
		result = cli_arg_parse_hex(arg, arg_value, msg->last_sent_lcp_confreq.last_sent_lcp_confreq_val);
		if (result < 0) {
			goto out;
		}
		msg->flags |= L2TP_API_SESSION_FLAG_LAST_SENT_LCP_CONFREQ;
		break;
	case L2TP_SESSION_ARGID_LAST_RCVD_LCP_CONFREQ:
		msg->last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_len = strlen(arg_value) / 2;
		msg->last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_val = malloc(msg->last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_len + 2 /* slack */);
		if (msg->last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_val == NULL) {
			result = -ENOMEM;
			goto out;
		}
		result = cli_arg_parse_hex(arg, arg_value, msg->last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_val);
		if (result < 0) {
			goto out;
		}
		msg->flags |= L2TP_API_SESSION_FLAG_LAST_RCVD_LCP_CONFREQ;
		break;
#else
	case L2TP_SESSION_ARGID_USE_PPP_PROXY:
	case L2TP_SESSION_ARGID_PROXY_AUTH_TYPE:
	case L2TP_SESSION_ARGID_PROXY_AUTH_NAME:
	case L2TP_SESSION_ARGID_PROXY_AUTH_CHALLENGE:
	case L2TP_SESSION_ARGID_PROXY_AUTH_RESPONSE:
	case L2TP_SESSION_ARGID_CALLING_NUMBER:
	case L2TP_SESSION_ARGID_CALLED_NUMBER:
	case L2TP_SESSION_ARGID_SUB_ADDRESS:
	case L2TP_SESSION_ARGID_INITIAL_RCVD_LCP_CONFREQ:
	case L2TP_SESSION_ARGID_LAST_SENT_LCP_CONFREQ:
	case L2TP_SESSION_ARGID_LAST_RCVD_LCP_CONFREQ:
		result = -EOPNOTSUPP;
		goto out;
#endif /* L2TP_TEST */
	}

	result = 0;

out:
	return result;
}

static int l2tp_act_session_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_session_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(80, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_session_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if ((msg.tunnel_id == 0) && (!msg.tunnel_name.valid)) {
		fprintf(stderr, "Required tunnel_id / tunnel_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		if (msg.tunnel_id != 0) {
			fprintf(stderr, "Created session %hu/%hu\n", msg.tunnel_id, clnt_res & 0xffff);
		} else {
			fprintf(stderr, "Created session %hu on tunnel %s\n", clnt_res & 0xffff, OPTSTRING_PTR(msg.tunnel_name));
		}
	}

out:
	return result;
}

static int l2tp_act_session_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	u_short tunnel_id = 0;
	u_short session_id = 0;
	optstring tunnel_name = { 0, };
	optstring session_name = { 0, };
	int flags;
	L2TP_ACT_DECLARATIONS(6, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SESSION_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], tunnel_id, flags, 0);
			break;
		case L2TP_SESSION_ARGID_TUNNEL_NAME:
			OPTSTRING(tunnel_name) = strdup(arg_values[arg]);
			if (OPTSTRING(tunnel_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			tunnel_name.valid = 1;
			break;
		case L2TP_SESSION_ARGID_SESSION_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], session_id, flags, 0);
			break;
		case L2TP_SESSION_ARGID_SESSION_NAME:
			OPTSTRING(session_name) = strdup(arg_values[arg]);
			if (OPTSTRING(session_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			session_name.valid = 1;
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if ((tunnel_id == 0) && (tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}
	if ((session_id == 0) && (session_name.valid == 0)) {
		fprintf(stderr, "Required session_id or session_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_delete_1(tunnel_id, tunnel_name, session_id, session_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		char tid[6];
		char sid[6];
		sprintf(&tid[0], "%hu", tunnel_id);
		sprintf(&sid[0], "%hu", session_id);
		fprintf(stderr, "Deleted session %s/%s\n", 
			tunnel_id == 0 ? OPTSTRING_PTR(tunnel_name) : tid,
			session_id == 0 ? OPTSTRING_PTR(session_name) : sid);
	}
out:
	return result;
}

static int l2tp_act_session_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_session_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(80, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_session_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if ((msg.tunnel_id == 0) && (msg.tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}
	if ((msg.session_id == 0) && (msg.session_name.valid == 0)) {
		fprintf(stderr, "Required session_id or session_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		char tid[6];
		char sid[6];
		sprintf(&tid[0], "%hu", msg.tunnel_id);
		sprintf(&sid[0], "%hu", msg.session_id);
		fprintf(stderr, "Modified session %s/%s\n", 
			msg.tunnel_id == 0 ? OPTSTRING_PTR(msg.tunnel_name) : tid,
			msg.session_id == 0 ? OPTSTRING_PTR(msg.session_name) : sid);
	}

out:
	return result;
}

static int l2tp_act_session_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	u_short tunnel_id = 0;
	optstring tunnel_name = { 0, };
	u_short session_id = 0;
	optstring session_name = { 0, };
	int flags;
	L2TP_ACT_DECLARATIONS(6, l2tp_session_arg_ids_t, struct l2tp_api_session_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SESSION_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], tunnel_id, flags, 0);
			break;
		case L2TP_SESSION_ARGID_TUNNEL_NAME:
			OPTSTRING(tunnel_name) = strdup(arg_values[arg]);
			if (OPTSTRING(tunnel_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			tunnel_name.valid = 1;
			break;
		case L2TP_SESSION_ARGID_SESSION_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], session_id, flags, 0);
			break;
		case L2TP_SESSION_ARGID_SESSION_NAME:
			OPTSTRING(session_name) = strdup(arg_values[arg]);
			if (OPTSTRING(session_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			session_name.valid = 1;
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if ((tunnel_id == 0) && (tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}
	if ((session_id == 0) && (session_name.valid == 0)) {
		fprintf(stderr, "Required session_id or session_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_session_get_1(tunnel_id, tunnel_name, session_id, session_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	printf("Session %hd on tunnel %hd:-\n", clnt_res.session_id, clnt_res.tunnel_id);
	printf("  type: %s, state: %s\n", 
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_LAIC ? "LAC Incoming Call" :
		clnt_res.session_type == L2TP_API_SESSION_TYPE_LAOC ? "LAC Outgoing Call" :
		clnt_res.session_type == L2TP_API_SESSION_TYPE_LNIC ? "LNS Incoming Call" :
		clnt_res.session_type == L2TP_API_SESSION_TYPE_LNOC ? "LNS Outgoing Call" : "??"),
	       OPTSTRING_PTR(clnt_res.state));
	if (OPTSTRING_PTR(clnt_res.create_time) != NULL) {
		printf("  created at: %s", OPTSTRING(clnt_res.create_time));
	}
	if (OPTSTRING_PTR(clnt_res.session_name) != NULL) {
		printf("  administrative name: %s\n", OPTSTRING(clnt_res.session_name));
	}
	printf("  created by admin: %s", clnt_res.created_by_admin ? "YES" : "NO");
	if (clnt_res.peer_session_id != 0) {
		printf(", peer session id: %hd\n", clnt_res.peer_session_id);
	} else {
		printf("\n");
	}
	if (OPTSTRING_PTR(clnt_res.priv_group_id) != NULL) {
		printf("  private group id: %s\n", OPTSTRING(clnt_res.priv_group_id));
	}
	if (OPTSTRING_PTR(clnt_res.user_name) != NULL) {
		printf("  ppp user name: %s\n", OPTSTRING(clnt_res.user_name));
	}
	if (OPTSTRING_PTR(clnt_res.user_password) != NULL) {
		printf("  ppp user password: %s\n", OPTSTRING(clnt_res.user_password));
	}
	if (OPTSTRING_PTR(clnt_res.interface_name) != NULL) {
		printf("  ppp interface name: %s\n", OPTSTRING(clnt_res.interface_name));
	}
	if (OPTSTRING_PTR(clnt_res.ppp_profile_name) != NULL) {
		printf("  ppp profile name: %s\n", OPTSTRING(clnt_res.ppp_profile_name));
	}
	printf("  data sequencing required: %s\n", 
	       clnt_res.sequencing_required ? "ON" : "OFF");
	printf("  use data sequence numbers: %s\n", 
	       clnt_res.use_sequence_numbers ? "ON" : "OFF");
	if (clnt_res.reorder_timeout != 0) {
		printf("  reorder timeout: %u\n", clnt_res.reorder_timeout);
	}
	print_trace_flags(clnt_res.trace_flags, NULL);
	printf("  framing types:%s%s%s\n", 
	       ((clnt_res.framing_type_sync == 0) && (clnt_res.framing_type_async == 0)) ? " NONE" : "",
	       clnt_res.framing_type_sync ? " SYNC" : "",
	       clnt_res.framing_type_async ? " ASYNC" : "");
	printf("  bearer types:%s%s%s\n", 
	       ((clnt_res.bearer_type_digital == 0) && (clnt_res.bearer_type_analog == 0)) ? " NONE" : "",
	       clnt_res.bearer_type_digital ? " DIGITAL" : "",
	       clnt_res.bearer_type_analog ? " ANALOG" : "");
	if (clnt_res.call_serial_number != 0) {
		printf("  call serial number: %d\n", clnt_res.call_serial_number);
	}
	if (clnt_res.physical_channel_id != 0) {
		printf("  physical channel id: %d\n", clnt_res.physical_channel_id);
	}
	if ((clnt_res.minimum_bps != 0) || (clnt_res.maximum_bps != 0)) {
		printf("  min bps: %d, max bps: %d\n", clnt_res.minimum_bps, clnt_res.maximum_bps);
	}
	if (clnt_res.tx_connect_speed != 0) {
		if (clnt_res.rx_connect_speed == 0) {
			printf("  connect speed: %d\n", clnt_res.tx_connect_speed);
		} else {
			printf("  tx connect speed: %d, rx connect speed: %d\n", 
			       clnt_res.tx_connect_speed, clnt_res.rx_connect_speed);
		}
	}
	if (OPTSTRING_PTR(clnt_res.calling_number) != NULL) {
		printf("  calling number: '%s'\n", OPTSTRING(clnt_res.calling_number));
	}
	if (OPTSTRING_PTR(clnt_res.called_number) != NULL) {
		printf("  called number: '%s'\n", OPTSTRING(clnt_res.called_number));
	}
	if (OPTSTRING_PTR(clnt_res.sub_address) != NULL) {
		printf("  sub address: '%s'\n", OPTSTRING(clnt_res.sub_address));
	}
	printf("  use ppp proxy: %s\n", clnt_res.use_ppp_proxy ? "YES" : "NO");
	if (clnt_res.proxy_auth_type != L2TP_API_SESSION_PROXY_AUTH_TYPE_RESERVED) {
		printf("  proxy auth type: %s\n", 
		       (clnt_res.proxy_auth_type == L2TP_API_SESSION_PROXY_AUTH_TYPE_PLAIN_TEXT) ? "TEXT" :
		       (clnt_res.proxy_auth_type == L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_CHAP) ? "CHAP" :
		       (clnt_res.proxy_auth_type == L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_PAP) ? "PAP" :
		       (clnt_res.proxy_auth_type == L2TP_API_SESSION_PROXY_AUTH_TYPE_NO_AUTH) ? "NONE" :
		       (clnt_res.proxy_auth_type == L2TP_API_SESSION_PROXY_AUTH_TYPE_PPP_MSCHAPV1) ? "MSCHAP" : "??");
	}
	if (OPTSTRING_PTR(clnt_res.proxy_auth_name) != NULL) {
		printf("  proxy auth name: '%s'\n", OPTSTRING(clnt_res.proxy_auth_name));
	}
	if (clnt_res.proxy_auth_challenge.proxy_auth_challenge_len > 0) {
		int index;
		printf("  proxy auth challenge: ");
		for (index = 0; index < clnt_res.proxy_auth_challenge.proxy_auth_challenge_len; index++) {
			printf("%02x", clnt_res.proxy_auth_challenge.proxy_auth_challenge_val[index]);
		}
		printf("\n");
	}
	if (clnt_res.proxy_auth_response.proxy_auth_response_len > 0) {
		int index;
		printf("  proxy auth response: ");
		for (index = 0; index < clnt_res.proxy_auth_response.proxy_auth_response_len; index++) {
			printf("%02x", clnt_res.proxy_auth_response.proxy_auth_response_val[index]);
		}
		printf("\n");
	}
	if (clnt_res.initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_len > 0) {
		int index;
		printf("  initial received LCP CONFREQ: ");
		for (index = 0; index < clnt_res.initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_len; index++) {
			printf("%02x", clnt_res.initial_rcvd_lcp_confreq.initial_rcvd_lcp_confreq_val[index]);
		}
		printf("\n");
	}
	if (clnt_res.last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_len > 0) {
		int index;
		printf("  last received LCP CONFREQ: ");
		for (index = 0; index < clnt_res.last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_len; index++) {
			printf("%02x", clnt_res.last_rcvd_lcp_confreq.last_rcvd_lcp_confreq_val[index]);
		}
		printf("\n");
	}
	if (clnt_res.last_sent_lcp_confreq.last_sent_lcp_confreq_len > 0) {
		int index;
		printf("  last sent LCP CONFREQ: ");
		for (index = 0; index < clnt_res.last_sent_lcp_confreq.last_sent_lcp_confreq_len; index++) {
			printf("%02x", clnt_res.last_sent_lcp_confreq.last_sent_lcp_confreq_val[index]);
		}
		printf("\n");
	}
	if (clnt_res.peer.result_code != 0) {
		printf("  last peer response information:\n");
		printf("    result code: %hd, error code: %hd\n",
		       clnt_res.peer.result_code, clnt_res.peer.error_code);
		if (OPTSTRING_PTR(clnt_res.peer.error_message) != NULL) {
			printf("    message: '%s'\n", OPTSTRING(clnt_res.peer.error_message));
		}
	}
	if (clnt_res.peer.q931_cause_code != 0) {
		printf("  last peer Q931 information:\n");
		printf("    q931 cause code: %hd, cause msg: %hd\n",
		       clnt_res.peer.q931_cause_code, clnt_res.peer.q931_cause_msg);
		if (OPTSTRING_PTR(clnt_res.peer.q931_advisory_msg) != NULL) {
			printf("    advisory: '%s'\n", OPTSTRING(clnt_res.peer.q931_advisory_msg));
		}
	}

	printf("\n  Peer configuration data:-\n");
	if (OPTSTRING_PTR(clnt_res.peer.private_group_id) != NULL) {
		printf("    private group id: %s\n", OPTSTRING(clnt_res.peer.private_group_id));
	}
	printf("    data sequencing required: %s\n", 
	       clnt_res.peer.sequencing_required ? "ON" : "OFF");
	printf("    framing types:%s%s%s\n", 
	       ((clnt_res.framing_type_sync == 0) && (clnt_res.framing_type_async == 0)) ? " NONE" : "",
	       clnt_res.peer.framing_type_sync ? " SYNC" : "",
	       clnt_res.peer.framing_type_async ? " ASYNC" : "");
	printf("    bearer types:%s%s%s\n", 
	       ((clnt_res.bearer_type_digital == 0) && (clnt_res.bearer_type_analog == 0)) ? " NONE" : "",
	       clnt_res.peer.bearer_type_digital ? " DIGITAL" : "",
	       clnt_res.peer.bearer_type_analog ? " ANALOG" : "");
	if (clnt_res.peer.call_serial_number != 0) {
		printf("    call serial number: %d\n", clnt_res.peer.call_serial_number);
	}
	if (clnt_res.peer.physical_channel_id != 0) {
		printf("    physical channel id: %d\n", clnt_res.peer.physical_channel_id);
	}
	if ((clnt_res.peer.minimum_bps != 0) || (clnt_res.peer.maximum_bps != 0)) {
		printf("    min bps: %u, max bps: %u\n", clnt_res.peer.minimum_bps, clnt_res.peer.maximum_bps);
	}
	if (clnt_res.peer.connect_speed != 0) {
		if (clnt_res.peer.rx_connect_speed == 0) {
			printf("    connect speed: %u\n", clnt_res.peer.connect_speed);
		} else {
			printf("    tx connect speed: %u, rx connect speed: %u\n", 
			       clnt_res.peer.connect_speed, clnt_res.peer.rx_connect_speed);
		}
	}
	if (OPTSTRING_PTR(clnt_res.peer.calling_number) != NULL) {
		printf("    calling number: '%s'\n", OPTSTRING(clnt_res.peer.calling_number));
	}
	if (OPTSTRING_PTR(clnt_res.peer.called_number) != NULL) {
		printf("    called number: '%s'\n", OPTSTRING(clnt_res.peer.called_number));
	}
	if (OPTSTRING_PTR(clnt_res.peer.sub_address) != NULL) {
		printf("    calling number: '%s'\n", OPTSTRING(clnt_res.peer.sub_address));
	}
	if ((clnt_res.stats.data_rx_oos_discards > 0) || (clnt_res.stats.data_rx_oos_packets > 0)) {
		printf("  data rx out-of-sequence packets: %llu, discards: %llu\n",
		       clnt_res.stats.data_rx_oos_packets, clnt_res.stats.data_rx_oos_discards);
	}
	printf("  data rx packets: %llu, rx bytes: %llu, rx errors: %llu\n", clnt_res.stats.data_rx_packets, clnt_res.stats.data_rx_bytes, clnt_res.stats.data_rx_errors);
	printf("  data tx packets: %llu, tx bytes: %llu, tx errors: %llu\n", clnt_res.stats.data_tx_packets, clnt_res.stats.data_tx_bytes, clnt_res.stats.data_tx_errors);

out:
	return result;
}

static int l2tp_act_session_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	u_short tunnel_id = 0;
	optstring tunnel_name = { 0, };
	int loop;
	int flags;
	L2TP_ACT_DECLARATIONS(4, l2tp_session_arg_ids_t, struct l2tp_api_session_list_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SESSION_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], tunnel_id, flags, 0);
			break;
		case L2TP_SESSION_ARGID_TUNNEL_NAME:
			OPTSTRING(tunnel_name) = strdup(arg_values[arg]);
			if (OPTSTRING(tunnel_name) == NULL) {
				result = -ENOMEM;
				goto out;
			}
			tunnel_name.valid = 1;
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if ((tunnel_id == 0) && (tunnel_name.valid == 0)) {
		fprintf(stderr, "Required tunnel_id or tunnel_name argument is missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_session_list_1(tunnel_id, tunnel_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.session_ids.session_ids_len > 0) {
		char tunnel_id_str[10];
		sprintf(&tunnel_id_str[0], "%hu", tunnel_id);
		printf("%hd sessions on tunnel %s:-\n", clnt_res.session_ids.session_ids_len, 
		       (tunnel_id != 0) ? tunnel_id_str : OPTSTRING_PTR(tunnel_name));

		/* Sort the list of session ids */
		qsort(&clnt_res.session_ids.session_ids_val[0], clnt_res.session_ids.session_ids_len,
		      sizeof(clnt_res.session_ids.session_ids_val[0]), l2tp_id_compare);

		for (loop = 0; loop < clnt_res.session_ids.session_ids_len; loop++) {
			printf("\t%hd\n", clnt_res.session_ids.session_ids_val[loop]);
		}
	}	

out:
	return result;
}

/*****************************************************************************
 * Session profiles
 *****************************************************************************/

static struct cli_arg_entry l2tp_args_session_profile_create[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	"Name of session profile"),
	ARG(PPP_PROFILE_NAME,	"ppp_profile_name",	0,	string,	"Name of ppp profile to use for PPP parameters"),
	L2TP_SESSION_MODIFY_ARGS,
	ARG(SESSION_TYPE,	"session_type",		0,	string,	"Session type: LAC/LNS incoming/outgoing"),
	ARG(PRIV_GROUP_ID,	"priv_group_id",	0,	string,	"Private group ID, used to separate this session into a named administrative group"),
	ARG(FRAMING_TYPE,	"framing_type",		0,	int32,	"Framing type: sync, async or any. Default: any (derived from tunnel)"),
	ARG(BEARER_TYPE,	"bearer_type",		0,	int32,	"Bearer type: none, digital, analog, any. Default: any (derived from tunnel)"),
	ARG(MINIMUM_BPS,	"minimum_bps",		0,	uint32,	"Minimum bits/sec acceptable. Default: 0"),
	ARG(MAXIMUM_BPS,	"maximum_bps",		0,	uint32,	"Maximum bits/sec required. Default: no limit"),
	ARG(CONNECT_SPEED,	"connect_speed",	0,	uint32,	"Specified as speed[:txspeed, indicates connection speeds."),
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_profile_delete[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	"Name of session profile"),
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_profile_modify[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	"Name of session profile"),
	ARG(PPP_PROFILE_NAME,	"ppp_profile_name",	0,	string,	"Name of ppp profile to use for PPP parameters"),
	L2TP_SESSION_MODIFY_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_session_profile_show[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	"Name of session profile"),
	{ NULL, },
};

static int l2tp_parse_session_profile_arg(l2tp_session_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_session_profile_msg_data *msg)
{
	int result = -EINVAL;
	int num_matches;
	int ints[2];

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_SESSION_ARGID_PROFILE_NAME:
		msg->profile_name = strdup(arg_value);
		if (msg->profile_name == NULL) {
			result = -ENOMEM;
			goto out;
		}
		break;
	case L2TP_SESSION_ARGID_TRACE_FLAGS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->trace_flags, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_TRACE_FLAGS);
		break;
	case L2TP_SESSION_ARGID_SEQUENCING_REQUIRED:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->sequencing_required, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_SEQUENCING_REQUIRED);
		break;
	case L2TP_SESSION_ARGID_USE_SEQUENCE_NUMBERS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_sequence_numbers, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_USE_SEQUENCE_NUMBERS);
		break;
	case L2TP_SESSION_ARGID_REORDER_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->reorder_timeout, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_REORDER_TIMEOUT);
		break;
	case L2TP_SESSION_ARGID_PPP_PROFILE_NAME:
		OPTSTRING(msg->ppp_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->ppp_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->ppp_profile_name.valid = 1;
		msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_PPP_PROFILE_NAME;
		break;
	case L2TP_SESSION_ARGID_SESSION_TYPE:
		if (strcasecmp(arg_value, "laic") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LAIC;
		} else if (strcasecmp(arg_value, "laoc") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LAOC;
		} else if (strcasecmp(arg_value, "lnic") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LNIC;
		} else if (strcasecmp(arg_value, "lnoc") == 0) {
			msg->session_type = L2TP_API_SESSION_TYPE_LNOC;
		} else {
			fprintf(stderr, "Bad session type %s: expecting laic|laoc|lnic|lnoc\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_SESSION_TYPE;
		break;
	case L2TP_SESSION_ARGID_PRIV_GROUP_ID:
		OPTSTRING(msg->priv_group_id) = strdup(arg_value);
		if (OPTSTRING(msg->priv_group_id) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->priv_group_id.valid = 1;
		msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_PRIV_GROUP_ID;
		break;
	case L2TP_SESSION_ARGID_FRAMING_TYPE:
		if (strcasecmp(arg_value, "sync") == 0) {
			msg->framing_type_sync = TRUE;
			msg->framing_type_async = FALSE;
		} else if (strcasecmp(arg_value, "async") == 0) {
			msg->framing_type_sync = FALSE;
			msg->framing_type_async = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->framing_type_sync = TRUE;
			msg->framing_type_async = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->framing_type_sync = FALSE;
			msg->framing_type_async = FALSE;
		} else {
			fprintf(stderr, "Bad framing type %s: expecting none|sync|async|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_FRAMING_TYPE;
		break;
	case L2TP_SESSION_ARGID_BEARER_TYPE:
		if (strcasecmp(arg_value, "digital") == 0) {
			msg->bearer_type_digital = TRUE;
			msg->bearer_type_analog = FALSE;
		} else if (strcasecmp(arg_value, "analog") == 0) {
			msg->bearer_type_digital = FALSE;
			msg->bearer_type_analog = TRUE;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->bearer_type_digital = TRUE;
			msg->bearer_type_analog = TRUE;
		} else if (strcasecmp(arg_value, "none") == 0) {
			msg->bearer_type_digital = FALSE;
			msg->bearer_type_analog = FALSE;
		} else {
			fprintf(stderr, "Bad bearer type %s: expecting none|digital|analog|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_BEARER_TYPE;
		break;
	case L2TP_SESSION_ARGID_MINIMUM_BPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->minimum_bps, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_MINIMUM_BPS);
		break;
	case L2TP_SESSION_ARGID_MAXIMUM_BPS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->maximum_bps, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_MAXIMUM_BPS);
		break;
	case L2TP_SESSION_ARGID_CONNECT_SPEED:
		num_matches = sscanf(arg_value, "%d:%d", &ints[0], &ints[1]);
		if (num_matches >= 1) {
			msg->rx_connect_speed = ints[0];
			msg->tx_connect_speed = ints[0];
			if (num_matches == 2) {
				msg->tx_connect_speed = ints[1];
			}
			msg->flags |= L2TP_API_SESSION_PROFILE_FLAG_CONNECT_SPEED;
		} else {
			fprintf(stderr, "Expecting connect_speed[:tx_connect_speed]\n");
			goto out;
		}
		break;
	case L2TP_SESSION_ARGID_USE_PPP_PROXY:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_ppp_proxy, msg->flags, L2TP_API_SESSION_PROFILE_FLAG_USE_PPP_PROXY);
		break;
	case L2TP_SESSION_ARGID_TUNNEL_ID:
	case L2TP_SESSION_ARGID_TUNNEL_NAME:
	case L2TP_SESSION_ARGID_SESSION_ID:
	case L2TP_SESSION_ARGID_SESSION_NAME:
	case L2TP_SESSION_ARGID_INTERFACE_NAME:
	case L2TP_SESSION_ARGID_USER_NAME:
	case L2TP_SESSION_ARGID_USER_PASSWORD:
	case L2TP_SESSION_ARGID_PROXY_AUTH_TYPE:
	case L2TP_SESSION_ARGID_PROXY_AUTH_NAME:
	case L2TP_SESSION_ARGID_PROXY_AUTH_CHALLENGE:
	case L2TP_SESSION_ARGID_PROXY_AUTH_RESPONSE:
	case L2TP_SESSION_ARGID_CALLING_NUMBER:
	case L2TP_SESSION_ARGID_CALLED_NUMBER:
	case L2TP_SESSION_ARGID_SUB_ADDRESS:
	case L2TP_SESSION_ARGID_INITIAL_RCVD_LCP_CONFREQ:
	case L2TP_SESSION_ARGID_LAST_SENT_LCP_CONFREQ:
	case L2TP_SESSION_ARGID_LAST_RCVD_LCP_CONFREQ:
		/* these are invalid in a session profile */
		result = -EINVAL;
		break;
	}

	result = 0;

out:
	return result;
}

static int l2tp_act_session_profile_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_session_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_session_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_profile_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created session profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_session_profile_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SESSION_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_profile_delete_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Deleted session profile %s\n", profile_name);
	}

out:
	return result;
}

static int l2tp_act_session_profile_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_session_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_session_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_session_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_session_profile_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified session profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_session_profile_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_session_arg_ids_t, struct l2tp_api_session_profile_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_SESSION_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_session_profile_get_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	printf("Session profile %s\n", clnt_res.profile_name);
	printf("  ppp profile: %s\n", OPTSTRING(clnt_res.ppp_profile_name));
	print_trace_flags(clnt_res.trace_flags, NULL);
	printf("  session type: %s\n",
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_UNSPECIFIED) ? "unspecified" :
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_LAIC) ? "LAC Incoming Call" :
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_LAOC) ? "LAC Outgoing Call" :
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_LNIC) ? "LNS Incoming Call" :
	       (clnt_res.session_type == L2TP_API_SESSION_TYPE_LNOC) ? "LNS Outgoing Call" : "??");
	if (OPTSTRING_PTR(clnt_res.priv_group_id) != NULL) {
		printf("  private group id: %s\n", OPTSTRING(clnt_res.priv_group_id));
	}
	printf("  data sequencing required: %s\n", 
	       clnt_res.sequencing_required ? "ON" : "OFF");
	printf("  use data sequence numbers: %s\n", 
	       clnt_res.use_sequence_numbers ? "ON" : "OFF");
	if (clnt_res.reorder_timeout != 0) {
		printf("  reorder timeout: %u ms\n", clnt_res.reorder_timeout);
	}
	printf("  framing types:%s%s%s\n", 
	       ((clnt_res.framing_type_sync == 0) && (clnt_res.framing_type_async == 0)) ? " NONE" : "",
	       clnt_res.framing_type_sync ? " SYNC" : "",
	       clnt_res.framing_type_async ? " ASYNC" : "");
	printf("  bearer types:%s%s%s\n", 
	       ((clnt_res.bearer_type_digital == 0) && (clnt_res.bearer_type_analog == 0)) ? " NONE" : "",
	       clnt_res.bearer_type_digital ? " DIGITAL" : "",
	       clnt_res.bearer_type_analog ? " ANALOG" : "");
	if ((clnt_res.minimum_bps != 0) || (clnt_res.maximum_bps != 0)) {
		printf("  min bps: %d, max bps: %d\n", clnt_res.minimum_bps, clnt_res.maximum_bps);
	}
	if (clnt_res.tx_connect_speed != 0) {
		if (clnt_res.rx_connect_speed == 0) {
			printf("  connect speed: %d\n", clnt_res.tx_connect_speed);
		} else {
			printf("  tx connect speed: %d, rx connect speed: %d\n", 
			       clnt_res.tx_connect_speed, clnt_res.rx_connect_speed);
		}
	}
	printf("  use count: %d\n", clnt_res.use_count);
	printf("\n");

out:
	return result;
}

static int l2tp_act_session_profile_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_session_profile_list_msg_data clnt_res;
	struct l2tp_api_session_profile_list_entry *walk;
	int result;
	const char **profile_names;
	int index;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_session_profile_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.num_profiles > 0) {
		profile_names = calloc(clnt_res.num_profiles, sizeof(profile_names[0]));
		if (profile_names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(ENOMEM));
			goto out;
		}
	
		walk = clnt_res.profiles;
		for (index = 0; index < clnt_res.num_profiles; index++) {
			if ((walk == NULL) || (walk->profile_name[0] == '\0')) {
				break;
			}
			profile_names[index] = walk->profile_name;
			walk = walk->next;
		}	

		/* Sort the profile names */
		qsort(&profile_names[0], index, sizeof(profile_names[0]), l2tp_name_compare);

		for (index = 0; index < clnt_res.num_profiles; index++) {
			printf("\t%s\n", profile_names[index]);
		}

		free(profile_names);
	}

	result = 0;

out:
	return result;
}


/*****************************************************************************
 * Ppp profiles
 *****************************************************************************/

typedef enum {
	L2TP_PPP_ARGID_TRACE_FLAGS,
	L2TP_PPP_ARGID_PROFILE_NAME,
	L2TP_PPP_ARGID_ASYNCMAP,
	L2TP_PPP_ARGID_MTU,
	L2TP_PPP_ARGID_MRU,
	L2TP_PPP_ARGID_SYNC_MODE,
	L2TP_PPP_ARGID_AUTH_PAP,
	L2TP_PPP_ARGID_AUTH_CHAP,
	L2TP_PPP_ARGID_AUTH_MSCHAP,
	L2TP_PPP_ARGID_AUTH_MSCHAPV2,
	L2TP_PPP_ARGID_AUTH_EAP,
	L2TP_PPP_ARGID_REQ_PAP,
	L2TP_PPP_ARGID_REQ_CHAP,
	L2TP_PPP_ARGID_REQ_MSCHAP,
	L2TP_PPP_ARGID_REQ_MSCHAPV2,
	L2TP_PPP_ARGID_REQ_EAP,
	L2TP_PPP_ARGID_REQ_NONE,
	L2TP_PPP_ARGID_CHAP_INTERVAL,
	L2TP_PPP_ARGID_CHAP_MAX_CHALLENGE,
	L2TP_PPP_ARGID_CHAP_RESTART,
	L2TP_PPP_ARGID_PAP_MAX_AUTH_REQS,
	L2TP_PPP_ARGID_PAP_RESTART_INTVL,
	L2TP_PPP_ARGID_PAP_TIMEOUT,
	L2TP_PPP_ARGID_IDLE_TIMEOUT,
	L2TP_PPP_ARGID_IPCP_MAX_CFG_REQS,
	L2TP_PPP_ARGID_IPCP_MAX_CFG_NAKS,
	L2TP_PPP_ARGID_IPCP_MAX_TERM_REQS,
	L2TP_PPP_ARGID_IPCP_RETX_INTVL,
	L2TP_PPP_ARGID_LCP_ECHO_FAIL_COUNT,
	L2TP_PPP_ARGID_LCP_ECHO_INTERVAL,
	L2TP_PPP_ARGID_LCP_MAX_CFG_REQS,
	L2TP_PPP_ARGID_LCP_MAX_CFG_NAKS,
	L2TP_PPP_ARGID_LCP_MAX_TERM_REQS,
	L2TP_PPP_ARGID_LCP_RETX_INTVL,
	L2TP_PPP_ARGID_MAX_CONNECT_TIME,
	L2TP_PPP_ARGID_MAX_FAILURE_COUNT,
	L2TP_PPP_ARGID_LOCAL_IPADDR,
	L2TP_PPP_ARGID_REMOTE_IPADDR,
	L2TP_PPP_ARGID_DNS_IPADDR_PRI,
	L2TP_PPP_ARGID_DNS_IPADDR_SEC,
	L2TP_PPP_ARGID_WINS_IPADDR_PRI,
	L2TP_PPP_ARGID_WINS_IPADDR_SEC,
	L2TP_PPP_ARGID_IP_POOL_NAME,
	L2TP_PPP_ARGID_USE_RADIUS,
	L2TP_PPP_ARGID_RADIUS_HINT,
	L2TP_PPP_ARGID_USE_AS_DEFAULT_ROUTE,
	L2TP_PPP_ARGID_MULTILINK,
	L2TP_PPP_ARGID_MPPE,
	L2TP_PPP_ARGID_COMP_MPPC,
	L2TP_PPP_ARGID_COMP_ACCOMP,
	L2TP_PPP_ARGID_COMP_PCOMP,
	L2TP_PPP_ARGID_COMP_BSDCOMP,
	L2TP_PPP_ARGID_COMP_DEFLATE,
	L2TP_PPP_ARGID_COMP_PREDICTOR1,
	L2TP_PPP_ARGID_COMP_VJ,
	L2TP_PPP_ARGID_COMP_CCOMP_VJ,
	L2TP_PPP_ARGID_COMP_ASK_DEFLATE,
	L2TP_PPP_ARGID_COMP_ASK_BSDCOMP,
} l2tp_ppp_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_PPP_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_PPP_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

/* Paremeters for Create and Modify operations */
#define L2TP_PPP_MODIFY_ARGS 																\
	ARG(TRACE_FLAGS, 	"trace_flags", 		0, 	uint32,	"Trace flags, for debugging network problems"),					\
	ARG(ASYNCMAP, 		"asyncmap", 		0, 	uint32,	"Async character map. Valid only if PPP is async mode."),			\
	ARG(MTU, 		"mtu",	 		0, 	uint16,	"Maximum Transmit Unit (MTU) or maximum packet size transmitted."),		\
	ARG(MRU, 		"mru",	 		0, 	uint16,	"Maximum Receive Unit (MRU) or maximum packet size passed when received."),	\
	ARG(SYNC_MODE, 		"sync_mode", 		0, 	string,	"Allow PPP sync/async operation."),						\
	ARG(AUTH_PAP, 		"auth_pap", 		0, 	bool,	"Accept PPP PAP authentication. Default: YES"),					\
	ARG(AUTH_CHAP, 		"auth_chap", 		0, 	bool,	"Accept PPP CHAP authentication. Default: YES"),					\
	ARG(AUTH_MSCHAP,	"auth_mschapv1",	0, 	bool,	"Accept PPP MSCHAP authentication. Default: YES"),				\
	ARG(AUTH_MSCHAPV2, 	"auth_mschapv2", 	0, 	bool,	"Accept PPP MSCHAPV2 authentication. Default: YES"),				\
	ARG(AUTH_EAP, 		"auth_eap", 		0, 	bool,	"Accept PPP EAP authentication. Default: YES"),					\
	ARG(REQ_PAP, 	        "req_pap", 	        0, 	bool,	"Allow PPP PAP authentication. Default: NO"),					\
	ARG(REQ_CHAP, 	        "req_chap",      	0, 	bool,	"Allow PPP CHAP authentication. Default: NO"),					\
	ARG(REQ_MSCHAP,	        "req_mschapv1",	        0, 	bool,	"Allow PPP MSCHAP authentication. Default: NO"),				\
	ARG(REQ_MSCHAPV2, 	"req_mschapv2", 	0, 	bool,	"Allow PPP MSCHAPV2 authentication. Default: NO"),				\
        ARG(REQ_EAP, 	        "req_eap",        	0, 	bool,	"Allow PPP EAP authentication. Default: NO"), \
	ARG(REQ_NONE, 		"req_none", 		0, 	bool,	"Allow unauthenticated PPP users. Default: NO"),				\
	ARG(CHAP_INTERVAL,	"chap_interval",	0,	int32,	("Rechallenge the peer every chap_interval seconds. "				\
									 "Default=0 (don't rechallenge).")),						\
	ARG(CHAP_MAX_CHALLENGE,	"chap_max_challenge",	0,	int32,	("Maximum number of CHAP challenges to transmit without successful "		\
									 "acknowledgment before declaring a failure. Default=10.")),			\
	ARG(CHAP_RESTART,	"chap_restart",		0,	int32,	("Retransmission timeout for CHAP challenges. Default=3.")),			\
	ARG(PAP_MAX_AUTH_REQS,	"pap_max_auth_requests", 0,	int32,	("Maximum number of PAP authenticate-request transmissions. Default=10.")),	\
	ARG(PAP_RESTART_INTVL,	"pap_restart_interval",	0,	int32,	"Retransmission timeout for PAP requests. Default=3."),				\
	ARG(PAP_TIMEOUT,	"pap_timeout",		0,	int32,	"Maximum time to wait for peer to authenticate itself. Default=0 (no limit)."),	\
	ARG(IDLE_TIMEOUT,	"idle_timeout",		0,	int32,	"Disconnect session if idle for more than N seconds. Default=0 (no limit)."),	\
	ARG(IPCP_MAX_CFG_REQS,	"ipcp_max_config_requests", 0,	int32,	("Maximum number of IPCP config-requests to transmit without successful "	\
	    								 "acknowledgement before declaring a failure. Default=10.")),			\
	ARG(IPCP_MAX_CFG_NAKS,	"ipcp_max_config_naks",	0,	int32,	("Maximum number of IPCP config-naks to allow before starting to send "		\
									 "config-rejects instead. Default=10.")),					\
	ARG(IPCP_MAX_TERM_REQS,	"ipcp_max_terminate_requests", 0, int32, "Maximum number of IPCP term-requests to send. Default=3."),			\
	ARG(IPCP_RETX_INTVL,	"ipcp_retransmit_interval", 0,	int32,	"IPCP retransmission timeout. Default=3."),					\
	ARG(LCP_ECHO_FAIL_COUNT,"lcp_echo_failure_count",0,	int32,	("Number of LCP echo failures to accept before assuming peer is down. "		\
									 "Default=5.")),								\
	ARG(LCP_ECHO_INTERVAL,	"lcp_echo_interval",	0,	int32,	"Send LCP echo-request to peer every N seconds. Default=0 (don't send)."),	\
	ARG(LCP_MAX_CFG_REQS,	"lcp_max_config_requests", 0,	int32,	"Maximum number of LCP config-request transmissions. Default=10."),		\
	ARG(LCP_MAX_CFG_NAKS,	"lcp_max_config_naks",	0,	int32,	("Maximum number of LCP config-requests to transmit without successful "  	\
	    								 "acknowledgement before declaring a failure. Default=10.")),			\
	ARG(LCP_MAX_TERM_REQS,	"lcp_max_terminate_requests", 0, int32,	"Maximum number of LCP term-requests to send. Default=3."),			\
	ARG(LCP_RETX_INTVL,	"lcp_retransmit_interval", 0,	int32,	"LCP retransmission timeout. Default=3."),					\
	ARG(MAX_CONNECT_TIME,	"max_connect_time",	0,	int32,	("Maximum connect time (in seconds) that the PPP session may stay in use."	\
									 "Default=0 (no limit)")),							\
	ARG(MAX_FAILURE_COUNT,	"max_failure_count",	0,	int32,	"Terminate after N consecutive attempts. 0 is no limit. Default=10."),		\
	ARG(IP_POOL_NAME,	"ip_pool_name",		0,	string,	"IP pool name. If system supports IP address pools, this name will be "		\
									"passed to PPP for address assignment."),					\
	ARG(LOCAL_IPADDR,	"local_ipaddr",		0,	ipaddr,	"IP address of local PPP interface"),						\
	ARG(REMOTE_IPADDR,	"remote_ipaddr",	0,	ipaddr,	"IP address of remote PPP interface"),						\
	ARG(DNS_IPADDR_PRI,	"dns_ipaddr_pri",	0,	ipaddr,	"Primary DNS address"),								\
	ARG(DNS_IPADDR_SEC,	"dns_ipaddr_sec",	0,	ipaddr,	"Secondary DNS address"),							\
	ARG(WINS_IPADDR_PRI,	"wins_ipaddr_pri",	0,	ipaddr,	"Primary WINS address"),							\
	ARG(WINS_IPADDR_SEC,	"wins_ipaddr_sec",	0,	ipaddr,	"Secondary WINS address"),							\
	ARG(USE_RADIUS,		"use_radius",		0,	bool,	"Use RADIUS for PPP authentication and connection attributes"),			\
	ARG(RADIUS_HINT,	"radius_hint",		0,	string,	"String to pass to RADIUS client for use when doing RADIUS lookup"),		\
	ARG(USE_AS_DEFAULT_ROUTE, "default_route",	0,	bool,	"Use link as default route"),							\
	ARG(MULTILINK,		"multilink",		0, 	bool, 	"Enable PPP multilink connections."),                                           \
	ARG(MPPE,		"mppe",		0, 	bool, 	"Enable PPP MPPE."),                                                \
	ARG(COMP_MPPC,		"comp_mppc",		0, 	bool, 	"Enable PPP MPPC compression."),                                                \
	ARG(COMP_ACCOMP,	"comp_accomp",		0, 	bool, 	"Enable PPP ACCOMP compression."),                                              \
	ARG(COMP_PCOMP,		"comp_pcomp",		0, 	bool, 	"Enable PPP PCOMP compression."),                                               \
	ARG(COMP_BSDCOMP,	"comp_bsdcomp",		0, 	bool, 	"Enable PPP BSDCOMP compression."),                                             \
	ARG(COMP_DEFLATE,	"comp_deflate",		0, 	bool, 	"Enable PPP DEFLATE compression."),                                             \
	ARG(COMP_PREDICTOR1,	"comp_predictor1",	0, 	bool, 	"Enable PPP PREDICTOR1 compression."),                                          \
	ARG(COMP_VJ,		"comp_vj",		0, 	bool, 	"Enable PPP VJ compression."),                                                  \
        ARG(COMP_CCOMP_VJ,	"comp_ccomp_vj",	0, 	bool, 	"Enable PPP VJCCOMP compression."),                                             \
	ARG(COMP_ASK_DEFLATE,	"comp_ask_deflate",	0, 	bool, 	"Ask for PPP DEFLATE compression."),                                            \
	ARG(COMP_ASK_BSDCOMP,   "comp_ask_bsdcomp",   	0, 	bool, 	"Ask for PPP BSDCOMP compression.")

static struct cli_arg_entry l2tp_args_ppp_profile_create[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of ppp profile")),
	L2TP_PPP_MODIFY_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_ppp_profile_delete[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of ppp profile")),
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_ppp_profile_modify[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of ppp profile")),
	L2TP_PPP_MODIFY_ARGS,
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_ppp_profile_show[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of ppp profile")),
	{ NULL, },
};

static int l2tp_parse_ppp_profile_arg(l2tp_ppp_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_ppp_profile_msg_data *msg)
{
	int result = -EINVAL;

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_PPP_ARGID_PROFILE_NAME:
		msg->profile_name = strdup(arg_value);
		if (msg->profile_name == NULL) {
			result = -ENOMEM;
			goto out;
		}
		break;
	case L2TP_PPP_ARGID_TRACE_FLAGS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->trace_flags, msg->flags, L2TP_API_PPP_PROFILE_FLAG_TRACE_FLAGS);
		break;
	case L2TP_PPP_ARGID_ASYNCMAP:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->asyncmap, msg->flags, L2TP_API_PPP_PROFILE_FLAG_ASYNCMAP);
		break;
	case L2TP_PPP_ARGID_MTU:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->mtu, msg->flags, L2TP_API_PPP_PROFILE_FLAG_MTU);
		break;
	case L2TP_PPP_ARGID_MRU:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->mru, msg->flags, L2TP_API_PPP_PROFILE_FLAG_MRU);
		break;
	case L2TP_PPP_ARGID_SYNC_MODE:
		if (strcasecmp(arg_value, "sync") == 0) {
			msg->sync_mode = L2TP_API_PPP_SYNCMODE_SYNC;
		} else if (strcasecmp(arg_value, "async") == 0) {
			msg->sync_mode = L2TP_API_PPP_SYNCMODE_ASYNC;
		} else if (strcasecmp(arg_value, "any") == 0) {
			msg->sync_mode = L2TP_API_PPP_SYNCMODE_SYNC_ASYNC;
		} else {
			fprintf(stderr, "Bad sync mode %s: expecting sync|async|any\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_PPP_PROFILE_FLAG_SYNC_MODE;
		break;
	case L2TP_PPP_ARGID_AUTH_PAP:
		L2TP_ACT_PARSE_ARG_FLAG_NEG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_AUTH_REFUSE_PAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_AUTH_CHAP:
		L2TP_ACT_PARSE_ARG_FLAG_NEG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_AUTH_REFUSE_CHAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_AUTH_MSCHAP:
		L2TP_ACT_PARSE_ARG_FLAG_NEG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_AUTH_REFUSE_MSCHAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_AUTH_MSCHAPV2:
		L2TP_ACT_PARSE_ARG_FLAG_NEG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_AUTH_REFUSE_MSCHAPV2, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_AUTH_EAP:
		L2TP_ACT_PARSE_ARG_FLAG_NEG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_AUTH_REFUSE_EAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_PAP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_PAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_CHAP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_CHAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_MSCHAP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_MSCHAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_MSCHAPV2:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_MSCHAPV2, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_EAP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_EAP, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_REQ_NONE:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->auth_flags, L2TP_API_PPP_REQUIRE_NONE, msg->flags, L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS);
		break;
	case L2TP_PPP_ARGID_CHAP_INTERVAL:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->chap_interval, msg->flags, L2TP_API_PPP_PROFILE_FLAG_CHAP_INTERVAL);
		break;
	case L2TP_PPP_ARGID_CHAP_MAX_CHALLENGE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->chap_max_challenge, msg->flags, L2TP_API_PPP_PROFILE_FLAG_CHAP_MAX_CHALLENGE);
		break;
	case L2TP_PPP_ARGID_CHAP_RESTART:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->chap_restart, msg->flags, L2TP_API_PPP_PROFILE_FLAG_CHAP_RESTART);
		break;
	case L2TP_PPP_ARGID_PAP_MAX_AUTH_REQS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->pap_max_auth_requests, msg->flags, L2TP_API_PPP_PROFILE_FLAG_PAP_MAX_AUTH_REQUESTS);
		break;
	case L2TP_PPP_ARGID_PAP_RESTART_INTVL:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->pap_restart_interval, msg->flags, L2TP_API_PPP_PROFILE_FLAG_PAP_RESTART_INTERVAL);
		break;
	case L2TP_PPP_ARGID_PAP_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->pap_timeout, msg->flags, L2TP_API_PPP_PROFILE_FLAG_PAP_TIMEOUT);
		break;
	case L2TP_PPP_ARGID_IDLE_TIMEOUT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->idle_timeout, msg->flags, L2TP_API_PPP_PROFILE_FLAG_IDLE_TIMEOUT);
		break;
	case L2TP_PPP_ARGID_IPCP_MAX_CFG_REQS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->ipcp_max_config_requests, msg->flags, L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_REQUESTS);
		break;
	case L2TP_PPP_ARGID_IPCP_MAX_CFG_NAKS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->ipcp_max_config_naks, msg->flags, L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_NAKS);
		break;
	case L2TP_PPP_ARGID_IPCP_MAX_TERM_REQS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->ipcp_max_terminate_requests, msg->flags, L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_TERMINATE_REQUESTS);
		break;
	case L2TP_PPP_ARGID_IPCP_RETX_INTVL:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->ipcp_retransmit_interval, msg->flags, L2TP_API_PPP_PROFILE_FLAG_IPCP_RETRANSMIT_INTERVAL);
		break;
	case L2TP_PPP_ARGID_LCP_ECHO_FAIL_COUNT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_echo_failure_count, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_FAILURE_COUNT);
		break;
	case L2TP_PPP_ARGID_LCP_ECHO_INTERVAL:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_echo_interval, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_INTERVAL);
		break;
	case L2TP_PPP_ARGID_LCP_MAX_CFG_REQS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_max_config_requests, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_REQUESTS);
		break;
	case L2TP_PPP_ARGID_LCP_MAX_CFG_NAKS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_max_config_naks, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_NAKS);
		break;
	case L2TP_PPP_ARGID_LCP_MAX_TERM_REQS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_max_terminate_requests, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_TERMINATE_REQUESTS);
		break;
	case L2TP_PPP_ARGID_LCP_RETX_INTVL:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->lcp_retransmit_interval, msg->flags, L2TP_API_PPP_PROFILE_FLAG_LCP_RETRANSMIT_INTERVAL);
		break;
	case L2TP_PPP_ARGID_MAX_CONNECT_TIME:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_connect_time, msg->flags, L2TP_API_PPP_PROFILE_FLAG_MAX_CONNECT_TIME);
		break;
	case L2TP_PPP_ARGID_MAX_FAILURE_COUNT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->max_failure_count, msg->flags, L2TP_API_PPP_PROFILE_FLAG_MAX_FAILURE_COUNT);
		break;
	case L2TP_PPP_ARGID_LOCAL_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->local_ip_addr, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_LOCAL_IP_ADDR);
		break;
	case L2TP_PPP_ARGID_REMOTE_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_ip_addr, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_PEER_IP_ADDR);
		break;
	case L2TP_PPP_ARGID_DNS_IPADDR_PRI:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->dns_addr_1, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_1);
		break;
	case L2TP_PPP_ARGID_DNS_IPADDR_SEC:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->dns_addr_2, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_2);
		break;
	case L2TP_PPP_ARGID_WINS_IPADDR_PRI:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->wins_addr_1, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_1);
		break;
	case L2TP_PPP_ARGID_WINS_IPADDR_SEC:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->wins_addr_2, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_2);
		break;
	case L2TP_PPP_ARGID_IP_POOL_NAME:
		OPTSTRING(msg->ip_pool_name) = strdup(arg_value);
		if (OPTSTRING(msg->ip_pool_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->ip_pool_name.valid = 1;
		msg->flags2 |= L2TP_API_PPP_PROFILE_FLAG_IP_POOL_NAME;
		break;
	case L2TP_PPP_ARGID_USE_RADIUS:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_radius, msg->flags, L2TP_API_PPP_PROFILE_FLAG_USE_RADIUS);
		break;
	case L2TP_PPP_ARGID_RADIUS_HINT:
		OPTSTRING(msg->radius_hint) = strdup(arg_value);
		if (OPTSTRING(msg->radius_hint) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->radius_hint.valid = 1;
		msg->flags |= L2TP_API_PPP_PROFILE_FLAG_RADIUS_HINT;
		break;
	case L2TP_PPP_ARGID_USE_AS_DEFAULT_ROUTE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->use_as_default_route, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_USE_AS_DEFAULT_ROUTE);
		break;
	case L2TP_PPP_ARGID_MULTILINK:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->multilink, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_MULTILINK);
		break;
	case L2TP_PPP_ARGID_MPPE:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->mppe, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_MPPE);
		break;
	case L2TP_PPP_ARGID_COMP_MPPC:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_MPPC, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_ACCOMP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_ACCOMP, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_PCOMP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_PCOMP, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_BSDCOMP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_BSDCOMP, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_DEFLATE:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_DEFLATE, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_PREDICTOR1:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_PREDICTOR1, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_VJ:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_VJ, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_CCOMP_VJ:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_CCOMP_VJ, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_ASK_DEFLATE:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_ASK_DEFLATE, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	case L2TP_PPP_ARGID_COMP_ASK_BSDCOMP:
		L2TP_ACT_PARSE_ARG_FLAG(arg, arg_value, msg->comp_flags, L2TP_API_PPP_COMP_ASK_BSDCOMP, msg->flags2, L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS);
		break;
	}
	result = 0;

out:
	return result;
}


static int l2tp_act_ppp_profile_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_ppp_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(60, l2tp_ppp_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_ppp_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_ppp_profile_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created ppp profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_ppp_profile_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_ppp_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_PPP_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_ppp_profile_delete_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Deleted ppp profile %s\n", profile_name);
	}

out:
	return result;
}

static int l2tp_act_ppp_profile_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_ppp_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(80, l2tp_ppp_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_ppp_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_ppp_profile_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified ppp profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static void ip_to_string(char *result, uint32_t addr)
{
	struct in_addr ip;
	char *str;

	ip.s_addr = addr;
	str = inet_ntoa(ip);
	if ((str != NULL) && (strcmp(str, "0.0.0.0") != 0)) {
		strcpy(result, str);
	} else {
		strcpy(result, "NOT SET");
	}
}

static int l2tp_act_ppp_profile_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	char local_ip[16];
	char peer_ip[16];
	char dns1[16];
	char dns2[16];
	char wins1[16];
	char wins2[16];
	L2TP_ACT_DECLARATIONS(4, l2tp_ppp_arg_ids_t, struct l2tp_api_ppp_profile_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_PPP_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_ppp_profile_get_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	printf("Ppp profile %s\n", clnt_res.profile_name);
	print_trace_flags(clnt_res.trace_flags, NULL);
	printf("  mru: %hu, mtu: %hu, mode: %s\n",
	       clnt_res.mru, clnt_res.mtu, 
	       (clnt_res.sync_mode == L2TP_API_PPP_SYNCMODE_SYNC_ASYNC) ? "SYNC|ASYNC" :
	       (clnt_res.sync_mode == L2TP_API_PPP_SYNCMODE_SYNC) ? "SYNC" :
	       (clnt_res.sync_mode == L2TP_API_PPP_SYNCMODE_ASYNC) ? "ASYNC" : "??");
	printf("  authenticate to peer using: %s%s%s%s%s\n", 
	       clnt_res.auth_flags & L2TP_API_PPP_AUTH_REFUSE_PAP ? "" : "PAP ",
	       clnt_res.auth_flags & L2TP_API_PPP_AUTH_REFUSE_CHAP ? "" : "CHAP ",
	       clnt_res.auth_flags & L2TP_API_PPP_AUTH_REFUSE_MSCHAP ? "" : "MSCHAP ",
	       clnt_res.auth_flags & L2TP_API_PPP_AUTH_REFUSE_MSCHAPV2 ? "" : "MSCHAPv2 ",
	       clnt_res.auth_flags & L2TP_API_PPP_AUTH_REFUSE_EAP ? "" : "EAP ");

	printf("  allowed (required) peer authentications: %s%s%s%s%s%s\n", 
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_PAP ? "PAP " : "",
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_CHAP ? "CHAP " : "",
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_MSCHAP ? "MSCHAP " : "",
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_MSCHAPV2 ? "MSCHAPv2 " : "",
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_EAP ? "EAP " : "",
	       clnt_res.auth_flags & L2TP_API_PPP_REQUIRE_NONE ? "NOAUTH " : "");

	printf("  compression options: %s%s%s%s%s%s%s%s%s%s\n", 
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_MPPC ? "MPPC " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_ACCOMP ? "ACCOMP " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_PCOMP ? "PCOMP " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_BSDCOMP ? "BSDCOMP " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_DEFLATE ? "DEFLATE " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_PREDICTOR1 ? "PREDICTOR1 " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_VJ ? "VJ " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_CCOMP_VJ ? "VJCCOMP " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_ASK_DEFLATE ? "ASK_DEFLATE " : "",
	       clnt_res.comp_flags & L2TP_API_PPP_COMP_ASK_BSDCOMP ? "ASK_BSDCOMP " : "");

	if (clnt_res.flags2 & L2TP_API_PPP_PROFILE_FLAG_MPPE) {
		printf("  mppe: %s\n", clnt_res.mppe ? "YES" : "NO");
	} else {
		printf("  mppe: <not set>\n");
	}

	printf("  max connect time: %d, max failure count: %d, idle timeout: %d\n",
	       clnt_res.max_connect_time, clnt_res.max_failure_count, clnt_res.idle_timeout);
	if (clnt_res.asyncmap != 0) {
		printf("  asyncmap: %#x\n", clnt_res.asyncmap);
	}
	printf("  multilink: %s\n", 
	       clnt_res.multilink ? "YES" : "NO");

	printf("  IP parameters:-\n");
	ip_to_string(&local_ip[0], clnt_res.local_ip_addr.s_addr);
	ip_to_string(&peer_ip[0], clnt_res.peer_ip_addr.s_addr);
	ip_to_string(&dns1[0], clnt_res.dns_addr_1.s_addr);
	ip_to_string(&dns2[0], clnt_res.dns_addr_2.s_addr);
	ip_to_string(&wins1[0], clnt_res.wins_addr_1.s_addr);
	ip_to_string(&wins2[0], clnt_res.wins_addr_2.s_addr);
	printf("    local address: %s, peer address: %s%s\n"
	       "    dns addresses: %s / %s\n"
	       "    wins addresses: %s / %s\n",
	       local_ip, peer_ip, 
	       clnt_res.use_as_default_route ? " [default route]" : "",
	       dns1, dns2, wins1, wins2);
	if (OPTSTRING_PTR(clnt_res.ip_pool_name) != NULL) {
		printf("    ip pool name: %s\n", OPTSTRING(clnt_res.ip_pool_name));
	}
	printf("    use radius: %s\n", clnt_res.use_radius ? "YES" : "NO");
	if (clnt_res.use_radius && OPTSTRING_PTR(clnt_res.radius_hint) != NULL) {
		printf("    radius hint: %s\n", OPTSTRING(clnt_res.radius_hint));
	}
	printf("  PAP parameters:-\n");
	printf("    max auth requests: %d, restart interval: %d, timeout: %d\n",
	       clnt_res.pap_max_auth_requests, clnt_res.pap_restart_interval, clnt_res.pap_timeout);
	printf("  CHAP parameters:-\n");
	printf("    interval: %d, max challenge: %d, restart: %d\n",
	       clnt_res.chap_interval, clnt_res.chap_max_challenge, clnt_res.chap_restart);
	printf("  LCP parameters:-\n");
	printf("    echo failure count: %d, echo interval: %d\n"
	       "    max config requests: %d, max config naks: %d\n"
	       "    max terminate requests: %d, retransmit interval: %d\n",
	       clnt_res.lcp_echo_failure_count, clnt_res.lcp_echo_interval,
	       clnt_res.lcp_max_config_requests, clnt_res.lcp_max_config_naks,
	       clnt_res.lcp_max_terminate_requests, clnt_res.lcp_retransmit_interval);
	printf("  IPCP parameters:-\n");
	printf("    max config requests: %d, max config naks: %d\n"
	       "    max terminate requests: %d, retransmit interval: %d\n",
	       clnt_res.ipcp_max_config_requests, clnt_res.ipcp_max_config_naks,
	       clnt_res.ipcp_max_terminate_requests, clnt_res.ipcp_retransmit_interval);
	printf("  use count: %d\n", clnt_res.use_count);
	printf("\n");

out:
	return result;
}

static int l2tp_act_ppp_profile_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_ppp_profile_list_msg_data clnt_res;
	struct l2tp_api_ppp_profile_list_entry *walk;
	int result;
	const char **profile_names;
	int index;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_ppp_profile_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.num_profiles > 0) {
		profile_names = calloc(clnt_res.num_profiles, sizeof(profile_names[0]));
		if (profile_names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(ENOMEM));
			goto out;
		}
	
		walk = clnt_res.profiles;
		for (index = 0; index < clnt_res.num_profiles; index++) {
			if ((walk == NULL) || (walk->profile_name[0] == '\0')) {
				break;
			}
			profile_names[index] = walk->profile_name;
			walk = walk->next;
		}	

		/* Sort the profile names */
		qsort(&profile_names[0], index, sizeof(profile_names[0]), l2tp_name_compare);

		for (index = 0; index < clnt_res.num_profiles; index++) {
			printf("\t%s\n", profile_names[index]);
		}

		free(profile_names);
	}

	result = 0;

out:
	return result;
}

/*****************************************************************************
 * Peer profiles
 *****************************************************************************/

typedef enum {
	L2TP_PEER_PROFILE_ARGID_PROFILE_NAME,
	L2TP_PEER_PROFILE_ARGID_PEER_IPADDR,
	L2TP_PEER_PROFILE_ARGID_PEER_PORT,
	L2TP_PEER_PROFILE_ARGID_LACLNS,
	L2TP_PEER_PROFILE_ARGID_TUNNEL_PROFILE,
	L2TP_PEER_PROFILE_ARGID_SESSION_PROFILE,
	L2TP_PEER_PROFILE_ARGID_PPP_PROFILE,
	L2TP_PEER_PROFILE_ARGID_NETMASK,
} l2tp_peer_profile_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_PEER_PROFILE_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_PEER_PROFILE_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

/* Paremeters for Create and Modify operations */
#define L2TP_PEER_MODIFY_ARGS 																\
	ARG(PEER_IPADDR,	"peer_ipaddr",		0,	ipaddr,	("IP address of peer")),							\
	ARG(PEER_PORT,		"peer_port",		0,	uint16,	("UDP port with which to connect to peer. Default=1701.")),			\
	ARG(NETMASK,		"netmask",		0,	ipaddr,	("IP netmask to be used when matching for peer_ipaddr. Default=255.255.255.255.")), \
	ARG(LACLNS,		"lac_lns",		0,	string,	("We can operate as a LAC or LNS or both.")),					\
	ARG(TUNNEL_PROFILE,	"tunnel_profile_name",	0,	string,	("Name of default Tunnel Profile. Default=\"default\"")),			\
	ARG(SESSION_PROFILE,	"session_profile_name",	0,	string,	("Name of default Session Profile. Default=\"default\"")),			\
	ARG(PPP_PROFILE,	"ppp_profile_name",	0,	string,	("Name of default Ppp Profile. Default=\"default\""))				\

static struct cli_arg_entry l2tp_args_peer_profile_create[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of peer profile")),							\
	L2TP_PEER_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_peer_profile_delete[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of peer profile")),							\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_peer_profile_modify[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of peer profile")),							\
	L2TP_PEER_MODIFY_ARGS,															\
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_peer_profile_show[] = {
	ARG(PROFILE_NAME,	"profile_name",		0,	string,	("Name of peer profile")),							\
	{ NULL, },
};

static int l2tp_parse_peer_profile_arg(l2tp_peer_profile_arg_ids_t arg_id, struct cli_node *arg, char *arg_value, struct l2tp_api_peer_profile_msg_data *msg)
{
	int result = -EINVAL;

	if (arg_value == NULL) {
		arg_value = empty_string;
	}

	switch (arg_id) {
	case L2TP_PEER_PROFILE_ARGID_PROFILE_NAME:
		msg->profile_name = strdup(arg_value);
		if (msg->profile_name == NULL) {
			result = -ENOMEM;
			goto out;
		}
		break;
	case L2TP_PEER_PROFILE_ARGID_TUNNEL_PROFILE:
		OPTSTRING(msg->default_tunnel_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->default_tunnel_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->default_tunnel_profile_name.valid = 1;
		msg->flags |= L2TP_API_PEER_PROFILE_FLAG_TUNNEL_PROFILE_NAME;
		break;
	case L2TP_PEER_PROFILE_ARGID_SESSION_PROFILE:
		OPTSTRING(msg->default_session_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->default_session_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->default_session_profile_name.valid = 1;
		msg->flags |= L2TP_API_PEER_PROFILE_FLAG_SESSION_PROFILE_NAME;
		break;
	case L2TP_PEER_PROFILE_ARGID_PPP_PROFILE:
		OPTSTRING(msg->default_ppp_profile_name) = strdup(arg_value);
		if (OPTSTRING(msg->default_ppp_profile_name) == NULL) {
			result = -ENOMEM;
			goto out;
		}
		msg->default_ppp_profile_name.valid = 1;
		msg->flags |= L2TP_API_PEER_PROFILE_FLAG_PPP_PROFILE_NAME;
		break;
	case L2TP_PEER_PROFILE_ARGID_PEER_IPADDR:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_addr, msg->flags, L2TP_API_PEER_PROFILE_FLAG_PEER_IPADDR);
		break;
	case L2TP_PEER_PROFILE_ARGID_PEER_PORT:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->peer_port, msg->flags, L2TP_API_PEER_PROFILE_FLAG_PEER_PORT);
		break;
	case L2TP_PEER_PROFILE_ARGID_LACLNS:
		if (strcasecmp(arg_value, "laclns") == 0) {
			msg->we_can_be_lac = 1;
			msg->we_can_be_lns = 1;
		} else if (strcasecmp(arg_value, "lac") == 0) {
			msg->we_can_be_lac = 1;
			msg->we_can_be_lns = 0;
		} else if (strcasecmp(arg_value, "lns") == 0) {
			msg->we_can_be_lac = 0;
			msg->we_can_be_lns = 1;
		} else {
			fprintf(stderr, "Bad authmode %s: expecting laclns|lac|lns\n", arg_value);
			result = -EINVAL;
			goto out;
		} 
		msg->flags |= L2TP_API_PEER_PROFILE_FLAG_LACLNS;
		break;
	case L2TP_PEER_PROFILE_ARGID_NETMASK:
		L2TP_ACT_PARSE_ARG(arg, arg_value, msg->netmask, msg->flags, L2TP_API_PEER_PROFILE_FLAG_NETMASK);
		break;
	}

	result = 0;

out:
	return result;
}

static int l2tp_act_peer_profile_create(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_peer_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_peer_profile_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_peer_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_peer_profile_create_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Created peer profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_peer_profile_delete(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_peer_profile_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_PEER_PROFILE_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_peer_profile_delete_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Deleted peer profile %s\n", profile_name);
	}

out:
	return result;
}

static int l2tp_act_peer_profile_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_peer_profile_msg_data msg = { 0, };
	L2TP_ACT_DECLARATIONS(40, l2tp_peer_profile_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		result = l2tp_parse_peer_profile_arg(arg_id, args[arg], arg_values[arg], &msg);
		if (result < 0) {
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_peer_profile_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified peer profile %s\n", msg.profile_name);
	}

out:
	return result;
}

static int l2tp_act_peer_profile_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *profile_name = NULL;
	char port[16];
	struct in_addr ip_addr;
	L2TP_ACT_DECLARATIONS(4, l2tp_peer_profile_arg_ids_t, struct l2tp_api_peer_profile_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_PEER_PROFILE_ARGID_PROFILE_NAME:
			profile_name = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (profile_name == NULL) {
		fprintf(stderr, "Required profile_name argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_peer_profile_get_1(profile_name, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	ip_addr.s_addr = clnt_res.peer_addr.s_addr;
	sprintf(&port[0], "%d", clnt_res.peer_port);
	printf("Peer profile %s:-\n"
	       "  address: %s, port %s\n",
	       clnt_res.profile_name, 
	       ip_addr.s_addr == INADDR_ANY ? "ANY" : inet_ntoa(ip_addr), 
	       clnt_res.peer_port == 0 ? "default" : port);
	if (clnt_res.netmask.s_addr != INADDR_BROADCAST) {
		ip_addr.s_addr = clnt_res.netmask.s_addr;
		printf("  netmask: %s\n", inet_ntoa(ip_addr));
	}
	printf("  mode %s/%s\n",
	       clnt_res.we_can_be_lac ? "LAC" : "-",
	       clnt_res.we_can_be_lns ? "LNS" : "-");
	printf("  default tunnel profile: %s\n"
	       "  default session profile: %s\n"
	       "  default ppp profile: %s\n",
	       OPTSTRING_PTR(clnt_res.default_tunnel_profile_name) ? OPTSTRING(clnt_res.default_tunnel_profile_name) : L2TP_API_TUNNEL_PROFILE_DEFAULT_PROFILE_NAME,
	       OPTSTRING_PTR(clnt_res.default_session_profile_name) ? OPTSTRING(clnt_res.default_session_profile_name) : L2TP_API_SESSION_PROFILE_DEFAULT_PROFILE_NAME,
	       OPTSTRING_PTR(clnt_res.default_ppp_profile_name) ? OPTSTRING(clnt_res.default_ppp_profile_name) : L2TP_API_PPP_PROFILE_DEFAULT_PROFILE_NAME);
	printf("  use count: %d\n", clnt_res.use_count);
	printf("\n");

out:
	return result;
}

static int l2tp_act_peer_profile_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_peer_profile_list_msg_data clnt_res;
	struct l2tp_api_peer_profile_list_entry *walk;
	int result;
	const char **profile_names;
	int index;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_peer_profile_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	if (clnt_res.num_profiles > 0) {
		profile_names = calloc(clnt_res.num_profiles, sizeof(profile_names[0]));
		if (profile_names == NULL) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(ENOMEM));
			goto out;
		}
	
		walk = clnt_res.profiles;
		for (index = 0; index < clnt_res.num_profiles; index++) {
			if ((walk == NULL) || (walk->profile_name[0] == '\0')) {
				break;
			}
			profile_names[index] = walk->profile_name;
			walk = walk->next;
		}	

		/* Sort the profile names */
		qsort(&profile_names[0], index, sizeof(profile_names[0]), l2tp_name_compare);

		for (index = 0; index < clnt_res.num_profiles; index++) {
			printf("\t%s\n", profile_names[index]);
		}

		free(profile_names);
	}

	result = 0;

out:
	return result;
}

/*****************************************************************************
 * Peers
 *****************************************************************************/

typedef enum {
	L2TP_PEER_ARGID_PEER_IPADDR,
	L2TP_PEER_ARGID_LOCAL_IPADDR,
} l2tp_peer_arg_ids_t;
 
#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_PEER_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_PEER_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

static struct cli_arg_entry l2tp_args_peer_show[] = {
	ARG(PEER_IPADDR,	"peer_ipaddr",		0,	ipaddr,	("IP address of peer")),							\
	ARG(LOCAL_IPADDR,	"local_ipaddr",		0,	ipaddr,	("IP address of local interface")),						\
	{ NULL, },
};

static int l2tp_act_peer_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_ip_addr peer_addr = { INADDR_ANY, };
	struct l2tp_api_ip_addr local_addr = { INADDR_ANY, };
	struct in_addr ip_addr;

	int flags = 0;
	L2TP_ACT_DECLARATIONS(4, l2tp_peer_arg_ids_t, struct l2tp_api_peer_msg_data);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_PEER_ARGID_PEER_IPADDR:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], peer_addr, flags, 0);
			break;
		case L2TP_PEER_ARGID_LOCAL_IPADDR:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], local_addr, flags, 0);
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (peer_addr.s_addr == INADDR_ANY) {
		fprintf(stderr, "Required peer_ipaddr argument missing\n");
		result = -EINVAL;
		goto out;
	}

	memset(&clnt_res, 0, sizeof(clnt_res));
	result = l2tp_peer_get_1(local_addr, peer_addr, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	if (clnt_res.result_code < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result_code));
		result = clnt_res.result_code;
		goto out;
	}

	ip_addr.s_addr = clnt_res.peer_addr.s_addr;
	printf("Peer %s, ", inet_ntoa(ip_addr));
	ip_addr.s_addr = clnt_res.local_addr.s_addr;
	printf("local %s:-\n", ip_addr.s_addr == INADDR_ANY ? "ANY" : inet_ntoa(ip_addr));
	printf("  number active tunnels: %d\n", clnt_res.num_tunnels);

out:
	return result;
}

static int l2tp_act_peer_list(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_peer_list_msg_data clnt_res;
	struct l2tp_api_peer_list_entry *walk;
	int result;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_peer_list_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res.result));
		result = clnt_res.result;
		goto out;
	}

	walk = clnt_res.peers;
	if (walk->peer_addr.s_addr != INADDR_ANY) {
		printf("%-16s %-16s\n", "Local", "Remote"); 
	}
	while ((walk != NULL) && (walk->peer_addr.s_addr != INADDR_ANY)) {
		struct in_addr ip_addr;
		ip_addr.s_addr = walk->local_addr.s_addr;
		printf("%-16s ", 
		       ip_addr.s_addr == INADDR_ANY ? "ANY" : inet_ntoa(ip_addr));
		ip_addr.s_addr = walk->peer_addr.s_addr;
		printf("%-16s\n", 
		       ip_addr.s_addr == INADDR_ANY ? "ANY" : inet_ntoa(ip_addr));
		walk = walk->next;
	}	

	result = 0;

out:
	return result;
}

/*****************************************************************************
 * config save/restore
 *****************************************************************************/

#define Y_OR_N(_var) (_var) ? "yes" : "no"
#define ON_OR_OFF(_var) (_var) ? "on" : "off"
#define OFF_OR_ON(_var) (_var) ? "off" : "on"

#undef ARG
#undef FLG

#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_CONFIG_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#define FLG(id, name, doc) \
	{ name, { L2TP_CONFIG_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	L2TP_CONFIG_ARGID_FILENAME,
} l2tp_config_arg_ids_t;

static struct cli_arg_entry l2tp_args_config[] = {
	ARG(FILENAME, 		"file", 		0, 	string,	"Filename for save/restore operation."),
	{ NULL, },
};

static void l2tp_config_dump_system(FILE *file, struct l2tp_api_system_msg_data *cfg)
{
	if (cfg->config.flags & (L2TP_API_CONFIG_FLAG_TRACE_FLAGS |
				 L2TP_API_CONFIG_FLAG_MAX_TUNNELS |
				 L2TP_API_CONFIG_FLAG_DRAIN_TUNNELS |
				 L2TP_API_CONFIG_FLAG_MAX_SESSIONS |
				 L2TP_API_CONFIG_FLAG_TUNNEL_ESTABLISH_TIMEOUT |
				 L2TP_API_CONFIG_FLAG_SESSION_ESTABLISH_TIMEOUT |
				 L2TP_API_CONFIG_FLAG_DENY_LOCAL_TUNNEL_CREATES |
				 L2TP_API_CONFIG_FLAG_DENY_REMOTE_TUNNEL_CREATES)) {

		fprintf(file, "system modify \\\n");

		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_TRACE_FLAGS) {
			fprintf(file, "trace_flags=%u \\\n", cfg->config.trace_flags);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_MAX_TUNNELS) {
			fprintf(file, "max_tunnels=%d \\\n", cfg->config.max_tunnels);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_DRAIN_TUNNELS) {
			fprintf(file, "drain_tunnels=%s \\\n", Y_OR_N(cfg->config.drain_tunnels));
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_MAX_SESSIONS) {
			fprintf(file, "max_sessions=%d \\\n", cfg->config.max_sessions);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_TUNNEL_ESTABLISH_TIMEOUT) {
			fprintf(file, "tunnel_establish_timeout=%d \\\n", cfg->config.tunnel_establish_timeout);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_SESSION_ESTABLISH_TIMEOUT) {
			fprintf(file, "session_establish_timeout=%d \\\n", cfg->config.session_establish_timeout);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_DENY_LOCAL_TUNNEL_CREATES) {
			fprintf(file, "deny_local_tunnel_creates=%d \\\n", cfg->config.deny_local_tunnel_creates);
		}
		if (cfg->config.flags & L2TP_API_CONFIG_FLAG_DENY_REMOTE_TUNNEL_CREATES) {
			fprintf(file, "deny_remote_tunnel_creates=%d \\\n", cfg->config.deny_remote_tunnel_creates);
		}
	}
}

static void l2tp_config_dump_peer_profile(FILE *file, struct l2tp_api_peer_profile_msg_data *cfg)
{
 	if (strcmp(cfg->profile_name, L2TP_API_PEER_PROFILE_DEFAULT_PROFILE_NAME) != 0) {
 		fprintf(file, "peer profile create profile_name=%s\n", cfg->profile_name);
 	}
 	if (cfg->flags & (L2TP_API_PEER_PROFILE_FLAG_LACLNS |
 			  L2TP_API_PEER_PROFILE_FLAG_TUNNEL_PROFILE_NAME |
 			  L2TP_API_PEER_PROFILE_FLAG_SESSION_PROFILE_NAME |
 			  L2TP_API_PEER_PROFILE_FLAG_PPP_PROFILE_NAME |
 			  L2TP_API_PEER_PROFILE_FLAG_PEER_IPADDR |
 			  L2TP_API_PEER_PROFILE_FLAG_PEER_PORT |
 			  L2TP_API_PEER_PROFILE_FLAG_NETMASK)) {
 
 		fprintf(file, "peer profile modify profile_name=%s \\\n", cfg->profile_name);
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_LACLNS) {
			fprintf(file, "\tlac_lns=%s \\\n",
				(cfg->we_can_be_lac && cfg->we_can_be_lns) ? "laclns" :
				(!cfg->we_can_be_lac && cfg->we_can_be_lns) ? "lns" :
				(cfg->we_can_be_lac && !cfg->we_can_be_lns) ? "lac" : "??");
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_TUNNEL_PROFILE_NAME) {
			fprintf(file, "\ttunnel_profile_name=%s \\\n", OPTSTRING_PTR(cfg->default_tunnel_profile_name));
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_SESSION_PROFILE_NAME) {
			fprintf(file, "\tsession_profile_name=%s \\\n", OPTSTRING_PTR(cfg->default_session_profile_name));
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_PPP_PROFILE_NAME) {
			fprintf(file, "\tppp_profile_name=%s \\\n", OPTSTRING_PTR(cfg->default_ppp_profile_name));
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_PEER_IPADDR) {
			struct in_addr ip;
			ip.s_addr = cfg->peer_addr.s_addr;
			fprintf(file, "\tpeer_ipaddr=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_PEER_PORT) {
			fprintf(file, "\tpeer_port=%hu \\\n", cfg->peer_port);
		}
		if (cfg->flags & L2TP_API_PEER_PROFILE_FLAG_NETMASK) {
			struct in_addr addr;
			addr.s_addr = cfg->netmask.s_addr;
			fprintf(file, "\tnetmask=%s \\\n", inet_ntoa(addr));
		}
		fprintf(file, "\n");
	}
}

static void l2tp_config_dump_tunnel_profile(FILE *file, struct l2tp_api_tunnel_profile_msg_data *cfg)
{
 	if (strcmp(cfg->profile_name, L2TP_API_TUNNEL_PROFILE_DEFAULT_PROFILE_NAME) != 0) {
 		fprintf(file, "tunnel profile create profile_name=%s\n", cfg->profile_name);
 	}
 	if (cfg->flags & (L2TP_API_TUNNEL_PROFILE_FLAG_HIDE_AVPS |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_AUTH_MODE |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_FRAMING_CAP |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_BEARER_CAP |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_USE_TIEBREAKER |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_HELLO_TIMEOUT |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_MAX_RETRIES |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_RX_WINDOW_SIZE |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_TX_WINDOW_SIZE |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_RETRY_TIMEOUT |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_IDLE_TIMEOUT |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_SECRET |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_ALLOW_PPP_PROXY |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_TRACE_FLAGS |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_USE_UDP_CHECKSUMS |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_HOST_NAME |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_MAX_SESSIONS |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_OUR_ADDR |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_PEER_ADDR |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_OUR_UDP_PORT |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_PEER_UDP_PORT |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_PEER_PROFILE_NAME |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_SESSION_PROFILE_NAME |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_PPP_PROFILE_NAME |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_DO_PMTU_DISCOVERY |
 			  L2TP_API_TUNNEL_PROFILE_FLAG_MTU)) {
 
 		fprintf(file, "tunnel profile modify profile_name=%s \\\n", cfg->profile_name);
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_HIDE_AVPS) {
			fprintf(file, "\thide_avps=%s \\\n", Y_OR_N(cfg->hide_avps));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_AUTH_MODE) {
			fprintf(file, "\tauth_mode=%s \\\n", 
				(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_NONE) ? "none" :
				(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_SIMPLE) ? "simple" :
				(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE) ? "challenge" : "??");
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_FRAMING_CAP) {
			fprintf(file, "\tframing_cap=%s \\\n", 
				(!cfg->framing_cap_sync && !cfg->framing_cap_async) ? "none" :
				(cfg->framing_cap_sync && cfg->framing_cap_async) ? "any" :
				(cfg->framing_cap_sync && !cfg->framing_cap_async) ? "sync" :
				(!cfg->framing_cap_sync && cfg->framing_cap_async) ? "async" : "??");
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_BEARER_CAP) {
			fprintf(file, "\tbearer_cap=%s \\\n", 
				(!cfg->bearer_cap_digital && !cfg->bearer_cap_analog) ? "none" :
				(cfg->bearer_cap_digital && cfg->bearer_cap_analog) ? "any" :
				(cfg->bearer_cap_digital && !cfg->bearer_cap_analog) ? "digital" :
				(!cfg->bearer_cap_digital && cfg->bearer_cap_analog) ? "analog" : "??");
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_USE_TIEBREAKER) {
			fprintf(file, "\tuse_tiebreaker=%s \\\n", Y_OR_N(cfg->use_tiebreaker));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_HELLO_TIMEOUT) {
			fprintf(file, "\thello_timeout=%d \\\n", cfg->hello_timeout);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_MAX_RETRIES) {
			fprintf(file, "\tmax_retries=%d \\\n", cfg->max_retries);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_RX_WINDOW_SIZE) {
			fprintf(file, "\trx_window_size=%d \\\n", cfg->rx_window_size);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_TX_WINDOW_SIZE) {
			fprintf(file, "\ttx_window_size=%d \\\n", cfg->tx_window_size);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_RETRY_TIMEOUT) {
			fprintf(file, "\tretry_timeout=%d \\\n", cfg->retry_timeout);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_IDLE_TIMEOUT) {
			fprintf(file, "\tidle_timeout=%d \\\n", cfg->idle_timeout);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_SECRET) {
			fprintf(file, "\tsecret=%s \\\n", OPTSTRING_PTR(cfg->secret));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_ALLOW_PPP_PROXY) {
			fprintf(file, "\tallow_ppp_proxy=%s \\\n", Y_OR_N(cfg->allow_ppp_proxy));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_TRACE_FLAGS) {
			fprintf(file, "\ttrace_flags=%u \\\n", cfg->trace_flags);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_USE_UDP_CHECKSUMS) {
			fprintf(file, "\tuse_udp_checksums=%s \\\n", Y_OR_N(cfg->use_udp_checksums));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_HOST_NAME) {
			fprintf(file, "\thost_name=%s \\\n", OPTSTRING_PTR(cfg->host_name));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_MAX_SESSIONS) {
			fprintf(file, "\tmax_sessions=%d \\\n", cfg->max_sessions);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_OUR_ADDR) {
			struct in_addr ip;
			ip.s_addr = cfg->our_addr.s_addr;
			fprintf(file, "\tsrc_ipaddr=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_PEER_ADDR) {
			struct in_addr ip;
			ip.s_addr = cfg->peer_addr.s_addr;
			fprintf(file, "\tdest_ipaddr=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_OUR_UDP_PORT) {
			fprintf(file, "\tour_udp_port=%hu \\\n", cfg->our_udp_port);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_PEER_UDP_PORT) {
			fprintf(file, "\tpeer_udp_port=%hu \\\n", cfg->peer_udp_port);
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_PEER_PROFILE_NAME) {
			fprintf(file, "\tpeer_profile_name=%s \\\n", OPTSTRING_PTR(cfg->peer_profile_name));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_SESSION_PROFILE_NAME) {
			fprintf(file, "\tsession_profile_name=%s \\\n", OPTSTRING_PTR(cfg->session_profile_name));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_PPP_PROFILE_NAME) {
			fprintf(file, "\tppp_profile_name=%s \\\n", OPTSTRING_PTR(cfg->ppp_profile_name));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_DO_PMTU_DISCOVERY) {
			fprintf(file, "\tdo_pmtu_discovery=%s \\\n", Y_OR_N(cfg->do_pmtu_discovery));
		}
		if (cfg->flags & L2TP_API_TUNNEL_PROFILE_FLAG_MTU) {
			fprintf(file, "\tmtu=%d \\\n", cfg->mtu);
		}
		fprintf(file, "\n");
	}
}

static void l2tp_config_dump_session_profile(FILE *file, struct l2tp_api_session_profile_msg_data *cfg)
{
 	if (strcmp(cfg->profile_name, L2TP_API_SESSION_PROFILE_DEFAULT_PROFILE_NAME) != 0) {
 		fprintf(file, "session profile create profile_name=%s\n", cfg->profile_name);
 	}
 	
 	if (cfg->flags & (L2TP_API_SESSION_PROFILE_FLAG_TRACE_FLAGS |
 			  L2TP_API_SESSION_PROFILE_FLAG_SEQUENCING_REQUIRED |
 			  L2TP_API_SESSION_PROFILE_FLAG_PPP_PROFILE_NAME |
 			  L2TP_API_SESSION_PROFILE_FLAG_SESSION_TYPE |
 			  L2TP_API_SESSION_PROFILE_FLAG_PRIV_GROUP_ID |
 			  L2TP_API_SESSION_PROFILE_FLAG_FRAMING_TYPE |
 			  L2TP_API_SESSION_PROFILE_FLAG_BEARER_TYPE |
 			  L2TP_API_SESSION_PROFILE_FLAG_MINIMUM_BPS |
 			  L2TP_API_SESSION_PROFILE_FLAG_MAXIMUM_BPS |
 			  L2TP_API_SESSION_PROFILE_FLAG_CONNECT_SPEED |
 			  L2TP_API_SESSION_PROFILE_FLAG_USE_PPP_PROXY |
 			  L2TP_API_SESSION_PROFILE_FLAG_USE_SEQUENCE_NUMBERS |
 			  L2TP_API_SESSION_PROFILE_FLAG_REORDER_TIMEOUT)) {
 
 		fprintf(file, "session profile modify profile_name=%s \\\n", cfg->profile_name);
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_TRACE_FLAGS) {
			fprintf(file, "\ttrace_flags=%u \\\n", cfg->trace_flags);
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_SEQUENCING_REQUIRED) {
			fprintf(file, "\tsequencing_required=%s \\\n", Y_OR_N(cfg->sequencing_required));
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_PPP_PROFILE_NAME) {
			fprintf(file, "\tppp_profile_name=%s \\\n", OPTSTRING_PTR(cfg->ppp_profile_name));
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_SESSION_TYPE) {
			fprintf(file, "\tsession_type=%s \\\n", 
				(cfg->session_type == L2TP_API_SESSION_TYPE_LAIC) ? "laic" : 
				(cfg->session_type == L2TP_API_SESSION_TYPE_LAOC) ? "laoc" : 
				(cfg->session_type == L2TP_API_SESSION_TYPE_LNIC) ? "lnic" : 
				(cfg->session_type == L2TP_API_SESSION_TYPE_LNOC) ? "lnoc" : "??");
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_PRIV_GROUP_ID) {
			fprintf(file, "\tpriv_group_id=%s \\\n", OPTSTRING_PTR(cfg->priv_group_id));
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_FRAMING_TYPE) {
			fprintf(file, "\tframing_type=%s \\\n", 
				(!cfg->framing_type_sync && !cfg->framing_type_async) ? "none" :
				(cfg->framing_type_sync && cfg->framing_type_async) ? "any" :
				(cfg->framing_type_sync && !cfg->framing_type_async) ? "sync" :
				(!cfg->framing_type_sync && cfg->framing_type_async) ? "async" : "??");
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_BEARER_TYPE) {
			fprintf(file, "\tbearer_type=%s \\\n", 
				(!cfg->bearer_type_digital && !cfg->bearer_type_analog) ? "none" :
				(cfg->bearer_type_digital && cfg->bearer_type_analog) ? "any" :
				(cfg->bearer_type_digital && !cfg->bearer_type_analog) ? "digital" :
				(!cfg->bearer_type_digital && cfg->bearer_type_analog) ? "analog" : "??");
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_MINIMUM_BPS) {
			fprintf(file, "\tminimum_bps=%d \\\n", cfg->minimum_bps);
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_MAXIMUM_BPS) {
			fprintf(file, "\tmaximum_bps=%d \\\n", cfg->maximum_bps);
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_CONNECT_SPEED) {
			fprintf(file, "\tconnect_speed=%d:%d \\\n", cfg->rx_connect_speed, cfg->tx_connect_speed);
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_USE_PPP_PROXY) {
			fprintf(file, "\tuse_ppp_proxy=%s \\\n", Y_OR_N(cfg->use_ppp_proxy));
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_USE_SEQUENCE_NUMBERS) {
			fprintf(file, "\tuse_sequence_numbers=%s \\\n", Y_OR_N(cfg->use_sequence_numbers));
		}
		if (cfg->flags & L2TP_API_SESSION_PROFILE_FLAG_REORDER_TIMEOUT) {
			fprintf(file, "\treorder_timeout=%d \\\n", cfg->reorder_timeout);
		}
		fprintf(file, "\n");
	}
}

static void l2tp_config_dump_ppp_profile(FILE *file, struct l2tp_api_ppp_profile_msg_data *cfg)
{
 	if (strcmp(cfg->profile_name, L2TP_API_PPP_PROFILE_DEFAULT_PROFILE_NAME) != 0) {
 		fprintf(file, "ppp profile create profile_name=%s\n", cfg->profile_name);
 	}
 
 	/* Unfortunately we have 2 flags variables to check because there are so 
 	 * many arguments... 
 	 */
 	if ((cfg->flags & (L2TP_API_PPP_PROFILE_FLAG_TRACE_FLAGS |
 			   L2TP_API_PPP_PROFILE_FLAG_ASYNCMAP |
 			   L2TP_API_PPP_PROFILE_FLAG_MRU |
 			   L2TP_API_PPP_PROFILE_FLAG_MTU |
 			   L2TP_API_PPP_PROFILE_FLAG_USE_RADIUS |
 			   L2TP_API_PPP_PROFILE_FLAG_RADIUS_HINT |
 			   L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS |
 			   L2TP_API_PPP_PROFILE_FLAG_SYNC_MODE |
 			   L2TP_API_PPP_PROFILE_FLAG_CHAP_INTERVAL |
 			   L2TP_API_PPP_PROFILE_FLAG_CHAP_MAX_CHALLENGE |
 			   L2TP_API_PPP_PROFILE_FLAG_CHAP_RESTART |
 			   L2TP_API_PPP_PROFILE_FLAG_PAP_MAX_AUTH_REQUESTS |
 			   L2TP_API_PPP_PROFILE_FLAG_PAP_RESTART_INTERVAL |
 			   L2TP_API_PPP_PROFILE_FLAG_PAP_TIMEOUT |
 			   L2TP_API_PPP_PROFILE_FLAG_IDLE_TIMEOUT |
 			   L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_REQUESTS |
 			   L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_NAKS |
 			   L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_TERMINATE_REQUESTS |
 			   L2TP_API_PPP_PROFILE_FLAG_IPCP_RETRANSMIT_INTERVAL |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_FAILURE_COUNT |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_INTERVAL |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_REQUESTS |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_NAKS |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_TERMINATE_REQUESTS |
 			   L2TP_API_PPP_PROFILE_FLAG_LCP_RETRANSMIT_INTERVAL |
 			   L2TP_API_PPP_PROFILE_FLAG_MAX_CONNECT_TIME |
 			   L2TP_API_PPP_PROFILE_FLAG_MAX_FAILURE_COUNT)) ||
 	    (cfg->flags2 & (L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_1 |
 			    L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_2 |
 			    L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_1 |
 			    L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_2 |
 			    L2TP_API_PPP_PROFILE_FLAG_LOCAL_IP_ADDR |
 			    L2TP_API_PPP_PROFILE_FLAG_PEER_IP_ADDR |
 			    L2TP_API_PPP_PROFILE_FLAG_IP_POOL_NAME |
 			    L2TP_API_PPP_PROFILE_FLAG_USE_AS_DEFAULT_ROUTE |
 			    L2TP_API_PPP_PROFILE_FLAG_MULTILINK |
 			    L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS))) {
 
 		fprintf(file, "ppp profile modify profile_name=%s \\\n", cfg->profile_name);

		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_TRACE_FLAGS) {
			fprintf(file, "\ttrace_flags=%u \\\n", cfg->trace_flags);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_ASYNCMAP) {
			fprintf(file, "\tasyncmap=%u \\\n", cfg->asyncmap);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_MRU) {
			fprintf(file, "\tmru=%hu \\\n", cfg->mru);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_MTU) {
			fprintf(file, "\tmtu=%hu \\\n", cfg->mtu);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_USE_RADIUS) {
			fprintf(file, "\tuse_radius=%s \\\n", Y_OR_N(cfg->use_radius));
			if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_RADIUS_HINT) {
				fprintf(file, "\tradius_hint=%s \\\n", OPTSTRING_PTR(cfg->radius_hint));
			}
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_AUTH_FLAGS) {
			fprintf(file, "\tauth_pap=%s \\\n", OFF_OR_ON(cfg->auth_flags & L2TP_API_PPP_AUTH_REFUSE_PAP));
			fprintf(file, "\tauth_chap=%s \\\n", OFF_OR_ON(cfg->auth_flags & L2TP_API_PPP_AUTH_REFUSE_CHAP));
			fprintf(file, "\tauth_mschapv1=%s \\\n", OFF_OR_ON(cfg->auth_flags & L2TP_API_PPP_AUTH_REFUSE_MSCHAP));
			fprintf(file, "\tauth_mschapv2=%s \\\n", OFF_OR_ON(cfg->auth_flags & L2TP_API_PPP_AUTH_REFUSE_MSCHAPV2));
			fprintf(file, "\tauth_eap=%s \\\n", OFF_OR_ON(cfg->auth_flags & L2TP_API_PPP_AUTH_REFUSE_EAP));

			fprintf(file, "\treq_pap=%s \\\n", ON_OR_OFF(cfg->auth_flags & L2TP_API_PPP_REQUIRE_PAP));
			fprintf(file, "\treq_chap=%s \\\n", ON_OR_OFF(cfg->auth_flags & L2TP_API_PPP_REQUIRE_CHAP));
			fprintf(file, "\treq_mschapv1=%s \\\n", ON_OR_OFF(cfg->auth_flags & L2TP_API_PPP_REQUIRE_MSCHAP));
			fprintf(file, "\treq_mschapv2=%s \\\n", ON_OR_OFF(cfg->auth_flags & L2TP_API_PPP_REQUIRE_MSCHAPV2));
			fprintf(file, "\treq_eap=%s \\\n", ON_OR_OFF(cfg->auth_flags & L2TP_API_PPP_REQUIRE_EAP));

			fprintf(file, "\treq_none=%s \\\n", Y_OR_N(cfg->auth_flags & L2TP_API_PPP_REQUIRE_NONE));
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_SYNC_MODE) {
			fprintf(file, "\tsync_mode=%s \\\n", 
				cfg->sync_mode == L2TP_API_PPP_SYNCMODE_SYNC ? "sync" :
				cfg->sync_mode == L2TP_API_PPP_SYNCMODE_ASYNC ? "async" :
				cfg->sync_mode == L2TP_API_PPP_SYNCMODE_SYNC_ASYNC ? "any" : "??");
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_CHAP_INTERVAL) {
			fprintf(file, "\tchap_interval=%d \\\n", cfg->chap_interval);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_CHAP_MAX_CHALLENGE) {
			fprintf(file, "\tchap_max_challenge=%d \\\n", cfg->chap_max_challenge);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_CHAP_RESTART) {
			fprintf(file, "\tchap_restart=%d \\\n", cfg->chap_restart);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_PAP_MAX_AUTH_REQUESTS) {
			fprintf(file, "\tpap_max_auth_requests=%d \\\n", cfg->pap_max_auth_requests);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_PAP_RESTART_INTERVAL) {
			fprintf(file, "\tpap_restart_interval=%d \\\n", cfg->pap_restart_interval);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_PAP_TIMEOUT) {
			fprintf(file, "\tpap_timeout=%d \\\n", cfg->pap_timeout);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_IDLE_TIMEOUT) {
			fprintf(file, "\tidle_timeout=%d \\\n", cfg->idle_timeout);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_REQUESTS) {
			fprintf(file, "\tipcp_max_config_requests=%d \\\n", cfg->ipcp_max_config_requests);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_CONFIG_NAKS) {
			fprintf(file, "\tipcp_max_config_naks=%d \\\n", cfg->ipcp_max_config_naks);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_IPCP_MAX_TERMINATE_REQUESTS) {
			fprintf(file, "\tipcp_max_terminate_requests=%d \\\n", cfg->ipcp_max_terminate_requests);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_IPCP_RETRANSMIT_INTERVAL) {
			fprintf(file, "\tipcp_retransmit_interval=%d \\\n", cfg->ipcp_retransmit_interval);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_FAILURE_COUNT) {
			fprintf(file, "\tlcp_echo_failure_count=%d \\\n", cfg->lcp_echo_failure_count);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_ECHO_INTERVAL) {
			fprintf(file, "\tlcp_echo_interval=%d \\\n", cfg->lcp_echo_interval);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_REQUESTS) {
			fprintf(file, "\tlcp_max_config_requests=%d \\\n", cfg->lcp_max_config_requests);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_CONFIG_NAKS) {
			fprintf(file, "\tlcp_max_config_naks=%d \\\n", cfg->lcp_max_config_naks);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_MAX_TERMINATE_REQUESTS) {
			fprintf(file, "\tlcp_max_terminate_requests=%d \\\n", cfg->lcp_max_terminate_requests);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_LCP_RETRANSMIT_INTERVAL) {
			fprintf(file, "\tlcp_retransmit_interval=%d \\\n", cfg->lcp_retransmit_interval);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_MAX_CONNECT_TIME) {
			fprintf(file, "\tmax_connect_time=%d \\\n", cfg->max_connect_time);
		}
		if (cfg->flags & L2TP_API_PPP_PROFILE_FLAG_MAX_FAILURE_COUNT) {
			fprintf(file, "\tmax_failure_count=%d \\\n", cfg->max_failure_count);
		}

		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_1) {
			struct in_addr ip;
			ip.s_addr = cfg->dns_addr_1.s_addr;
			fprintf(file, "\tdns_ipaddr_pri=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_2) {
			struct in_addr ip;
			ip.s_addr = cfg->dns_addr_2.s_addr;
			fprintf(file, "\tdns_ipaddr_sec=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_1) {
			struct in_addr ip;
			ip.s_addr = cfg->wins_addr_1.s_addr;
			fprintf(file, "\twins_ipaddr_pri=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_2) {
			struct in_addr ip;
			ip.s_addr = cfg->wins_addr_2.s_addr;
			fprintf(file, "\twins_ipaddr_sec=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_LOCAL_IP_ADDR) {
			struct in_addr ip;
			ip.s_addr = cfg->local_ip_addr.s_addr;
			fprintf(file, "\tlocal_ipaddr=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_PEER_IP_ADDR) {
			struct in_addr ip;
			ip.s_addr = cfg->peer_ip_addr.s_addr;
			fprintf(file, "\tremote_ipaddr=%s \\\n", inet_ntoa(ip));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_IP_POOL_NAME) {
			fprintf(file, "\tip_pool_name=%s \\\n", OPTSTRING_PTR(cfg->ip_pool_name));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_USE_AS_DEFAULT_ROUTE) {
			fprintf(file, "\tdefault_route=%s \\\n", Y_OR_N(cfg->use_as_default_route));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_MULTILINK) {
			fprintf(file, "\tmultilink=%s \\\n", Y_OR_N(cfg->multilink));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_MPPE) {
			fprintf(file, "\tmppe=%s \\\n", Y_OR_N(cfg->mppe));
		}
		if (cfg->flags2 & L2TP_API_PPP_PROFILE_FLAG_COMP_FLAGS) {
			fprintf(file, "\tcomp_mppc=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_MPPC));
			fprintf(file, "\tcomp_accomp=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_ACCOMP));
			fprintf(file, "\tcomp_pcomp=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_PCOMP));
			fprintf(file, "\tcomp_bsdcomp=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_BSDCOMP));
			fprintf(file, "\tcomp_deflate=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_DEFLATE));
			fprintf(file, "\tcomp_predictor1=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_PREDICTOR1));
			fprintf(file, "\tcomp_vj=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_VJ));
			fprintf(file, "\tcomp_ccomp_vj=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_CCOMP_VJ));
			fprintf(file, "\tcomp_ask_deflate=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_ASK_DEFLATE));
			fprintf(file, "\tcomp_ask_bsdcomp=%s \\\n", ON_OR_OFF(cfg->comp_flags & L2TP_API_PPP_COMP_ASK_BSDCOMP));
		}
		fprintf(file, "\n");
	}
}

struct l2tp_config_tunnel_map {
	char *tunnel_name;
	uint16_t tunnel_id;
	struct l2tp_config_tunnel_map *next;
};

static struct l2tp_config_tunnel_map *l2tp_config_tunnel_map = NULL;

static int l2tp_config_tunnel_map_add(char *tunnel_name, uint16_t tunnel_id)
{
	struct l2tp_config_tunnel_map *entry;
	static struct l2tp_config_tunnel_map *tail = NULL;

	entry = calloc(1, sizeof(*entry));
	if (entry == NULL) {
		return -ENOMEM;
	}

	if (tunnel_name != NULL) {
		entry->tunnel_name = strdup(tunnel_name);
		if (entry->tunnel_name == NULL) {
			free(entry);
			return -ENOMEM;
		}
	}
	entry->tunnel_id = tunnel_id;

	if (l2tp_config_tunnel_map == NULL) {
		l2tp_config_tunnel_map = entry;
		tail = entry;
	} else {
		tail->next = entry;
		tail = entry;
	}

	return 0;
}

static struct l2tp_config_tunnel_map *l2tp_config_tunnel_map_find(char *tunnel_name, uint16_t tunnel_id)
{
	struct l2tp_config_tunnel_map *entry;

	for (entry = l2tp_config_tunnel_map; entry != NULL; entry = entry->next) {
		if (tunnel_id != 0) {
			if (entry->tunnel_id == tunnel_id) {
				return entry;
			}
		} else if ((tunnel_name != NULL) && (entry->tunnel_name != NULL)) {
			if (strcmp(entry->tunnel_name, tunnel_name) == 0) {
				return entry;
			}
		}
	}

	return NULL;
}

static void l2tp_config_tunnel_map_cleanup(void)
{
	struct l2tp_config_tunnel_map *entry;
	struct l2tp_config_tunnel_map *tmp;

	for (entry = l2tp_config_tunnel_map; entry != NULL; ) {
		tmp = entry->next;
		free(entry->tunnel_name);
		free(entry);
		entry = tmp;
	}
	
}

static void l2tp_config_dump_tunnel(FILE *file, struct l2tp_api_tunnel_msg_data *cfg)
{
	struct in_addr ip;
	char tunnel_name[10]; /* l2tpNNNNN */

	/* If the tunnel wasn't given an tunnel_name, derive one from its tunnel_id */
	if ((cfg->flags & L2TP_API_TUNNEL_FLAG_TUNNEL_NAME) == 0) {
		sprintf(&tunnel_name[0], "l2tp%hu", cfg->tunnel_id);
		OPTSTRING(cfg->tunnel_name) = tunnel_name;
		cfg->tunnel_name.valid = 1;
	}

	/* Record the mapping of tunnel_id to tunnel_name so that we can easily
	 * derive the tunnel name from a tunnel_id when dumping sessions.
	 */
	l2tp_config_tunnel_map_add(OPTSTRING_PTR(cfg->tunnel_name), cfg->tunnel_id);

	ip.s_addr = cfg->peer_addr.s_addr;
	fprintf(file, "tunnel create tunnel_name=%s dest_ipaddr=%s \\\n", 
		OPTSTRING_PTR(cfg->tunnel_name), inet_ntoa(ip));
#ifdef L2TP_TEST
	fprintf(file, "\ttunnel_id=%hu \\\n", cfg->tunnel_id);
#endif
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_CONFIG_ID) {
		fprintf(file, "\tconfig_id=%d \\\n", cfg->config_id);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_HIDE_AVPS) {
		fprintf(file, "\thide_avps=%s \\\n", Y_OR_N(cfg->hide_avps));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_AUTH_MODE) {
		fprintf(file, "\tauth_mode=%s \\\n", 
			(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_NONE) ? "none" :
			(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_SIMPLE) ? "simple" :
			(cfg->auth_mode == L2TP_API_TUNNEL_AUTH_MODE_CHALLENGE) ? "challenge" : "??");
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_FRAMING_CAP) {
		fprintf(file, "\tframing_cap=%s \\\n", 
			(!cfg->framing_cap_sync && !cfg->framing_cap_async) ? "none" :
			(cfg->framing_cap_sync && cfg->framing_cap_async) ? "any" :
			(cfg->framing_cap_sync && !cfg->framing_cap_async) ? "sync" :
			(!cfg->framing_cap_sync && cfg->framing_cap_async) ? "async" : "??");
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_BEARER_CAP) {
		fprintf(file, "\tbearer_cap=%s \\\n", 
			(!cfg->bearer_cap_digital && !cfg->bearer_cap_analog) ? "none" :
			(cfg->bearer_cap_digital && cfg->bearer_cap_analog) ? "any" :
			(cfg->bearer_cap_digital && !cfg->bearer_cap_analog) ? "digital" :
			(!cfg->bearer_cap_digital && cfg->bearer_cap_analog) ? "analog" : "??");
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_USE_TIEBREAKER) {
		fprintf(file, "\tuse_tiebreaker=%s \\\n", Y_OR_N(cfg->use_tiebreaker));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_HELLO_TIMEOUT) {
		fprintf(file, "\thello_timeout=%d \\\n", cfg->hello_timeout);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_MAX_RETRIES) {
		fprintf(file, "\tmax_retries=%d \\\n", cfg->max_retries);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_RX_WINDOW_SIZE) {
		fprintf(file, "\trx_window_size=%d \\\n", cfg->rx_window_size);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_TX_WINDOW_SIZE) {
		fprintf(file, "\ttx_window_size=%d \\\n", cfg->tx_window_size);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_RETRY_TIMEOUT) {
		fprintf(file, "\tretry_timeout=%d \\\n", cfg->retry_timeout);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_IDLE_TIMEOUT) {
		fprintf(file, "\tidle_timeout=%d \\\n", cfg->idle_timeout);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_SECRET) {
		fprintf(file, "\tsecret=%s \\\n", OPTSTRING_PTR(cfg->secret));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_ALLOW_PPP_PROXY) {
		fprintf(file, "\tallow_ppp_proxy=%s \\\n", Y_OR_N(cfg->allow_ppp_proxy));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_TRACE_FLAGS) {
		fprintf(file, "\ttrace_flags=%u \\\n", cfg->trace_flags);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_USE_UDP_CHECKSUMS) {
		fprintf(file, "\tuse_udp_checksums=%s \\\n", Y_OR_N(cfg->use_udp_checksums));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_PERSIST) {
		fprintf(file, "\tpersist=%s \\\n", Y_OR_N(cfg->persist));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_HOST_NAME) {
		fprintf(file, "\thost_name=%s \\\n", OPTSTRING_PTR(cfg->host_name));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_MAX_SESSIONS) {
		fprintf(file, "\tmax_sessions=%d \\\n", cfg->max_sessions);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_OUR_ADDR) {
		struct in_addr ip;
		ip.s_addr = cfg->our_addr.s_addr;
		fprintf(file, "\tsrc_ipaddr=%s \\\n", inet_ntoa(ip));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_OUR_UDP_PORT) {
		fprintf(file, "\tour_udp_port=%hu \\\n", cfg->our_udp_port);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_PEER_UDP_PORT) {
		fprintf(file, "\tpeer_udp_port=%hu \\\n", cfg->peer_udp_port);
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_PEER_PROFILE_NAME) {
		fprintf(file, "\tpeer_profile_name=%s \\\n", OPTSTRING_PTR(cfg->peer_profile_name));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_SESSION_PROFILE_NAME) {
		fprintf(file, "\tsession_profile_name=%s \\\n", OPTSTRING_PTR(cfg->session_profile_name));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_PPP_PROFILE_NAME) {
		fprintf(file, "\tppp_profile_name=%s \\\n", OPTSTRING_PTR(cfg->ppp_profile_name));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_DO_PMTU_DISCOVERY) {
		fprintf(file, "\tdo_pmtu_discovery=%s \\\n", Y_OR_N(cfg->do_pmtu_discovery));
	}
	if (cfg->flags & L2TP_API_TUNNEL_FLAG_MTU) {
		fprintf(file, "\tmtu=%d \\\n", cfg->mtu);
	}
	fprintf(file, "\n");
}

static void l2tp_config_dump_session(FILE *file, struct l2tp_api_session_msg_data *cfg)
{
	struct l2tp_config_tunnel_map *entry;

	/* Derive the tunnel name from the tunnel_id if tunnel_name is not set */

	if ((cfg->flags & L2TP_API_SESSION_FLAG_TUNNEL_NAME) == 0) {
		entry = l2tp_config_tunnel_map_find(NULL, cfg->tunnel_id);
		if (entry == NULL) {
			return;
		}
		OPTSTRING(cfg->tunnel_name) = entry->tunnel_name;
		cfg->tunnel_name.valid = 1;
	}

	fprintf(file, "session create tunnel_name=%s \\\n", OPTSTRING_PTR(cfg->tunnel_name));
#ifdef L2TP_TEST
	fprintf(file, "\ttunnel_id=%hu \\\n", cfg->tunnel_id);
	fprintf(file, "\tsession_id=%hu \\\n", cfg->session_id);
#endif

	if (cfg->flags & L2TP_API_SESSION_FLAG_TRACE_FLAGS) {
		fprintf(file, "\ttrace_flags=%u \\\n", cfg->trace_flags);
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_SEQUENCING_REQUIRED) {
		fprintf(file, "\tsequencing_required=%s \\\n", Y_OR_N(cfg->sequencing_required));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_PROFILE_NAME) {
		fprintf(file, "\tprofile_name=%s \\\n", OPTSTRING_PTR(cfg->profile_name));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_PPP_PROFILE_NAME) {
		fprintf(file, "\tppp_profile_name=%s \\\n", OPTSTRING_PTR(cfg->ppp_profile_name));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_SESSION_TYPE) {
		fprintf(file, "\tsession_type=%s \\\n", 
			(cfg->session_type == L2TP_API_SESSION_TYPE_LAIC) ? "laic" : 
			(cfg->session_type == L2TP_API_SESSION_TYPE_LAOC) ? "laoc" : 
			(cfg->session_type == L2TP_API_SESSION_TYPE_LNIC) ? "lnic" : 
			(cfg->session_type == L2TP_API_SESSION_TYPE_LNOC) ? "lnoc" : "??");
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_PRIV_GROUP_ID) {
		fprintf(file, "\tpriv_group_id=%s \\\n", OPTSTRING_PTR(cfg->priv_group_id));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_FRAMING_TYPE) {
		fprintf(file, "\tframing_type=%s \\\n", 
			(!cfg->framing_type_sync && !cfg->framing_type_async) ? "none" :
			(cfg->framing_type_sync && cfg->framing_type_async) ? "any" :
			(cfg->framing_type_sync && !cfg->framing_type_async) ? "sync" :
			(!cfg->framing_type_sync && cfg->framing_type_async) ? "async" : "??");
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_BEARER_TYPE) {
		fprintf(file, "\tbearer_type=%s \\\n", 
			(!cfg->bearer_type_digital && !cfg->bearer_type_analog) ? "none" :
			(cfg->bearer_type_digital && cfg->bearer_type_analog) ? "any" :
			(cfg->bearer_type_digital && !cfg->bearer_type_analog) ? "digital" :
			(!cfg->bearer_type_digital && cfg->bearer_type_analog) ? "analog" : "??");
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_MINIMUM_BPS) {
		fprintf(file, "\tminimum_bps=%d \\\n", cfg->minimum_bps);
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_MAXIMUM_BPS) {
		fprintf(file, "\tmaximum_bps=%d \\\n", cfg->maximum_bps);
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_CONNECT_SPEED) {
		fprintf(file, "\tconnect_speed=%d:%d \\\n", cfg->rx_connect_speed, cfg->tx_connect_speed);
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_USE_PPP_PROXY) {
		fprintf(file, "\tuse_ppp_proxy=%s \\\n", Y_OR_N(cfg->use_ppp_proxy));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_USE_SEQUENCE_NUMBERS) {
		fprintf(file, "\tuse_sequence_numbers=%s \\\n", Y_OR_N(cfg->use_sequence_numbers));
	}
	if (cfg->flags & L2TP_API_SESSION_FLAG_REORDER_TIMEOUT) {
		fprintf(file, "\treorder_timeout=%d \\\n", cfg->reorder_timeout);
	}
	fprintf(file, "\n");
}

static int l2tp_config_save(const char *file_name)
{
	struct l2tp_api_system_msg_data sys;
	int tid, sid;
	struct l2tp_api_peer_profile_list_msg_data peer_profile_list;
	struct l2tp_api_peer_profile_msg_data peer_profile;
	struct l2tp_api_peer_profile_list_entry *pewalk;
	struct l2tp_api_tunnel_profile_list_msg_data tunnel_profile_list;
	struct l2tp_api_tunnel_profile_msg_data tunnel_profile;
	struct l2tp_api_tunnel_profile_list_entry *tpwalk;
	struct l2tp_api_session_profile_list_msg_data session_profile_list;
	struct l2tp_api_session_profile_msg_data session_profile;
	struct l2tp_api_session_profile_list_entry *spwalk;
	struct l2tp_api_ppp_profile_list_msg_data ppp_profile_list;
	struct l2tp_api_ppp_profile_msg_data ppp_profile;
	struct l2tp_api_ppp_profile_list_entry *ppwalk;
	struct l2tp_api_tunnel_list_msg_data tunnel_list;
	struct l2tp_api_tunnel_msg_data tunnel;
	struct l2tp_api_session_list_msg_data session_list;
	struct l2tp_api_session_msg_data session;
	int num_tunnels;
	int num_sessions;
	int result = 0;
	FILE *file;
	optstring session_name = { 0, };
	optstring tunnel_name = { 0, };

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

	/* system */

	fprintf(file, "\n# system\n");
	memset(&sys, 0, sizeof(sys));
	result = l2tp_system_get_1(&sys, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	l2tp_config_dump_system(file, &sys);

	/* peer profile */

	fprintf(file, "\n# peer profiles\n");
	memset(&peer_profile_list, 0, sizeof(peer_profile_list));
	result = l2tp_peer_profile_list_1(&peer_profile_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (peer_profile_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-peer_profile_list.result));
		result = peer_profile_list.result;
		goto out;
	}

	pewalk = peer_profile_list.profiles;
	while ((pewalk != NULL) && (pewalk->profile_name[0] != '\0')) {
		memset(&peer_profile, 0, sizeof(peer_profile));
		result = l2tp_peer_profile_get_1(pewalk->profile_name, &peer_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}

		if (peer_profile.result_code < 0) {
			continue;
		}

		l2tp_config_dump_peer_profile(file, &peer_profile);

		pewalk = pewalk->next;
	}	

	/* tunnel profile */

	fprintf(file, "\n# tunnel profiles\n");
	memset(&tunnel_profile_list, 0, sizeof(tunnel_profile_list));
	result = l2tp_tunnel_profile_list_1(&tunnel_profile_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (tunnel_profile_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-tunnel_profile_list.result));
		result = tunnel_profile_list.result;
		goto out;
	}

	tpwalk = tunnel_profile_list.profiles;
	while ((tpwalk != NULL) && (tpwalk->profile_name[0] != '\0')) {
		memset(&tunnel_profile, 0, sizeof(tunnel_profile));
		result = l2tp_tunnel_profile_get_1(tpwalk->profile_name, &tunnel_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}

		if (tunnel_profile.result_code < 0) {
			continue;
		}

		l2tp_config_dump_tunnel_profile(file, &tunnel_profile);

		tpwalk = tpwalk->next;
	}	

	/* session profile */

	fprintf(file, "\n# session profiles\n");
	memset(&session_profile_list, 0, sizeof(session_profile_list));
	result = l2tp_session_profile_list_1(&session_profile_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (session_profile_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-session_profile_list.result));
		result = session_profile_list.result;
		goto out;
	}

	spwalk = session_profile_list.profiles;
	while ((spwalk != NULL) && (spwalk->profile_name[0] != '\0')) {
		memset(&session_profile, 0, sizeof(session_profile));
		result = l2tp_session_profile_get_1(spwalk->profile_name, &session_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}

		if (session_profile.result_code < 0) {
			continue;
		}

		l2tp_config_dump_session_profile(file, &session_profile);

		spwalk = spwalk->next;
	}	

	/* ppp profile */

	fprintf(file, "\n# ppp profiles\n");
	memset(&ppp_profile_list, 0, sizeof(ppp_profile_list));
	result = l2tp_ppp_profile_list_1(&ppp_profile_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (ppp_profile_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-ppp_profile_list.result));
		result = ppp_profile_list.result;
		goto out;
	}

	ppwalk = ppp_profile_list.profiles;
	while ((ppwalk != NULL) && (ppwalk->profile_name[0] != '\0')) {
		memset(&ppp_profile, 0, sizeof(ppp_profile));
		result = l2tp_ppp_profile_get_1(ppwalk->profile_name, &ppp_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}

		if (ppp_profile.result_code < 0) {
			continue;
		}

		l2tp_config_dump_ppp_profile(file, &ppp_profile);

		ppwalk = ppwalk->next;
	}	

	/* tunnels and sessions */

	fprintf(file, "\n# locally created tunnels and sessions\n");
	memset(&tunnel_list, 0, sizeof(tunnel_list));
	result = l2tp_tunnel_list_1(&tunnel_list, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (tunnel_list.result != 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-tunnel_list.result));
		result = tunnel_list.result;
		goto out;
	}

	num_tunnels = tunnel_list.tunnel_ids.tunnel_ids_len;

	for (tid = 0; tid < num_tunnels; tid++) {
		memset(&tunnel, 0, sizeof(tunnel));
		result = l2tp_tunnel_get_1(tunnel_list.tunnel_ids.tunnel_ids_val[tid], tunnel_name, &tunnel, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (tunnel.result_code < 0) {
			continue;
		}
		if (!tunnel.created_by_admin) {
			continue;
		}

		l2tp_config_dump_tunnel(file, &tunnel);

		memset(&session_list, 0, sizeof(session_list));
		result = l2tp_session_list_1(tunnel_list.tunnel_ids.tunnel_ids_val[tid], tunnel_name, &session_list, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (session_list.result != 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-session_list.result));
			result = session_list.result;
			goto out;
		}

		num_sessions = session_list.session_ids.session_ids_len;

		for (sid = 0; sid < num_sessions; sid++) {
			memset(&session, 0, sizeof(session));
			result = l2tp_session_get_1(tunnel_list.tunnel_ids.tunnel_ids_val[tid], tunnel_name, session_list.session_ids.session_ids_val[sid], session_name, &session, cl);
			if (result != RPC_SUCCESS) {
				clnt_perror(cl, server);
				result = -EAGAIN;
				goto out;
			}
			if (session.result_code < 0) {
				continue;
			}
			if (!session.created_by_admin) {
				continue;
			}

			l2tp_config_dump_session(file, &session);
		}
	}

out:
	l2tp_config_tunnel_map_cleanup();

	if (file != NULL) {
		fflush(file);
		fclose(file);
	}

	return result;
}

static int l2tp_config_get_line(char *buffer, int buf_size, FILE *file)
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

static int l2tp_config_restore(const char *file_name)
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

		chars_read = l2tp_config_get_line(buffer + count, 4000 - count, file);
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

static int l2tp_act_config_save(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *file_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_config_arg_ids_t, int);
	int ret = 0;

	clnt_res = 0;

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_CONFIG_ARGID_FILENAME:
			file_name = arg_values[arg];
			break;
		}
	} L2TP_ACT_END();

	ret = l2tp_config_save(file_name);

out:
	return ret;
}

static int l2tp_act_config_restore(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *file_name = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_config_arg_ids_t, int);
	int ret = 0;

	clnt_res = 0;

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_CONFIG_ARGID_FILENAME:
			file_name = arg_values[arg];
			break;
		}
	} L2TP_ACT_END();

	if (file_name == NULL) {
		fprintf(stderr, "Required file_name argument is missing.\n");
		exit(1);
	}

	ret = l2tp_config_restore(file_name);

out:
	return ret;
}

/*****************************************************************************
 * debug ...
 *****************************************************************************/

#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_DEBUG_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_DEBUG_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	L2TP_DEBUG_ARGID_DEBUG_PROTOCOL,
	L2TP_DEBUG_ARGID_DEBUG_FSM,
	L2TP_DEBUG_ARGID_DEBUG_API,
	L2TP_DEBUG_ARGID_DEBUG_AVP,
	L2TP_DEBUG_ARGID_DEBUG_AVP_HIDE,
	L2TP_DEBUG_ARGID_DEBUG_AVP_DATA,
	L2TP_DEBUG_ARGID_DEBUG_FUNC,
	L2TP_DEBUG_ARGID_DEBUG_XPRT,
	L2TP_DEBUG_ARGID_DEBUG_DATA,
	L2TP_DEBUG_ARGID_DEBUG_PPP,
	L2TP_DEBUG_ARGID_DEBUG_SYSTEM,
	L2TP_DEBUG_ARGID_TUNNEL_ID,
	L2TP_DEBUG_ARGID_SESSION_ID,
	L2TP_DEBUG_ARGID_TUNNEL_PROFILE_NAME,
	L2TP_DEBUG_ARGID_SESSION_PROFILE_NAME,
	L2TP_DEBUG_ARGID_PPP_PROFILE_NAME,
	L2TP_DEBUG_ARGID_SYSTEM,
} l2tp_debug_arg_ids_t;

static struct cli_arg_entry l2tp_args_debug_modify[] = {
	ARG(DEBUG_PROTOCOL,		"protocol",		0,	bool,	"L2TP protocol events"),
	ARG(DEBUG_FSM,			"fsm",			0,	bool,	"Finite State Machine events (e.g. state changes)"),
	ARG(DEBUG_API,			"api",			0,	bool,	"Management interface interactions"),
	ARG(DEBUG_XPRT,			"transport",		0,	bool,	"Log tunnel transport activity, e.g. packet sequence" \
										"numbers, packet receive and transmit, to debug tunnel " \
										"link establishment or failures"),
	ARG(DEBUG_DATA,			"data",			0,	bool,	"Log L2TP data channel activity. Only L2TP control " \
										"messages are logged, never user data packets."),
	ARG(DEBUG_PPP,			"ppp",			0,	bool,	"Enables trace of PPP packets from the PPP subsystem" ),
	ARG(DEBUG_AVP_DATA,		"avp_data",		0,	bool,	"L2TP Attribute Value Pairs (AVPs) data contents" \
	    									"For detailed message content trace"),
	ARG(DEBUG_AVP_HIDE,		"avp_hide",		0,	bool,	"Show AVP hiding details"),
	ARG(DEBUG_AVP,			"avp",			0,	bool,	"High level AVP info (shows AVPs present, not their contents)"),
	ARG(DEBUG_FUNC,			"func",			0,	bool,	"Internal functional behavior"),
	ARG(DEBUG_SYSTEM,		"system",		0,	bool,	"Low level system activity, e.g. timers, sockets etc" ),
	ARG(TUNNEL_ID,			"tunnel_id",		0,	uint16,	"tunnel_id of entity being modified"),
	ARG(SESSION_ID,			"session_id",		0,	uint16,	"session_id of entity being modified"),
	ARG(TUNNEL_PROFILE_NAME,	"tunnel_profile_name",	0,	bool,	"Name of tunnel profile being modified"),
	ARG(SESSION_PROFILE_NAME,	"session_profile_name",	0,	bool,	"Name of session profile being modified"),
	ARG(PPP_PROFILE_NAME,		"ppp_profile_name",	0,	bool,	"Name of ppp profile being modified"),
	FLG(SYSTEM,			"system",				"Modify system debug settings"),
	{ NULL, },
};

static struct cli_arg_entry l2tp_args_debug_show[] = {
	ARG(TUNNEL_ID,			"tunnel_id",		0,	uint16,	"tunnel_id of entity being shown"),
	ARG(SESSION_ID,			"session_id",		0,	uint16,	"session_id of entity being shown"),
	ARG(TUNNEL_PROFILE_NAME,	"tunnel_profile_name",	0,	bool,	"Name of tunnel profile being shown"),
	ARG(SESSION_PROFILE_NAME,	"session_profile_name",	0,	bool,	"Name of session profile being shown"),
	ARG(PPP_PROFILE_NAME,		"ppp_profile_name",	0,	bool,	"Name of ppp profile being shown"),
	FLG(SYSTEM,			"system",				"Show system debug settings"),
	{ NULL, },
};

static int l2tp_act_debug_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	cli_bool_t bool_arg;
	int flags;
	uint32_t trace_flags;
	struct l2tp_debug_info {
		int	debug_protocol:1;
		int	debug_fsm:1;
		int	debug_api:1;
		int	debug_transport:1;
		int	debug_data:1;
		int	debug_ppp:1;
		int	debug_avp_data:1;
		int	debug_avp_hide:1;
		int	debug_avp:1;
		int	debug_func:1;
		int	debug_system:1;
		int	system:1;
		uint16_t tunnel_id;
		uint16_t session_id;
		char	*tunnel_profile_name;
		char	*session_profile_name;
		char	*ppp_profile_name;
	} msg = { 0, };
	L2TP_ACT_DECLARATIONS(60, l2tp_debug_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_DEBUG_ARGID_DEBUG_PROTOCOL:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_protocol = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_FSM:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_fsm = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_API:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_api = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_XPRT:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_transport = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_DATA:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_data = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_PPP:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_ppp = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_AVP_DATA:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_avp_data = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_AVP_HIDE:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_avp_hide = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_AVP:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_avp = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_FUNC:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_func = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_DEBUG_SYSTEM:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], bool_arg, flags, 0);
			msg.debug_system = bool_arg;
			break;
		case L2TP_DEBUG_ARGID_SYSTEM:
			msg.system = 1;
			break;
		case L2TP_DEBUG_ARGID_TUNNEL_PROFILE_NAME:
			msg.tunnel_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_SESSION_PROFILE_NAME:
			msg.session_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_PPP_PROFILE_NAME:
			msg.ppp_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.tunnel_id, flags, 0);
			break;
		case L2TP_DEBUG_ARGID_SESSION_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.session_id, flags, 0);
			break;
		}
	} L2TP_ACT_END();

	trace_flags = ((msg.debug_protocol  ? L2TP_DEBUG_PROTOCOL : 0) |
		       (msg.debug_fsm       ? L2TP_DEBUG_FSM : 0) |
		       (msg.debug_api       ? L2TP_DEBUG_API : 0) |
		       (msg.debug_transport ? L2TP_DEBUG_XPRT : 0) |
		       (msg.debug_data      ? L2TP_DEBUG_DATA : 0) |
		       (msg.debug_ppp       ? L2TP_DEBUG_PPP : 0) |
		       (msg.debug_avp_data  ? L2TP_DEBUG_AVP_DATA : 0) |
		       (msg.debug_avp_hide  ? L2TP_DEBUG_AVP_HIDE : 0) |
		       (msg.debug_avp       ? L2TP_DEBUG_AVP : 0) |
		       (msg.debug_func      ? L2TP_DEBUG_FUNC : 0) |
		       (msg.debug_system    ? L2TP_DEBUG_SYSTEM : 0));

	if (msg.system) {
		struct l2tp_api_system_msg_data sys;
		memset(&sys, 0, sizeof(sys));
		sys.config.trace_flags = trace_flags;
		sys.config.flags = L2TP_API_CONFIG_FLAG_TRACE_FLAGS;
		result = l2tp_system_modify_1(sys, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else if (msg.tunnel_profile_name != NULL) {
		struct l2tp_api_tunnel_profile_msg_data tunnel_profile;
		memset(&tunnel_profile, 0, sizeof(tunnel_profile));
		tunnel_profile.profile_name = msg.tunnel_profile_name;
		tunnel_profile.trace_flags = trace_flags;
		tunnel_profile.flags = L2TP_API_TUNNEL_PROFILE_FLAG_TRACE_FLAGS;
		result = l2tp_tunnel_profile_modify_1(tunnel_profile, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else if (msg.session_profile_name != NULL) {
		struct l2tp_api_session_profile_msg_data session_profile;
		memset(&session_profile, 0, sizeof(session_profile));
		session_profile.profile_name = msg.session_profile_name;
		session_profile.trace_flags = trace_flags;
		session_profile.flags = L2TP_API_SESSION_PROFILE_FLAG_TRACE_FLAGS;
		result = l2tp_session_profile_modify_1(session_profile, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else if (msg.ppp_profile_name != NULL) {
		struct l2tp_api_ppp_profile_msg_data ppp_profile;
		memset(&ppp_profile, 0, sizeof(ppp_profile));
		ppp_profile.profile_name = msg.ppp_profile_name;
		ppp_profile.trace_flags = trace_flags;
		ppp_profile.flags = L2TP_API_PPP_PROFILE_FLAG_TRACE_FLAGS;
		result = l2tp_ppp_profile_modify_1(ppp_profile, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else if ((msg.tunnel_id != 0) && (msg.session_id != 0)) {
		struct l2tp_api_session_msg_data session;
		memset(&session, 0, sizeof(session));
		session.tunnel_id = msg.tunnel_id;
		session.session_id = msg.session_id;
		session.trace_flags = trace_flags;
		session.flags = L2TP_API_SESSION_FLAG_TRACE_FLAGS;
		result = l2tp_session_modify_1(session, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else if (msg.tunnel_id != 0) {
		struct l2tp_api_tunnel_msg_data tunnel;
		memset(&tunnel, 0, sizeof(tunnel));
		tunnel.tunnel_id = msg.tunnel_id;
		tunnel.trace_flags = trace_flags;
		tunnel.flags = L2TP_API_TUNNEL_FLAG_TRACE_FLAGS;
		result = l2tp_tunnel_modify_1(tunnel, &clnt_res, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			exit(1);
		}
		if (clnt_res < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
			goto out;
		}
	} else {
		fprintf(stderr, "Missing argument\n");
		result = -EINVAL;
	}

out:
	return result;
}

static int l2tp_act_debug_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	int flags = 0;
	int trace_flags;
	struct { 
		int system;
		uint16_t tunnel_id;
		uint16_t session_id;
		char *tunnel_profile_name;
		char *session_profile_name;
		char *ppp_profile_name;
	} msg = { 0, };

	L2TP_ACT_DECLARATIONS(20, l2tp_debug_arg_ids_t, int);
	clnt_res = 0;

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_DEBUG_ARGID_SYSTEM:
			msg.system = 1;
			break;
		case L2TP_DEBUG_ARGID_TUNNEL_PROFILE_NAME:
			msg.tunnel_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_SESSION_PROFILE_NAME:
			msg.session_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_PPP_PROFILE_NAME:
			msg.ppp_profile_name = arg_values[arg];
			break;
		case L2TP_DEBUG_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.tunnel_id, flags, 0);
			break;
		case L2TP_DEBUG_ARGID_SESSION_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.session_id, flags, 0);
			break;
		case L2TP_DEBUG_ARGID_DEBUG_PROTOCOL:
		case L2TP_DEBUG_ARGID_DEBUG_FSM:
		case L2TP_DEBUG_ARGID_DEBUG_API:
		case L2TP_DEBUG_ARGID_DEBUG_AVP:
		case L2TP_DEBUG_ARGID_DEBUG_AVP_HIDE:
		case L2TP_DEBUG_ARGID_DEBUG_AVP_DATA:
		case L2TP_DEBUG_ARGID_DEBUG_FUNC:
		case L2TP_DEBUG_ARGID_DEBUG_XPRT:
		case L2TP_DEBUG_ARGID_DEBUG_DATA:
		case L2TP_DEBUG_ARGID_DEBUG_PPP:
		case L2TP_DEBUG_ARGID_DEBUG_SYSTEM:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END();

	if (msg.system) {
		struct l2tp_api_system_msg_data sys;
		memset(&sys, 0, sizeof(sys));
		result = l2tp_system_get_1(&sys, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		trace_flags = sys.config.trace_flags;
	} else if (msg.tunnel_profile_name != NULL) {
		struct l2tp_api_tunnel_profile_msg_data tunnel_profile;
		memset(&tunnel_profile, 0, sizeof(tunnel_profile));
		result = l2tp_tunnel_profile_get_1(msg.tunnel_profile_name, &tunnel_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (tunnel_profile.result_code < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-tunnel_profile.result_code));
			result = tunnel_profile.result_code;
			goto out;
		}
		trace_flags = tunnel_profile.trace_flags;
	} else if (msg.session_profile_name != NULL) {
		struct l2tp_api_session_profile_msg_data session_profile;
		memset(&session_profile, 0, sizeof(session_profile));
		result = l2tp_session_profile_get_1(msg.session_profile_name, &session_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (session_profile.result_code < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-session_profile.result_code));
			result = session_profile.result_code;
			goto out;
		}
		trace_flags = session_profile.trace_flags;
	} else if (msg.ppp_profile_name != NULL) {
		struct l2tp_api_ppp_profile_msg_data ppp_profile;
		memset(&ppp_profile, 0, sizeof(ppp_profile));
		result = l2tp_ppp_profile_get_1(msg.ppp_profile_name, &ppp_profile, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		if (ppp_profile.result_code < 0) {
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-ppp_profile.result_code));
			result = ppp_profile.result_code;
			goto out;
		}
		trace_flags = ppp_profile.trace_flags;
	} else if ((msg.tunnel_id != 0) && (msg.session_id != 0)) {
		struct l2tp_api_session_msg_data session;
		optstring tunnel_name = { 0, };
		optstring session_name = { 0, };
		memset(&session, 0, sizeof(session));
		result = l2tp_session_get_1(msg.tunnel_id, tunnel_name, msg.session_id, session_name, &session, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		result = 0;
		if (session.result_code < 0) {
			result = session.result_code;
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-result));
			goto out;
		}
		trace_flags = session.trace_flags;
	} else if (msg.tunnel_id != 0) {
		struct l2tp_api_tunnel_msg_data tunnel;
		optstring tunnel_name = { 0, };
		memset(&tunnel, 0, sizeof(tunnel));
		result = l2tp_tunnel_get_1(msg.tunnel_id, tunnel_name, &tunnel, cl);
		if (result != RPC_SUCCESS) {
			clnt_perror(cl, server);
			result = -EAGAIN;
			goto out;
		}
		result = 0;
		if (tunnel.result_code < 0) {
			result = tunnel.result_code;
			fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-result));
			goto out;
		}
		trace_flags = tunnel.trace_flags;
	} else {
		fprintf(stderr, "Missing argument\n");
		result = -EINVAL;
		goto out;
	}

	print_trace_flags(trace_flags, NULL);

out:
	return result;
}

/*****************************************************************************
 * Test/debug functions
 *****************************************************************************/

#ifdef L2TP_TEST

#undef ARG
#define ARG(id, name, flag, type, doc) \
	{ name, { L2TP_TEST_ARGID_##id, flag, cli_arg_parse_##type, doc } }

#undef FLG
#define FLG(id, name, doc) \
	{ name, { L2TP_TEST_ARGID_##id, CLI_ARG_FLAG_NO_VALUE, NULL, doc } }

typedef enum {
	L2TP_TEST_ARGID_FAKE_RX_DROP,
	L2TP_TEST_ARGID_FAKE_TX_DROP,
	L2TP_TEST_ARGID_FAKE_TRIGGER_TYPE,
	L2TP_TEST_ARGID_CLEAR_FAKE_TRIGGER,
	L2TP_TEST_ARGID_HOLD_TUNNELS,
	L2TP_TEST_ARGID_HOLD_SESSIONS,
	L2TP_TEST_ARGID_NO_RANDOM_IDS,
	L2TP_TEST_ARGID_RESET_IDS,
	L2TP_TEST_ARGID_DEFAULT_CONFIG,
	L2TP_TEST_ARGID_LOG_MESSAGE,
	L2TP_TEST_ARGID_DO_TRANSPORT_TEST,
	L2TP_TEST_ARGID_TUNNEL_ID,
	L2TP_TEST_ARGID_SESSION_ID,
} l2tp_test_arg_ids_t;

static struct cli_arg_entry l2tp_args_test_modify[] = {
	ARG(FAKE_RX_DROP,	"fake_rx_drop",		0, 	bool, 	"Fake the dropping of one or more received L2TP control frames."),
	ARG(FAKE_TX_DROP,	"fake_tx_drop",		0, 	bool, 	"Fake the dropping of one or more transmitted L2TP control frames."),
	ARG(FAKE_TRIGGER_TYPE,	"fake_trigger_type",	0, 	string,	"Specifies how faked errors are to occur. Possible values are:-\n"
                                                                        "off    - faked error conditions off\n"
                                                                        "on     - faked error conditions on\n"
                                                                        "once   - faked error condition is forced once only\n"
                                                                        "low    - faked error condition occurs at random (~1%)\n"
                                                                        "medium - faked error condition occurs at random (~5%)\n"
                                                                        "high   - faked error condition occurs at random (~20%)"),
	FLG(CLEAR_FAKE_TRIGGER,	"clear_trigger",			"Clear the fake trigger status"),
	ARG(HOLD_TUNNELS,	"hold_tunnels",		0,	bool,	"Hold tunnel contexts until operator explicitely deletes them."),
	ARG(HOLD_SESSIONS,	"hold_sessions",	0,	bool,	"Hold session contexts until operator explicitely deletes them."),
	ARG(NO_RANDOM_IDS,	"no_random_ids",	0,	bool,	"Disable random tunnel_id/session_id generator."),
	FLG(RESET_IDS,		"reset_ids",				"Reset tunnel_id/session_id generator back to 0."),
	FLG(DEFAULT_CONFIG,	"default_config",			"Restore system back to default configuration."),
	FLG(DO_TRANSPORT_TEST,	"do_transport_test",			"Do transport test on the specified tunnel_id."),
	ARG(TUNNEL_ID,		"tunnel_id",		0,	uint16,	"Tunnel ID for some tests"),
	ARG(SESSION_ID,		"session_id",		0,	uint16,	"Session ID for some tests"),
	{ NULL, },
};

static int l2tp_act_test_modify(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_test_msg_data msg = {0. };
	L2TP_ACT_DECLARATIONS(10, l2tp_test_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TEST_ARGID_FAKE_RX_DROP:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.fake_rx_drop, msg.flags, L2TP_API_TEST_FLAG_FAKE_RX_DROP);
			break;
		case L2TP_TEST_ARGID_FAKE_TX_DROP:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.fake_tx_drop, msg.flags, L2TP_API_TEST_FLAG_FAKE_TX_DROP);
			break;
		case L2TP_TEST_ARGID_FAKE_TRIGGER_TYPE:
			if (arg_values[arg] == NULL) {
				arg_values[arg] = empty_string;
			}
			if (strcasecmp(arg_values[arg], "once") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_ONCE;
			} else if (strcasecmp(arg_values[arg], "low") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_LOW;
			} else if (strcasecmp(arg_values[arg], "medium") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_MEDIUM;
			} else if (strcasecmp(arg_values[arg], "high") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_HIGH;
			} else if (strcasecmp(arg_values[arg], "off") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_OFF;
			} else if (strcasecmp(arg_values[arg], "on") == 0) {
				msg.fake_trigger_type = L2TP_API_TEST_FAKE_TRIGGER_ON;
			} else {
				fprintf(stderr, "Bad value: %s. Expecting once|low|medium|high|off|on\n", arg_values[arg]);
				result = -EINVAL;
				goto out;
			}
			msg.flags |= L2TP_API_TEST_FLAG_FAKE_TRIGGER_TYPE;
			break;
		case L2TP_TEST_ARGID_CLEAR_FAKE_TRIGGER:
			msg.flags |= L2TP_API_TEST_FLAG_CLEAR_FAKE_TRIGGER;
			break;
		case L2TP_TEST_ARGID_HOLD_TUNNELS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.hold_tunnels, msg.flags, L2TP_API_TEST_FLAG_HOLD_TUNNELS);
			break;
		case L2TP_TEST_ARGID_HOLD_SESSIONS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.hold_sessions, msg.flags, L2TP_API_TEST_FLAG_HOLD_SESSIONS);
			break;
		case L2TP_TEST_ARGID_NO_RANDOM_IDS:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.no_random_ids, msg.flags, L2TP_API_TEST_FLAG_NO_RANDOM_IDS);
			break;
		case L2TP_TEST_ARGID_RESET_IDS:
			msg.flags |= L2TP_API_TEST_FLAG_RESET_IDS;
			break;
		case L2TP_TEST_ARGID_DEFAULT_CONFIG:
			msg.flags |= L2TP_API_TEST_FLAG_DEFAULT_CONFIG;
			break;
		case L2TP_TEST_ARGID_LOG_MESSAGE:
			result = -EINVAL;
			goto out;
		case L2TP_TEST_ARGID_DO_TRANSPORT_TEST:
			msg.flags |= L2TP_API_TEST_FLAG_DO_TRANSPORT_TEST;
			break;
		case L2TP_TEST_ARGID_TUNNEL_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.tunnel_id, msg.flags, L2TP_API_TEST_FLAG_TUNNEL_ID);
			break;
		case L2TP_TEST_ARGID_SESSION_ID:
			L2TP_ACT_PARSE_ARG(args[arg], arg_values[arg], msg.session_id, msg.flags, L2TP_API_TEST_FLAG_SESSION_ID);
			break;
		}
	} L2TP_ACT_END()

	result = l2tp_test_modify_1(msg, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = -clnt_res;
		goto out;
	}
	if (!opt_quiet) {
		fprintf(stderr, "Modified test config\n");
	}

out:
	return 0;
}

static struct cli_arg_entry l2tp_args_test_log[] = {
	ARG(LOG_MESSAGE,	"message",		0,	string,	"Send a message to the L2TP service log file."),
	{ NULL, },
};

static int l2tp_act_test_log(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	char *message = NULL;
	L2TP_ACT_DECLARATIONS(4, l2tp_test_arg_ids_t, int);

	L2TP_ACT_BEGIN() {
		switch (arg_id) {
		case L2TP_TEST_ARGID_LOG_MESSAGE:
			message = arg_values[arg];
			break;
		default:
			result = -EINVAL;
			goto out;
		}
	} L2TP_ACT_END()

	if (message == NULL) {
		fprintf(stderr, "Required message argument missing\n");
		result = -EINVAL;
		goto out;
	}

	result = l2tp_test_log_1(message, &clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}
	if (clnt_res < 0) {
		fprintf(stderr, "Operation failed: %s\n", l2tp_strerror(-clnt_res));
		result = -clnt_res;
		goto out;
	}

out:
	return 0;
}

static int l2tp_act_test_show(struct cli_node *node, int argc, char *argv[], int *arg_num)
{
	struct l2tp_api_test_msg_data clnt_res;
	int result = 0;

	memset(&clnt_res, 0, sizeof(clnt_res));

	result = l2tp_test_get_1(&clnt_res, cl);
	if (result != RPC_SUCCESS) {
		clnt_perror(cl, server);
		result = -EAGAIN;
		goto out;
	}

	printf("Test settings:-\n");
	printf("  fake rx drop: %s, fake tx drop: %s, fake trigger: %s\n",
	       clnt_res.fake_rx_drop ? "YES" : "NO", 
	       clnt_res.fake_tx_drop ? "YES" : "NO",
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_ON) ? "ON" :
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_OFF) ? "OFF" :
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_LOW) ? "LOW" :
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_MEDIUM) ? "MEDIUM" :
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_HIGH) ? "HIGH" :
	       (clnt_res.fake_trigger_type == L2TP_API_TEST_FAKE_TRIGGER_ONCE) ? "ONCE" : "??");
	if ((clnt_res.tunnel_id != 0) || (clnt_res.session_id != 0)) {
		printf("  tunnel_id: %hu, session_id: %hu\n", 
		       clnt_res.tunnel_id, clnt_res.session_id);
	}
	printf("  trigger status: %s\n", clnt_res.fake_trigger_fired ? "TRIGGERED" : "NOT TRIGGERED");
	if (clnt_res.fake_trigger_fired) {
		printf("  rx drops: %u, tx drops: %u\n", 
		       clnt_res.num_rx_drops, clnt_res.num_tx_drops);
	}
	printf("  hold tunnels: %s, sessions: %s\n",
	       clnt_res.hold_tunnels ? "YES" : "NO", clnt_res.hold_sessions ? "YES" : "NO");
	printf("  hash list hits/misses:-\n");
	printf("    tunnel_id: %d/%d\n", 
	       clnt_res.num_tunnel_id_hash_hits, clnt_res.num_tunnel_id_hash_misses);
	printf("    tunnel_name: %d/%d\n", 
	       clnt_res.num_tunnel_name_hash_hits, clnt_res.num_tunnel_name_hash_misses);
	printf("    session_id: %d/%d\n", 
	       clnt_res.num_session_id_hash_hits, clnt_res.num_session_id_hash_misses);

out:
	return result;
}

#endif /* L2TP_TEST */

/*****************************************************************************
 * Syntax tree
 *****************************************************************************/

static struct cli_node_entry cmds[] = {
	{ 0, CLI_NODE_TYPE_COMMAND, "exit", "exit application", l2tp_act_exit },
	{ 0, CLI_NODE_TYPE_COMMAND, "quit", "exit application", l2tp_act_exit },
	{ 0, CLI_NODE_TYPE_COMMAND, "help", "display help information", l2tp_act_help },
	{ 0, CLI_NODE_TYPE_KEYWORD, "config", "configuration save/restore", },
	{ 1, CLI_NODE_TYPE_COMMAND, "save", "save configuration", l2tp_act_config_save, &l2tp_args_config[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "restore", "restore configurationfrom file", l2tp_act_config_restore, &l2tp_args_config[0], },
	{ 0, CLI_NODE_TYPE_KEYWORD, "server", "server configuration", },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify server parameters", l2tp_act_server_modify, &l2tp_args_server_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show server parameters", l2tp_act_server_show, },
	{ 0, CLI_NODE_TYPE_KEYWORD, "system", "system commands", },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify system parameters", l2tp_act_system_modify, &l2tp_args_system_modify[0], },
	{ 1, CLI_NODE_TYPE_KEYWORD, "show", "show system configuration and statistics", },
	{ 2, CLI_NODE_TYPE_COMMAND, "configuration", "show system configuration", l2tp_act_system_show_config },
	{ 2, CLI_NODE_TYPE_COMMAND, "status", "show system status", l2tp_act_system_show_status },
	{ 2, CLI_NODE_TYPE_COMMAND, "statistics", "show system statistics", l2tp_act_system_show_stats },
	{ 2, CLI_NODE_TYPE_COMMAND, "version", "show system version", l2tp_act_system_show_version },
#ifdef L2TP_TEST
	{ 0, CLI_NODE_TYPE_KEYWORD, "test", "test commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify test parameters", l2tp_act_test_modify, &l2tp_args_test_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "log", "test messages", l2tp_act_test_log, &l2tp_args_test_log[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show test parameters", l2tp_act_test_show, },
#endif /* L2TP_TEST */
	{ 0, CLI_NODE_TYPE_KEYWORD, "tunnel", "tunnel commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP tunnel", l2tp_act_tunnel_create, &l2tp_args_tunnel_create[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP tunnel", l2tp_act_tunnel_delete, &l2tp_args_tunnel_delete[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP tunnel", l2tp_act_tunnel_modify, &l2tp_args_tunnel_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP tunnel", l2tp_act_tunnel_show, &l2tp_args_tunnel_show[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP tunnels", l2tp_act_tunnel_list, },
	{ 1, CLI_NODE_TYPE_KEYWORD, "profile", "tunnel profile commands" },
	{ 2, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP tunnel profile", l2tp_act_tunnel_profile_create, &l2tp_args_tunnel_profile_create[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP tunnel profile", l2tp_act_tunnel_profile_delete, &l2tp_args_tunnel_profile_delete[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP tunnel profile", l2tp_act_tunnel_profile_modify, &l2tp_args_tunnel_profile_modify[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP tunnel profile", l2tp_act_tunnel_profile_show, &l2tp_args_tunnel_profile_show[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP tunnel profiles", l2tp_act_tunnel_profile_list },
	{ 0, CLI_NODE_TYPE_KEYWORD, "session", "session commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP session", l2tp_act_session_create, &l2tp_args_session_create[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP session", l2tp_act_session_delete, &l2tp_args_session_delete[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP session", l2tp_act_session_modify, &l2tp_args_session_modify[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP session", l2tp_act_session_show, &l2tp_args_session_show[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP sessions on a specified tunnel", l2tp_act_session_list, &l2tp_args_session_list[0] },
	{ 1, CLI_NODE_TYPE_KEYWORD, "profile", "session profile commands" },
	{ 2, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP session profile", l2tp_act_session_profile_create, &l2tp_args_session_profile_create[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP session profile", l2tp_act_session_profile_delete, &l2tp_args_session_profile_delete[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP session profile", l2tp_act_session_profile_modify, &l2tp_args_session_profile_modify[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP session profile", l2tp_act_session_profile_show, &l2tp_args_session_profile_show[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP session profiles", l2tp_act_session_profile_list },
	{ 0, CLI_NODE_TYPE_KEYWORD, "ppp", "ppp commands" },
	{ 1, CLI_NODE_TYPE_KEYWORD, "profile", "ppp profile commands" },
	{ 2, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP ppp profile", l2tp_act_ppp_profile_create, &l2tp_args_ppp_profile_create[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP ppp profile", l2tp_act_ppp_profile_delete, &l2tp_args_ppp_profile_delete[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP ppp profile", l2tp_act_ppp_profile_modify, &l2tp_args_ppp_profile_modify[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP ppp profile", l2tp_act_ppp_profile_show, &l2tp_args_ppp_profile_show[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP ppp profiles", l2tp_act_ppp_profile_list },
	{ 0, CLI_NODE_TYPE_KEYWORD, "peer", "peer commands" },
	{ 1, CLI_NODE_TYPE_COMMAND, "show", "show a peer record", l2tp_act_peer_show, &l2tp_args_peer_show[0], },
	{ 1, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP peer records", l2tp_act_peer_list },
	{ 1, CLI_NODE_TYPE_KEYWORD, "profile", "peer profile commands" },
	{ 2, CLI_NODE_TYPE_COMMAND, "create", "create a new L2TP peer profile", l2tp_act_peer_profile_create, &l2tp_args_peer_profile_create[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "delete", "delete an L2TP peer profile", l2tp_act_peer_profile_delete, &l2tp_args_peer_profile_delete[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "modify", "modify an L2TP peer profile", l2tp_act_peer_profile_modify, &l2tp_args_peer_profile_modify[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "show", "show an L2TP peer profile", l2tp_act_peer_profile_show, &l2tp_args_peer_profile_show[0], },
	{ 2, CLI_NODE_TYPE_COMMAND, "list", "list all L2TP peer profiles", l2tp_act_peer_profile_list },
	{ 0, CLI_NODE_TYPE_KEYWORD, "debug", "debug commands", },
	{ 1, CLI_NODE_TYPE_COMMAND, "modify", "modify debug settings", l2tp_act_debug_modify, &l2tp_args_debug_modify[0], },
	{ 1, CLI_NODE_TYPE_KEYWORD, "show", "show debug settings", l2tp_act_debug_show, &l2tp_args_debug_show[0], },
	{ 0, CLI_NODE_TYPE_END, NULL, },
};

/*****************************************************************************
 * Application init and cleanup
 *****************************************************************************/

static void cleanup(void)
{
	clnt_destroy(cl);
#if 0 /* Never write history file to ensure that it will not grow wihtout limit. Default setting is no limix. */
	if (interactive) {
		cli_write_history_file(l2tp_histfile, l2tp_histfile_maxsize);
	}
#endif
}

int main(int argc, char *argv[])
{
	int result;
	int opt;
	int arg = 1;
	static char *exit_cmd[] = { "exit", NULL };
	char *hist_size;

	strcpy(server, "localhost");

	cli_init("l2tp");
	result = cli_add_commands(&cmds[0]);
	if (result < 0) {
		fprintf(stderr, "Application initialization error.\n");
		return result;
	}

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
		l2tp_set_prompt(server);
		break;
	default:
		break;
	}

	cl = clnt_create(server, L2TP_PROG, L2TP_VERSION, "udp");
	if (cl == NULL) {
		clnt_pcreateerror(server);
		exit(1);
	}
	atexit(cleanup);

	/* If user supplied arguments, send them to the CLI now and immediately exit.
	 */
	if (argc > arg) {
		(void) cli_execute(argc - arg, &argv[arg]);
		(void) cli_execute(1, exit_cmd);
	} else {
		/* interactive mode */
		interactive = 1;
		l2tp_histfile = getenv("L2TP_HISTFILE");
		if (l2tp_histfile == NULL) {
			l2tp_histfile = "~/.l2tp_history";
		}
		hist_size = getenv("L2TP_HISTFILESIZE");
		if (hist_size != NULL) {
			l2tp_histfile_maxsize = strtoul(hist_size, NULL, 0);
		}

		cli_read_history_file(l2tp_histfile);
		cli_run();
	}

	return 0;
}
