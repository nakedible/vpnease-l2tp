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

/* Symbol font definition. */

#include "bogl.h"

/* Offsets into index. */
static int symbol_offset[16] = {
  11, 0, 3, 6, 9, 11, 11, 11,
  11, 11, 11, 11, 11, 11, 11, 11,
};

/* Index into content data. */
static int symbol_index[] = {
  0x8, 0,
  0,
  0x8, 12,
  0,
  0x5, 24,
  0,
  0x5, 36,
  0,
};

/* Font character content data. */

u_int32_t symbol_content[] = {

/* Character 0x01:
   +--------------------------------+
   |                                |
   |                                |
   |*******                         |
   |*     *                         |
   |*     *                         |
   |*     *                         |
   |*     *                         |
   |*     *                         |
   |*******                         |
   |                                |
   |                                |
   |                                |
   +--------------------------------+ */
0x00000000,
0x00000000,
0xfe000000,
0x82000000,
0x82000000,
0x82000000,
0x82000000,
0x82000000,
0xfe000000,
0x00000000,
0x00000000,
0x00000000,

/* Character 0x02:
   +--------------------------------+
   |                                |
   |                                |
   |*******                         |
   |*     *                         |
   |* * * *                         |
   |*  *  *                         |
   |* * * *                         |
   |*     *                         |
   |*******                         |
   |                                |
   |                                |
   |                                |
   +--------------------------------+ */
0x00000000,
0x00000000,
0xfe000000,
0x82000000,
0xaa000000,
0x92000000,
0xaa000000,
0x82000000,
0xfe000000,
0x00000000,
0x00000000,
0x00000000,

/* Character 0x03:
   +--------------------------------+
   |                                |
   |                                |
   |  *                             |
   | ***                            |
   |*****                           |
   |  *                             |
   |  *                             |
   |  *                             |
   |  *                             |
   |                                |
   |                                |
   |                                |
   +--------------------------------+ */
0x00000000,
0x00000000,
0x20000000,
0x70000000,
0xf8000000,
0x20000000,
0x20000000,
0x20000000,
0x20000000,
0x00000000,
0x00000000,
0x00000000,

/* Character 0x04:
   +--------------------------------+
   |                                |
   |                                |
   |  *                             |
   |  *                             |
   |  *                             |
   |  *                             |
   |*****                           |
   | ***                            |
   |  *                             |
   |                                |
   |                                |
   |                                |
   +--------------------------------+ */
0x00000000,
0x00000000,
0x20000000,
0x20000000,
0x20000000,
0x20000000,
0xf8000000,
0x70000000,
0x20000000,
0x00000000,
0x00000000,
0x00000000,

};

struct bogl_font font_symbol =
  {
    "symbol",
    12,
    0x0f,
    symbol_offset,
    symbol_index,
    symbol_content,
  };
