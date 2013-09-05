"""Autoconfig EXE files.

Note: the same 32-bit autoconfigure EXE file works for Windows XP and Windows
Vista, for both 32-bit and 64-bit versions.  But because we want the flexibility
for future, there are separate EXE files for each variant now.  Of course, the
files are now identical.
"""
__docformat__ = 'epytext en'

import os
import time
import datetime

from nevow import inevow

from codebay.common import logger
from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import randutil
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.user.installation.autoconfigexe')

class _AutoconfigExe(commonpage.UserPage):
    autoconfig_exe_filename = None
    include_win2k_regdata = False
    force_server_address_to_ip = False
    
    @db.transact()
    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)

        # read unpatched exe
        f = None
        exedata = ''
        try:
            f = open(self.autoconfig_exe_filename, 'rb')
            exedata = f.read()
        finally:
            if f is not None:
                f.close()
                f = None

        # figure parameters
        server_address_in_uri = None
        try:
            server_address_in_uri = str(request.getRequestHostname())
        except:
            _log.exception('cannot figure out server_address_in_uri')

        server_ip = None
        try:
            server_ip = self._get_server_ip_for_win2k(ctx)
        except:
            _log.exception('cannot figure out server_ip')

        server_address = None
        if self.force_server_address_to_ip:
            server_address = server_ip
        else:
            server_address = server_address_in_uri

        if (server_address_in_uri is None) or (server_address_in_uri == ''):
            raise Exception('server_address_in_uri missing, failing')
        if (server_address is None) or (server_address == ''):
            raise Exception('server_address missing, failing')
        if self.include_win2k_regdata and ((server_ip is None) or (server_ip == '')):
            raise Exception('server_ip is needed and missing, failing')
        
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
            
        # Profile name, always uses address in URI, even if server address itself forced to IP
        profile_prefix = 'VPNease'
        try:
            if os.path.exists(constants.AUTOCONFIG_PROFILE_PREFIX_FILE):
                profile_prefix = helpers.read_and_strip_file(constants.AUTOCONFIG_PROFILE_PREFIX_FILE)
        except:
            _log.exception('failed when checking for alternative profile name')
        profile_name = '%s (%s)' % (profile_prefix, server_address_in_uri)

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

        # Windows 2000 registry-based IPsec policy + prohibitIpsec
        win2k_ipsec_policy_registry_file = ''
        try:
            if self.include_win2k_regdata:
                # Registry data is HEX encoded UTF-16; HEX encoding is used to avoid problems
                # with the parameters.cpp mechanism (null termination).  The resulting data is
                # large, around 50 kilobytes (!).

                # Always uses server IP for IPsec policy, because that's what Windows 2000 IPsec wants
                t = self._get_win2k_reg_file(server_ip, preshared_key)
                t = self._encode_windows_reg_file(t)  # UTF-16
                win2k_ipsec_policy_registry_file = t.encode('hex')  # hex-encoded UTF-16
        except:
            _log.exception('cannot create win2k registry file')
        
        # Fill paramdict and return
        paramdict = {}
        paramdict['operation'] = 'configure_profile'
        paramdict['profile_name'] = profile_name
        paramdict['desktop_shortcut_name'] = '%s.LNK' % profile_name  # xxx: for now the same
        paramdict['server_address'] = server_address
        paramdict['preshared_key'] = preshared_key
        paramdict['username'] = username
        paramdict['ppp_compression_enabled'] = '1'
        paramdict['default_route_enabled'] = '1'
        paramdict['create_desktop_shortcut'] = '1'
        paramdict['open_profile_after_creation'] = '1'
        if server_portfw:
            paramdict['server_behind_port_forward'] = '1'
        else:
            paramdict['server_behind_port_forward'] = '0'
        if self.include_win2k_regdata:
            paramdict['win2k_registry_file'] = win2k_ipsec_policy_registry_file
        return uihelpers.RewritingBinaryResource(exedata, paramdict)

        #
        #  XXX - Future feature -> generate autoconfig EXE with all parameters except
        #  username.  This would allow "operator like" cases where the same EXE is
        #  delivered to all authenticated users (e.g. through an operator portal).
        #
        
    #
    #  Windows 2000 support begins
    #
    
    def _get_server_ip_for_win2k(self, ctx):
        try:
            request = inevow.IRequest(ctx)
            server_address = str(request.getRequestHostname())
            t = datatypes.IPv4Address.fromString(server_address)
            return t.toString()
        except:  # XXX: wide catch
            pass

        # use management connection natted IP
        global_st = helpers.get_global_status()
        if global_st.hasS(ns.managementConnectionOurNattedAddress):
            return global_st.getS(ns.managementConnectionOurNattedAddress, rdf.IPv4Address).toString()

        return None

    def _reg_encode_bytes(self, x, linelen=16): 
        res = u'' 
 
        xlen = len(x) 
        num = 0 
        for i in xrange(xlen): 
            if num >= linelen: 
                res += u'\\\r\n' 
                res += u'  ' 
                num = 0 
 
            res += u'%02x' % ord(x[i]) 
            if i < xlen - 1: 
                res += u',' 
            num += 1 
 
        return res 
 
    def _reg_encode_utf16(self, x):
        return x.encode('utf_16_le') 
 
    def _reg_encode_utf16_list(self, xlist): 
        """Encode a list of Unicode strings into a comma separate hex encoded registry value."""
        t = '' 
        for x in xlist: 
            t += self._reg_encode_utf16(x + u'\u0000')  # null term 
        t += self._reg_encode_utf16(u'\u0000')  # end of list (double null) 
        return t 
 
    def _get_win2k_reg_file(self, server_ip, preshared_key):
        """Create the Windows 2000 IPsec policy as a registry file.

        The template for this was extracted by creating the policy according to
        VPNease instructions, testing the configuration, and then exporting the
        values using regedit.  The difficult parts were then verified against the
        ipsec2k1.1 library code (there is some reverse engineering work there).
        The registry data also includes the prohibitIpsec setting (set to 1 for
        Windows 2000 to bypass Rasman certificate-only policy).
        
        When generating a registry file, new GUIDs are generated each time,
        resulting in a number of policies.  This is an annoyance but should not
        be a real issue.  We have a couple of alternatives for this behavior.
        First, we could use fixed, build-time GUIDs.  This would limit the number
        of VPNease policies to at most one, but would prohibit the use of multiple
        servers.  Second, we could generate the GUIDs using a pseudorandom
        function which was deterministic but took, for instance, the server
        installation UUID and cookie UUID as inputs.  The result would be at most
        one policy per VPNease server.

        There are lots of details here.  To figure out or debug something, it is
        best to compare the data against (1) the ipsec2k1.1 library, and (2) the
        actual export (see e.g. ticket #902 and its attachments).
        """

        #
        #  XXX: pseudorandom GUIDs?  See #910.
        #
        
        def _get_guid():
            return randutil.random_uuid().upper()

        # XXX: non-ASCII pre-shared keys?
        preshared_key = unicode(preshared_key)

        # if server IP is not an *IP* address (but a DNS name), we fail here
        server_ip_long = datatypes.IPv4Address.fromString(server_ip).toLong()

        # actual data
        whenchanged = '%08x' % int(time.time())  # seems like this at least - XXX: timezone?
        now = datetime.datetime.utcnow()
        ipsec_policy_guid = _get_guid()
        ipsec_policy_name = 'VPNease Policy %s' % server_ip
        ipsec_filter_guid = _get_guid()
        ipsec_filter_name = 'VPNease Filter List %s' % server_ip
        ipsec_isakmp_policy_guid = _get_guid()
        ipsec_negotiation_policy1_guid = _get_guid()
        ipsec_negotiation_policy2_guid = _get_guid()
        ipsec_negotiation_policy2_name = 'VPNease Filter Action %s' % server_ip
        ipsec_nfa1_guid = _get_guid()
        ipsec_nfa2_guid = _get_guid()

        common_description = u'Automatically generated by VPNease (%s)' % now.isoformat()

        ipsec_negotiation_policy1_owner_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecNFA{%s}' % ipsec_nfa1_guid
            ]))
        ipsec_negotiation_policy2_owner_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecNFA{%s}' % ipsec_nfa2_guid
            ]))
        ipsec_nfa1_owner_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecPolicy{%s}' % ipsec_policy_guid
            ]))
        ipsec_nfa2_owner_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecPolicy{%s}' % ipsec_policy_guid
            ]))
        ipsec_nfa2_filter_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecFilter{%s}' % ipsec_filter_guid
            ]))
        ipsec_policy_nfa_reference = self._reg_encode_bytes(self._reg_encode_utf16_list([
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecNFA{%s}' % ipsec_nfa1_guid,
            u'SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecNFA{%s}' % ipsec_nfa2_guid
            ]))

        def _dword_le_hex(x):
            return '%02x%02x%02x%02x' % (((x >> 0) & 0xff),
                                         ((x >> 8) & 0xff),
                                         ((x >> 16) & 0xff),
                                         ((x >> 24) & 0xff))
        
        def _utf16_le_nullterm_hex(x):
            x = x + u'\u0000'
            return x.encode('utf_16_le').encode('hex')

        tmp = ''.join([
            '00acbb118d49d111863900a0248d3021',                                  # ipsecNFA class id, fixed
            _dword_le_hex(42 + 0*2),                                             # length of data, a bit uncertain but correct
            _dword_le_hex(1),                                                    # XXX: unknown
            _dword_le_hex(5),                                                    # type: .. XXX: 5 seems to be Kerberos??
            _dword_le_hex((0 + 1) * 2),                                          # length of psk (encoded length)
            _utf16_le_nullterm_hex(u''),                                         # utf16le nullterm psk (empty in this nfa)
            'fdffffff',                                                          # all connections
            '02000000000000000000000000000000000002000000000000'                 # unknown part
            ])
        ipsec_nfa1_ipsecdata = self._reg_encode_bytes(tmp.decode('hex'))

        tmp = ''.join([
            '00acbb118d49d111863900a0248d3021',                                  # ipsecNFA class id, fixed
            _dword_le_hex(42 + len(preshared_key)*2),                            # length of data, a bit uncertain but correct
            _dword_le_hex(1),                                                    # XXX: unknown
            _dword_le_hex(1),                                                    # type: psk
            _dword_le_hex((len(preshared_key) + 1) * 2),                         # length of psk (encoded length)
            _utf16_le_nullterm_hex(preshared_key),                               # utf16le nullterm psk
            'fdffffff',                                                          # all connections
            '02000000000000000000000000000100000002000000000000'                 # unknown part
            ])
        ipsec_nfa2_ipsecdata = self._reg_encode_bytes(tmp.decode('hex'))
        
        server_ip_byte1 = '%02x' % ((server_ip_long >> 24) & 0xff)
        server_ip_byte2 = '%02x' % ((server_ip_long >> 16) & 0xff)
        server_ip_byte3 = '%02x' % ((server_ip_long >> 8) & 0xff)
        server_ip_byte4 = '%02x' % ((server_ip_long >> 0) & 0xff)

        reg_data = u"""\
Windows Registry Editor Version 5.00\r
\r
[HKEY_LOCAL_MACHINE\\SYSTEM\\CurrentControlSet\\Services\\RasMan\\Parameters]\r
"ProhibitIpsec"=dword:00000001\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local]\r
"ActivePolicy"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecPolicy{%(ipsec_policy_guid)s}"\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecFilter{%(ipsec_filter_guid)s}]\r
"ClassName"="ipsecFilter"\r
"ipsecID"="{%(ipsec_filter_guid)s}"\r
"ipsecName"="%(ipsec_filter_name)s"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecData"=hex:b5,20,dc,80,c8,2e,d1,11,a8,9e,00,a0,24,8d,30,21,4a,00,00,00,01,\\\r
  00,00,00,02,00,00,00,00,00,02,00,00,00,00,00,02,00,00,00,00,00,48,3c,a9,2a,\\\r
  e1,1c,3f,46,aa,a1,60,d8,18,ab,68,78,01,00,00,00,00,00,00,00,00,00,00,00,%(server_ip_byte1)s,\\\r
  %(server_ip_byte2)s,%(server_ip_byte3)s,%(server_ip_byte4)s,ff,ff,ff,ff,00,00,00,00,11,00,00,00,a5,06,00,00,00,00,00,00,00\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecFilter{%(ipsec_filter_guid)s}"\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecISAKMPPolicy{%(ipsec_isakmp_policy_guid)s}]\r
"ClassName"="ipsecISAKMPPolicy"\r
"ipsecID"="{%(ipsec_isakmp_policy_guid)s}"\r
"ipsecName"="{%(ipsec_isakmp_policy_guid)s}"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecData"=hex:b8,20,dc,80,c8,2e,d1,11,a8,9e,00,a0,24,8d,30,21,40,01,00,00,ff,\\\r
  e6,f9,f9,7c,18,1c,45,9a,f5,18,03,84,29,04,92,00,00,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,04,00,00,00,00,00,00,00,03,00,00,00,40,00,00,00,\\\r
  08,00,00,00,02,00,00,00,40,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,02,00,00,00,00,00,00,00,00,00,00,00,80,70,00,00,01,00,\\\r
  34,00,00,00,00,00,03,00,00,00,40,00,00,00,08,00,00,00,01,00,00,00,40,00,00,\\\r
  00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,02,00,00,00,\\\r
  00,00,00,00,00,00,00,00,80,70,00,00,00,00,00,00,00,00,00,00,01,00,00,00,40,\\\r
  00,00,00,08,00,00,00,02,00,00,00,40,00,00,00,00,00,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,00,01,00,00,00,00,00,00,00,00,00,00,00,80,70,00,\\\r
  00,00,00,46,00,00,00,00,00,01,00,00,00,40,00,00,00,08,00,00,00,01,00,00,00,\\\r
  40,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,03,00,00,01,\\\r
  00,00,00,00,00,00,00,00,00,00,00,80,70,00,00,a8,0a,1c,04,00\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecISAKMPPolicy{%(ipsec_isakmp_policy_guid)s}"\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy1_guid)s}]\r
"ClassName"="ipsecNegotiationPolicy"\r
"ipsecID"="{%(ipsec_negotiation_policy1_guid)s}"\r
"ipsecNegotiationPolicyType"="{62F49E13-6C37-11D1-864C-14A300000000}"\r
"ipsecNegotiationPolicyAction"="{8A171DD3-77E3-11D1-8659-A04F00000000}"\r
"ipsecName"="{8A171DD3-77E3-11D1-8659-A04F00000000}"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecOwnersReference"=hex(7):%(ipsec_negotiation_policy1_owner_reference)s\r
"ipsecData"=hex:b9,20,dc,80,c8,2e,d1,11,a8,9e,00,a0,24,8d,30,21,e4,01,00,00,06,\\\r
  00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,01,00,00,00,03,00,\\\r
  00,00,02,00,00,00,02,00,00,00,40,00,00,00,08,00,00,00,29,00,00,00,27,00,00,\\\r
  00,01,00,00,00,00,00,00,00,2a,00,00,00,1f,00,00,00,d9,ac,59,00,9c,01,09,00,\\\r
  04,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,01,\\\r
  00,00,00,03,00,00,00,01,00,00,00,02,00,00,00,40,00,00,00,08,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,00,00,00,00,00,04,00,09,00,01,00,00,00,98,01,23,\\\r
  00,f0,ef,c8,00,80,70,00,00,01,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,01,00,00,00,01,00,00,00,02,00,00,00,02,00,00,00,40,00,00,00,08,\\\r
  00,00,00,00,00,00,00,00,00,00,00,5c,00,4c,00,6f,00,63,00,04,00,09,00,01,00,\\\r
  69,00,98,01,23,00,28,5a,c8,00,4e,00,46,00,41,00,7b,00,00,00,00,00,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,01,00,00,00,01,00,00,00,01,00,00,00,02,00,00,00,\\\r
  40,00,00,00,08,00,00,00,00,00,00,00,00,00,00,00,70,00,73,00,65,00,63,00,04,\\\r
  00,09,00,01,00,7b,00,a0,f6,c8,00,28,5a,c8,00,38,00,31,00,35,00,36,00,00,00,\\\r
  00,00,00,00,00,00,00,00,00,00,00,00,00,00,01,00,00,00,02,00,00,00,00,00,00,\\\r
  00,01,00,00,00,40,00,00,00,08,00,00,00,1c,16,4b,76,00,00,00,00,00,01,00,00,\\\r
  c8,46,08,77,c8,46,08,77,c8,46,08,77,99,9d,f6,c4,a4,b7,b9,45,b1,ed,cd,13,64,\\\r
  4a,f5,17,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,00,01,00,00,00,01,00,\\\r
  00,00,00,00,00,00,01,00,00,00,40,00,00,00,08,00,00,00,02,00,00,00,02,00,00,\\\r
  00,40,00,00,00,08,00,00,00,00,00,00,00,40,00,00,00,08,00,00,00,2c,01,00,00,\\\r
  09,00,11,00,01,00,09,00,00\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecNegotiationPolicy{%(ipsec_negotiation_policy1_guid)s}"\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy2_guid)s}]\r
"ClassName"="ipsecNegotiationPolicy"\r
"ipsecID"="{%(ipsec_negotiation_policy2_guid)s}"\r
"ipsecNegotiationPolicyType"="{62F49E10-6C37-11D1-864C-14A300000000}"\r
"ipsecNegotiationPolicyAction"="{8A171DD3-77E3-11D1-8659-A04F00000000}"\r
"ipsecName"="%(ipsec_negotiation_policy2_name)s"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecData"=hex:b9,20,dc,80,c8,2e,d1,11,a8,9e,00,a0,24,8d,30,21,54,00,00,00,01,\\\r
  00,00,00,2c,01,00,00,00,00,00,00,00,00,00,00,00,00,00,00,01,00,00,00,03,00,\\\r
  00,00,01,00,00,00,02,00,00,00,40,00,00,00,08,00,00,00,00,00,00,00,00,00,00,\\\r
  00,70,00,73,00,65,00,63,00,04,00,09,00,01,00,7b,00,a0,f6,c8,00,28,5a,c8,00,\\\r
  38,00,31,00,35,00,36,00,00\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecNegotiationPolicy{%(ipsec_negotiation_policy2_guid)s}"\r
"ipsecOwnersReference"=hex(7):%(ipsec_negotiation_policy2_owner_reference)s\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecNFA{%(ipsec_nfa1_guid)s}]\r
"ClassName"="ipsecNFA"\r
"ipsecID"="{%(ipsec_nfa1_guid)s}"\r
"ipsecNegotiationPolicyReference"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy1_guid)s}"\r
"ipsecName"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy1_guid)s}"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecData"=hex:%(ipsec_nfa1_ipsecdata)s\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecNFA{%(ipsec_nfa1_guid)s}"\r
"ipsecOwnersReference"=hex(7):%(ipsec_nfa1_owner_reference)s\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecNFA{%(ipsec_nfa2_guid)s}]\r
"ClassName"="ipsecNFA"\r
"ipsecID"="{%(ipsec_nfa2_guid)s}"\r
"ipsecNegotiationPolicyReference"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy2_guid)s}"\r
"ipsecName"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecNegotiationPolicy{%(ipsec_negotiation_policy2_guid)s}"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"ipsecData"=hex:%(ipsec_nfa2_ipsecdata)s\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecNFA{%(ipsec_nfa2_guid)s}"\r
"ipsecOwnersReference"=hex(7):%(ipsec_nfa2_owner_reference)s\r
"ipsecFilterReference"=hex(7):%(ipsec_nfa2_filter_reference)s\r
\r
[HKEY_LOCAL_MACHINE\\SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\ipsecPolicy{%(ipsec_policy_guid)s}]\r
"ClassName"="ipsecPolicy"\r
"ipsecID"="{%(ipsec_policy_guid)s}"\r
"ipsecName"="%(ipsec_policy_name)s"\r
"ipsecDataType"=dword:00000100\r
"description"="%(common_description)s"\r
"whenChanged"=dword:%(whenchanged)s\r
"name"="ipsecPolicy{%(ipsec_policy_guid)s}"\r
"ipsecISAKMPReference"="SOFTWARE\\\\Policies\\\\Microsoft\\\\Windows\\\\IPSec\\\\Policy\\\\Local\\\\ipsecISAKMPPolicy{%(ipsec_isakmp_policy_guid)s}"\r
"ipsecNFAReference"=hex(7):%(ipsec_policy_nfa_reference)s\r
"ipsecData"=hex:63,21,20,22,4c,4f,d1,11,86,3b,00,a0,24,8d,30,21,04,00,00,00,30,\\\r
  2a,00,00,00\r
""" % {'whenchanged': whenchanged,
       'ipsec_policy_guid': ipsec_policy_guid,
       'ipsec_policy_name': ipsec_policy_name,
       'ipsec_filter_guid': ipsec_filter_guid,
       'ipsec_filter_name': ipsec_filter_name,
       'ipsec_isakmp_policy_guid': ipsec_isakmp_policy_guid,
       'ipsec_negotiation_policy1_guid': ipsec_negotiation_policy1_guid,
       'ipsec_negotiation_policy2_guid': ipsec_negotiation_policy2_guid,
       'ipsec_negotiation_policy2_name': ipsec_negotiation_policy2_name,
       'ipsec_nfa1_guid': ipsec_nfa1_guid,
       'ipsec_nfa2_guid': ipsec_nfa2_guid,
       'ipsec_negotiation_policy1_owner_reference': ipsec_negotiation_policy1_owner_reference,
       'ipsec_negotiation_policy2_owner_reference': ipsec_negotiation_policy2_owner_reference,
       'ipsec_nfa1_owner_reference': ipsec_nfa1_owner_reference,
       'ipsec_nfa2_owner_reference': ipsec_nfa2_owner_reference,
       'ipsec_nfa2_filter_reference': ipsec_nfa2_filter_reference,
       'ipsec_policy_nfa_reference': ipsec_policy_nfa_reference,
       'ipsec_nfa1_ipsecdata': ipsec_nfa1_ipsecdata,
       'ipsec_nfa2_ipsecdata': ipsec_nfa2_ipsecdata,
       'server_ip_byte1': server_ip_byte1,
       'server_ip_byte2': server_ip_byte2,
       'server_ip_byte3': server_ip_byte3,
       'server_ip_byte4': server_ip_byte4,
       'common_description': common_description,
       }

        return reg_data
    
    def _encode_windows_reg_file(self, x):
        # UTF16 BOM: little-endian
        res = '\xff\xfe'
        for c in x:
            t = ord(c)
            res += chr((t >> 0) & 0xff)
            res += chr((t >> 8) & 0xff)
        return res
    
    def _windows_unicode_to_python_triplequoted(self, x):
        """Helper function not used directly in product.

        Reads in a Windows .reg file which are little-endian UTF16 documents
        with a byte order marker of 0xff 0xfe.  Converts the input to a Python
        triple-quoted string with proper escapes.
        """
        
        if x[0] == chr(0xff) and x[1] == chr(0xfe): 
            # windows little-endian unicode marker ok 
            pass 
        else: 
            raise Exception('does not seem like a windows unicode file') 
 
        x = x[2:] 
        nch = len(x) / 2 
        res = 'u"""\\\n'
        n_quots = 0 
        for i in xrange(nch): 
            t0 = x[i*2 + 0] 
            t1 = x[i*2 + 1] 
 
            o = ord(t0) + ord(t1)*256 
            if (o == ord('"')): 
                n_quots += 1 
            else: 
                n_quots = 0 

            if ((o >= ord('a')) and (o <= ord('z'))) or \
               ((o >= ord('A')) and (o <= ord('Z'))) or \
               ((o >= ord('0')) and (o <= ord('9'))):
                res += chr(o) 
            elif (o <= 0x7e) and (chr(o) in ' \n\t:-_=[](){},.\''): 
                res += chr(o) 
            elif (o == ord('"') and n_quots < 3): 
                res += chr(o) 
            elif (o == ord('\\')): 
                # two quotes 
                res += '\\\\' 
            elif (o == ord('\r')): 
                res += '\\r' 
            else: 
                res += '\\u%04x' % o 
 
        res += '"""' 
        return res 

class WindowsXp32Bit(_AutoconfigExe):
    autoconfig_exe_filename = constants.AUTOCONFIG_EXE_WINXP_32BIT

class WindowsXp64Bit(_AutoconfigExe):
    autoconfig_exe_filename = constants.AUTOCONFIG_EXE_WINXP_64BIT

class WindowsVista32Bit(_AutoconfigExe):
    autoconfig_exe_filename = constants.AUTOCONFIG_EXE_VISTA_32BIT

class WindowsVista64Bit(_AutoconfigExe):
    autoconfig_exe_filename = constants.AUTOCONFIG_EXE_VISTA_64BIT

class Windows2k32Bit(_AutoconfigExe):
    autoconfig_exe_filename = constants.AUTOCONFIG_EXE_WIN2K_32BIT
    include_win2k_regdata = True
    force_server_address_to_ip = True
