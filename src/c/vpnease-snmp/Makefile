CC=gcc

CFLAGS=-I. `net-snmp-config --cflags`

# shared library flags (assumes gcc)
DLFLAGS=-fPIC -shared

TARGETS=vpneaseMIB.so

all: $(TARGETS)

clean:
	rm $(TARGETS)

make-template-code:
	MIBDIRS=/usr/share/snmp/mibs/:. MIBS="+VPNEASE-MIB" mib2c -c mib2c.scalar.conf vpneaseMIB

start-test-snmpd:
	sudo snmpd -d -f -Lo -DALL | tee /tmp/snmpd-log.txt

walk-test-snmpd:
	MIBDIRS=/usr/share/snmp/mibs:/tmp MIBS=+VPNEASE-MIB snmpwalk 127.0.0.1 -c public -v 2c vpneaseMIB

vpneaseMIB.so: vpneaseMIB.c Makefile
	$(CC) $(CFLAGS) $(DLFLAGS) -c -o vpneaseMIB.o vpneaseMIB.c
	$(CC) $(CFLAGS) $(DLFLAGS) -o vpneaseMIB.so vpneaseMIB.o

tester: tester.c vpneaseMIB.c Makefile
	$(CC) $(CFLAGS) -DWITHOUT_NETSNMP_INTERFACE -DTESTER_DEBUG -o tester tester.c vpneaseMIB.c
