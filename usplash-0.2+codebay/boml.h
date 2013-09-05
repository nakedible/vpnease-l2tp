/* BOGL - Ben's Own Graphics Library.
   Written by Ben Pfaff <pfaffben@debian.org>.

   This program is free software; you can redistribute it and/or
   modify it under the terms of the GNU General Public License as
   published by the Free Software Foundation; either version 2 of the
   License, or (at your option) any later version.
   
   This program is distributed in the hope that it will be useful, but
   WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
   General Public License for more details.
   
   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
   USA. */

#ifndef boml_h
#define boml_h

/* Mouse event types. */
enum
  {
    BOML_E_NONE,		/* Nothing to report. */

    BOML_E_MOVE,		/* Movement. */
    BOML_E_PRESS,		/* Button pressed. */
    BOML_E_RELEASE,		/* Button released. */
  };

int boml_quick_init (void);
void boml_init (void (*callback) (int));
void boml_show (void);
void boml_hide (void);
void boml_refresh (void);
void boml_drawn (int is_drawn);
void boml_draw (void);
void boml_pointer (const struct bogl_pointer *, int colors[2]);
int boml_fds (int test, fd_set *);
int boml_event (int *x, int *y, int *btn);

#endif /* boml_h */
