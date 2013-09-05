"""Legal pages."""
__docformat__ = 'epytext en'

from codebay.l2tpserver.webui import commonpage

class LegalNoticePage(commonpage.PlainPage):
    template = 'legal/legalnotice.xhtml'
    pagetitle = u'Codebay Oy - VPNease\u00ae LEGAL NOTICE'
