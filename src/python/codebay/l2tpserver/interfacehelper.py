"""Helper for getting information about network interfaces.

This functionality is shared by many modules: installer, boot scripts,
web UI, license management, etc.
"""
__docformat__ = 'epytext en'

import re, datetime, math

from codebay.common import datatypes
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants
from codebay.l2tpserver import netidentify

run_command = runcommand.run_command

# regexes to parse the output of 'ip -s -o link list'
_re_iplink_hdr = re.compile(r'^\d+:\s*(.*?):\s+.*$')
_re_iplink_info = re.compile(r'^.*?link.*?$')
_re_iplink_type = re.compile(r'^.*?link/(.*?)\s+.*?$')
_re_iplink_rxhdr = re.compile(r'^\s*RX:\s+.*$')
_re_iplink_rxctr = re.compile(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$')
_re_iplink_txhdr = re.compile(r'^\s*TX:\s+.*$')
_re_iplink_txctr = re.compile(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$')
_re_iplink_up = re.compile(r'^.*?<.*?UP.*?>.*?$')
_re_iplink_hdr_mtu = re.compile(r'^.*?mtu\s+(\d+)\s*.*?$')
_re_iplink_info_mac = re.compile(r'^.*?link\S+\s+(.*?)\s+.*?$')

# regexes to parse the output of 'ip -s -o addr list <dev>'
_re_ipaddr_inet = re.compile(r'^.*?\s+inet\s+(.*?)\s+.*?$')

# regex for ppp device names ('l2tpN-N')
_re_ppp_devname = re.compile(r'^l2tp\d+-\d+$')

class InterfaceInfo:
    """Represent the relevant information from 'ip -s link list' for a single device."""
    def __init__(self, devname, rxbytes, rxpackets, txbytes, txpackets, mtu, mac, linktype):
        """Constructor."""

        self.devname = devname
        self.rxbytes = int(rxbytes)
        self.rxpackets = int(rxpackets)
        self.txbytes = int(txbytes)
        self.txpackets = int(txpackets)
        self.mtu = int(mtu)
        self.mac = mac
        self.linktype = linktype

    def get_device_name(self):
        return self.devname

    def get_mtu(self):
        return self.mtu

    def get_mac(self):
        return self.mac

    def get_link_type(self):
        return self.linktype
    
    def is_ethernet_device(self):
        return self.linktype == 'ether'

    def is_l2tp_ppp_device(self):
        m = _re_ppp_devname.match(self.devname)
        if m is not None:
            return True
        return False

    def get_current_ipv4_address_info(self):
        (retval, retout, reterr) = run_command([constants.CMD_IP, '-s', '-o', 'addr', 'list', self.devname], retval=runcommand.FAIL)
        for i in retout.split('\n'):
            for j in i.split('\\'):
                m = _re_ipaddr_inet.match(j)
                if m is not None:
                    return datatypes.IPv4AddressSubnet.fromString(m.group(1))

        return None

    def identify_device(self):
        return netidentify.identify_device(self.devname)

    def toString(self):
        """Convert to one-line string."""

        return '%s: mac=%s, linktype=%s, mtu=%s, rx=%s/%s, tx=%s/%s' % (self.devname, self.mac, self.linktype, self.mtu, self.rxbytes, self.rxpackets, self.txbytes, self.txpackets)

class InterfaceInfos:
    """Represent the state of all devices (interfaces) at a certain time."""

    def __init__(self):
        """Constructor."""

        self.all_devs = None

    def from_system(klass, devname=None, filterfunc=None, require_up=True):
         """Get device information from system (i.e., the 'ip' command)."""

         di = klass()
         di.all_devs = di._get_interface_infos(devname, filterfunc, require_up)
         return di
    from_system = classmethod(from_system)

    def get_interface_list(self):
        """Get all devices in a (shallow copy) list."""

        return self.all_devs[:]  # clone

    def get_interface_names(self):
        """Get list of all interface names."""

        t = []
        for i in self.all_devs:
            t.append(i.devname)

        return t
    
    def get_interface_by_name(self, devname):
        """Get a specific device."""

        for i in self.all_devs:
            if i.devname == devname:
                return i

        return None
    
    def _get_interface_infos(self, devname, filterfunc, require_up):
        """Get a list of InterfaceInfos for all devices in 'ip -s link list'."""

        d = []
        if devname is not None:
            d.append(str(devname))

        (retval, retout, reterr) = run_command([constants.CMD_IP, '-s', '-o', 'link', 'list'] + d, retval=runcommand.FAIL)

        # gather info about all devices
        alldevs = []
        for i in retout.split('\n'):
            try:
                (l_hdr, l_info, l_rxhdr, l_rxcnt, l_txhdr, l_txcnt) = i.split('\\')
            except:
                continue

            # We ignore devices which are not 'up'.  pppd will create a device
            # even before calling pre-ip-up; if we don't ignore such devices,
            # reconcile will consider them to be "out of sync" with RDF, and
            # will nuke them.

            dev, mtu, mac, linktype = None, None, None, None
            
            m = _re_iplink_up.match(l_hdr)
            if m is None and require_up:
                continue

            m = _re_iplink_hdr.match(l_hdr)
            if m is None: continue
            dev = m.group(1)

            m = _re_iplink_hdr_mtu.match(l_hdr)
            if m is None: continue  # MTU is mandatory
            mtu = int(m.group(1))

            m = _re_iplink_info.match(l_info)
            if m is None: continue
            # no info, ignore

            m = _re_iplink_type.match(l_info)
            if m is not None:
                linktype = m.group(1)
                
            m = _re_iplink_info_mac.match(l_info)
            if m is not None:  # MAC is not mandatory
                mac = m.group(1)

            m = _re_iplink_rxhdr.match(l_rxhdr)
            if m is None: continue
            # no info, ignore

            m = _re_iplink_rxctr.match(l_rxcnt)
            if m is None: continue
            rxbytes, rxpackets = m.group(1), m.group(2)

            m = _re_iplink_txhdr.match(l_txhdr)
            if m is None: continue
            # no info, ignore

            m = _re_iplink_txctr.match(l_txcnt)
            if m is None: continue
            txbytes, txpackets = m.group(1), m.group(2)

            d = InterfaceInfo(dev, rxbytes, rxpackets, txbytes, txpackets, mtu, mac, linktype)

            if filterfunc and not filterfunc(d):
                pass
            else:
                alldevs.append(d)

        return alldevs

def get_interfaces():
    """Get all interfaces that are currently up."""
    return InterfaceInfos.from_system()

def get_all_interfaces():
    """Get all interfaces, up or down.."""
    return InterfaceInfos.from_system(require_up=False)

