KERNEL_SRCDIR ?= /lib/modules/`uname -r`/build

ALL_TESTS= test3 test4 test5 test6 test7 test8 test9 test10

CFLAGS=-Wall -O2 -I. -I../include -I$(KERNEL_SRCDIR)/include -g \
	-DCONFIG_PPPOE_MODULE -DCONFIG_PPPOL2TP_MODULE -DCONFIG_PPPOL2TP_DEBUG
CC=gcc

all:	$(ALL_TESTS)

test3: test3.o testlib.o
test4: test4.o testlib.o 
test5: test5.o testlib.o 
test6: test6.o testlib.o 
test7: test7.o testlib.o 
test8: test8.o testlib.o
test9: test9.o testlib.o
test10: test10.o testlib.o

test3.o: testlib.h
test4.o: testlib.h
test5.o: testlib.h
test6.o: testlib.h
test7.o: testlib.h
test8.o: testlib.h
test9.o: testlib.h
test10.o: testlib.h

clean:
	$(RM) $(ALL_TESTS) $(ALL_TESTS:%=%.o) testlib.o

distclean:		clean
			-$(RM) TAGS

install:

TAGS:
			etags -t $(wildcard *.c) $(wildcard *.h)

BANNER=			@echo "----------------------------------------------------------------------------"
TCLSH=			tclsh all.tcl -preservecore 3 -verbose bps -tmpdir ./results -outfile $@.result

.PHONY:			test-setup test-postprocess test-kernel-module-1 test-kernel-module-2

test:			test-setup test-kernel-module test-postprocess

test-setup:
			@if [ -d ./results ]; then rm -fr ./results; fi
			@mkdir ./results

test-kernel-module:	
			$(BANNER)
			@$(TCLSH) -constraints kernelModule -limitcontraints 1

test-postprocess:	
			$(BANNER)
			@(failed=`grep FAILED results/*.result | wc -l`; \
			let failed2=failed/2 ;\
			passed=`grep PASSED results/*.result | wc -l`; \
			echo "TEST SUMMARY: $$passed tests PASSED, $$failed2 tests FAILED" ;\
			exit $$failed2)
