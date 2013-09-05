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
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bogl.h"
#include "boglP.h"
#include "bogl-font.h"

#define INDEX_BITS 8
#define INDEX_MASK ((1<<INDEX_BITS)-1)

struct bogl_glyph
  {
    unsigned long char_width; /* ((wc & ~index_mask) | width) */
    struct bogl_glyph *next;
    u_int32_t *content;   /* (height * ((width + 31) / 32)) values */
  };

/* Returns nonzero iff LINE begins with PREFIX. */
static inline int
matches_prefix (const char *line, const char *prefix)
{
  return !strncmp (line, prefix, strlen (prefix));
}

/* Reads a .bdf font file in FILENAME into a struct bogl_font, which
   is returned.  On failure, returns NULL, in which case an error
   message can be retrieved using bogl_error(). */
struct bogl_font *
bogl_read_bdf (char *filename)
{
  char *font_name;
  int font_height;
  struct bogl_glyph *font_glyphs[1<<INDEX_BITS];

  /* Line buffer, current buffer size, and line number in input file. */
  char *line;
  size_t line_size;
  int ln = 0;

  /* Number of characters in font, theoretically, and the number that
     we've seen.  These can be different at the end because there may
     be named characters in the font that aren't encoded into
     character set. */
  int n_chars;
  int char_index;

  /* Font ascent and descent in pixels. */
  int ascent;
  int descent;

  /* Character to substitute when a character lacks a glyph of its
     own.  Normally the space character. */
  int default_char;

  /* .bdf file. */
  FILE *file;

  /* Read a line from FILE.  Returns nonzero if successful, reports an
     error message using bogl_fail() if not.  Strips trailing
     whitespace from input line. */
  int read_line (void)
  {
    ssize_t len;

    ln++;
    len = getline (&line, &line_size, file);
    if (len == -1)
      {
	if (ferror (file))
	  return bogl_fail ("reading %s: %s", filename, strerror (errno));
	else
	  return bogl_fail ("%s:%d: unexpected end of file", filename, ln);
      }

    while (len > 0 && isspace ((unsigned char) line[len - 1]))
      line[--len] = 0;
    
    return 1;
  }

  /* Attempt to malloc NBYTES bytes.  Sets a BOGL error message on
     failure.  Returns the result of the malloc() operation in any
     case. */
  void *
  smalloc (size_t nbytes)
  {
    void *p = malloc (nbytes);
    if (p == NULL)
      bogl_fail ("%s:%d: virtual memory exhausted", filename, ln);
    return p;
  }
  
  /* Parse header information.  Returns nonzero if successful, reports
     an error message using bogl_fail() if not.

     On success will always: set ascent, descent, default_char,
     font_height, and initialize font_glyphs. */
  int read_bdf_header (void)
  {
    int bbx = 0, bby = 0, bbw = 0, bbh = 0;
    ascent = descent = 0;
    default_char = ' ';
    
    for (;;)
      {
	if (!read_line ())
	  return 0;
	  
	if (matches_prefix (line, "FONT_ASCENT "))
	  ascent = atoi (line + strlen ("FONT_ASCENT "));
	else if (matches_prefix (line, "FONT_DESCENT"))
	  descent = atoi (line + strlen ("FONT_DESCENT"));
	else if (matches_prefix (line, "DEFAULT_CHAR "))
	  default_char = atoi (line + strlen ("DEFAULT_CHAR "));
	else if (matches_prefix (line, "FONTBOUNDINGBOX "))
	  sscanf (line + strlen ("FONTBOUNDINGBOX "), "%d %d %d %d",
		  &bbw, &bbh, &bbx, &bby);
	else if (matches_prefix (line, "CHARS "))
	  break;
      }

    n_chars = atoi (line + strlen ("CHARS "));
    if (n_chars < 1)
      return bogl_fail ("%s:%d: font contains no characters", filename, ln);

    /* Adjust ascent and descent based on bounding box. */
    if (-bby > descent)
      descent = -bby;
    if (bby + bbh > ascent)
      ascent = bby + bbh;

    font_height = ascent + descent;
    if (font_height <= 0)
      return bogl_fail ("%s:%d: font ascent (%d) + descent (%d) must be "
			"positive", filename, ln, ascent, descent);

    {
      int i;

      for (i = 0; i < (1<<INDEX_BITS); i++)
	font_glyphs[i] = NULL;
    }

    return 1;
  }

  /* Parse a character definition.  Returns nonzero if successful,
     reports an error message using bogl_fail() if not.

     Sets the character data into font->content, font->offset, and
     font->width as appropriate.  Updates char_index. */
  int read_character (void)
  {
    int encoding = -1;
    int width = INT_MIN;
    int bbx = 0, bby = 0, bbw = 0, bbh = 0;

    /* Read everything for this character up to the bitmap. */
    for (;;)
      {
	if (!read_line ())
	  return 0;

	if (matches_prefix (line, "ENCODING "))
	  encoding = atoi (line + strlen ("ENCODING "));
	else if (matches_prefix (line, "DWIDTH "))
	  width = atoi (line + strlen ("DWIDTH "));
	else if (matches_prefix (line, "BBX "))
	  sscanf (line + strlen ("BBX "), "%d %d %d %d",
		  &bbw, &bbh, &bbx, &bby);
	else if (matches_prefix (line, "BITMAP"))
	  break;
      }

    /* Adjust width based on bounding box. */
    if (width == INT_MIN)
      return bogl_fail ("%s:%d: character width not specified", filename, ln);
    if (bbx < 0)
      {
	width -= bbx;
	bbx = 0;
      }
    if (bbx + bbw > width)
      width = bbx + bbw;

    /* Put the character's encoding into the font table. */
    if (encoding != -1 && width <= INDEX_MASK)
      {
	u_int32_t *content, *bm;
	int i;
	struct bogl_glyph **t;

	t = &font_glyphs[encoding & INDEX_MASK];
	while (*t &&
	       (((*t)->char_width & ~INDEX_MASK) != (encoding & ~INDEX_MASK)))
	  t = &((*t)->next);
	if (*t)
	  return bogl_fail ("%s:%d: duplicate entry for character");

	*t = smalloc (sizeof (struct bogl_glyph));
	if (*t == NULL)
	  return 0;
	content = smalloc (sizeof (u_int32_t) *
			   font_height * ((width + 31)/32));
	if (content == NULL)
	  {
	    free (*t);
	    *t = NULL;
	    return 0;
	  }

	memset(content, 0,
	       sizeof (u_int32_t) * font_height * ((width + 31)/32));
	(*t)->char_width = (encoding & ~INDEX_MASK) | width;
	(*t)->next = NULL;
	(*t)->content = content;

	/* Read the glyph bitmap. */
	/* FIXME: This won't work for glyphs wider than 32 pixels. */
	bm = content;
	for (i = 0; ; i++) {
	  int row;

	  if (!read_line ())
	    return 0;
	  if (matches_prefix (line, "ENDCHAR"))
	    break;

	  if (encoding == -1)
	    continue;

	  row = font_height - descent - bby - bbh + i;
	  if (row < 0 || row >= font_height)
	    continue;
	  bm[row] = strtol (line, NULL, 16) << (32 - 4 * strlen (line) - bbx);
	}
    }

    /* Advance to next glyph. */
    if (encoding != -1)
      char_index++;

    return 1;
  }

  void free_font_glyphs (void)
  {
    int i;
    struct bogl_glyph *t, *tnext;

    for (i = 0; i < (1<<INDEX_BITS); i++)
      for (t = font_glyphs[i]; t != NULL; t = tnext)
	{
	  tnext = t->next;
	  free (t);
	}
  }

  /* Open the file. */
  file = fopen (filename, "r");
  if (file == NULL)
    {
      bogl_fail ("opening %s: %s\n", filename, strerror (errno));
      return NULL;
    }

  /* Make the font name based on the filename.  This is probably not
     the best thing to do, but it seems to work okay for now. */
  {
    unsigned char *cp;
    
    font_name = strdup (filename);
    if (font_name == NULL)
      {
	bogl_fail ("virtual memory exhausted");
	goto lossage;
      }
    
    cp = strstr (font_name, ".bdf");
    if (cp)
      *cp = 0;
    for (cp = (unsigned char *) font_name; *cp; cp++)
      if (!isalnum (*cp))
	*cp = '_';
  }

  line = NULL;
  line_size = 0;

  char_index = 0;

  /* Read the header. */
  if (!read_bdf_header ())
    goto lossage;

  /* Read all the glyphs. */
  {
    for (;;)
      {
	if (!read_line ())
	  goto lossage;

	if (matches_prefix (line, "STARTCHAR "))
	  {
#if 0
	    if (char_index >= n_chars)
	      {
		bogl_fail ("%s:%d: font contains more characters than "
			   "declared", filename, ln);
		goto lossage;
	      }
#endif
	    
	    if (!read_character ())
	      goto lossage;
	  }
	else if (matches_prefix (line, "ENDFONT"))
	  break;
      }

    /* Make sure that we found at least one encoded character. */ 
    if (!char_index)
      {
	bogl_fail ("%s:%d: font contains no encoded characters", filename, ln);
	goto lossage;
      }
  }

  /* Build the bogl_font structure. */
  {
    struct bogl_font *font = NULL;
    int *offset = NULL;
    int *index = NULL;
    u_int32_t *content = NULL;
    int index_size = 0, indexp = 0;
    int content_size = 0, contentp = 0;
    int i, j;

    for (i = 0; i < (1<<INDEX_BITS); i++)
      {
	struct bogl_glyph *t = font_glyphs[i];
	if (t != NULL)
	  {
	    for (; t != NULL; t = t->next)
	      {
		index_size += 2;
		content_size +=
		  font_height * (((t->char_width & INDEX_MASK) + 31) / 32);
	      }
	    ++index_size;
	  }
      }
	    
    font = smalloc (sizeof (struct bogl_font));
    offset = smalloc (sizeof (int) * (1<<INDEX_BITS));
    index = smalloc (sizeof (int) * index_size);
    content = smalloc (sizeof (u_int32_t) * content_size);
    if (font == NULL || offset == NULL || index == NULL || content == NULL)
      {
	free(font), free(offset), free(index), free(content);
	goto lossage;
      }

    for (i = 0; i < (1<<INDEX_BITS); i++)
      {
	struct bogl_glyph *t = font_glyphs[i];
	if (t == NULL)
	  offset[i] = index_size - 1;
	else
	  {
	    offset[i] = indexp;
	    for (; t != NULL; t = t->next)
	      {
		int n = font_height *
		  (((t->char_width & INDEX_MASK) + 31) / 32);
		index[indexp++] = t->char_width;
		index[indexp++] = contentp;
		for (j = 0; j < n; j++)
		  content[contentp++] = t->content[j];
	      }
	    index[indexp++] = 0;
	  }
      }
#if 0
    if (indexp != index_size || contentp != content_size)
      {
	bogl_fail ("Internal error");
	return NULL;
      }
#endif

    font->name = font_name;
    font->height = font_height;
    font->index_mask = INDEX_MASK;
    font->index = index;
    font->offset = offset;
    font->content = content;
    font->default_char = default_char;

    /* Clean up. */
    free_font_glyphs ();
    fclose (file);
    free (line);
    return font;
  }

 lossage:
  /* Come here on error. */
  free_font_glyphs ();
  free (line);
  fclose (file);
  return NULL;
}

/* Free FONT. */
void
bogl_free_font (struct bogl_font *font)
{
  free (font->name);
  free (font->offset);
  free (font->content);
  free (font);
}
