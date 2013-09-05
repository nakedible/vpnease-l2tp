"""
Interface error page.
"""
__docformat__ = 'epytext en'

from codebay.common import rdf
from codebay.l2tpserver import helpers
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.rdfconfig import ns_ui

class InterfaceErrorPage(commonpage.AdminPage):
    template = 'admin/misc/interfaceerror.xhtml'
    pagetitle = 'Network Interface Configuration Error'
