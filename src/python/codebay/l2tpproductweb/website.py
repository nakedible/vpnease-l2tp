"""
VPNease product website, dynamically served.
"""
__docformat__ = 'epytext en'

import os
import md5
import mimetools
import mimetypes
from zope.interface import implements
from twisted.cred import checkers, credentials, portal, error
from twisted.internet import defer, ssl
from nevow import guard, inevow, appserver, rend, static, loaders

from codebay.common import logger

from codebay.l2tpproductweb import pages

_log = logger.get('l2tpproductweb.website')

HTTP_PORT = 8080

# --------------------------------------------------------------------------

# Python modules: mimetools, mimetypes, MimeWriter

def get_mimetype(name):
    try:
        mimetype, encoding = mimetypes.guess_type(name)
        return mimetype
    except:
        _log.exception('failed to guess mime type')
        return 'application/octet-stream'
    
def check_md5(fname, md5sum):
    f = open(fname, 'rb')
    bufsize = 65536
    try:
        dig = md5.md5()
        while True:
            t = f.read(bufsize)
            if len(t) == 0:
                break
            dig.update(t)
        res = dig.hexdigest()
        if res != md5sum:
            raise Exception('MD5 for %s is %s, differ from expected %s' % (fname, res, md5sum))
    finally:
        if f is not None:
            f.close()

# --------------------------------------------------------------------------

class RedirectPage(rend.Page):
    docFactory = loaders.xmlfile(pages.get_filename('redirect-template.xhtml'))
    
    def __init__(self, topic, target):
        rend.Page.__init__(self)
        self.topic = topic
        self.target = target
        
    def render_redirect_target(self, ctx, data):
        return self.target

    def render_redirect_topic(self, ctx, data):
        return self.topic

# --------------------------------------------------------------------------

# XXX: this shares code with the product - can this be unified in codebay
# helpers easily?

class PageHierarchy(object):
    """Base class for describing resource hierarchies."""
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

# --------------------------------------------------------------------------

class RootHierarchy(PageHierarchy):
    def __init__(self, master):
        self.master = master
    
    def initialize(self):
        """Initialize hierarchy.

        Note that this is done only once and is *very* slow, because we check the
        MD5 sums of downloadable binaries to ensure they have been consistently
        deployed.
        """

        _log.info('Initializing root hierarchy')

        imagefiles =  [
            'favicon.ico',
            'favicon.gif',
            'bg-banner.gif',
            'bg-menu-current.gif',
            'bg-menu-sep.gif',
            'bullet-document.png',
            'bullet-star.gif',
            'bullet-form.png',
            'external.gif',
            'feed-icon.gif',
            'logo.gif',
            'status-snapshot.gif',
            'freetrial-button-small-blue.png',
            'freetrial-button-medium-blue.png',
            'buynow-button-small-blue.png',
            'buynow-button-medium-blue.png',
            ]

        stylefiles = [
            'form.css',
            'home.css',
            'layout.css',
            'site.css',
            'cb.css',
            'iehacks.css',
            'print-site.css',
            'print-cb.css',
            'print-web.css',
            ]

        pagelist = [
            pages.ProductHomePage,
            pages.FeaturesPage,
            pages.ProductComparisonPage,
            pages.PricingPage,
            pages.PaymentOptionsPage,
            pages.ProductAskMorePage,
            pages.ProductAskMoreSuccessPage,
            pages.ProductAskMoreFailurePage,
            pages.BuyLicensePage,
            pages.BuyLicenseConfirmPage,
            pages.BuyLicenseSuccessPage,
            pages.BuyLicenseFailurePage,
            pages.LicenseAgreementPage,
            pages.PrivacyPolicyPage,
            pages.DescriptionOfFilePage,
            pages.DualUsePage,
            pages.LegalNoticePage,
                  
            pages.SupportHomePage,
            pages.FaqPage,
            pages.TestServersPage,
            pages.SupportAskMorePage,
            pages.SupportAskMoreSuccessPage,
            pages.SupportAskMoreFailurePage, 
            pages.SupportRequestPage,
            pages.SupportRequestSuccessPage,
            pages.SupportRequestFailurePage,
            pages.QuickInstallationGuidePage,
            pages.ServerInstallationPage,
            pages.ServerBiosSetupPage,
            pages.ServerRequirementsPage,
            pages.VirtualizationProductsPage,
            pages.ClientConfigurationPage,
            pages.AdministrationInterfacePage,
            pages.SiteToSiteConfigurationPage,
            pages.EncryptionAndStandardsPage,
            pages.AuthenticationOptionsPage,
            pages.SnmpMonitoringPage,
            pages.ServerClusteringPage,
            pages.MultiCustomerConfigurationPage,
            
            pages.PartnersHomePage,
            pages.PartnerBenefitsPage,
            pages.PartnerDiscountsPage,
            pages.ServiceProviderPartnerProcessPage,
            pages.InstallationPartnerProcessPage,
            pages.ServiceProviderPartnerSalesMaterialsPage,
            pages.InstallationPartnerSalesMaterialsPage,
            pages.PartnerAskMorePage,
            pages.PartnerAskMoreSuccessPage,
            pages.PartnerAskMoreFailurePage,
            pages.RequestPartnershipPage,
            pages.RequestPartnershipSuccessPage,
            pages.RequestPartnershipFailurePage,
            pages.ServiceProviderPartnerActivateLicensePage,
            pages.ServiceProviderPartnerActivateLicenseConfirmPage,
            pages.ServiceProviderPartnerActivateLicenseSuccessPage,
            pages.ServiceProviderPartnerActivateLicenseFailurePage,
            pages.InstallationPartnerActivateLicensePage,
            pages.InstallationPartnerActivateLicenseConfirmPage,
            pages.InstallationPartnerActivateLicenseSuccessPage,
            pages.InstallationPartnerActivateLicenseFailurePage,
            pages.PartnerLicenseAgreementPage,

            pages.DownloadHomePage,
            pages.LatestVersionPage,
            pages.PreviousVersionsPage,
            pages.OpenSourcePage,
            ]

        partners_pagelist = [
            pages.PartnerSiteTestPage,
            pages.PartnerSiteLicensesPage,
            pages.PartnerSiteFloatingLicensesPage,
            ]
        
        downloads = [
            #'':   # FIXME: redirect to www.vpnease.com
            ( '81726ddc5958dd01b0a6562c93fcf6c1', 'vpnease_1-0-5287-appliance-novmwaretools.zip' ),
            ( '9970c980c5cb1141e198562b1c5c763b', 'vpnease_1-0-5287-appliance-vmwaretools.zip' ),
            ( '556ad782f61f091aa65e2a72a24f8bca', 'vpnease_1-0-5287.iso' ),
            ( '71582407738e98e511789f53f10edbfd', 'vpnease_1-0-5287.iso.zip' ),
            ( 'c7ac00c3487cb443124463f5e3621d58', 'vpnease_opensource_r5287.tar.gz' ),
            ( 'bd736bf8e00f1be4427e4fc3f4a794f6', 'vpnease_1-0-5529-appliance-novmwaretools.zip' ),
            ( '4cf44a23f45bf869e2d6c9167a0e2ad9', 'vpnease_1-0-5529-appliance-vmwaretools.zip' ),
            ( 'f33e19d92003736b90badf903b90df68', 'vpnease_1-0-5529.iso' ),
            ( 'd9e5048621ec6467dfda7cec988f38a9', 'vpnease_1-0-5529.iso.zip' ),
            ( '94d82358da3a024be7133f4309eaec89', 'vpnease_opensource_r5529.tar.gz' ),
            ( '43dcb0c32c910a437dc7adaf1834df2e', 'vpnease_1-1-6708-appliance-novmwaretools.zip' ),
            ( '86759690f94507a174b8116a5e1d44d2', 'vpnease_1-1-6708-appliance-vmwaretools.zip' ),
            ( 'c775eb41b268302ed5fe2f7ecd4a43e4', 'vpnease_1-1-6708.iso' ),
            ( '72956771f904fd826c800ca8cb682244', 'vpnease_1-1-6708.iso.zip' ),
            ( 'ef4a12056e50277f0d75cec256240ba1', 'VPNEASE-MIB_1-1-6708.txt' ),
            ( 'd0d408844776d75f66f111635a5357d7', 'dictionary_1-1-6708.vpnease' ),
            ( 'ed241c5b8dccc89403e5872a50c3322d', 'vpnease_opensource_r6708.tar.gz' ),
            ( 'b653e25a5d9596416aa4afccde9335f8', '2007-09-24-vpnease_datasheet_en.pdf' ),
            ( '018478fa09e42396937efa307f40610f', '2007-09-24-vpnease_datasheet_fi.pdf' ),
            ( '521025c77e9a1907b9b4885cbed10b02', '2007-10-30-vpnease_sales_presentation_en.pdf' ),
            ( '6404e798b88652ea1086f0428401f6cd', '2007-10-30-vpnease_sales_presentation_fi.pdf' ),
            ( '5367f1eb2c2eea904b8b9a9c809c01c7', '2008-03-31-vpnease_sales_presentation_en.pdf' ),
            ( '98105da98fd03fb5c97bca6803bc8e38', '2008-03-31-vpnease_sales_presentation_fi.pdf' ),
            ( '7224934dd429a0ef97751ab3b27c1aa6', 'recovery.sh' ),
            ]

        # XXX: apache2 now serves downloads
        downloads = []
        
        t = {}
        for i in imagefiles:
            t[i] = static.File(pages.get_filename('i/%s' % i), defaultType=get_mimetype(i))
        image_hierarchy = t
        
        t = {}
        for i in stylefiles:
            t[i] = static.File(pages.get_filename('s/%s' % i), defaultType=get_mimetype(i))
        style_hierarchy = t

        t = {}
        for topic, href in [
            [ 'product-pages',                      'http://www.vpnease.com/product-home.html',                ],
            [ 'support-pages',                      'http://www.vpnease.com/support-home.html',                ],
            [ 'vpn-client-compatibility',           'http://www.vpnease.com/wiki/wiki/ThirdPartyVpnClientCompatibility', ],
            [ 'linux-client',                       'http://www.vpnease.com/wiki/wiki/LinuxClientIssues', ],
            [ 'windows2000-vpn-client-limitations', 'http://www.vpnease.com/wiki/wiki/Windows2000ClientIssues',],
            [ 'end-user-license-agreement',         'http://www.vpnease.com/license-agreement.html',           ],
            [ 'privacy-policy',                     'http://www.vpnease.com/privacy-policy.html',              ],
            [ 'multiple-installation-targets',      'http://www.vpnease.com/wiki/wiki/FAQ',                    ],
            [ 'installation-recovery',              'http://www.vpnease.com/wiki/wiki/FAQ#Myproductupdatefailedhowtorecover' ],
            ]:
            t[topic] = RedirectPage(topic, href)
        topic_hierarchy = t

        t = {}
        for i in partners_pagelist:
            t[i.uri] = i
        partners_hierarchy = t
        
        t = {}
        t[''] = pages.HomePage
        t['index.html'] = pages.HomePage  # FIXME: redirect
        t['index.htm'] = pages.HomePage   # FIXME: redirect
        t['i'] = image_hierarchy
        t['s'] = style_hierarchy
        t['topic'] = topic_hierarchy
        t['partners'] = partners_hierarchy
        for i in pagelist:
            t[i.uri] = i
        for (md5, i) in downloads:
            fname = pages.get_filename('d/%s' % i)

            force_md5_check = False
            skip_md5_check = True  # FIXME
            
            if (pages.production_mode or force_md5_check) and (not skip_md5_check):
                _log.info('checking md5 for %s (expect: %s)' % (fname, md5))
                try:
                    check_md5(fname, md5)
                except:
                    _log.error('md5 check failed for %s' % fname)
                    raise
            else:
                pass
            
            t[i] = static.File(fname, defaultType=get_mimetype(i))
        self.hierarchy = t

class WebSite:
    def __init__(self, original):
        self.master = original

    def createMainSite(self):
        r = RootHierarchy(self.master)
        r.initialize()
        site = appserver.NevowSite(r)
        return site

# --------------------------------------------------------------------------


