__docformat__ = 'epytext en'

import os

import formal
from twisted.internet import reactor, protocol
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


class InstallerProcessProtocol(protocol.ProcessProtocol):
    # XXX: now eats stdout and stderr, could something with them
    pass

#
#  XXX: we re-read medium information many many times below; need to cache the
#  MediaInfo... perhaps user render 'data' field for this.
#

class InstallConfirmPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/installconfirm.xhtml'
    pagetitle = u'Install / Recovery \u21d2 Confirm Installation (Step 3 of 4)'

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

    def render_recovery(self, ctx, data):
        root = livecddb.get_livecd_database_root()
        if root.hasS(ns_ui.attemptRecovery) and root.getS(ns_ui.attemptRecovery, rdf.Boolean):
            if root.hasS(ns_ui.previousConfigurationRdfXml):
                ver_str = 'unknown'
                if root.hasS(ns_ui.previousInstalledVersion):
                    ver_str = root.getS(ns_ui.previousInstalledVersion, rdf.String)
                return 'Previous installation found (version %s), attempting recovery of previous configuration' % ver_str
            else:
                return 'No previous installation found, cannot recover previous configuration'
        else:
            return 'Recovery of previous configuration not attempted (overwrite any existing data)'

    def render_installation_model(self, ctx, data):
        root = livecddb.get_livecd_database_root()
        if root.hasS(ns_ui.installLargeDisk) and root.getS(ns_ui.installLargeDisk, rdf.Boolean):
            return 'Install with separate /boot and root partitions'
        else:
            return 'Install with single root partition'
        
    @db.transact()
    def form_confirm_installation(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('confirm', formal.String(), label='Start installation'))
        sg.add(formalutils.SubmitField('reselect', formal.String(), label='Back'))
        sg.add(formalutils.SubmitField('cancel', formal.String(), label='Cancel'))
        form.add(sg)
        
        form.addAction(self.submitted_confirm_installation, name='confirm', label='Start installation', validate=False)
        form.addAction(self.submitted_reselect, name='reselect', label='Back', validate=False)
        form.addAction(self.submitted_cancel_installation, name='cancel', label='Cancel', validate=False)

        return form

    @db.transact()
    def submitted_confirm_installation(self, ctx, form, data):
        debug_install = True

        root = livecddb.get_livecd_database_root()

        print 'submitted_confirm_installation'

        # If a previous install has failed, we cannot allow install to begin.
        # This is because current installer may corrupt host filesystem state
        # in case install fails (see codebay.l2tpserver.installer.install).
        if root.hasS(ns_ui.installHasBeenStarted):
            print 'earlier install run, refusing to install'

            # XXX: separate page?
            request = inevow.IRequest(ctx)
            request.redirect(request.URLPath().sibling('installfailed.html'))
            request.finish()
            return ''

        # If recovery attempted, write recovery rdf/xml to a temp file
        recovery_rdfxml = '/tmp/recovery-data.xml'
        if os.path.exists(recovery_rdfxml):
            os.unlink(recovery_rdfxml)

        if root.hasS(ns_ui.previousConfigurationRdfXml):
            f = None
            try:
                f = open(recovery_rdfxml, 'wb')
                f.write(root.getS(ns_ui.previousConfigurationRdfXml, rdf.String).decode('hex'))
            finally:
                if f is not None:
                    f.close()
                    f = None
        else:
            recovery_rdfxml = None
            
        # Large install
        large_install_param = '0'
        if root.hasS(ns_ui.installLargeDisk) and root.getS(ns_ui.installLargeDisk, rdf.Boolean):
            large_install_param = '1'

        # Fire up the installer
        #
        # The underlying assumption here is that prechecks are strong enough to
        # prevent install failures from occurring - install failures are not recoverable.
        #
        # NB: Because we're running a shell command, we need strict control of what
        # goes into these fields.  They are not likely to be exploits as such, but
        # can cause interesting failures.
        #
        # As such, it would be better to run the installer through Twisted; we could
        # process the stdout inside the UI code and so on.  However, this is enough
        # for now: the Twisted change can be done later if it adds any value to this.
        #
        # XXX: passwordgen is not ideal for hostname 'uid' generation, but works.

        # XXX: we should track previous instance and kill it if necessary
        for i in [ constants.INSTALL_STATUS_FILE,
                   constants.INSTALL_STDOUT,
                   constants.INSTALL_STDERR ]:
            if os.path.exists(i):
                os.unlink(i)

        # arguments
        target = root.getS(ns_ui.targetDevice, rdf.String)
        cmd = constants.CMD_L2TPGW_INSTALL
        args = [ constants.CMD_L2TPGW_INSTALL,
                 'install',                                                 # command
                 target,                                                    # target device
                 'vpnease-%s' % passwordgen.generate_password(length=8),    # hostname
                 constants.ADMIN_USER_NAME,                                 # admin user
                 passwordgen.generate_password(length=8),                   # admin password
                 large_install_param ]                                      # large install ('1' or '0')

        if recovery_rdfxml is not None:
            args.append(recovery_rdfxml)
            
        # env
        env = None
        if debug_install:
            env = dict(os.environ)
            env['CODEBAY_LOGGER_DEBUG'] = '1'
            env['CODEBAY_LOGGER_STDOUT'] = '1'

        print 'spawning installer, cmd=%s, args=%s, env=%s' % (cmd, args, env)

        # XXX: we should track the process more carefully
        p = reactor.spawnProcess(InstallerProcessProtocol(),
                                 executable=cmd,
                                 args=args,
                                 env=env,
                                 usePTY=1)

        # set 'sticky' marker: second install start will be refused
        root.setS(ns_ui.installHasBeenStarted, rdf.Boolean, True)

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('installcopying.html'))
        request.finish()
        return ''

    @db.transact()
    def submitted_cancel_installation(self, ctx, form, data):
        print 'submitted_cancel_installation'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('welcome.html'))
        request.finish()
        return ''

    @db.transact()
    def submitted_reselect(self, ctx, form, data):
        print 'submitted_cancel_reselect'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('installtarget.html'))
        request.finish()
        return ''
