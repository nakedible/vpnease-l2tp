"""Product license invoice computation helpers."""

import os
import sys
import gmpy

from twisted.internet import defer

from codebay.common import logger
from codebay.l2tpproductweb import checkeuvatid

_log = logger.get('l2tpproductweb.invoicing')

def compute_partner_discount_oct2007(monthly_inv_vat0):
    t = gmpy.mpq(monthly_inv_vat0)

    disc = gmpy.mpq(0)

    # cumulative discount is computed starting from highest
    # discount rate
    for [limit, percentage] in [ [ 10000, 30 ],
                                 [ 5000, 25 ],
                                 [ 2500, 20 ],
                                 [ 1000, 15 ],
                                 [ 500, 10 ] ]:
        excess = t - gmpy.mpq(limit)
        if excess > gmpy.mpq(0):
            disc += excess * gmpy.mpq(percentage) / gmpy.mpq(100)
            t = limit

    return disc

def compute_partner_discount_oct2007_float(monthly_inv_vat0):
    return float(compute_partner_discount_oct2007(monthly_inv_vat0))

def compute_license_price_oct2007(user_count, s2s_count):
    price = gmpy.mpq(0)

    if user_count > gmpy.mpq(100):
        price += gmpy.mpq(user_count) * gmpy.mpq(7)
    elif user_count > gmpy.mpq(10):
        price += gmpy.mpq(user_count) * gmpy.mpq(8)
    elif user_count >= gmpy.mpq(0):
        price += gmpy.mpq(user_count) * gmpy.mpq(9)
    else:
        raise Exception('negative user count')
    
    if s2s_count >= gmpy.mpq(0):
        price += gmpy.mpq(s2s_count) * gmpy.mpq(19)
    else:
        raise Exception('negative s2s count')

    return price

def compute_license_price_oct2007_float(user_count, s2s_count):
    return float(compute_license_price_oct2007(user_count, s2s_count))

class VatStatus:
    def __init__(self):
        self.vat_percent = None
        self.vat_status = None
        self.vat_marking = None
    
def determine_vat(country, in_eu, business_id, eu_vat_id):
    """See L2tpVatIssues for discussion.

    Note that country should not be used directly for anything at this point.
    For EU countries, we can detect the country reliably from the EU VAT ID
    (e.g. Finnish VAT IDs start with 'FI').  If there is no EU VAT ID, then
    the outcome is to use Finnish VAT anyway if otherwise within EU.
    """

    # Note: country is ignored now
    if country is None:
        raise Exception('VAT check failed, missing country')
    country = country.strip().lower()

    if business_id is not None:
        business_id = business_id.strip().lower()

    if eu_vat_id is not None:
        eu_vat_id = eu_vat_id.strip().lower()

    _vat_finland = 'Intangible service sales within Finland'
    _vat_non_eu = 'Export of intangible service outside of EU'
    _vat_eu_rev = 'Intangible service sales within EU, Reverse charge'
    _vat_eu_fin = 'Intangible service sales within EU, Finnish VAT added'

    # XXX: mutability hack
    vat_percent = [None]
    vat_status = [None]
    vat_marking = [None]

    def _get_result():
        if (vat_percent[0] is None) or (vat_status[0] is None) or (vat_marking[0] is None):
            raise Exception('VAT check failed, one or more values is missing')
        rv = VatStatus()
        rv.vat_percent = vat_percent[0]
        rv.vat_status = vat_status[0]
        rv.vat_marking = vat_marking[0]

        _log.info('VAT check: c=%s, eu=%s, bid=%s, vid=%s -> %d%%, %s, %s' % (country, in_eu, business_id, eu_vat_id,
                                                                              rv.vat_percent, rv.vat_status, rv.vat_marking))
        return rv
    
    def _got_vat(res):
        if res:
            if eu_vat_id.startswith('fi'):
                vat_percent[0] = 22
                vat_status[0] = 'Finnish VAT'
                vat_marking[0] = _vat_finland
            else:
                vat_percent[0] = 0
                vat_status[0] = 'EU, VAT ID OK'
                vat_marking[0] = _vat_eu_rev
            return None
        else:
            raise Exception('Cannot verify EU VAT ID: %s' % res)
        
    d = defer.Deferred()
    if in_eu:
        # EU countries (and Finland)
        if eu_vat_id is not None:
            # Have VAT ID, check it
            def _vat_check(res):
                _log.info('checking eu vat id: %s' % eu_vat_id)
                return checkeuvatid.check_eu_vat_id(eu_vat_id.strip().upper())  # deferred
            d.addCallback(_vat_check)
            d.addCallback(_got_vat)
        else:
            # No business ID, use full VAT
            vat_percent[0] = 22
            vat_status[0] = 'EU, no VAT ID'
            vat_marking[0] = _vat_eu_fin
    else:
        # Outside EU
        vat_percent[0] = 0
        vat_status[0] = 'Outside EU'
        vat_marking[0] = _vat_non_eu

    d.addCallback(lambda x: _get_result())
    d.callback(None)
    return d


# --------------------------------------------------------------------------

if __name__ == '__main__':
    fees = float(sys.argv[1])
    disc = compute_partner_discount_oct2007(fees)
    total = fees - disc
    print 'Partner discount (October 2007 rule) of %.4f euros is %.4f euros, total %.4f euros (VAT 0), %.4f (VAT 22)' % \
          (fees, disc, total, total*1.22)
