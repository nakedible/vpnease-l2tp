"""Windows Mobile pages."""
__docformat__ = 'epytext en'

from nevow import inevow, tags as T

import os, formal

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.winmobile')

class WindowsMobileConfigurationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/winmobile/configuration.xhtml'
    pagetitle = 'Windows Mobile Configuration'
    next_uri = 'finished.html'

class WindowsMobileFinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/winmobile/finished.xhtml'
    pagetitle = 'Windows Mobile Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration.html'
