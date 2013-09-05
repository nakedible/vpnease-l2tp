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

/* bogl-cfb.h: Common inline functions and data structures used by the
   packed-pixel drivers.  This should be considered an internal,
   private header file.

   Written by David Huggins-Daines <dhd@debian.org> */

#include <sys/types.h>
#include <string.h>
#include <endian.h>

struct bits4 {
  unsigned int p0:4 __attribute__ ((packed));
  unsigned int p1:4 __attribute__ ((packed));
} __attribute__ ((packed));

struct bits24 {
  unsigned char bytes[3]  __attribute__ ((packed));
} __attribute__ ((packed));

static inline unsigned int
get_var (volatile void* src, size_t off, size_t b)
{
  unsigned int c;
  switch (b)
      {
      case 32:
	/* FIXME: probably has endianness problems */
	return ((u_int32_t*)(src))[off];
      case 24:
	/* FIXME: probably also has endianness problems */
	c  = ((struct bits24*)(src))[off].bytes[2] << 16;
	c += ((struct bits24*)(src))[off].bytes[1] << 8;
	c += ((struct bits24*)(src))[off].bytes[0];
	return c;
      case 16:
	return ((unsigned short*)(src))[off];
      case 8:
	return ((unsigned char*)(src))[off];
      case 4:
	if (off % 2)
	  return ((struct bits4*)(src))[off/2].p1;
	else
	  return ((struct bits4*)(src))[off/2].p0;
      }
  return 0;
}

static inline void
put_var (volatile void* dst, size_t off, unsigned int c, size_t b)
{
  switch (b)
      {
      case 32:
	/* FIXME: probably has endianness problems */
	((u_int32_t*)(dst))[off] = c;
	break;
      case 24:
	/* FIXME: probably also has endianness problems */
	((struct bits24*)(dst))[off].bytes[2] = (c >> 16);
	((struct bits24*)(dst))[off].bytes[1] = (c >> 8);
	((struct bits24*)(dst))[off].bytes[0] = c;
	break;
      case 16:
	((unsigned short*)(dst))[off] = c;
	break;
      case 8:
	((unsigned char*)(dst))[off] = c;
	break;
      case 4:
	if (off % 2)
	  ((struct bits4*)(dst))[off/2].p1 = c;
	else
	  ((struct bits4*)(dst))[off/2].p0 = c;
	break;
      }
}

static inline void*
memset_24(void* d, unsigned int c, size_t len, size_t b)
{
  unsigned char* dst = d;

  if (len > 8)
    {
      /* We have to use a block of 3 regardless of the sizeof(int) */
      unsigned int block[3];
      const unsigned int bsiz = sizeof(unsigned int);
      ssize_t xlen;
      
      /* Yes we have to do it this way due to little-endian brain
	 damage */
      put_var (block, 0, c, 24);
      put_var (block, 1, c, 24);
      put_var (block, 2, c, 24);
      put_var (block, 3, c, 24);
      
      if (sizeof(unsigned int) == 8)
	{
	  put_var (block, 4, c, 24);
	  put_var (block, 5, c, 24);
	  put_var (block, 6, c, 24);
	  put_var (block, 7, c, 24);
	}

      /* Align to an int boundary */
      while ((unsigned int)dst % sizeof(unsigned int))
	{
	  put_var(dst, 0, c, 24);
	  dst += 3;
	  len--;
	}
      
      xlen = len / bsiz;
      while (xlen)
	{
	  
	  ((unsigned int*)(dst))[0] = block[0];
	  ((unsigned int*)(dst))[1] = block[1];
	  ((unsigned int*)(dst))[2] = block[2];
	  dst += sizeof(block);
	  xlen--;
	}
      len %= bsiz;
    }
  
  /* Plot individual pixels */
  while (len--)
    {
      put_var(dst, 0, c, 24);
      dst += 3;
    }
  return dst;
}

static inline void*
memset_sub8(void* d, unsigned int c, ssize_t offset, size_t len, size_t b)
{
  unsigned char* dst = d;
  unsigned char fill;
  int i;

  /* Align to one byte */
  while (offset % (8 / b))
    {
      put_var (dst, offset, c, b);
      offset++;
      len--;
    }
  dst += offset * b / 8;

  /* Copy */
  for (i = 0; i*b < 8; i++)
    put_var (&fill, i, c, b);
  memset (dst, fill, len * b / 8);
  dst += len * b / 8;

  /* Align again */
  len %= 8 / b;
  for (i = 0; i < len; i++)
    {
      put_var (dst, i, c, b);
    }
  dst++;

  return dst;
}

void* memset_var(void* d, unsigned int c, ssize_t offset,
		 size_t len, size_t b);
