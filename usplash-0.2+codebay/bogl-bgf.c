
#include <fcntl.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "bogl.h"
#include "bogl-font.h"

struct bogl_font *bogl_mmap_font(char *file)
{
  int fd;
  struct stat buf;
  void *f;
  struct bogl_font *font;

  fd = open(file, O_RDONLY);
  if (fd == -1)
    return 0;

  if (fstat(fd, &buf))
    return 0;

  f = mmap(0, buf.st_size, PROT_READ, MAP_SHARED, fd, 0);
  if (f == (void *)-1)
    return 0;

  if (memcmp("BGF1", f, 4))
    return 0;

  font = (struct bogl_font *)malloc(sizeof(struct bogl_font));
  if (!font)
    return 0;

  memcpy(font, f + 4, sizeof(*font));
  font->name = ((void *)font->name - (void *)0) + f;
  font->offset = ((void *)font->offset - (void *)0) + f;
  font->index = ((void *)font->index - (void *)0) + f;
  font->content = ((void *)font->content - (void *)0) + f;

  return font;
}
