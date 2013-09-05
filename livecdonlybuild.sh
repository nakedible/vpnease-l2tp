#!/bin/bash

set -e

./build.py livecdbuild --ubuntu-image /root/work/ubuntu-6.06.1-desktop-i386.iso

revision=`svnversion .`

echo "Live-CD revision r$revision build ok."
