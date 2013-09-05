# BEGIN CONFIGURABLE SETTINGS

ifdef PPPD_SRCDIR
CFLAGS.pppd=	-I$(PPPD_SRCDIR)/include -I$(PPPD_SRCDIR)/pppd
endif
ifndef PPPD_LIBDIR
PPPD_LIBDIR=	/usr/lib/pppd/$(PPPD_VERSION)
endif

# END CONFIGURABLE SETTINGS

# __KERNGLUE__ hack needed because asm/param.h includes linux/config.h
# in some distributions
CFLAGS += $(CFLAGS.optimize) -I../kernel/include -I$(KERNEL_SRCDIR)/include -I.. \
       -I/usr/include/pppd -I/usr/include/net -I../ppp_headers \
	$(CFLAGS.pppd) -D__KERNGLUE__ -fPIC
LDFLAGS	+= -shared

all:	pppol2tp.so

pppol2tp.so: pppol2tp.c ../l2tp_event_rpc_xdr.o ../l2tp_event_rpc_client.o
	$(CC) -o $@ $(LDFLAGS) $(CFLAGS) -D_linux_=1 $^

install: pppol2tp.so
	$(INSTALL) -d $(DESTDIR)$(PPPD_LIBDIR)
	$(INSTALL) pppol2tp.so $(DESTDIR)$(PPPD_LIBDIR)

clean:
	-rm -rf *.o *.so
