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

/* bogl-pcfb.c: pseudocolor packed pixel driver for BOGL

   Written by David Huggins-Daines <dhd@debian.org> based on Ben's
   original cfb8 driver. */

/*#define NDEBUG*/
#include <assert.h>
#include <errno.h>
#include <string.h>
#include <limits.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <sys/types.h>
#include <stdlib.h>
#include "bogl.h"
#include "boglP.h"
#include "bogl-cfb.h"
#include "bogl-pcfb.h"

static int bpp;
static unsigned char* save;

static inline unsigned int
cmap_lookup (int entry)
{
  return entry;
}

/* Set pixel (X,Y) to color C. */
void
bogl_pcfb_pixel (int x, int y, int c)
{
  bogl_drawing = 1;

  assert (x >= 0 && x < bogl_xres);
  assert (y >= 0 && y < bogl_yres);

  put_var (bogl_frame + y * bogl_line_len, x, cmap_lookup(c), bpp);

  bogl_drawing = 0;
}

/* Paint a horizontal line from (X1,Y) to (X2,Y) in color C, where X2
   >= X1.  The final point is not painted. */
void
bogl_pcfb_hline (int x1, int x2, int y, int c)
{
  assert (x1 >= 0 && x1 < bogl_xres);
  assert (x2 >= 0 && x2 <= bogl_xres);
  assert (x2 >= x1);
  assert (y >= 0 && y < bogl_yres);

  if (x1 == x2)
    return;

  bogl_drawing = 1;
  memset_var ((void*)bogl_frame
	      + (y * bogl_line_len),
	      cmap_lookup(c), x1,
	      x2 - x1, bpp);
  bogl_drawing = 0;
}

/* Paints a vertical line from (X,Y1) to (X,Y2) in color C.  The final
   point is not painted. */
void
bogl_pcfb_vline (int x, int y1, int y2, int c)
{
  assert (x >= 0 && x < bogl_xres);
  assert (y1 >= 0 && y1 < bogl_yres);
  assert (y2 >= 0 && y2 <= bogl_yres);
  assert (y2 >= y1);

  bogl_drawing = 1;
  for (; y1 < y2; y1++)
    put_var (bogl_frame + (y1 * bogl_line_len), x, cmap_lookup(c), bpp);
  bogl_drawing = 0;
}

/* Clear the region from (X1,Y1) to (X2,Y2) to color C, not including
   the last row or column.  If C == -1 then the region's colors are
   inverted rather than set to a particular color.  */
void
bogl_pcfb_clear (int x1, int y1, int x2, int y2, int c)
{
  unsigned char *dst;

  assert (0 <= x1 && x1 <= x2 && x2 <= bogl_xres);
  assert (0 <= y1 && y1 <= y2 && y2 <= bogl_yres);

  if (x1 == x2)
    return;

  bogl_drawing = 1;
  dst = (char *) bogl_frame + (y1 * bogl_line_len);
  for (; y1 < y2; y1++)
    {
      memset_var (dst, cmap_lookup(c), x1, x2 - x1, bpp);
      dst += bogl_line_len;
    }
  bogl_drawing = 0;
}

void
bogl_pcfb_text (int xx, int yy, const char *s, int n, int fg, int bg, int ul,
		const struct bogl_font *font)
{
  int h, k;
  wchar_t wc;

  assert (xx >= 0 && xx < bogl_xres);
  assert (yy >= 0 && yy < bogl_yres);

  bogl_drawing = 1;

  h = bogl_font_height (font);
  if (yy + h > bogl_yres)
    h = bogl_yres - yy;

  mbtowc (0, 0, 0);
  for (; (k = mbtowc (&wc, s, n)) > 0; s += k, n -= k)
    {
      char *dst = (char *) bogl_frame + (yy * bogl_line_len);

      u_int32_t *character = NULL;
      int w = bogl_font_glyph (font, wc, &character);

      int x, y, h1 = ul ? h - 1 : h;

      if (character == NULL)
	continue;
 
      if (xx + w > bogl_xres)
	w = bogl_xres - xx;
      
      for (y = 0; y < h1; y++)
	{
	  u_int32_t c = *character++;
	  
	  for (x = 0; x < w; x++)
	    {
	      if (c & 0x80000000)
		put_var (dst, xx+x, cmap_lookup(fg), bpp);
	      else if (bg != -1)
		put_var (dst, xx+x, cmap_lookup(bg), bpp);

	      c <<= 1;
	    }

	  dst += bogl_line_len;
	}

      if (ul)
        for (x = 0; x < w; x++)
          put_var (dst, xx+x, cmap_lookup(fg), bpp);
        

      xx += w;
      if (xx >= bogl_xres)
	break;
    }

  bogl_drawing = 0;
}

/* Write PIXMAP at location (XX,YY) */
void
bogl_pcfb_put (int xx, int yy, const struct bogl_pixmap *pixmap,
		const int color_map[16])
{
  char *dst;
  const unsigned char *src;
  int h;
  
  assert (xx + pixmap->width <= bogl_xres);
  assert (yy >= 0 && yy < bogl_yres);
  assert (yy + pixmap->height <= bogl_yres);
  src = pixmap->data;

  bogl_drawing = 1;

  h = pixmap->height;
  dst = (char *) bogl_frame + (yy * bogl_line_len);
  while (h--)
    {
      int w = pixmap->width;
      int offset = xx;
      while (w)
	{
	  int color = *src & 0xf;
	  int count = *src >> 4;
	  src++;
	  w -= count;

	  if (color != pixmap->transparent)
	    memset_var ((char *) dst, cmap_lookup(color_map[color]),
			offset, count, bpp);
	  offset += count;
	}
      dst += bogl_line_len;
    }

  bogl_drawing = 0;
}

/* Draw mouse pointer POINTER with its hotspot at (X,Y), if VISIBLE !=
   0.  Restores the previously saved background at that point, if
   VISIBLE == 0.  COLORS[] gives the color indices to paint the
   cursor.

   This routine performs full clipping on all sides of the screen. */
void 
bogl_pcfb_pointer (int visible, int x1, int y1,
		    const struct bogl_pointer *pointer,
		    int colors[2])
{
  int y_count;		/* Number of scanlines. */
  int y_ofs;		/* Number of scanlines to skip drawing. */
  int x_ofs;		/* Number of pixels to skip drawing on each line. */

  assert (pointer != NULL);

  x1 -= pointer->hx;
  y1 -= pointer->hy;
  
  if (y1 + 16 > bogl_yres)
    {
      y_count = bogl_yres - y1;
    }
  else
    y_count = 16;

  if (x1 < 0)
    {
      x_ofs = -x1;
      x1 = 0;
    }
  else
    x_ofs = 0;

  if (y1 < 0)
    {
      y_ofs = -y1;
      y1 = 0;
      y_count -= y_ofs;
    }
  else
    y_ofs = 0;

  bogl_drawing = 1;

  /* Save or restore the framebuffer contents. */
  {
    int sx_ofs = x1;
    int rowbytes = 16 * bpp / 8;

    if (sx_ofs + 16 > bogl_xres)
      {
	sx_ofs = bogl_xres - 16;
      }
    /* Avoid mouse droppings on <8-bit displays */
    else if (bpp < 8 && sx_ofs % (8 / bpp))
      rowbytes++;

    if (visible)
      {
	char *dst = save;
	char *src = (char *) bogl_frame
	  + (sx_ofs * bpp / 8)
	  + (y1 * bogl_line_len);
	int y;
	
	for (y = 0; y < y_count; y++)
	  {
	    memcpy (dst, src, rowbytes);
	    dst += rowbytes;
	    src += bogl_line_len;
	  }
      }
    else
      {
	char *dst = (char *) bogl_frame
	  + (sx_ofs * bpp / 8)
	  + (y1 * bogl_line_len);
	char *src = save;
	int y;
	
	for (y = 0; y < y_count; y++)
	  {
	    memcpy (dst, src, rowbytes);
	    dst += bogl_line_len;
	    src += rowbytes;
	  }
      }
  }

  /* Now draw it */
  if (visible)
    {
      const unsigned short *mask_p, *color_p;
      int y;
      int x_count = 16;
      
      if (x1 + 16 > bogl_xres)
	x_count = bogl_xres - x1;

      mask_p = pointer->mask + y_ofs;
      color_p = pointer->color + y_ofs;
      for (y = 0; y < y_count; y++, mask_p++, color_p++)
	{
	  unsigned char *dst;
	  unsigned short bg_bits, fg_bits;
	  int x;
	  
	  dst = (char *) bogl_frame
	    + ((y1 + y) * bogl_line_len);
	  bg_bits = *mask_p ^ *color_p;
	  fg_bits = *mask_p & *color_p;

	  for (x = 0; x < x_count; x++)
	    {
	      if (bg_bits & 0x8000)
		put_var (dst, x + x1, cmap_lookup(colors[0]), bpp);
	      else if (fg_bits & 0x8000)
		put_var (dst, x + x1, cmap_lookup(colors[1]), bpp);
	      else ; /* transparent (we hope) */
	      bg_bits <<= 1;
	      fg_bits <<= 1;
	    }
	}
    }

  bogl_drawing = 0;
}

void
bogl_pcfb_move (int sx, int sy, int dx, int dy, int w, int h)
{
  int i, j;

  bogl_drawing = 1;

  /* FIXME: Some clever memmove magic would undoubtedly be more efficient. */
  for (i = 0; i < h; i++)
    {
      for (j = 0; j < w; j++)
	{
	  unsigned int c;
	  c = get_var (bogl_frame + (sy+i) * bogl_line_len, sx+j, bpp);
	  put_var (bogl_frame + (dy+i) * bogl_line_len, dx+j, c, bpp);
	}
    }

  bogl_drawing = 0;
}

/* Initialize PCFB mode.  Returns the number of bytes to mmap for the
   framebuffer. */
size_t
bogl_pcfb_init (int fb, int new_bpp)
{
  bpp = new_bpp;

  /* Need an extra column for sub-8bpp displays */
  save = malloc (((16*bpp/8) + 1) * 16);
  if (save == NULL)
    return bogl_fail ("allocating backing store: %s", strerror (errno));
  return bogl_xres * bogl_yres * bpp / 8;
}

/*
 * vim:ts=8:sw=2
 */
