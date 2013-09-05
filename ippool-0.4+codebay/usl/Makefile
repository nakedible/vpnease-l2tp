#############################################################################
# Copyright (C) 2004 Katalix Systems Ltd
# 
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
#
#############################################################################

USL_SRCS.c=		usl_fd.c usl_misc.c usl_pid.c usl_signal.c \
			usl_timer.c usl_fsm.c
USL_SRCS.h=		usl_fsm.h usl.h usl_list.h
USL_SRCS_TEST.c=	usl_test.c

USL_SRCS.o=		$(USL_SRCS.c:%.c=%.o)
USL_SRCS_TEST.o=	$(USL_SRCS_TEST.c:%.c=%.o)

LDFLAGS.usl_test=	-L. -lc

CFLAGS=			-g -MMD -Wall -Werror -I. -I..

ifeq ($(USE_DMALLOC),y)
CPPFLAGS.dmalloc=	-DUSL_DMALLOC
LIBS.dmalloc=		-ldmalloc
endif

CPPFLAGS=		-DDEBUG
CFLAGS=			-I. -Icli -isystem kernel -MMD -Wall -g $(CPPFLAGS) $(CPPFLAGS.dmalloc)

.PHONY:			all test clean

all:			libusl.a

test:			libusl.a usl_test

libusl.a:		$(USL_SRCS.o)
			$(AR) rus $@ $^

usl_test:		$(USL_SRCS_TEST.o) libusl.a
			$(CC) -o $@ $(USL_SRCS_TEST.o) $(LDFLAGS.usl_test)

clean:
	$(RM) $(USL_SRCS.o) $(USL_SRCS_TEST.o) libusl.a usl_test $(wildcard *.d)

%.o:	%.c
			$(CC) -c $(CFLAGS) $< -o $@

install:		all
#			$(INSTALL) -d $(DESTDIR)/usr/lib
#			$(INSTALL) libusl.a $(DESTDIR)/usr/lib

checkin:		clean
			ci -u -q Makefile $(USL_SRCS.c) $(USL_SRCS.h) $(USL_SRCS_TEST.c)


include $(wildcard *.d /dev/null)

