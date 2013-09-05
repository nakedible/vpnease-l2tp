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
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/time.h>
#include <sys/types.h>
#include <termios.h>
#include <unistd.h>
#include <time.h>
#include "bogl.h"
#include "boml.h"

#define M_GPM
#define M_INPUT

#ifdef M_GPM
#include <sys/socket.h>
#include <sys/un.h>
#endif

#if defined __alpha__
#define M_SERIAL
#define M_PS2
#elif defined __i386__
#define M_SERIAL
#define M_PS2
#define M_MSBUS
#elif defined __mc68000__
#define M_ADB
#elif defined __powerpc__
#define M_SERIAL
#define M_ADB
#define M_PS2
#elif defined __sparc__
#define M_SUN
#endif

struct mouse;

/* Packet drivers and detection routines. */
#define N_SERIAL 0
#define N_PS2 0
#define N_MSBUS 0
#define N_ADB 0
#define N_SUN 0

#ifdef M_GPM
static int detect_gpm (void);
# ifndef M_SERIAL
#  define M_SERIAL_MS
static void ms_driver (struct mouse *);
# endif
#endif

#ifdef M_INPUT
# ifndef M_PS2
#  define M_PS2_DRIVER
static void ps2_driver (struct mouse *);
# endif
static int input_mouse_found = 0;
static void detect_input (void);
#endif
 
#ifdef M_SERIAL
#undef N_SERIAL
#define N_SERIAL 8
#define M_SERIAL_MS
static void detect_serial (void);
static void ms_driver (struct mouse *);
static void msc_driver (struct mouse *);
static void mman_driver (struct mouse *);
#endif

/* These next three are actually the same protocol, but bind to
   different files in /dev.  Thus they use bm_driver. */
#if defined(M_MSBUS) ||  defined(M_ADB) || defined(M_SUN)
static void bm_driver (struct mouse *);
#endif

#ifdef M_MSBUS
#undef N_MSBUS
#define N_MSBUS 1
static void detect_msbus (void);
#endif

#ifdef M_ADB
#undef N_ADB
#define N_ADB 1
static void detect_adb (void);
#endif

#ifdef M_SUN
#undef N_SUN
#define N_SUN 1
static void detect_sun (void);
#endif

#ifdef M_PS2
#undef N_PS2
#define N_PS2 1
#define M_PS2_DRIVER
static void detect_ps2 (void);
static void ps2_driver (struct mouse *);
#endif

#define N_DETECT (N_SERIAL + N_MSBUS + N_PS2 + N_ADB + N_SUN)

/* Detection progress. */
static void inc (void);

static void (*detect_callback) (int);
static int detect_count;

/* Mouse types. */
enum
  {
#ifdef M_SERIAL_MS
    /* Serial mice using the MS protocol */
    T_MS_SERIAL,		/* Microsoft. */
    T_MS3_SERIAL,		/* Microsoft Intellimouse. */
#endif

#ifdef M_SERIAL
    /* Other serial mice. */
    T_MSC_SERIAL,		/* Mouse Systems. */
    T_MMAN_SERIAL,		/* Logitech Mouseman. */
#endif

#ifdef M_MSBUS
    /* Bus mice. */
    T_MS_BUS,			/* Microsoft/Logitech. */
#endif

#ifdef M_ADB
    T_ADB,			/* Apple ADB */
#endif

#ifdef M_SUN
    T_SUN,			/* Sun */
#endif

#ifdef M_PS2_DRIVER
    /* PS/2 mice. */
    T_PS2,			/* Generic. */
#endif
  };

/* Mouse attributes description. */
struct mouse_info
  {
    char *name;				/* Name. */
    int packet_size;			/* (Initial) bytes per packet. */
    unsigned char id[4];		/* Packet identification info. */
    void (*driver) (struct mouse *);	/* Packet driver. */
  };

/* Some of the information below is borrowed from gpm. */
static struct mouse_info mouse_info[] = 
  {
#ifdef M_SERIAL_MS
    {"Microsoft serial",		3, {0x40,0x40,0x40,0x00}, ms_driver},
    {"Microsoft Intellimouse serial",	4, {0xc0,0x40,0xc0,0x00}, ms_driver},
#endif

#ifdef M_SERIAL
    {"Mouse Systems serial",		5, {0xf8,0x80,0x00,0x00}, msc_driver},
    {"Mouseman serial",			3, {0xe0,0x80,0x80,0x00}, mman_driver},
#endif

#ifdef M_MSBUS
    {"Microsoft bus",			3, {0xf8,0x80,0x00,0x00}, bm_driver},
#endif

#ifdef M_ADB
    {"Apple Desktop Bus",		3, {0xf8,0x80,0x00,0x00}, bm_driver},
#endif

#ifdef M_SUN
    {"Sun",		                3, {0xf8,0x80,0x00,0x00}, bm_driver},
#endif

#ifdef M_PS2_DRIVER
    {"Generic PS/2",			3, {0xc0,0x00,0x00,0x00}, ps2_driver},
#endif
  };

/* A mouse. */
struct mouse
  {
    struct mouse *next;		/* Linked list. */
    int type;			/* Type of mouse, one of T_*. */
    int fd;			/* File descriptor. */
    unsigned char pbuf[8];	/* Protocol buffer. */
    int ppos;			/* Number of bytes in buffer. */
    int packet_size;		/* Bytes per packet. */
  };

/* All detected mice. */
static struct mouse *mice;

/* Current mouse state. */
static int x, y;	/* Pointer location. */
static int show;	/* >0: Show the pointer. */
static int drawn;	/* !=0: Pointer is currently drawn. */
static int button;	/* Button down? */

/* Event queue. */
struct event
  {
    int type;		/* One of BOML_E_*. */
    int x;
    int y;
    int btn;
  };

/* Next or previous item in the queue after INDEX. */
#define q_next(INDEX) \
	((INDEX) + 1 < QUEUE_SIZE ? (INDEX) + 1 : 0)
#define q_prev(INDEX) \
	((INDEX) > 0 ? (INDEX) - 1 : QUEUE_SIZE - 1)

#define QUEUE_SIZE 8
static struct event queue[QUEUE_SIZE];
static int qh, qt;	

#ifdef M_SERIAL
static int probe_com (char *port, int pnp);
#endif
static void state (int dx, int dy, int button);

/* Mouse pointer. */
static const struct bogl_pointer *pointer;
static int pointer_colors[2];


/* Public code. */

int
boml_quick_init (void)
{
  static int inited = 0;
  if (inited)
    return inited - 1;
  inited = 1;
  
#ifdef M_GPM
  if(detect_gpm ())
    {
      inited++;
      return (inited - 1);
    }
#endif

#ifdef M_INPUT
  detect_input ();
  if (input_mouse_found)
    {
      inited++;
      return (inited - 1);
    }
#endif

  return (inited - 1);
}

/* Detects mice and initializes the mouse library. */
void
boml_init (void (*callback) (int))
{
  /* Assure idempotence. */
  static int inited = 0;
  if (inited)
    return;
  inited = 1;

  detect_callback = callback;
  detect_count = 0;

#ifdef M_PS2
  detect_ps2 ();
  inc ();
#endif

#ifdef M_MSBUS
  detect_msbus ();
  inc ();
#endif

#ifdef M_ADB
  detect_adb ();
  inc ();
#endif

#ifdef M_SUN
  detect_sun ();
  inc ();
#endif
 
#ifdef M_SERIAL
  detect_serial ();
#endif
}

/* Calls the callback, if any, with a report of the progress of mouse
   detection in percent, incremented to the next mark (out of N_DETECT
   marks total). */
static void
inc (void)
{
  detect_count++;
  if (detect_callback)
    detect_callback (100 * detect_count / N_DETECT);
}

/* Reads mouse activities from the proper port and update the screen
   pointer position. */
void
boml_refresh (void)
{
  int sx = x;
  int sy = y;
  /* How many bytes to read at once */
  int howmany = 1;
  struct mouse *mouse;

  for (mouse = mice; mouse; mouse = mouse->next)
    {
      struct mouse_info *minfo = &mouse_info[mouse->type];

      fcntl (mouse->fd, F_SETFL, O_NONBLOCK);
      /* On bus mice (which means also all m68k mice) we have to read
         three bytes instead of one... This might be true of other
         mice as well. */
#if defined(M_ADB)
      if (mouse->type == T_ADB)
	howmany = 3;
#endif /* M_ADB */
#if defined (M_MSBUS)
      if (mouse->type == T_MS_BUS)
	howmany = 3;
#endif /* M_MSBUS */
      while (read (mouse->fd, &mouse->pbuf[mouse->ppos], howmany) == howmany)
	{
#ifdef M_SERIAL
	  /* The MouseMan protocol is extremely fscked up.  Packets can
	     have 3 or 4 bytes.  Attempt to detect changing from 3 byte to
	     4 byte packets. */
	  if (mouse->type == T_MMAN_SERIAL
	      && mouse->ppos == 0
	      && (mouse->pbuf[0] & minfo->id[0]) != minfo->id[1]
	      && (mouse->pbuf[0] >> 4) <= 3)
	    {
	      int b = mouse->pbuf[0] >> 4;
	      mouse->packet_size = 4;
	      state (0, 0, b & 0x20);
	      mouse->ppos = 0;
	      continue;
	    }
#endif

	  if ((mouse->ppos == 0
	       && (mouse->pbuf[0] & minfo->id[0]) != minfo->id[1])
	      || (mouse->ppos == 1
		  && (mouse->pbuf[1] & minfo->id[2]) != minfo->id[3]))
	    {
	      /* Nope, not a packet */
	      mouse->ppos = 0;
	      continue;
	    }

	  mouse->ppos += howmany;
	  if (mouse->ppos >= mouse->packet_size)
	    {
	      minfo->driver (mouse);
	      mouse->ppos = 0;
	    }
	}
    }
  
  if ((sx != x || sy != y || !drawn) && show)
    {
      if (drawn)
	bogl_pointer (0, sx, sy, pointer, pointer_colors);
      bogl_pointer (1, x, y, pointer, pointer_colors);
      drawn = 1;
    }
}

/* Tells the library whether the mouse cursor is drawn.  This is
   different from whether it is *supposed* to be drawn.  For instance,
   if the screen got cleared by a VT switch, the mouse cursor may have
   been erased inadvertently. */
void
boml_drawn (int is_drawn)
{
  drawn = is_drawn;
}

/* Draw the mouse cursor if it's not drawn but it should be. */
void
boml_redraw (void)
{
  if (show > 0 && !drawn)
    {
      bogl_pointer (1, x, y, pointer, pointer_colors);
      drawn = 1;
    }
}

/* Show the mouse cursor.  The mouse cursor being `shown' is a
   recursive property: if you call boml_show() N times to show the
   cursor, then you must call boml_hide() N times in order to hide
   it. */
void
boml_show (void)
{
  if (!mice)
    return;

  show++;
  if (show == 1 && !drawn)
    {
      bogl_pointer (1, x, y, pointer, pointer_colors);
      drawn = 1;
    }
}

/* Hide the mouse cursor.  See comment above boml_show() for more
   details. */
void
boml_hide (void)
{
  if (!mice)
    return;

  show--;
  if (show == 0 && drawn)
    {
      bogl_pointer (0, x, y, pointer, pointer_colors);
      drawn = 0;
    }
}

/* Change the mouse cursor to pointer P.  The cursor is drawn in the
   colors specified by COLORS. */
void
boml_pointer (const struct bogl_pointer *p, int colors[2])
{
  boml_hide ();
  pointer = p;
  pointer_colors[0] = colors[0];
  pointer_colors[1] = colors[1];
  boml_show ();
}

/* If TEST == 0, sets all the mice' file descriptors into FDS.  If
   TEST != 0, returns if at least one file descriptor is set in
   FDS. */
int
boml_fds (int test, fd_set *fds)
{
  struct mouse *mouse;

  for (mouse = mice; mouse; mouse = mouse->next)
    if (test)
      {
	if (FD_ISSET (mouse->fd, fds))
	  return 1;
      }
    else
      FD_SET (mouse->fd, fds);

  return 0;
}

/* Check for mouse activity.  Returns the mouse event type.  Stores
   the mouse location into (X,Y) and the button status into BTN, where
   nonzero indicates the button is pressed. */
int
boml_event (int *x, int *y, int *btn)
{
  int type;
  
  if (qt == qh)
    return BOML_E_NONE;

  type = queue[qt].type;
  if (x)
    *x = queue[qt].x;
  if (y)
    *y = queue[qt].y;
  if (btn)
    *btn = queue[qt].btn;

  qt = q_next (qt);
  return type;
}

/* Bookkeeping. */

/* Add an event of the specified type to the event queue. */
static void
event (int type)
{
  /* Merge multiple movement events into a single events. */
  if (type == BOML_E_MOVE && qh != qt
      && queue[q_prev (qh)].type == BOML_E_MOVE)
    {
      queue[q_prev (qh)].x = x;
      queue[q_prev (qh)].y = y;
      return;
    }

  queue[qh].type = type;
  queue[qh].x = x;
  queue[qh].y = y;
  queue[qh].btn = button;
  
  qh = q_next (qh);
  if (qt == qh)
    qt = q_next (qt);
}
      
/* The mouse moved (DX,DY) units, and the button is in state BTN (!=0:
   pressed).  Record that fact. */
static void
state (int dx, int dy, int btn)
{
  if (dx || dy)
    {
      x += dx;
      y += dy;
      if (x < 0)
	x = 0;
      if (x >= bogl_xres)
	x = bogl_xres - 1;
      if (y < 0)
	y = 0;
      if (y >= bogl_yres)
	y = bogl_yres - 1;
    }
  if (btn != button)
    {
      button = btn;
      if (button)
	event (BOML_E_PRESS);
      else
	event (BOML_E_RELEASE);
    }
  else if (button)
    event (BOML_E_MOVE);
}

/* Add a mouse of type TYPE to the list of mice.  The mouse is open on
   file descriptor FD. */
static void
add_mouse (int type, int fd)
{
  struct mouse *mouse = malloc (sizeof (struct mouse));
  mouse->next = mice;
  mouse->type = type;
  mouse->fd = fd;
  mouse->ppos = 0;
  mouse->packet_size = mouse_info[type].packet_size;
  mice = mouse;
}

#ifdef M_GPM
/* If we have a gpm repeater, assume ms3. */
static int
detect_gpm (void)
{
  int ret;
  int fd;
  struct sockaddr_un sock;
  
  ret = 1;

  /* Make sure GPM is answering requests... */
  fd = socket (PF_UNIX, SOCK_STREAM, 0);  
  if(fd < 0)
    ret = 0;
  else
    {
      sock.sun_family = AF_UNIX;
      strcpy(sock.sun_path, "/dev/gpmctl");
      if(connect (fd, &sock, SUN_LEN(&sock)) < 0)
	ret = 0;
      close (fd);
    }

  fd = open ("/dev/gpmdata", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    return 0;
  
  /* Poll the mouse whether or not we could find gpm, in
     case it starts up later; but keep searching in that case. */
  add_mouse (T_MS3_SERIAL, fd);
  return ret;
}
#endif

#ifdef M_INPUT
/* Check for /dev/input/mice, by opening mouse0 instead -
   i.e. check that there's really a mouse there right now. 
   Keep it open anyway, but set the mouse found flag accordingly. */
static void
detect_input (void)
{
  int fd;

  fd = open("/dev/input/mouse0", O_RDONLY | O_NONBLOCK);
  if (fd >= 0) {
    input_mouse_found = 1;
    close(fd);
  }

  fd = open("/dev/input/mice", O_RDONLY | O_NONBLOCK);
  if(fd < 0)
    return;

  add_mouse(T_PS2, fd);
}
#endif

/* PS/2 mouse code. */

#ifdef M_PS2
/* Attempt to detect presence of a PS/2 mouse.  If successful, sets
   `type' to indicate mouse type. */
static void
detect_ps2 (void)
{
  static const unsigned char s2[] = { 246, 230, 244, 243, 100, 232, 3, };
  int fd;

  fd = open ("/dev/psaux", O_RDWR | O_NONBLOCK);
  if (fd < 0)
    return;

  write (fd, s2, sizeof s2);
  usleep (30000);
  tcflush (fd, TCIFLUSH);

  add_mouse (T_PS2, fd);
}
#endif /* M_PS2 */

#ifdef M_PS2_DRIVER
static void
ps2_driver (struct mouse *m)
{
  int x, y;

  x = y = 0;
  if (m->pbuf[1])
    x = (m->pbuf[0] & 0x10) ? m->pbuf[1] - 256 : m->pbuf[1];
  if (m->pbuf[2])
    y = (m->pbuf[0] & 0x20) ? 256 - m->pbuf[2] : -m->pbuf[2];

  state (x, y, m->pbuf[0] & 1);
}
#endif /* M_PS2_DRIVER */

/* Microsoft/Apple Busmouse and Sun mouse code. */

#ifdef M_MSBUS
/* Attempt to detect presence of a Microsoft bus mouse.  If
   successful, sets `type' to indicate mouse type. */
static void
detect_msbus (void)
{
  int fd = open ("/dev/inportbm", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    return;

  add_mouse (T_MS_BUS, fd);
}
#endif /* M_MSBUS */

#ifdef M_ADB
static void
detect_adb (void)
{
  int fd = open ("/dev/adbmouse", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    return;

  add_mouse (T_ADB, fd);
}
#endif /* M_ADB */

#ifdef M_SUN
/* FIXME: Reading the GPM code tells me that this is almost certainly
   wrong.  Some Sparc person will have to fix it. */
static void
detect_sun (void)
{
  int fd = open ("/dev/sunmouse", O_RDONLY | O_NONBLOCK);
  if (fd < 0)
    return;

  add_mouse (T_SUN, fd);
}
#endif /* M_SUN */

/* The decoder is definitely the same for all three though */
#if defined(M_ADB) || defined(M_SUN) || defined(M_MSBUS)
static void
bm_driver (struct mouse *m)
{
  signed char *p = (signed char *) (m->pbuf);
  state (p[1], -p[2], !(p[0] & 0x04));
}
#endif /* M_ADB || M_SUN || M_MSBUS */

/* Serial mice. */

#ifdef M_SERIAL
/* Attempt to detect presence of a serial mouse.  If successful, sets
   `type' to indicate mouse type. */
static void
detect_serial (void)
{
  static char device[] = "/dev/ttySx";

  for (device[9] = '0'; device[9] <= '3'; device[9]++)
    {
      int success;

      success = probe_com (device, 1);
      inc ();
      
      if (!success)	
	probe_com (device, 0);
      inc ();
    }
}
#endif /* M_SERIAL */

#ifdef M_SERIAL_MS
/* ms and ms3 protocols are the same except that ms3 has an extra byte
   in each packet. */
static void
ms_driver (struct mouse *m)
{
  state ((signed char) ((m->pbuf[0] & 0x03) << 6) | (m->pbuf[1] & 0x3f),
	 (signed char) ((m->pbuf[0] & 0x0c) << 4) | (m->pbuf[2] & 0x3f),
	 m->pbuf[0] & 0x20);
}
#endif

#ifdef M_SERIAL
static void
msc_driver (struct mouse *m)
{
  signed char *p = (signed char *) (m->pbuf);
  state (p[3] + p[1], p[4] - p[2], !(m->pbuf[0] & 0x04));
}

static void
mman_driver (struct mouse *m)
{
  if (m->packet_size == 4 && (m->pbuf[3] >> 4) == 0)
    m->packet_size = 3;
  
  state ((signed char) (((m->pbuf[0] & 0x03) << 6) | (m->pbuf[1] & 0x3f)),
	 (signed char) (((m->pbuf[0] & 0x0c) << 4) | (m->pbuf[2] & 0xef)),
	 m->pbuf[0] & 0x20);
}

#if 0
static void
logi_driver (struct mouse *m)
{
  state (m->pbuf[0] & 0x10 ? m->pbuf[1] : -m->pbuf[1],
	 m->pbuf[0] & 0x08 ? -m->pbuf[2] : m->pbuf[2],
	 m->pbuf[0] & 0x04);
}
#endif /* 0*/

#endif /* M_SERIAL_DRIVER */

#if 0
/* Test routine. */
int
main (void)
{
  boml_init ();
  return 0;
}
#endif

#ifdef M_SERIAL
/* The following code comes from mice.c in gpm-1.13, although it is
   heavily modified.  The original copyright notice is reproduced in
   full below. */

/*
 * mice.c - mouse definitions for gpm-Linux
 *
 * Copyright 1993        ajh@gec-mrc.co.uk (Andrew Haylett)
 * Copyright 1994-1998   rubini@linux.it (Alessandro Rubini)
 *
 *   This program is free software; you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation; either version 2 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 *
 *   You should have received a copy of the GNU General Public License
 *   along with this program; if not, write to the Free Software
 *   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 ********/

static void
set_speed (int fd, int old, unsigned short flags)
{
  struct termios tty;
  tcgetattr(fd, &tty);
    
  tty.c_iflag = IGNBRK | IGNPAR;
  tty.c_oflag = 0;
  tty.c_lflag = 0;
  tty.c_line = 0;
  tty.c_cc[VTIME] = 0;
  tty.c_cc[VMIN] = 1;
  tty.c_cflag = flags | old;
  tcsetattr(fd, TCSAFLUSH, &tty);

  write(fd, "*n", 2);
  usleep(100000);

  tty.c_cflag = flags | B1200;
  tcsetattr(fd, TCSAFLUSH, &tty);
}

static void
init_serial (int fd)
{
  const int flags = CS7 | CREAD | CLOCAL | HUPCL;

  /* Change to 1200 baud from any baud rate. */
  set_speed (fd, B9600, flags);
  set_speed (fd, B4800, flags);
  set_speed (fd, B2400, flags);
  set_speed (fd, B1200, flags);

  /* Flush pending input. */
  {
    struct timeval timeout = {0, 0};
    unsigned char c;
    fd_set set;
    
    FD_ZERO (&set);
    for (;;)
      {
	FD_SET (fd, &set);
	switch (select (fd+1, &set, NULL, NULL, &timeout))
	  {
	  case 1:
	    if (read(fd,&c,1)==0)
	      break;

	  case -1:
	    continue;
	  }
	break;
      }
  }
}

/* The code below is taken from the following files in the Red Hat 5.2
   mouseconfig-3.1.3 distribution.  It's been essentially rewritten.

   pnp_probe_com.c
   pnp_probe_com.h

   The original copyright notice is reproduced in full below.  All
   modifications are subject to the license at the top of this
   file. */

/* probe serial port for PnP/Legacy devices
 *
 *
 * Michael Fulbright (msf@redhat.com)
 *
 * Copyright 1997 Red Hat Software
 *
 * This software may be freely redistributed under the terms of the GNU
 * public license.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
 *
 */

struct pnp_com_id
  {
    unsigned char other_id[17];		/* For pre-PNP compatibility. */
    unsigned char other_len;		/* Length of the other_id. */
    unsigned char pnp_rev_major;	/* PnP major revision number. */
    unsigned char pnp_rev_minor;	/* PnP minor revision number. */
    unsigned char manufacturer[4];	/* EISA manufacturer (string). */
    unsigned char product_id[5];	/* Mfr determined product ID (string) */
    unsigned char serial_number[9];	/* Optional dev serial number (string) */
    unsigned char class_name[33];	/* Optional PnP Class name (string) */
    unsigned char driver_id[42];	/* Optional compat device IDs (string) */
    unsigned char user_name[42];	/* Optional verbose product descr (string) */
  };

/* There are two possible bytes to signify the start of a PnP ID
   string. */
#define BeginPnP1 0x28
#define BeginPnP2 0x08

/* Likewise, two possible stop bytes. */
#define EndPnP1   0x29
#define EndPnP2   0x09

/* These chars indicate extensions to the base dev id exist. */
#define ExtendPnP1 0x5c
#define ExtendPnP2 0x3c

#define PNP_COM_MAXLEN 256

/* Wait until there is data available on fd, for up to TIMEOUT
   microseconds. */
static int
wait_for_input (int fd, long timeout)
{
  struct timeval tv;
  fd_set ready;
  int n;

  tv.tv_sec = 0;
  tv.tv_usec = timeout;

  FD_ZERO (&ready);
  FD_SET (fd, &ready);

  n = select (fd + 1, &ready, NULL, &ready, &tv);
  return n;
}

static int
open_serial_port (char *port)
{
  int fd;

  fd = open (port, O_RDWR | O_NONBLOCK);
  if (fd < 0)
    return fd;

  /* Reset file so it is no longer in non-blocking mode. */
  if (fcntl (fd, F_SETFL, 0) < 0)
    {
      close (fd);
      return -1;
    }

  return fd;
}

/* <0 means ioctl error occurred. */
static int
get_serial_lines (int fd)
{
  int modem_lines;

  ioctl (fd, TIOCMGET, &modem_lines);
  return modem_lines;
}

/* <0 means ioctl error occurred */
static int
set_serial_lines (int fd, int modem_lines)
{
  return ioctl (fd, TIOCMSET, &modem_lines);
}

static int
get_serial_attr (int fd, struct termios *attr)
{
  return tcgetattr (fd, attr);
}

static int
set_serial_attr (int fd, struct termios *attr)
{
  return tcsetattr (fd, TCSANOW, attr);
}

/* Set serial port to 1200 baud, 'nbits' bits, 1 stop, no parity. */
static int
setup_serial_port (int fd, int nbits)
{
  struct termios attr;

  if (get_serial_attr (fd, &attr) < 0)
    return 0;
  
  attr.c_iflag = IGNBRK | IGNPAR;
  attr.c_cflag = 0;
  attr.c_cflag &= ~(CSIZE | CSTOPB | PARENB | PARODD | PARENB);
  attr.c_cflag |= CREAD | CLOCAL;	/*| CRTSCTS ; */
  if (nbits == 7)
    attr.c_cflag |= CS7 | CSTOPB;
  else
    attr.c_cflag |= CS8;
  attr.c_oflag = 0;
  attr.c_lflag = 0;

  attr.c_cc[VMIN] = 1;
  attr.c_cc[VTIME] = 5;

  cfsetospeed (&attr, B1200);
  cfsetispeed (&attr, B1200);

  return set_serial_attr (fd, &attr) >= 0;
}

/* Request for PnP info from serial device.  See page 6 of the pnpcom
   doc from Microsoft.  Returns nonzero only if successful. */
static int
init_pnp_com_seq1 (int fd)
{
  int modem_lines = get_serial_lines (fd);

  /* Turn off RTS and wait 200 ms for DSR to come up. */
  set_serial_lines (fd, modem_lines & ~(TIOCM_RTS));
  usleep (200000);

  /* See if DSR came up. */
  modem_lines = get_serial_lines(fd);
  if (!(modem_lines & TIOCM_DSR))
    {
      set_serial_lines (fd, modem_lines | TIOCM_DTR | TIOCM_RTS);
      return 0;
    }

  /* Com port setup, 1st phase.  Now we set port to be 1200 baud, 7
     bits, no parity, 1 stop bit. */
  if (!setup_serial_port (fd, 7))
    return 0;
  
  /* Drop DTR and RTS. */
  modem_lines &= ~(TIOCM_RTS | TIOCM_DTR);
  set_serial_lines (fd, modem_lines);
  usleep (200000);

  /* Bring DTR back up. */
  modem_lines |= TIOCM_DTR;
  set_serial_lines (fd, modem_lines);
  usleep (200000);

  /* Enter next phase. */
  modem_lines |= TIOCM_RTS;
  set_serial_lines (fd, modem_lines);
  usleep (200000);

  return 1;
}

/* See if this is a legacy mouse device.  Only called if the PnP probe
   above failed.  We turn off the mouse via RS232 lines, then turn it
   on.  If it spits out an 'M' character (at 1200 baud, 7N1) it could
   be a mouse.  Returns nonzero only if successful. */
static int
legacy_probe_com (int fd)
{
  /* Now we set port to be 1200 baud, 7 bits, no parity, 1 stop bit. */
  if (!setup_serial_port (fd, 7))
    return 0;

  /* Drop DTR and RTS, then bring them back up. */
  {
    int modem_lines = get_serial_lines (fd);

    set_serial_lines (fd, modem_lines & ~(TIOCM_RTS | TIOCM_DTR));
    usleep (200000);
    set_serial_lines (fd, modem_lines | TIOCM_DTR | TIOCM_RTS);
  }

  /* Start reading - quit after first character. */
  {
    int starttime = (int) time (NULL);
    
    for (;;)
      {
	if (wait_for_input (fd, 250000) <= 0)
	  return 0;

	/* Read a character. */
	{
	  unsigned char resp;
	
	  if (read (fd, &resp, 1) > 0)
	    return resp == 'M';
	  if (errno != EAGAIN)
	    return 0;
	}

	/* Shouldn't run more than 2 seconds. */
	if (time (NULL) - starttime > 2)
	  return 0;
      }
  }
}

/* Retrieve the PnP ID string.  Timeout after 3 seconds.  Should
   probably set a 200 msec timeout per char, as spec says.  If no char
   received, we're done.  Returns number of characters retrieved. */
static int
read_pnp_string (int fd, unsigned char *pnp_string, int *pnp_len)
{
  int pnp_index;
  time_t starttime;
  int end_char;

  pnp_index = 0;
  end_char = -1;
  starttime = time (NULL);

  for (;;)
    {
      unsigned char c;
      
      /* Don't wait more than 3 seconds. */
      if (time (NULL) - starttime > 4)
	break;

      /* Wait for a character to arrive. */
      if (wait_for_input (fd, 250000) <= 0)
	break;

      /* Read a byte. */
      {
	ssize_t nbytes = read (fd, &c, 1);
	
	if (nbytes < 0 && errno != EAGAIN)
	  break;
	if (nbytes == 0)
	  continue;
      }

      /* Store the byte. */
      if (pnp_index < 99)
	pnp_string[pnp_index++] = c;

      /* Check for end of string. */
      if (end_char != -1)
	{
	  if (c == end_char)
	    break;
	}
      else if (c == BeginPnP1)
	end_char = EndPnP1;
      else if (c == BeginPnP2)
	end_char = EndPnP2;
    }

  pnp_string[pnp_index] = 0;
  *pnp_len = pnp_index;

  return pnp_index;
}

/* Parse the PnP ID string into components.  Returns nonzero only if
   successful. */
static int
parse_pnp_string (unsigned char *pnp_id_string, int pnp_len,
		  struct pnp_com_id *pnp_id)
{
  unsigned char pnp_string[100];

  unsigned char *p1, *p2;
  unsigned char *start;
  unsigned char *curpos;

  int xlate_6bit;

  int stage;

  /* Clear out pnp_id and make a local copy of pnp_id_string. */
  memset (pnp_id, 0, sizeof (*pnp_id));
  memcpy (pnp_string, pnp_id_string, pnp_len + 1);

  /* First find the start of the PnP part of string.  Use the marker
     which points nearest to start of the string and is actually
     defined.  The length of the initial part cannot be more than 17
     bytes. */
  {
    
    p1 = memchr (pnp_string, BeginPnP1, pnp_len);
    p2 = memchr (pnp_string, BeginPnP2, pnp_len);

    start = p1;
    if (!start || (p2 && p2 < start))
      start = p2;
    if (!start || start - pnp_string > 17)
      return 0;
  }
  
  /* Copy everything before the start of the PnP block. */
  memcpy (pnp_id->other_id, pnp_string, start - pnp_string);
  pnp_id->other_len = start - pnp_string;

  /* Translate data in PnP fields if necessary. */
  if (start == p2)
    {
      unsigned char *cp;

      for (cp = start; ; cp++)
	{
	  /* Skip the revision fields (bytes 1 and 2 after start). */
	  if (cp != start + 1 && cp != start + 2)
	    *cp += 0x20;
	  putchar (*cp);
	  
	  if (*cp == EndPnP1)
	    break;
	}

      xlate_6bit = 1;
    }
  else
    xlate_6bit = 0;

  /* Now we get the PnP fields - all were zeroed out above. */
  curpos = start + 1;

  {
    int rev_tmp = ((curpos[0] & 0x3f) << 6) + (curpos[1] & 0x3f);
    pnp_id->pnp_rev_major = rev_tmp / 100;
    pnp_id->pnp_rev_minor = rev_tmp % 100;
  }
  curpos += 2;

  memcpy (pnp_id->manufacturer, curpos, 3);
  curpos += 3;

  memcpy (pnp_id->product_id, curpos, 4);
  curpos += 4;

  /* Now read extension fields, if any. */
  for (stage = 0; *curpos == ExtendPnP1 || *curpos == ExtendPnP2; stage++)
    {
      static const char extension_delims[] =
	{EndPnP1, ExtendPnP1, ExtendPnP2, 0};

      int len;

      unsigned char *endfield = strpbrk ((unsigned char*)++curpos, extension_delims);
      if (!endfield)
	return 0;

      /* If we reached the end of all PnP data, back off since
	 there is a checksum at the end of extension data. */
      len = endfield - curpos;
      if (*endfield == EndPnP1)
	len -= 2;
      
      switch (stage)
	{
	case 0:
	  if (len != 8 && len != 0)
	    return 0;
	  memcpy (pnp_id->serial_number, curpos, len);
	  break;

	case 1:
	  if (len > 33)
	    return 0;
	  memcpy (pnp_id->class_name, curpos, len);
	  break;

	case 2:
	  if (len > 41)
	    return 0;
	  memcpy (pnp_id->driver_id, curpos, len);
	  break;

	case 3:
	  if (len > 41)
	    return 0;
	  memcpy (pnp_id->user_name, curpos, len);
	  break;
	
	}

      curpos += len;
      if (*endfield == EndPnP1)
	break;
    }

  /* If we had any extensions, we expect and check a checksum. */
  if (stage)
    {
      unsigned int checksum;
      const unsigned char *cp;
      char hex_checksum[3];

      checksum = curpos[2];
      for (cp = start; cp < curpos; cp++)
	checksum += *cp;
      
      if (xlate_6bit)
	checksum -= 0x20 * (curpos - start + 1 - 2);
      
      sprintf (hex_checksum, "%.2X", checksum & 0xff);
      if (strncmp (hex_checksum, curpos, 2))
	return 0;
    }

  return 1;
}

static int
guess_mouse_type (struct pnp_com_id *pnp_id)
{
  int type;
  
  /* First, figure out whether it's a mouse or not. */
  if (pnp_id->class_name[0] == 0)
    {
      char *model;

      model = strstr (pnp_id->driver_id, "PNP");
      if (model)
	model += 3;
      else
	model = pnp_id->product_id;

      if (strncmp (model, "0F", 2))
	return -1;
    }
  else if (strcmp (pnp_id->class_name, "MOUSE"))
    return -1;
  
  /* It's a mouse.  Default to Microsoft protocol--most common. */
  type = T_MS_SERIAL;

  /* Test for some common mouse types.  Send me more! */
  {
    const char *mfg = pnp_id->manufacturer;
    const char *model = pnp_id->product_id;
    
    if (!strcmp (mfg, "MSH") && !strcmp (model, "0001"))
      type = T_MS3_SERIAL;
    else if (!strcmp (mfg, "LGI") && !strncmp (model, "80", 2))
      type = T_MMAN_SERIAL;
    else if (!strcmp (mfg, "KYE") && !strcmp (model, "0003"))
      type = T_MS3_SERIAL;
  }

  return type;
}

/* If PNP != 0, checks for a plug-n-play mouse on device PORT; if PNP
   == 0, checks for a legacy mouse on that device.  Returns nonzero if
   a device is found. */
static int
probe_com (char *port, int pnp)
{
  struct termios origattr;

  /* Open serial port. */
  int fd = open_serial_port (port);
  if (fd < 0)
    return 0;

  /* Save port attributes. */
  if (get_serial_attr (fd, &origattr) < 0)
    {
      close (fd);
      return 0;
    }

  /* Retrieve PnP string or check for legacy mouse. */
  if (pnp)
    {
      struct pnp_com_id pnp_id;

      unsigned char pnp_string[100];
      int pnp_strlen;

      if (init_pnp_com_seq1 (fd)
	  && read_pnp_string (fd, pnp_string, &pnp_strlen)
	  && parse_pnp_string (pnp_string, pnp_strlen, &pnp_id))
	{
	  int type = guess_mouse_type (&pnp_id);
	  if (type != -1)
	    {
	      add_mouse (type, fd);
	      return 1;
	    }
	}
    }
  else if (legacy_probe_com (fd))
    {
      init_serial (fd);

      /* FIXME: Must detect MS, MSC, LOGI. */
      add_mouse (T_MS_SERIAL, fd);
      return 1;
    }
  else
    {
      /* Restore port attributes. */
      set_serial_attr (fd, &origattr);
      close (fd);
    }

  return 0;
}

#endif /* M_SERIAL */
