"""License management.

Customer licenses are simply managed as a list of CustomerLicense instances
read from a CSV file.  Demo licenses are stored in simple key-value encoded files.
"""
__docformat__ = 'epytext en'

import os, re, datetime, textwrap, md5
from codebay.common import datatypes
from codebay.common import logger
from codebay.common import licensekey
from codebay.l2tpadmin import dbaccess
from codebay.l2tpmanagementprotocol import managementprotocol
from codebay.l2tpmanagementserver import constants as msconstants

_log = logger.get('l2tpmanagementserver.licensemanager')

# FIXME
use_sql = False

class CustomerLicense:
    """Customer license data representation."""
    def __init__(self, license_key, validity_start, validity_end, license_string, user_count, s2s_count):
        self.license_key = unicode(license_key.upper())
        self.validity_start = validity_start
        self.validity_end = validity_end
        if license_string is None:
            self.license_string = unicode("Floating license")
        else:
            self.license_string = unicode(license_string)
        self.user_count = user_count
        self.site_to_site_count = s2s_count

    def __unicode__(self):
        return 'CustomerLicense[%s, %s, %s, %s, %s, %s]' % (self.license_key, self.license_string, self.validity_start, self.validity_end, self.user_count, self.site_to_site_count)
    
class DemoLicense:
    """Demo license data representation."""
    def __init__(self, license_key, grant_time, remote_address, remote_port, installation_uuid, cookie_uuid):
        self.license_key = license_key
        self.grant_time = grant_time
        self.remote_address = remote_address
        self.remote_port = remote_port
        self.installation_uuid = installation_uuid
        self.cookie_uuid = cookie_uuid

class LicenseManager:
    """Manage license related checks and computations."""

    def __init__(self, master):
        self.master = master  # XXX: unused

    def _parse_demo_license(self, license_key):
        re_keyval = re.compile(r'^(.*?)=(.*?)$')

        grant_time = None
        remote_address = None
        remote_port = None
        installation_uuid = None
        
        f = None
        try:
            try:
                fname = str(os.path.join(msconstants.DEMO_LICENSE_DIRECTORY, license_key))
                f = open(fname, 'rb')
                for line in f.readlines():
                    line = line.strip()
                    m = re_keyval.match(line)
                    if m is not None:
                        g = m.groups()
                        if len(g) == 2:
                            key, value = g[0], g[1]
                            if key == 'grant-time':
                                grant_time = datatypes.parse_datetime_from_iso8601_subset(value)
                            elif key == 'remote-address':
                                remote_address = datatypes.IPv4Address.fromString(value)
                            elif key == 'remote-port':
                                remote_port = int(value)
                            elif key == 'installation-uuid':
                                installation_uuid = str(value)
                            else:
                                _log.warning('skipping demo license key-value pair: %s=%s' % (key,value))
            except IOError:
                # eat error
                pass
            except:
                _log.exception('failed in parsing demo license file for license key %s' % license_key)
                raise
        finally:
            if f is not None:
                f.close()

        if (grant_time is not None) and (remote_address is not None) and (remote_port is not None) and (installation_uuid is not None):
            return DemoLicense(license_key, grant_time, remote_address, remote_port, installation_uuid, None)
        else:
            return None

    def _parse_demo_licenses(self):
        res = {}
        for license_key in os.listdir(msconstants.DEMO_LICENSE_DIRECTORY):
            try:
                tmp = self._parse_demo_license(license_key)
                res[license_key] = tmp
            except:
                _log.exception('failed in parsing demo license %s' % license_key)
        return res
    
    # FIXME: uses file, nuke later
    def get_demo_licenses(self):
        return self._parse_demo_licenses().values()
        
    # FIXME: nuke file part later
    def get_demo_license(self, license_key):
        if use_sql:
            try:
                da = dbaccess.get_database_accessor()
                lk = da.find_license_key(license_key=license_key)
                if lk is None:
                    return None
                if not lk.is_enabled:
                    return None
                if not lk.is_demo_license:
                    return None

                # XXX: separate CustomerLicense and DemoLicense objects are a hassle at this point?
                return DemoLicense(lk.license_key,
                                   lk.validity_start,
                                   datatypes.IPv4Address.fromString(lk.demo_remote_address),
                                   lk.demo_remote_port,
                                   lk.demo_installation_uuid,
                                   lk.demo_cookie_uuid)
            except:
                _log.exception('failed when looking for license key %s' % license_key)
            return None                
        else:
            return self._parse_demo_license(license_key)

    # FIXME: nuke file part later
    def get_customer_license_information(self, license_key):
        if use_sql:
            try:
                da = dbaccess.get_database_accessor()
                lk = da.find_license_key(license_key=license_key)
                if lk is None:
                    return None
                if not lk.is_enabled:
                    return None
                if lk.is_demo_license:
                    return None
                return CustomerLicense(lk.license_key,
                                       lk.validity_start,
                                       lk.validity_end,
                                       lk.license_string,
                                       lk.limit_normal_user_connections,
                                       lk.limit_site_to_site_connections)
            except:
                _log.exception('failed when looking for license key %s' % license_key)
            return None                
        else:
            for lic in get_customer_licenses():
                try:
                    if lic.license_key == license_key:
                        return lic
                except:
                    _log.exception('failed to process license %s, skipping' % lic)
            return None
    
    def _compute_temporary_validity_period(self, customer_validity_start, customer_validity_end):
        # Compute validity time and recheck time
        #
        # Actual validity delivered to the client here is a synthesis of database imposed
        # start and end time, and the "comfort" period we want to assign for validity
        # re-checking.  The protocol client never knows where the validity limits actually
        # come from.  For instance, if a license is cancelled, it may become valid by the
        # end of next month.  This causes the next validity period computation to take
        # this into account.
        #
        # Recheck time is intended to ensure that the client rechecks the validity
        # periodically, and will cause the client to obey the new "snapshot" values.
        # However, if the management server is down, the validity period delivered
        # earlier will remain valid in the client - hence the validity period should
        # probably extend at least one week further than current timestamp, unless
        # license validity ends.  Even in that case there has to be some slack if the
        # administrator has extended the license (reactivated after cancellation) and
        # the management server just happens to be down.
        #
        # This complicated logic is below.
        
        _log.debug('determining license validity and recheck time')

        now = datetime.datetime.utcnow()
        validity_start = now
        validity_end = now + msconstants.LICENSE_MAX_VALIDITY
        recheck_time = now + msconstants.LICENSE_RECHECK_DEFAULT

        _log.debug('step 1: start=%s end=%s recheck=%s' % (validity_start.isoformat(), validity_end.isoformat(), recheck_time.isoformat()))

        # allow None for customer_validity_{start,end}
        if customer_validity_start is None:
            customer_validity_start = validity_start
        if customer_validity_end is None:
            customer_validity_end = validity_end

        # license in validity period?
        license_in_validity_period = (now >= customer_validity_start) and (now <= customer_validity_end)

        # license validity start
        if customer_validity_start > validity_start:
            validity_start = customer_validity_start

        # license validity end
        if customer_validity_end < validity_end:
            validity_end = customer_validity_end

        # sanity
        if validity_start > validity_end:
            validity_start = validity_end

        _log.debug('step 2: start=%s end=%s recheck=%s' % (validity_start.isoformat(), validity_end.isoformat(), recheck_time.isoformat()))

        # compute current validity period (with respect to *current* time)
        validity_time = validity_end - now

        _log.debug('validity_time initially %s' % validity_time)

        # ensure that at least a minimum validity period exists, recompute end time
        if validity_time < msconstants.LICENSE_MIN_VALIDITY:
            _log.debug('validity_time too short, clamping')
            validity_time = msconstants.LICENSE_MIN_VALIDITY
            validity_end = now + validity_time
            
        _log.debug('validity_time now %s' % validity_time)
                
        _log.debug('step 3: start=%s end=%s recheck=%s' % (validity_start.isoformat(), validity_end.isoformat(), recheck_time.isoformat()))

        # determine recheck time
        if validity_start > now:
            # license becomes valid in the future
            _log.debug('license becomes valid in the future, quick recheck')
            recheck_time = now + msconstants.LICENSE_RECHECK_QUICK  # FIXME??? interval dependent???
        elif now > validity_end:
            # license is invalid
            _log.debug('license is already invalid, quick recheck')
            recheck_time = now + msconstants.LICENSE_RECHECK_QUICK  # FIXME??? interval dependent???
        else:
            # license is valid, check daily or more frequently if expiring soon
            if validity_time < msconstants.LICENSE_MAX_VALIDITY:
                _log.debug('license is valid and validity is short, quick recheck')
                recheck_time = now + msconstants.LICENSE_RECHECK_QUICK
            else:
                _log.debug('license is valid and validity is long, default recheck')
                recheck_time = now + msconstants.LICENSE_RECHECK_DEFAULT

        _log.debug('step 4: start=%s end=%s recheck=%s' % (validity_start.isoformat(), validity_end.isoformat(), recheck_time.isoformat()))

        # add leeway to validity to cover time differences
        validity_start = validity_start - msconstants.LICENSE_VALIDITY_START_LEEWAY
        validity_end = validity_end + msconstants.LICENSE_VALIDITY_END_LEEWAY

        # now done
        _log.debug('step 5 (done): start=%s end=%s recheck=%s' % (validity_start.isoformat(), validity_end.isoformat(), recheck_time.isoformat()))

        return license_in_validity_period, validity_start, validity_end, recheck_time
    
    def _fill_in_unknown_license(self, res, now):
        res['licenseMaxRemoteAccessConnections'] = 0
        res['licenseMaxSiteToSiteConnections'] = 0
        res['licenseValidityStart'] = now
        res['licenseValidityEnd'] = now
        res['licenseRecheckLatestAt'] = now + msconstants.LICENSE_RECHECK_QUICK
        res['licenseString'] = u''
        res['licenseStatus'] = u'UNKNOWN'
        res['isDemoLicense'] = False
        res['demoValidityStart'] = now
        res['demoValidityEnd'] = now

    def license_lookup(self, res, arg_licenseKey):
        now = datetime.datetime.utcnow()

        # anonymous license?
        if arg_licenseKey == '':
            # empty license key is anonymous
            self._fill_in_unknown_license(res, now)
            return

        # non-anonymous; check syntax first
        try:
            _log.debug('checking license syntax for: %s' % arg_licenseKey)
            ign = str(arg_licenseKey)  # check that no Unicode chars
            (val, broken) = licensekey.decode_license(arg_licenseKey)
            _log.debug('=> result %s, %s' % (val, broken))
            if val is None:
                raise Exception('one or more groups broken')
        except:  # FIXME: wide...
            _log.error('invalid license key: %s' % arg_licenseKey)
            raise managementprotocol.InvalidLicenseError('Invalid license key: %s' % str(arg_licenseKey))
        
        # check for a demo license
        dlic = None
        try:
            dlic = self.get_demo_license(arg_licenseKey)
        except:
            _log.exception('failed to get demo license info')

        # check for a customer license?
        clic = None
        try:
            clic = self.get_customer_license_information(arg_licenseKey)
        except:
            _log.exception('failed to get customer license info')

        # get basic license parameters before validity time computation
        _log.debug('clic=%s, dlic=%s' % (clic, dlic))
        if clic is not None:
            _log.info('found a full customer license for %s' % arg_licenseKey)
            is_demo = False
            customer_validity_start = clic.validity_start
            customer_validity_end = clic.validity_end
            demo_validity_start = now
            demo_validity_end = now
            user_count = clic.user_count
            s2s_count = clic.site_to_site_count
            license_string = clic.license_string
        elif dlic is not None:
            _log.info('found a demo license')
            is_demo = True
            customer_validity_start = dlic.grant_time
            customer_validity_end = customer_validity_start + msconstants.DEMO_LICENSE_TIME
            demo_validity_start = customer_validity_start
            demo_validity_end = customer_validity_end
            user_count = msconstants.DEMO_LICENSE_USER_COUNT
            s2s_count = msconstants.DEMO_LICENSE_SITE_TO_SITE_COUNT
            license_string = 'Demo license'
        else:
            _log.warning('no license info found for license key %s, returning unknown' % arg_licenseKey)
            self._fill_in_unknown_license(res, now)
            return
        
        # compute temporary validity and recheck time, i.e. time that server
        # can operate withouch rechecking
        license_in_validity_period, validity_start, validity_end, recheck_time = self._compute_temporary_validity_period(customer_validity_start, customer_validity_end)

        # license status
        if license_in_validity_period:
            license_status = u'VALID'
        else:
            # FIXME: license is valid even if it has been expired... ???
            license_status = u'DISABLED'
        
        # license parameters are now ready
        res['licenseMaxRemoteAccessConnections'] = user_count
        res['licenseMaxSiteToSiteConnections'] = s2s_count
        res['licenseValidityStart'] = validity_start
        res['licenseValidityEnd'] = validity_end
        res['licenseRecheckLatestAt'] = recheck_time
        res['licenseString'] = license_string
        res['licenseStatus'] = license_status
        res['isDemoLicense'] = is_demo
        res['demoValidityStart'] = demo_validity_start
        res['demoValidityEnd'] = demo_validity_end

    # FIXME: file based now
    def create_new_demo_license(self, remote_address, remote_port, installation_uuid):
        key = str(licensekey.create_random_license())
        grant_time = datetime.datetime.utcnow()
        f = None
        try:
            f = open(str(os.path.join(msconstants.DEMO_LICENSE_DIRECTORY, key)), 'wb')
            f.write(textwrap.dedent("""\
            grant-time=%s
            remote-address=%s
            remote-port=%s
            installation-uuid=%s
            """ % (datatypes.encode_datetime_to_iso8601_subset(grant_time),
                   remote_address.toString(),
                   str(remote_port),
                   installation_uuid
                   )))
        finally:
            if f is not None:
                f.close()
        return key

    # FIXME: file based now
    def check_existing_demo_license(self, remote_address, remote_port, installation_uuid):
        demo_licenses = self._parse_demo_licenses()   # XXX: slow operation
        for license_key in demo_licenses.keys():
            lic = demo_licenses[license_key]
            if lic.installation_uuid == installation_uuid:
                return license_key
        return None

    def detect_test_license_request_abuse(self):
        # Abuse detection.
        #
        # What we're trying to detect here is repeated test license requests from
        # the same source.  This is done at various levels of paranoia:
        #
        #   1. If a test license has been allocated to a particular installation
        #      UUID, return the same test license always.
        #
        #   2. If the installation UUID is new, but there is a previous license
        #      from this remote IP address, return the same test license.
        #
        # FIXME: lenience? allow N fresh test licenses per IP?
        #
        # Installation UUID and possibly other information is assumed to come from
        # an earlier Identify exchange.

        # FIXME
        return False

# --------------------------------------------------------------------------

# XXX: IP restrictions?

_customer_licenses = None
_customer_license_last_read = None
_re_date = re.compile(r'^(\d\d\d\d)-(\d\d)-(\d\d)$')

def _parse_csv(f):            
    import csv

    # XXX: UTC?
    def _parse_date(x):   # 2008-05-01
        if x in ['ANY', '']:
            return None
        grp = _re_date.match(x).groups()
        return datetime.datetime(int(grp[0]), int(grp[1]), int(grp[2]))

    # dummy date used for disabled licenses
    inv_date = datetime.datetime(1980, 1, 1)

    res = []
    
    reader = csv.reader(f)
    for row in reader:
        try:
            if len(row) < 7:
                continue

            decrow = []
            for i in xrange(len(row)):
                decrow.append(row[i].decode('utf-8').strip())

            lkey = decrow[0]
            if len(lkey) != (5*5 + 4):
                continue
        
            try:
                (val, broken) = licensekey.decode_license(lkey)
                if val is None:
                    raise Exception('invalid license key')
            except:
                _log.warning('skipping invalid license key: %s, row: %s' % (lkey, repr(decrow)))
                continue

            # process row
            lkey = decrow[0].upper()
            lstr = decrow[1]
            lstatus = decrow[2].upper()

            if lstr == '':
                pass
            if lstatus == '':
                raise Exception('invalid license status')
            if not (lstatus in ['FLOATING', 'ACTIVE', 'DISABLED']):
                raise Exception('invalid license status: %s' % lstatus)

            if lstatus == 'FLOATING':
                lvalidfrom = None
                lvalidto = None
                lusers = 100
                ls2s = 100
                lstr = 'Floating license'
            elif lstatus == 'DISABLED':
                lvalidfrom = inv_date
                lvalidto = inv_date
                lusers = 0
                ls2s = 0
                lstr = 'Disabled'
            elif lstatus == 'ACTIVE':
                lvalidfrom = _parse_date(decrow[3])
                lvalidto = _parse_date(decrow[4])
                lusers = int(decrow[5])
                ls2s = int(decrow[6])
            else:
                raise Exception('invalid status for license, did not expect to get here')

            res.append(CustomerLicense(lkey, lvalidfrom, lvalidto, lstr, lusers, ls2s))
        except:
            _log.exception('failed to process license csv row: %s' % repr(row))

    return res

def _get_csv_licenses(fname):
    f = None
    try:
        f = open(fname, 'rb')
        return _parse_csv(f)
    finally:
        if f is not None:
            f.close()
            f = None
    
# XXX: unclean interfaces now, master uses this to detect changes
def get_customer_license_csv_md5():
    f = None
    try:
        f = open(msconstants.LICENSE_CSV_FILE, 'rb')
        return md5.md5(f.read()).digest().encode('hex')
    finally:
        if f is not None:
            f.close()
            f = None

# XXX: unclean API
def force_customer_license_reread():
    global _customer_licenses
    _customer_licenses = None
    
def get_customer_licenses():
    """Get customer licenses, re-reading from disk if necessary."""
    
    global _customer_licenses
    global _customer_license_last_read

    now = datetime.datetime.utcnow()
    reread = False
    reread_limit = 5*60  # 5 min
    
    if _customer_licenses is None:
        reread = True
    elif _customer_license_last_read is None:
        reread = True
    else:
        diff = now - _customer_license_last_read
        if (diff < datetime.timedelta(0, 0, 0)) or (diff > datetime.timedelta(0, reread_limit, 0)):
            reread = True
        else:
            reread = False
        
    if reread:
        _customer_license_last_read = now
        
        t = _get_csv_licenses(msconstants.LICENSE_CSV_FILE)
        
        # sanity
        chk = {}
        for i in t:
            if chk.has_key(i.license_key):
                raise Exception('duplicate license key: %s' % i.license_key)
            chk[i.license_key] = True

        # write to /tmp for debugging
        f = None
        try:
            f = open('/tmp/active-licenses.txt', 'wb')
            for i in t:
                f.write('%s\n' % unicode(i).encode('utf-8'))
        finally:
            if f is not None:
                f.close()
                f = None
        
        _customer_licenses = t
    
    return _customer_licenses

def get_demo_licenses():
    lm = LicenseManager(None)
    return lm.get_demo_licenses()
