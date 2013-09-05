/*
 *  Trivial tool for sending notifications to notification-daemon
 *  using the libnotify library.  (Implemented because python-notify
 *  was not available for Ubuntu Dapper, even through multiverse.)
 *
 *  (c) 2006-2007 Codebay Oy.  All Rights Reserved.
 */

#include <stdio.h>
#include <stdlib.h>

#include <X11/Xlib.h>
#include <X11/Intrinsic.h>
#include <X11/Xutil.h>

#include <glib.h>

#include <libnotify/notify.h>
#include <libnotify/notification.h>

void usage(void) {
        fprintf(stderr, "Usage: %s <summary> <body> <icon> <timeout(ms)> <category> <urgency:CRITICAL/NORMAL/LOW>\n", "notifytool");
}

int main(int argc, char *argv[]) {
	Display *dpy = NULL;
	int rc = -1;
	int libnotify_inited = 0;
	gboolean gres;
	gchar *n_summary = NULL;
	gchar *n_body = NULL;
	gchar *n_icon = NULL;
	gint n_timeout = (gint) 0;
	char *n_category = NULL;
	NotifyUrgency n_urgency = (NotifyUrgency) 0;
	NotifyNotification *notif = NULL;

	if(argc != 7) {
	        goto usage_and_exit;
	}
	n_summary = (gchar *) argv[1];
	n_body = (gchar *) argv[2];
	n_icon = (gchar *) argv[3];
	n_timeout = (gint) atoi(argv[4]);
	n_category = (char *) argv[5];
	if(strcmp(argv[6], "CRITICAL") == 0) {
	        n_urgency = NOTIFY_URGENCY_CRITICAL;
	} else if(strcmp(argv[6], "NORMAL") == 0) {
	        n_urgency = NOTIFY_URGENCY_NORMAL;
	} else if(strcmp(argv[6], "LOW") == 0) {
	        n_urgency = NOTIFY_URGENCY_LOW;
	} else {
	        goto usage_and_exit;
	}

	/* ok, we are happy with the parameters, start working */
	
#if 0
	dpy = XOpenDisplay (NULL);
	if(dpy == NULL) {
		fprintf(stderr, "Cannot open display\n");
		rc = 1;
		goto cleanup;
	}
	fprintf(stderr, "Display: %p\n", dpy);
#endif

	gres = notify_init("VPNease Notification");
	if(!gres) {
	        fprintf(stderr, "notify_init() failed, exiting\n");
		rc = 1;
		goto cleanup;
	}
	fprintf(stderr, "notify_init() returned %d (ok)\n", (int) gres);
	libnotify_inited = 1;

	notif = notify_notification_new(n_summary, n_body, n_icon, NULL);

	notify_notification_set_timeout(notif, n_timeout);
	notify_notification_set_category(notif, n_category);
	notify_notification_set_urgency(notif, n_urgency);
	notify_notification_show(notif, NULL);

	rc = 0;
	/* fall through */

 cleanup:
	if(0) {
	        /* do not call this, it will close the graphical notification too */
#if 0
		gboolean res;
		res = notify_notification_close(notif, NULL);
#endif
	}
	if(libnotify_inited) {
	        notify_uninit();
	}
	if(dpy) {
		XCloseDisplay(dpy);
	}

	return rc;

 usage_and_exit:
	usage();
	return 1;
}
