"""Main status page."""
__docformat__ = 'epytext en'

from codebay.l2tpserver.webui import commonpage

class StatusMainPage(commonpage.AdminPage):
    template = 'admin/status/main.xhtml'
    pagetitle = 'Status / Overview'
