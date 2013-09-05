"""Password generator.

Generates medium security passwords of configurable length.  The
character set used for passwords is minimal, consisting of digits
and ASCII alphabet, minus hard-to-distinguish characters (such as
zero, big O, etc).
"""

__docformat__ = 'epytext en'

from codebay.common import randutil

def _init_charset():
    _chars = '0123456789' + 'abcdefghijklmnopqrstuvwxyz' + 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

    # initialize chardict
    _chardict = {}
    for i in xrange(len(_chars)):
        t = _chars[i]
        _chardict[t] = ''

    # remove characters which are a bad idea
    for i in ['0', 'O', '5', 'S', '1', 'l', '2','Z', 'u', 'v', 'Q', 'G', '6']:
        del _chardict[i]

    return ''.join(_chardict.keys())

_chars = _init_charset()

def generate_password(length=8):
    """Generate a random password."""

    pw = ''
    for i in xrange(length):
        idx = int(randutil.random_float() * float(len(_chars)))
        if idx >= len(_chars):
            idex = len(_chars) - 1  # should never happen
        pw += _chars[idx]

    if len(pw) != length:
        raise Exception('internal error in generate_password: length does not match (%d != %d)' % (len(pw), length))

    return pw
