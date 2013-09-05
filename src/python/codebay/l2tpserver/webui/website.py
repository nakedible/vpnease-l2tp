"""
L2TPServer webui website hierarchies, and authentication/session management
(realms, credential checkers, minds, etc).
"""
__docformat__ = 'epytext en'

import os

from zope.interface import implements
from twisted.cred import checkers, credentials, portal, error
from twisted.internet import defer, ssl
from nevow import guard, inevow, appserver, rend

from codebay.common import rdf
from codebay.common import logger

from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import constants
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import commonpage, frontpage, loginpages, legalpages, forwardingpage, uihelpers

_log = logger.get('l2tpserver.webui.website')

# --------------------------------------------------------------------------

class CustomOpenSSLContextFactory(ssl.DefaultOpenSSLContextFactory):
    """Custom OpenSSL context factory."""

    def reread_files(self):
        # This is not terribly beautiful, but we must force the already created
        # context to change SSL related files.  See twisted.internet.ssl,
        # especially DefaultOpenSSLContextFactory.
        ctx = self.getContext()

        # Re-read external files; if that fails, (re-)read self-signed files
        try:
            # See e.g.: http://pyopenssl.sourceforge.net/pyOpenSSL.ps
            if os.path.exists(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN) and \
                   os.path.exists(constants.WEBUI_EXTERNAL_PRIVATE_KEY):
                _log.info('re-reading ssl certificates, using external files')
                ctx.use_certificate_chain_file(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN)
                ctx.use_certificate_file(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN)
                ctx.use_privatekey_file(constants.WEBUI_EXTERNAL_PRIVATE_KEY)
            else:
                _log.info('re-reading ssl certificates, using self-signed files')
                ctx.use_certificate_file(constants.WEBUI_CERTIFICATE)
                ctx.use_privatekey_file(constants.WEBUI_PRIVATE_KEY)
        except:
            _log.exception('failure to read certificate, attempting to load self-signed certificate as failsafe')
            _log.info('re-reading ssl certificates, using self-signed files')
            ctx.use_certificate_file(constants.WEBUI_CERTIFICATE)
            ctx.use_privatekey_file(constants.WEBUI_PRIVATE_KEY)
            
# --------------------------------------------------------------------------

#
#  XXX: The "top level web UI" solution needs a rewrite for clarity.
#
#  Page hierarchies should no longer be created dynamically on every
#  request.
#

class PageHierarchy(object):
    """Base class for describing resource hierarchies.

    Hierarchies work as follows:

    If the hierarchy resource is rendered as a child by itself
    (eg. http://site/foo) it will return a redirect adding a slash to
    the request (eg. http://site/foo/).

    When an URL under the hierarchy is accessed, self.hierarchy
    dictionary is looked up for the corresponding path component.

    If the result is another dictionary, the search continues under it
    for the next path component.

    If the result is a IResource (eg. a created Page instance or
    similar), rendering is passed on to that resource.

    If the result creates IResource instances (eg. a Page class or
    similar), a resource is created from it by calling
    self.makeResource and rendering is passed on to it.

    Otherwise pass rendering on to self.notFound.

    initialize should be overridden to create self.hierarchy.

    makeResource can be overridden if resources automatically created
    should have constructor arguments.

    notFound can be overridden to provide a custom page in case no
    match is found.
    """
    implements(inevow.IResource)
    hierarchy = None

    def do_initialize(self):
        self.initialize()

    def initialize(self):
        self.hierarchy = {}

    def notFound(self, ctx, segments):
        return rend.NotFound

    def makeResource(self, ctx, restsegments, r):
        return r(), restsegments

    def locateChild(self, ctx, segments):
        # render normally
        if self.hierarchy is None:
            self.do_initialize()
        cursegments = segments
        curroot = self.hierarchy
        while len(cursegments):
            r = curroot.get(cursegments[0], None)
            if isinstance(r, dict):
                curroot = curroot[cursegments[0]]
                cursegments = cursegments[1:]
                # XXX: if cursegments is now empty, perhaps return something other than notFound
            elif inevow.IResource.providedBy(r):
                return r, cursegments[1:]
            elif inevow.IResource.implementedBy(r):
                return self.makeResource(ctx, cursegments[1:], r)
            else:
                return self.notFound(ctx, segments)
        return self.notFound(ctx, segments)

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().child(''))
        return ''

class ForwardingPageHierarchy(object):
    """Page hierarchy for forced PPP connection web forwards."""
    implements(inevow.IResource)

    def notFound(self, ctx, segments):
        return rend.NotFound

    def locateChild(self, ctx, segments):
        # always the same result
        return forwardingpage.ForwardingPage(), []

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().child(''))
        return ''

class WebUiRootHierarchy(PageHierarchy):
    """Root hierarchy for the actual Web UI, including admin and user contexts.

    Shares the static hierarchy with Live CD, which is not optimal.
    """
    def __init__(self, master):
        self.master = master
    
    def initialize(self):
        self.hierarchy = {
            '': frontpage.FrontPage,
            'robots.txt': commonpage.RobotsTxtPage,
            'check.html': commonpage.CheckPage,
            'locallogin.html': loginpages.LocalAdminLogin(),
            'prohibited.html': loginpages.AccessProhibited(),
            'web-forced-redirection': forwardingpage.WebForcedRedirectionPage,
            'legal': LegalHierarchy(),
            'user': WebUiUserRealm.createRealm(self.master),
            'admin': WebUiAdminRealm.createRealm(self.master),
            'static': StaticHierarchy()
            }

class LiveCdRootHierarchy(PageHierarchy):
    """Root hierarchy for the Live CD.

    Shares the static hierarchy with web UI, which is not optimal.
    """
    def __init__(self, master):
        self.master = master
    
    def initialize(self):
        self.hierarchy = {
            '': frontpage.LivecdFrontPage,
            'robots.txt': commonpage.RobotsTxtPage,
            'livecd': LivecdHierarchy(),
            'legal': LegalHierarchy(),
            'static': StaticHierarchy()
            }

class StaticHierarchy(PageHierarchy):
    """Static files (images, CSS, JS) needed by either Live CD or web UI."""
    def initialize(self):
        from nevow import static
        self.hierarchy = { }

        files = [
            # css
            'site.css',
            'form.css',
            'layout.css',
            'login.css',
            'cb.css',
            'print-site.css',
            'print-ui.css',
            'print-cb.css',
            'print-formal.css',
            'formal.css',
            'hacks.css',
            'iehacks.css',
            
            # javascript
            'commonutils.js',
            'formalutils.js',
            'ajaxutils.js',
            'admin.js',
            'admin_ajaxupdate.js',
            'user_autologout.js',
            'livecd_ajaxupdate.js',
            'formal.js',
            
            # logo & favicon
            'vpnease-logo.gif',
            'vpnease-logo-small.gif',
            'favicon.gif',

            # css and other layout related images
            'bg-header.jpg',
            'bg-main-2.gif',
            'bg-main.gif',
            'bg-main-no-nav.gif',
            'bg-nav-a.gif',
            'bg-nav.png',
            'bg-box.gif',
            'bg-fieldset1-top.gif',
            'bg-fieldset2-top.gif',
            'bg-fieldset1-bottom.gif',
            'bg-fieldset2-bottom.gif',
            'bg-button.gif',
            'external.gif',
            'sep.gif',
            'bg-login-1.gif',
            'bg-login-2.gif',
            'hidden.gif',
            
            # buttons
            'button_up.png',
            'button_down.png',
            'button_add.png',
            'button_remove.png',
            'button_collapse.png',
            'button_expand.png',
            'button_expand_icon.png',  # for use within text paragraphs
            'button_help.png',
            'arrow.gif',
            
            # progress and activity bars
            'progress-1.gif',
            'progress-2.gif',

            # screenshots
            'w2k-spcheck-combined.png',
            'w2k-dialing-information-combined.png',
            'wxp-spcheck-combined.png',
            'wxp-dialing-information-combined.png',

            # SNMP MIB(s)
            'VPNEASE-MIB.txt',
            ]

        for i in files:
            self.hierarchy[i] = uihelpers.ExpiringFile(os.path.join(constants.WEBUI_PAGES_DIR, 'static', i))

        if os.path.exists(constants.CUSTOMER_LOGO):
            self.hierarchy['customer-logo.png'] = uihelpers.ExpiringFile(constants.CUSTOMER_LOGO)

class LegalHierarchy(PageHierarchy):
    """Legal documents for web UI."""
    def initialize(self):
        self.hierarchy = {
            'legalnotice.html': legalpages.LegalNoticePage
            }

class LoggedInHierarchy(PageHierarchy):
    """Subclass of PageHiearchy with logged in state tracking with a 'mind' object."""
    def __init__(self, master, mind):
        self.master = master
        self.mind = mind

    def makeResource(self, ctx, restsegments, r):
        return r(master=self.master, mind=self.mind), restsegments

class UserHierarchy(LoggedInHierarchy):
    """Hierarchy for user part of the web UI."""
    def initialize(self):
        from codebay.l2tpserver.webui.user import welcome
        from codebay.l2tpserver.webui.user import changepassword
        from codebay.l2tpserver.webui.user import passwordchanged
        from codebay.l2tpserver.webui.user.installation import winxp
        from codebay.l2tpserver.webui.user.installation import osx
        from codebay.l2tpserver.webui.user.installation import vista
        from codebay.l2tpserver.webui.user.installation import win2k
        from codebay.l2tpserver.webui.user.installation import winmobile
        from codebay.l2tpserver.webui.user.installation import other
        from codebay.l2tpserver.webui.user.installation import autoconfigexe
        from codebay.l2tpserver.webui.user.installation import autoconfigosx

        self.hierarchy = {
            'welcome.html': welcome.ClientStartPage,
            'changepassword.html': changepassword.ChangePasswordPage,
            'passwordchanged.html': passwordchanged.PasswordChangedPage,
            'vpnease_autoconfigure_winxp32.exe': autoconfigexe.WindowsXp32Bit,
            'vpnease_autoconfigure_winxp64.exe': autoconfigexe.WindowsXp64Bit,
            'vpnease_autoconfigure_vista32.exe': autoconfigexe.WindowsVista32Bit,
            'vpnease_autoconfigure_vista64.exe': autoconfigexe.WindowsVista64Bit,
            'vpnease_autoconfigure_win2k32.exe': autoconfigexe.Windows2k32Bit,
            'vpnease_autoconfigure_macosx.networkConnect': autoconfigosx.AutoconfigOsx,
            'installation': { 'winxp': { 'autodetect.html': winxp.WindowsXpAutoDetectPage,
                                         'autodetectdone.html': winxp.WindowsXpAutoDetectDonePage,
                                         'configuration.html': winxp.WindowsXpConfigurationPage,
                                         'finished.html': winxp.WindowsXpFinishedPage,
                                         'winxp-sp2-natt-enable.reg': winxp.WindowsXpSp2NattEnableRegFile,
                                         'winxp-sp2-natt-disable.reg': winxp.WindowsXpSp2NattDisableRegFile },
                              'osx104': { 'autodetect.html': osx.Osx104AutoDetectPage,
                                          'autodetectdone.html': osx.Osx104AutoDetectDonePage,
                                          'autofinished.html': osx.Osx104AutoFinishedPage,
                                          'configuration.html': osx.Osx104ConfigurationPage,
                                          'finished.html': osx.Osx104FinishedPage },
                              'osx105': { 'autodetect.html': osx.Osx105AutoDetectPage,
                                          'autodetectdone.html': osx.Osx105AutoDetectDonePage,
                                          'autofinished.html': osx.Osx105AutoFinishedPage,
                                          'configuration.html': osx.Osx105ConfigurationPage,
                                          'finished.html': osx.Osx105FinishedPage },
                              'vista': { 'autodetect.html': vista.WindowsVistaAutoDetectPage,
                                         'autodetectdone.html': vista.WindowsVistaAutoDetectDonePage,
                                         'configuration.html': vista.WindowsVistaConfigurationPage,
                                         'finished.html': vista.WindowsVistaFinishedPage,
                                         'vista-natt-enable.reg': vista.WindowsVistaNattEnableRegFile,
                                         'vista-natt-disable.reg': vista.WindowsVistaNattDisableRegFile },
                              'win2000': { 'autodetect.html': win2k.Windows2000AutoDetectPage,
                                           'autodetectdone.html': win2k.Windows2000AutoDetectDonePage,
                                           'configuration1.html': win2k.Windows2000Configuration1Page,
                                           'configuration2.html': win2k.Windows2000Configuration2Page,
                                           'configuration3.html': win2k.Windows2000Configuration3Page,
                                           'finished.html': win2k.Windows2000FinishedPage,
                                           'win2k-disable-ipsec-policy.reg': win2k.Windows2000DisableIpsecPolicyRegFile,
                                           'win2k-enable-ipsec-policy.reg': win2k.Windows2000EnableIpsecPolicyRegFile },
                              'other': { 'information.html': other.InformationPage },
                              'winmobile': { 'configuration.html': winmobile.WindowsMobileConfigurationPage,
                                             'finished.html': winmobile.WindowsMobileFinishedPage } }
                              #'linux': { 'information.html': other.LinuxPage },
                              #'win9x': { 'information.html': other.Windows9xMePage },
                              #'nokiatablet': { 'information.html': other.NokiaTabletPage },
                              #'opensource': { 'information.html': other.OpenSourcePage } }
            }
            
class AdminHierarchy(LoggedInHierarchy):
    """Hierarchy for admin part of the web UI."""
    def initialize(self):
        from codebay.l2tpserver.webui.admin.management import management
        from codebay.l2tpserver.webui.admin.config import networkconfig
        from codebay.l2tpserver.webui.admin.config import routingfirewall
        from codebay.l2tpserver.webui.admin.config import sitetositeconfig
        from codebay.l2tpserver.webui.admin.config import debugconfig
        from codebay.l2tpserver.webui.admin.users import userconfig
        from codebay.l2tpserver.webui.admin.status import statusmain
        from codebay.l2tpserver.webui.admin.status import users
        from codebay.l2tpserver.webui.admin.status import sitetosites
        from codebay.l2tpserver.webui.admin.misc import initialconfigpage
        from codebay.l2tpserver.webui.admin.misc import interfaceerrorpage
        from codebay.l2tpserver.webui.admin import dumps
        from codebay.l2tpserver.webui.admin import activateconfiguration
        
        self.hierarchy = {
            'dumpconfig.html': dumps.DumpConfigPage,
            'dumpstatus.html': dumps.DumpStatusPage,
            'dumpuiconfig.html': dumps.DumpUiConfigPage,
            'dumpall.html': dumps.DumpAllPage,
            'dumpsnmp.html': dumps.DumpSnmpPage,
            'dumpsyslog.html': dumps.DumpSyslogPage,
            'ajaxstatus.html': commonpage.AjaxStatus,
            'activateconfiguration.html': activateconfiguration.ActivateConfigurationPage,
            'ajaxactivateconfiguration.html': activateconfiguration.AjaxActivateConfiguration,
            'graph.html': commonpage.GraphPage,
            'misc': { 'initialconfig.html': initialconfigpage.InitialConfigPage,
                      'interfaceerror.html': interfaceerrorpage.InterfaceErrorPage,
                      },
            'config': { 'networkconfig.html': networkconfig.NetworkPage,
                        'routingfirewall.html': routingfirewall.RoutingFirewallPage,
                        'sitetositeconfig.html': sitetositeconfig.SiteToSitePage,
                        'debugconfig.html': debugconfig.DebugPage },
            'management': { 'management.html': management.ManagementPage,
                            'confirmreboot.html': management.ConfirmRebootPage,
                            'confirmshutdown.html': management.ConfirmShutdownPage,
                            'confirmupdate.html': management.ConfirmUpdatePage,
                            'waitreboot.html': management.WaitRebootPage,
                            'waitshutdown.html': management.WaitShutdownPage,
                            'waitupdate.html': management.WaitUpdatePage,
                            'configexport.html': management.ConfigExportPage,
                            'configimport.html': management.ConfigImportPage,
                            'waitconfigimport.html': management.WaitConfigImportPage,
                            'diagnosticsexport.html': management.DiagnosticsExportPage },
            'users': { 'userconfig.html': userconfig.UsersPage },
            'status': { 'main.html': statusmain.StatusMainPage,
                        'users.html': users.UserStatusPage,
                        'usershistory.html': users.UserStatusWithHistoryPage,
                        'sitetosites.html': sitetosites.SiteToSiteStatusPage,
                        'sitetositeshistory.html': sitetosites.SiteToSiteStatusWithHistoryPage }
            }

class LivecdHierarchy(PageHierarchy):
    def initialize(self):
        from codebay.l2tpserver.webui.livecd import \
             welcomepage, \
             installlicense, \
             installtarget, \
             installconfirm, \
             installcopying, \
             installcomplete, \
             installfailed, \
             waitreboot, \
             formattarget, \
             formatconfirm, \
             formatprogress, \
             formatcomplete, \
             formatfailed

        self.hierarchy = {
            '': frontpage.LivecdFrontPage,
            'welcome.html': welcomepage.WelcomePage,
            'installlicense.html': installlicense.InstallLicensePage,
            'installtarget.html': installtarget.InstallTargetPage,
            'installconfirm.html': installconfirm.InstallConfirmPage,
            'installcopying.html': installcopying.InstallCopyingPage,
            'installcomplete.html': installcomplete.InstallCompletePage,
            'installfailed.html': installfailed.InstallFailedPage,
            'waitreboot.html': waitreboot.WaitRebootPage,
            'ajaxprogress.html': installcopying.AjaxProgressPage,
            'formattarget.html': formattarget.FormatTargetPage,
            'formatconfirm.html': formatconfirm.FormatConfirmPage,
            'formatprogress.html': formatprogress.FormatProgressPage,
            'formatcomplete.html': formatcomplete.FormatCompletePage,
            'formatfailed.html': formatfailed.FormatFailedPage,
            'ajaxformatprogress.html': formatprogress.AjaxProgressPage
            }

# --------------------------------------------------------------------------

class WebUiSite:
    def __init__(self, original):
        self.master = original

    def createMainSite(self):
        r = WebUiRootHierarchy(self.master)
        site = appserver.NevowSite(r)
        return site

    def createForwardingSite(self):
        r = ForwardingPageHierarchy()
        site = appserver.NevowSite(r)
        return site

class LiveCdSite:
    def __init__(self, original):
        self.master = original

    def createMainSite(self):
        r = LiveCdRootHierarchy(self.master)
        site = appserver.NevowSite(r)
        return site

# --------------------------------------------------------------------------

class WebUiBaseMind(object):
    """Base class for the 'mind' object, representing authenticated user."""
    def __init__(self, request, cred):
        self.request = request
        self.credentials = cred

    def isLocal(self):
        if self.request.getClientIP() == '127.0.0.1':
            return True
        else:
            return False

class WebUiAdminMind(WebUiBaseMind):
    pass

class WebUiUserMind(WebUiBaseMind):
    pass

class WebUiCredentialChecker:
    implements(checkers.ICredentialsChecker)
    credentialInterfaces = (credentials.IUsernamePassword,)

    def __init__(self, require_admin=True):
        self.require_admin = require_admin

    @db.transact()
    def requestAvatarId(self, c):
        try:
            username = c.username
            password = c.password
            
            def _check_admin_rights(u):
                if u.getS(ns_ui.adminRights, rdf.Boolean):
                    return True
                else:
                    return False

            def _auth_callback(res):
                if res:
                    return username
                else:
                    return defer.fail(error.UnauthorizedLogin())

            def _auth_failed(x):
                _log.error('authentication errback, %s' % x)
                return defer.fail(error.UnauthorizedLogin())
            
            # NB: this will authenticate the user without regard to authorization.
            # Or more precisely: we *do* an authorization check for admin rights,
            # but whether admin connections are allowed through this interface of
            # the server is checked elsewhere (in AdminRealm, getAvatarResource).

            if self.require_admin:
                d = uihelpers.check_username_and_password_local_and_radius(username, password, filters=[_check_admin_rights], radius=True, radius_require_admin=True)
            else:
                d = uihelpers.check_username_and_password_local_and_radius(username, password, filters=[], radius=True, radius_require_admin=False)

            d.addCallback(_auth_callback)
            d.addErrback(_auth_failed)
            return d
        except:
            _log.exception('unknown error in requestAvatarId')
            return defer.fail(error.UnauthorizedLogin())
            
class WebUiBaseRealm(object):
    """Base class for web UI 'realms', representing authenticated hierarchies."""
    implements(portal.IRealm)
    mind = None

    def __init__(self, original):
        self.master = original

    def getAvatarResource(self, avatar_id, mind):
        """Get the resource (hierarchy) for (authenticated or anonymous) mind."""
        raise NotImplemented()

    def requestAvatar(self, avatar_id, mind, *interfaces):
        if inevow.IResource in interfaces:
            self.master.user_login(avatar_id, mind)
            def _logout():
                self.master.user_logout(avatar_id, mind)
            return (inevow.IResource, self.getAvatarResource(avatar_id, mind), _logout)
        raise NotImplemented()

class WebUiAdminRealm(WebUiBaseRealm):
    """Web UI realm for admin pages."""
    mind = WebUiAdminMind
    
    def createRealm(klass, master):
        realm = klass(master)
        p = portal.Portal(realm)
        p.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)
        p.registerChecker(WebUiCredentialChecker(require_admin=True))
        s = guard.SessionWrapper(p, mindFactory=klass.mind)
        s.useCookies = False    # XXX: False is good for debugging, URIs show session info
        return s
    createRealm = classmethod(createRealm)

    @db.transact()
    def getAvatarResource(self, avatar_id, mind):
        # This check is complicated a bit by web UI access control; admin may not
        # be allowed to access web UI admin part from public and/or private interface.
        # The check we do is against our local address (obtained from mind.request).
        #
        # If access is prohibited, the resource returned from here will prevent access
        # to all parts of the admin hierarchy.  Nevertheless, there is an extra check
        # there, too.

        if mind.isLocal():
            # local connections always accepted
            return AdminHierarchy(self.master, mind)
        else:
            # remote connection
            if not mind.request.isSecure():
                # don't allow non-ssl access
                return loginpages.AccessProhibited()

            if avatar_id is checkers.ANONYMOUS:
                # no authentication yet
                _log.debug('remote connection, mind anonymous')
                try:
                    if uihelpers.check_request_local_address_against_config(mind.request):
                        _log.debug('-> admin login')
                        return loginpages.AdminLogin()
                    else:
                        _log.debug('-> admin prohibited')
                        return loginpages.AccessProhibited()
                except:
                    _log.exception('failed in checking adminrealm access control')
                    return loginpages.AccessProhibited()
            else:
                # authenticated already - still check access
                _log.debug('remote connection, mind authenticated')
                try:
                    if uihelpers.check_request_local_address_against_config(mind.request):
                        _log.debug('-> admin ok')
                        return AdminHierarchy(self.master, mind)
                    else:
                        # This page is not very pretty, but the intent is for the web UI
                        # not to give an option to attempt login or access when it is not
                        # allowed.
                        _log.debug('-> admin prohibited')
                        return loginpages.AccessProhibited()
                except:
                    _log.exception('failed in checking adminrealm access control')
                    return loginpages.AccessProhibited()
                    
class WebUiUserRealm(WebUiBaseRealm):
    """Web UI realm for user pages."""
    mind = WebUiUserMind
    
    def createRealm(klass, master):
        realm = klass(master)
        p = portal.Portal(realm)
        p.registerChecker(checkers.AllowAnonymousAccess(), credentials.IAnonymous)
        p.registerChecker(WebUiCredentialChecker(require_admin=False))
        s = guard.SessionWrapper(p, mindFactory=klass.mind)
        s.useCookies = False    # XXX: False is good for debugging, URIs show session info
        return s
    createRealm = classmethod(createRealm)

    def getAvatarResource(self, avatar_id, mind):
        if avatar_id is checkers.ANONYMOUS:
            return loginpages.UserLogin()
        else:
            if not mind.request.isSecure():
                # don't allow non-ssl access
                return loginpages.AccessProhibited()

            return UserHierarchy(self.master, mind)
