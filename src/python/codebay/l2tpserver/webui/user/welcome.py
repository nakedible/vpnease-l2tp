"""Client (non-install) pages."""
__docformat__ = 'epytext en'

from nevow import inevow, loaders, rend, url

import formal

from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

class ClientStartPage(formal.ResourceMixin, commonpage.UserPage, uihelpers.UserAgentHelpers, uihelpers.AutoconfigureHelpers):
    template = 'user/welcome.xhtml'
    pagetitle = 'Welcome!'

    def _is_autoconfigure_ok(self, ctx):
        request = inevow.IRequest(ctx)
        useragent = request.getHeader('User-Agent')
        t = self.detect_platform_from_user_agent(useragent)

        if t.has_key('platform') and t['platform'] is not None and \
           t.has_key('architecture') and t['architecture'] is not None:
            if t['architecture'] in ['x86', 'x64']:
                return t['platform']
        return None
    
    def render_autoconfigure_ok_winxp(self, ctx, data):
        if self._is_autoconfigure_ok(ctx) in ['winxp']:
            return ctx.tag
        else:
            return ''
        
    def render_autoconfigure_ok_vista(self, ctx, data):
        if self._is_autoconfigure_ok(ctx) in ['vista']:
            return ctx.tag
        else:
            return ''
        
    def render_autoconfigure_not_ok(self, ctx, data):
        if not self._is_autoconfigure_ok(ctx) in ['winxp', 'vista']:
            return ctx.tag
        else:
            return ''

    def render_multiple_connections_ok(self, ctx, data):
        username = self.get_logged_in_username()
        if (uihelpers.find_user(username) is not None) and (uihelpers.get_user_fixed_ip(username) is None):
            return ctx.tag
        else:
            return ''

    def render_multiple_connections_not_ok(self, ctx, data):
        username = self.get_logged_in_username()
        if (uihelpers.find_user(username) is not None) and (uihelpers.get_user_fixed_ip(username) is not None):
            return ctx.tag
        else:
            return ''

    def render_multiple_connections_not_known(self, ctx, data):
        username = self.get_logged_in_username()
        if uihelpers.find_user(username) is None:
            return ctx.tag
        else:
            return ''

    def render_user_fixed_ip(self, ctx, data):
        try:
            return uihelpers.get_user_fixed_ip(self.get_logged_in_username())
        except:
            return ''
