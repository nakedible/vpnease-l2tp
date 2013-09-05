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

#include "bogl.h"

/*
    0000111122223333       0000111122223333
   +----------------+     +----------------+
  0|***             |0   0|***             |0
  1|*  **           |1   1|*****           |1
  2|*    **         |2   2|*******         |2
  3| *     **       |3   3| ********       |3
  4| *       **     |4   4| **********     |4
  5|  *        **   |5   5|  ***********   |5
  6|  *          *  |6   6|  ************  |6
  7|   *     *****  |7   7|   ***********  |7
  8|   *      *     |8   8|   ********     |8
  9|    *  *   *    |9   9|    ********    |9
  a|    *  **   *   |a   a|    *********   |a
  b|     * * *   *  |b   b|     *** *****  |b
  c|     * *  *   * |c   c|     ***  ***** |c
  d|      *    *   *|d   d|      *    *****|d
  e|            * * |e   e|            *** |e
  f|             *  |f   f|             *  |f
   +----------------+     +----------------+
    0000111122223333       0000111122223333

*/

struct bogl_pointer pointer_arrow =
  {
    -1, -1,
    {
      0xe000, 0xf800, 0xfe00, 0x7f80,
      0x7fe0, 0x3ff8, 0x3ffc, 0x1ffc,
      0x1fe0, 0x0ff0, 0x0ff8, 0x077c,
      0x073e, 0x021f, 0x000e, 0x0004,
    },
    {
      0xe000, 0x9800, 0x8600, 0x4180,
      0x4060, 0x2018, 0x2004, 0x107c,
      0x1020, 0x0910, 0x0988, 0x0544,
      0x0522, 0x0211, 0x000a, 0x0004,
    },
  };


