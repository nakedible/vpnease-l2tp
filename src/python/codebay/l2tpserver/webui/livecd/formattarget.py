__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils

from codebay.common import rdf
from codebay.l2tpserver.webui.livecd import livecddb
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import mediahelper
from codebay.l2tpserver import db

class FormatTargetPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/formattarget.xhtml'
    pagetitle = u'Format USB Stick \u21d2 Select Target (Step 1 of 3)'

    def _get_disks(self):
        # XXX: this now gets run multiple times...
        return mediahelper.get_media().get_disk_media_list()

    def render_check_disks_one_or_multiple(self, ctx, data):
        if len(self._get_disks()) > 0:
            return ctx.tag
        return ''

    def render_check_disks_none(self, ctx, data):
        if len(self._get_disks()) == 0:
            return ctx.tag
        return ''

    @db.transact()
    def form_select_target(self, ctx):
        form = formal.Form()

        g = formalutils.CollapsibleGroup('selecttarget', label='Select Target Device')
        g.setCollapsed(False)
        
        targets = []
        for m in self._get_disks():
            errors = []
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
            
        lbl = 'Target device'
        g.add(formal.Field('target', formal.String(required=True),
                           formal.widgetFactory(formal.RadioChoice, options=targets),
                           label=lbl))
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('selecttarget', formal.String(), label='Next'))
        sg.add(formalutils.SubmitField('rescan', formal.String(), label='Rescan'))
        sg.add(formalutils.SubmitField('cancel', formal.String(), label='Cancel'))
        g.add(sg)
        
        form.add(g)
        form.addAction(self.submitted_select_target, name='selecttarget', label='Continue', validate=False)
        form.addAction(self.submitted_rescan, name='rescan', label='Rescan targets', validate=False)
        form.addAction(self.submitted_cancel_formatting, name='cancel', label='Cancel formatting', validate=False)

        # set previous selection if exists as default value
        cfg = livecddb.get_livecd_database_root()
        if cfg.hasS(ns_ui.targetDevice):
            form.data['selecttarget.target'] = cfg.getS(ns_ui.targetDevice, rdf.String)

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

        fda = formalutils.FormDataAccessor(form, [], ctx)
        try:
            target = form.data['selecttarget.target']
            print 'selected target: %s' % target

            medium = mediahelper.get_media().get_medium_by_device_name(target)
            if medium.is_write_protected():
                fda.add_error('selecttarget.target', 'Target medium is write-protected')
        except:
            fda.add_error('selecttarget.target', 'Target medium cannot be selected')
        fda.finalize_validation()

        livecddb.get_livecd_database_root().setS(ns_ui.targetDevice, rdf.String, target)
        print livecddb.dump_livecd_database()

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('formatconfirm.html'))
        return ''

    @db.transact()
    def submitted_cancel_formatting(self, ctx, form, data):
        print 'submitted_cancel_formatting'

        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('welcome.html'))
        return ''

    @db.transact()
    def submitted_rescan(self, ctx, form, data):
        # clear previous selection if exists
        cfg = livecddb.get_livecd_database_root()
        if cfg.hasS(ns_ui.targetDevice):
            cfg.removeNodes(ns_ui.targetDevice)
