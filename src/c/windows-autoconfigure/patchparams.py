
import os

f = open('testmain', 'rb')
t = f.read()
f.close()

def _find_parameter_area(t):
    marker1 = '##### BEGIN PARAMETER BLOCK #####'
    marker2 = '##### END PARAMETER BLOCK #####'

    idx1 = t.find(marker1)
    idx2 = t.find(marker2)
    ridx1 = t.rfind(marker1)
    ridx2 = t.rfind(marker2)
    
    pbeg = None
    pend = None
    if (idx1 > 0) and (idx2 > 0):
        if (idx2 > idx1) and (idx1 == ridx1) and (idx2 == ridx2):
            pbeg = idx1 + len(marker1)
            pend = idx2
            plen = pend - pbeg
            if plen > 0:
                return pbeg, pend

    return None, None

def _inject_parameters(t, pbeg, pend, params):
    plen = pend - pbeg
    
    keys = params.keys()
    keys.sort()
    param_str = ''
    for k in keys:
        param_str += '%s\x00%s\x00' % (k, params[k])
    param_str += '\x00'

    param_len = len(param_str)
    if param_len > plen:
        raise Exception('parameters do not find into parameter area')

    new_t = t[:pbeg] + param_str + ('.' * (plen - param_len)) + t[pend:]
    return new_t

pbeg, pend = _find_parameter_area(t)
if pbeg is None or pend is None:
    print 'parameter block not found, not patching'

else:
    print 'parameter area is [%d,%d[ (%d bytes)' % (pbeg, pend, pend-pbeg)

    params = {'foo':'FOO',
              'bar':'BAARI',
              'quux':'QuuX'}

    t = _inject_parameters(t, pbeg, pend, params)

g = open('testmain-patched', 'wb')
g.write(t)
g.close()

