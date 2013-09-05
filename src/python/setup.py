#!/usr/bin/env python2.4

from distutils import core

core.setup(name='l2tpgw',
           description='L2TP/IPsec VPN Gateway',
           long_description='''L2TP/IPsec VPN Gateway''',
           version='1.0.0',
           license='Commercial',
           url='http://www.vpnease.com/',
           author='VPNease support',
           author_email='support@vpnease.com',
           packages=['codebay',
                     'codebay.common',
                     'codebay.l2tpmanagementprotocol',
                     'codebay.l2tpserver',
                     'codebay.l2tpserver.config',
                     'codebay.l2tpserver.installer',
                     'codebay.l2tpserver.update',
                     'codebay.l2tpserver.webui',
                     'codebay.l2tpserver.webui.livecd',
                     'codebay.l2tpserver.webui.admin',
                     'codebay.l2tpserver.webui.admin.config',
                     'codebay.l2tpserver.webui.admin.management',
                     'codebay.l2tpserver.webui.admin.status',
                     'codebay.l2tpserver.webui.admin.users',
                     'codebay.l2tpserver.webui.admin.misc',
                     'codebay.l2tpserver.webui.user',
                     'codebay.l2tpserver.webui.user.installation',
                     'codebay.nevow',
                     'codebay.nevow.formalutils'],
           scripts=[])

