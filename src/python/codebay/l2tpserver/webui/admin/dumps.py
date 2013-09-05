"""Various debug use web pages.

Currently RDF dumps in a readable format.
"""
__docformat__ = 'epytext en'

import os

from codebay.common import rdf
from codebay.common import logger
from codebay.common import datatypes
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import db
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfdumper
from codebay.l2tpserver import runcommand

run_command = runcommand.run_command

_log = logger.get('l2tpserver.webui.admin.dumps')

class DumpConfigPage(commonpage.AdminPage):
    template = 'admin/dumpconfig.xhtml'
    pagetitle = 'L2TP/IPsec Configuration Dump'
    
    def render_dump(self, ctx, data):
        rd = rdfdumper.RdfDumper()
        return rd.dump_resource(db.get_db().getRoot().getS(ns.l2tpDeviceConfig))

class DumpStatusPage(commonpage.AdminPage):
    template = 'admin/dumpstatus.xhtml'
    pagetitle = 'L2TP/IPsec Status Dump'
        
    def render_dump(self, ctx, data):
        rd = rdfdumper.RdfDumper()
        return rd.dump_resource(db.get_db().getRoot().getS(ns.l2tpDeviceStatus))

class DumpUiConfigPage(commonpage.AdminPage):
    template = 'admin/dumpuiconfig.xhtml'
    pagetitle = 'Web UI Configuration Dump'
        
    def render_dump(self, ctx, data):
        rd = rdfdumper.RdfDumper()
        return rd.dump_resource(db.get_db().getRoot().getS(ns_ui.uiConfig))

class DumpAllPage(commonpage.AdminPage):
    template = 'admin/dumpall.xhtml'
    pagetitle = 'Global Dump'
        
    def render_dump(self, ctx, data):
        rd = rdfdumper.RdfDumper()
        return rd.dump_resource(db.get_db().getRoot())

class DumpSnmpPage(commonpage.AdminPage):
    template = 'admin/dumpsnmp.xhtml'
    pagetitle = 'SNMP Dump'
        
    def render_dump(self, ctx, data):
        myenv = dict(os.environ)
        myenv['MIBS'] = '+VPNEASE-MIB'

        community = None
        try:
            community = helpers.get_ui_config().getS(ns_ui.snmpCommunity, rdf.String)
        except:
            _log.exception('cannot get snmp communit string, defaulting to public')
            community = 'public'

        rc, stdout, stderr = run_command([constants.CMD_SNMPWALK, '-v', '2c', '-c', community, '127.0.0.1', 'vpneaseMIB'], retval=runcommand.FAIL, env=myenv)
        return stdout


class DumpSyslogPage(commonpage.AdminPage):
    template = 'admin/dumpsyslog.xhtml'
    pagetitle = 'Syslog Dump'

    def render_dump(self, ctx, data):
        f = None
        contents = ''
        try:
            f = open(constants.SYSLOG_LOGFILE, 'rb')
            contents = f.read()
        finally:
            if f is not None:
                f.close()
                f = None
        return contents
    
