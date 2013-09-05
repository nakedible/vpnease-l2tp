#!/bin/bash

set -e

builds=" \
basefiles \
firefox \
freeradius \
radiusclient \
radiusclientng \
sqlalchemy \
pythonapsw \
matplotlib \
l2tpgw \
matplotlib \
sqlalchemy \
usplash \
casper \
conntrack \
iptables \
ezipupdate \
formal \
ippool \
kernel \
libnetfilterconntrack \
libnfnetlink \
monit \
nevow \
openl2tp \
openswan \
ppp \
rrd \
syslog \
snmpd \
twisted"

if test -e ./_build_temp; then
    echo "Please move old _build_temp somewhere safe or delete it..."
    exit 0
fi

for i in $builds; do
   ./build.py ${i}build --help || exit 1
done

for i in $builds; do
    echo "Building now: ${i}build.."
    ./build.py ${i}build || exit 1
    echo "done."
done

revision=`svnversion .`

./build.py vpneasebuild --module-search-path ./_build_temp || exit 1

scp -r _build_temp/vpneasebuild/vpnease-repository_r$revision root@ode:/var/local/data/repositories/vpnease/ || exit 1
ssh root@ode \(cd /var/local/data/repositories/vpnease\;rm 1.2\;ln -s vpnease-repository_r$revision 1.2\) || exit 1

./build.py livecdbuild --ubuntu-image /root/work/ubuntu-6.06.1-desktop-i386.iso
