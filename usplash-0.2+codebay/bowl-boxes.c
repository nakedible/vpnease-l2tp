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

#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdarg.h>
#include <sys/ioctl.h>
#include <linux/vt.h>

#include "boxes.h"
#include "bogl-font.h"
#include "bogl.h"
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
#ifndef unused
#define unused __attribute__((unused))
#endif

extern struct bogl_font *title_font;
extern struct bogl_font *text_font;
extern struct bogl_font *button_font;
extern struct bogl_font *input_font;
extern struct bogl_font *menu_font;


void
chvt (int vt_no)
{
  int fd = open ("/dev/tty0", O_RDWR);
  if (fd < 0)
    return;
  if (!ioctl (fd, VT_ACTIVATE, vt_no))
    ioctl (fd, VT_WAITACTIVE, vt_no);
  close (fd);
}

int 
setTitleFont (char *fontname)
{
  struct bogl_font *new_font = bogl_read_bdf(fontname);
  
  if (new_font == NULL)
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      return 1;
    }  
  title_font = new_font;
  bogl_refresh = 1;
  return 0;
}


int
setInputFont (char *fontname)
{
  struct bogl_font *new_font = bogl_read_bdf(fontname);
  
  if (new_font == NULL)
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      return 1;
    }  
  input_font = new_font;
  bogl_refresh = 1;
  return 0;
}

int
setTextFont (char *fontname)
{
  struct bogl_font *new_font = bogl_read_bdf(fontname);
  
  if (new_font == NULL)
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      return 1;
    }  
  text_font = new_font;
  bogl_refresh = 1;
  return 0;
}

int
setButtonFont (char *fontname)
{
  struct bogl_font *new_font = bogl_read_bdf(fontname);
  
  if (new_font == NULL)
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      return 1;
    }  
  button_font = new_font;
  bogl_refresh = 1;
  return 0;
}

int
setMenuFont (char *fontname)
{
  struct bogl_font *new_font = bogl_read_bdf(fontname);
  
  if (new_font == NULL)
    {
      fprintf (stderr, "Error loading fonts: %s\n", bogl_error ());
      return 1;
    }  
  menu_font = new_font;
  bogl_refresh = 1;
  return 0;
}

#if 0
int
setFont(struct boxFonts *fonts)
{
  if (!setMenuFont(fonts->menuFont))
    return 1;
  if (!setInputFont(fonts->inputFont))
    return 1;    
  if (!setButtonFont(fonts->buttonFont))
    return 1;    
  if (!setTitleFont(fonts->titleFont))
    return 1;    
  if (!setTextFont(fonts->textFont))
    return 1;
  return 0;        
}
#else
int
setFont (const char *fontname, const char *acm)
{
    return 0;
}
#endif

void
setMono(void)
{
#warning FIXME: mono detection
/*
  bogl_gray_scale (bootargs.ismono);
*/
  bogl_gray_scale (0);
  bogl_refresh = 1;
}

int 
stderrToTTY (int tty)
{
  static int fd = -1;
  char dev[10];

  /* stderr redirect only works on 2.0 kernels */
  /* FIXME: we need to figure out why it fails on 2.2 kernels.
   *        In the meantime skip it. */
#ifndef STANDALONE_TEST
#warning FIXME: kver test in stderrToTTY
#if 0
  /* REALLY FIXME */
  if (strncmp (kver, "2.0", 3))
#endif
#endif
    return 0;
  if (fd > 0)
    close (fd);
  snprintf (dev, 10, "/dev/tty%d", tty);
  if ((fd = open (dev, O_RDWR | O_NOCTTY)) < 0)
    return 1;
  if (-1 == dup2 (fd, 2))
    return 1;
  return 0;
}

void 
boxResume (void)
{
  stderrToTTY (3);
  bowl_init ();
}

void 
boxSuspend (void)
{
  bowl_done ();
  stderrToTTY (1);
}

void 
boxPopWindow (void)
{
  /* Not yet implemented. */
}

void 
boxFinished (void)
{
  bowl_done ();
  stderrToTTY (1);
}

void
boxInit (void) 
{
  chvt (1);
  bowl_init ();
  stderrToTTY(3);
}

int
pleaseWaitBox (const char *text)
{
  bowl_flush ();
  bowl_title (_("Please wait"));
  bowl_new_text (text);
  bowl_layout ();

  return 0;
}

int vaproblemBox(const char *title, const char *fmt, ...) {
  char *p;
  va_list ap;
  if ((p = malloc(128)) == NULL)
    return -1;
  
  va_start(ap, fmt);
  (void) vsnprintf(p, 128, fmt, ap);
  va_end(ap);

  problemBox(p, title);
  return 0;
}
		    

int
problemBox (const char *text, const char *title)
{
  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_button (_("Continue"), 0);
  bowl_layout ();
  bowl_run ();

  return 0;
}

int
wideMessageBox (const char *text, const char *title)
{
  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_button (_("Continue"), 0);
  bowl_layout ();
  bowl_run ();

  return 0;
}

int
perrorBox (const char *text)
{
  char buf[1024];
  snprintf (buf, 1024, "%s: %s", text, strerror (errno));
  problemBox (buf, _("Error"));
  return 0;
}

int
twoButtonBox (const char *text, const char *title,
	      const char *button1, const char *button2)
{
  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_button (button1, 1);
  bowl_new_button (button2, 0);
  bowl_layout ();
  return bowl_run ();
}

int
yesNoBox (const char *text, const char *title)
{
  return twoButtonBox (text, title, _("Yes"), _("No"));
}

char *
inputBox (const char *text, const char *title, const char *proto)
{
  char *s;

  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_input (&s, proto);
  bowl_new_button (_("Ok"), 1);
  bowl_new_button (_("Cancel"), 0);
  bowl_layout ();
  bowl_default (1);
  if (bowl_run ())
    return s;
  free (s);
  return NULL;
}

/*
int
enterDirBox (const char *title, const char *prompt, const char *dir, char *buf, size_t bufsize)
{
    char *s;
    int result;

    bowl_flush ();
    bowl_title (title);
    bowl_new_text (prompt);
    bowl_new_input (&s, dir);
    bowl_new_button (_("Ok"), 1);
    bowl_new_button (_("Cancel"), 0);
    bowl_layout ();
    bowl_default (1);

    if (bowl_run ())
    {
        strcpy (buf, s);   */ /* Actually, I must check whether the length of buf allows to hold a whole s */
/*
        result = DLG_OKAY;
    }
    else
        result = DLG_CANCEL;

    free (s);

    return result;
}
*/
int
menuBox (const char *text, const char *title,
	 struct d_choices *choices, int nchoices, int cancel)
{
  int i;

  for (i = 0; i < nchoices; i++)
    if (choices[i].tag || choices[i].string)
      choices[i].state = i;
    else
      choices[i].state = -1;
  
  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_menu ((struct bowl_menu_item *) choices, nchoices, 15);
  if (cancel)
    bowl_new_button (_("Cancel"), DLG_CANCEL);
  bowl_layout ();
  return bowl_run ();
}

int 
scaleBox (const char *text, const char *title, long long value, int action)
{
  static struct widget *scale;

  switch (action)
    {
    case SCALE_CREATE:
      bowl_flush ();
      bowl_title (title);
      bowl_new_text (text);
      scale = bowl_new_scale (value);
      bowl_layout ();
      bowl_refresh ();
      break;

    case SCALE_REFRESH:
      bowl_set_scale (scale, value);
      break;

    case SCALE_DELETE:
      bowl_flush ();
      bowl_refresh ();
      break;
    }

  return 0;
}

int
checkBox (const char *text, const char *title, int height unused,
          int width unused, char **choices, char **values, int nchoices)
{
  char *result;

  result = malloc (nchoices);
  memcpy (result, *values, nchoices);

  bowl_flush ();
  bowl_title (title);
  bowl_new_text (text);
  bowl_new_checkbox (choices, result, nchoices, 15);
  bowl_new_button (_("Ok"), 1);
  bowl_new_button (_("Cancel"), 0);
  bowl_default (1);
  bowl_layout ();
  if (bowl_run ())
    {
      memcpy (*values, result, nchoices);
      return DLG_CANCEL;
    }
  else
    return DLG_OKAY;
}

/*
 * tz_dialogBox
 * Dialog box for timezone selection and setting:
 * char *text         - Introductory info.
 * char *title        - Title in the dialog box
 * int height         - Height of the box
 * int width          - Width of the box.
 * struct list* files - List of the file options.
 * struct list* dirs  - List of the directory options.
 */
int tz_dialogBox(const char* text, const char* title, 
                 int height, int width,
                 struct list* files, struct list* dirs)
{
  const int count = 1 + dirs->nelem + 2 + files->nelem;
  struct bowl_menu_item menu[count];
  int i, j;

  for (i = 0; i < count; i++)
    {
      menu[i].tag = NULL;
      menu[i].command = -1;
    }
      
  i = 0;
  menu[i++].item = _("Directories:");
    
  for (j = 0; j < dirs->nelem; j++)
    {
      menu[i].item = dirs->data[j];
      menu[i].command = OPT_D + j;
      i++;
    }

  i++; /* Blank line. */
  menu[i++].item = _("Timezones:");
  
  for (j = 0; j < files->nelem; j++)
    {
      menu[i].item = files->data[j];
      menu[i].command = OPT_F + j;
      i++;
    }

  return menuBox (text, title, (struct d_choices *) menu,
		  count, 1);
}

#ifdef STANDALONE_TEST
int
main (void)
{
  bowl_init ();
#if 0
  twoButtonBox ("some sample text", "confirmation", "yes", "no");
#elif 0
  problemBox (MSG_SILO_PROBLEM, MSG_PROBLEM);
#elif 0
  for (;;)
    {
      pleaseWaitBox (MSG_RUNNING_LILO);
      sleep (2);
    }
#elif 0
  inputBox (MSG_LINUX_AND_SWAP, MSG_NO_SWAP_PARTITION, "/dev/sda1");
#elif 1
  {
      char buf[128];
      enterDirBox ("Enter a directory", "Here you must type the directory name", "/debian", buf, 128);
  }
#elif 1
  {
    struct d_choices opt[30];
    int i;

    for (i = 0; i < 30; i++)
      {
	opt[i].tag = malloc (16);
	sprintf (opt[i].tag, "таг %d", i);
	opt[i].string = malloc (128);
	sprintf (opt[i].string, "item %d", i);
	opt[i].state = i;
      }

    menuBox ("This is a little text", "I'm the title", opt, 30, 1);
  }
#elif 1
  {
    char *choices[30];
    char values[30];
    char *valuesp;
    int i;

    for (i = 0; i < 30; i++)
      {
	choices[i] = malloc (128);
	sprintf (choices[i], "item %d", i);
	values[i] = i % 2 ? '*' : ' ';
      }

    valuesp = values;
    checkBox ("This is a little text", "I'm the title", 10, 50,
	      choices, &valuesp, 30);
  }
#elif 0
  {
    int i;

    scaleBox ("Installing rescue floppy...", "Please wait",
	      10, SCALE_CREATE);
    for (i = 0; i <= 10; i++)
      {
	scaleBox (NULL, NULL, i, SCALE_REFRESH);
	sleep (1);
      }
  }
#elif 1
  bowl_new_text (MSG_BAD_FLOPPY MSG_LINUX_AND_SWAP);
  bowl_title (MSG_NO_SWAP_PARTITION);
  bowl_new_button (MSG_YES, 0);
  bowl_new_button (MSG_NO, 0);
  bowl_new_button (_("Cancel"), 0);
  bowl_new_button ("Quit", 0);
  bowl_new_button ("Help", 0);
  bowl_layout ();
  bowl_run ();
#endif

  return 0;
}
#endif
