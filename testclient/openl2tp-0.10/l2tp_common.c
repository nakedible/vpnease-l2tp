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

/* Common code, shared by more than one application */

#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <ctype.h>
#include <unistd.h>
#include <stdlib.h>
#include <sys/types.h>
#include <errno.h>

#include "usl.h"
#include "l2tp_private.h"


unsigned long l2tp_parse_debug_mask(char *debug_arg)
{
	unsigned long mask = 0;
	char *end = NULL;
	int index;
	char *str;
	char *strp;
	int len;

	static const struct {
		int mask;
		const char *name;
		int min_name_len;
	} debug_flag_names[] = {
		{ L2TP_PROTOCOL, "protocol", 4 },
		{ L2TP_FSM, "fsm", 3 },
		{ L2TP_API, "api", 3 },
		{ L2TP_AVPHIDE, "avphide", 4 },
		{ L2TP_AVPDATA, "avpdata", 4 },
		{ L2TP_AVP, "avp", 3 },
		{ L2TP_FUNC, "func", 3 },
		{ L2TP_XPRT, "xprt", 3 },
		{ L2TP_DATA, "data", 3 },
		{ L2TP_SYSTEM, "system", 3 },
		{ L2TP_PPP, "ppp", 3 },
	};

	/* Check for simple case - an integer mask */
	mask = strtoul(debug_arg, &end, 0);
	if ((end != NULL) && (*end == '\0')) {
		return mask;
	}

	/* Check for "all" */
	if (strcasecmp(debug_arg, "all") == 0) {
		return -1;
	}

	/* Look for colon-separated args, i.e. fsm:protocol */
	str = debug_arg;
	for (;;) {
		strp = strchr(str, ':');
		if (strp == NULL) {
			len = strlen(str);
		} else {
			len = strp - str;
		}
		if (len == 0) {
			break;
		}
		for (index = 0; index < (sizeof(debug_flag_names) / sizeof(debug_flag_names[0])); index++) {
			if (len < debug_flag_names[index].min_name_len) {
				continue;
			}
			if (strncasecmp(str, debug_flag_names[index].name, debug_flag_names[index].min_name_len) == 0) {
				mask |= debug_flag_names[index].mask;
				break;
			}
		}
		if (strp == NULL) {
			break;
		}
		str = strp + 1;
	}

	return mask;
}

const char *l2tp_strerror(int error)
{
	static char unknown_err[30];
	char *str = &unknown_err[0];

	if (error < L2TP_ERR_BASE) {
		return strerror(error);
	}

	switch (error) {
	case L2TP_ERR_PARAM_NOT_MODIFIABLE:
		str = "Parameter not modifiable";
		break;
	case L2TP_ERR_PEER_ADDRESS_MISSING:
		str = "Peer address missing";
		break;
	case L2TP_ERR_PEER_NOT_FOUND:
		str = "Peer not found";
		break;
	case L2TP_ERR_PEER_PROFILE_NOT_FOUND:
		str = "Peer profile not found";
		break;
	case L2TP_ERR_PPP_PROFILE_NOT_FOUND:
		str = "PPP profile not found";
		break;
	case L2TP_ERR_PROFILE_ALREADY_EXISTS:
		str = "Profile already exists";
		break;
	case L2TP_ERR_PROFILE_NAME_ILLEGAL:
		str = "Profile name illegal";
		break;
	case L2TP_ERR_PROFILE_NAME_MISSING:
		str = "Profile name missing";
		break;
	case L2TP_ERR_SESSION_ALREADY_EXISTS:
		str = "Session already exists";
		break;
	case L2TP_ERR_SESSION_ID_ALLOC_FAILURE:
		str = "Session id allocation failure";
		break;
	case L2TP_ERR_SESSION_LIMIT_EXCEEDED:
		str = "Session limit exceeded";
		break;
	case L2TP_ERR_SESSION_NOT_FOUND:
		str = "Session not found";
		break;
	case L2TP_ERR_SESSION_PROFILE_NOT_FOUND:
		str = "Session profile not found";
		break;
	case L2TP_ERR_SESSION_SPEC_MISSING:
		str = "Session id or session name missing";
		break;
	case L2TP_ERR_SESSION_TYPE_BAD:
		str = "Session type invalid";
		break;
	case L2TP_ERR_SESSION_TYPE_ILLEGAL_FOR_TUNNEL:
		str = "Session type illegal for tunnel";
		break;
	case L2TP_ERR_TUNNEL_ADD_ADMIN_DISABLED:
		str = "Tunnel is administratively disabled";
		break;
	case L2TP_ERR_TUNNEL_CREATE_ADMIN_DISABLED:
		str = "Tunnel creation is administratively disabled";
		break;
	case L2TP_ERR_TUNNEL_ALREADY_EXISTS:
		str = "Tunnel already exists";
		break;
	case L2TP_ERR_TUNNEL_ID_ALLOC_FAILURE:
		str = "Tunnel id allocation failure";
		break;
	case L2TP_ERR_TUNNEL_NOT_FOUND:
		str = "Tunnel not found";
		break;
	case L2TP_ERR_TUNNEL_PROFILE_NOT_FOUND:
		str = "Tunnel profile not found";
		break;
	case L2TP_ERR_TUNNEL_SPEC_MISSING:
		str = "Tunnel id or tunnel name missing";
		break;
	case L2TP_ERR_TUNNEL_TOO_MANY_SESSIONS:
		str = "Tunnel too many sessions";
		break;
	case L2TP_ERR_TUNNEL_TOO_MANY_SAME_IP:
		str = "Too many tunnels between same IP addresses";
		break;
	case L2TP_ERR_TUNNEL_LIMIT_EXCEEDED:
		str = "Tunnel limit exceeded";
		break;
	default:
		sprintf(&unknown_err[0], "Unknown error (%d)", error);
		break;
	}
	
	return str;
}
