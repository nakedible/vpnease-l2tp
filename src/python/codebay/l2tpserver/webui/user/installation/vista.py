"""Vista pages."""
__docformat__ = 'epytext en'

from nevow import inevow

import os
import formal

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.vista')

class WindowsVistaAutoDetectPage(formal.ResourceMixin,
                                 uihelpers.UserInformationForm,
                                 uihelpers.UserAgentHelpers,
                                 uihelpers.AutoconfigureHelpers,
                                 commonpage.UserPage):
    template = 'user/installation/vista/autodetect.xhtml'
    pagetitle = 'Windows Vista Autoconfiguration'
    next_uri = 'configuration.html'
    next_label = 'Configure manually'

class WindowsVistaAutoDetectDonePage(uihelpers.AutoconfigureHelpers,
                                     commonpage.UserPopupPage):
    template = 'user/installation/vista/autodetectdone.xhtml'
    pagetitle = 'Windows Vista Autoconfiguration'

class WindowsVistaConfigurationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/vista/configuration.xhtml'
    pagetitle = 'Windows Vista Configuration'
    next_uri = 'finished.html'
    prev_uri = None
    
class WindowsVistaFinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/vista/finished.xhtml'
    pagetitle = 'Windows Vista Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration.html'

class WindowsVistaNattEnableRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'vista', 'vista-natt-enable.reg')

class WindowsVistaNattDisableRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'vista', 'vista-natt-disable.reg')
