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

CLI_SRCS.c=		cli_lib.c cli_readline.c
CLI_SRCS.h=		cli_api.h cli_private.h
CLI_SRCS_TEST.c=	cli_test.c

CLI_SRCS.o=		$(CLI_SRCS.c:%.c=%.o)
CLI_SRCS_TEST.o=	$(CLI_SRCS_TEST.c:%.c=%.o)

LDFLAGS.cli_test=	-L.. -L. $(READLINE_LDFLAGS) -lcli -lusl -lreadline -lcurses -lc

CFLAGS=			-g -MMD -Wall -Werror -I.. $(READLINE_CFLAGS)

.PHONY:			all test clean

all:			libcli.a

test:			libcli.a cli_test

libcli.a:		$(CLI_SRCS.o)
			$(AR) rus $@ $^

cli_test:		$(CLI_SRCS_TEST.o) libcli.a
			$(CC) -o $@ $(CLI_SRCS_TEST.o) $(LDFLAGS.cli_test)

clean:
	$(RM) $(CLI_SRCS.o) $(CLI_SRCS_TEST.o) libcli.a cli_test $(wildcard *.d)

%.o:	%.c
			$(CC) -c $(CFLAGS) $< -o $@

install:		all
#			$(INSTALL) -d $(DESTDIR)/usr/lib
#			$(INSTALL) libcli.a $(DESTDIR)/usr/lib

include $(wildcard *.d /dev/null)
