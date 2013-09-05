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

/* bogl-cfb.h: Just contains the memset_var function, which has
   definitely gotten too large to be inlined (unless of course the
   bits-per-pixel argument is a constant, in which case most of it
   gets optimized away)

   Written by David Huggins-Daines <dhd@debian.org>.

   Somewhat based on sysdeps/generic/memset.c in GNU libc sources
   Copyright (C) 1991 Free Software Foundation, Inc. */

#include <assert.h>
#include "bogl-cfb.h"

/* Some notes:
   - len is counted in pixels, not bits!
   - Of course there are many architecture-specific ways to optimize
   this.  PPC can move things around in FP registers, 68040 can use
   MOVE16, on i686 there are string instructions, and of course we
   could probably use VIS registers on Sparc64.  Frankly, I don't
   care. */  
void*
memset_var(void* d, unsigned int c, ssize_t offset, size_t len, size_t b)
{
  unsigned char* dst;
  int i;

  /* 8 bits per pixel and less */
  if (b < 8)
    return memset_sub8(d, c, offset, len, b);
  if (b == 8)
    return memset((unsigned char*) d + offset, c, len);

  /* 24 bits per pixel */
  if (b == 24)
    return memset_24((unsigned char*) d + offset * 3, c, len, b);

  /* For anything else, assert that we are actually aligned on a pixel
     boundary, otherwise we are sure to lose */
  dst = (unsigned char*) d + offset * b / 8;
  assert((((unsigned int)dst * 8) % b) == 0);

  /* Sanity... */
  assert (b <= 32);

  /* 16/32 bits per pixel */
  if (len > 64)
    {
      /* Size of an "unsigned int" in pixels:
	 == sizeof(unsigned int) / b / 8 */
      const int intsiz = sizeof(unsigned int) * 8 / b;
      const unsigned int mask = (b == 32) ? ((unsigned int) -1) : ((1 << b) - 1);
      unsigned int fill;
      /* MUST be signed! */
      ssize_t xlen;
      
      /* Construct an "unsigned int" full of pixels */
      fill = 0;
      for (i = 0; i < intsiz; i++)
	fill |= (c&mask) << (b*i);
/*    printf ("c is %x, fill is %x\n\r", c, fill); */

/*    printf ("Filling %d pixels == %d bytes\n\r", len, len * b / 8); */
      /* Align to an int boundary */
      while ((unsigned int)dst % sizeof(unsigned int))
	{
/*        printf ("Aligning %d bytes\n\r", (unsigned int)dst % sizeof(unsigned int)); */
	  if (b >= 8)
	    {
	      put_var(dst, 0, c, b);
	      dst += b / 8;
	      len--;
	    }
	  else
	    {
	      int i;
	      for (i = 0; i < (8 / b); i++)
		{
		  put_var(dst, i, c, b);
		  len--;
		}
	      dst++;
	    }
	}

      /* Write 8 unsigned ints at a time for as long as possible */
      xlen = len / (intsiz * 8);
/*    printf ("Filling %d units of %d pixels\n\r", xlen, intsiz * 8); */
      while (xlen > 0)
	{
	  ((unsigned int *) dst)[0] = fill;
	  ((unsigned int *) dst)[1] = fill;
	  ((unsigned int *) dst)[2] = fill;
	  ((unsigned int *) dst)[3] = fill;
	  ((unsigned int *) dst)[4] = fill;
	  ((unsigned int *) dst)[5] = fill;
	  ((unsigned int *) dst)[6] = fill;
	  ((unsigned int *) dst)[7] = fill;
	  /* == 8 * intsiz * (b / 8) */
	  dst += intsiz * b;
	  xlen--;
	}
      len %= (intsiz * 8);
      
      /* Now individual unsigned ints */
      xlen = len / intsiz;
/*    printf ("Filling %d units of %d pixels\n\r", xlen, intsiz); */
      while (xlen > 0)
	{
	  ((unsigned int *) dst)[0] = fill;
	  dst += intsiz * b / 8;
	  xlen--;
	}
      len %= intsiz;
    }
  
  /* In any case, fill in some individual pixels */
/*    printf ("Filling %d pixels\n\r", len); */
  for (i = 0; i < len; i++)
    {
      put_var(dst, i, c, b);
    }
  return dst;
}
