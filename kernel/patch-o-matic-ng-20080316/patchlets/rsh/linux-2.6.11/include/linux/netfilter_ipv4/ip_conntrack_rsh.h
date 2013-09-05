/* RSH extension for IP connection tracking, Version 1.0
 * (C) 2002 by Ian (Larry) Latter <Ian.Latter@mq.edu.au>
 * based on HW's ip_conntrack_irc.c     
 *
 * ip_conntrack_rsh.c,v 1.0 2002/07/17 14:49:26
 *
 *      This program is free software; you can redistribute it and/or
 *      modify it under the terms of the GNU General Public License
 *      as published by the Free Software Foundation; either version
 *      2 of the License, or (at your option) any later version.
 */
#ifndef _IP_CONNTRACK_RSH_H
#define _IP_CONNTRACK_RSH_H

#define RSH_PORT	514

/* This structure is per expected connection */
struct ip_ct_rsh_expect
{
	u_int16_t port;
};

/* This structure exists only once per master */
struct ip_ct_rsh_master {
};

#endif /* _IP_CONNTRACK_RSH_H */

