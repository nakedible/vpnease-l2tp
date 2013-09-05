"""Autoconfig for Mac OS X.

Creates a property list (plist) for autoconfigured the Mac OS X VPN client.

Good related resources:
  * http://en.wikipedia.org/wiki/Property_list
  * http://developer.apple.com/documentation/Darwin/Reference/ManPages/man5/plist.5.html
  * http://developer.apple.com/documentation/CoreFoundation/Conceptual/CFPropertyLists/CFPropertyLists.html
  * http://www.apple.com/DTDs/PropertyList-1.0.dtd
  * http://developer.apple.com/documentation/Networking/Conceptual/SystemConfigFrameworks/SC_UnderstandSchema/chapter_4_section_2.html  (see 'PPP' parameters)

OpenDarwin 'ppp' component processes PPP related parameters, but OpenDarwin is now discontinued:
  * http://en.wikipedia.org/wiki/OpenDarwin
  * http://www.opendarwin.info/opendarwin.org/en/
  * http://darwinports.com/
  * http://www.opensource.apple.com/darwinsource/10.5/
  * http://www.opensource.apple.com/darwinsource/10.4/

Option processing can be viewed from 'ppp' module of OpenDarwin.  This is for ppp-314.tar.gz (Leopard):
  * Helpers/vpnd/RASSchemaDefinitions.h
    * Most definitions related to RAS
  * Controller/ppp_manager.c
    * Look for 'defaultroute', which controls whether defaultroute is added to pppd
    * Found the following: #define kSCPropNetOverridePrimaryCFSTR("OverridePrimary")
    * Perhaps option name is "OverridePrimary", under IPv4 options
"""
__docformat__ = 'epytext en'

import os
import textwrap

from nevow import inevow, static

from codebay.common import logger
from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.autoconfigosx')

class AutoconfigOsx(commonpage.UserPage):
    @db.transact()
    def renderHTTP(self, ctx):
        # XXX: refactor this to a helper??
        def _xml_escape(x):
            return helpers.xml_escape(x)

        # XXX: simple base64 encoding does not seem to be enough
        def _base64_encode(x):
            # base64 produces a newline, strip it away; still not correct tho
            return x.encode('base64').strip()

        request = inevow.IRequest(ctx)

        # figure parameters
        server_address = ''
        try:
            server_address = str(request.getRequestHostname())
        except:
            _log.exception('cannot figure out server_address')
            
        preshared_key = ''
        try:
            psk_seq = helpers.get_ui_config().getS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey)))
            preshared_key = str(psk_seq[0].getS(ns_ui.preSharedKey, rdf.String))
        except:
            _log.exception('cannot figure out preshared_key')

        username = ''
        try:
            tmp = self.get_logged_in_username()
            if tmp is not None:
                username = str(tmp)
        except:
            _log.exception('cannot figure out username')
            
        # Profile name
        profile_prefix = 'VPNease'
        try:
            if os.path.exists(constants.AUTOCONFIG_PROFILE_PREFIX_FILE):
                profile_prefix = helpers.read_and_strip_file(constants.AUTOCONFIG_PROFILE_PREFIX_FILE)
        except:
            _log.exception('failed when checking for alternative profile name')
        profile_name = '%s (%s)' % (profile_prefix, server_address)

        # Server behind port forward
        server_portfw = False
        try:
            global_st = helpers.get_global_status()
            if global_st.hasS(ns.behindNat):
                if global_st.getS(ns.behindNat, rdf.Boolean):
                    server_portfw = True
                else:
                    server_portfw = False
            else:
                # assume worst - reboot *MAY* be required
                server_portfw = True

            # markerfile for debugging
            if helpers.check_marker_file(constants.FORCE_NATTREBOOT_MARKERFILE):
                _log.warning('force nat-t reboot marker file exists, pretending server is behind port forward')
                server_portfw = True
        except:
            _log.exception('cannot determine whether server is behind port forward, may be OK')
            
        #
        #  Notes about OSX plist for networkConnect
        #
        #    * There are settings for PPP redial counts etc.  We don't use them
        #      because we want to minimize risks.
        #
        #    * DisconnectOnXXX settings only seem to work when inside SystemConfig,
        #      not inside UserConfigs.
        #
        #    * SystemConfig -> IPv4 -> OverridePrimary=1 should, based on PPP code,
        #      set 'default route' setting but doesn't seem to work.
        #
        #    * UserConfigs -> IPsec -> ExportedSharedSecret contains the pre-shared
        #      key for IKE in some sort of encrypted format.  The value is base64
        #      encoded but the pre-shared key is processed (encrypted or masked)
        #      prior to base64.  Note that whatever the unknown (and seemingly
        #      undocumented transform is, it has to be reversible because IKE needs
        #      the PSK.
        #
        #    * CCP / MPPC / MPPE are disabled now.  They don't actually work in
        #      Leopard at least.
        #
        
        # create xml plist
        textdata = textwrap.dedent("""\
            <?xml version="1.0" encoding="UTF-8"?>
            <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            <plist version="1.0">
                <dict>
                    <key>L2TP</key>
                    <dict>
                        <key>SystemConfig</key>
                        <dict>
                            <key>PPP</key>
                            <dict>
                                <key>DisconnectOnSleep</key>
                                <integer>1</integer>
                                <key>DisconnectOnFastUserSwitch</key>
                                <integer>1</integer>
                                <key>DisconnectOnLogout</key>
                                <integer>1</integer>
                            </dict>
                        </dict>

                        <key>UserConfigs</key>
                        <array>
                            <dict>
                                <key>EAP</key>
                                <dict/>
                                <key>IPSec</key>
                                <dict>
                                    <key>AuthenticationMethod</key>
                                    <string>SharedSecret</string>
                                    <key>LocalIdentifier</key>
                                    <string></string>
                                    <key>LocalIdentifierType</key>
                                    <string>KeyID</string>
                                </dict>
                                <key>PPP</key>
                                <dict>
                                    <key>AuthName</key>
                                    <string>%(username)s</string>
                                    <key>CommRemoteAddress</key>
                                    <string>%(server_address)s</string>
                                    <key>UserDefinedName</key>
                                    <string>%(profile_name)s</string>
                                    <key>CCPEnabled</key>
                                    <integer>%(ccp_enabled)d</integer>
                                    <key>CCPMPPE128Enabled</key>
                                    <integer>%(ccp_mppe40_enabled)d</integer>
                                    <key>CCPMPPE40Enabled</key>
                                    <integer>%(ccp_mppe128_enabled)d</integer>
                                </dict>
                            </dict>
                        </array>
                    </dict>
                </dict>
            </plist>
        """) % {
            'preshared_key_base64': _xml_escape(_base64_encode(preshared_key)),
            'username': _xml_escape(username),
            'server_address': _xml_escape(server_address),
            'profile_name': _xml_escape(profile_name),
            'override_primary': 1, # XXX: force default route
            'ccp_enabled': 0,
            'ccp_mppe40_enabled': 0,
            'ccp_mppe128_enabled': 0,
            }
        
        #
        #  Content-Type is interesting.  If this is served as 'text/xml', Safari
        #  will display the file without offering a save option.  Even if it is
        #  saved, Safari will *refuse* saving the file with '.networkConnect'
        #  extension.
        #
        #  'application/octet-stream' causes Safari to save the file, and use can
        #  double click to run it.
        #

        return uihelpers.UncachedData(textdata, 'application/octet-stream')
