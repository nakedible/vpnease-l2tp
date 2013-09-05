#!/bin/sh

cat > /tmp/recovery.py <<EOF
#!/usr/bin/python

import os
import sys

print 'VPNease update recovery'
print '-----------------------'

print ''
print '*** Starting update recovery ***'
print ''

opts = '-o APT::Get::AllowUnauthenticated=true -o Aptitude::CmdLine::Ignore-Trust-Violations=yes'

os.system('DEBIAN_FRONTEND="noninteractive" dpkg --configure -a')
os.system('DEBIAN_FRONTEND="noninteractive" apt-get %s update' % opts)
os.system('DEBIAN_FRONTEND="noninteractive" aptitude %s -q -y upgrade' % opts)
os.system('DEBIAN_FRONTEND="noninteractive" aptitude %s -q -y install vpnease' % opts)
os.system('DEBIAN_FRONTEND="noninteractive" dpkg --configure -a')

print ''
print '*** Update recovery complete ***'
print ''
print 'Type "reboot" to restart server.'
EOF

python /tmp/recovery.py
