/* -*- c -*- */

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
 * NOTE: APPLICATIONS USING THIS INTERFACE OR DERIVED FILES THEREOF MUST
 *       EITHER BE LICENSED UNDER GPL OR UNDER AN L2TP COMMERCIAL LICENSE.
 *	 FROM KATALIX SYSTEMS LIMITED.
 *
 *****************************************************************************/

/*
 * L2TP application event interface definition.
 * Applications tell openl2tp of events using this interface. The interface
 * is separated from the main configuration interface because event-generating
 * clients don't need the configuration interface.
 *
 * Events are used as follows:-
 * PPP_UPDOWN_IND	- tells OpenL2TP of PPP session state changes.
 * PPP_STATUS_IND	- tells of reason of failure for async requests
 * PPP_ACCM_IND		- tells OpenL2TP of PPP ACCM negotiated options
 */

/*****************************************************************************
 * API definition
 *****************************************************************************/

program L2TP_EVENT_PROG {
	version L2TP_EVENT_VERSION {
		void L2TP_SESSION_PPP_UPDOWN_IND(uint16_t tunnel_id, uint16_t session_id, int unit, bool up) = 1;
		void L2TP_SESSION_PPP_STATUS_IND(uint16_t tunnel_id, uint16_t session_id, int result) = 2;
		void L2TP_SESSION_PPP_ACCM_IND(uint16_t tunnel_id, uint16_t session_id, uint32_t send_accm, uint32_t recv_accm) = 3;
	} = 1;			/* version 1 */
} = 300774;			/* official number registered at rpc@sun.com */
