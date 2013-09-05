__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils

from codebay.common import rdf
from codebay.l2tpserver.webui.livecd import livecddb
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import constants
from codebay.l2tpserver import interfacehelper

class WelcomePage(commonpage.LiveCdPage):
    template = 'livecd/welcome.xhtml'
    pagetitle = u'Welcome to % s Live CD!' % constants.PRODUCT_NAME
    
    def _check_prereqs(self):
        is_livecd = True
        try:
            open(constants.LIVECD_MARKER_FILE, 'rb').close()
        except:
            is_livecd = False

        is_lowmem = True
        try:
            open(constants.LOWMEM_MARKER_FILE, 'rb').close()
        except:
            is_lowmem = False

        n_ether = 0
        try:
            ifaces = interfacehelper.get_interfaces()
            for i in ifaces.get_interface_list():
                if i.is_ethernet_device():
                    n_ether += 1
        except:
            pass

        print 'livecd prerequisites: is_livecd=%s, is_lowmem=%s, n_ether=%s' % (is_livecd, is_lowmem, n_ether)

        if (not is_livecd) or (is_lowmem) or (n_ether < 1):
            return False
        return True

    def render_livecd_test_prereqs_ok(self, ctx, data):
        if self._check_prereqs():
            return ctx.tag
        return ''

    def render_livecd_test_prereqs_not_ok(self, ctx, data):
        if not self._check_prereqs():
            return ctx.tag
        return ''

    def render_reset_state(self, ctx, data):
        # reset selected device for installer/formatter
        # don't nuke whole database, because we want to remember install failed -case
        root = livecddb.get_livecd_database_root()
        root.removeNodes(ns_ui.targetDevice)
        root.removeNodes(ns_ui.attemptRecovery)
        root.removeNodes(ns_ui.previousConfigurationRdfXml)
        root.removeNodes(ns_ui.previousInstalledVersion)
        root.removeNodes(ns_ui.installLargeDisk)
        return ''

