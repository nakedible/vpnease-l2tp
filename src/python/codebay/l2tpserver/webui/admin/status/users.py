"""Users status page."""
__docformat__ = 'epytext en'

from nevow import tags as T

from codebay.l2tpserver.webui import commonpage

class UserStatusPage(commonpage.AdminPage):
    template = 'admin/status/users.xhtml'
    pagetitle = 'Status / User Connections'

    def render_include_history(self, ctx, data):
        return ''
    def render_dont_include_history(self, ctx, data):
        return ctx.tag
    def render_history_switch_link(self, ctx, data):
        return T.a(href='usershistory.html')['Show history']
    
class UserStatusWithHistoryPage(commonpage.AdminPage):
    template = 'admin/status/users.xhtml'
    pagetitle = 'Status / User Connections'

    def render_include_history(self, ctx, data):
        return ctx.tag
    def render_dont_include_history(self, ctx, data):
        return ''
    def render_history_switch_link(self, ctx, data):
        return T.a(href='users.html')['Hide history']
