"""Site-to-sites status page."""
__docformat__ = 'epytext en'

from nevow import tags as T

from codebay.l2tpserver.webui import commonpage

class SiteToSiteStatusPage(commonpage.AdminPage):
    template = 'admin/status/sitetosites.xhtml'
    pagetitle = 'Status / Site-to-Site Connections'

    def render_include_history(self, ctx, data):
        return ''
    def render_dont_include_history(self, ctx, data):
        return ctx.tag
    def render_history_switch_link(self, ctx, data):
        return T.a(href='sitetositeshistory.html')['Show history']

class SiteToSiteStatusWithHistoryPage(commonpage.AdminPage):
    template = 'admin/status/sitetosites.xhtml'
    pagetitle = 'Status / Site-to-Site Connections'

    def render_include_history(self, ctx, data):
        return ctx.tag
    def render_dont_include_history(self, ctx, data):
        return ''
    def render_history_switch_link(self, ctx, data):
        return T.a(href='sitetosites.html')['Hide history']
