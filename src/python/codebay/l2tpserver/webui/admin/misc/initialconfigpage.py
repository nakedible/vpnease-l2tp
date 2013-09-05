"""
Initial config page.
"""
__docformat__ = 'epytext en'

from codebay.common import rdf
from codebay.l2tpserver import helpers
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.rdfconfig import ns_ui

class InitialConfigPage(commonpage.AdminPage):
    template = 'admin/misc/initialconfig.xhtml'
    pagetitle = 'Initial Configuration'
