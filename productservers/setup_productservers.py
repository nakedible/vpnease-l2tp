#!/usr/bin/env python2.4

from distutils import core

import os
os.chdir('../src/python')

core.setup(name='vpnease-maintenance',
           description='VPNease maintenance servers',
           long_description='''VPNease maintenance servers''',
           version='1.0.0',
           license='Commercial',
           url='http://www.vpnease.com/',
           author='VPNese support',
           author_email='support@vpnease.com',
           packages=['codebay',
                     'codebay.common',
                     'codebay.nevow',
                     'codebay.nevow.formalutils',
                     'codebay.l2tpmanagementprotocol',
                     'codebay.l2tpserver',
                     'codebay.l2tpmanagementserver',
                     'codebay.l2tpmanagementserver.licenses',
                     'codebay.l2tpadmin',
                     'codebay.l2tpproductweb',
                     ],
           scripts=[])
