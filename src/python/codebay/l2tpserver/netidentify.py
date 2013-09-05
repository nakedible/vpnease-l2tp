"""Helper for identifying details of Linux network devices.

This tool extracts network MAC, vendor, and device information from
sysfs.  It will then use any available PCI databases to look up
details of the device, preferring:
  1. External list from pciids
  2. Ubuntu hwdata PCI list
  3. Debian PCI list
  4. External list from www.pcidatabase.com

NB: We currently only identify PCI/PCI-E devices.  This should suffice
for almost all uses.
"""
__docformat__ = 'epytext en'

import os, re

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers

# list of pci hw files
_hwdata_sources = constants.PCI_HWDATA_SOURCES

# NB: some pci data has broken IDs, e.g. '003' instead of '0003' or
# '01234' instead of '1234' We need to fix these or skip.  Regexps
# below accept them and _fix_id() later converts them to valid IDs.
_re_class_line = re.compile(r'^C')
_re_vendor_line = re.compile(r'^([0-9a-fA-F]+)\s+(.*?)\s+\n?$')
_re_device_line = re.compile(r'^\t([0-9a-fA-F]+)\s+(.*?)\s+\n?$')
_re_subvendordevice_line = re.compile(r'^\t\t([0-9a-fA-F]+)\s+([0-9a-fA-F]+)\s+(.*?)\s+\n?$')

class PciData:
    def __init__(self):
        self.vendors = {}   # '8086' -> name
        self.devices = {}   # '8086:1234' -> device name

        for i in _hwdata_sources:
            try:
                # this is assumed to parse all formats
                self._parse_pciids_hwdata(i)
            except:
                pass

    # FIXME: 2009-10-20: _fix_id() throws exception in some cases, len(id) is applied
    # to an object which does not support id() -- make this more robust
    def _fix_id(self, id):
        if len(id) == 4:
            return id
        if len(id) < 4:
            return ('0000' + id)[-4:]
        if len(id) > 4:
            return id[-4:]  # XXX: this assumes the ID is of the form '<bogus>1234'

    def _parse_pciids_hwdata(self, name):
        f = None
        try:
            f = open(name, 'rb')

            vendor = None
            while True:
                l = f.readline()
                if l == '': break

                # skip class lines
                m = _re_class_line.match(l)
                if m is not None:
                    continue
            
                m = _re_vendor_line.match(l)
                if m is not None:
                    vendor = self._fix_id(m.group(1))
                    if not self.vendors.has_key(vendor):
                        self.vendors[vendor] = m.group(2)
                    continue

                m = _re_device_line.match(l)
                if m is not None:
                    device = self._fix_id(m.group(1))
                    if vendor is None:
                        # XXX: warning?
                        continue
                    str = '%s:%s' % (vendor, device)
                    if not self.devices.has_key(str):
                        self.devices[str] = m.group(2)
                    continue

                m = _re_subvendordevice_line.match(l)
                if m is not None:
                    subvendor, subdevice = self._fix_id(m.group(1)), self._fix_id(m.group(2))

                    # XXX: We skip these now
                    str = '%s:%s' % (subvendor, subdevice)
                    if not self.devices.has_key(str):
                        self.devices[str] = m.group(3)
        except:
            # XXX: no use to raise here
            pass

        if f is not None:
            f.close()
        
    def pci_vendor_lookup(self, vendor):
        # FIXME: here 'vendor' may not be a string
        id = self._fix_id(vendor)
        if self.vendors.has_key(id):
            return self.vendors[id]
        return None
    
    def pci_device_lookup(self, vendor, device):
        str = '%s:%s' % (self._fix_id(vendor), self._fix_id(device))
        if self.devices.has_key(str):
            return self.devices[str]
        return None

class NetworkDeviceInfo:
    def __init__(self):
        self.device = None
        self.vendor_id = None
        self.device_id = None
        self.vendor_string = None
        self.device_string = None
        self.mac = None
        self.vmware = False
        # XXX: virtual pc, virtual server
        # XXX: parallels

    def _readfile(self, name):
        t = None
        f = None
        try:
            if os.path.exists(name):
                f = open(name, 'rb')
                t = f.read()
                t = t.strip()
                f.close()
                f = None
        except:
            pass

        if f is not None: f.close()
        return t
    
    def _identify(self, dev, pcidata):
        """Call only once."""

        self.device = dev

        dir1 = '/sys/class/net/%s' % dev
        dir2 = os.path.join(dir1, 'device')
        
        if not os.path.exists(dir1):
            return

        self.mac = self._readfile(os.path.join(dir1, 'address'))

        if not os.path.exists(dir2):
            return

        self.vendor_id = self._readfile(os.path.join(dir2, 'vendor'))
        self.device_id = self._readfile(os.path.join(dir2, 'device'))
        self.vendor_string = pcidata.pci_vendor_lookup(self.vendor_id)
        self.device_string = pcidata.pci_device_lookup(self.vendor_id, self.device_id)

        self.vmware = helpers.host_is_vmware()

_global_pcidata = None

def initialize_database():
    """Initialize the (PCI) device database.

    This takes a few seconds, and is initialized also "on demand" if
    not initialized manually beforehand.
    """
    global _global_pcidata

    # takes a few seconds to load...
    if _global_pcidata is None:
        _global_pcidata = PciData()
    
def identify_device(devname):
    """Identify a (PCI) network device.

    To speed up, call initialize_database() beforehand.  The device
    database is initialized only once
    """

    initialize_database()
    
    i = NetworkDeviceInfo()
    i._identify(devname, _global_pcidata)
    return i
    
