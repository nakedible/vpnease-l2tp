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

# BEGIN CONFIGURABLE SETTINGS

ifdef PPPD_SRCDIR
CFLAGS.pppd=	-I$(PPPD_SRCDIR)/include -I$(PPPD_SRCDIR)/pppd
endif
ifndef PPPD_LIBDIR
PPPD_LIBDIR=	/usr/lib/pppd/$(PPPD_VERSION)
endif

# END CONFIGURABLE SETTINGS

CFLAGS	+= -g -I.. $(CFLAGS.pppd) -I/usr/include/pppd -fPIC
LDFLAGS	+= -shared

all:	ippool.so

ippool.so: ippool.c
	$(CC) -o $@ $(LDFLAGS) $(CFLAGS) -D_linux_=1 ippool.c ../ippool_rpc_client.o ../ippool_rpc_xdr.o

install: ippool.so
	$(INSTALL) -d $(DESTDIR)$(PPPD_LIBDIR)
	$(INSTALL) ippool.so $(DESTDIR)$(PPPD_LIBDIR)

clean:
	-rm -rf *.o *.so
