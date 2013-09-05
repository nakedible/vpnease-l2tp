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

#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <stdlib.h>
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
#include "ippool_private.h"

/* Patch information.
 * Each patch adds its version number to this array.
 */
static int ippool_installed_patches[] = {
	0,			/* end of list */
};

/* Private variables */

static pid_t			ippool_my_pid = 0;
#ifdef IPPOOL_DMALLOC
static unsigned long 		ippool_dmalloc_mark;
#endif

int				ippool_opt_nodaemon = 0;
int				ippool_opt_debug = 0;
int				ippool_opt_remote_rpc = 0;
int				ippool_opt_log_facility = LOG_DAEMON;

#define IPPOOL_PID_FILENAME    "/var/run/ippoold.pid"

static void ippool_init(void);
static void ippool_cleanup(void);
static int ippool_parse_args(int argc, char **argv);

static void usage(char **argv, int exit_code)
{
	fprintf(stderr, "Usage: %s [-f] [-d debugmask] [-u udpport] [-p plugin] [-R]\n"
		"	[-L facility] [-h]\n", argv[0]);
	fprintf(stderr, 
		"\t-h			This message\n"
		"\t-f			Run in foreground\n"
		"\t-R			Enable remote management (SUN RPC)\n"
		"\t-L <facility>\t	Send syslog messages to the specified facility\n"
 		"\t			local0..local7\n"
		"\t-d			Enable debug trace messages\n");
	exit(exit_code);
}

int main(int argc, char **argv)
{
	int result;
	int log_flags = LOG_PID;
	int fd;
	char pidstr[10];

	/* Parse arguments */
	result = ippool_parse_args(argc, argv);
	if (result < 0) {
		fprintf(stderr, "Invalid argument\n");
		return result;
	}

	/* Create a pid file, error if already exists */
	fd = open(IPPOOL_PID_FILENAME, O_WRONLY | O_CREAT | O_EXCL, 0660);
	if (fd < 0) {
		if (errno == EEXIST) {
			fprintf(stderr, "File %s already exists. Is %s already running?\n",
				IPPOOL_PID_FILENAME, argv[0]);
		} else {
			fprintf(stderr, "File %s: %m", IPPOOL_PID_FILENAME);
		}
		exit(1);
	}

	/* Become a daemon */
	if (!ippool_opt_nodaemon) {
		usl_daemonize();
	}

	/* We write the PID file AFTER the double-fork */
	sprintf(&pidstr[0], "%d", getpid());
	if (write(fd, &pidstr[0], strlen(pidstr)) < 0)
	        syslog(LOG_WARNING, "Failed to write pid file %s", IPPOOL_PID_FILENAME);
	close(fd);

	/* Open the syslog */
	if (ippool_opt_debug) {
		log_flags |= LOG_NDELAY;
	}
	openlog("ippoold", log_flags, ippool_opt_log_facility);
	setlogmask(LOG_UPTO(LOG_DEBUG));
	ippool_log(LOG_INFO, "Start %s", ippool_opt_debug ? " (debug enabled)" : "");

	/* Init the app */
	ippool_init();

	/* Main loop - USL takes care of it */
	usl_main_loop();

	return 0;
}

static int ippool_parse_log_facility(char *arg)
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

static int ippool_parse_args(int argc, char **argv)
{
	int opt;
	int result = 0;

	while((opt = getopt(argc, argv, "dL:fRh")) != -1) {
		switch(opt) {
		case 'h':
			usage(argv, 0);
			break;
		case 'f':
			ippool_opt_nodaemon = 1;
			break;
		case 'd':
			ippool_opt_debug = 1;
			break;
		case 'R':
			ippool_opt_remote_rpc = 1;
			break;
		case 'L':
			ippool_opt_log_facility = ippool_parse_log_facility(optarg);
			if (ippool_opt_log_facility < 0) {
				result = -EINVAL;
			}
			break;
		default:
			usage(argv, 1);
		}
	}

	return result;
}

static void ippool_toggle_debug(void)
{
#ifdef USL_DMALLOC
	dmalloc_log_unfreed();
	dmalloc_log_stats();
	dmalloc_log_heap_map();
#endif

	ippool_opt_debug = !ippool_opt_debug;
}

static void ippool_dmalloc_dump(void)
{
#ifdef IPPOOL_DMALLOC
	dmalloc_log_changed(ippool_dmalloc_mark, 1, 0, 1);
	ippool_dmalloc_mark = dmalloc_mark();
	dmalloc_message("DMALLOC MARK set to %lu\n", ippool_dmalloc_mark);
#endif
}

/* Warn about features not yet supported from one place so they're
 * easier to find...
 */
void ippool_warn_not_yet_supported(const char *what)
{
	ippool_log(LOG_WARNING, "WARNING: %s not yet supported", what);
}

/* die - clean up state and exit with the specified status.
 */
static void ippool_die(void)
{
	static int exiting = 0;

	if (!exiting) {
		exiting = 1;
		ippool_log(LOG_INFO, "Exiting");
		exit(1);
	} else {
		_exit(1);
	}
}

/* This function is registered as a signal notifier with USL.
 */
static void ippool_signal_handler(void *arg, int sig)
{
	switch (sig) {
	case SIGUSR1:
		ippool_toggle_debug();
		break;
	case SIGUSR2:
		ippool_dmalloc_dump();
		break;
	case SIGTERM:
		/* This is handled in the main loop */
		break;
	default:
		break;
	}
}

void ippool_vlog(int level, const char *fmt, va_list ap)
{
	if (ippool_opt_nodaemon) {
		vprintf(fmt, ap);
		printf("\n");
	} else {
		vsyslog(level, fmt, ap);
	}
	DMALLOC_VMESSAGE(fmt, ap);
}

void ippool_log(int level, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	ippool_vlog(level, fmt, ap);
	va_end(ap);
}

static void ippool_system_log(int level, const char *fmt, ...)
{
	if (ippool_opt_debug) {
		va_list ap;

		va_start(ap, fmt);
		ippool_vlog(level, fmt, ap);
		va_end(ap);
	}
}

/*****************************************************************************
 * Management interface
 *****************************************************************************/

bool_t ippool_app_info_get_1_svc(struct ippool_api_app_msg_data *msg, struct svc_req *req)
{
	int patches_len;

	msg->build_date = strdup(__DATE__);
	msg->build_time = strdup(__TIME__);
	msg->major = IPPOOL_APP_MAJOR_VERSION;
	msg->minor = IPPOOL_APP_MINOR_VERSION;
	msg->cookie = IPPOOL_APP_COOKIE;

	patches_len = sizeof(ippool_installed_patches) - sizeof(ippool_installed_patches[0]);
	msg->patches.patches_len = patches_len / sizeof(ippool_installed_patches[0]);
	if (msg->patches.patches_len > 0) {
		msg->patches.patches_val = malloc(patches_len);
		if (msg->patches.patches_val == NULL) {
			return FALSE;
		}
		memcpy(msg->patches.patches_val, &ippool_installed_patches[0], patches_len);
	}

	if ((msg->build_date == NULL) || (msg->build_time == NULL)) {
		return FALSE;
	}

	return TRUE;
}

/*****************************************************************************
 * Init and cleanup
 *****************************************************************************/

void ippool_restore_default_config(void)
{
}

static void ippool_init(void)
{
#ifdef IPPOOL_DMALLOC
	/* dmalloc debug options are set in the environment. However,
	 * certain options cause problems to this application. We
	 * therefore ensure that the troublesome options are disabled,
	 * regardless of the user's settings.  The disabled options
	 * are: alloc-blank, free-blank, force-linear.  If these
	 * options are enabled, it causes strange problems in the
	 * generated RPC code.
	 */
	dmalloc_debug(dmalloc_debug_current() & 0xff5dffff);
	ippool_dmalloc_mark = dmalloc_mark();
	if (getenv("DMALLOC_OPTIONS") != NULL) {
		ippool_log(LOG_WARNING, "DMALLOC debugging enabled");
	}
#endif
	ippool_my_pid = getpid();

	atexit(ippool_cleanup);
	IPPOOL_DEBUG("%s (%s %s)", __FUNCTION__, __DATE__, __TIME__);
	usl_set_debug(ippool_opt_debug, ippool_system_log);

	usl_signal_terminate_hook = ippool_die;
	usl_signal_init();
	usl_fd_init();
	usl_signal_notifier_add(ippool_signal_handler, NULL);

	ippool_api_init();
}

static void ippool_cleanup(void)
{
	pid_t pid;

	pid = getpid();
	if (pid != ippool_my_pid) {
		IPPOOL_DEBUG("%s: not main pid so returning now", __FUNCTION__);
		return;
	}

	IPPOOL_DEBUG("%s: starting", __FUNCTION__);

	usl_signal_notifier_remove(ippool_signal_handler, NULL);

	/* Cleanup all resources */
	ippool_api_cleanup();

	usl_fd_cleanup();
	usl_signal_cleanup();
	usl_pid_cleanup();

	IPPOOL_DEBUG("%s: done", __FUNCTION__);

#ifdef IPPOOL_DMALLOC
	dmalloc_log_changed(ippool_dmalloc_mark, 1, 0, 1);
#endif
}

