#
# Makefile for the Linux Kernel modules
#

AS		= $(CROSS_COMPILE)as
LD		= $(CROSS_COMPILE)ld
CC		= $(CROSS_COMPILE)gcc
AR		= $(CROSS_COMPILE)ar
NM		= $(CROSS_COMPILE)nm
STRIP		= $(CROSS_COMPILE)strip
INSTALL		= $(CROSS_COMPILE)install

DEPMOD		= /sbin/depmod
DEPMOD_FLAGS	= $(shell uname -r)

obj-m = pppol2tp.o

# When cross-compiling, KERNEL_SRCDIR and KERNEL_DESTDIR must be defined
ifneq ($(CROSS_COMPILE),)
ifneq ($(KERNEL_SRCDIR),)
$(error KERNEL_SRCDIR must be defined when cross-compiling)
endif
ifneq ($(KERNEL_DESTDIR),)
$(error KERNEL_DESTDIR must be defined when cross-compiling)
endif
endif
KERNEL_SRCDIR	= /lib/modules/`uname -r`/build
KERNEL_DESTDIR	= $(DESTDIR)/lib/modules/`uname -r`/kernel/extra

export KERNEL_SRCDIR KERNEL_DESTDIR

# Derive KERNEL_VERSIOn from kernel makefile
KMAJ = $(shell cat $(KERNEL_SRCDIR)/Makefile | awk -F= '/^VERSION =/ {print $$2}' | \
		sed 's/^[ \t]*//;s/[ \t]*$$//')

KMIN = $(shell cat $(KERNEL_SRCDIR)/Makefile | awk -F= '/^PATCHLEVEL =/ {print $$2}' | \
		sed 's/^[ \t]*//;s/[ \t]*$$//')

KERNEL_VERSION = $(KMAJ).$(KMIN)

# Some source files are different for v2.4 and v2.6
PPPOL2TP_C = pppol2tp_v$(KMAJ)$(KMIN).c
IF_PPPOX.H = if_pppox_v$(KMAJ)$(KMIN).h

.PHONY:	clean test hfiles

############################################################################
# Handle 2.4 and 2.6 build differences
############################################################################

ifeq ($(KERNEL_VERSION),2.4)
# For 2.4 builds, we must hard-code compiler args according to architecture

PPPOL2TP_O=	$(obj-m)

ifneq ($(UML_TARGET),y)
ifeq ($(strip $(findstring ppc,$(ARCH))),ppc)
ARCH_CFLAGS=	-ffreestanding -ffixed-r2 -mmultiple -mstring
else
ifeq ($(strip $(findstring mips,$(ARCH))),mips)
ARCH_CFLAGS=	-mips2 -fno-pic -mlong-calls -mno-abicalls
else
ARCH_CFLAGS=	-mpreferred-stack-boundary=2
endif
endif

CFLAGS= -D__KERNEL__ -D__OPTIMIZE__ -I include -I $(KERNEL_SRCDIR)/include \
	-I $(KERNEL_SRCDIR)/arch/ppc \
	-Wstrict-prototypes -Wno-trigraphs -O2 -fno-strict-aliasing \
	-fno-common -fomit-frame-pointer -pipe $(ARCH_CFLAGS) \
	-Wall -DMODULE -DCONFIG_PPPOE_MODULE -DCONFIG_PPPOL2TP_MODULE
else
CFLAGS= -D__KERNEL__ -I include -I $(KERNEL_SRCDIR)/include \
	-I $(KERNEL_SRCDIR)/arch/um/include -Derrno=kernel_errno \
	-I $(KERNEL_SRCDIR)/arch/um/kernel/tt/include -I $(KERNEL_SRCDIR)/arch/um/kernel/skas/include \
	-Wstrict-prototypes -Wno-trigraphs -O2 -fno-strict-aliasing \
	-fno-common -fomit-frame-pointer -pipe -mpreferred-stack-boundary=2 \
	-U__i386__ -Ui386 -g -D__arch_um__ -DSUBARCH="i386" -D_LARGEFILE64_SOURCE \
	-Wall -DMODULE -DCONFIG_PPPOE_MODULE -DCONFIG_PPPOL2TP_MODULE
endif

all:	hfiles pppol2tp.o

pppol2tp.o: pppol2tp_v24.c
	$(CC) $(CFLAGS) -DKBUILD_BASENAME=$(basename $@) -c -o $@ $<

else

PPPOL2TP_O=	$(obj-m:%.o=%.ko)

# For 2.6, we let the kernel's build environment do the work

NOSTDINC_FLAGS := -I$(obj)/include -I$(KERNEL_SRCDIR)/include $(NOSTDINC_FLAGS)

all:	hfiles pppol2tp.c
	make -C $(KERNEL_SRCDIR) SUBDIRS=`pwd` V=1
endif

############################################################################
# Common targets
############################################################################

pppol2tp.c:	$(PPPOL2TP_C)
	cp $< $@
	chmod ug+w $@

hfiles:
	@if [ ! -e include/linux/if_pppox.h ]; then \
		cd include/linux ;\
		ln -s $(IF_PPPOX.H) if_pppox.h ;\
	fi
ifeq ($(KERNEL_VERSION),2.4)
	@if [ ! -e include/linux/list.h ]; then \
		cd include/linux ;\
		ln -s list_v24.h list.h ;\
	fi
	@if [ ! -e include/linux/hash.h ]; then \
		cd include/linux ;\
		ln -s hash_v24.h hash.h ;\
	fi
endif

test:
	$(MAKE) -C test $(MFLAGS) $@

clean:
	$(MAKE) -C test $(MFLAGS) $@
	rm -f pppol2tp.c include/linux/if_pppox.h include/linux/list.h include/linux/hash.h \
		pppol2tp.tmp* pppol2tp.ksyms
	rm -fr *.mod.c .*cmd *.o *.ko .tmp_versions

install:
	$(INSTALL) -d $(KERNEL_DESTDIR)
	$(INSTALL) $(PPPOL2TP_O) $(KERNEL_DESTDIR)
#ifeq ($(CROSS_COMPILE),)
#	$(DEPMOD) -a $(DEPMOD_FLAGS)
#endif

