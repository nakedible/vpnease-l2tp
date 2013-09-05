"""Other client pages."""
__docformat__ = 'epytext en'

from nevow import inevow

import formal

from codebay.common import logger
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.other')

# Other
class InformationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/other/information.xhtml'
    pagetitle = 'Other Operating Systems'
    next_uri = None
    prev_uri = None
