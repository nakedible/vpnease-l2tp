"""Windows 2000 pages."""
__docformat__ = 'epytext en'

from nevow import inevow

import os
import formal

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.win2k')

class Windows2000AutoDetectPage(formal.ResourceMixin,
                                uihelpers.UserInformationForm,
                                uihelpers.UserAgentHelpers,
                                uihelpers.AutoconfigureHelpers,
                                commonpage.UserPage):
    template = 'user/installation/win2000/autodetect.xhtml'
    pagetitle = 'Windows 2000 Autoconfiguration'
    next_uri = 'configuration1.html'
    next_label = 'Configure manually'

class Windows2000AutoDetectDonePage(uihelpers.AutoconfigureHelpers,
                                    commonpage.UserPopupPage):
    template = 'user/installation/win2000/autodetectdone.xhtml'
    pagetitle = 'Windows 2000 Autoconfiguration'

class Windows2000Configuration1Page(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/win2000/configuration1.xhtml'
    pagetitle = 'Windows 2000 Configuration (1 of 3)'
    next_uri = 'configuration2.html'
    prev_uri = None

class Windows2000Configuration2Page(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/win2000/configuration2.xhtml'
    pagetitle = 'Windows 2000 Configuration (2 of 3)'
    next_uri = 'configuration3.html'
    prev_uri = 'configuration1.html'
    
class Windows2000Configuration3Page(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/win2000/configuration3.xhtml'
    pagetitle = 'Windows 2000 Configuration (3 of 3)'
    next_uri = 'finished.html'
    prev_uri = 'configuration2.html'

class Windows2000FinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/win2000/finished.xhtml'
    pagetitle = 'Windows 2000 Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration3.html'

class Windows2000DisableIpsecPolicyRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'win2000', 'win2k-disable-ipsec-policy.reg')

class Windows2000EnableIpsecPolicyRegFile(commonpage.RegFile):
    raw_regfile = os.path.join(constants.WEBUI_PAGES_DIR, 'user', 'installation', 'win2000', 'win2k-enable-ipsec-policy.reg')
