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
 * Test code
 */
#include "usl.h"
#include "ippool_private.h"
#include "ippool_rpc.h"


bool_t ippool_test_log_1_svc(char *message, int *result, struct svc_req *req)
{
#ifdef IPPOOL_TEST
	ippool_log(LOG_INFO, "APP: %s", message);
	*result = 0;
	return TRUE;
#else /* IPPOOL_TEST */
	return FALSE;
#endif /* IPPOOL_TEST */
}

