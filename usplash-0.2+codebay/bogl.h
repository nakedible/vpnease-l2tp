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

#ifndef bogl_h
#define bogl_h

#include <stdlib.h>
#include <sys/types.h>

/* As a temporary measure, we do this here rather than in config.h,
   which would probably make more sense. */
#include <limits.h>
#ifndef MB_LEN_MAX
#define MB_LEN_MAX 6 /* for UTF-8 */
#endif

/* Proportional font structure definition. */
struct bogl_font
  {
    char *name;				/* Font name. */
    int height;				/* Height in pixels. */
    int index_mask;			/* ((1 << N) - 1). */
    int *offset;			/* (1 << N) offsets into index. */
    int *index;
    /* An index entry consists of ((wc & ~index_mask) | width) followed
       by an offset into content. A list of such entries is terminated
       by the value 0. */
    u_int32_t *content;
    /* 32-bit right-padded bitmap array. The bitmap for a single glyph
       consists of (height * ((width + 31) / 32)) values. */
    wchar_t default_char;
  };

/* Pixmap structure definition. */
struct bogl_pixmap
  {
    int width, height;			/* Width, height in pixels. */
    int ncols;				/* Number of colors. */
    int transparent;			/* Transparent color or -1 if none. */
    unsigned char (*palette)[3];	/* Palette. */
    unsigned char *data;		/* Run-length compressed data. */
  };

/* Pointer structure definition. */
struct bogl_pointer
  {
    int hx, hy;				/* Hot spot. */
    unsigned short mask[16];		/* Drawing mask: 0=clear, 1=drawn. */
    unsigned short color[16];		/* Pixel colors: 0=black, 1=white. */
  };

/* Screen parameters. */
extern int bogl_xres, bogl_yres, bogl_ncols;

/* 1=Must refresh screen due to tty change. */
extern int bogl_refresh;

/* Generic routines. */
int bogl_init (void);
void bogl_done (void);
const char *bogl_error (void);

void bogl_gray_scale (int make_gray);
void bogl_fb_set_palette (int c, int nc, unsigned char palette[][3]);
void bogl_rectangle (int x1, int y1, int x2, int y2, int c);
int bogl_metrics (const char *s, int n, const struct bogl_font *font);

/* Font access. */
#define bogl_font_height(FONT) ((FONT)->height)
int bogl_font_glyph (const struct bogl_font *font, wchar_t wc, u_int32_t **bitmap);
int bogl_in_font (const struct bogl_font *font, wchar_t wc);

/* Device-specific routines. */
void (*bogl_pixel) (int x, int y, int c);
void (*bogl_hline) (int x1, int x2, int y, int c);
void (*bogl_vline) (int x, int y1, int y2, int c);
void (*bogl_text) (int x, int y, const char *s, int n, int fg, int bg, int ul,
		   const struct bogl_font *font);
void (*bogl_clear) (int x1, int y1, int x2, int y2, int c);
void (*bogl_move) (int sx, int sy, int dx, int dy, int w, int h);
void (*bogl_put) (int x, int y, const struct bogl_pixmap *pixmap,
		  const int color_map[16]);
void (*bogl_pointer) (int visible, int x, int y,
		      const struct bogl_pointer *,
		      int colors[2]);
void (*bogl_set_palette) (int c, int nc, unsigned char palette[][3]);
void (*bogl_reinit) (void);

#endif /* bogl_h */
