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

.PHONY:			all clean distclean install subdirs-all

all:			

clean:

distclean:		clean

TAGS:
			@for d in $(SUBDIRS); do $(MAKE) -C $$d $(MFLAGS) $@; done
			etags -t $(wildcard *.c) $(wildcard *.h)

install:		all
			@for d in $(SUBDIRS); do $(MAKE) -C $$d $(MFLAGS) $@; if [ $$? -ne 0 ]; then exit 1; fi; done

BANNER=			@echo "----------------------------------------------------------------------------"
TCLSH=			tclsh all.tcl -preservecore 3 -verbose bps -tmpdir ./results -outfile $@.result

.PHONY:			test-setup test-postprocess test-ippool

test:			test-setup test-ippool test-postprocess

test-setup:
			@if [ -d ./results ]; then rm -fr ./results; fi
			@mkdir ./results

test-ippool:	
			$(BANNER)
			@$(TCLSH) -constraints "ipPool"

test-postprocess:	
			$(BANNER)
			@(failed=`grep FAILED results/*.result | wc -l`; \
			let failed2=failed/2 ;\
			passed=`grep PASSED results/*.result | wc -l`; \
			echo "TEST SUMMARY: $$passed tests PASSED, $$failed2 tests FAILED" ;\
			exit $$failed2)

