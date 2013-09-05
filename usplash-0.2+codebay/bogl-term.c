/* BOGL - Ben's Own Graphics Library.
   This file is by Edmund GRIMLEY EVANS <edmundo@rano.org>.

   Rendering optimisation and delay code
   (c) Copyright Red Hat Inc 2002  <alan@redhat.com>

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

/*
 * This implements a simple text console whose capatilities are
 * described by the terminfo source in "bterm.ti".
 */

#include <string.h>
#include "bogl.h"
#include "bogl-term.h"

#define MAX_CCHARS 5

struct bogl_term *bogl_term_new(struct bogl_font *font)
{
  struct bogl_term *term;
  int i;

  term = calloc(sizeof(struct bogl_term), 1);
  if (!term)
    return 0;

  term->font = font;
  term->xbase = term->ybase = 0;
  term->xstep = bogl_font_glyph(font, ' ', 0);
  term->ystep = bogl_font_height(font);
  if (term->xstep <= 0 || term->ystep <= 0) {
    free(term);
    return 0;
  }

  term->xsize = bogl_xres / term->xstep;
  term->ysize = bogl_yres / term->ystep;
  term->xpos = 0, term->ypos = 0;
  term->fg = term->def_fg = 0;
  term->bg = term->def_bg = 7;
  term->rev = 0;
  term->state = 0;
  term->cur_visible = 1;
  memset(&term->ps, 0, sizeof(&term->ps));

  term->screen = malloc(term->xsize * term->ysize * sizeof(wchar_t));
  term->dirty = malloc(term->xsize * term->ysize);
  term->screenfg = malloc(term->xsize * term->ysize * sizeof(int));
  term->screenbg = malloc(term->xsize * term->ysize * sizeof(int));
  term->screenul = malloc(term->xsize * term->ysize * sizeof(int));
  term->cchars = malloc(term->xsize * term->ysize * sizeof(wchar_t *));
  if (!term->screen || !term->screenfg || !term->screenbg || !term->screenul || !term->cchars || !term->dirty) {
    free(term->screen);
    free(term->screenfg);
    free(term->screenbg);
    free(term->screenul);
    free(term->cchars);
    free(term->dirty);
    free(term);
    return 0;
  }
  for (i = 0; i < term->xsize * term->ysize; i++) {
    term->screen[i] = ' ';
    term->screenfg[i] = term->def_fg;
    term->screenbg[i] = term->def_bg;
    term->screenul[i] = 0;
    term->cchars[i] = 0;
    term->dirty[i] = 1;
  }
  term->yorig = 0;

  return term;
}

#define XPOS(x) (term->xbase + term->xstep * (x))
#define YPOS(y) (term->ybase + term->ystep * (y))
#define SCR(x, y) \
((x) + (((y) + term->yorig) % term->ysize) * term->xsize)


static int term_match(struct bogl_term *term, int p1, int p2)
{
    if(term->screen[p1] != term->screen[p2])
    	return 0;
    if(term->screenfg[p1] != term->screenfg[p2])
    	return 0;
    if(term->screenbg[p1] != term->screenbg[p2])
    	return 0;
    if(term->screenul[p1] != term->screenul[p2])
    	return 0;
    return 1;
}

static int term_is_clear(struct bogl_term *term, int p1)
{
    if(term->screen[p1] != ' ')
    	return 0;
    if(term->screenfg[p1] != term->fg)
    	return 0;
    if(term->screenbg[p1] != term->bg)
    	return 0;
    if(term->screenul[p1] != 0)
    	return 0;
    return 1;
}

void
bogl_term_dirty (struct bogl_term *term)
{
  int x,y;
    
  for(y = 0; y < term->ysize; y++)
    for(x=0; x < term->xsize; x++)
      term->dirty[SCR(x,y)]=1;
}

/* We are scrolling so anything which isn't the same as the spot below
   is deemed dirty.  If this seems to be off by one, then it is, sort
   of.  When this function is called yorig is set such that (0,0) is
   the former left corner of the screen.  Right after we return yorig
   will be incremented, causing both the screen contents and the dirty
   array to be "scrolled".  So we have to mark the _lower_ spot dirty
   here.  */

static void dirty_scroll(struct bogl_term *term)
{
    int x,y;
    
    for(y = 0; y < term->ysize-1; y++)
    	for(x=0; x < term->xsize; x++)
    {
      int this_point = SCR(x,y);
      int next_point = SCR(x,y+1);
      if (term->dirty[this_point]
	  || !term_match (term, this_point, next_point))
	term->dirty[next_point] = 1;
    }
}

/* We are backscrolling so anything which isn't the same as the spot
   above is deemed dirty.  Same caveat as above, in reverse.  */
   
static void dirty_backscroll(struct bogl_term *term)
{
    int x,y;
    
    for(y = 1; y < term->ysize; y++)
    	for(x=0; x < term->xsize; x++)
    {
      int this_point = SCR(x,y);
      int next_point = SCR(x,y-1);
      if (term->dirty[this_point]
	  || !term_match (term, this_point, next_point))
	term->dirty[next_point] = 1;
    }
}

static void
cursor_down (struct bogl_term *term)
{
    int i;

    if (term->ypos < term->ysize - 1) {
        ++term->ypos;
        return;
    }

    dirty_scroll(term);
    ++term->yorig;

    for (i = 0; i < term->xsize; i++)
    {
        int p = SCR(i, term->ypos);

        term->screen[p] = ' ';
        term->screenfg[p] = term->fg;
        term->screenbg[p] = term->bg;
        term->screenul[p] = 0;
        term->dirty[p] = 1;
        free (term->cchars[p]);
        term->cchars[p] = 0;
    }
}

static void
put_char (struct bogl_term *term, int x, int y, wchar_t wc, wchar_t *cchars,
	  int fg, int bg, int ul)
{
    char buf[MB_LEN_MAX];
    int j, k, r, w;

    wctomb(0, 0);
    if ((k = wctomb(buf, wc)) == -1)
        return;

    if (bogl_in_font (term->font, wc))
    {
        bogl_text (XPOS(x), YPOS(y), buf, k, fg, bg, ul, term->font);

        if (cchars)
            for (j = 0; j < MAX_CCHARS && cchars[j]; j++)
            {
                wctomb(0, 0);
                if ((k = wctomb(buf, cchars[j])) != -1)
                bogl_text(XPOS(x), YPOS(y), buf, k, fg, -1, ul, term->font);
            }
    }
    else
    {
        /* repeat the default char w times */
        w = wcwidth(wc);
        for (r = 0; r < w; r++)
        bogl_text (XPOS(x + r), YPOS(y), buf, k, fg, bg, ul, term->font);
    }
}

static void
show_cursor (struct bogl_term *term, int show)
{
    int i, x, fg, bg;

    if ((x = term->xpos) == term->xsize)
        x = term->xsize - 1;

    i = SCR(x, term->ypos);

    while (!term->screen[i])
        --i, --x;

    if (term->screen[i])
    {
        if ((show && !term->rev) || (!show && term->rev))
            fg = term->screenbg[i], bg = term->screenfg[i];
        else
            fg = term->screenfg[i], bg = term->screenbg[i];
        put_char(term, x, term->ypos, term->screen[i], term->cchars[i], fg, bg, term->screenul[i]);
        term->dirty[SCR(x, term->ypos)] = 1;
    }
}

static void
clear_left (struct bogl_term *term)
{
    int j, i = SCR(term->xpos, term->ypos);
    if (!term->screen[i])
    {
        for (j = i - 1; !term->screen[j]; j--)
        {
            if(term->screen[j] != ' ')
            	term->dirty[j] = 1;
            term->screen[j] = ' ';
        }

        term->screen[j] = ' ';
        term->dirty[j] = 1;
    }
}

static void
clear_right (struct bogl_term *term)
{
  int j, i = SCR(term->xpos, term->ypos);

  for (j = 0; term->xpos + j < term->xsize && !term->screen[i + j]; j++)
  {
    if(term->screen[i + j] != ' ')
    {
    	term->dirty[i + j] = 1;
        term->screen[i + j] = ' ';
    }
  }
}

static void
term_clear_one (struct bogl_term *term, int i)
{
  if(!term_is_clear(term, i))
    {
      term->dirty[i] = 1;
      term->screen[i] = ' ';
      term->screenfg[i] = term->fg;
      term->screenbg[i] = term->bg;
      term->screenul[i] = 0;
    }
  free (term->cchars[i]);
  term->cchars[i] = 0;
}

void
bogl_term_out (struct bogl_term *term, char *s, int n)
{
    wchar_t wc;
    size_t k, kk;
    int i, j, w, txp, f, b, use_acs, x, y;
    char buf[MB_LEN_MAX];

    k = 0;
    while (1)
    {
	s += k;
	n -= k;

	/* The n <= 0 check was originally only necessary because of a bug
	   (?) in glibc 2.2.3, as opposed to libiconv.  glibc will
	   successfully convert a zero-length string.  It is also the only
	   exit point from this loop when we run out of characters, whether
	   we successfully decode a zero-length string or error out.  The
	   exception is an incomplete multibyte sequence, just below.  */
	if (n <= 0)
	    break;

	k = mbrtowc (&wc, s, n, &term->ps);

	/* If we fail to write a character, skip forward one byte and continue.
	   There's not much we can do to recover, but it's better than discarding
	   the whole line.  */
	if (k == (size_t) -1)
	{
	    k = 1;
	    /* The mbrtowc documentation suggests that we could use mbrtowc
	       to reset term->ps, but that doesn't work in practice; ps is in
	       an undefined state which appears to be the illegal state to make
	       the reset call in.  Use memset.  */
	    memset (&term->ps, 0, sizeof (term->ps));
	    continue;
	}
	else if (k == (size_t) -2)
	{
	    /* Incomplete character, so we exit and wait for more to arrive.  */
	    break;
	}

        if (!k)
            k = 1;

        txp = term->xp;
        term->xp = -1;

        if (wc == 0)            /* 0 has a special meaning in term->screen[] */
            continue;

        if (wc == 8)
        {                       /* cub1=^H */
            if (term->xpos)
                --term->xpos;
            term->state = 0;
            continue;
        }

        if (wc == 9)
        {                       /* ht=^I */
            int target;
            /* I'm not sure whether this way of going over the right margin
               is correct, so I don't declare this capability in terminfo. */
            target = (term->xpos / 8) * 8 + 8;
            while(term->xpos < target)
            {
	        if (term->xpos >= term->xsize)
	        {
	            term->xpos = 0;
	            cursor_down (term);
	            break;
	        }
	        bogl_term_out(term, " ", 1);
	    }
            term->state = 0;
            continue;
        }

        if (wc == 10)
        {                       /* ind=^J */
            cursor_down (term);
            term->state = 0;
            continue;
        }

        if (wc == 13)
        {                       /* cr=^M */
            term->xpos = 0;
            term->state = 0;
            continue;
        }

	if (wc == 14)
	{
	    term->acs = 1;
	    continue;
	}

	if (wc == 15)
	{
	    term->acs = 0;
	    continue;
	}

        if (wc == 27)
        {                       /* ESC = \E */
            term->state = -1;
            continue;
        }

        if (term->state == -1)
        {
            if (wc == '[')
            {
                term->state = 1;
                term->arg[0] = 0;
                continue;
            }
            /* `ri' capability: Scroll up one line.  */
            if (wc == 'M')
            {
                if (term->ypos > 0)
                    term->ypos--;
                else
                {
                    /* Delete the bottom line.  */
                    for (i = SCR (0, term->ysize - 1);
                         i < SCR (term->xsize, term->ysize - 1);
                         i++)
                        free (term->cchars[i]);

                    /* Move all other lines down.  Fortunately, this is easy.  */
                    dirty_backscroll(term);
                    term->yorig--;

                    /* Clear the top line.  */
                    for (i = SCR (0, 0); i < SCR (term->xsize, 0); i++)
                    {
                        term->screen[i] = ' ';
                        term->screenfg[i] = term->fg;
                        term->screenbg[i] = term->bg;
                        term->screenul[i] = 0;
                        term->cchars[i] = 0;
                        term->dirty[i] = 1;
                    }
                }
            }
            term->state = 0;
            continue;
        }

        if (term->state > 0)
        {
            if ('0' <= wc && wc <= '9')
            {
                if (term->state > sizeof (term->arg) / sizeof (int))
                    continue;

                term->arg[term->state - 1] *= 10;
                term->arg[term->state - 1] += wc - '0';
                continue;
            }
            if (wc == ';')
            {
                if (term->state > sizeof (term->arg) / sizeof (int))
                    continue;
                if (term->state < sizeof (term->arg) / sizeof (int))
                    term->arg[term->state] = 0;

                ++term->state;
                continue;
            }

            if (wc == '?')
            {
                if (term->state == 1 && term->arg[0] == 0)
                    ++term->state, term->arg[0] = -1, term->arg[1] = 0;
                else
                    term->state = 0;
                continue;
            }

            if (wc == 'H')
            {                   /* home=\E[H, cup=\E[%i%p1%d;%p2%dH */
                if (term->state < 3)
                {
                    if (term->state == 2)
                    {
                        if (term->arg[1] <= term->xsize)
                            term->xpos = term->arg[1] ? term->arg[1] - 1 : 0;
                    }
                    else
                        term->xpos = 0;
                    if (term->arg[0] <= term->ysize)
                        term->ypos = term->arg[0] ? term->arg[0] - 1 : 0;
                }
                term->state = 0;
                continue;
            }

            if (wc == 'J')
            {                   /* clear=\E[H\E[2J */
                /* arg[0]: 0 means clear cursor to end, 1 should mean clear
                   until cursor, 2 means clear whole screen.  */
                if (term->state == 1 && term->arg[0] == 2)
                {
                    for (i = 0; i < term->xsize * term->ysize; i++)
                    {
                    	if(!term_is_clear(term, i))
                    	{
	                    term->dirty[i] = 1;
	                    term->screen[i] = ' ';
	                    term->screenfg[i] = term->fg;
	                    term->screenbg[i] = term->bg;
	                    term->screenul[i] = 0;
	                }
                        free (term->cchars[i]);
                        term->cchars[i] = 0;
                    }
                }
                else if (term->state == 1 && term->arg[0] == 0)
                {
		  for (x = term->xpos; x < term->xsize; x++)
		    term_clear_one (term, SCR (x, term->ypos));

		  for (y = term->ypos + 1; y < term->ysize; y++)
		    for (x = 0; x < term->xsize; x++)
		      term_clear_one (term, SCR (x, y));

		  term->state = 0;
		  continue;
		}
            }

            if (wc == 'K')
            {                   /* el=\E[K */
                if (term->state == 1 && !term->arg[0])
                {
                    clear_left (term);
                    for (i = SCR (term->xpos, term->ypos); i < SCR (term->xsize, term->ypos); i++)
                    {
                        if(!term_is_clear(term, i))
                        {
                            term->dirty[i] = 1;
                            term->screen[i] = ' ';
                            term->screenfg[i] = term->fg;
                            term->screenbg[i] = term->bg;
                            term->screenul[i] = 0;
                        }
                        free (term->cchars[i]);
                        term->cchars[i] = 0;
                    }
                }
                term->state = 0;
                continue;
            }

            if (wc == 'h')
            {                   /* cnorm=\E[?25h */
                if (term->arg[0] == -1 && term->arg[1] == 25)
                    term->cur_visible = 1;
                term->state = 0;
                continue;
            }

            if (wc == 'l')
            {                   /* civis=\E[?25l */
                if (term->arg[0] == -1 && term->arg[1] == 25)
                    term->cur_visible = 0;

                term->state = 0;
                continue;
            }

            if (wc == 'm')
            {                   /* setab=\E[4%p1%dm, setaf=\E[3%p1%dm */
                if (term->arg[0] == 4 || term->arg[0] == 24)
                    term->ul = term->arg[0] == 4;
                else if (30 <= term->arg[0] && term->arg[0] < 38)
                    term->fg = term->arg[0] - 30;
                else if (40 <= term->arg[0] && term->arg[0] < 48)
                    term->bg = term->arg[0] - 40;
                else if (term->arg[0] == 39)
                    term->fg = term->def_fg;
                else if (term->arg[0] == 49)
                    term->bg = term->def_bg;
                else if (term->arg[0] == 7)
                    term->rev = 1;
                else if (term->arg[0] == 27)
                    term->rev = 0;
                else if (term->arg[0] == 0)
                {
                    term->rev = 0;
                    term->fg = term->def_fg;
                    term->bg = term->def_bg;
                }

                term->state = 0;
                continue;
            }

            term->state = 0;
            continue;
        }

	use_acs = 0;
	if (term->acs)
	{
            /* FIXME: If we are using a non-UTF-8 locale, the wcwidth
               call below will almost certainly fail.  We should have
               hardcoded results to fall back on in that case.  This
               will probably be fixed when I make this code drastically
               less dependent on mbrtowc and wctomb, which I really
               haven't figured out how to do yet.  They aren't really
               appropriate for a terminal emulator to be using!  */
	    switch (wc)
	    {
	    case 'q':
	      wc = 0x2500;
	      use_acs = 1;
	      break;
	    case 'j':
	      wc = 0x2518;
	      use_acs = 1;
	      break;
	    case 'x':
	      wc = 0x2502;
	      use_acs = 1;
	      break;
	    case 'a':
	      wc = 0x2591;
	      use_acs = 1;
	      break;
	    case 'm':
	      wc = 0x2514;
	      use_acs = 1;
	      break;
	    case 'l':
	      wc = 0x250c;
	      use_acs = 1;
	      break;
	    case 'k':
	      wc = 0x2510;
	      use_acs = 1;
	      break;
	    case 'u':
	      wc = 0x2524;
	      use_acs = 1;
	      break;
	    case 't':
	      wc = 0x251c;
	      use_acs = 1;
	      break;
	    }
	}

	/* At this point, if we can not decode a character because of ACS,
	   replace it with a space to minimize graphical corruption.  */
        if ((w = wcwidth (wc)) < 0)
        {
            if (use_acs)
            {
                wc = 0x20;
                w = wcwidth (wc);
            } else
                continue;
        }

        wctomb (0, 0);
        kk = wctomb (buf, wc);
        if (kk == -1)           /* impossible */
            continue;
#if 0
        {
            write (2, "p", 1);
        }
#endif

        f = term->rev ? term->bg : term->fg;
        b = term->rev ? term->fg : term->bg;
        
        if (w > 0)
        {
            if (w <= term->xsize)
            {

                if (term->xpos + w > term->xsize)
                {
                    clear_left (term);

                    for (i = SCR (term->xpos, term->ypos); i < SCR (term->xsize, term->ypos); i++)
                    {
                        if(!term_is_clear(term,i))
                        {
                            term->dirty[i] = 1;
                            term->screen[i] = ' ';
                            /* Use term->fg and term->bg rather than f and b - this is not
                               affected by reverse video. */
                            term->screenfg[i] = term->fg;
                            term->screenbg[i] = term->bg;
                            term->screenul[i] = 0;
                        }
                        free (term->cchars[i]);
                        term->cchars[i] = NULL;
                    }

                    term->xpos = 0;
                    cursor_down (term);
                }

                clear_left (term);
                i = SCR (term->xpos, term->ypos);
                term->dirty[i] = 1;
                term->screen[i] = wc;
                term->screenfg[i] = f;
                term->screenbg[i] = b;
                term->screenul[i] = term->ul;
                free (term->cchars[i]);
                term->cchars[i] = NULL;

                for (j = 1; j < w; j++)
                {
                    term->dirty[i + j] = 1;
                    term->screen[i + j] = 0;
                    term->screenfg[i + j] = f;
                    term->screenbg[i + j] = b;
                    term->screenul[i + j] = 0;
                }

                if (bogl_in_font (term->font, wc))
                {
                    term->xp = term->xpos, term->yp = term->ypos;
                    term->xpos += w;
                }
                else
                {
                    /* repeat the default char w times */
                    int r;

                    for (r = 0; r < w; r++)
                    {
                        term->xp = term->xpos, term->yp = term->ypos;
                        ++term->xpos;
                    }
                }

                clear_right (term);
            }
        }
        else
        {                       /* w == 0 */
            if (txp >= 0)
            {
                term->xp = txp;
//                bogl_text (XPOS (term->xp), YPOS (term->yp), buf, kk, f, -1, term->ul, term->font);
            }
            else
            {
                clear_left (term);
//                bogl_text (XPOS (term->xpos), YPOS (term->ypos), buf, kk, f, b, term->ul, term->font);
                term->xp = term->xpos, term->yp = term->ypos;
                term->xpos += 1;
                clear_right (term);
            }
        }
    }

}

void
bogl_term_redraw (struct bogl_term *term)
{
    int x, y, i;

    /* We should move these and distinguish redraw/refresh I guess
    		-- AC */
    		
    bogl_clear(0, YPOS(term->ysize), bogl_xres, bogl_yres, 0);
    bogl_clear(XPOS(term->xsize), 0, bogl_xres, YPOS(term->ysize), 0);
    for (y = 0; y < term->ysize; y++)
        for (x = 0; x < term->xsize; x++)
        {
            i = SCR(x, y);
            if (term->screen[i] && term->dirty[i])
            {
                put_char(term, x, y, term->screen[i], term->cchars[i], term->screenfg[i], term->screenbg[i], term->screenul[i]);
                term->dirty[i] = 0;
            }
        }
    if (term->cur_visible)
    {
        show_cursor(term, 1);
    }        
}
