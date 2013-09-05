"""
Page that redirects forced web forwarded connections to appropriate URIs.
"""
__docformat__ = 'epytext en'

from nevow import inevow, rend, url

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.common import randutil
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.config import openl2tp
from codebay.l2tpserver.rdfconfig import ns, ns_ui

_log = logger.get('l2tpserver.webui.forwardingpage')

class ForwardingPage(rend.Page):
    """Page used on non-standard ports to forward web requests to actual web UI.

    The redirected URI will contain context information as query parameters for
    actual processing in WebForcedRedirectionPage (below).  That page will also
    redirect the client, creating a two-level redirect.  This should not be a
    problem for browsers (yet).
    """
    
    @db.transact()
    def renderHTTP(self, ctx):
        """Determine appropriate redirection URI and redirect.

        Special care must be taken to avoid caching of any content that is
        served here; when the user reissues the same URI to his browser,
        the page should work unless a new forwarding happens.
        """

        try:
            request = inevow.IRequest(ctx)

            host_hdr = request.getHeader('Host')        # may be None
            use_ssl = request.isSecure()
            our_ppp_ip = openl2tp.get_server_ppp_address()  # may except in several cases
            our_ip = str(request.getHost().host)
            our_port = int(request.getHost().port)
            peer_ip = str(request.getClientIP())        # XXX: validate?

            # XXX: may need later, but currently unused
            peer_port = None
            
            # XXX: we should also test if runner is active; not done now, as it is not critical
            # (our_ppp_ip may be invalid but we don't mind)

            # construct a base uri, and append query parameters afterwards
            if use_ssl:
                tmp = 'https://'
            else:
                tmp = 'http://'
            random_uuid = randutil.random_uuid()  # used to make every forwarding URI unique; prevents caching
            tmp += '%s/%s/%s' % (our_ppp_ip.toString(), 'web-forced-redirection', random_uuid)
            redir = url.URL.fromString(tmp)

            # figure out various parameters for redirect
            original_uri = str(request.URLPath())

            client_ppp_address = peer_ip

            if not use_ssl and our_port == constants.WEBUI_FORWARD_PORT_UIFORCED_HTTP:
                forwarding_reason = 'webui-forced'
            elif not use_ssl and our_port == constants.WEBUI_FORWARD_PORT_LICENSE_HTTP:
                forwarding_reason = 'license'
            elif not use_ssl and our_port == constants.WEBUI_FORWARD_PORT_OLDPSK_HTTP:
                forwarding_reason = 'old-psk'
            elif use_ssl and our_port == constants.WEBUI_FORWARD_PORT_UIFORCED_HTTPS:
                forwarding_reason = 'webui-forced'
            elif use_ssl and our_port == constants.WEBUI_FORWARD_PORT_LICENSE_HTTPS:
                forwarding_reason = 'license'
            elif use_ssl and our_port == constants.WEBUI_FORWARD_PORT_OLDPSK_HTTPS:
                forwarding_reason = 'old-psk'
            else:
                raise Exception('unknown local port for forwarding: %s, cannot determine reason' % our_port)

            try:
                ppp_dev = helpers.find_ppp_device_status(address=datatypes.IPv4Address.fromString(peer_ip), username=None)
                client_username = ppp_dev.getS(ns.username, rdf.String)
            except:
                client_username = ''  # XXX: web UI should default to something useful, empty is good here

            try:
                ppp_user = helpers.find_ppp_user(client_username)
                client_user_node = str(ppp_user.getUri())
            except:
                client_user_node = '' # XXX: web UI should do something useful with this
            
            # add resulting args
            redir = redir.add('original_uri', original_uri)
            redir = redir.add('client_username', client_username)
            redir = redir.add('client_ppp_address', client_ppp_address)
            redir = redir.add('client_user_node', client_user_node)
            redir = redir.add('forwarding_reason', forwarding_reason)
            
            # logging
            _log.info('redirecting incoming request (%s:%s -> %s:%s) to uri %s' % (peer_ip, peer_port, our_ip, our_port, str(redir)))
            
            # return a redirect
            request.redirect(redir)
            request.finish()
            return ''
        except:
            _log.exception('cannot determine forwarding uri')
            raise
        

class WebForcedRedirectionPage(commonpage.PlainPage):
    template = 'web-forced-redirection.xhtml'
    pagetitle = 'VPN Access Restricted'
    
    REASON_CHANGEPW = 'REASON_CHANGEPW'
    REASON_LICENSE = 'REASON_LICENSE'
    REASON_OLDPSK = 'REASON_OLDPSK'
    REASON_UNKNOWN = 'REASON_UNKNOWN'

    def locateChild(self, ctx, segments):
        # all children are us
        return self, []
    
    # Request args:
    #   - original_uri
    #   - client_username
    #   - client_ppp_address
    #   - client_user_node
    #   - forwarding_reason

    def render_uri(self, ctx, data):
        request = inevow.IRequest(ctx)
        return str(request.URLPath())

    def _determine_restriction_type(self, ctx, data):
        request = inevow.IRequest(ctx)
        url = request.URLPath()
        reason = request.args['forwarding_reason'][0]
        if reason == 'webui-forced':
            return self.REASON_CHANGEPW
        elif reason == 'license':
            return self.REASON_LICENSE
        elif reason == 'old-psk':
            return self.REASON_OLDPSK
        else:
            return self.REASON_UNKNOWN
            
    def render_restricted_changepw(self, ctx, data):
        if self._determine_restriction_type(ctx, data) == self.REASON_CHANGEPW:
            return ctx.tag
        else:
            return ''

    def render_restricted_license(self, ctx, data):
        if self._determine_restriction_type(ctx, data) == self.REASON_LICENSE:
            return ctx.tag
        else:
            return ''

    def render_restricted_oldpsk(self, ctx, data):
        if self._determine_restriction_type(ctx, data) == self.REASON_OLDPSK:
            return ctx.tag
        else:
            return ''

    def render_restricted_unknown(self, ctx, data):
        if self._determine_restriction_type(ctx, data) == self.REASON_UNKNOWN:
            return ctx.tag
        else:
            return ''
