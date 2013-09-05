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

#ifndef USL_FSM_H
#define USL_FSM_H

struct usl_fsm_table;

struct usl_fsm_instance {
	char				name[16];
	int 				state;
	const struct usl_fsm_table	*table;
};

typedef	void (*usl_fsm_action_fn_t)(void *arg1, void *arg2, void *arg3);

struct usl_fsm_entry {
	int			state;
	int			event;
	usl_fsm_action_fn_t	action;
	int			new_state;
};

struct usl_fsm_table {
	const char		*name;
	void			(*log)(struct usl_fsm_instance const *fsmi, int level, const char *fmt, ...);
	int			num_states;
	const char		**state_names;
	int			num_events;
	const char		**event_names;
	struct usl_fsm_entry	fsm[];
};

extern void usl_fsm_handle_event(struct usl_fsm_instance *fsmi,
				 int event, void *arg1, void *arg2, void *arg3);
extern void usl_fsm_new_state(const struct usl_fsm_table *fsm, 
			      struct usl_fsm_instance *fsmi, int new_state);
extern const char *usl_fsm_state_name(struct usl_fsm_instance *fsmi);
extern const char *usl_fsm_event_name(struct usl_fsm_instance *fsmi, int event);



#endif
