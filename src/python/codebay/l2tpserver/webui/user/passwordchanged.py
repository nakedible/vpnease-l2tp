"""Client (non-install) pages."""
__docformat__ = 'epytext en'

from nevow import inevow, loaders, rend, url, stan, tags as T, static

from codebay.l2tpserver.webui import commonpage

class PasswordChangedPage(commonpage.UserPage):
    template = 'user/passwordchanged.xhtml'
    pagetitle = 'Password Changed'
