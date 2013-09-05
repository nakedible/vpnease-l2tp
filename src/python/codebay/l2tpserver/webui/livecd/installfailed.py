__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver.installer import installhelpers

class InstallFailedPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/installfailed.xhtml'
    pagetitle = u'Install / Recovery \u21d2 Failed'

    # XXX: why?
    def macro_content_left(self, ctx):
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

