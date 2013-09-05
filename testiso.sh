#!/bin/sh

/usr/bin/mkisofs -r -V test.iso -cache-inodes -J -l -b isolinux/isolinux.bin -c isolinux/boot.cat -no-emul-boot -boot-load-size 4 -boot-info-table -o test.iso _build_temp.old/livecdbuild/live-cd-target/
