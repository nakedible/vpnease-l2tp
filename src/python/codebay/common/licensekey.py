"""Common code for handling 5x5 character license keys.

License keys contain 90 bits of raw information, encoded in five
groups of 18 bits each.  Each bit contains four characters of
actual data (total 18 bits, see below) and one check character.
Errors in individual groups are almost always detected.

The encoding uses 23 characters defined in the _chars variable.
The 18-bit value (0...262143) is encoded modulo 23 in "big endian"
order.  Let v be the 18-bit value.  We find constants a, b, c, d
each in the range 0...22, which satisfy:

   v = a*(23^3) + b*(23^2) + c*(23^1) + d

This is always possible because we can express integers in the
range 0...23^4-1 = 0...279840 using this convention.  Finally,
we compute the check character, e, as:

   e = (a * C1) + (b * C2) + (c * C3) + (d * C4) + C5 mod 23

Here the only important thing really is that the multipliers
should satisfy gcd(x,23)=1 for x in {C1, C2, C3, C4, C5}.
This is trivially the case because 23 is a prime.  We select
constants as {3, 5, 7, 11, 13}.

The five-character group then becomes <a,b,c,d,e>, where each
characters is encoded through the _chars table.

Example:

>>> from codebay.common import licensekey
>>> licensekey.encode_license(12345678901234567890L)
'AAAAT-ABJ3H-J89W3-YMCMW-XL7VF'
>>> licensekey.decode_license('AAAAT-ABJ3H-J89W3-YMCMW-XL7VF')
(12345678901234567890L, [])
>>> licensekey.decode_license('AAAAT-ACJ3H-J81W3-YMCMW-ZL7VF')
(None, [1, 2, 4])
"""
__docformat__ = 'epytext en'

from codebay.common import randutil

_chars = 'ABCEFHJKLMNPRTVWXY34789'
_char_min = 0
_char_max = len(_chars) - 1
_C = [3, 5, 7, 11, 13]

def _char_to_int(ch):
    for i in xrange(_char_min, _char_max+1):
        if _chars[i] == ch:
            return i
    raise Exception('Invalid character: %s' % ch)

def _int_to_char(i):
    if (i < _char_min) or (i > _char_max):
        raise Exception('Invalid integer: %s' % i)
    return _chars[i]

def _encode_group(v):
    if (v < 0) or (v >= 262144):
        raise Exception('Invalid value: %s' % v)

    m = len(_chars)
    t = v

    d, t = t % m, t / m
    c, t = t % m, t / m
    b, t = t % m, t / m
    a, t = t % m, t / m
    e = ((a * _C[0]) + (b * _C[1]) + (c * _C[2]) + (d * _C[3]) + _C[4]) % m

    if t != 0:
        raise Exception('Invalid input value: %s' % v)

    res = []
    for i in (a, b, c, d, e):
        res.append(_int_to_char(i))
    return ''.join(res)

def _decode_group(s):
    if len(s) != 5:
        raise Exception('Invalid group: %s' % s)
    
    s = s.upper()
    t = []
    for i in (s[0], s[1], s[2], s[3], s[4]):
        t.append(_char_to_int(i))
    a, b, c, d, e = t[0], t[1], t[2], t[3], t[4]
    
    m = len(_chars)
    v = (a*m*m*m) + (b*m*m) + (c*m) + (d)
    check = ((a * _C[0]) + (b * _C[1]) + (c * _C[2]) + (d * _C[3]) + _C[4]) % m

    if check != e:
        raise Exception('Decoding failed (check character does not match)')

    return v

def _exhaustive_group_test():
    for i in xrange(262144):
        t1 = _encode_group(i)
        t2 = _decode_group(t1)
        if (t2 != i):
            raise Exception('Exhaustive test failed at i=%s' % i)

def _encode_license_long(v):
    m = 262144L  # 2^18
    t = long(v)

    g1, t = t % m, t / m
    g2, t = t % m, t / m
    g3, t = t % m, t / m
    g4, t = t % m, t / m
    g5, t = t % m, t / m

    if t != 0:
        raise Exception('Invalid value: %s' % v)

    return [_encode_group(g5),
            _encode_group(g4),
            _encode_group(g3),
            _encode_group(g2),
            _encode_group(g1)]

def _random_license_long():
    from codebay.common import randutil

    res = 0L
    m = 262144L
    for i in xrange(5):
        res = (res * m) + long(randutil.random_float() * 262144L)
    return res

def _string_to_long(v):
    t = 0L
    for i in xrange(len(v)):
        ch = ord(v[i])
        t = t*256L + ch
    return t

def _long_to_string(l, num):
    res = []

    m = 256L
    t = l
    for i in xrange(num):
        a, t = t % m, t / m
        res.append(chr(a))
    res.reverse()
    return ''.join(res)

def encode_license(v):
    """Encode a 90-bit value into a license key.

    The input 'v' may be either a (long) integer, or a Python string
    (at most 12 characters long) which is interpreted as an 8-bit big
    endian integer.
    """

    licval = None
    if isinstance(v, (int, long)):
        licval = long(v)
    elif isinstance(v, (str,)):
        licval = _string_to_long(v)
    else:
        raise Exception('Invalid input: %s' % v)

    groups = _encode_license_long(licval)
    return '-'.join(groups)

def decode_license(s, output='long'):
   """Decode a license string of the form 'XXXXX-XXXXX-XXXXX-XXXXX-XXXXX'

   Output is a pair: (value, broken_groups).  Value is a long integer
   containing the license 90-bit value.  By setting output='string',
   the output changes into an 8-bit string of 12 characters, interpreted
   as a big endian integer.

   In case the license key contains five groups separated by dashes,
   but one or more of the groups are broken, the broken_groups return
   value is an array of group indices, indicating which groups are broken.
   The indices are 0...4, 0 being the first, 4 being the last.  In
   this case the output value is None.

   If the license is broken beyond repair, an Exception is thrown.
   """

   groups = s.split('-')
   if len(groups) != 5:
       raise Exception('Invalid license key: %s' % s)

   broken = []
   res = 0L
   m = 262144L
   
   for i in xrange(len(groups)):
       if len(groups[i]) != 5:
           broken.append(i)
           continue

       # this is meaningless if any groups are broken, but we catch this at the end
       try:
           tmp = _decode_group(groups[i])
           res = (res * m) + tmp
       except:
           broken.append(i)
           continue

       # all ok

   if len(broken) > 0:
       return None, broken

   if output == 'long':
       return res, []
   elif output == 'string':
       return _long_to_string(res, 12), []
   else:
       raise Exception('Unknown output type: %s' % output)

def create_random_license():
    """Create a random license key.

    Be careful: you'll want to check that the license key is indeed
    unique (for instance, if it is a database key).
    """

    t = _string_to_long(randutil.random_bytes(32))
    t = t % (2L**90L)
    return encode_license(t)
                        
    
