
#ifndef bogl_term_h
#define bogl_term_h

#include <wchar.h>

struct bogl_term {
  const struct bogl_font *font;
  int xbase, ybase;
  int xsize, ysize;
  int xstep, ystep;
  int xpos, ypos;
  int def_fg, def_bg;
  int fg, bg, ul;
  int rev;
  int state;
  int cur_visible;
  int xp, yp;
  int arg[2];
  mbstate_t ps;
  wchar_t *screen; /* character in cell, or 0 */
  int *screenfg, *screenbg, *screenul; /* colours in cell */
  char *dirty; /* bitmask of dirty chars */
  wchar_t **cchars; /* combining chars in cell, or 0 */
  int yorig; /* increment this to scroll */
  int acs;
};

struct bogl_term *bogl_term_new(struct bogl_font *font);
void bogl_term_out(struct bogl_term *term, char *s, int n);
void bogl_term_redraw(struct bogl_term *term);
void bogl_term_delete(struct bogl_font *font);
void bogl_term_dirty (struct bogl_term *term);

#endif
