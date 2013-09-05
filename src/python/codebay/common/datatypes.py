"""
Codebay datatypes.
"""
__docformat__ = 'epytext en'

import re, datetime, time

re_ipv4_address = re.compile(r'^(\d+)\.(\d+)\.(\d+)\.(\d+)$')
re_ipv4_subnet = re.compile(r'^(\d+\.\d+\.\d+\.\d+)/(\d+)$')
re_ipv4_address_range = re.compile(r'^(\d+\.\d+\.\d+\.\d+)-(\d+\.\d+\.\d+\.\d+)$')
re_port = re.compile(r'^(\d+)$')
re_port_range = re.compile(r'^(\d+)-(\d+)$')

ADDR_INVALID = -1L
ADDR_MIN = 0L
ADDR_MAX = (255L<<24L) + (255L<<16L) + (255L<<8L) + 255L
CIDR_INVALID = -1L
CIDR_MIN = 0L
CIDR_MAX = 32L
PORT_INVALID = -1L
PORT_MIN = 0L
PORT_MAX = 65535L

class Error(Exception):
    """Datatype Exception."""
    
class InvalidIPAddress(Error):
    """Invalid IP address Exception."""
    
class InvalidSubnet(Error):
    """Invalid subnet mask Exception."""
        
class InvalidIPAddressRange(Error):
    """Invalid IP address range Exception."""
        
class InvalidPort(Error):
    """Invalid port Exception."""
        
class InvalidPortRange(Error):
    """Invalid port range Exception."""

def _cidr_to_mask_long(cidr):
    return (~(0xffffffffL >> cidr)) & 0xffffffffL

# global mask list
_masks = {}
for i in xrange(0, 33):
    m = _cidr_to_mask_long(i)
    a = (m >> 24L) & 0xffL
    b = (m >> 16L) & 0xffL
    c = (m >> 8L) & 0xffL
    d = (m >> 0L) & 0xffL
    mask = '%d.%d.%d.%d' % (a, b, c, d)
    _masks[mask] = long(i)
    
def mask_to_cidr(mask):
    try:
        return _masks[mask]
    except:
        raise InvalidSubnet()

class IPv4Address:
    """IPv4Address.

    >>> a = IPv4Address.fromString('1.2.3.4')
    >>> a.toString()
    '1.2.3.4'
    >>> a.toLong()
    16909060L
    >>> b = IPv4Address.fromLong(16909061L)
    >>> b.toString()
    '1.2.3.5'
    >>> b.toLong()
    16909061L
    >>> a == b
    False
    >>> a < b
    True
    """
    addr = ADDR_INVALID

    def __cmp__(self, other):
         if self.__class__ == other.__class__:
              return cmp(self.addr, other.addr)
         else:
              return cmp(self.__class__, other.__class__)

    def fromString(klass, str):
        try:
            a = 0L
            for i in re_ipv4_address.match(str).groups():
                t = long(i)
                if (t < 0L) or (t > 255L): raise Exception()
                a = (a << 8L) + t
            v = klass()
            v.addr = a
            return v
        except:
            raise InvalidIPAddress()
    fromString = classmethod(fromString)

    def toString(self):
        [a, b, c, d] = self.toIntegerList()
        return "%d.%d.%d.%d" % (a, b, c, d)

    def fromLong(klass, l):
        if (l < ADDR_MIN) or (l > ADDR_MAX): raise Error()
        v = klass()
        v.addr = l
        return v
    fromLong = classmethod(fromLong)

    def toLong(self):
        return self.addr

    def fromIntegerList(klass, l):
        if len(l) != 4:
            raise Error('invalid parameter list')
        return klass.fromString('%d.%d.%d.%d' % (l[0], l[1], l[2], l[3]))
    fromIntegerList = classmethod(fromIntegerList)
    
    def toIntegerList(self):
        (a, b, c, d) = ((self.addr >> 24L) & 0xffL, (self.addr >> 16L) & 0xffL,
                        (self.addr >> 8L) & 0xffL, self.addr & 0xffL)
        return [a, b, c, d]

class _IPv4SubnetBase:
    addr = None
    cidr = CIDR_INVALID

    def __cmp__(self, other):
         if self.__class__ == other.__class__:
              return cmp((self.cidr, self.addr), (other.cidr, other.addr))
         else:
              return cmp(self.__class__, other.__class__)

    def validityChecks(self):
        if (self.cidr < CIDR_MIN) or (self.cidr > CIDR_MAX): raise InvalidSubnet()

    def fromString(klass, str):
        try:
            v = klass()
            (a, b) = re_ipv4_subnet.match(str).groups()
            v.addr = IPv4Address.fromString(a)
            v.cidr = long(b)
            v.validityChecks()
            return v
        except InvalidSubnet:
            raise
        except:
            raise InvalidIPAddress()
    fromString = classmethod(fromString)

    def fromStrings(klass, str1, str2):
        return klass.fromString('%s/%d' % (str1, mask_to_cidr(str2)))
    fromStrings = classmethod(fromStrings)
    
    def toString(self):
        return "%s/%d" % (self.addr.toString(), self.cidr)

    # XXX: other constructors (from longs, from address+cidr, etc)

    def getSubnet(self):
        # this is relevant e.g. for IPv4AddressSubnet, whose subnet
        # we may need
        return IPv4Subnet.fromString('%s/%d' % (self.getFirstAddress().toString(),
                                                self.getCidr()))
    
    def getAddress(self):
        return self.addr

    def getCidr(self):
        return self.cidr

    def getMask(self):
        return IPv4Address.fromLong(_cidr_to_mask_long(self.cidr))

    def getNetHostBits(self):
        mask = _cidr_to_mask_long(self.cidr)
        addr = self.addr.toLong()
        netbits = addr & mask
        hostbits = addr & ((~mask) & 0xffffffffL)
        return (netbits, hostbits)

    def getFirstAddress(self):
        (netbits, hostbits) = self.getNetHostBits()
        return IPv4Address.fromLong(netbits)

    def getLastAddress(self):
        (netbits, hostbits) = self.getNetHostBits()
        broadcast = (~_cidr_to_mask_long(self.cidr)) & 0xffffffffL
        return IPv4Address.fromLong(netbits + broadcast)

    def getFirstUsableAddress(self):
        if (self.cidr >= 31):
            return self.getFirstAddress()   # special case
        (netbits, hostbits) = self.getNetHostBits()
        return IPv4Address.fromLong(netbits + 1)

    def getLastUsableAddress(self):
        if (self.cidr >= 31):
            return self.getLastAddress()   # special case
        (netbits, hostbits) = self.getNetHostBits()
        broadcast = (~_cidr_to_mask_long(self.cidr)) & 0xffffffffL
        return IPv4Address.fromLong(netbits + broadcast - 1)

    def isUsable(self):
        if (self.cidr >= 31):
            return True  # special cases
        firstaddr = self.getFirstUsableAddress().toLong()
        lastaddr = self.getLastUsableAddress().toLong()
        addr = self.addr.toLong()
        return (addr >= firstaddr) and (addr <= lastaddr)

    def inSubnet(self, addr):
        (f, a, l) = (self.getFirstAddress().toLong(),
                     addr.toLong(),
                     self.getLastAddress().toLong())
        return (a >= f) and (a <= l)

    def overlapsWithSubnet(self, sub):
        of, ol = self.getFirstAddress().toLong(), self.getLastAddress().toLong()
        sf, sl = sub.getFirstAddress().toLong(), sub.getLastAddress().toLong()

        # ranges [of,ol] and [sf,sl] distict?
        if ol < sf:         #          [sf,sl]
            return False    # [of,ol]
        if of > sl:         #          [sf,sl]
            return False    #                  [of,ol]
        return True

class IPv4Subnet(_IPv4SubnetBase):
    """IPv4Subnet.

    >>> s = IPv4Subnet.fromString('10.0.0.0/8')
    >>> s.getAddress().toLong()
    167772160L
    >>> s.getCidr()
    8L
    >>> s.isUsable()
    False
    >>> a = s.getLastUsableAddress()
    >>> a.toString()
    '10.255.255.254'
    >>> s = IPv4Subnet.fromString('10.0.0.0/31')
    >>> s.isUsable()
    True
    >>> a = s.getFirstUsableAddress()
    >>> a.toString()
    '10.0.0.0'
    >>> s = IPv4Subnet.fromString('10.0.0.1/24')
    Traceback (most recent call last):
        ...
    InvalidIPAddress
    >>> s = IPv4Subnet.fromString('10.0.0.0/24xx')
    Traceback (most recent call last):
        ...
    InvalidIPAddress
    >>> s = IPv4Subnet.fromString('xx10.0.0.0/24')
    Traceback (most recent call last):
        ...
    InvalidIPAddress
    """
    def validityChecks(self):
        if (self.cidr < CIDR_MIN) or (self.cidr > CIDR_MAX): raise InvalidSubnet()
        (netbits, hostbits) = self.getNetHostBits()
        if hostbits != 0L: raise InvalidIPAddress()

class IPv4AddressSubnet(_IPv4SubnetBase):
    pass

class IPv4AddressRange:
    firstaddr = None
    lastaddr = None

    def __cmp__(self, other):
         if self.__class__ == other.__class__:
              return cmp((self.firstaddr, self.lastaddr), (other.firstaddr, other.lastaddr))
         else:
              return cmp(self.__class__, other.__class__)

    def fromString(klass, str):
        try:
            v = klass()
            (a, b) = re_ipv4_address_range.match(str).groups()
            v.firstaddr = IPv4Address.fromString(a)
            v.lastaddr = IPv4Address.fromString(b)
            if (v.lastaddr.toLong() < v.firstaddr.toLong()): raise InvalidIPAddressRange()
            return v
        except InvalidIPAddressRange:
            raise
        except:
            raise InvalidIPAddress()
    fromString = classmethod(fromString)

    def fromAddress(klass, first, last):
         r = klass.fromString('%s-%s' % (first.toString(), last.toString()))
         firstaddr = r.getFirstAddress()
         lastaddr = r.getLastAddress()
         return r
    fromAddress = classmethod(fromAddress)

    def toString(self):
        return "%s-%s" % (self.firstaddr.toString(), self.lastaddr.toString())

    def getFirstAddress(self):
        return self.firstaddr

    def getLastAddress(self):
        return self.lastaddr

    def inRange(self, addr):
        (f, a, l) = (self.firstaddr.toLong(), addr.toLong(), self.lastaddr.toLong())
        return (a >= f) and (a <= l)

    def size(self):
        return max(0, self.lastaddr.toLong() - self.firstaddr.toLong() + 1)


class Port:
    port = PORT_INVALID

    def __cmp__(self, other):
         if self.__class__ == other.__class__:
              return cmp(self.port, other.port)
         else:
              return cmp(self.__class__, other.__class__)

    def fromString(klass, str):
        try:
            a = long(re_port.match(str).group(1))
            if (a < PORT_MIN) or (a > PORT_MAX): raise Exception()
            v = klass()
            v.port = a
            return v
        except:
            raise InvalidPort()
    fromString = classmethod(fromString)

    def toString(self):
        return "%d" % self.port

    def fromLong(klass, l):
        if (l < PORT_MIN) or (l > PORT_MAX): raise InvalidPort()
        v = klass()
        v.port = l
        return v
    fromLong = classmethod(fromLong)

    def toLong(self):
        return self.port

class PortRange:
    firstport = None
    lastport = None

    def __cmp__(self, other):
         if self.__class__ == other.__class__:
              return cmp((self.firstport, self.lastport), (other.firstport, other.lastport))
         else:
              return cmp(self.__class__, other.__class__)

    def fromString(klass, str):
        try:
            v = klass()
            (a, b) = re_port_range.match(str).groups()
            v.firstport = Port.fromString(a)
            v.lastport = Port.fromString(b)
            if (v.lastport.toLong() < v.firstport.toLong()): raise InvalidPortRange()
            return v
        except InvalidPortRange:
            raise
        except:
            raise InvalidPort()
    fromString = classmethod(fromString)

    def toString(self):
        return "%s-%s" % (self.firstport.toString(), self.lastport.toString())

    def getFirstPort(self):
        return self.firstport

    def getLastPort(self):
        return self.lastport

    def inRange(self, port):
        (f, p, l) = (self.firstport.toLong(), port.toLong(), self.lastport.toLong())
        return (p >= f) and (p <= l)

# XXX: where to place these?  should be shared in several places?  datatypes?

_DATETIME_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z')
def parse_datetime_from_iso8601_subset(value):
    """Parse a datetime object from a strict subset of ISO 8601.

    See: http://en.wikipedia.org/wiki/ISO_8601.
    """

    m = _DATETIME_RE.match(value)
    if not m:
        raise Exception('Cannot get datetime from "%s".' % value)
    try:
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        hour = int(m.group(4))
        minute = int(m.group(5))
        second = int(m.group(6))
        if m.group(7) is not None:
            microsecond = int((m.group(7)+'000000')[:6])
        else:
            microsecond = 0
    except ValueError:
        raise Exception('Cannot get datetime from "%s".' % value)
    return datetime.datetime(year, month, day, hour, minute, second, microsecond)

def encode_datetime_to_iso8601_subset(value):
    """Encode a datetime into a ISO 8601 subset."""

    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            raise Exception('Cannot set datetime from non-naive %s.' % repr(value))
        return '%sZ' % value.isoformat()
    else:
        raise Exception('Cannot set datetime from %s.' % repr(value))

def encode_datetime_to_float(value):
    """Convert a datetime into a floating point UNIX timestamp.

    The timestamp will also contain microseconds from the datetime.
    """

    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            raise Exception('Cannot convert datetime from non-naive %s.' % repr(value))
        t = time.mktime(value.timetuple())  # this will be missing microseconds
        t += value.microsecond / 1000000.0
        return t
    else:
        raise Exception('Cannot convert datetime from %s.' % repr(value))

def parse_datetime_from_float(value):
    return datetime.datetime.utcfromtimestamp(value)

