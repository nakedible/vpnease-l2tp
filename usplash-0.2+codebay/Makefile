LIBS = -lc
LIB = libbogl.a
DEVLINK = libbogl.so
SONAME = libbogl.so.0
SHARED_LIB = libbogl.so.0.1

CFLAGS =  -g -D_GNU_SOURCE
WARNCFLAGS += -Wall -D_GNU_SOURCE
ALLCFLAGS = $(CFLAGS) $(WARNCFLAGS) $(FBCFLAGS)

architecture := $(shell dpkg-architecture -qDEB_BUILD_GNU_CPU)

LIBOBJECTS = $(LIBBOGLOBJECTS) $(LIBBOMLOBJECTS) $(LIBBOWLOBJECTS)	\
	$(LIBRSRCOBJECTS)
LIBBOGLOBJECTS = bogl.o bogl-font.o
LIBBOMLOBJECTS = arrow.o boml.o
LIBRSRCOBJECTS = helvB10.o
ARTWORK = usplash-artwork.so

SOURCES_DEP = arrow.c bdftobogl.c bogl-cfb.c bogl-cfb.h bogl-cfb8.c	\
bogl-cfb8.h bogl-font.c bogl-font.h bogl-pcfb.c bogl-pcfb.h		\
bogl-tcfb.c bogl-tcfb.h bogl-test.c bogl.c bogl.h boglP.h boml.c	\
boml.h pngtobogl.c usplash.c

ifeq (,)
	FBCFLAGS += -DBOGL_CFB_FB=1
	LIBBOGLOBJECTS += bogl-cfb.o bogl-pcfb.o bogl-tcfb.o
endif

ifneq (,$(filter i386 i486 arm ia64 x86_64,$(architecture)))
	FBCFLAGS += -DBOGL_VGA16_FB=1
	LIBBOGLOBJECTS += bogl-vga16.o
	SOURCES_DEP += bogl-vga16.c bogl-vga16.h
endif

OBJECTS = $(LIBOBJECTS)

GENERATED = helvB10.c helvB12.c helvR10.c timBI18.c usplash-artwork.c

#		 libutf8/libutf8_plug.so unifont-reduced.bgf
all:    depend $(SHARED_LIB) $(LIB) usplash bdftobogl reduce-font usplash-default.so

usplash-default.so: $(ARTWORK)
	cp $(ARTWORK) usplash-default.so

%.lo: %.c
	$(CC) $(ALLCFLAGS) -o $@ -fPIC -c $<

%.o: %.c
	$(CC) $(ALLCFLAGS) -o $@ -c $<

$(SHARED_LIB): $(OBJECTS:%.o=%.lo)
	$(CC) -shared -Wl,-soname,$(SONAME) -o $(SHARED_LIB) $(OBJECTS:%.o=%.lo)

reduce-font: reduce-font.c

$(LIB): $(OBJECTS)
	rm -f $(LIB)
	ar rcs $(LIB) $(OBJECTS)

bogl-test: $(LIB) bogl-test.c tux75.o
	$(CC) $(ALLCFLAGS) -o bogl-test bogl-test.c tux75.o $(LIB)

bdftobogl: $(LIBBOGLOBJECTS)
%.c: %.bdf bdftobogl
	./bdftobogl $< > $@

pngtobogl: pngtobogl.o
	$(CC) $(ALLCFLAGS) -o pngtobogl pngtobogl.o -lgd -lpng -lm

%.c: %.png pngtobogl
	./pngtobogl $< > $@

depend: .depend
.depend: $(SOURCES_DEP)
	$(CPP) $(ALLCFLAGS) -M $(SOURCES_DEP) > .depend

clean: 
	rm -rf reduce-font bterm bdftobogl pngtobogl *.o $(GENERATED) *-test lang.h tmp.*.c $(LIB) unifont-reduced.bgf unifont-reduced.bdf usplash usplash_write
	rm -f $(OBJECTS:%.o=%.lo) $(SHARED_LIB)
	rm -f $(ARTWORK) usplash-default.so
	rm -f .depend

distclean: clean
	rm -f $(LIB) .depend *~ .nfs*

force:

ifeq (.depend,$(wildcard .depend))
include .depend
endif

%.so: %.lo
	$(CC) -shared -Wl,-soname,$@ $< -o $@

usplash: libbogl.a usplash.c usplash_write.c 
	$(CC) $(ALLCFLAGS) usplash.c -o usplash libbogl.a -ldl
	$(CC) $(ALLCFLAGS) -o usplash_write usplash_write.c

install: all
	install -m644 usplash-default.so $(DESTDIR)/usr/lib/usplash
	install -m755 usplash usplash_write usplash_down $(DESTDIR)/sbin
