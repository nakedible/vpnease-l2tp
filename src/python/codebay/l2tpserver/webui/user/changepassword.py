"""Client (non-install) pages."""
__docformat__ = 'epytext en'

from nevow import inevow, loaders, rend, url, stan, tags as T, static

import os
import formal

from codebay.common import rdf
from codebay.common import logger
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui, ns_zipfiles
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import uidatahelpers

_log = logger.get('l2tpserver.webui.user.changepassword')

class ChangePasswordPage(formal.ResourceMixin, commonpage.UserPage):
    template = 'user/changepassword.xhtml'
    pagetitle = 'Change Password'

    @db.transact()
    def render_password_change_allowed(self, ctx, data):
        username = self.get_logged_in_username()
        user_rdf = uihelpers.find_user(username)
        if user_rdf is None:
            return ''
        else:
            return ctx.tag
    
    @db.transact()
    def render_password_change_not_allowed(self, ctx, data):
        username = self.get_logged_in_username()
        user_rdf = uihelpers.find_user(username)
        if user_rdf is None:
            return ctx.tag
        else:
            return ''

    @db.transact()
    def form_changepassword(self, ctx):
        form = formal.Form()
        g = formalutils.CollapsibleGroup('changepassword', label='Change Password')
        g.setCollapsed(False)
        g.add(formal.Field('pw1', formal.String(required=True),
                           formal.widgetFactory(formalutils.HiddenPassword),
                           label='Old password'))
        g.add(formal.Field('pw2', formal.String(required=True),
                           formal.widgetFactory(formalutils.HiddenPassword),
                           label='New password'))
        g.add(formal.Field('pw3', formal.String(required=True),
                           formal.widgetFactory(formalutils.HiddenPassword),
                           label='New password (again)'))
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('changepassword', formal.String(), label='Change password'))
        g.add(sg)
        form.add(g)
        form.addAction(self.submitted, name='changepassword', validate=False)
        return form

    @db.transact()
    def submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx).descend('changepassword')
        if fda.has_key('pw2') and fda.has_key('pw3') and (fda['pw2'] != fda['pw3']):
            fda.add_error('pw2', 'Passwords do not match')
            fda.add_error('pw3', 'Passwords do not match')

        # verify old password
        username = self.get_logged_in_username()
        user_rdf = uihelpers.find_user(username)
        if user_rdf is None:
            # presumably RADIUS user
            fda.add_error('pw1', 'Password change not allowed')
        else:
            if fda.has_key('pw1') and (not uihelpers.check_username_and_password(username, fda['pw1'])):
                fda.add_error('pw1', 'Password incorrect')

        # prevent password change if marker exists; this is useful for demo server
        if os.path.exists(constants.NOPWCHANGE_MARKERFILE):
            _log.info('nopwchange marker exists, not changing password')
            fda.add_error('pw1', 'Password change not allowed')

        # finalize validation
        fda.finalize_validation()

        # XXX: does admin need control here? i.e., prevent changing of password?

        # ok, we're happy; change the password
        _log.info('changing password for user %s' % username)
        uihelpers.change_user_password(username, fda['pw2'])

        # restart radius server with new config; no need to nuke connections here because
        # no users are added or removed.
        try:
            pd = uidatahelpers.CreateProtocolData()
            pd.save_protocol_data(use_current_config=True)
            pd.activate_protocol_data(use_current_config=True)
            pd.restart_freeradius()  # needs protocol config in place
        except:
            _log.exception('cannot restart freeradius, ignoring')

        # redirect
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('passwordchanged.html'))
        request.finish()
        return ''
