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

#include <stdio.h>
#include <stdarg.h>
#include <ctype.h>
#include <unistd.h>

#include <time.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>
#include <fcntl.h>
#include <syslog.h>
#include <netdb.h>
#include <errno.h>
#include <syscall.h>

#include <sys/types.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <signal.h>
#include <setjmp.h>
#include <sys/utsname.h>

#include <wait.h>

#include "usl.h"
#include "l2tp_private.h"

#define L2TP_PID_FILENAME	"/var/run/openl2tpd.pid"

/* Patch information.
 * Each patch adds its version number to this array.
 */
static int l2tp_installed_patches[] = {
	0,			/* end of list */
};

/* Private variables */

static pid_t			l2tp_my_pid = 0;
static int			l2tp_rand_fd = -1;
#ifdef L2TP_DMALLOC
static unsigned long 		l2tp_dmalloc_mark;
#endif

int				l2tp_opt_nodaemon = 0;
unsigned long			l2tp_opt_trace_flags = 0;
int				l2tp_opt_debug = 0;
int				l2tp_opt_udp_port = 0;
#ifdef BIND_ADDRESS_OPTION
unsigned int                    l2tp_opt_ip_address = 0;
#endif
int				l2tp_opt_flags = 0;
int				l2tp_opt_remote_rpc = 0;
int				l2tp_opt_log_facility = LOG_DAEMON;
void		 		*l2tp_sig_notifier = NULL;
uint16_t			l2tp_firmware_revision = 0;
char				*l2tp_kernel_version = NULL;
char				*l2tp_cpu_name = NULL;

struct l2tp_stats		l2tp_stats;


static void l2tp_init(void);
static void l2tp_cleanup(void);
static int l2tp_parse_args(int argc, char **argv);

static void usage(char **argv, int exit_code)
{
	fprintf(stderr, "Usage: %s [-f] [-d debugmask] [-u udpport] [-p plugin] [-R]\n"
		"	[-L facility] [-h]\n", argv[0]);
	fprintf(stderr, 
		"\t-h                   This message\n"
		"\t-f                   Run in foreground\n"
		"\t-u <port>            UDP port\n"
#ifdef BIND_ADDRESS_OPTION
		"\t-a <address>         Bind address\n"
#endif
		"\t-p <plugin>          Load plugin\n"
		"\t-R                   Enable remote management (SUN RPC)\n"
		"\t-L <facility>        Send syslog messages to the specified facility\n"
 		"\t                     local0..local7\n"
#ifdef DEBUG
		"\t-D                   Enable verbose debug messages\n"
#endif
		"\t-d <flags>           Enable debug trace messages\n");
	exit(exit_code);
}

int main(int argc, char **argv)
{
	int result;
	int log_flags = LOG_PID;
	struct utsname name;
	int fd;
	char pidstr[10];

	/* Parse arguments */
	result = l2tp_parse_args(argc, argv);
	if (result < 0) {
		fprintf(stderr, "Invalid argument\n");
		return result;
	}

	/* Create a pid file, error if already exists */
	fd = open(L2TP_PID_FILENAME, O_WRONLY | O_CREAT | O_EXCL, 0660);
	if (fd < 0) {
		if (errno == EEXIST) {
			fprintf(stderr, "File %s already exists. Is %s already running?\n",
				L2TP_PID_FILENAME, argv[0]);
		} else {
			fprintf(stderr, "File %s: %m", L2TP_PID_FILENAME);
		}
		exit(1);
	}

	/* Get system kernel info, which is used to build our vendor name */
	result = uname(&name);
	if (result < 0) {
		fprintf(stderr, "Failed to get system version info: %m");
		return result;
	}
	l2tp_kernel_version = strdup(name.release);
	l2tp_cpu_name = strdup(name.machine);
	if ((l2tp_kernel_version == NULL) || (l2tp_cpu_name == NULL)) {
		fprintf(stderr, "Out of memory\n");
		return -1;
	}
	l2tp_firmware_revision = (((L2TP_APP_MAJOR_VERSION & 0x0f) << 4) |
				  ((L2TP_APP_MINOR_VERSION & 0x0f) << 0));

	/* Become a daemon */
	if (!l2tp_opt_nodaemon) {
		usl_daemonize();
	}

	/* We write the PID file AFTER the double-fork */
	sprintf(&pidstr[0], "%d", getpid());
	if (write(fd, &pidstr[0], strlen(pidstr)) < 0)
		syslog(LOG_WARNING, "Failed to write pid file %s", L2TP_PID_FILENAME);
	close(fd);

	/* Open the syslog */
	if (l2tp_opt_debug) {
		log_flags |= LOG_NDELAY;
	}
	openlog("openl2tpd", log_flags, l2tp_opt_log_facility);
	setlogmask(LOG_UPTO(LOG_DEBUG));
	l2tp_log(LOG_INFO, "Start, trace_flags=%08x%s", l2tp_opt_trace_flags,
		 l2tp_opt_debug ? " (debug enabled)" : "");

	/* Init the app */
	l2tp_init();

	/* Main loop - USL takes care of it */
	usl_main_loop();

	return 0;
}

void l2tp_mem_dump(int level, void *data, int data_len, int hex_only)
{
	int x, y;
	unsigned char *bytep;
	char cbuf[80];
	char nbuf[80];
	char *p;

	bytep = data;
	for (y = 0; y < data_len; y += 16) {
		memset(&cbuf[0], 0, sizeof(cbuf));
		memset(&nbuf[0], 0, sizeof(nbuf));
		p = &nbuf[0];

		for (x = 0; x < 16; x++, bytep++) {
			if ((x + y) >= data_len) {
				break;
			}
			cbuf[x] = isprint(*bytep) ? *bytep : '.';
			p += sprintf(p, "%02x ", *bytep);
		}
		l2tp_log(level, "%8d: %-48s  %s", y, nbuf, hex_only ? "" : cbuf);
	}
}

char *l2tp_buffer_hexify(void *buf, int buf_len)
{
	static char string_buf[80];
	int max_len = (buf_len < ((sizeof(string_buf) - 1) / 3)) ? buf_len : (sizeof(string_buf) - 1) / 3;
	int index;
	char *bufp = &string_buf[0];
	unsigned char *datap = (unsigned char *) buf;

	/* We use 3 chars in the output buffer per octet */
	for (index = 0; index < max_len; index++) {
		bufp += sprintf(bufp, "%02x ", *datap);
		datap++;
	}
	*bufp = '\0';
	
	return &string_buf[0];
}
 

static int l2tp_parse_log_facility(char *arg)
{
	static const struct {
		char *name;
		int facility;
	} codes[] = {
		{ "local0", LOG_LOCAL0 },
		{ "local1", LOG_LOCAL1 },
		{ "local2", LOG_LOCAL2 },
		{ "local3", LOG_LOCAL3 },
		{ "local4", LOG_LOCAL4 },
		{ "local5", LOG_LOCAL5 },
		{ "local6", LOG_LOCAL6 },
		{ "local7", LOG_LOCAL7 },
		{ NULL, 0 }
	};
	int index;

	if (arg == NULL) {
		return -EINVAL;
	}

	for (index = 0; codes[index].name != NULL; index++) {
		if (strcasecmp(arg, codes[index].name) == 0) {
			return codes[index].facility;
		}
	}

	fprintf(stderr, "Expecting local[0-7]\n");
	return -EINVAL;
}

static int l2tp_parse_args(int argc, char **argv)
{
	int opt;
	int result = 0;
	int plugin_loaded = 0;

#ifdef BIND_ADDRESS_OPTION
	while((opt = getopt(argc, argv, "p:a:d:u:L:fRDh")) != -1) {
#else
	while((opt = getopt(argc, argv, "p:d:u:L:fRDh")) != -1) {
#endif
		switch(opt) {
		case 'h':
			usage(argv, 0);
			break;
		case 'f':
			l2tp_opt_nodaemon = 1;
			break;
#ifdef DEBUG
		case 'D':
			l2tp_opt_debug = 1;
			break;
#endif
		case 'd':
			l2tp_opt_trace_flags = l2tp_parse_debug_mask(optarg);
			break;
		case 'p':
			if (l2tp_plugin_load(optarg) < 0) {
				exit(1);
			}
			plugin_loaded = 1;
			break;
		case 'R':
			l2tp_opt_remote_rpc = 1;
			break;
		case 'L':
			l2tp_opt_log_facility = l2tp_parse_log_facility(optarg);
			if (l2tp_opt_log_facility < 0) {
				result = -EINVAL;
			}
			break;
		case 'u':
			sscanf(optarg, "%d", &l2tp_opt_udp_port);
			L2TP_DEBUG(L2TP_API, "Using port %d", l2tp_opt_udp_port);
			break;
#ifdef BIND_ADDRESS_OPTION
		case 'a':
			{
				unsigned char a, b, c, d;
				int r;
				r = sscanf(optarg, "%hhu.%hhu.%hhu.%hhu", &a, &b, &c, &d);
				if (r != 4) {
					result = -EINVAL;
				} else {
					l2tp_opt_ip_address = a*256*256*256 + b*256*256 + c*256 + d;
					L2TP_DEBUG(L2TP_API, "Using address %d", l2tp_opt_ip_address);
				}
			}
			break;
#endif
		default:
			usage(argv, 1);
		}
	}

	/* Load ppp_unix plugin if no other plugin is requested */
	if (!plugin_loaded) {
		if (l2tp_plugin_load("ppp_unix.so") < 0) {
			exit(1);
		}
	}

	return result;
}

static void l2tp_toggle_debug(void)
{
#ifdef USL_DMALLOC
	dmalloc_log_unfreed();
	dmalloc_log_stats();
	dmalloc_log_heap_map();
#endif

	l2tp_opt_debug = !l2tp_opt_debug;
}

static void l2tp_dmalloc_dump(void)
{
#ifdef L2TP_DMALLOC
	dmalloc_log_changed(l2tp_dmalloc_mark, 1, 0, 1);
	l2tp_dmalloc_mark = dmalloc_mark();
	dmalloc_message("DMALLOC MARK set to %lu\n", l2tp_dmalloc_mark);
#endif
}

/* Warn about features not yet supported from one place so they're
 * easier to find...
 */
void l2tp_warn_not_yet_supported(const char *what)
{
	l2tp_log(LOG_WARNING, "WARNING: %s not yet supported", what);
}

/* die - clean up state and exit with the specified status.
 */
static void l2tp_die(void)
{
	static int exiting = 0;

	if (!exiting) {
		exiting = 1;
		l2tp_log(LOG_INFO, "Exiting");
		exit(1);
	} else {
		_exit(1);
	}
}

/* This function is registered as a signal notifier with USL.
 */
static void l2tp_signal_handler(void *arg, int sig)
{
	switch (sig) {
	case SIGUSR1:
		l2tp_toggle_debug();
		break;
	case SIGUSR2:
		l2tp_dmalloc_dump();
		break;
	case SIGTERM:
		/* This is handled in the main loop */
		break;
	default:
		break;
	}
}

void l2tp_make_random_vector(void *buf, int buf_len)
{
	size_t count;

	count = usl_fd_read(l2tp_rand_fd, buf, buf_len);
	if ((count < 0) && (errno != EAGAIN)) {
		l2tp_log(LOG_ERR, "ERROR: problem reading /dev/random: %s", strerror(errno));
		exit(1);
	}
}

int l2tp_random(int min, int max)
{
	float scale = (float) (max - min);

	return min + (int) (scale * rand() / (RAND_MAX + scale));
}

void l2tp_vlog(int level, const char *fmt, va_list ap)
{
	if (l2tp_opt_nodaemon) {
		vprintf(fmt, ap);
		printf("\n");
	} else {
		vsyslog(level, fmt, ap);
	}
	DMALLOC_VMESSAGE(fmt, ap);
}

void l2tp_log(int level, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	l2tp_vlog(level, fmt, ap);
	va_end(ap);
}

static void l2tp_system_log(int level, const char *fmt, ...)
{
	if (l2tp_opt_trace_flags & L2TP_DEBUG_SYSTEM) {
		va_list ap;

		va_start(ap, fmt);
		l2tp_vlog(level, fmt, ap);
		va_end(ap);
	}
}

char *l2tp_system_time(void)
{
	time_t now;
	char *tstr;

	now = time(NULL);
	if (now == -1) {
		return NULL;
	}

	tstr = ctime(&now);
	if (tstr != NULL) {
		return strdup(tstr);
	}
	return NULL;
}

/*****************************************************************************
 * Management interface
 *****************************************************************************/

bool_t l2tp_app_info_get_1_svc(struct l2tp_api_app_msg_data *msg, struct svc_req *req)
{
	int patches_len;

	msg->build_date = strdup(__DATE__);
	msg->build_time = strdup(__TIME__);
	msg->major = L2TP_APP_MAJOR_VERSION;
	msg->minor = L2TP_APP_MINOR_VERSION;
	msg->cookie = L2TP_APP_COOKIE;

	patches_len = sizeof(l2tp_installed_patches) - sizeof(l2tp_installed_patches[0]);
	msg->patches.patches_len = patches_len / sizeof(l2tp_installed_patches[0]);
	if (msg->patches.patches_len > 0) {
		msg->patches.patches_val = malloc(patches_len);
		if (msg->patches.patches_val == NULL) {
			return FALSE;
		}
		memcpy(msg->patches.patches_val, &l2tp_installed_patches[0], patches_len);
	}

	if ((msg->build_date == NULL) || (msg->build_time == NULL)) {
		return FALSE;
	}

	return TRUE;
}

bool_t l2tp_system_get_1_svc(struct l2tp_api_system_msg_data *msg, struct svc_req *req)
{
	int type;
	struct l2tp_api_system_msg_stats *stat;

	memset(msg, 0, sizeof(*msg));

	msg->config.trace_flags = l2tp_opt_trace_flags;
	msg->config.udp_port = l2tp_opt_udp_port;
	msg->config.flags = l2tp_opt_flags;

	/* catch uncopied data errors */
	USL_POISON_MEMORY(&msg->status.stats, 0xaa, sizeof(msg->status.stats));

	msg->status.stats.total_sent_control_frames = l2tp_stats.total_sent_control_frames;
	msg->status.stats.total_rcvd_control_frames = l2tp_stats.total_rcvd_control_frames;
	msg->status.stats.total_control_frame_send_fails = l2tp_stats.total_control_frame_send_fails;
	msg->status.stats.total_retransmitted_control_frames = l2tp_stats.total_retransmitted_control_frames;
	msg->status.stats.event_queue_full_errors = l2tp_stats.event_queue_full_errors;
	msg->status.stats.short_frames = l2tp_stats.short_frames;
	msg->status.stats.wrong_version_frames = l2tp_stats.wrong_version_frames;
	msg->status.stats.unexpected_data_frames = l2tp_stats.unexpected_data_frames;
	msg->status.stats.bad_rcvd_frames = l2tp_stats.bad_rcvd_frames;
	msg->status.stats.no_control_frame_resources = l2tp_stats.no_control_frame_resources;
	msg->status.stats.no_peer_resources = l2tp_stats.no_peer_resources;
	msg->status.stats.no_tunnel_resources = l2tp_stats.no_tunnel_resources;
	msg->status.stats.no_session_resources = l2tp_stats.no_session_resources;
	msg->status.stats.no_ppp_resources = l2tp_stats.no_ppp_resources;
	msg->status.stats.auth_fails = l2tp_stats.auth_fails;
	msg->status.stats.no_matching_tunnel_id_discards = l2tp_stats.no_matching_tunnel_id_discards;
	msg->status.stats.no_matching_session_id_discards = l2tp_stats.no_matching_session_id_discards;
	msg->status.stats.mismatched_tunnel_ids = l2tp_stats.mismatched_tunnel_ids;
	msg->status.stats.mismatched_session_ids = l2tp_stats.mismatched_session_ids;
	msg->status.stats.encode_message_fails = l2tp_stats.encode_message_fails;
	msg->status.stats.ignored_avps = l2tp_stats.ignored_avps;
	msg->status.stats.vendor_avps = l2tp_stats.vendor_avps;
	msg->status.stats.illegal_messages = l2tp_stats.illegal_messages;
	msg->status.stats.unsupported_messages = l2tp_stats.unsupported_messages;
	msg->status.stats.messages.messages_len = L2TP_API_MSG_TYPE_COUNT;
	msg->status.stats.messages.messages_val = calloc(L2TP_API_MSG_TYPE_COUNT, sizeof(*msg->status.stats.messages.messages_val));
	if (msg->status.stats.messages.messages_val == NULL) {
		msg->status.stats.messages.messages_len = 0;
	}
	
	stat = msg->status.stats.messages.messages_val;
	for (type = 0; type < msg->status.stats.messages.messages_len; type++) {
		stat->rx = l2tp_stats.messages[type].rx;
		stat->tx = l2tp_stats.messages[type].tx;
		stat->rx_bad = l2tp_stats.messages[type].rx_bad;
		stat++;
	}
	
	msg->status.stats.too_many_tunnels = l2tp_stats.too_many_tunnels;
	msg->status.stats.too_many_sessions = l2tp_stats.too_many_sessions;
	msg->status.stats.tunnel_setup_failures = l2tp_stats.tunnel_setup_failures;
	msg->status.stats.session_setup_failures = l2tp_stats.session_setup_failures;

	l2tp_tunnel_globals_get(msg);
	l2tp_session_globals_get(msg);

	return TRUE;
}

bool_t l2tp_system_modify_1_svc(struct l2tp_api_system_msg_data msg, int *result, struct svc_req *req)
{
	if (msg.config.flags & L2TP_API_CONFIG_FLAG_TRACE_FLAGS) {
		l2tp_opt_trace_flags = msg.config.trace_flags;
	}
	if (msg.config.flags & L2TP_API_CONFIG_FLAG_RESET_STATISTICS) {
		memset(&l2tp_stats, 0, sizeof(l2tp_stats));
		msg.config.flags &= ~L2TP_API_CONFIG_FLAG_RESET_STATISTICS;
	}
	l2tp_tunnel_globals_modify(&msg, result);
	l2tp_session_globals_modify(&msg, result);

	*result = 0;

	/* Remember all non-default parameters */
	l2tp_opt_flags |= msg.config.flags;
	
	return TRUE;
}

/*****************************************************************************
 * Init and cleanup
 *****************************************************************************/

/* Removes any profiles and resets the default profiles.
 */
void l2tp_restore_default_config(void)
{
	l2tp_opt_flags = 0;

	l2tp_ppp_reinit();
	l2tp_session_reinit();
	l2tp_tunnel_reinit();
	l2tp_peer_reinit();
}

static void l2tp_init(void)
{
	l2tp_log(LOG_INFO, "started");
#ifdef L2TP_DMALLOC
	/* dmalloc debug options are set in the environment. However,
	 * certain options cause problems to this application. We
	 * therefore ensure that the troublesome options are disabled,
	 * regardless of the user's settings.  The disabled options
	 * are: alloc-blank, free-blank, force-linear.  If these
	 * options are enabled, it causes strange problems in the
	 * generated RPC code.
	 */
	dmalloc_debug(dmalloc_debug_current() & 0xff5dffff);
	l2tp_dmalloc_mark = dmalloc_mark();
	if (getenv("DMALLOC_OPTIONS") != NULL) {
		l2tp_log(LOG_WARNING, "DMALLOC debugging enabled");
	}
#endif
	l2tp_my_pid = getpid();

	atexit(l2tp_cleanup);
	L2TP_DEBUG(L2TP_FUNC, "%s (%s %s): trace flags = %08lx", __FUNCTION__, __DATE__, __TIME__, l2tp_opt_trace_flags);
	usl_set_debug(l2tp_opt_debug, l2tp_system_log);

	usl_signal_terminate_hook = l2tp_die;
	usl_signal_init();
	usl_fd_init();
	usl_timer_init();
	usl_pid_init();
	l2tp_net_init();

	l2tp_rand_fd = open("/dev/random", O_RDONLY);
	if (l2tp_rand_fd < 0) {
		fprintf(stderr, "No /dev/random device found. Exiting.\n");
		exit(1);
	}

	usl_signal_notifier_add(l2tp_signal_handler, NULL);

	l2tp_avp_init();
	l2tp_peer_init();
	l2tp_api_init();
	l2tp_xprt_init();
	l2tp_tunnel_init();
	l2tp_session_init();
	l2tp_ppp_init();
}

static void l2tp_cleanup(void)
{
	pid_t pid;

	pid = getpid();
	if (pid != l2tp_my_pid) {
		L2TP_DEBUG(L2TP_FUNC, "%s: not main pid so returning now", __FUNCTION__);
		return;
	}

	l2tp_log(LOG_INFO, "Cleaning up before exiting");

	usl_signal_notifier_remove(l2tp_signal_handler, NULL);

	/* Cleanup all resources */
	l2tp_api_cleanup();
	l2tp_net_cleanup();
	l2tp_avp_cleanup();
	l2tp_ppp_cleanup();
	l2tp_session_cleanup();
	l2tp_xprt_cleanup();
	l2tp_tunnel_cleanup();
	l2tp_peer_cleanup();

	usl_timer_cleanup();
	usl_fd_cleanup();
	usl_signal_cleanup();
	usl_pid_cleanup();

	if (l2tp_rand_fd != 0) {
		close(l2tp_rand_fd);
	}

	L2TP_DEBUG(L2TP_FUNC, "%s: done", __FUNCTION__);

#ifdef L2TP_DMALLOC
	dmalloc_log_changed(l2tp_dmalloc_mark, 1, 0, 1);
	// dmalloc_log_unfreed();
	// dmalloc_log_stats();
	// dmalloc_log_heap_map();
#endif

	/* Remove pid file */
	unlink(L2TP_PID_FILENAME);
}

