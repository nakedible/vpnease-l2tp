"""
Login pages.
"""
__docformat__ = 'epytext en'

from codebay.common import rdf
from codebay.common import logger

from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import doclibrary
from codebay.l2tpserver.webui import renderers

from nevow import inevow, guard

_log = logger.get('l2tpserver.webui.loginpages')

_pagedir = constants.WEBUI_PAGES_DIR

doclib = doclibrary.DocLibrary(_pagedir)

LOGIN_FAILURE_TEXT = 'Invalid username or password'

saferender = uihelpers.saferender

# --------------------------------------------------------------------------

class AdminLogin(commonpage.CommonPage, renderers.CommonRenderers):
    addSlash = True
    docFactory = doclib.getDocument('admin/login.xhtml')

    def render_page_title(self, ctx, data):
        return 'Administrator Login'

    def macro_login_action(self, ctx):
        # suffix tells where to go after login, but EXCLUDES /admin part!
        return guard.LOGIN_AVATAR + '/status/main.html'  # XXX: constant?

    def render_login_error(self, ctx, data):
        request = inevow.IRequest(ctx)
        if request.args.has_key('login-failure'):
            # XXX: the text in request.args is ugly
            #t = request.args['login-failure']
            t = LOGIN_FAILURE_TEXT
            return t
        else:
            return ''

# --------------------------------------------------------------------------

class LocalAdminLogin(commonpage.CommonPage, renderers.CommonRenderers):
    addSlash = False
    docFactory = doclib.getDocument('admin/locallogin.xhtml')

    def render_page_title(self, ctx, data):
        return 'Local Administrator Login'

    def render_login_action(self, ctx, data):
        # XXX: this causes a session to be created automatically, because
        # local access from anonymous mind is allowed

        ui_root = helpers.get_ui_config()

        next = '/admin/status/main.html'  # XXX: constant?
        if ui_root.hasS(ns_ui.initialConfigSaved) and (not ui_root.getS(ns_ui.initialConfigSaved, rdf.Boolean)):
            next = '/admin/misc/initialconfig.html'
        elif not uihelpers.check_network_interface_configuration():
            next = '/admin/misc/interfaceerror.html'
        return next
    
    # XXX: pretty useless: login really cannot fail for local admin
    def render_login_error(self, ctx, data):
        request = inevow.IRequest(ctx)
        if request.args.has_key('login-failure'):
            # XXX: the text in request.args is ugly
            #t = request.args['login-failure']
            t = LOGIN_FAILURE_TEXT
            return t
        else:
            return ''

    def render_welcome_page(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.welcomePageShown) and ui_root.getS(ns_ui.welcomePageShown, rdf.Boolean):
            return ''
        else:
            return ctx.tag

    def render_normal_page(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.welcomePageShown) and ui_root.getS(ns_ui.welcomePageShown, rdf.Boolean):
            return ctx.tag
        else:
            return ''

    def render_welcome_rendered(self, ctx, data):
        ui_root = helpers.get_ui_config()
        ui_root.setS(ns_ui.welcomePageShown, rdf.Boolean, True)
        return ''

# --------------------------------------------------------------------------

class UserLogin(commonpage.CommonPage, renderers.CommonRenderers):
    addSlash = True
    docFactory = doclib.getDocument('user/login.xhtml')

    def render_page_title(self, ctx, data):
        return 'User Login'
    
    def macro_login_action(self, ctx):
        # suffix tells where to go after login, but EXCLUDES /user part!
        return guard.LOGIN_AVATAR + '/welcome.html'  # XXX: constant?

    def render_login_error(self, ctx, data):
        request = inevow.IRequest(ctx)
        if request.args.has_key('login-failure'):
            # XXX: the text in request.args is ugly
            #t = request.args['login-failure']
            t = LOGIN_FAILURE_TEXT
            return t
        else:
            return ''

    @saferender(default='')
    def render_adminlogin_enabled(self, ctx, data):
        if uihelpers.check_request_local_address_against_config(inevow.IRequest(ctx)):
            return ctx.tag
        else:
            return ''

    @saferender(default='')
    def render_adminlogin_disabled(self, ctx, data):
        if uihelpers.check_request_local_address_against_config(inevow.IRequest(ctx)):
            return ''
        else:
            return ctx.tag

# --------------------------------------------------------------------------

class AccessProhibited(commonpage.PlainPage):
    addSlash = True
    template = 'prohibited.xhtml'
    pagetitle = 'Access Denied'
