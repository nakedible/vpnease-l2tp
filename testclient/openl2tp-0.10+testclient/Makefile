# BEGIN CONFIGURABLE SETTINGS

# Define USE_DMALLOC to enable dmalloc memory debugging
# USE_DMALLOC=		y

# Define to include test code. This must be defined to run the
# regression tests
# L2TP_TEST=		y

# Define to compile in debug code. Also makes default trace flags
# enable all messages
# L2TP_DEBUG=		y

# Use asynchronous RPC requests where appropriate
# Affects only L2TP-PPP-IPPOOL interfaces, not management interfaces.
L2TP_USE_ASYNC_RPC=	y

# Build for UML environment?
# UML_TARGET=		y

# Compile the kernel module?
KERNEL_MODULE=		y

# Point to kernel source tree
KERNEL_SRCDIR=		/lib/modules/$(shell uname -r)/build

# Points to pppd install. 
# By default, pppd headers are assumed to be in /usr/include/pppd. but 
# can be pointed to a local pppd source tree if desired.
PPPD_VERSION=		2.4.4b1
# PPPD_SRCDIR=		/usr/local/src/ppp-2.4.3
# PPPD_LIBDIR=		/usr/lib/pppd/2.4.3

# Points to readline install root. READLINE_DIR should have lib/ & include/ subdirs
# If not defined, readline is assumed to be installed in the standard places that
# the compiler looks.
READLINE_DIR=		

# For cross-compiling
CROSS_COMPILE=

# END CONFIGURABLE SETTINGS

AS		= $(CROSS_COMPILE)as
LD		= $(CROSS_COMPILE)ld
CC		= $(CROSS_COMPILE)gcc
AR		= $(CROSS_COMPILE)ar
NM		= $(CROSS_COMPILE)nm
STRIP		= $(CROSS_COMPILE)strip
INSTALL		= $(CROSS_COMPILE)install

ifneq ($(READLINE_DIR),)
READLINE_LDFLAGS=	-L $(READLINE_DIR)/lib
READLINE_CFLAGS=	-I $(READLINE_DIR)/include
endif

export KERNEL_SRCDIR PPPD_VERSION PPPD_SRCDIR PPPD_LIBDIR READLINE_LDFLAGS READLINE_CFLAGS
export CROSS_COMPILE AS LD CC AR NM STRIP OBJCOPY OBJDUMP INSTALL UML_TARGET
export KERNEL_DESTDIR DESTDIR

SUBDIRS=		usl cli plugins pppd test doc

.PHONY:			$(SUBDIRS:%=subdir-%)

L2TP_RPC_STEM=		l2tp_rpc
L2TP_EVENT_RPC_STEM=	l2tp_event_rpc

RPC_FILES=		$(L2TP_RPC_STEM)_server.c $(L2TP_RPC_STEM)_client.c $(L2TP_RPC_STEM)_xdr.c $(L2TP_RPC_STEM).h \
			$(L2TP_EVENT_RPC_STEM)_server.c $(L2TP_EVENT_RPC_STEM)_client.c $(L2TP_EVENT_RPC_STEM)_xdr.c $(L2TP_EVENT_RPC_STEM).h

L2TPD_SRCS.c=		l2tp_main.c l2tp_common.c l2tp_api.c l2tp_avp.c l2tp_packet.c \
			l2tp_network.c l2tp_tunnel.c l2tp_peer.c l2tp_transport.c \
			l2tp_session.c l2tp_ppp.c \
			l2tp_plugin.c l2tp_test.c md5.c

L2TPD_SRCS.h=		l2tp_api.h l2tp_avp.h l2tp_private.h md5.h

ifeq ($(L2TP_TEST),y)
CPPFLAGS.l2tptest=	-DL2TP_TEST
endif

L2TPCONFIG_SRCS.c=	l2tp_config.c l2tp_common.c

L2TPD_SRCS.o=		$(L2TPD_SRCS.c:%.c=%.o) $(L2TP_RPC_STEM)_server.o $(L2TP_RPC_STEM)_xdr.o $(L2TP_EVENT_RPC_STEM)_server.o $(L2TP_EVENT_RPC_STEM)_xdr.o
L2TPCONFIG_SRCS.o=	$(L2TPCONFIG_SRCS.c:%.c=%.o) $(L2TP_RPC_STEM)_client.o $(L2TP_RPC_STEM)_xdr.o $(L2TP_EVENT_RPC_STEM)_client.o $(L2TP_EVENT_RPC_STEM)_xdr.o

ifeq ($(USE_DMALLOC),y)
CPPFLAGS.dmalloc=	-DL2TP_DMALLOC
LIBS.dmalloc=		-ldmalloc
export USE_DMALLOC
endif

CPPFLAGS=		$(CPPFLAGS.l2tptest)
CFLAGS=			-I. -Iusl -Icli -Ikernel/include -MMD -Wall -Werror $(CPPFLAGS) $(CPPFLAGS.dmalloc) $(OPT_CFLAGS)
LDFLAGS.l2tpd=		-Wl,-E -L. -Lusl -lusl -lnsl -ldl $(LIBS.dmalloc) -lc
LDFLAGS.l2tpconfig=	-Lcli -lcli -lreadline -lcurses -lnsl $(LIBS.dmalloc) $(READLINE_LDFLAGS) -lc

ifeq ($(L2TP_DEBUG),y)
CFLAGS.optimize=       -g
CPPFLAGS+=		-DDEBUG
else
CFLAGS.optimize=       -O2
endif
export CFLAGS.optimize

CFLAGS+=               $(CFLAGS.optimize)

ifeq ($(L2TP_USE_ASYNC_RPC),y)
CPPFLAGS+=		-DL2TP_ASYNC_RPC
endif

RPCGEN=			rpcgen
RPCGENFLAGS=		-N -M -C -L

.PHONY:			all clean distclean install kernel daemon app

all:			generated-files kernel daemon app

kernel:			FORCE
ifeq ($(KERNEL_MODULE),y)
			$(MAKE) -C $@ $(MFLAGS) EXTRA_CFLAGS="$(CPPFLAGS)"
endif

daemon:			generated-files kernel $(SUBDIRS:%=subdir-%) openl2tpd

app:			generated-files l2tpconfig

.PHONY:			$(SUBDIRS:%=subdir-%)

$(SUBDIRS:%=subdir-%):
			$(MAKE) -C $(@:subdir-%=%) $(MFLAGS) EXTRA_CFLAGS="$(CPPFLAGS)"

# Compile without -Wall because rpcgen-generated code is full of warnings.
# __KERNGLUE__ hack needed because asm/param.h includes linux/config.h
# in some distributions
%_xdr.o:		%_xdr.c
			$(CC) -I. -MMD -g -c $(CPPFLAGS) -D__KERNGLUE__ $<

%_client.o:		%_client.c
			$(CC) -I. -MMD -g -c $(CPPFLAGS) $<

%_server.o:		%_server.c
			$(CC) -I. -MMD -g -c $(CPPFLAGS) $<

%_xdr.c:		%.x
			-$(RM) $@
			$(RPCGEN) $(RPCGENFLAGS) -c -o $@ $<

%_server.c:		%.x
			-$(RM) $@ $@.tmp
			$(RPCGEN) $(RPCGENFLAGS) -m -o $@.tmp $<
			cat $@.tmp | sed -e 's/switch (rqstp->rq_proc) {/if (l2tp_api_rpc_check_request(transp) < 0) return; switch (rqstp->rq_proc) {/' > $@

%_client.c:		%.x
			-$(RM) $@
			$(RPCGEN) $(RPCGENFLAGS) -l -o $@ $<

%.h:			%.x
			-$(RM) $@
			$(RPCGEN) $(RPCGENFLAGS) -h -o $@ $<

.PHONY:			generated-files plugins clean distclean cxref

generated-files:	$(RPC_FILES) bits_per_long.h

clean:
			@for d in kernel $(SUBDIRS); do $(MAKE) -C $$d $(MFLAGS) $@; if [ $$? -ne 0 ]; then exit 1; fi; done
			-$(RM) $(L2TPD_SRCS.o) $(L2TPCONFIG_SRCS.o) openl2tpd l2tpconfig $(RPC_FILES)
			-$(RM) $(wildcard *.d) bits_per_long.h
			-$(RM) -r cxref
			-$(RM) $(wildcard l2tp_*rpc_*.tmp)

distclean:		clean
			-$(RM) TAGS

TAGS:
			@for d in $(SUBDIRS); do $(MAKE) -C $$d $(MFLAGS) $@; done
			etags -t $(wildcard *.c) $(wildcard *.h)

openl2tpd:		$(L2TPD_SRCS.o)
			$(CC) -o $@ $^ $(LDFLAGS.l2tpd)

l2tpconfig:		$(L2TPCONFIG_SRCS.o)
			$(CC) -o $@ $^ $(LDFLAGS.l2tpconfig)

%.o:	%.c
			$(CC) -c $(CFLAGS) $< -o $@

bits_per_long.h:
			echo "/* Auto-generated from asm/types.h */" > $@
ifneq ($(UML_TARGET),y)
			grep BITS_PER_LONG $(KERNEL_SRCDIR)/include/asm/types.h >> $@
else
			grep BITS_PER_LONG $(KERNEL_SRCDIR)/include/asm/arch/types.h >> $@
endif

cxref:
			-mkdir cxref
			cxref $(wildcard *.[ch] usl/*.[ch]) \
				-R. -Ocxref -no-comments -xref-func -raw  \
				$(CPPFLAGS) \
				-I. -Iusl -Icli -Ikernel/include > cxref/l2tp.raw

.PHONY:			all install-all install-daemon install-app kernel

install:		install-all

install-all:		all install-daemon install-app

install-daemon:
			@for d in $(SUBDIRS); do $(MAKE) -C $$d $(MFLAGS) install; if [ $$? -ne 0 ]; then exit 1; fi; done
			$(INSTALL) -d $(DESTDIR)/usr/sbin
			$(INSTALL) openl2tpd $(DESTDIR)/usr/sbin

install-app:
			$(INSTALL) -d $(DESTDIR)/usr/bin
			$(INSTALL) l2tpconfig $(DESTDIR)/usr/bin
			$(INSTALL) -d $(DESTDIR)/usr/lib/openl2tp
			$(INSTALL) l2tp_rpc.x $(DESTDIR)/usr/lib/openl2tp/l2tp_rpc.x
			$(INSTALL) l2tp_event_rpc.x $(DESTDIR)/usr/lib/openl2tp/l2tp_event_rpc.x


FORCE:

sinclude		$(wildcard *.d) /dev/null
