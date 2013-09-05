#ifdef __linux__
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <unistd.h>

/*
 * Copied from Ubiquity debian-installer sources: parted_devices.c
 * Modified to output divice type: "normal", "readonly" or "cdrom"
 */

/* from <linux/cdrom.h> */
#define CDROM_GET_CAPABILITY    0x5331  /* get capabilities */
#endif /* __linux__ */

#include <parted/parted.h>

#ifdef __linux__
int
is_cdrom(const char *path)
{
  int fd;
  int ret;

  fd = open(path, O_RDONLY | O_NONBLOCK);
  ret = ioctl(fd, CDROM_GET_CAPABILITY, NULL);
  close(fd);

  if (ret >= 0)
    return 1;
  else
    return 0;
}
#else /* !__linux__ */
#define is_cdrom(path) 0
#endif /* __linux__ */

int
main(int argc, char *argv[])
{
  PedDevice *dev;
  char *status = "readwrite";
  char *type = "disk";
  ped_exception_fetch_all();
  ped_device_probe_all();
  for (dev = NULL; NULL != (dev = ped_device_get_next(dev));) {
    if (dev->read_only)
      status = "readonly";
    if (is_cdrom(dev->path))
      type = "cdrom";
    printf("%s\t%s\t%s\t%lli\t%s\n",
	   dev->path,
	   type,
	   status,
	   dev->length * PED_SECTOR_SIZE,
	   dev->model);
  }
  return 0;
}
