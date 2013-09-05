#  Requires:
#    * libparted-dev

CFLAGS=-Wall -Os -D_GNU_SOURCE
LIBS=-lparted -ldl

parted_all_devices:
	gcc -o parted_all_devices $(CFLAGS) parted_all_devices.c $(LIBS)

clean:
	rm -f parted_all_devices

