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

#ifndef CLI_PRIVATE_H
#define CLI_PRIVATE_H

#define CLI_MAX_ARGC		200
#define CLI_MAX_KEYWORDS	50


extern int cli_rl_buffer_to_argv(char *start, char *end, char *argv[], int argv_len);
extern int cli_rl_set_prompt(const char *prompt);
extern int cli_rl_stuff_char(int ch);
extern void cli_rl_show_help(void);
extern void cli_rl_wait_then_execute_command(void);
extern int cli_rl_write_history_file(char *filename, int max_size);
extern int cli_rl_read_history_file(char *filename);
extern void cli_rl_clear_history(void);
extern void cli_rl_init(const char *app_name);
extern void cli_rl_cleanup(void);


#endif /* CLI_PRIVATE_H */
