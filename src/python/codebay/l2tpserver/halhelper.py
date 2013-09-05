"""
Helper class to read and interpret HAL information from lshal -command output.

XXX: there could be some other use for this besides the mediahelper.
"""

__docformat__ = 'epytext en'

import re

from codebay.l2tpserver import constants

from codebay.l2tpserver import runcommand
run_command = runcommand.run_command

def _clean_string(value):
    v = value.strip()
    if len(value) < 2: return

    return v[1:len(v) - 1].strip()

class HalDevice:
    def __init__(self):
        self.udi = None
        self.properties = {}


    def get_udi(self):
        return self.udi

    def set_udi(self, udi):
        self.udi = udi

    def get_property(self, name):
        if self.properties.has_key(name):
            return self.properties[name]
        else:
            return None

    def set_property(self, name, value):
        self.properties[name] = value

def _parse_string_list(value):
    if len(value) < 1: return None
    ret = []
    for l in value.split(','):
        ret.append(_clean_string(l))
    return ret

class HalHelper:
    def __init__(self):
        self.devices = {}

    def get_device(self, udi):
        if self.devices.has_key(udi):
            return self.devices[udi]
        else:
            return None

    def get_devices_by_properties(self, props):
        ret = []
        for k, d in self.devices.iteritems():
            match = True
            for p, v in props:
                if d.get_property(p) != v:
                    match = False
                    break
            if match:
                ret.append(d)

        return ret

    def _do_lshal_scan(self):
        [rv, out, err] = run_command([constants.CMD_LSHAL])
        if rv != 0: return

        udi_re = re.compile(r"^udi = (.+?)$")

        string_prop_re = re.compile(r"^  (.+?) = '(.+?)'  \(string\)")
        string_list_prop_re = re.compile(r"^  (.+?) = \{(.+?)\} \(string list\)") # Note: one space intended!
        int_prop_re = re.compile(r"^  (.+?) = (.+?)  (0x\d+) \(int\)")
        uint64_prop_re = re.compile(r"^  (.+?) = (.+?)  (0x\d+) \(uint64\)")
        bool_prop_re = re.compile(r"^  (.+?) = (.+?)  \(bool\)")

        def _parse_bool(value):
            if value == 'true': return True
            return False


        hd = None
        for l in out.split('\n'):
            m = udi_re.match(l)
            if m is not None:
                udi = _clean_string(m.groups()[0])
                hd = HalDevice()
                hd.set_udi(udi)
                self.devices[udi] = hd
                continue

            if hd is None:
                continue

            m = string_prop_re.match(l)
            if m is not None:
                hd.set_property(m.groups()[0], str(m.groups()[1]))
                continue

            m = string_list_prop_re.match(l)
            if m is not None:
                hd.set_property(m.groups()[0], _parse_string_list(m.groups()[1]))
                continue

            m = int_prop_re.match(l)
            if m is not None:
                hd.set_property(m.groups()[0], int(m.groups()[1]))
                continue

            m = uint64_prop_re.match(l)
            if m is not None:
                hd.set_property(m.groups()[0], long(m.groups()[1]))
                continue

            m = bool_prop_re.match(l)
            if m is not None:
                hd.set_property(m.groups()[0], _parse_bool(m.groups()[1]))
                continue

    def from_system(klass):
        hi = klass()
        hi._do_lshal_scan()
        return hi
    from_system = classmethod(from_system)

def get_halinfo():
    return HalHelper().from_system()

