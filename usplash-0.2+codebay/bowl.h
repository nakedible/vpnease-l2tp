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

#ifndef bowl_h
#define bowl_h

void bowl_init (void);
void bowl_done (void);

void bowl_layout (void);
void bowl_refresh (void);
void bowl_title (const char *);
void bowl_default (int result);
int bowl_run (void);

/* Menu item. */
struct bowl_menu_item
  {
    char *tag;
    char *item;
    int command;
  };

void bowl_flush (void);
void bowl_new_text (const char *);
void bowl_new_button (const char *, int command);
void bowl_new_input (char **, const char *proto);
void bowl_new_menu (const struct bowl_menu_item *, int n_items, int height);
void bowl_new_checkbox (char **choices, char *values, int n,
			int height);
struct widget *bowl_new_scale (long long max);

void bowl_set_scale (struct widget *w, long long value);

#endif /* bowl_h */
