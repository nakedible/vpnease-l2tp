"""Mac OS X pages."""
__docformat__ = 'epytext en'

from nevow import inevow

import formal

from codebay.common import logger
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.osx')

class Osx104AutoDetectPage(formal.ResourceMixin,
                           uihelpers.UserInformationForm,
                           uihelpers.UserAgentHelpers,
                           uihelpers.AutoconfigureHelpers,
                           commonpage.UserPage):
    template = 'user/installation/osx104/autodetect.xhtml'
    pagetitle = 'Mac OS X 10.4 (Tiger) Configuration'
    next_uri = 'autofinished.html'
    next_label = 'Next'

class Osx104AutoDetectDonePage(uihelpers.AutoconfigureHelpers,
                               commonpage.UserPopupPage):
    template = 'user/installation/osx104/autodetectdone.xhtml'
    pagetitle = 'Mac OS X 10.4 (Tiger) Configuration'

class Osx104ConfigurationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx104/configuration.xhtml'
    pagetitle = 'Mac OS X 10.4 (Tiger) Configuration'
    next_uri = 'finished.html'
    prev_uri = None
    
class Osx104FinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx104/finished.xhtml'
    pagetitle = 'Mac OS X 10.4 (Tiger) Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration.html'

class Osx104AutoFinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx104/finished.xhtml'
    pagetitle = 'Mac OS X 10.4 (Tiger) Configuration (Finished)'
    next_uri = None
    prev_uri = 'autodetect.html'

class Osx105AutoDetectPage(formal.ResourceMixin,
                           uihelpers.UserInformationForm,
                           uihelpers.UserAgentHelpers,
                           uihelpers.AutoconfigureHelpers,
                           commonpage.UserPage):
    template = 'user/installation/osx105/autodetect.xhtml'
    pagetitle = 'Mac OS X 10.5 (Leopard) Configuration'
    next_uri = 'autofinished.html'
    next_label = 'Next'

class Osx105AutoDetectDonePage(uihelpers.AutoconfigureHelpers,
                               commonpage.UserPopupPage):
    template = 'user/installation/osx105/autodetectdone.xhtml'
    pagetitle = 'Mac OS X 10.5 (Leopard) Configuration'

class Osx105ConfigurationPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx105/configuration.xhtml'
    pagetitle = 'Mac OS X 10.5 (Leopard) Configuration'
    next_uri = 'finished.html'
    prev_uri = None
    
class Osx105FinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx105/finished.xhtml'
    pagetitle = 'Mac OS X 10.5 (Leopard) Configuration (Finished)'
    next_uri = None
    prev_uri = 'configuration.html'

class Osx105AutoFinishedPage(formal.ResourceMixin, uihelpers.UserInformationForm, commonpage.UserPage):
    template = 'user/installation/osx105/finished.xhtml'
    pagetitle = 'Mac OS X 10.5 (Leopard) Configuration (Finished)'
    next_uri = None
    prev_uri = 'autodetect.html'
