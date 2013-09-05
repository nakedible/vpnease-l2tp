__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils

from codebay.common import rdf
from codebay.l2tpserver.webui.livecd import livecddb
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import constants
from codebay.l2tpserver import db
from codebay.l2tpserver import interfacehelper

class InstallLicensePage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/installlicense.xhtml'
    pagetitle = u'Install / Recovery \u21d2 Requirements (Step 1 of 4)'
    
    def render_check_earlier_install_run(self, ctx, data):
        if not livecddb.get_livecd_database_root().hasS(ns_ui.installHasBeenStarted):
            return ''
        return ctx
        
    def render_check_no_earlier_install_run(self, ctx, data):
        if livecddb.get_livecd_database_root().hasS(ns_ui.installHasBeenStarted):
            return ''
        return ctx
        
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

        ifaces = interfacehelper.get_interfaces()
        n_ether = 0
        for i in ifaces.get_interface_list():
            if i.is_ethernet_device():
                n_ether += 1

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
        return ''

    @db.transact()
    def form_start_install(self, ctx):
        lbl = 'I have read and accept the License Agreement and the Privacy Policy'
        
        form = formal.Form()
        
        g = formalutils.CollapsibleGroup('startinstall', label='License Agreement and Privacy Policy')
        g.setCollapsed(False)
        g.add(formal.Field('acceptlicense', formal.Boolean(required=True), label=lbl))
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('startinstallation', formal.String(), label='Next'))
        g.add(sg)
        form.add(g)
        form.addAction(self.submitted_start_install, name='startinstallation', label='Next', validate=False)

        form.data['startinstall.acceptlicense'] = False

        return form

    @db.transact()
    def submitted_start_install(self, ctx, form, data):
        print 'submitted_start_install'

        fda = formalutils.FormDataAccessor(form, [], ctx)
        if not fda['startinstall.acceptlicense']:
            fda.add_error('startinstall.acceptlicense', 'Required')
        fda.finalize_validation()

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('installtarget.html'))
        request.finish()
        return ''

    @db.transact()
    def form_reboot_computer(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('reboot', formal.String(), label='Reboot computer'))
        form.add(sg)
        form.addAction(self.submitted_reboot_computer, name='reboot', label='Reboot computer', validate=False)

        return form

    @db.transact()
    def submitted_reboot_computer(self, ctx, form, data):
        print 'submitted_reboot_computer'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('waitreboot.html'))
        request.finish()
        return ''

