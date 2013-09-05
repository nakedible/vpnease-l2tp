__docformat__ = 'epytext en'

import os

import formal
from twisted.internet import reactor
from nevow import inevow

from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils

from codebay.common import rdf
from codebay.common import passwordgen
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui.livecd import livecddb
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import mediahelper
from codebay.l2tpserver import db

from codebay.l2tpserver.webui.livecd.installconfirm import InstallerProcessProtocol

#
#  XXX: we re-read medium information many many times below; need to cache the
#  MediaInfo... perhaps user render 'data' field for this.
#

#
#  XXX: shares a lot with installer
#

class FormatConfirmPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/formatconfirm.xhtml'
    pagetitle = u'Format USB Stick \u21d2 Confirm Formatting (Step 2 of 3)'
    
    def render_device(self, ctx, data):
        return livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
    
    def render_devicehuman(self, ctx, data):
        target = livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
        medium = mediahelper.get_media().get_medium_by_device_name(target)
        return medium.get_human_readable_description()

    def render_sizehuman(self, ctx, data):
        target = livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
        medium = mediahelper.get_media().get_medium_by_device_name(target)
        return medium.get_size_pretty()

    def render_sizebytes(self, ctx, data):
        target = livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
        medium = mediahelper.get_media().get_medium_by_device_name(target)
        return medium.get_size()

    def render_bustype(self, ctx, data):
        target = livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
        medium = mediahelper.get_media().get_medium_by_device_name(target)
        return medium.get_human_readable_bus_type()

    @db.transact()
    def form_confirm_formatting(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('confirm', formal.String(), label='Start formatting'))
        sg.add(formalutils.SubmitField('reselect', formal.String(), label='Back'))
        sg.add(formalutils.SubmitField('cancel', formal.String(), label='Cancel'))
        form.add(sg)
        
        form.addAction(self.submitted_confirm_formatting, name='confirm', label='Start formatting', validate=False)
        form.addAction(self.submitted_reselect, name='reselect', label='Back', validate=False)
        form.addAction(self.submitted_cancel_formatting, name='cancel', label='Cancel', validate=False)

        return form

    @db.transact()
    def submitted_confirm_formatting(self, ctx, form, data):
        debug_install = True

        print 'submitted_confirm_formatting'

        # Fire up the formatter

        # XXX: we should track previous instance and kill it if necessary
        for i in [ constants.INSTALL_STATUS_FILE,
                   constants.INSTALL_STDOUT,
                   constants.INSTALL_STDERR ]:
            if os.path.exists(i):
                os.unlink(i)

        # arguments
        target = livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)
        cmd = constants.CMD_L2TPGW_INSTALL
        args = [ constants.CMD_L2TPGW_INSTALL,
                 'fatformat',                                               # command
                 target,                                                    # target device
                 'vpnease-%s' % passwordgen.generate_password(length=8),    # hostname
                 constants.ADMIN_USER_NAME,                                 # admin user
                 passwordgen.generate_password(length=8),                   # admin password
                 '0' ]                                                      # large install ('1' or '0')
          
        # env
        env = None
        if debug_install:
            env = dict(os.environ)
            env['CODEBAY_LOGGER_DEBUG'] = '1'
            env['CODEBAY_LOGGER_STDOUT'] = '1'

        print 'spawning installer (format), cmd=%s, args=%s, env=%s' % (cmd, args, env)

        # XXX: we should track the process more carefully
        p = reactor.spawnProcess(InstallerProcessProtocol(),
                                 executable=cmd,
                                 args=args,
                                 env=env,
                                 usePTY=1)

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('formatprogress.html'))
        request.finish()
        return ''

    @db.transact()
    def submitted_cancel_formatting(self, ctx, form, data):
        print 'submitted_cancel_formatting'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('welcome.html'))
        request.finish()
        return ''

    @db.transact()
    def submitted_reselect(self, ctx, form, data):
        print 'submitted_cancel_reselect'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('formattarget.html'))
        request.finish()
        return ''
