"""Windows XP pages."""
__docformat__ = 'epytext en'

from nevow import inevow, tags as T

import os, formal

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.winxp')

class WindowsXpAutoDetectPage(formal.ResourceMixin,
                              uihelpers.UserInformationForm,
                              uihelpers.UserAgentHelpers,
                              uihelpers.AutoconfigureHelpers,
                              commonpage.UserPage):
    template = 'user/installation/winxp/autodetect.xhtml'
    pagetitle = 'Windows XP Autoconfiguration'
    next_uri = 'configuration.html'
    next_label = 'Configure manually'

class WindowsXpAutoDetectDonePage(uihelpers.AutoconfigureHelpers,
                                  commonpage.UserPopupPage):
    template = 'user/installation/winxp/autodetectdone.xhtml'
    pagetitle = 'Windows XP Autoconfiguration'
    
class WindowsXpConfigurationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/winxp/configuration.xhtml'
    pagetitle = 'Windows XP Configuration'
    next_uri = 'finished.html'

class WindowsXpFinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/winxp/finished.xhtml'
    pagetitle = 'Windows XP Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration.html'

class WindowsXpSp2NattEnableRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'winxp', 'winxp-sp2-natt-enable.reg')

class WindowsXpSp2NattDisableRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'winxp', 'winxp-sp2-natt-disable.reg')
