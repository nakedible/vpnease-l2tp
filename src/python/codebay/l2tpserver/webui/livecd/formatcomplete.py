__docformat__ = 'epytext en'

import formal
from nevow import inevow, loaders, rend, url, tags as T

from codebay.l2tpserver import helpers
from codebay.l2tpserver.webui import commonpage
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver.installer import installhelpers

class FormatCompletePage(formal.ResourceMixin, commonpage.LiveCdPage):
    template = 'livecd/formatcomplete.xhtml'
    pagetitle = u'Format USB Stick \u21d2 Completed'
