"""Front page.

Provides appropriate web forwarding responses when user or admin
loads the plain URI of the server (e.g. http://someserver/).
"""
__docformat__ = 'epytext en'

import os

from nevow import inevow, loaders, rend, url

from codebay.common import rdf

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver.webui import commonpage

class FrontPage(commonpage.CommonPage):
    addSlash = True

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)

        # extract parameters
        is_local = (request.getClientIP() == '127.0.0.1')
        is_secure = request.isSecure()
        u = url.URL.fromContext(ctx)

        # start building redirection URI
        redirect_uri = u
        u = u.clear()
        
        # http only allowed for local connections
        if (not is_secure) and (not is_local):
            # Note: although commonpage handles http to https redirections,
            # we override renderHTTP from commonpage and need to deal with
            # the same stuff here.
            redirect_uri = redirect_uri.secure(secure=True, port=constants.WEBUI_PORT_HTTPS_INT)

        # XXX: here we assume that if we are running on live cd,
        # testing has already started so behavior should match
        # installed system.
        
        if is_local:
            # Local connection
            redirect_uri = redirect_uri.click('locallogin.html')
        else:
            # Remote connection -> user login
            redirect_uri = redirect_uri.child('user')

        if u == redirect_uri:
            raise Exception('uri unchanged, avoid redirection loop')

        request.redirect(redirect_uri)
        request.finish()
        return ''

class AdminFrontPage(commonpage.PlainPage):
    template = 'admin/frontpage.xhtml'
    pagetitle = 'Access Denied'
    
class UserFrontPage(commonpage.PlainPage):
    template = 'user/frontpage.xhtml'
    pagetitle = 'Access Denied'

class LivecdFrontPage(commonpage.PlainPage):
    addSlash = True
    pagetitle = 'Access Denied'

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)

        # extract parameters
        is_local = (request.getClientIP() == '127.0.0.1')
        u = url.URL.fromContext(ctx)

        # only local connections allowed
        if not is_local:
            raise Exception('access denied')
        
        # build redirection URI
        redirect_uri = u
        redirect_uri = redirect_uri.child('livecd').child('welcome.html')
                
        # sanity
        if u == redirect_uri:
            raise Exception('uri unchanged, avoid redirection loop')

        # finally, redirect
        request.redirect(redirect_uri)
        request.finish()
        return ''
