#!/bin/sh

set -e

pomng_add="base ROUTE addrtype IPMARK XOR policy NETLINK POOL mport string"
pomng_force="pool condition random NETLINK TCPLAG dstlimit string"
pomng_exclude="ip_queue_vwmark"

iptables="iptables-1.3.3"
#pomng="patch-o-matic-ng-20050618"
pomng="patch-o-matic-ng-20080316-with-downloads"
#kernel="linux-2.6.12"
kernel="linux-source-2.6.15-2.6.15"
ipset="ipset"

dba=$(dpkg-architecture -qDEB_BUILD_ARCH)

pwd="$(pwd)"
build="${pwd}/debian/build"
doc="${build}/doc"
stamp="${build}/stamp"
patches="patches"
upstream="${pwd}/upstream"
arch_patches="${patches}/${dba}"
iptables_profectio="${build}/${iptables}"
kernel_profectio="${build}/${kernel}"
#kernel_profectio="${pwd}/../../kernelbuild/linux-source-2.6.15-2.6.15/debian/build/build-386"
pomng_profectio="${build}/${pomng}"

unpack() {
  for tarball in "$@"; do
    tarball="${tarball}.tar.bz2"
    dinfo "$tarball"
    bunzip2 -dc "${upstream}/${tarball}" | ( cd "$build"; tar xf - )
  done
}

sgml() {
  for sgmldoc in "$@"; do
    sgmldoc="${sgmldoc}-HOWTO.sgml"
    dinfo "$sgmldoc"
    sgml2html "${upstream}/${sgmldoc}" >/dev/null 2>&1
  done
}

dinfo () {
  echo "${0} - ${*}"
}

test -f "${stamp}/prep" && {
  echo already prepared.
  exit 0
}

# package build paths
dinfo "installing source symlinks."
install -d "$doc" "$stamp"
(cd "$build"; ln -sf "$iptables" iptables_profectio; ln -sf "$kernel" kernel_profectio)

# unpack upstream tarballs
dinfo "preparing upstream source..."
unpack "$kernel"
unpack "$iptables"
unpack "$pomng"
ln -s "${build}/${ipset}" "$iptables_profectio/ipset"

unpack "$ipset"
> ${build}/ipset/Makefile

# patch-o-matic-ng
dinfo "applying patch-o-matic-ng..."

exclude=""
for i in $pomng_exclude; do
  exclude="--exclude $i $exclude"
done

for i in $pomng_add; do
  (cd "$pomng_profectio";
    yes N | ./runme  --batch $exclude --kernel-path $kernel_profectio \
      --iptables-path $iptables_profectio $i)
done

for  i in $pomng_force; do
 d="debian/build/$pomng/$i/linux"
 if test -d $d; then
   cp -a $d/* $kernel_profectio
 fi
done

# do man pages here, after pomng, so local patches can be applied
dinfo "buidling man pages..."
(cd "$iptables_profectio"; make iptables.8 ip6tables.8)

# compile upstream changelog
dinfo "assembling changelog..."
rm -f "${doc}/changelog"
for i in $( (cd ${upstream}; ls CL???-changes*) | sort -r ); do
  dinfo "$i"
  if echo $i | grep -q .txt; then
    cat "${upstream}/${i}" >>  "${doc}/changelog"
  elif echo $i | grep -q .html; then
    html2text -o - "${upstream}/$i" >> "${doc}/changelog"
  fi
done

# process sgml HOWTOS
dinfo "processing sgml documents..."
( cd ${doc}; sgml packet-filtering NAT netfilter-hacking netfilter-extensions )

# local debian patches
dinfo "applying local patches..."
  #fix this mess up or something, please
if test -d "$arch_patches"; then
  patches="$patches/all $arch_patches"
else
  patches="$patches/all"
fi

for patch in $( find $patches -type f -name \*.patch | sort -t / -k 3 ); do
  dinfo "${patch##*/patches/}"
  patch -p1 -s -d "$build" < "$patch"
done

touch "${stamp}/prep"

dinfo "done."
