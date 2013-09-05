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

/*#define NDEBUG*/
#include <assert.h>
#include <string.h>
#include "bogl.h"
#include "boglP.h"
#include "bogl-cfb8.h"

#define BYTES_PP 1
#define put_8(dst, off, c) (((unsigned char*)(dst))[off] = c)

/* Set pixel (X,Y) to color C. */
void
bogl_cfb8_pixel (int x, int y, int c)
{
  bogl_drawing = 1;

  assert (x >= 0 && x < bogl_xres);
  assert (y >= 0 && y < bogl_yres);
  assert (c >= 0 && c < bogl_ncols);
  
  put_8 (bogl_frame + y * bogl_line_len, x, c);

  bogl_drawing = 0;
}

/* Paint a horizontal line from (X1,Y) to (X2,Y) in color C, where X2
   >= X1.  The final point is not painted. */
void
bogl_cfb8_hline (int x1, int x2, int y, int c)
{
  assert (x1 >= 0 && x1 < bogl_xres);
  assert (x2 >= 0 && x2 <= bogl_xres);
  assert (x2 >= x1);
  assert (y >= 0 && y < bogl_yres);
  assert (c >= 0 && c < bogl_ncols);

  if (x1 == x2)
    return;

  bogl_drawing = 1;
  memset ((char *) bogl_frame + x1 + y * bogl_line_len, c, x2 - x1);
  bogl_drawing = 0;
}

/* Paints a vertical line from (X,Y1) to (X,Y2) in color C.  The final
   point is not painted. */
void
bogl_cfb8_vline (int x, int y1, int y2, int c)
{
  assert (x >= 0 && x < bogl_xres);
  assert (y1 >= 0 && y1 < bogl_yres);
  assert (y2 >= 0 && y2 <= bogl_yres);
  assert (y2 >= y1);
  assert (c >= 0 && c < bogl_ncols);

  bogl_drawing = 1;
  for (; y1 < y2; y1++)
    put_8 (bogl_frame + y1 * bogl_line_len, x, c);
  bogl_drawing = 0;
}

/* Clear the region from (X1,Y1) to (X2,Y2) to color C, not including
   the last row or column.  If C == -1 then the region's colors are
   inverted rather than set to a particular color.  */
void
bogl_cfb8_clear (int x1, int y1, int x2, int y2, int c)
{
  volatile char *dst;

  assert (0 <= x1 && x1 <= x2 && x2 <= bogl_xres);
  assert (0 <= y1 && y1 <= y2 && y2 <= bogl_yres);
  assert (c >= -1 && c < bogl_ncols);

  if (x1 == x2)
    return;

  bogl_drawing = 1;
  dst = bogl_frame + x1 + y1 * bogl_line_len;
  for (; y1 < y2; y1++)
    {
      memset ((char *) dst, c, x2 - x1);
      dst += bogl_line_len;
    }
  bogl_drawing = 0;
}

void
bogl_cfb8_text (int xx, int yy, const char *s, int n, int fg, int bg,
		struct bogl_font *font)
{
  int h;
  
  assert (xx >= 0 && xx < bogl_xres);
  assert (yy >= 0 && yy < bogl_yres);
  assert (fg >= 0 && fg < bogl_ncols);
  assert (bg >= -1 && bg < bogl_ncols);

  bogl_drawing = 1;

  h = font->height;
  if (yy + h > bogl_yres)
    h = bogl_yres - yy;

  for (; n--; s++)
    {
      volatile char *dst = bogl_frame + xx + yy * bogl_line_len;

      const unsigned char ch = *s;
      const u_int32_t *character = &font->content[font->offset[ch]];
      int w = font->width[ch];

      int x, y;

      if (xx + w > bogl_xres)
	w = bogl_xres - xx;
      
      for (y = 0; y < h; y++)
	{
	  u_int32_t c = *character++;
	  
	  for (x = 0; x < w; x++)
	    {
	      if (c & 0x80000000)
		put_8 (dst, x, fg);
	      else if (bg != -1)
		put_8 (dst, x, bg);

	      c <<= 1;
	    }

	  dst += bogl_line_len;
	}

      xx += w;
      if (xx >= bogl_xres)
	break;
    }

  bogl_drawing = 0;
}

/* Write PIXMAP at location (XX,YY), with the pixmap's colors mapped
   according to COLOR_MAP. */
void
bogl_cfb8_put (int xx, int yy, const struct bogl_pixmap *pixmap,
	       const int color_map[16])
{
  volatile char *dst;
  const unsigned char *src;
  int h;
  
  assert (xx + pixmap->width <= bogl_xres);
  assert (yy >= 0 && yy < bogl_yres);
  assert (yy + pixmap->width <= bogl_yres);
  src = pixmap->data;

  bogl_drawing = 1;

  h = pixmap->height;
  dst = bogl_frame + (xx * BYTES_PP) + (yy * bogl_line_len);
  while (h--)
    {
      int w = pixmap->width;
      while (w)
	{
	  int color = *src & 0xf;
	  int count = *src >> 4;
	  src++;

	  w -= count;
	  memset ((char *)dst, color_map[color], count);
	  dst += count * BYTES_PP;
	}

      dst += bogl_line_len - (pixmap->width * BYTES_PP);
    }

  bogl_drawing = 0;
}

/* Draw mouse pointer POINTER with its hotspot at (X,Y), if VISIBLE !=
   0.  Restores the previously saved background at that point, if
   VISIBLE == 0.  COLORS[] gives the color indices to paint the
   cursor.

   This routine performs full clipping on all sides of the screen. */
void 
bogl_cfb8_pointer (int visible, int x1, int y1,
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
    /* 16x16 packed pixels */
    static unsigned char saved[16 * 16 * BYTES_PP];
    int sx_ofs = x1;
      
    if (sx_ofs + 16 > bogl_xres)
      sx_ofs = bogl_xres - 16;

    if (visible)
      {
	volatile char *dst = saved;
	volatile char *src = bogl_frame
	  + (sx_ofs * BYTES_PP)
	  + (y1 * bogl_line_len);
	int y;
	
	for (y = 0; y < y_count; y++)
	  {
	    memcpy ((char *) dst, (char *) src, 16 * BYTES_PP);
	    dst += 16 * BYTES_PP;
	    src += bogl_line_len;
	  }
      }
    else
      {
	volatile char *dst = bogl_frame
	  + (sx_ofs * BYTES_PP)
	  + (y1 * bogl_line_len);
	volatile char *src = saved;
	int y;
	
	for (y = 0; y < y_count; y++)
	  {
	    memcpy ((char *) dst, (char *) src, 16 * BYTES_PP);
	    dst += bogl_line_len;
	    src += 16 * BYTES_PP;
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
	  volatile char *dst;
	  unsigned short bg_bits, fg_bits;
	  int x;
	  
	  dst = bogl_frame + ((y1 + y) * bogl_line_len);
	  bg_bits = *mask_p ^ *color_p;
	  fg_bits = *mask_p & *color_p;

	  for (x = 0; x < x_count; x++)
	    {
	      if (bg_bits & 0x8000)
		put_8 (dst, x + x1, colors[0]);
	      else if (fg_bits & 0x8000)
		put_8 (dst, x + x1, colors[1]);
	      else 
		; /* It's fine the way it is... */
	      bg_bits <<= 1;
	      fg_bits <<= 1;
	    }
	}
    }

  bogl_drawing = 0;
}


/* Initialize CFB8 mode.  Returns the number of bytes to mmap for the
   framebuffer. */
size_t
bogl_cfb8_init (void)
{
  return bogl_xres * bogl_yres;
}
