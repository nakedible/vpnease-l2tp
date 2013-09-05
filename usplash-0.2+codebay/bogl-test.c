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

#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include "bogl.h"

extern struct bogl_font font_helvB10;
extern struct bogl_font font_helvB12;
extern struct bogl_font font_helvR10;
extern struct bogl_font font_timBI18;

extern struct bogl_pointer pointer_arrow;

struct bogl_font *font_list[] =
  {
    &font_helvB10,
    &font_helvB12,
    &font_helvR10,
    &font_timBI18,

    NULL
  };

static const unsigned char palette[16][3] = 
  {
    {0x00, 0x00, 0x00},	/* 0: Black. */
    {0xaa, 0xaa, 0xaa},	/* 1: Gray 66%. */
    {0xff, 0xff, 0xff},	/* 2: White. */
    {0x00, 0x00, 0xff},	/* 3: Blue. */
    {0xff, 0x00, 0x00},	/* 4: Red. */
    {0x00, 0x00, 0x00},	/* 5: Unused #1. */
    {0x00, 0x00, 0x00},	/* 6: Unused #2. */
    {0x00, 0x00, 0x00},	/* 7: Unused #3. */
    {0x00, 0x00, 0x00},	/* 8: Unused #4. */
    {0x00, 0x00, 0x00},	/* 9: Unused #5. */
    {0xa9, 0x99, 0x75},	/* A: Tux #1. */
    {0xec, 0xc9, 0x39},	/* B: Tux #2. */
    {0x61, 0x52, 0x39},	/* C: Tux #3. */
    {0xe4, 0xa8, 0x10},	/* D: Tux #4. */
    {0xa0, 0x6d, 0x0c},	/* E: Tux #5. */
    {0x38, 0x2e, 0x1e},	/* F: Tux #6. */
  };

extern struct bogl_pixmap pixmap_tux50;
extern struct bogl_pixmap pixmap_tux75;

struct bogl_pixmap *pixmap_list[] =
  {
    &pixmap_tux75,

    NULL
  };

#define n_pixmaps ((int) (sizeof (pixmap_list)			\
			  / sizeof (struct bogl_pixmap *)) - 1)

/* Print a helpful syntax message and terminate. */
void
usage (void)
{
  struct bogl_font **font;

  bogl_done ();
  printf ("usage:\t\"bogl-test test-type\"\n"
	  "\twhere test-type may be one of the following:\n\n"
	  "\thline\thorizontal lines\n"
	  "\tvline\tvertical lines\n"
	  "\tbox\tsolid boxes\n"
	  "\ttext\ttext drawing (specify font from list below)\n"
	  "\tpointer\ttest pointer drawing & erasing\n"
	  "\tput\tpixmap drawing (specify pixmap from 0 to %d)\n\n"
	  "available fonts:\n",
	  n_pixmaps - 1);

  for (font = font_list; *font; font++)
    printf ("\t%s\n", (*font)->name);

  
  exit (0);
}

int
main (int argc, char *argv[])
{
  if (argc < 2)
    usage ();

  setlocale (LC_ALL, "");

  if (!bogl_init ())
    {
      printf ("bogl: %s\n", bogl_error ());
      return 0;
    }

  bogl_set_palette (0, 16, palette);

  if (!strcmp (argv[1], "hline"))
    for (;;)
      {
	int x1, x2, t;

	x1 = rand () % bogl_xres;
	x2 = rand () % bogl_xres;
	if (x1 > x2)
	  t = x1, x1 = x2, x2 = t;
	bogl_hline (x1, x2, rand () % bogl_yres, rand () % 16);
      }

  if (!strcmp (argv[1], "vline"))
    for (;;)
      {
	int y1, y2, t;

	y1 = rand () % bogl_yres;
	y2 = rand () % bogl_yres;
	if (y1 > y2)
	  t = y1, y1 = y2, y2 = t;
	bogl_vline (rand () % bogl_xres, y1, y2, rand () % 16);
      }

  if (!strcmp (argv[1], "box"))
    for (;;)
      {
	int x1, x2, y1, y2, t;
	x1 = rand () % bogl_xres;
	x2 = rand () % bogl_xres;
	if (x1 > x2)
	  t = x1, x1 = x2, x2 = t;
	y1 = rand () % bogl_yres;
	y2 = rand () % bogl_yres;
	if (y1 > y2)
	  t = y1, y1 = y2, y2 = t;
	bogl_clear (x1, y1, x2, y2, rand () % 16);
      }

  if (!strcmp (argv[1], "text"))
    {
      struct bogl_font **font;

      if (argc < 3)
	usage ();

      for (font = font_list; *font; font++)
	if (!strcmp ((*font)->name, argv[2]))
	  break;
      if (!*font)
	usage ();
      
      for (;;)
	{
	  char s[64 * MB_LEN_MAX];
	  char *p = s;
	  wchar_t wc;
	  int len;
	  int fg, bg;
	  int i, k;
      
	  fg = rand () % 16;
	  bg = rand () % 16;
	  if (fg == bg)
	    continue;
      
	  len = rand () % 64;
	  wctomb(0, 0);
	  for (i = 0; i < len; i++)
	    {
	      for (;;)
		{
		  /* There could be chars beyond 0xFFFF, but we want
		     this to run at a reasonable speed. */
		  wc = rand () % 0x10000;
		  if (bogl_in_font(*font, wc) && (k = wctomb(p, wc)) != -1)
		    break;
		}
	      p += k;
	    }

/*	  bogl_text (rand () % bogl_xres, rand () % bogl_yres, s, p - s,
	  fg, bg, *font); */
	}
    }
  
  if (!strcmp (argv[1], "put"))
    {
      struct bogl_pixmap *pixmap;
      int index;
      int color_map[] = {6, 7, 8, 9, 10, 11, 12, 13};
      
      if (argc < 3 || (index = atoi (argv[2])) < 0 || index >= n_pixmaps)
	usage ();
      pixmap = pixmap_list[index];
      
      bogl_set_palette (6, 8, pixmap->palette);

      bogl_refresh = 1;
      for (;;)
	{
	  if (bogl_refresh)
	    {
	      bogl_refresh = 0;
	      bogl_clear (0, 0, bogl_xres, bogl_yres, 1);
	      bogl_put (0, 0, pixmap, color_map);
	    }
	  pause ();
	}
      
      exit (0);
    }

  if (!strcmp (argv[1], "pointer"))
    {
      bogl_clear (0, 0, bogl_xres, bogl_yres, 1);

      for (;;)
	{
	  int x = rand () % bogl_xres;
	  int y = rand () % bogl_yres;
	  
	  bogl_pointer (1, x, y, &pointer_arrow, (int []) {15, 0});
	  getchar ();

	  bogl_pointer (0, x, y, &pointer_arrow, NULL);
	  getchar ();
	}
    }
  
  usage ();
}
