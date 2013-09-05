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

#ifndef IPPOOL_PRIVATE_H
#define IPPOOL_PRIVATE_H

#include <stdarg.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netdb.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <assert.h>
#ifdef IPPOOL_DMALLOC
#include <dmalloc.h>
#endif

#include "usl_list.h"

#include "ippool_rpc.h"

#define IPPOOL_VENDOR_STRING		IPPOOL_APP_VENDOR_INFO " Linux"

#ifdef IPPOOL_DMALLOC
#define DMALLOC_MESSAGE(fmt, args...)	dmalloc_message(fmt, ##args)
#define DMALLOC_VMESSAGE(fmt, ap)	dmalloc_vmessage(fmt, ap)
#else
#define DMALLOC_MESSAGE(fmt, args...)	do { } while(0)
#define DMALLOC_VMESSAGE(fmt, args...)	do { } while(0)
#endif

#ifdef DEBUG
#define IPPOOL_DEBUG(fmt, args...)						\
	do {								\
		if (ippool_opt_debug) {					\
			if (ippool_opt_nodaemon) {				\
				printf("DEBUG: " fmt "\n", ##args);	\
			} else {					\
				syslog(LOG_DEBUG, "DEBUG: " fmt, ##args);\
			}						\
		}							\
		DMALLOC_MESSAGE(fmt, ##args);				\
	} while(0)
#else
#define IPPOOL_DEBUG(level, fmt, args...)
#endif /* DEBUG */

#define BUG_TRAP(_cond)		assert(!(_cond))

/*****************************************************************************
 * Application shared types
 *****************************************************************************/

/* This dummy structure contains all messages of the interface and is used to generate
 * a cookie for the application. We use this to tell when one of the structures of the
 * interface changes size.
 */
struct ippool_api_app_cookie {
	struct ippool_api_app_msg_data app_info;
};

#define IPPOOL_APP_COOKIE		sizeof(struct ippool_api_app_cookie)

/*****************************************************************************
 * Internal interfaces
 *****************************************************************************/

extern int ippool_opt_remote_rpc;
extern int ippool_opt_nodaemon;
extern int ippool_opt_debug;

/* ippool_main.c */
extern void ippool_vlog(int level, const char *fmt, va_list ap);
extern void ippool_log(int level, const char *fmt, ...);

/* ippool_api.c */
extern void ippool_api_init(void);
extern void ippool_api_cleanup(void);


#endif
