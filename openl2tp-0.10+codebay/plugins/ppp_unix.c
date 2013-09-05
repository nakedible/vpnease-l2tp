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
 * Plugin to use the standard UNIX pppd
 */

#include <unistd.h>
#include <fcntl.h>
#include <sys/types.h>
#include <signal.h>
#include <net/ethernet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/stat.h>
#include <unistd.h>

#include <sys/ioctl.h>
#include <linux/if_ether.h>
#include <linux/if_pppox.h>
#include <linux/ppp_defs.h>
#include <linux/if_ppp.h>
#include <linux/if_pppol2tp.h>

#include "usl.h"
#include "l2tp_private.h"

#ifndef offsetof
#define offsetof(type, field) ((int) ((char *) &((type *) 0)->field))
#endif

#define PPP_UNIX_MAX_PPPD_ARGS				(128)

/* FIXME: should be in system's socket.h */
#ifndef SOL_PPPOL2TP
#define SOL_PPPOL2TP	269
#endif

/* One ppp context is used per session. We bump reference counts on
 * the tunnel/session while we hold references to those data
 * structures.
 */
struct ppp_context {
	struct usl_list_head				list;
	uint16_t					tunnel_id;
	uint16_t					session_id;
	uint16_t					peer_tunnel_id;
	uint16_t					peer_session_id;
	char						*interface_name;
	struct l2tp_api_ppp_profile_msg_data		*ppp_profile_data;
	uint16_t					mtu;
	uint16_t					mru;
	int						closed;
	pid_t						pid;
	int						trace_flags;
	int						tunnel_fd;
	int						kernel_fd;
	struct l2tp_tunnel const			*tunnel;
	struct l2tp_session const			*session;
};

static USL_LIST_HEAD(ppp_unix_list);

static int ppp_unix_delete(struct ppp_context *ppp);
static int ppp_unix_pppd_terminate(struct ppp_context *ppp, uint16_t tunnel_id, uint16_t session_id);

/* Used to record previous value of hook so that we can chain them */
static int (*ppp_unix_old_session_created_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id);
static int (*ppp_unix_old_session_deleted_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id);
static int (*ppp_unix_old_session_modified_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id);
static int (*ppp_unix_old_session_up_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id, uint16_t peer_tunnel_id, uint16_t peer_session_id);
static int (*ppp_unix_old_session_down_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id);
static int (*ppp_unix_old_session_get_stats_hook)(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id, struct pppol2tp_ioc_stats *stats);

/* For testing, we use a dummy pppd which dumps its args to a file for analysis and sleeps. */
#ifdef L2TP_TEST
#define PPP_UNIX_PPPD_DUMMY_FILE "./pppd_dummy"
static int ppp_unix_dummy_pppd = 0;
#endif

static int ppp_unix_use_dummy_pppd(void)
{
#ifdef L2TP_TEST
	return ppp_unix_dummy_pppd;
#else
	return FALSE;
#endif
}

/*****************************************************************************
 * Unix pppd command line builder
 *****************************************************************************/

typedef enum {
	PPP_UNIX_FIELD_INTEGER,
	PPP_UNIX_FIELD_BITMASK
} ppp_unix_arg_type;

struct ppp_unix_pppd_arg {
	const char              *string;
	ppp_unix_arg_type       type;
	int                     offset;
	int                     data_size;
	uint32_t		mask;
	uint32_t		flags;
};

#define PPP_UNIX_PARAM(_string, _field, _flags, _type, _mask)	\
	{ _string, PPP_UNIX_FIELD_##_type, offsetof(struct l2tp_api_ppp_profile_msg_data, _field), \
	  sizeof(((struct l2tp_api_ppp_profile_msg_data *)0)->_field), _mask, \
	  L2TP_API_PPP_PROFILE_FLAG_##_flags }

static const struct ppp_unix_pppd_arg ppp_unix_pppd_args[] = {
	PPP_UNIX_PARAM("asyncmap",		asyncmap,			ASYNCMAP,			INTEGER, 0),
	PPP_UNIX_PARAM("chap-interval",		chap_interval,			CHAP_INTERVAL,			INTEGER, 0),
	PPP_UNIX_PARAM("chap-max-challenge",	chap_max_challenge,		CHAP_MAX_CHALLENGE,		INTEGER, 0),
	PPP_UNIX_PARAM("chap-restart",		chap_restart,			CHAP_RESTART,			INTEGER, 0),
	PPP_UNIX_PARAM("pap-max-authreq", 	pap_max_auth_requests,		PAP_MAX_AUTH_REQUESTS,		INTEGER, 0),
	PPP_UNIX_PARAM("pap-restart", 	        pap_restart_interval,		PAP_RESTART_INTERVAL,		INTEGER, 0),
	PPP_UNIX_PARAM("pap-timeout", 	        pap_timeout,			PAP_TIMEOUT,			INTEGER, 0),
	PPP_UNIX_PARAM("idle", 	       	        idle_timeout,			IDLE_TIMEOUT,			INTEGER, 0),
	PPP_UNIX_PARAM("ipcp-max-configure",    ipcp_max_config_requests,	IPCP_MAX_CONFIG_REQUESTS,	INTEGER, 0),
	PPP_UNIX_PARAM("ipcp-max-failure", 	ipcp_max_config_naks,		IPCP_MAX_CONFIG_NAKS, 		INTEGER, 0),
	PPP_UNIX_PARAM("ipcp-max-terminate",    ipcp_max_terminate_requests,	IPCP_MAX_TERMINATE_REQUESTS,	INTEGER, 0),
	PPP_UNIX_PARAM("ipcp-restart", 	        ipcp_retransmit_interval,	IPCP_RETRANSMIT_INTERVAL,	INTEGER, 0),
	PPP_UNIX_PARAM("lcp-echo-failure", 	lcp_echo_failure_count,		LCP_ECHO_FAILURE_COUNT,		INTEGER, 0),
	PPP_UNIX_PARAM("lcp-echo-interval",     lcp_echo_interval,		LCP_ECHO_INTERVAL,		INTEGER, 0),
	PPP_UNIX_PARAM("lcp-max-configure", 	lcp_max_config_requests,	LCP_MAX_CONFIG_REQUESTS,	INTEGER, 0),
	PPP_UNIX_PARAM("lcp-max-failure", 	lcp_max_config_naks,		LCP_MAX_CONFIG_NAKS,		INTEGER, 0),
	PPP_UNIX_PARAM("lcp-max-terminate",	lcp_max_terminate_requests,	LCP_MAX_TERMINATE_REQUESTS,	INTEGER, 0),
	PPP_UNIX_PARAM("lcp-restart",       	lcp_retransmit_interval,	LCP_RETRANSMIT_INTERVAL,	INTEGER, 0),
	PPP_UNIX_PARAM("maxconnect",        	max_connect_time,		MAX_CONNECT_TIME,		INTEGER, 0),
	PPP_UNIX_PARAM("maxfail", 		max_failure_count,		MAX_FAILURE_COUNT,		INTEGER, 0),
	{ NULL,	PPP_UNIX_FIELD_INTEGER, -1, 0, 0, 0 }
};


/* Authentication flags are best handled separately. */
/* Note that this separate handling is now almost usesless because only the
 * auth/noauth options are really handled differently here. */
struct ppp_unix_pppd_arg_reverse {
	const char              *string;
	const char              *reverse;
	uint32_t		mask;
};

static const struct ppp_unix_pppd_arg_reverse ppp_unix_pppd_args_auth[] = {
	{ "refuse-eap", NULL, L2TP_API_PPP_AUTH_REFUSE_EAP},
	{ "refuse-mschap-v2", NULL, L2TP_API_PPP_AUTH_REFUSE_MSCHAPV2},
	{ "refuse-mschap", NULL, L2TP_API_PPP_AUTH_REFUSE_MSCHAP},
	{ "refuse-chap", NULL, L2TP_API_PPP_AUTH_REFUSE_CHAP},
	{ "refuse-pap", NULL, L2TP_API_PPP_AUTH_REFUSE_PAP},
	{ "require-eap", NULL, L2TP_API_PPP_REQUIRE_EAP},
	{ "require-mschap-v2", NULL, L2TP_API_PPP_REQUIRE_MSCHAPV2},
	{ "require-mschap", NULL, L2TP_API_PPP_REQUIRE_MSCHAP},
	{ "require-chap", NULL, L2TP_API_PPP_REQUIRE_CHAP},
	{ "require-pap", NULL, L2TP_API_PPP_REQUIRE_PAP},
	{ "noauth", "auth", L2TP_API_PPP_REQUIRE_NONE},
	{ NULL, NULL, 0}
};

static const struct ppp_unix_pppd_arg_reverse ppp_unix_pppd_args_comp[] = {
	{ "mppc", "nomppc", L2TP_API_PPP_COMP_MPPC},
	{ NULL, "noaccomp", L2TP_API_PPP_COMP_ACCOMP},
	{ NULL, "nopcomp", L2TP_API_PPP_COMP_PCOMP},
	{ NULL, "nobsdcomp", L2TP_API_PPP_COMP_BSDCOMP},
	{ NULL, "nodeflate", L2TP_API_PPP_COMP_DEFLATE},
	{ NULL, "nopredictor1", L2TP_API_PPP_COMP_PREDICTOR1},
	{ NULL, "novj", L2TP_API_PPP_COMP_VJ},
	{ NULL, "novjccomp", L2TP_API_PPP_COMP_CCOMP_VJ},
	{ NULL, NULL, 0}
};

/* Convert param structure to argv[]. Return argc.
 */
static char buf[512];

static int ppp_unix_params_to_argv(struct ppp_context *ppp, struct l2tp_api_ppp_profile_msg_data *params, int argc, char *argv[])
{
	int int_val;
	uint32_t bit_val;
	const struct ppp_unix_pppd_arg *ppp_arg;
	int arg = 0;
	struct in_addr ip;

	argv[arg++] = "pppd";

	/* MPPE encryption is not desirable, but pppd mppe option
	   must still be settable because it controls the mppe
	   and thus mppc negotiation. 

	   NB: Leaving mppe option out does not seem to produce a
	   sensible default, but it is still possible to configure
	   it that way by not touching the configuration option.

	   NB: the "required" mppe option is not used at all.
	*/
	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_MPPE) {
		if (params->mppe) {
			/* NB: suboptions are required if mppe
			 * option is at all present!
			 * Disable all encryptions to be sure.
			 */
			argv[arg++] = "mppe";
			argv[arg++] = "no40,no56,no128";
		} else {
			argv[arg++] = "nomppe";
		}
	}

	/* New auth-option handling. */
	{
		int offset = offsetof(struct l2tp_api_ppp_profile_msg_data, auth_flags);
		const struct ppp_unix_pppd_arg_reverse *ppp_arg_auth = &ppp_unix_pppd_args_auth[0];

		while (ppp_arg_auth->string || ppp_arg_auth->reverse) {
			bit_val = (*(int *) (((char *) params) + offset)) & ppp_arg_auth->mask;
			if (bit_val) {
				if (ppp_arg_auth->string != NULL) {
					argv[arg++] = (char *) ppp_arg_auth->string;
				}
			} else {
				if (ppp_arg_auth->reverse != NULL) {
					argv[arg++] = (char *) ppp_arg_auth->reverse;
				}
			}
			ppp_arg_auth++;
		}
	}

	/* New compression-option handling. */
	{
		int offset = offsetof(struct l2tp_api_ppp_profile_msg_data, comp_flags);
		const struct ppp_unix_pppd_arg_reverse *ppp_arg_comp = &ppp_unix_pppd_args_comp[0];

		while (ppp_arg_comp->string || ppp_arg_comp->reverse) {
			bit_val = (*(int *) (((char *) params) + offset)) & ppp_arg_comp->mask;
			if (bit_val) {
				if (ppp_arg_comp->string != NULL) {
					argv[arg++] = (char *) ppp_arg_comp->string;
				}
			} else {
				if (ppp_arg_comp->reverse != NULL) {
					argv[arg++] = (char *) ppp_arg_comp->reverse;
				}
			}
			ppp_arg_comp++;
		}
	}


	/* Options for "required" (asked) compression methods. */
	/* These override "noxx" flags earlier, but should not be a problem. */
	{
		if (params->comp_flags & L2TP_API_PPP_COMP_ASK_BSDCOMP) {
			argv[arg++] = "bsdcomp";
			argv[arg++] = "15,15";
		}
		if (params->comp_flags & L2TP_API_PPP_COMP_ASK_DEFLATE) {
			argv[arg++] = "deflate";
			argv[arg++] = "15,15";
		}
	}

	/* Do the difficult cases which aren't in the translation table */
	buf[0] = '\0';
	if (params->flags2 & (L2TP_API_PPP_PROFILE_FLAG_LOCAL_IP_ADDR | L2TP_API_PPP_PROFILE_FLAG_PEER_IP_ADDR)) {
		if (params->local_ip_addr.s_addr != 0) {
			ip.s_addr = params->local_ip_addr.s_addr;
			strcat(&buf[0], inet_ntoa(ip));
		}
		strcat(&buf[0], ":");
		if (params->peer_ip_addr.s_addr != 0) {
			ip.s_addr = params->peer_ip_addr.s_addr;
			strcat(&buf[0], inet_ntoa(ip));
		}
		if (strlen(buf) > 0) {
			argv[arg++] = strdup(buf);
		}
	}

	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_1) {
		ip.s_addr = params->dns_addr_1.s_addr;
		strcpy(&buf[0], inet_ntoa(ip));
		argv[arg++] = "ms-dns";
		argv[arg++] = strdup(buf);
	}
	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_DNS_ADDR_2) {
		ip.s_addr = params->dns_addr_2.s_addr;
		strcpy(&buf[0], inet_ntoa(ip));
		argv[arg++] = "ms-dns";
		argv[arg++] = strdup(buf);
	}
	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_1) {
		ip.s_addr = params->wins_addr_1.s_addr;
		strcpy(&buf[0], inet_ntoa(ip));
		argv[arg++] = "ms-wins";
		argv[arg++] = strdup(buf);
	}
	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_WINS_ADDR_2) {
		ip.s_addr = params->wins_addr_2.s_addr;
		strcpy(&buf[0], inet_ntoa(ip));
		argv[arg++] = "ms-wins";
		argv[arg++] = strdup(buf);
	}
	if ((params->trace_flags & L2TP_DEBUG_PPP) != 0) {
		argv[arg++] = "debug";
		argv[arg++] = "kdebug";
		sprintf(&buf[0], "%d", 7);
		argv[arg++] = strdup(buf);
	}

	if (params->flags & L2TP_API_PPP_PROFILE_FLAG_MTU) {
		argv[arg++] = "mtu";
		sprintf(&buf[0], "%hu", ppp->mtu);
		argv[arg++] = strdup(buf);
	}
	if (params->flags & L2TP_API_PPP_PROFILE_FLAG_MRU) {
		argv[arg++] = "mru";
		sprintf(&buf[0], "%hu", ppp->mru);
		argv[arg++] = strdup(buf);
	}
	if (params->flags & L2TP_API_PPP_PROFILE_FLAG_USE_RADIUS) {
		if (params->use_radius) {
			/* ppp-2.4.2 now has a radius client plugin. If a radius_hint was given, 
			 * assume it's a radius config filename 
			 */
			argv[arg++] = "plugin";
			argv[arg++] = "radius.so";
			if ((params->flags & L2TP_API_PPP_PROFILE_FLAG_RADIUS_HINT) && (OPTSTRING_PTR(params->radius_hint) != NULL)) {
				argv[arg++] = "radius-config-file";
				argv[arg++] = strdup(OPTSTRING(params->radius_hint));
			}
		}
	}
	if (params->flags2 & L2TP_API_PPP_PROFILE_FLAG_USE_AS_DEFAULT_ROUTE) {
		if (params->use_as_default_route) {
			argv[arg++] = "defaultroute";
		}
	}

	/* never use a default IP local address (derived from gethostbyname()) */
	argv[arg++] = "noipdefault";

	/* increase the child wait timeout from the default 5 seconds.
	 * 60 seconds seems to be a good compromise. */
	argv[arg++] = "child-timeout";
	argv[arg++] = "60";

	/* ippool plugin support */
	if ((params->flags2 & L2TP_API_PPP_PROFILE_FLAG_IP_POOL_NAME) && (OPTSTRING_PTR(params->ip_pool_name) != NULL)) {
		argv[arg++] = "plugin";
		argv[arg++] = "ippool.so";
		argv[arg++] = "ippool_name";
		argv[arg++] = strdup(OPTSTRING(params->ip_pool_name));
		if ((params->trace_flags & L2TP_DEBUG_PPP) != 0) {
			argv[arg++] = "ippool_debug";
			argv[arg++] = "1";
		}
	}

	/* By default, use sync mode */
	if (!((params->flags & L2TP_API_PPP_PROFILE_FLAG_SYNC_MODE) &&
	      (params->sync_mode == L2TP_API_PPP_SYNCMODE_ASYNC))) {
		argv[arg++] = "sync";
	}

	/* Now handle each parameter from our translation table. Only
	 * add the arg if the ppp profile indicates that it's been
	 * set.
	 */
	ppp_arg = &ppp_unix_pppd_args[0];
	while (ppp_arg->string) {
		if (ppp_arg->flags & params->flags) {
			switch (ppp_arg->type) {
			case PPP_UNIX_FIELD_INTEGER:
				int_val = (*(int *) (((char *) params) + ppp_arg->offset));
				if (int_val) {
					argv[arg++] = (char *) ppp_arg->string;
					sprintf(&buf[0], "%u", int_val);
					argv[arg++] = strdup(buf);
				}
				break;
			case PPP_UNIX_FIELD_BITMASK:
				bit_val = (*(int *) (((char *) params) + ppp_arg->offset)) & ppp_arg->mask;
				if (bit_val) {
					argv[arg++] = (char *) ppp_arg->string;
				}
				break;
			}
		}
		ppp_arg++;
	}

	if (arg > argc) {
		syslog(LOG_ERR, "Too many pppd arguments to convert");
		return -E2BIG;
	}

	return arg;
}

/*****************************************************************************
 * L2TP socket API
 *****************************************************************************/

static int ppp_unix_socket_connect(int session_fd, int tunnel_fd, struct sockaddr_in const *addr, 
				   uint16_t tunnel_id, uint16_t session_id, uint16_t peer_tunnel_id, uint16_t peer_session_id)
{
	struct sockaddr_pppol2tp sax;
	int fd;

	L2TP_DEBUG(L2TP_FUNC, "%s: session_fd=%d tunnel_fd=%d tid=%hu sid=%hu peer=%hu/%hu addr=%s port=%hu",
		   __FUNCTION__, session_fd, tunnel_fd, tunnel_id, session_id,
		   peer_tunnel_id, peer_session_id, inet_ntoa(addr->sin_addr), htons(addr->sin_port));

	/* Note, the target socket must be bound already, else it will not be ready */  
	sax.sa_family = AF_PPPOX;
	sax.sa_protocol = PX_PROTO_OL2TP;
	sax.pppol2tp.pid = 0;
	sax.pppol2tp.fd = tunnel_fd;
	sax.pppol2tp.addr.sin_addr.s_addr = addr->sin_addr.s_addr;
	sax.pppol2tp.addr.sin_port = addr->sin_port;
	sax.pppol2tp.addr.sin_family = AF_INET;
	sax.pppol2tp.s_tunnel  = tunnel_id;
	sax.pppol2tp.s_session = session_id;
	sax.pppol2tp.d_tunnel  = peer_tunnel_id;
	sax.pppol2tp.d_session = peer_session_id;
  
	fd = connect(session_fd, (struct sockaddr *)&sax, sizeof(sax));
	if (fd < 0 )	{
		return -errno;
	}
	return 0;
}

/*****************************************************************************
 * Internal implementation 
 *****************************************************************************/

static struct ppp_context *ppp_unix_find_by_id(uint16_t tunnel_id, uint16_t session_id)
{
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	struct ppp_context *ppp;

	L2TP_DEBUG(L2TP_FUNC, "%s: look for %hu/%hu", __FUNCTION__, tunnel_id, session_id);

	usl_list_for_each(walk, tmp, &ppp_unix_list) {
		ppp = usl_list_entry(walk, struct ppp_context, list);
		L2TP_DEBUG(L2TP_FUNC, "%s: at %hu/%hu", __FUNCTION__, ppp->tunnel_id, ppp->session_id);
		if ((ppp->tunnel_id == tunnel_id) && (ppp->session_id == session_id)) {
			return ppp;
		}
	}

	return NULL;
}

/* We come here when one of our pppds terminates. Called from USL.
 */
static void ppp_unix_pppd_terminated(void *arg, int signal)
{
	struct ppp_context *ppp = arg;

	if (ppp == NULL) {
		L2TP_DEBUG(L2TP_FUNC, "%s: unknown/unknown terminated on signal %d, ppp context already gone (maybe late pppd exit).", __FUNCTION__, signal);
		return;
	}

	L2TP_DEBUG(L2TP_FUNC, "%s: %hu/%hu terminated on signal %d", __FUNCTION__, ppp->tunnel_id, ppp->session_id, signal);

	if (!ppp->closed) {
		ppp->closed = 1;
		l2tp_session_close_event(ppp->tunnel_id, ppp->session_id);
	}
}

/* Called on SESSION_DOWN. We find our ppp context and kill its pppd.
 */
static int ppp_unix_pppd_terminate(struct ppp_context *ppp, uint16_t tunnel_id, uint16_t session_id)
{
	if (ppp == NULL) {
		ppp = ppp_unix_find_by_id(tunnel_id, session_id);
		if (ppp == NULL) {
			return 0;
		}
	}

	L2TP_DEBUG(L2TP_FUNC, "%s: pid=%d", __FUNCTION__, ppp->pid);

	/* If pppd is still alive, kill it. The pid handler will tell
	 * the session, which in turn lead to a SESSION_DELETED event
	 * where we will clean up.
	 */
	if ((ppp->pid != 0) && (ppp->session != NULL)) {
		int pid = ppp->pid;
		struct l2tp_session *session = ppp->session;

		l2tp_session_log(ppp->session, L2TP_DATA, LOG_INFO, "%s: stopping unix pppd pid %d", l2tp_session_get_name(ppp->session), pid);
		ppp->pid = 0;

		ppp->session = NULL;
		l2tp_session_dec_use_count((void *) session);
		kill(pid, SIGTERM);
	} else {
		ppp_unix_pppd_terminated(ppp, SIGTERM);
	}

	return 0;
}

#if 0
/* Allow a debugger to attach */
int ppp_unix_debugger_wait = 1;
#endif

/* Spawn pppd. This is horrible because we must build command line
 * arguments for pppd using our binary data structures. PPP parameters
 * come from a ppp profile. Some additional L2TP-specific stuff comes
 * from the session config.
 */
static char tmpstr[512];

static int ppp_unix_pppd_spawn(struct ppp_context *ppp)
{
	pid_t pid;
	int result = 0;
	struct l2tp_session_config const *scfg;

	pid = usl_pid_safe_fork();
	if (pid < 0) {
		l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "unable to fork pppd instance for session %hu/%hu: %m", 
				 ppp->tunnel_id, ppp->session_id);
		result = pid;
		goto out;
	}
	if (pid == 0) { 
		/* child */
		char *argv[PPP_UNIX_MAX_PPPD_ARGS];
		int session_fd;
		int arg;
#if 0
		while (ppp_unix_debugger_wait) {
			sleep(1);
		}
#endif		
		scfg = l2tp_session_get_config(ppp->session);

		/* PPP proxy is not supported, but fake that it is supported if testing with a dummy pppd */
		if (scfg->use_ppp_proxy && !ppp_unix_use_dummy_pppd()) {
			l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "sess %hu/%hu: ppp proxy requested but not supported by UNIX pppd", 
					 ppp->tunnel_id, ppp->session_id);
			result = -EOPNOTSUPP;
			goto abort_child;
		}

		if (scfg->do_pmtu_discovery) {
			ppp->ppp_profile_data->flags |= (L2TP_API_PPP_PROFILE_FLAG_MTU | L2TP_API_PPP_PROFILE_FLAG_MRU);
			ppp->mtu = ppp->mru = scfg->mtu;
		}

		memset(&argv[0], 0, sizeof(argv));
		arg = ppp_unix_params_to_argv(ppp, ppp->ppp_profile_data, PPP_UNIX_MAX_PPPD_ARGS, &argv[0]);
		argv[arg++] = "nodetach";
		if (scfg->user_name != NULL) {
			argv[arg++] = "user";
			argv[arg++] = strdup(scfg->user_name);
		}
		if (scfg->user_password != NULL) {
			argv[arg++] = "password";
			argv[arg++] = strdup(scfg->user_password);
		}
		argv[arg++] = "local";

		if (ppp->ppp_profile_data->multilink) {
			argv[arg++] = "multilink";
		}

		argv[arg++] = "plugin";
		argv[arg++] = "pppol2tp.so";

		if (!ppp_unix_use_dummy_pppd()) {
			int flags;
			session_fd = socket(AF_PPPOX, SOCK_DGRAM, PX_PROTO_OL2TP);
			if (session_fd < 0) {
				l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "sess %hu/%hu: unable to open pppox socket: %m", 
						 ppp->tunnel_id, ppp->session_id);
				result = -errno;
				goto abort_child;
			}
			flags = fcntl(session_fd, F_GETFL);
			if (flags == -1 || fcntl(session_fd, F_SETFL, flags | O_NONBLOCK) == -1) {
				l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "sess %hu/%hu: unable to set socket nonblock: %m");
				result = -errno;
				goto abort_child;
			}

			result = ppp_unix_socket_connect(session_fd, ppp->tunnel_fd, l2tp_tunnel_get_peer_addr(ppp->tunnel),
							 ppp->tunnel_id, ppp->session_id, 
							 ppp->peer_tunnel_id, ppp->peer_session_id);
			if (result < 0) {
				l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "sess %hu/%hu: unable to connect pppox socket: %m", 
						 ppp->tunnel_id, ppp->session_id);
				result = -errno;
				close(session_fd);
				goto abort_child;
			}
		} else {
			l2tp_session_log(ppp->session, L2TP_DATA, LOG_DEBUG, "sess %hu/%hu: using dummy pppd", 
					 ppp->tunnel_id, ppp->session_id);
			session_fd = 0;
		}

		/* Add pppol2tp arguments.
		 * NOTE: since there is no userspace interface to pppd once it is running,
		 * we cannot modify any PPP parameters once pppd has been started. These
		 * parameters are therefore unmodifiable when using UNIX pppd.
		 */

		argv[arg++] = "pppol2tp";
		snprintf(&tmpstr[0], 16, "%d", session_fd);
		argv[arg++] = strdup(tmpstr);

		if (scfg->use_sequence_numbers) {
			argv[arg++] = "pppol2tp_send_seq";
		}
		if (scfg->sequencing_required) {
			argv[arg++] = "pppol2tp_recv_seq";
		}
		if (scfg->reorder_timeout) {
			argv[arg++] = "pppol2tp_reorderto";
			snprintf(&tmpstr[0], 32, "%u", scfg->reorder_timeout);
			argv[arg++] = strdup(tmpstr);
		}
		if (l2tp_session_is_lns(ppp->session)) {
			argv[arg++] = "pppol2tp_lns_mode";
			argv[arg++] = "pppol2tp_tunnel_id";
			snprintf(&tmpstr[0], 32, "%hu", ppp->tunnel_id);
			argv[arg++] = strdup(tmpstr);
			argv[arg++] = "pppol2tp_session_id";
			snprintf(&tmpstr[0], 32, "%hu", ppp->session_id);
			argv[arg++] = strdup(tmpstr);
		} else {
			if ((scfg->user_password != NULL) && (scfg->user_name != NULL)) {
				argv[arg++] = "ipparam";
				snprintf(&tmpstr[0], 500, "client:%s:%s", scfg->user_name, scfg->user_password);
				argv[arg++] = strdup(tmpstr);
			}
		}
		if (scfg->trace_flags != 0) {
			int flags = 0;
			if (scfg->trace_flags & L2TP_DEBUG_API) {
				flags |= PPPOL2TP_MSG_CONTROL;
			}
			if (scfg->trace_flags & L2TP_DEBUG_XPRT) {
				flags |= PPPOL2TP_MSG_SEQ;
			}
			if (scfg->trace_flags & L2TP_DEBUG_DATA) {
				flags |= PPPOL2TP_MSG_DATA;
			}
			if (scfg->trace_flags & L2TP_DEBUG_FUNC) {
				flags |= PPPOL2TP_MSG_DEBUG;
			}
			if (flags != 0) {
				argv[arg++] = "pppol2tp_debug_mask";
				snprintf(&tmpstr[0], 32, "%u", flags);
				argv[arg++] = strdup(tmpstr);
			}
		}

		/* Set interface name if not using multilink */
		if (!ppp->ppp_profile_data->multilink) {
			if (scfg->interface_name != NULL) {
				ppp->interface_name = strdup(scfg->interface_name);
			} else {
				snprintf(&tmpstr[0], 32, "l2tp%hu-%hu", ppp->tunnel_id, ppp->session_id);
				ppp->interface_name = strdup(tmpstr);
			}
			if (ppp->interface_name == NULL) {
				result = -ENOMEM;
				close(session_fd);
				goto abort_child;
			}
			argv[arg++] = "pppol2tp_ifname";
			argv[arg++] = ppp->interface_name;
		}

		argv[arg++] = NULL;

		l2tp_session_log(ppp->session, L2TP_DATA, LOG_DEBUG, 
				 "sess %hu/%hu:"
				 /* 0  1  2  3  4  5  6  7  8  9 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*10 11 12 13 14 15 16 17 18 19 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*20 21 22 23 24 25 26 27 28 29 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*30 31 32 33 34 35 36 37 38 39 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*40 41 42 43 44 45 46 47 48 49 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*50 51 52 53 54 55 56 57 58 59 */
				 " %s %s %s %s %s %s %s %s %s %s"
				 /*60 */
				 " %s",
				 ppp->tunnel_id, ppp->session_id,
				 argv[0]  ? argv[0]  : "", argv[1]  ? argv[1]  : "", argv[2]  ? argv[2]  : "",
				 argv[3]  ? argv[3]  : "", argv[4]  ? argv[4]  : "", argv[5]  ? argv[5]  : "",
				 argv[6]  ? argv[6]  : "", argv[7]  ? argv[7]  : "", argv[8]  ? argv[8]  : "",
				 argv[9]  ? argv[9]  : "", argv[10] ? argv[10] : "", argv[11] ? argv[11] : "",
				 argv[12] ? argv[12] : "", argv[13] ? argv[13] : "", argv[14] ? argv[14] : "",
				 argv[15] ? argv[15] : "", argv[16] ? argv[16] : "", argv[17] ? argv[17] : "",
				 argv[18] ? argv[18] : "", argv[19] ? argv[19] : "", argv[20] ? argv[20] : "",
				 argv[21] ? argv[21] : "", argv[22] ? argv[22] : "", argv[23] ? argv[23] : "",
				 argv[24] ? argv[24] : "", argv[25] ? argv[25] : "", argv[26] ? argv[26] : "",
				 argv[27] ? argv[27] : "", argv[28] ? argv[28] : "", argv[29] ? argv[29] : "",
				 argv[30] ? argv[30] : "", argv[31] ? argv[31] : "", argv[32] ? argv[32] : "",
				 argv[33] ? argv[33] : "", argv[34] ? argv[34] : "", argv[35] ? argv[35] : "",
				 argv[36] ? argv[36] : "", argv[37] ? argv[37] : "", argv[38] ? argv[38] : "",
				 argv[39] ? argv[39] : "", argv[40] ? argv[40] : "", argv[41] ? argv[41] : "",
				 argv[42] ? argv[42] : "", argv[43] ? argv[43] : "", argv[44] ? argv[44] : "",
				 argv[45] ? argv[45] : "", argv[46] ? argv[46] : "", argv[47] ? argv[47] : "",
				 argv[48] ? argv[48] : "", argv[49] ? argv[49] : "", argv[50] ? argv[50] : "",
				 argv[51] ? argv[51] : "", argv[52] ? argv[52] : "", argv[53] ? argv[53] : "",
				 argv[54] ? argv[54] : "", argv[55] ? argv[55] : "", argv[56] ? argv[56] : "",
				 argv[57] ? argv[57] : "", argv[58] ? argv[58] : "", argv[59] ? argv[59] : "",
				 argv[60] ? "..." : "");

		fcntl(session_fd,  F_SETFD, 0);   /* Remove close on exec flag */

#ifdef L2TP_TEST
		/* For testing, if a pppd_dummy executable exists in the current directory, run it
		 * instead of the real pppd. 
		 */
		result = execv(PPP_UNIX_PPPD_DUMMY_FILE, argv);
#endif
    
		result = execv(L2TP_PPP_UNIX_PPPD_PATH, argv);

		/* If we get here, exec() failed. Log that fact and exit */
		l2tp_log(LOG_ERR, "sess %hu/%hu: pppd could not be started: %s", 
			 ppp->tunnel_id, ppp->session_id, strerror(errno));
		exit(-errno);
	} else {
		/* parent */
		l2tp_session_log(ppp->session, L2TP_DATA, LOG_DEBUG, "sess %hu/%hu: spawned pppd pid=%d", 
				 ppp->tunnel_id, ppp->session_id, pid);
		ppp->pid = pid;

		result = usl_pid_record_child(pid, ppp_unix_pppd_terminated, ppp);
		if (result < 0) {
			l2tp_session_log(ppp->session, L2TP_DATA, LOG_ERR, "sess %hu/%hu: failed to track pppd child pid %d. Aborting.", 
					 ppp->tunnel_id, ppp->session_id, pid);
			ppp_unix_pppd_terminate(ppp, 0, 0);
		}
	}

out:
	L2TP_DEBUG(L2TP_FUNC, "%s: result=%d", __FUNCTION__, result);
	return result;

abort_child:
	L2TP_DEBUG(L2TP_FUNC, "%s: child aborting, result=%d", __FUNCTION__, result);
	exit(result);
}

/* Get PPP parameter data from the profile.
 */
static int ppp_unix_param_defaults(struct ppp_context *ppp, char *ppp_profile_name)
{
	l2tp_api_ppp_profile_msg_data *profile;
	int result = 0;

	profile = calloc(1, sizeof(*profile));
	if (profile == NULL) {
		result = -ENOMEM;
		goto out;
	}

	if (ppp_profile_name == NULL) {
		ppp_profile_name = L2TP_API_PPP_PROFILE_DEFAULT_PROFILE_NAME;
	}

	result = l2tp_ppp_profile_get(ppp_profile_name, profile);
	if (result < 0) {
		L2TP_DEBUG(L2TP_API, "Ppp profile '%s' not found", ppp_profile_name);
		free(profile);
		return result;
	}

	ppp->ppp_profile_data = profile;

	ppp->trace_flags = profile->trace_flags;

out:
	return result;
}

/*****************************************************************************
 * Context management
 *****************************************************************************/

static int ppp_unix_delete(struct ppp_context *ppp)
{
	if (ppp->ppp_profile_data != NULL) {
		l2tp_ppp_profile_msg_free(ppp->ppp_profile_data);
	}

	/* Use temp variable to hold pointer in order to avoid doing
	 * double cleanup in case use count decrease causes session
	 * or tunnel termination.
	 */
	if (ppp->tunnel != NULL) {
		struct l2tp_tunnel *tunnel = ppp->tunnel;
		ppp->tunnel = NULL;
		l2tp_tunnel_dec_use_count((void *) tunnel);
	}
	if (ppp->session != NULL) {
		struct l2tp_session *session = ppp->session;
		ppp->session = NULL;
		l2tp_session_dec_use_count((void *) session);
	}

	if (ppp->interface_name != NULL) {
		free(ppp->interface_name);
	}
	usl_list_del(&ppp->list);

#ifdef DEBUG
	memset(ppp, 0xe9, sizeof(*ppp));
#endif
	free(ppp);

	return 0;
}

static int ppp_unix_create(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id)
{
	struct ppp_context *ppp = NULL;
	int result = 0;
	struct l2tp_tunnel const *tunnel;
	struct l2tp_session_config const *scfg;

	ppp = ppp_unix_find_by_id(tunnel_id, session_id);
	if (ppp != NULL) {
		/* Nothing to do if already exists - it just means we got multiple create events */
		result = -EEXIST;
		goto out;
	}

	/* Allocate a new ppp context */
	ppp = calloc(1, sizeof(struct ppp_context));
	if (ppp == NULL) {
		result = -ENOMEM;
		l2tp_stats.no_ppp_resources++;
		goto err;
	}

	USL_LIST_HEAD_INIT(&ppp->list);

	tunnel = l2tp_session_get_tunnel(session);
	ppp->tunnel_id = tunnel_id;
	ppp->session_id = session_id;
	l2tp_tunnel_inc_use_count((void *) tunnel);
	ppp->tunnel = tunnel;
	ppp->tunnel_fd = l2tp_tunnel_get_fd(tunnel);
	ppp->kernel_fd = l2tp_xprt_get_kernel_fd(tunnel);
	l2tp_session_inc_use_count((void *) session);
	ppp->session = session;

	/* Fill with values from the specified PPP profile. Use default profile if none is specified. */
	scfg = l2tp_session_get_config(session);
	result = ppp_unix_param_defaults(ppp, scfg->ppp_profile_name);
	if (result < 0) {
		goto err;
	}

	/* The PPP session's MTU is derived from the PPP profile and tunnel's MTU */
	ppp->mtu = ppp->mru = l2tp_tunnel_get_mtu(tunnel);
	if (ppp->ppp_profile_data->mtu < ppp->mtu) {
		ppp->mtu = ppp->ppp_profile_data->mtu;
	}
	if (ppp->ppp_profile_data->mru < ppp->mru) {
		ppp->mru = ppp->ppp_profile_data->mru;
	}

	/* Link it to our list of ppps */
	usl_list_add(&ppp->list, &ppp_unix_list);

	return 0;

err:
	if (ppp != NULL) {
		ppp_unix_delete(ppp);
	}

out:
	return result;
}

/*****************************************************************************
 * Hooks
 * These functions are called by OpenL2TP when certain events occur.
 * We use the events to start/stop pppd.
 * SESSION_CREATED	- create a new context to handle ppp on the session
 * SESSION_UP		- spawn a pppd
 * SESSION_DOWN		- stop (kill) pppd and tell session in case it doesn't
 *			  yet know that ppp has died.
 * SESSION_DELETED	- destroy our ppp context
 *****************************************************************************/

static int ppp_unix_session_created(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id)
{
	int result = 0;

	if (ppp_unix_old_session_created_hook != NULL) {
		result = (*ppp_unix_old_session_created_hook)(session, tunnel_id, session_id);
	}

	L2TP_DEBUG(L2TP_DATA, "%s: %s: tid=%hu sid=%hu", __FUNCTION__, l2tp_session_get_name(session),
		   tunnel_id, session_id);

	if (result >= 0) {
		l2tp_session_log(session, L2TP_DATA, LOG_INFO, "%s: creating UNIX pppd context", l2tp_session_get_name(session));

		result = ppp_unix_create(session, tunnel_id, session_id);
	}

	return result;
}

static int ppp_unix_session_deleted(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id)
{
	int result = 0;

	if (ppp_unix_old_session_deleted_hook != NULL) {
		result = (*ppp_unix_old_session_deleted_hook)(session, tunnel_id, session_id);
	}

	L2TP_DEBUG(L2TP_DATA, "%s: %s: tid=%hu sid=%hu", __FUNCTION__, l2tp_session_get_name(session),
		   tunnel_id, session_id);

	if (result >= 0) {
		struct ppp_context *ppp = ppp_unix_find_by_id(tunnel_id, session_id);
		if (ppp != NULL) {
			l2tp_session_log(session, L2TP_DATA, LOG_INFO, "%s: cleaning UNIX pppd context", l2tp_session_get_name(session));
			usl_pid_remove_callback_arg(ppp->pid, ppp);
			ppp_unix_delete(ppp);
		}
	}

	return result;
}

static int ppp_unix_session_modified(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id)
{
	int result = 0;
	struct ppp_context *ppp;
	int mtu;
	struct ifreq ifr;
	int tmp_fd;

	if (ppp_unix_old_session_modified_hook != NULL) {
		result = (*ppp_unix_old_session_modified_hook)(session, tunnel_id, session_id);
	}

	L2TP_DEBUG(L2TP_API, "%s: tid=%hu sid=%hu", __FUNCTION__, tunnel_id, session_id);

	ppp = ppp_unix_find_by_id(tunnel_id, session_id);
	if (ppp == NULL) {
		goto out;
	}

	/* MTU changed? */
	mtu = l2tp_tunnel_get_mtu(ppp->tunnel);
	if ((mtu != ppp->mtu) || (mtu != ppp->mru)) {
		l2tp_session_log(session, L2TP_PPP, LOG_INFO, "sess %hu/%hu: changed mtu", 
				 tunnel_id, session_id);

		tmp_fd = socket(AF_INET, SOCK_DGRAM, 0);
		if (tmp_fd >= 0) {
			memset (&ifr, '\0', sizeof (ifr));
			strncpy(ifr.ifr_name, ppp->interface_name, sizeof (ifr.ifr_name));
			ifr.ifr_mtu = mtu;

			result = ioctl(tmp_fd, SIOCSIFMTU, (caddr_t) &ifr);
			close(tmp_fd);
		}     

		/* Unfortunately there is no way to tell pppd to change the MTU of its
		 * file descriptor. ioctl(fd, PPPIOCSMRU/PPPIOCSMTU). pppd really needs
		 * an API to allow these changes...
		 */
		ppp->mtu = mtu;
		ppp->mru = mtu;
	}

		
	/* Parameters of a pppd that is already running cannot be
	 * modified - pppd has no interface to do so.
	 */
out:
	return result;
}

static int ppp_unix_session_up(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id, uint16_t peer_tunnel_id, uint16_t peer_session_id)
{
	struct ppp_context *ppp;
	int result = 0;

	if (ppp_unix_old_session_up_hook != NULL) {
		result = (*ppp_unix_old_session_up_hook)(session, tunnel_id, session_id, peer_tunnel_id, peer_session_id);
	}

	L2TP_DEBUG(L2TP_DATA, "%s: %s: tid=%hu sid=%hu ptid=%hu psid=%hu", __FUNCTION__, l2tp_session_get_name(session),
		   tunnel_id, session_id, peer_tunnel_id, peer_session_id);

	if (result >= 0) {
		ppp = ppp_unix_find_by_id(tunnel_id, session_id);
		if (ppp != NULL) {
			ppp->peer_tunnel_id = peer_tunnel_id;
			ppp->peer_session_id = peer_session_id;
			if (ppp->pid == 0) {
				l2tp_session_log(session, L2TP_DATA, LOG_INFO, "%s: starting UNIX pppd", l2tp_session_get_name(session));
				result = ppp_unix_pppd_spawn(ppp);
			}
		} else {
			l2tp_session_log(session, L2TP_DATA, LOG_ERR, "%s: UNIX pppd context not found", l2tp_session_get_name(session));
			result = -ENOENT;
		}
	}

	return result;
}

static int ppp_unix_session_down(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id)
{
	int result = 0;

	if (ppp_unix_old_session_down_hook != NULL) {
		result = (*ppp_unix_old_session_down_hook)(session, tunnel_id, session_id);
	}

	L2TP_DEBUG(L2TP_DATA, "%s: %s: tid=%hu sid=%hu", __FUNCTION__, l2tp_session_get_name(session),
		   tunnel_id, session_id);

	if (result >= 0) {
		result = ppp_unix_pppd_terminate(NULL, tunnel_id, session_id);
	}

	return result;
}

static int ppp_unix_session_get_stats(struct l2tp_session const *session, uint16_t tunnel_id, uint16_t session_id, struct pppol2tp_ioc_stats *stats)
{
	struct ppp_context *ppp;
	int result = 0;

	if (ppp_unix_old_session_get_stats_hook != NULL) {
		(*ppp_unix_old_session_get_stats_hook)(session, tunnel_id, session_id, stats);
	}

	L2TP_DEBUG(L2TP_DATA, "%s: %s: tid=%hu sid=%hu", __FUNCTION__, l2tp_session_get_name(session),
		   tunnel_id, session_id);

	ppp = ppp_unix_find_by_id(tunnel_id, session_id);
	if ((ppp != NULL) && (ppp->kernel_fd >= 0)) {
		stats->tunnel_id = tunnel_id;
		stats->session_id = session_id;
		L2TP_DEBUG(L2TP_API, "PPP: sess %s: using fd=%d", l2tp_session_get_name(session), ppp->kernel_fd);
		result = ioctl(ppp->kernel_fd, PPPIOCGL2TPSTATS, stats);
		if (result < 0) {
			result = -errno;
			l2tp_session_log(session, L2TP_API, LOG_ERR, "PPP: sess %s: ioctl(PPPIOCGL2TPSTATS) failed: %m", l2tp_session_get_name(session));
			goto out;
		}
	} else {
		L2TP_DEBUG(L2TP_DATA, "%s: %s: no ppp context for tid=%hu sid=%hu fd=%d", __FUNCTION__, l2tp_session_get_name(session),
			   tunnel_id, session_id, ppp ? ppp->tunnel_fd : -1);
	}
out:
	return result;
}

/*****************************************************************************
 * L2TP plugin interface
 *****************************************************************************/

const char l2tp_plugin_version[] = "V0.10";

int l2tp_plugin_init(void)
{	
#ifdef L2TP_TEST
	struct stat statbuf;
	if (stat(PPP_UNIX_PPPD_DUMMY_FILE, &statbuf) == 0) {
		L2TP_DEBUG(L2TP_API, "Using dummy pppd for testing.");
		ppp_unix_dummy_pppd = 1;
	}
#endif

	ppp_unix_old_session_created_hook = l2tp_session_created_hook;
	ppp_unix_old_session_deleted_hook = l2tp_session_deleted_hook;
	ppp_unix_old_session_modified_hook = l2tp_session_modified_hook;
	ppp_unix_old_session_up_hook = l2tp_session_up_hook;
	ppp_unix_old_session_down_hook = l2tp_session_down_hook;
	ppp_unix_old_session_get_stats_hook = l2tp_session_get_stats_hook;

	l2tp_session_created_hook = ppp_unix_session_created;
	l2tp_session_deleted_hook = ppp_unix_session_deleted;
	l2tp_session_modified_hook = ppp_unix_session_modified;
	l2tp_session_up_hook = ppp_unix_session_up;
	l2tp_session_down_hook = ppp_unix_session_down;
	l2tp_session_get_stats_hook = ppp_unix_session_get_stats;

	return 0;
}

void l2tp_plugin_cleanup(void)
{
	struct usl_list_head *walk;
	struct usl_list_head *tmp;
	struct ppp_context *ppp;

	l2tp_session_created_hook = ppp_unix_old_session_created_hook;
	l2tp_session_deleted_hook = ppp_unix_old_session_deleted_hook;
	l2tp_session_modified_hook = ppp_unix_old_session_modified_hook;
	l2tp_session_up_hook = ppp_unix_old_session_up_hook;
	l2tp_session_down_hook = ppp_unix_old_session_down_hook;
	l2tp_session_get_stats_hook = ppp_unix_old_session_get_stats_hook;

	usl_list_for_each(walk, tmp, &ppp_unix_list) {
		ppp = usl_list_entry(walk, struct ppp_context, list);
		ppp_unix_delete(ppp);
	}
}

