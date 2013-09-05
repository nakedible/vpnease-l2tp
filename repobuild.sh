#!/bin/bash

set -e

builds=" \
l2tpgw"

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

echo "New build r$revision ready and uploaded (no live-cd image created)"

