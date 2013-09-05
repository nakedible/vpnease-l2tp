CFLAGS	:= -g -MMD -Wall -O2 -isystem ../kernel/include -I. -I.. -I../usl -fPIC $(EXTRA_CFLAGS)
LDFLAGS	:= -shared

PLUGINS.c:=	ppp_unix.c ppp_null.c ppp_test.c

PLUGINS.so=	$(PLUGINS.c:%.c=%.so)

SRC.generated=

.PHONY:		all clean install TAGS

all:		generated-files $(PLUGINS.so)

clean:
	$(RM) $(PLUGINS.so) $(wildcard *.o) $(wildcard *.d) $(SRC.generated)

%.so: %.c
	$(CC) -o $@ $(LDFLAGS) $(CFLAGS) $<

.PHONY:		generated-files

install:		all
			$(INSTALL) -d $(DESTDIR)/usr/lib/openl2tp
			$(INSTALL) $(PLUGINS.so) $(DESTDIR)/usr/lib/openl2tp


generated-files:	$(SRC.generated)

include $(wildcard *.d) /dev/null
