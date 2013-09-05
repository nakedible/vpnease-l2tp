#
#  SOAP-based EU VAT number checker, see:
#
#      http://ec.europa.eu/taxation_customs/vies/viesdisc.do
#
#  and Wiki page:
#
#      L2tpVatIssues
#

import os, sys, re

from twisted.web import soap

from codebay.common import logger

_log = logger.get('l2tpproductweb.checkeuvatid')

def split_eu_vat_id(vatid):
    # Remove internal and external whitespace
    t = ''
    for c in vatid.strip():
        if not (c in ' \t\n'):
            t += c
        
    r = re.compile(r'^(\D\D)(.*?)$')
    m = r.match(t)
    if m is not None:
        return m.group(1), m.group(2)
    raise Exception('invalid VAT ID: %s' % vatid)
    
def check_eu_vat_id(vatid):
    """Check an EU VAT ID string (of the form: FI01234567) and return True if
    it is currently valid.
    """

    from twisted.internet import defer

    def _success(res):
        vat_valid = False
        if hasattr(res, 'valid'):
            if res.valid == 1:
                return True
        return False

    def _failure(reason):
        _log.warning('Warning: VAT ID check failed, reason: %s' % reason)
        return False

    try:
        vat_cc, vat_no = split_eu_vat_id(vatid)

        # FIXME: should Proxy be reused???

        soap_uri = 'http://ec.europa.eu/taxation_customs/vies/api/checkVatPort'
        p = soap.Proxy(soap_uri)

        d = p.callRemote('checkVat', countryCode=vat_cc, vatNumber=vat_no)
        d.addCallbacks(_success, _failure)
        return d
    except:
        # XXX: we don't want to catch import failures at least...
        _log.exception('VAT ID check failed')
        return defer.succeed(False)

# --------------------------------------------------------------------------

if __name__ == '__main__':
    from twisted.internet import reactor

    if len(sys.argv) != 2:
        print 'Usage: python checkeuvatid.py <VAT ID, e.g. FI01234567>'
        sys.exit(1)

    vatid = sys.argv[1]

    def _done(res):
        if res:
            print 'EU VAT ID: "%s" is VALID' % vatid
        else:
            print 'EU VAT ID: "%s" is INVALID' % vatid
        reactor.stop()
        
    d = check_eu_vat_id(vatid)
    d.addCallback(_done)

    reactor.run()
