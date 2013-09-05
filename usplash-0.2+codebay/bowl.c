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

#define _GNU_SOURCE 1
#include <assert.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <unistd.h>
#include "bogl-font.h"
#include "bogl.h"
#include "boml.h"
#include "bowl.h"

#ifdef _TESTING_
#       define _(String) String
#else
#       include <libintl.h>
#       define _(String) gettext(String)
#endif

/* #include "dbootstrap.h"
  #include "lang.h"
  */

#define bogl_char_width(ch, font) \
bogl_font_glyph(font, (wchar_t)(unsigned char)ch, 0)

/* Widget type. */
enum
  {
    W_TEXT,
    W_BUTTON,
    W_INPUT,
    W_MENU,
    W_CHECKBOX,
    W_SCALE,
  };

/* A widget. */
struct widget
  {
    struct widget *next, *prev;
    int type;		/* Widget type. */
    int w, h;		/* Width, height. */
    int x, y;		/* Location. */
    union
      {
	struct
	  {
	    char *text;		/* Text contents. */
	  }
	text;

	struct
	  {
	    char *label;	/* Button label. */
	    int command;	/* Value returned to caller. */
	    int focused;	/* Drawn as focused? */
	  }
	button;

	struct
	  {
	    char **string;	/* Input line contents. */
	    int length;		/* Number of characters on line. */
	    int offset;		/* Leftmost displayed character. */
	    int cursor;		/* Cursor position. */
	  }
	input;

	struct
	  {
	    int length;		/* Number of items. */
	    int offset;		/* Topmost displayed item. */
	    int cursor;		/* Selected item. */
	    int shown;		/* Number of items to show at once. */

	    int tag_width;	/* Width of tag column. */

	    char **item;	/* Items. */
	    char **tag;		/* Tags. */
	    int *state;		/* Values to return to caller. */
	  }
	menu;

	struct
	  {
	    int length;		/* Number of items. */
	    int offset;		/* Topmost displayed item. */
	    int cursor;		/* Selected item. */
	    int shown;		/* Number of items to show at once. */

	    int tag_width;	/* Width of tag column. */

	    char **item;	/* Items. */
	    char *values;	/* Values. */
	  }
	checkbox;

	struct
	  {
	    long long value;	/* Current value. */
	    long long max;	/* Maximum value. */
	  }
	scale;
      }
    p;
  };

static struct widget *widgets_head, *widgets_tail;
static struct widget *focus;

/* Mouse grab if active, but usually NULL. */
static struct widget *grab;

static int default_result;

static char *title;

static int wx1, wy1, wx2, wy2;

/* Colors. */
#define BASIC_COLORS 5
static unsigned char palette[16][3] = 
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
    {0xff, 0xff, 0xfb},	/* 9: Unused #5. */
    {0xa9, 0x99, 0x75},	/* A: Tux #1. */
    {0xec, 0xc9, 0x39},	/* B: Tux #2. */
    {0x61, 0x52, 0x39},	/* C: Tux #3. */
    {0xe4, 0xa8, 0x10},	/* D: Tux #4. */
    {0xa0, 0x6d, 0x0c},	/* E: Tux #5. */
    {0x38, 0x2e, 0x1e},	/* F: Tux #6. */
  };

enum
  {
    black, gray, white, blue, red, 
    custom1, custom2, custom3, custom4, custom5, custom6,
    custom7, custom8, custom9, custom10, custom11,
  };

static int pix_cmap[16];

#define wallpaper_color blue
#define big_title_color white

#define window_bg_color gray
#define window_outline_color black
#define window_title_color black

#define text_color black
#define focus_color red

#define menu_cursor_bg_color blue
#define menu_cursor_fg_color white

/* Fonts. */

extern struct bogl_pixmap pixmap_tux75; 
extern struct bogl_font font_helvR10;
extern struct bogl_font font_helvB12;
extern struct bogl_font font_helvB10;
extern struct bogl_font font_timBI18;
extern struct bogl_font font_symbol;

struct bogl_font *title_font;
struct bogl_font *text_font;
struct bogl_font *button_font;
struct bogl_font *input_font;
struct bogl_font *menu_font;


#define symbol_font (&font_symbol)

/* Symbol font characters. */
#define SYM_UNCHECKED "\1"		/* Unchecked check box. */
#define SYM_CHECKED "\2"		/* Checked check box. */
#define SYM_UP "\3"			/* Up arrow. */
#define SYM_DOWN "\4"			/* Down arrow. */

/* Measurements. */
#define horz_margin 5
#define vert_margin 5
#define cursor_width 5
#define window_width (bogl_xres * 3 / 4)
#define left_margin ((bogl_xres - window_width) / 2)
#define arrow_width 6

/* Prototypes. */

static void *xmalloc (size_t);
static void *xrealloc (void *, size_t);
static char *xstrdup (const char *);

static int flow_text (char **dest, const char *src, int width,
		      const struct bogl_font *font);
static void add_widget (struct widget *);
static void draw_widget (struct widget *);
static void rect_3d (int x1, int y1, int x2, int y2);
static int keypress (int ch);
static void focus_next (int dir);
static int dialogue_result (void);

static int mouse (void);

static void menu_up (void);
static void menu_down (void);
static void menu_page_up (void);
static void menu_page_down (void);
static void menu_draw_item (struct widget *w, int index, int bg);
static void menu_draw_cursor (int visible);
static int menu_click (int x, int y);

static void checkbox_toggle (void);

static void input_eol (struct widget *);
static void input_insert (int ch);
static void input_backspace (void);
static void input_delete (void);
static void input_kill_fwd (void);
static void input_kill_bkwd (void);
static void input_kill_word_bkwd (void);
static void input_kill_word_fwd (void);
static void input_fwd_word (void);
static void input_bkwd_word (void);
static int input_cursor_left ();
static int input_cursor_right ();
static int input_bol (void);
static void input_visible_width (struct widget *, int *count, int *width);
static int input_cursor_width (struct widget *);
static int input_cursor_position (struct widget *, int side);
static void input_draw_cursor (int visible);
static void input_move (int (*func) (void));
#define input_str(W) (*(W)->p.input.string)
#define input_ofs(W) ((W)->p.input.offset)
#define input_csr(W) ((W)->p.input.cursor)
#define input_len(W) ((W)->p.input.length)
#define input_field_width(W) ((W)->w - 2 * horz_margin)

/* Initialize BOWL fonts */
static void
bowl_font_init (void)
{
  if(! title_font)
    title_font = bogl_read_bdf("helvR10.bdf");
  if(! text_font)
    text_font = bogl_read_bdf("helvR10.bdf");
  if(! button_font)
    button_font = bogl_read_bdf("helvR10.bdf");
  if(! input_font)
    input_font = bogl_read_bdf("helvR10.bdf");
  if(! menu_font)
    menu_font = bogl_read_bdf("helvR10.bdf");

  if (!(title_font && text_font && button_font && input_font && menu_font))
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      exit (EXIT_FAILURE);
    }
}

/* Set custom colors from a pixmap's palette. */
void
bowl_init_palette(struct bogl_pixmap *pix)
{
  int custom = BASIC_COLORS;
  int i, j;
  
  /* Sanity check. */
  if(pix->ncols >= 16)
    return;

  for(i = 0; i < pix->ncols; i++)
  {
    /* Check existing palette. */
    for(j = 0; j < BASIC_COLORS; j++)
      if(pix->palette[i][0] == palette[j][0]
          && pix->palette[i][1] == palette[i][1]
          && pix->palette[i][2] == palette[i][2])
        {
          pix_cmap[i] = j;
          break;
        }
    if(j < BASIC_COLORS)
      continue;

    /* Too many colors? */
    if(custom >= 16)
      break;
    
    palette[custom][0] = pix->palette[i][0];
    palette[custom][1] = pix->palette[i][1];
    palette[custom][2] = pix->palette[i][2];
    pix_cmap[i] = custom;
    custom++;
  }
}

/* Start up BOWL. */
void
bowl_init (void)
{
  static int inited = 0;
  extern struct bogl_pointer pointer_arrow;

  bowl_font_init ();

  /* Initialize graphics. */
  if (!bogl_init ())
    {
      fprintf (stderr, "Error starting graphics: %s\n", bogl_error ());
      exit (EXIT_FAILURE);
    }

  if (!inited)
    {
      struct widget *w;

      void callback (int percent)
	{
	  bowl_set_scale (w, percent);
	}

      bowl_init_palette(&pixmap_tux75);

      bowl_flush ();
      if (boml_quick_init () == 0)
        {
          bowl_title (_("Please wait"));
          bowl_new_text (_("Detecting mice..."));
          w = bowl_new_scale (100);
          bowl_layout ();
          boml_init (callback);
        }
    }

  /* Initialize mouse. */
  boml_pointer (&pointer_arrow, ((int []) {black, white}));
  boml_show ();
  bowl_flush ();

  inited = 1;
}

/* Close down BOWL. */
void
bowl_done ()
{
  boml_hide ();
  bogl_done ();
}

/* Arranges all the widgets on the screen and draws them. */
void
bowl_layout (void)
{
  struct widget *w;
  int y = 0;

  focus = NULL;
  
  y += bogl_font_height (title_font);
  y += vert_margin;
  for (w = widgets_head; w; )
    {
      int h = w->h;
      
      if (w->type == W_TEXT)
	{
	  w->x = left_margin + horz_margin;
	  w->y = y;
	  w = w->next;
	}
      else 
	{
	  struct widget *x;
	  int n = 0;
	  int i;

	  if (!focus)
	    focus = w;
	  
	  for (x = w; x; x = x->next)
	    if (x->type == w->type)
	      n++;
	    else
	      break;
	  
	  for (i = 0; i < n; i++)
	    {
	      w->x = (window_width * i / n + (window_width / n / 2) - w->w / 2
		      + left_margin);
	      w->y = y;
	      w = w->next;
	    }
	}

      y += h + vert_margin;
    }

  wy2 = y;
  y = (bogl_yres - y) / 2;
  for (w = widgets_head; w; w = w->next)
    w->y += y;

  wx1 = left_margin;
  wy1 = y;
  wx2 = left_margin + window_width;
  wy2 += y;

  bogl_refresh = 1;
  bowl_refresh ();
}

/* Redraw the screen if necessary. */
void
bowl_refresh (void)
{
  const char *big_title = "Debian GNU/Linux 2.2 Installation";

  struct widget *w;

  if (!bogl_refresh)
    {
      boml_refresh ();
      return;
    }
  
  bogl_refresh = 0;
  boml_drawn (0);

  bogl_set_palette (0, 16, palette);
  bogl_clear (0, 0, bogl_xres, bogl_yres, wallpaper_color);
  bogl_put (0, 0, &pixmap_tux75, pix_cmap);
  bogl_text (55, 0, big_title, (int) strlen (big_title), big_title_color, -1, 0,
	     &font_timBI18);

  if (!widgets_head)
    return;

  bogl_clear (wx1, wy1, wx2, wy2, window_bg_color);
  rect_3d (wx1, wy1, wx2, wy1 + bogl_font_height (title_font));
  rect_3d (wx1, wy1 + bogl_font_height (title_font) + 1, wx2, wy2);
  bogl_hline (wx1, wx2, wy1 + bogl_font_height (title_font), wallpaper_color);
  if (title)
    bogl_text (wx1 + horz_margin, wy1, title, strlen (title),
	       window_title_color, -1, 0, title_font);

  for (w = widgets_head; w; w = w->next)
    draw_widget (w);

  boml_refresh ();
}

/* Draw and run the dialogue.  Returns the command value of the button
   that ended the dialogue, or -1 if none. */
int
bowl_run (void)
{
  const int tty = fileno (stdin);
  int cursor_on = 1;
  
  fd_set fds;

  FD_ZERO (&fds);
  
  for (;;)
    {
      struct timeval timeout;
      timeout.tv_sec = 0;
      timeout.tv_usec = 500000;

      bowl_refresh ();
      FD_SET (tty, &fds);
      boml_fds (0, &fds);
      if (select (FD_SETSIZE, &fds, NULL, NULL, &timeout) > 0)
	{
	  if (FD_ISSET (tty, &fds))
	    {
	      int n_chars;
	      unsigned char key;

	      cursor_on = 1;
	      if (-1 == ioctl (tty, FIONREAD, &n_chars))
		continue;

	      while (n_chars--)
		if (1 == read (tty, &key, 1))
		  {
		    if (keypress (key))
		      return dialogue_result ();
		  }
		else
		  break;
	    }

	  if (boml_fds (1, &fds))
	    {
	      boml_refresh ();
	      if (mouse ())
		return dialogue_result ();
	    }
	}
      else
	{
	  if (focus->type == W_INPUT)
	    input_draw_cursor (cursor_on ^= 1);
	}
    }
}

/* Clear and free all the widgets on the list. */
void
bowl_flush (void)
{
  struct widget *w, *n;

  grab = NULL;
  for (w = widgets_head; w; w = n)
    {
      n = w->next;
      switch (w->type)
	{
	case W_TEXT:
	  free (w->p.text.text);
	  break;
	case W_BUTTON:
	  free (w->p.button.label);
	  break;
	case W_MENU:
	case W_CHECKBOX:
	  {
	    int i;

	    for (i = 0; i < w->p.menu.length; i++)
	      {
		if (w->type == W_MENU)
		  free (w->p.menu.tag[i]);
		free (w->p.menu.item[i]);
	      }
	    if (w->type == W_MENU)
	      {
		free (w->p.menu.tag);
		free (w->p.menu.state);
	      }
	    free (w->p.menu.item);
	  }
	  break;
	case W_SCALE:
	  break;
	default:
	  abort ();
	}
      free (w);
    }
  widgets_head = widgets_tail = NULL;

  free (title);
  title = NULL;

  bogl_refresh = 1;
  default_result = -1;
}

/* Set the default termination result for this dialogue.  A default
   result of -1 means there is no default. */
void
bowl_default (int result)
{
  default_result = result;
}

/* Add a text widget containing TEXT to the widget list. */
void
bowl_new_text (const char *text)
{
  struct widget *w = xmalloc (sizeof (struct widget));

  w->type = W_TEXT;
  w->w = window_width - 2 * horz_margin;
  w->h = (bogl_font_height (text_font)
	  * flow_text (&w->p.text.text, text, w->w, text_font));

  add_widget (w);
}

/* Add a button with text LABEL and returning COMMAND to the widget
   list. */
void
bowl_new_button (const char *label, int command)
{
  struct widget *w = xmalloc (sizeof (struct widget));
  int n = (int) strlen (label);

  w->type = W_BUTTON;
  w->w = (bogl_metrics (label, n, button_font) + 2 * horz_margin);
  w->h = bogl_font_height (button_font) * 3 / 2;

  w->p.button.label = xstrdup (label);
  w->p.button.command = command;

  add_widget (w);
}

/* Add an input line to the widget list.  The string is stored in
   *STRING.  If PROTO is not a null pointer then it will be used as
   the default contents. */
void
bowl_new_input (char **string, const char *proto)
{
  struct widget *w = xmalloc (sizeof (struct widget));

  w->type = W_INPUT;
  w->w = window_width - 2 * horz_margin;
  w->h = bogl_font_height (input_font) + 6;

  w->p.input.string = string;
  *w->p.input.string = xstrdup (proto);
  w->p.input.length = proto ? strlen (proto) : 0;
  input_eol (w);

  add_widget (w);
}

/* Add a menu to the widget list.  The menu has N_ITEMS items, taken
   from ITEMS.  The menu will show at most HEIGHT menu items at
   once. */
void
bowl_new_menu (const struct bowl_menu_item *items, int n_items, int height)
{
  struct widget *w = xmalloc (sizeof (struct widget));
  int i;

  if (height > n_items)
    height = n_items;

  w->type = W_MENU;
  w->w = window_width - 2 * horz_margin;
  w->h = bogl_font_height (input_font) * height + 6;

  w->p.menu.tag = xmalloc (sizeof (char *) * n_items);
  w->p.menu.item = xmalloc (sizeof (char *) * n_items);
  w->p.menu.state = xmalloc (sizeof (int) * n_items);

  w->p.menu.tag_width = 0;

  w->p.menu.length = n_items;
  w->p.menu.offset = 0;
  w->p.menu.cursor = 0;

  w->p.menu.shown = height;

  for (i = 0; i < n_items; i++)
    {
      w->p.menu.tag[i] = xstrdup (items[i].tag);
      if (w->p.menu.tag[i])
	{
	  int width = bogl_metrics (w->p.menu.tag[i],
				    strlen (w->p.menu.tag[i]),
				    menu_font);
	  if (width > w->p.menu.tag_width)
	    w->p.menu.tag_width = width;
	}

      w->p.menu.state[i] = items[i].command;
    }

  if (w->p.menu.tag_width > 0)
    w->p.menu.tag_width += horz_margin;

  for (i = 0; i < n_items; i++)
    if (items[i].item)
      {
	const char *s;
	int width;

	width = w->w - horz_margin * 2 - w->p.menu.tag_width - arrow_width;
	for (s = items[i].item; *s; s++)
	  {
	    int cw = bogl_char_width (*s, menu_font);
	  
	    if (width - cw < 0)
	      break;
	    width -= cw;
	  }
	w->p.menu.item[i] = xmalloc (s - items[i].item + 1);
	memcpy (w->p.menu.item[i], items[i].item, s - items[i].item);
	w->p.menu.item[i][s - items[i].item] = 0;
      }
    else
      w->p.menu.item[i] = NULL;

  add_widget (w);
}

/* Add a checkbox group to the widget list.  The N checkboxes are
   labeled as given in CHOICES.  Each index into VALUES is ' ' for
   unchecked or '*' for checked, and their values will be modified by
   the user's actions. */
void
bowl_new_checkbox (char **choices, char *values, int n, int height)
{
  struct widget *w = xmalloc (sizeof (struct widget));
  int i;

  w->type = W_CHECKBOX;
  w->w = window_width - 2 * horz_margin;
  w->h = bogl_font_height (input_font) * height + 6;

  w->p.checkbox.values = values;
  w->p.checkbox.item = xmalloc (sizeof (char *) * n);

  w->p.checkbox.tag_width = (bogl_char_width (SYM_CHECKED[0], symbol_font)
			 + horz_margin);

  w->p.checkbox.length = n;
  w->p.checkbox.offset = 0;
  w->p.checkbox.cursor = 0;

  w->p.checkbox.shown = height;

  for (i = 0; i < n; i++)
    {
      const char *s;
      int width;

      width = w->w - horz_margin * 2 - w->p.checkbox.tag_width - arrow_width;
      for (s = choices[i]; *s; s++)
	{
	  int cw = bogl_char_width (*s, menu_font);
	  
	  if (width - cw < 0)
	    break;
	  width -= cw;
	}
      w->p.checkbox.item[i] = xmalloc (s - choices[i] + 1);
      memcpy (w->p.checkbox.item[i], choices[i], s - choices[i]);
      w->p.checkbox.item[i][s - choices[i]] = 0;
    }

  add_widget (w);
}
  
/* Add a scale to the widget list and return it.  The scale goes from
   0 to MAX. */
struct widget *
bowl_new_scale (long long max)
{
  struct widget *w = xmalloc (sizeof (struct widget));

  w->type = W_SCALE;
  w->w = (window_width - horz_margin * 2) / 2;
  w->h = bogl_font_height (text_font) * 2;

  w->p.scale.value = 0;
  w->p.scale.max = max;

  add_widget (w);

  return w;
}

/* Make S the dialogue title. */
void
bowl_title (const char *s)
{
  const char *p;
  int w;

  p = s;
  w = 0;
  while (*p)
    {
      w += bogl_char_width (*p, title_font);
      if (w > window_width - horz_margin * 2)
	break;
      p++;
    }

  free (title);
  title = NULL;
  
  title = xmalloc (p - s + 1);
  memcpy (title, s, p - s);
  title[p - s] = 0;
}

/* Utilities. */

/* Routine to flow text, copying from TEXT to DEST while inserting
   newlines where needed.  Allocates *DEST automatically.  TEXT is in
   font FONT.

   It's so nice to be able to make _simple_ assumptions.  This is a piece
   of cake after other programs I've written that need to do kerning,
   ligatures, full justification, multiple fonts, ... */
static int
flow_text (char **dest, const char *text, int width,
	   const struct bogl_font *font)
{
  /* Current destination pointer. */
  char *d;

  /* Beginning, end of source line. */
  const char *s, *p;

  /* Cumulative width; number of lines. */
  int w, nl;
  
  *dest = xmalloc (strlen (text) + 128);
  d = *dest;
  s = p = text;
  w = nl = 0;
  for (;;)
    {
      /* Handle end-of-string and end-of-line. */
      if (*p == 0)
	{
	  if (p != s)
	    {
	      memcpy (d, s, p - s);
	      d += p - s;
	      *d++ = '\n';
	    }
	  *d = 0;
	  return nl + 1;
	}
      else if (*p == '\n')
	{
	  memcpy (d, s, p - s + 1);
	  d += p - s + 1;
	  s = ++p;
	  nl++;
	  w = 0;
	  continue;
	}

      /* Add a character if it will fit. */
      {
	int cw;

	cw = bogl_char_width (*p, font);
	if (w + cw <= width)
	  {
	    w += cw;
	    p++;
	    continue;
	  }
      }
      
      /* Output a line. */
      {
	int no_wrap = 0;

	{
	  const char *sp = p;
	
	  while (p > s && !isspace ((unsigned char) p[-1]))
	    p--;
	  while (p > s && isspace ((unsigned char) p[-1]))
	    p--;
	  if (p == s)
	    {
	      no_wrap = 1;
	      p = sp - 1;
	    }
	  assert (p != s);
	}

	/* Copy the text into the destination string. */
	memcpy (d, s, p - s);
	d += p - s;
	*d++ = '\n';

	/* Advance to the next line. */
	if (no_wrap)
	  p++;
	else
	  while (isspace ((unsigned char) *p))
	    p++;
	w = 0;
	s = p;
	nl++;
      }
    }
}

/* Out of memory.  Give up. */
static void
out_of_memory (void)
{
  fprintf (stderr, "virtual memory exhausted\n");
  abort ();
}

/* Allocate AMT bytes of memory and make sure it succeeded. */
void *
xmalloc (size_t size)
{
  void *p;
  
  if (size == 0)
    return 0;
  p = malloc (size);
  if (!p)
    out_of_memory ();
  return p;
}

/* Reallocate BLOCK to AMT bytes in size and make sure it
   succeeded. */
void *
xrealloc (void *p, size_t size)
{
  if (p == NULL)
    return xmalloc (size);
  if (size == 0)
    {
      free (p);
      return NULL;
    }
  p = realloc (p, size);
  if (!p)
    out_of_memory ();
  return p;
}

/* Make a copy of string S and return a pointer to it.  If S is null,
   returns a null pointer. */
char *
xstrdup (const char *s)
{
  if (s)
    {
      size_t size = strlen (s) + 1;
      char *p = xmalloc (size);
      memcpy (p, s, size);
      return p;
    }
  else
    return NULL;
}

/* Add the specified widget W to the widget list. */
static void 
add_widget (struct widget *w)
{
  if (widgets_head == NULL)
    {
      widgets_head = widgets_tail = w;
      w->next = w->prev = NULL;
    }
  else
    {
      w->prev = widgets_tail;
      w->next = NULL;
      widgets_tail = widgets_tail->next = w;
    }
}

static void
rect_3d (int x1, int y1, int x2, int y2)
{
  bogl_hline (x1, x2 - 1, y1, white);
  bogl_vline (x1, y1, y2 - 1, white);

  bogl_hline (x1 + 1, x2, y2 - 1, black);
  bogl_vline (x2 - 1, y1 + 1, y2, black);

  bogl_pixel (x1, y2 - 1, gray);
  bogl_pixel (x2 - 1, y1, gray);
}

/* Draw the specified widget W. */
static void
draw_widget (struct widget *w)
{
  boml_hide ();
  
  switch (w->type)
    {
    case W_TEXT:
      {
	int y = w->y;
	char *p;

	p = w->p.text.text;
	for (;;)
	  {
	    char *e = strchr (p, '\n');
	    if (!e)
	      break;

	    bogl_text (w->x, y, p, e - p, text_color, -1, 0, text_font);
	    y += bogl_font_height (text_font);
	    p = e + 1;
	  }
      }
      break;

    case W_BUTTON:
      bogl_clear (w->x, w->y, w->x + w->w, w->y + w->h, window_bg_color);
      if (w == focus)
	bogl_rectangle (w->x + 2, w->y + 2, w->x + w->w - 2, w->y + w->h - 2,
			focus_color);
      rect_3d (w->x, w->y, w->x + w->w, w->y + w->h);
      bogl_text (w->x + horz_margin,
		 w->y + bogl_font_height (button_font) / 4,
		 w->p.button.label, (int) strlen (w->p.button.label),
		 text_color, -1, 0, button_font);
      w->p.button.focused = (w == focus);
      break;

    case W_INPUT:
      {
	int count;
	int width;
	
	rect_3d (w->x, w->y, w->x + w->w, w->y + w->h);
	bogl_clear (w->x + 1, w->y + 1, w->x + w->w - 2, w->y + w->h - 2,
		    window_bg_color);
	if (w == focus)
	  bogl_rectangle (w->x + 2, w->y + 2,
			  w->x + w->w - 2, w->y + w->h - 2, focus_color);

	input_visible_width (w, &count, &width);
	bogl_text (w->x + horz_margin, w->y + 3,
		   &input_str (w)[input_ofs (w)], count,
		   text_color, -1, 0, input_font);

	if (w == focus)
	  input_draw_cursor (1);
      }
      break;

    case W_MENU:
    case W_CHECKBOX:
      {
	int i;
	
	rect_3d (w->x, w->y, w->x + w->w, w->y + w->h);
	bogl_clear (w->x + 1, w->y + 1, w->x + w->w - 2, w->y + w->h - 2,
		    window_bg_color);
	if (w == focus)
	  bogl_rectangle (w->x + 2, w->y + 2,
			  w->x + w->w - 2, w->y + w->h - 2, focus_color);

	for (i = w->p.menu.offset; i < w->p.menu.offset + w->p.menu.shown; i++)
	  menu_draw_item (w, i,
			  i == w->p.menu.cursor ? menu_cursor_bg_color : -1);

	if (w->p.menu.offset)
	  bogl_text (w->x + w->w - horz_margin - arrow_width,
		     w->y + 3, SYM_UP, 1, text_color, -1, 0, symbol_font);
	if (w->p.menu.offset + w->p.menu.shown < w->p.menu.length)
	  bogl_text (w->x + w->w - horz_margin - arrow_width,
		     (w->y + 3
		      + bogl_font_height (text_font) * (w->p.menu.shown - 1)),
		     SYM_DOWN, 1, text_color, -1, 0, symbol_font);
		     
      }
      break;

    case W_SCALE:
      {

	bogl_clear (w->x, w->y, w->x + w->w, w->y + w->h, window_bg_color);
	
	{
	  long long amt = w->p.scale.value * w->w / w->p.scale.max;

	  if (amt > 0)
	    rect_3d (w->x, w->y, w->x + amt, w->y + w->h);
	}
	
	{
	  char percent[16];
	  int width;

	  sprintf (percent, "%d%%",
		   (int) (w->p.scale.value * 100ll / w->p.scale.max));
	  width = bogl_metrics (percent, strlen (percent), text_font);
	  bogl_text (w->x + w->w / 2 - width / 2,
		     w->y + w->h / 2 - bogl_font_height (text_font) / 2,
		     percent, strlen (percent), text_color, -1, 0, text_font);
	}
      }
      break;
	
    default:
      abort ();
    }

  boml_show ();
}

/* The user pressed a key.  The character received was CH.  Returns
   nonzero only if the dialogue with the user is over. */
static int
keypress (int ch)
{
  static int state = 0;
  static int accum;

  switch (state)
    {
    case 0:
      if (ch == '\e')
	state = 1;
      else if (ch == '\t')
	focus_next (1);
      else if (ch == '\r'
	       && (focus->type == W_BUTTON
		   || (focus->type == W_MENU
		       && focus->p.menu.state[focus->p.menu.cursor] != -1)
		   || default_result != -1))
	return 1;
      else if (ch == 'V' - 64
	       && (focus->type == W_MENU || focus->type == W_CHECKBOX))
	menu_page_down ();
      else if (focus->type == W_INPUT)
	{
	  if (ch == '\x7f')
	    {
	      input_backspace ();
	      draw_widget (focus);
	    }
	  else if (ch >= 32 && ch <= 126)
	    input_insert (ch);
	  else if (ch == 'A' - 64)
	    input_move (input_bol);
	  else if (ch == 'B' - 64)
	    input_move (input_cursor_left);
	  else if (ch == 'D' - 64)
	    {
	      input_delete ();
	      draw_widget (focus);
	    }
	  else if (ch == 'E' - 64)
	    {
	      input_eol (focus);
	      draw_widget (focus);
	    }
	  else if (ch == 'F' - 64)
	    input_move (input_cursor_right);
	  else if (ch == 'K' - 64)
	    input_kill_fwd ();
	  else if (ch == 'U' - 64)
	    input_kill_bkwd ();
	}
      else if (ch == '\x7f')
	focus_next (-1);
      else if (focus->type == W_CHECKBOX && ch == ' ')
	checkbox_toggle ();
      else if (focus->type == W_BUTTON && ch == ' ')
	return 1;
      break;
      
    case 1:
      state = 0;
      if (ch == '[')
	state = 2;
      else if (focus->type == W_INPUT)
	switch (ch)
	  {
	  case 'b':
	    input_bkwd_word ();
	    break;

	  case 'd':
	    input_kill_word_fwd ();
	    break;

	  case 'f':
	    input_fwd_word ();
	    break;

	  case '\x7f':
	    input_kill_word_bkwd ();
	    break;
	  }
      else if (focus->type == W_MENU || focus->type == W_CHECKBOX)
	switch (ch)
	  {
	  case 'v':
	    menu_page_up ();
	    break;
	  }
      break;

    case 2:
      state = 0;
      if ((focus->type == W_MENU || focus->type == W_CHECKBOX) && ch == 'A')
	menu_up ();
      else if ((focus->type == W_MENU || focus->type == W_CHECKBOX)
	       && ch == 'B')
	menu_down ();
      else if (focus->type == W_INPUT && ch == 'C')
	input_move (input_cursor_right);
      else if (focus->type == W_INPUT && ch == 'D')
	input_move (input_cursor_left);
      else if (ch == 'A' || ch == 'D')
	focus_next (-1);
      else if (ch == 'B' || ch == 'C')
	focus_next (1);
      else
	{
	  if (ch >= '0' && ch <= '9')
	    {
	      accum = ch - '0';
	      state = 3;
	    }
	}
      break;

    case 3:
      state = 0;
      if (ch >= '0' && ch <= '9')
	{
	  accum = accum * 10 + ch - '0';
	  state = 3;
	}
      else if (ch == '~')
	{
	  if (focus->type == W_INPUT)
	    switch (accum)
	      {
	      case 1:
		input_move (input_bol);
		break;
	      
	      case 3:
		input_delete ();
		draw_widget (focus);
		break;
		
	      case 4:
		input_eol (focus);
		draw_widget (focus);
		break;
	      }
	  else if (accum == 3)
	    focus_next (-1);
	  else if (focus->type == W_MENU || focus->type == W_CHECKBOX)
	    switch (accum)
	      {
	      case 5:
		menu_page_up ();
		break;

	      case 6:
		menu_page_down ();
		break;
	      }
	}
      break;

    default:
      abort ();
    }

  return 0;
}

/* Sets the focused widget to W, if that's appropriate. */
static void
focus_widget (struct widget *w)
{
  struct widget *old_focus = focus;
  
  if (w == focus || w == NULL
      || w->type == W_TEXT)
    return;

  focus = w;
  boml_hide ();
  draw_widget (old_focus);
  draw_widget (focus);
  boml_show ();
}

/* Moves the focus to the next control, if DIR > 0, or to the previous
   control, if DIR < 0. */
static void
focus_next (int dir)
{
  struct widget *w;
  
  w = focus;
  if (w == NULL)
    return;

  do 
    {
      if (dir > 0)
	{
	  w = w->next;
	  if (w == NULL)
	    w = widgets_head;
	}
      else 
	{
	  w = w->prev;
	  if (w == NULL)
	    w = widgets_tail;
	}
    }
  while (w->type == W_TEXT);

  focus_widget (w);
}

/* Returns the command value of the button that caused the dialogue to
   terminate.  */
static int
dialogue_result (void)
{
  if (focus->type == W_BUTTON)
    return focus->p.button.command;
  else if (focus->type == W_MENU)
    return focus->p.menu.state[focus->p.menu.cursor];
  else
    return default_result;

  return -1;
}

/* Mouse handling functions. */

/* Returns 1 if (X,Y) lies inside widget W, 0 otherwise. */
static int 
point_in_widget (struct widget *w, int x, int y)
{
  return (x >= w->x && x < w->x + w->w
	  && y >= w->y && y < w->y + w->h);
}

/* Find the widget that contains the specified pixel.  Returns NULL if
   no widget contains that pixel.  */
static struct widget *
find_widget_at (int x, int y)
{
  struct widget *w;
  
  for (w = widgets_head; w; w = w->next)
    if (point_in_widget (w, x, y))
      return w;
  return NULL;
}

/* Draw widget W, but as if it had the focus if F != 0 or as if it
   didn't have the focus if F == 0. */
static void
draw_as_focused (struct widget *w, int f)
{
  struct widget *old_focus = focus;

  if (f)
    focus = w;
  else
    focus = NULL;
  draw_widget (w);

  focus = old_focus;
}

/* Process all mouse events in the queue.  Returns 1 if the dialogue
   interaction is now complete. */
static int
mouse (void)
{
  for (;;)
    {
      int event, x, y, btn;

      event = boml_event (&x, &y, &btn);
      if (event == BOML_E_NONE)
	return 0;

      if (grab)
	{
	  switch (event)
	    {
	    case BOML_E_MOVE:
	      if (point_in_widget (grab, x, y) ^ grab->p.button.focused)
		draw_as_focused (grab, !grab->p.button.focused);
	      break;

	    case BOML_E_RELEASE:
	      grab = NULL;
	      draw_widget (focus);
	      if (point_in_widget (focus, x, y))
		return 1;
	      break;
	    }

	  continue;
	}

      switch (event)
	{
	case BOML_E_PRESS:
	  {
	    /* Click to focus. */
	    struct widget *w = find_widget_at (x, y);
	    focus_widget (w);
	    if (focus != w)
	      continue;
	    
	    if (w->type == W_BUTTON)
	      grab = w;
	    else if (w->type == W_MENU || w->type == W_CHECKBOX)
	      {
		if (menu_click (x - w->x, y - w->y))
		  return 1;
	      }
	  }
	  break;
	}
    }
}
	      

/* Input line utilities. */

/* Move to the end of the line. */
static void
input_eol (struct widget *w)
{
  int width = 0;

  input_csr (w) = input_ofs (w) = input_len (w);
  width = cursor_width;
  while (input_ofs (w) > 0)
    {
      int cw = bogl_char_width (input_str (w)[input_ofs (w) - 1], input_font);

      if (cw + width > input_field_width (w))
	break;
      width += cw;
      input_ofs (w)--;
    }
}

/* Calculate the number of characters visible in input line widget W.
   The number of characters is stored into *COUNT, and their width into
   *WIDTH. */
void
input_visible_width (struct widget *w, int *count, int *width)
{
  int i;
  
  *count = 0;
  *width = 0;
  for (i = input_ofs (w); i < input_len (w); i++)
    {
      int cw = bogl_char_width (input_str (w)[i], input_font);
	    
      if (*width + cw > input_field_width (w))
	break;

      *width += cw;
      (*count)++;
    }
}

/* Calculates and returns the width of the cursor for the focused
   input line. */
int
input_cursor_width (struct widget *w)
{
  if (input_csr (w) < input_len (w))
    return bogl_char_width (input_str (w)[input_csr (w)], input_font);
  else
    return cursor_width;
}

/* Calculates and returns the horizontal offset of the the cursor from
   the left side of the cursor field in input widget W.  If SIDE is
   zero then the the offset of the left side of the cursor is
   returned, otherwise the right side. */
int
input_cursor_position (struct widget *w, int side)
{
  int width = bogl_metrics (&input_str (w)[input_ofs (w)],
			    input_csr (w) - input_ofs (w),
			    input_font);
  if (side)
    width += input_cursor_width (w);
  
  return width;
}

/* Move the cursor right.  Returns nonzero if the display is
   scrolled. */
static int
input_cursor_right (void)
{
  int adjust_ofs = 0;
  int width;

  if (input_csr (focus) >= input_len (focus))
    return 0;
  
  input_csr (focus)++;
  width = input_cursor_position (focus, 1);
  while (width > input_field_width (focus))
    {
      width -= bogl_char_width (input_str (focus)[input_ofs (focus)],
				input_font);
      input_ofs (focus)++;
      adjust_ofs = 1;
    }

  return adjust_ofs;
}

/* Move the cursor left.  Returns nonzero if the display is
   scrolled. */
static int
input_cursor_left (void)
{
  if (input_csr (focus) == 0)
    return 0;

  input_csr (focus)--;
  if (input_csr (focus) < input_ofs (focus))
    {
      input_ofs (focus) = input_csr (focus);
      return 1;
    }
  else
    return 0;
}

/* Insert the specified character in the line of the focused input
   line, and update the display. */
static void
input_insert (int ch)
{
  input_str (focus) = xrealloc (input_str (focus), input_len (focus) + 1);
  memmove (&input_str (focus)[input_csr (focus) + 1],
	   &input_str (focus)[input_csr (focus)],
	   input_len (focus) - input_csr (focus));
  input_str (focus)[input_csr (focus)] = ch;
  input_len (focus)++;
  input_cursor_right ();
  draw_widget (focus);
}

/* Backspace the focused input line and update the display. */
static void
input_backspace (void)
{
  if (input_csr (focus) == 0)
    return;

  memmove (&input_str (focus)[input_csr (focus) - 1],
	   &input_str (focus)[input_csr (focus)],
	   input_len (focus) - input_csr (focus));
  input_len (focus)--;
  input_cursor_left ();
}

/* Delete the focused input line and update the display. */
static void
input_delete (void)
{
  if (input_csr (focus) >= input_len (focus))
    return;

  memmove (&input_str (focus)[input_csr (focus)],
	   &input_str (focus)[input_csr (focus) + 1],
	   input_len (focus) - input_csr (focus));
  input_len (focus)--;
}

/* Delete from the cursor to the end of the line, and update the
   display. */
static void
input_kill_fwd (void)
{
  if (input_csr (focus) >= input_len (focus))
    return;
  
  input_len (focus) = input_csr (focus);
  draw_widget (focus);
}

/* Delete from the cursor to the beginning of the line, and update
   the display. */
static void
input_kill_bkwd (void)
{
  input_len (focus) -= input_csr (focus);
  memmove (input_str (focus), &input_str (focus)[input_csr (focus)],
	   input_len (focus) + 1);
  input_csr (focus) = 0;
  draw_widget (focus);
}

/* Return nonzero iff the character at position P relative to the
   cursor position is part of a word. */
static int
input_csr_is_word (int p)
{
  int ch = input_str (focus)[input_csr (focus) + p];
  
  return ((ch >= '0' && ch <= '9')
	  || (ch >= 'a' && ch <= 'z')
	  || (ch >= 'A' && ch <= 'Z')
	  || ch > 127);
}

/* Move the cursor forward a word and update the display. */
static void
input_fwd_word (void)
{
  int redraw = 0;

  boml_hide ();
  input_draw_cursor (0);
  
  while (input_csr (focus) < input_len (focus) && !input_csr_is_word (0))
    redraw |= input_cursor_right ();
  while (input_csr (focus) < input_len (focus) && input_csr_is_word (0))
    redraw |= input_cursor_right ();

  if (redraw)
    draw_widget (focus);
  else
    input_draw_cursor (1);
  boml_show ();
}

/* Move the cursor backward a word and update the display. */
static void
input_bkwd_word (void)
{
  int redraw = 0;

  boml_hide ();
  input_draw_cursor (0);

  input_cursor_left ();
  if (input_csr (focus) == 0)
    return;
  
  while (input_csr (focus) > 0 && !input_csr_is_word (0))
    redraw |= input_cursor_left ();
  while (input_csr (focus) > 0 && input_csr_is_word (-1))
    redraw |= input_cursor_left ();

  if (redraw)
    draw_widget (focus);
  else
    input_draw_cursor (1);
  boml_show ();
}

/* Delete word behind the cursor. */
static void
input_kill_word_bkwd (void)
{
  while (input_csr (focus) > 0 && !input_csr_is_word (-1))
    input_backspace ();
  while (input_csr (focus) > 0 && input_csr_is_word (-1))
    input_backspace ();

  draw_widget (focus);
}

/* Delete word in front of the cursor. */
static void
input_kill_word_fwd (void)
{
  while (input_csr (focus) < input_len (focus) && !input_csr_is_word (0))
    input_delete ();
  while (input_csr (focus) < input_len (focus) && input_csr_is_word (0))
    input_delete ();

  draw_widget (focus);
}

/* Draw the cursor, if VISIBLE != 0, or erase it, if VISIBLE == 0. */
static void
input_draw_cursor (int visible)
{
  int cursor_x;
  int fg, bg;

  if (visible)
    fg = window_bg_color, bg = text_color;
  else
    fg = text_color, bg = window_bg_color;

  cursor_x = focus->x + horz_margin + input_cursor_position (focus, 0);

  boml_hide ();
  if (focus->p.input.cursor < focus->p.input.length)
    {
      char cursor[2];
      
      cursor[0] = input_str (focus)[input_csr (focus)];
      cursor[1] = '\0';

      bogl_text (cursor_x, focus->y + 3, cursor, 1, fg, bg, 0, input_font);
    }
  else
    bogl_clear (cursor_x, focus->y + 3, cursor_x + cursor_width,
		focus->y + 3 + bogl_font_height (input_font), bg);
  boml_show ();
}

/* Move to the beginning of the input line.  Return nonzero if
   scrolled. */
static int
input_bol (void)
{
  input_csr (focus) = 0;
  if (input_ofs (focus))
    {
      input_ofs (focus) = 0;
      return 1;
    }
  else
    return 0;
}

/* Calls FUNC and redraws the entire widget if FUNC returns nonzero,
   or just the cursor otherwise. */
static void
input_move (int (*func) (void))
{
  boml_hide ();
  input_draw_cursor (0);
  if (func ())
    draw_widget (focus);
  else
    input_draw_cursor (1);
  boml_show ();
}

/* Menu utilities. */

/* Draw menu item INDEX for menu widget W with background color BG. */
static void
menu_draw_item (struct widget *w, int index, int bg)
{
  int fg;
  int y;

  boml_hide ();
  y = w->y + 3 + bogl_font_height (menu_font) * (index - w->p.menu.offset);

  fg = text_color;
  if (bg != -1)
    {
      bogl_clear (w->x + horz_margin, y,
		  w->x + w->w - horz_margin - arrow_width,
		  y + bogl_font_height (menu_font), bg);
      if (bg == menu_cursor_bg_color)
	fg = menu_cursor_fg_color;
    }
	    
  if (w->type == W_MENU)
    {
      if (w->p.menu.tag[index])
	bogl_text (w->x + horz_margin, y,
		   w->p.menu.tag[index], strlen (w->p.menu.tag[index]),
		   fg, -1, 0, menu_font);
    }
  else /* W_CHECKBOX */ 
    {
      char *s;

      s = w->p.checkbox.values[index] == '*' ? SYM_CHECKED : SYM_UNCHECKED;
      bogl_text (w->x + horz_margin, y, s, 1, fg, -1, 0, symbol_font);
    }
		 
  if (w->p.menu.item[index])
    bogl_text (w->x + horz_margin + w->p.menu.tag_width, y,
	       w->p.menu.item[index], strlen (w->p.menu.item[index]),
	       fg, -1, 0, menu_font);
  boml_show ();
}


/* Draws the cursor for the focused menu if VISIBLE != 0, or erases
   the cursor if VISIBLE == 0. */
static void
menu_draw_cursor (int visible)
{
  menu_draw_item (focus, focus->p.menu.cursor,
		  visible ? menu_cursor_bg_color : window_bg_color);
}

/* Move the focused menu's cursor to LOC. */
static void
menu_move_cursor (int loc)
{
  boml_hide ();
  menu_draw_cursor (0);
  focus->p.menu.cursor = loc;
  menu_draw_cursor (1);
  boml_show ();
}

/* Move up one item on the focused menu. */
static void
menu_up (void)
{
  if (focus->p.menu.cursor == 0)
    return;

  if (focus->p.menu.cursor == focus->p.menu.offset)
    {
      focus->p.menu.cursor--;
      focus->p.menu.offset--;
      draw_widget (focus);
    }
  else
    menu_move_cursor (focus->p.menu.cursor - 1);
}

/* Move down one item on the focused menu. */
static void
menu_down (void)
{
  if (focus->p.menu.cursor == focus->p.menu.length - 1)
    return;

  if (focus->p.menu.cursor == focus->p.menu.offset + focus->p.menu.shown - 1)
    {
      focus->p.menu.cursor++;
      focus->p.menu.offset++;
      draw_widget (focus);
    }
  else
    menu_move_cursor (focus->p.menu.cursor + 1);
}

/* Move up an entire page on the focused menu. */
static void
menu_page_up (void)
{
  if (focus->p.menu.cursor == 0)
    return;

  if (focus->p.menu.cursor != focus->p.menu.offset)
    menu_move_cursor (focus->p.menu.offset);
  else
    {
      focus->p.menu.offset -= focus->p.menu.shown;
      if (focus->p.menu.offset < 0)
	focus->p.menu.offset = 0;
      focus->p.menu.cursor = focus->p.menu.offset;
      draw_widget (focus);
    }
}

/* Move down an entire page on the focused menu. */
static void
menu_page_down (void)
{
  if (focus->p.menu.cursor == focus->p.menu.length - 1)
    return;

  if (focus->p.menu.cursor != focus->p.menu.offset + focus->p.menu.shown - 1)
    menu_move_cursor (focus->p.menu.offset + focus->p.menu.shown - 1);
  else 
    {
      focus->p.menu.offset += focus->p.menu.shown;
      if (focus->p.menu.offset > focus->p.menu.length - focus->p.menu.shown)
	focus->p.menu.offset = focus->p.menu.length - focus->p.menu.shown;
      focus->p.menu.cursor = focus->p.menu.offset + focus->p.menu.shown - 1;
      draw_widget (focus);
    }
}

/* Subtract the `struct timeval' values X and Y, storing the result in
   RESULT.  Return 1 if the difference is negative, otherwise 0.  */
     
int
timeval_subtract (struct timeval *result, struct timeval *x, struct timeval *y)
{
  /* Perform the carry for the later subtraction by updating Y. */
  if (x->tv_usec < y->tv_usec) {
    int nsec = (y->tv_usec - x->tv_usec) / 1000000 + 1;
    y->tv_usec -= 1000000 * nsec;
    y->tv_sec += nsec;
  }
  if (x->tv_usec - y->tv_usec > 1000000) {
    int nsec = (y->tv_usec - x->tv_usec) / 1000000;
    y->tv_usec += 1000000 * nsec;
    y->tv_sec -= nsec;
  }
     
  /* Compute the time remaining to wait.
     `tv_usec' is certainly positive. */
  result->tv_sec = x->tv_sec - y->tv_sec;
  result->tv_usec = x->tv_usec - y->tv_usec;
     
  /* Return 1 if result is negative. */
  return x->tv_sec < y->tv_sec;
}

/* The menu has been clicked at (X,Y) relative to the menu's
   location.  Returns nonzero if a menu selection is made. */
static int
menu_click (int x, int y)
{
  int loc;
  
  if (x >= focus->w - horz_margin - arrow_width)
    {
      if (y >= 3 && y < bogl_font_height (menu_font) + 3)
	menu_up ();
      else if (y >= 3 + (bogl_font_height (menu_font)
			 * (focus->p.menu.shown - 1))
	       && y <= 3 + bogl_font_height (menu_font) * focus->p.menu.shown)
	menu_down ();

      return 0;
    }

  loc = focus->p.menu.offset + y / bogl_font_height (menu_font);
  if (loc < 0)
    loc = 0;
  else if (loc >= focus->p.menu.length)
    loc = focus->p.menu.length - 1;
  
  {
    static struct timeval last;
    struct timeval this;
    
    gettimeofday (&this, NULL);
    if (loc != focus->p.menu.cursor)
      menu_move_cursor (loc);
    else if (focus->type == W_MENU)
      {
	/* Detect double-click. */
	struct timeval diff;
	
	if (!timeval_subtract (&diff, &this, &last)
	    && diff.tv_sec == 0 && diff.tv_sec < 400000)
	  return 1;
      }
    last = this;
  }

  if (focus->type == W_CHECKBOX && x < focus->p.checkbox.tag_width)
    checkbox_toggle ();

  return 0;
}

/* Checkbox functions. */

static void
checkbox_toggle (void)
{
  char *s;

  boml_hide ();
  if (focus->p.checkbox.values[focus->p.checkbox.cursor] == '*')
    {
      focus->p.checkbox.values[focus->p.checkbox.cursor] = ' ';
      s = SYM_UNCHECKED;
    }
  else
    {
      focus->p.checkbox.values[focus->p.checkbox.cursor] = '*';
      s = SYM_CHECKED;
    }

  bogl_text (focus->x + horz_margin,
	     (focus->y + 3
	      + (bogl_font_height (menu_font)
		 * (focus->p.checkbox.cursor - focus->p.checkbox.offset))),
	     s, 1, menu_cursor_fg_color, menu_cursor_bg_color, 0, symbol_font);
  boml_show ();
}

/* Scale functions. */

void 
bowl_set_scale (struct widget *w, long long value)
{
  if (w->p.scale.value == value)
    {
      bowl_refresh ();
      return;
    }
  
  w->p.scale.value = value;
  if (bogl_refresh)
    bowl_refresh ();
  else
    draw_widget (w);
}
