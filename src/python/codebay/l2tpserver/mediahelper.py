"""Helpers for dealing with storage media, primarily during installation.
"""
__docformat__ = 'epytext en'

import os, re

from codebay.l2tpserver import halhelper

# Some useful Ubiquity binaries:
# /bin/hw-detect
# /bin/parted_devices

# Some other.. useful or not?
# /bin/mapdevfs
# /bin/debconf-get

class MediumInfo:
    def __init__(self):
        self.device = None   # e.g. '/dev/sda'
        self.status = None   # protection status: 'readwrite' or 'readonly'
        self.type = None     # device type: 'disk' or 'cdrom'
        self.size = None     # in bytes
        self.bus = None      # e.g. "ide", "scsi", etc.
        self.vendor = None   # e.g. "VMware,"
        self.model = None    # e.g. "VMware Virtual S"
        self.info = None     # human readable string
        self.partitions = None # partitions on this device

    def get_device(self):
        return self.device
    
    def get_size(self):
        return self.size
    
    def get_size_pretty(self, fake_units=True):
        kilo = 1024L
        if fake_units:
            kilo = 1000L
        mega = kilo*kilo
        giga = kilo*kilo*kilo

        size = long(self.size)

        if size < mega:
            return '%.2f kB' % (float(size) / float(kilo))
        elif size < giga:
            return '%.2f MB' % (float(size) / float(mega))
        else:
            return '%.2f GB' % (float(size) / float(giga))

    def get_vendor(self):
        return self.vendor

    def get_model(self):
        return self.model

    def get_info(self):
        return self.info
    
    def get_human_readable_description(self):
        t = self.info.lower()

        if not self.is_disk():
            # no magic, magic only works for disks
            return self.info

        # vmware magic
        r = re.compile(r'^.*?vmware.*?$')
        m = r.match(t)
        if m is not None:
            return 'VMware Virtual Disk'

        # parallels
        r = re.compile(r'^.*?virtual.*?hdd.*?$')
        m = r.match(t)
        if m is not None:
            return 'Parallels Virtual Disk'

        # virtual pc magic
        r = re.compile(r'^.*?virtual.*?hd.*?$')
        m = r.match(t)
        if m is not None:
            return 'Microsoft Virtual Disk'

        # no magic
        return self.info

    def get_bus_type(self):
        return self.bus

    def get_human_readable_bus_type(self):
        if self.bus is None or self.bus == '' or self.bus == 'Unknown':
            return 'Unknown'
        elif self.bus == 'ide':
            return 'IDE'
        elif self.bus == 'scsi':
            return 'SCSI'
        elif self.bus == 'sata':
            return 'Serial ATA (SATA)'
        elif self.bus == 'usb':
            return 'USB Storage'
        else:
            return self.bus.capitalize()

    def get_partitions(self):
        return self.partitions

    def is_write_protected(self):
        if self.status == 'readonly': return True
        return False

    def is_cdrom(self):
        if self.type == 'cdrom': return True
        return False

    def is_disk(self):
        if self.type == 'disk': return True
        return False

    def get_partition_devicename(self, number):
        # XXX: some paritions are "device" + "p" + number
        # XXX: such partitions are now not supported: the only way to
        # use such devices is to run a product in virtual machine.
        return self.device + str(number)

class MediaInfo:
    def __init__(self):
        self.media = []

    def from_system(klass):
        mi = klass()
        mi._do_parted_scan()
        return mi
    from_system = classmethod(from_system)
    
    def _do_parted_scan(self):
        self.media = []
        self.halinfo = halhelper.get_halinfo()
        for i in os.popen('/usr/lib/l2tpgw/parted_all_devices').read().split('\n'):
            l = i.split('\t')
            if len(l) > 2:
                m = MediumInfo()
                m.device = l[0]
                m.type = l[1]
                m.status = l[2]
                m.size = long(l[3])
                m.info = l[4]

                m.partitions = []

                d = self.halinfo.get_devices_by_properties([('block.device', m.device)])
                if len(d) > 0:
                    device = d[0]
                    m.vendor = device.get_property('info.vendor')
                    m.model = device.get_property('info.product')
                    m.bus = device.get_property('storage.bus')
                    p_list = self.halinfo.get_devices_by_properties([('info.parent', device.get_udi())])
                    for p in p_list:
                        p_name = p.get_property('block.device')
                        if p_name is not None:
                            m.partitions.append(p_name)

                if m.vendor is None:
                    m.vendor = 'Unknown'
                if m.model is None:
                    m.model = 'Unknown'
                if m.bus is None:
                    m.bus = 'Unknown'

                self.media.append(m)
    
    def get_media_list(self):
        return self.media

    def get_disk_media_list(self):
        disk_media = []
        for m in self.media:
            if m.is_disk():
                disk_media.append(m)

        return disk_media

    def get_medium_by_device_name(self, dev):
        for i in self.media:
            if dev == i.device: return i
        return None

    def verify_device_node(self, node):
        if not os.path.exists(node): return False
        # XXX: check file type..?
        return True

def get_media():
    return MediaInfo.from_system()
