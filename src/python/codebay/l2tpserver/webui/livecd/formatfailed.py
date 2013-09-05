__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver import helpers
from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver.installer import installhelpers

class FormatFailedPage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/formatfailed.xhtml'
    pagetitle = u'Format USB Stick \u21d2 Failed'

