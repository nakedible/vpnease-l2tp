"""Random number and UUID generation.

This is not a high speed implementation.

@var minseedlen:
    Minimum random seed length.

@var seedfile:
    Random seed file.  Should be readable for all relevant users.
"""
__docformat__ = 'epytext en'

import time, os, hmac

from codebay.common.siteconfig import conf

conf.add('minseedlen', 16)
conf.add('seedfile', '/tmp/randomseed.bin') # XXX: this is bad location, but file required before /var/run/l2tpgw/ is initialized
_seedhmac = None

class Error(Exception):
    """RandomException"""

def initialize_seed():
    """Create seed file from /dev/random."""

    f = open('/dev/random', 'rb')
    seed = f.read(conf.minseedlen)
    f.close()

    f = open(conf.seedfile, 'wb')
    f.write(seed)
    f.close()

def _get_seed():
    """Initialize global HMAC instance."""
    
    global _seedhmac
    
    if _seedhmac is not None:
        return

    try:
        f = open(conf.seedfile, 'rb')
        seed = f.read()
        f.close()
    except IOError:
        #raise Error('Missing seed file %s' % seedfile)
        f = open('/dev/urandom', 'rb') # XXX: do we want this?
        seed = f.read(conf.minseedlen)
        f.close()

    if len(seed) < conf.minseedlen:
        raise Error('Seed file is too short (%d, minimum %d)' % (conf.minseedlen, len(seed)))

    timestamp = str(time.time())
    ourpid = str(os.getpid())

    # hmac key should more or less guarantee a unique stream
    key = seed + '\x00' + timestamp + '\x00' + ourpid
    _seedhmac = hmac.HMAC(key)
        
def random_byte():
    """Get one random byte as a single character string."""

    _get_seed()

    h = _seedhmac
    h.update('\x00')  # this will cumulate across calls
    t = h.digest()
    res = t[0]
    return res

def random_bytes(num):
    """Get many random bytes as a string."""
    
    t = ''
    for i in xrange(num):
        t += random_byte()
    return t

def random_int(n):
    """Get one random integer in the range [0, ..., n-1]."""
    t = 0L
    for i in xrange(16):
        t *= 256L
        t += long(ord(random_byte()))
    return t % n

def random_float():
    """Get one random float in the range [0.0, ..., 1.0[."""
    t = 0L  # < 2^64
    m = 1L  # grows to 2^64
    for i in xrange(8):
        t *= 256L
        m *= 256L
        t += long(ord(random_byte()))
    return float(t) / float(m)

def random_uuid():
    """Create a random UUID as specified in RFC 4122.

    See: http://www.rfc-editor.org/rfc/rfc4122.txt.
    """
    
    t = random_bytes(16)
    t1 = chr((ord(t[8]) | 0x80) & 0xbf)  # set bit 7, clear bit 6
    t2 = chr((ord(t[6]) & 0x0f) | 0x40)  # set four topmost bits to 4 (0b0100)
    t = t[0:6] + t2 + t[7] + t1 + t[9:16]
    
    hex = t.encode('hex')
    return hex[0:8] + '-' + hex[8:12] + '-' + hex[12:16] + '-' + hex[16:20] + '-' + hex[20:32]

def permute_list(x):
    """Permute a list randomly."""

    res = []
    while len(x) > 0:
        idx = random_int(len(x))
        res.append(x.pop(idx))
    return res
