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
from codebay.l2tpserver import mediahelper
from codebay.l2tpserver.installer import installhelpers

class InstallTargetPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/installtarget.xhtml'
    pagetitle = u'Install / Recovery \u21d2 Select Target (Step 2 of 4)'
    
    def _get_disks(self):
        # XXX: this now gets run multiple times...
        return mediahelper.get_media().get_disk_media_list() # Note: ignore cdrom devices

    def render_check_disks_multiple(self, ctx, data):
        if len(self._get_disks()) > 1:
            return ctx.tag
        return ''

    def render_check_disks_one(self, ctx, data):
        if len(self._get_disks()) == 1:
            return ctx.tag
        return ''

    def render_check_disks_none(self, ctx, data):
        if len(self._get_disks()) == 0:
            return ctx.tag
        return ''

    @db.transact()
    def form_select_target(self, ctx):
        form = formal.Form()

        g = formalutils.CollapsibleGroup('selecttarget', label='Installation Targets')
        g.setCollapsed(False)
        
        targets = []
        for m in self._get_disks():
            errors = []
            if m.get_size() < constants.DISK_SIZE_MINIMUM:
                errors.append('device too small')
            if m.is_write_protected():
                errors.append('write-protected')
            if errors:
                errorstr = ' [' + (', '.join(errors)) + ']'
            else:
                errorstr = ''
                
            devname = m.get_device()
            devstring = '%s %s (%s) %s' % (m.get_size_pretty(), m.get_human_readable_description(), m.get_device(), errorstr)
            targets.append((devname, devstring))

        def _target_cmp(x, y):
            x_dev, x_info = x
            y_dev, y_info = y
            return unicode.__cmp__(unicode(x_dev), unicode(y_dev))
        targets.sort(cmp=_target_cmp)
            
        # XXX: we can't currently disable individual radiobuttons in Formal.
        # We thus leave them enabled, and check for device size below.  This
        # is unfortunate, but better than not showing small devices at all
        
        lbl = 'Target device'
        g.add(formal.Field('target', formal.String(required=True),
                           formal.widgetFactory(formal.RadioChoice, options=targets),
                           label=lbl))
        g.add(formal.Field('recovery', formal.Boolean(required=False), label='Attempt recovery'))
        
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('selecttarget', formal.String(), label='Next'))
        sg.add(formalutils.SubmitField('rescan', formal.String(), label='Rescan'))
        sg.add(formalutils.SubmitField('cancel', formal.String(), label='Cancel'))
        g.add(sg)
        
        form.add(g)
        form.addAction(self.submitted_select_target, name='selecttarget', label='Next', validate=False)
        form.addAction(self.submitted_rescan, name='rescan', label='Rescan', validate=False)
        form.addAction(self.submitted_cancel_installation, name='cancel', label='Cancel', validate=False)

        # set previous selection if exists as default value
        cfg = livecddb.get_livecd_database_root()
        if cfg.hasS(ns_ui.targetDevice):
            form.data['selecttarget.target'] = cfg.getS(ns_ui.targetDevice, rdf.String)
        if cfg.hasS(ns_ui.attemptRecovery):
            form.data['selecttarget.recovery'] = cfg.getS(ns_ui.attemptRecovery, rdf.Boolean)
            
        return form

    @db.transact()
    def form_rescan_targets(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('rescan', formal.String(), label='Rescan targets'))
        form.add(sg)
        form.addAction(self.submitted_rescan, name='rescan', label='Rescan targets', validate=False)

        return form

    @db.transact()
    def submitted_select_target(self, ctx, form, data):
        print 'submitted_select_target'

        # XXX: target selection error messages as constants?
        fda = formalutils.FormDataAccessor(form, [], ctx)
        target = None
        recovery = False
        large_install = False
        try:
            target = form.data['selecttarget.target']
            print 'selected target: %s' % target

            medium = mediahelper.get_media().get_medium_by_device_name(target)
            if medium.get_size() < constants.DISK_SIZE_MINIMUM:
                fda.add_error('selecttarget.target', 'Minimum target medium size is 2 GB')
            if medium.is_write_protected():
                fda.add_error('selecttarget.target', 'Target medium is write-protected')

            if form.data.has_key('selecttarget.recovery'):
                recovery = form.data['selecttarget.recovery']

            if medium.get_size() >= constants.DISK_SIZE_MINIMUM_FOR_LARGE_INSTALL:
                large_install = True
        except:
            fda.add_error('selecttarget.target', 'Target medium cannot be selected')
        fda.finalize_validation()

        root = livecddb.get_livecd_database_root()
        root.setS(ns_ui.targetDevice, rdf.String, target)
        root.setS(ns_ui.attemptRecovery, rdf.Boolean, recovery)
        root.removeNodes(ns_ui.previousConfigurationRdfXml)
        root.removeNodes(ns_ui.previousInstalledVersion)
        
        # Recovery check here
        if recovery:
            print 'attempting recovery from %s' % target

            try:
                prev_cfg, prev_version = installhelpers.recover_existing_configuration(target)
                if prev_cfg is not None:
                    root.setS(ns_ui.previousConfigurationRdfXml, rdf.String, prev_cfg.encode('hex'))

                    if prev_version is not None:
                        root.setS(ns_ui.previousInstalledVersion, rdf.String, prev_version)
                    else:
                        pass
                else:
                    raise Exception('did not find recovery data')
            except:
                print 'recovery failed'

        # Select installation model based on target size
        root.setS(ns_ui.installLargeDisk, rdf.Boolean, large_install)

        print livecddb.dump_livecd_database()
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('installconfirm.html'))
        return ''

    @db.transact()
    def submitted_cancel_installation(self, ctx, form, data):
        print 'submitted_cancel_installation'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('welcome.html'))
        return ''

    @db.transact()
    def submitted_rescan(self, ctx, form, data):
        # clear previous selection if exists
        cfg = livecddb.get_livecd_database_root()
        if cfg.hasS(ns_ui.targetDevice):
            cfg.removeNodes(ns_ui.targetDevice)

