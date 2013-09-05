"""L2TP specific helpers."""
__docformat__ = 'epytext en'

import re, os, datetime, time, fcntl, tempfile

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.common import randutil
from codebay.common import helpers as common_helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import db
from codebay.l2tpserver import versioninfo

run_command = runcommand.run_command
_log = logger.get('l2tpserver.helpers')

def get_debug(cfg):
    if get_debug_heavy(cfg):
        return True

    if not cfg.hasS(ns.debug):
        return False

    debug = cfg.getS(ns.debug)
    if debug.hasType(ns.DebugNone):
        return False
    elif debug.hasType(ns.DebugNormal):
        return True
    else:
        raise Exception('unexpected debug level')

def get_debug_heavy(cfg):
    if not cfg.hasS(ns.debug):
        return False

    debug = cfg.getS(ns.debug)
    if debug.hasType(ns.DebugHeavy):
        return True
    return False

def get_debug_level_string(cfg):
    if not cfg.hasS(ns.debug):
        return 'none'

    debug = cfg.getS(ns.debug)
    if debug.hasType(ns.DebugNone):
        return 'none'
    elif debug.hasType(ns.DebugNormal):
        return 'normal'
    elif debug.hasType(ns.DebugHeavy):
        return 'heavy'
    else:
        raise Exception('unexpected debug level')
    
def priv_iface_exists(cfg):
    (priv_iface, _) = get_private_iface(cfg)
    if priv_iface is not None:
        return True
    return False

def get_dyndns_config(cfg):
    ret = None
    (pub_iface, _) = get_public_iface(cfg)
    if pub_iface.hasS(ns.dynamicDnsConfig):
        ret = pub_iface.getS(ns.dynamicDnsConfig, rdf.Type(ns.DynamicDnsConfig))
    return ret

def get_qos_config(cfg):
    net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
    return net_cfg.getS(ns.qosConfig, rdf.Type(ns.QosConfig))

def get_iface_name(iface):
    if iface is None: return None
    return iface.getS(ns.interfaceName, rdf.String)

def get_public_iface(cfg):
    net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
    pub_iface = net_cfg.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
    return pub_iface, get_iface_name(pub_iface)

def get_private_iface(cfg):
    net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
    if net_cfg.hasS(ns.privateInterface):
        priv_iface = net_cfg.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
        return priv_iface, get_iface_name(priv_iface)
    else:
        return None, None

def get_ifaces(cfg):
    return get_public_iface(cfg), get_private_iface(cfg)

def get_iface_mtus(cfg):
    (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = get_ifaces(cfg)
    pub_mtu, priv_mtu = None, None
    if pub_iface is not None:
        pub_mtu = pub_iface.getS(ns.mtu, rdf.Integer)
    if priv_iface is not None:
        priv_mtu = priv_iface.getS(ns.mtu, rdf.Integer)
    return pub_mtu, priv_mtu

def get_proxyarp_iface(cfg):
    """Internal helper to get proxy ARP interface info from L2TP network configuration root."""

    ret = (None, None)
    (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = get_ifaces(cfg)
    if priv_iface is not None:
        if priv_iface.getS(ns.proxyArp, rdf.Boolean):
            ret = (priv_iface, priv_iface_name)

    if pub_iface.getS(ns.proxyArp, rdf.Boolean):
        if ret[0] is not None:
            raise Exception('proxyarp defined for both public and private interfaces.')
        ret = (pub_iface, pub_iface_name)

    return ret

def is_nat_interface(iface):
    if iface is not None:
        return iface.getS(ns.nat, rdf.Boolean)
    return False

def is_private_nat(cfg):
    return is_nat_interface(get_private_iface(cfg)[0])

def is_public_nat(cfg):
    return is_nat_interface(get_public_iface(cfg)[0])

def is_client_routing(cfg):
    net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
    return net_cfg.getS(ns.clientToClientRouting, rdf.Boolean)

def is_dhcp_interface(iface):
    if iface is not None:
        addr = iface.getS(ns.address)
        if addr.hasType(ns.DhcpAddress):
            return True
    return False

def get_public_dhcp_interface(cfg):
    (pub_iface, _) = get_public_iface(cfg)
    if is_dhcp_interface(pub_iface): return pub_iface
    return None

def get_private_dhcp_interface(cfg):
    (priv_iface, _) = get_private_iface(cfg)
    if priv_iface is not None and  is_dhcp_interface(priv_iface): return priv_iface
    return None

def write_file(dest, contents, append=False, perms=0755):
    common_helpers.write_file(dest, contents, append=append, perms=perms)

_re_host_output = re.compile(r'^.*?\s+(A|has\saddress)\s+(.*?)\s*$')

def dns_resolve_host(hostname):
    """Resolve DNS name using 'host' command.

    Return a list of addresses (A) entries, in the order returned by the
    server, eg. randomized or round robin.

    If 'hostname' is an IPv4 address in dotted decimal notation, returns
    a single element list containing just that address.
    """

    _log.debug('dns_resolve_host: %s' % hostname)

    try:
        addr = datatypes.IPv4Address.fromString(hostname)
        _log.debug('dns_resolve_host: IPv4 address, returning directly')
        return [addr]
    except:
        _log.debug('dns_resolve_host: not an IPv4 address')

    [rv, stdout, stderr] = run_command([constants.CMD_HOST, '-t', 'A', hostname])
    _log.debug('dns_resolve_host: retval=%s' % rv)

    res = []
    for l in stdout.split('\n'):
        m = _re_host_output.match(l)
        if m is not None:
            addrstr = m.group(2)
            _log.debug('match: %s' % addrstr)

            addr = None
            try:
                addr = datatypes.IPv4Address.fromString(addrstr)
            except:
                _log.debug('failed to parse address: %s' % addrstr)

            if addr is not None:
                res.append(addr)

    return res

def get_db_root():
    return db.get_db().getRoot()

def get_config():
    """Get protocol configuration root node from RDF database."""

    return db.get_db().getRoot().getS(ns.l2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))

def get_new_config():
    """Get new protocol configuration root node from RDF database."""

    return db.get_db().getRoot().getS(ns.newL2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))

def get_status():
    """Get protocol status root node from RDF database."""
    
    return db.get_db().getRoot().getS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))

def get_global_status():
    """Get global status root node from RDF database."""
    
    return db.get_db().getRoot().getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))

def get_ui_config():
    """Get UI config node from RDF database."""

    return db.get_db().getRoot().getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))

def get_new_ui_config():
    """Get new UI config node from RDF database."""

    return db.get_db().getRoot().getS(ns_ui.newUiConfig, rdf.Type(ns_ui.UiConfig))

def get_license_info():
    """Get license information node from RDF database."""

    return db.get_db().getRoot().getS(ns_ui.licenseInfo, rdf.Type(ns_ui.LicenseInfo))

def get_ppp_devices():
    return get_status().getS(ns.pppDevices, rdf.Type(ns.PppDevices)).getSet(ns.pppDevice, rdf.Type(ns.PppDevice))

def get_retired_ppp_devices():
    return get_global_status().getS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices)).getSet(ns.pppDevice, rdf.Type(ns.PppDevice))

def dump_to_file_using_rdfdumper(rdf_node, filename):
    f = None
    try:
        from codebay.l2tpserver import rdfdumper
        rd = rdfdumper.RdfDumper()
        tmp = rd.dump_resource(rdf_node)
        f = open(filename, 'wb')
        f.write(tmp)
        f.close()
        f = None
    except:
        _log.exception('cannot dump %s to %s' % (rdf_node, filename))

    try:
        if f is not None:
            f.close()
            f = None
    except:
        _log.exception('failed to close file')

def host_is_vmware():
    """Return True if host is running VMware."""
    [rv, stdout, stderr] = run_command([constants.CMD_LSPCI], retval=runcommand.FAIL)
    r = re.compile(r'^.*?vmware.*?$')
    for l in stdout.split('\n'):
        t = l.lower()
        if r.match(t):
            return True
    return False

def host_is_virtualpc():
    """Return True if host is running Virtual PC."""
    # XXX: implement when required
    raise Exception('unimplemented')

def reboot_host(reason):
    """Reboot the host, writing 'reason' to log and console.

    Returns immediately but reboot is processed in the background.
    """
    
    if reason is None:
        reason = '(unspecified reason)'

    [rv, stdout, stderr] = run_command([constants.CMD_SHUTDOWN, '-r', 'now', reason], retval=runcommand.FAIL)

def is_live_cd():
    return check_marker_file(constants.LIVECD_MARKER_FILE)

def is_lowmem():
    return check_marker_file(constants.LOWMEM_MARKER_FILE)

def check_marker_file(fname):
    """Return True if marker file exists, otherwise return False."""
    ret = True
    try:
        open(fname, 'rb').close()
    except:
        ret = False
    return ret

def read_and_strip_file(fname):
    f = None
    try:
        f = open(fname, 'rb')
        t = f.read()
        t = t.strip()
        f.close()
        return t
    except:
        if f is not None:
            f.close()
        return None
    
def get_installation_uuid():
    return read_and_strip_file(constants.INSTALLATION_UUID)

def get_boot_uuid():
    return read_and_strip_file(constants.BOOT_UUID)

def get_cookie_uuid():
    return read_and_strip_file(constants.COOKIE_UUID)

# XXX: store cookie UUID in RDF or file?  how does RDF work with export/import?
def write_cookie_uuid(cookie_uuid):
    f = None
    try:
        f = open(constants.COOKIE_UUID, 'wb')
        f.write('%s\n' % cookie_uuid.strip())
    except:
        _log.exception('failed to write cookie uuid')

    if f is not None:
        f.close()

def _generate_signed_certificate(in_ca_privkey, in_ca_certificate, in_ca_serialfile, out_privkey, out_cert, nbits=1024, common_name=None, organization=None):
    _log.info('generating signed certificate: ca_privkey=%s, ca_cert=%s, ca_serialefile=%s privkey=%s, cert=%s, nbits=%s' % (in_ca_privkey, in_ca_certificate, in_ca_serialfile, out_privkey, out_cert, nbits))

    # NB: certificate nbits > 1024 causes problems with some browsers (folklore)

    # delete old files just in case
    try:
        os.unlink(out_privkey)
    except:
        pass
    try:
        os.unlink(out_cert)
    except:
        pass

    # some cert parameters
    out_certreq = tempfile.mktemp(suffix='-certreq')
    ndays = 365*20  # 20 years -- to avoid "Y2038" problems (2008 + 30 = 2038); observed in practice
    if common_name is None:
        inst_uuid = get_installation_uuid()
        common_name = '%s Server (%s)' % (constants.PRODUCT_NAME, inst_uuid)
    if organization is None:
        organization = 'Codebay'
    subject = '/' + '/'.join(['C=FI',
                              'ST=Not applicable',
                              'L=Helsinki',
                              'O=%s' % organization,
                              'OU=%s' % constants.PRODUCT_NAME,
                              'CN=%s' % common_name,
                              'emailAddress=%s' % constants.PRODUCT_SUPPORT_EMAIL])

    # generate keypair (private key has both public and private key)
    _log.debug('genrsa')
    run_command([constants.CMD_OPENSSL, 'genrsa',
                 '-out', out_privkey,
                 '-f4',
                 str(nbits)])
    if not os.path.exists(out_privkey):
        raise Exception('failed to create private key')

    # generate a cert req
    _log.debug('req')
    run_command([constants.CMD_OPENSSL, 'req',
                 '-inform', 'PEM',
                 '-outform', 'PEM',
                 '-out', out_certreq,
                 '-verify',
                 '-keyform', 'PEM',
                 '-key', out_privkey,
                 '-new',
                 '-batch',
                 '-days', str(ndays),  # XXX: this is ignored now and will not be in the certreq... (dup below for x509)
                 '-subj', subject])
    if not os.path.exists(out_certreq):
        raise Exception('failed to create certificate request')

    # generate the final signed certificate
    _log.debug('x509')
    self_signed = (in_ca_privkey is None)
    if self_signed:
        _log.debug('self-signed')
        run_command([constants.CMD_OPENSSL, 'x509',
                     '-inform', 'PEM',
                     '-outform', 'PEM',
                     '-in', out_certreq,
                     '-out', out_cert,
                     '-signkey', out_privkey,
                     '-req',
                     '-days', str(ndays)])
    else:
        _log.debug('CA signed')
        run_command([constants.CMD_OPENSSL, 'x509',
                     '-inform', 'PEM',
                     '-outform', 'PEM',
                     '-in', out_certreq,
                     '-out', out_cert,
                     '-CA', in_ca_certificate,
                     '-CAkey', in_ca_privkey,
                     '-CAserial', in_ca_serialfile,
                     '-CAcreateserial', # XXX: not necessary usually
                     '-req',
                     '-days', str(ndays)])

    if not os.path.exists(out_cert):
        raise Exception('failed to create cert')

    _log.info('self-signed certificate and private key generated successfully')

def generate_self_signed_certificate(out_privkey, out_cert, nbits=1024, common_name=None, organization=None):
    return _generate_signed_certificate(None, None, None, out_privkey, out_cert, nbits, common_name, organization)

def generate_ca_signed_certificate(in_ca_privkey, in_ca_certificate, in_ca_serialfile, out_privkey, out_cert, nbits=1024, common_name=None, organization=None):
    return _generate_signed_certificate(in_ca_privkey, in_ca_certificate, in_ca_serialfile, out_privkey, out_cert, nbits, common_name, organization)


def check_self_signed_certificate(privkey, cert):
    try:
        if not os.path.exists(privkey):
            _log.info('private key file does not exist, self signed certificate considered invalid')
            return False

        if not os.path.exists(cert):
            _log.info('certificate file does not exist, self signed certificate considered invalid')
            return False

        end_secs = 30*24*60*60  # 30 days
        retval, ign1, ign2 = run_command([constants.CMD_OPENSSL, 'x509',
                                          '-inform', 'PEM',
                                          '-in', cert,
                                          '-checkend', str(end_secs)])
        if retval != 0:
            _log.info('certificate will expire within the next %s seconds, self signed certificate considered invalid' % end_secs)
            return False

        return True
    except:
        _log.exception('something went wrong when checking self signed certificate, assuming it is invalid')
        return False

def get_product_name():
    return constants.PRODUCT_NAME

_cached_product_version = None

def get_product_version(cache=True, filecache=False):
    """Return product version string in an exact format.

    Suitable for use in management protocol, for instance.  Caches result
    and returns version from cache unless cache=True.  Product version
    should not change without a web UI and product restart.
    """

    global _cached_product_version

    # memory cache, generally useful
    if cache and _cached_product_version is not None:
        return _cached_product_version

    # file cache, useful for e.g. cron scripts
    if filecache and os.path.exists(constants.PRODUCT_VERSION_CACHE_FILE):
        f = None
        t = None
        try:
            f = open(constants.PRODUCT_VERSION_CACHE_FILE, 'rb')
            t = f.read()
            t = t.strip()
        finally:
            if f is not None:
                f.close()
            f = None
        return t
    
    [version_string, cached] = versioninfo.get_version_info()

    # update caches
    _cached_product_version = version_string
    if not os.path.exists(constants.PRODUCT_VERSION_CACHE_FILE):
        f = None
        try:
            f = open(constants.PRODUCT_VERSION_CACHE_FILE, 'wb')
            f.write(version_string)
        finally:
            if f is not None:
                f.close()
            f = None

    return version_string

def get_product_identifier_string():
    """Return a free-form, human readable product identifier string."""
    ver = None
    try:
        ver = get_product_version()
    except:
        ver = '(unknown version)'

    return '%s %s' % (constants.PRODUCT_NAME, ver)

def write_random_uuid_file(fname):
    f = None
    try:
        f = open(fname, 'wb')
        f.write('%s\n' % randutil.random_uuid())
    except:
        timestamp = None

    if f is not None:
        f.close()

def write_datetime_marker_file(fname):
    """Write a timestamp to a markerfile.

    Returns the datetime object used for the timestamp on the
    markerfile.
    """

    timestamp = datetime.datetime.utcnow()

    f = None
    try:
        f = open(fname, 'wb')
        f.write('%s\n' % datatypes.encode_datetime_to_iso8601_subset(timestamp))
    except:
        timestamp = None

    if f is not None:
        f.close()

    return timestamp

def read_datetime_marker_file(fname):
    """Reads a timestamp from a markerfile.

    Returns the datetime object parsed from the timestamp in
    markerfile if found and valid, None otherwise.
    """

    timestamp = None

    f = None
    try:
        f = open(fname, 'rb')
        timestamp = datatypes.parse_datetime_from_iso8601_subset(f.readline().strip())
    except:
        pass

    if f is not None:
        f.close()

    return timestamp

def get_standard_zipfile_name(name):
    now = datetime.datetime.utcnow()
    t = now.strftime('%Y%m%d-%H%M%S')
    return '%s-%s.zip' % (t, name)

def timedelta_to_seconds(td):
    return td.days*24.0*60.0*60.0 + float(td.seconds) + td.microseconds/1000000.0

def find_ppp_user(username=None):
    cfg_users = get_config().getS(ns.usersConfig, rdf.Type(ns.UsersConfig))

    res = []
    for i, u in enumerate(cfg_users.getS(ns.users, rdf.Bag(rdf.Type(ns.User)))):
        if (username is not None) and (u.getS(ns.username, rdf.String) == username):
            res.append(u)
        
    if len(res) == 0:
        return None
    elif len(res) == 1:
        return res[0]
    else:
        # XXX: allow list return?
        raise Exception('multiple users match criteria')

def filter_ppp_device_statuses(filterlist):
    rdfdevs = get_ppp_devices()

    res = []
    for i, d in enumerate(rdfdevs):
        match = True
        for f in filterlist:
            try:
                rc = f(d)
                if not rc:
                    match = False
                    break
            except:
                match = False
                break
        if match:
            res.append(d)
    return res

def filter_ppp_device_statuses_single(filterlist):
    res = filter_ppp_device_statuses(filterlist)
    if len(res) == 0:
        return None
    if len(res) == 1:
        return res[0]

    # multiple matches, take most recent
    r = None
    starttime = None
    for d in res:
        try:
            if not d.hasS(ns.startTime):
                continue
            s = d.getS(ns.startTime, rdf.Datetime)

            if r is None or (starttime is not None and s > starttime):
                r = d
                starttime = s
        except:
            continue

    if r is None:
        # this is an emergency alternative; couldn't compare times
        return res[0]
    else:
        return r

def find_ppp_device_status_sitetosite_client(username):
    def _f1(d):
        return d.getS(ns.username, rdf.String) == username
    def _f2(d):
        return d.getS(ns.connectionType).hasType(ns.SiteToSiteClient)
        
    return filter_ppp_device_statuses_single([_f1, _f2])
    
def find_ppp_device_status_sitetosite_server(username):
    def _f1(d):
        return d.getS(ns.username, rdf.String) == username
    def _f2(d):
        return d.getS(ns.connectionType).hasType(ns.SiteToSiteServer)
        
    return filter_ppp_device_statuses_single([_f1, _f2])
    
def find_ppp_device_status(address=None, username=None):
    """Find device status node based on address and/or username.

    This is currently only used by the web UI.  For the web UI this is the best
    guess for identifying the device related to a forced web forward; which
    allows the web UI to default username for user login, for instance.
    """

    def _f1(d):
        return (address is not None) and (d.getS(ns.pppAddress, rdf.IPv4Address) == address)
    def _f2(d):
        return (username is not None) and (d.getS(ns.username, rdf.String) == username)

    # There may be multiple matching devices in corner cases, e.g. two devices
    # in RDF with the same IP address.  License monitor reconcile process should
    # eliminate these discrepancies eventually but here we may still encounter
    # them from time to time.
    #
    # If there are multiple matching entries, we take the newest one and assume
    # that is the desired one.  If the entries have a different username, this
    # may match to the wrong user.  This is not critical: the web UI does not
    # allow the user to make any user-related changes until the user has logged
    # in (providing his password).  This function only provides the default value
    # for login username.
    #
    # So: return device with latest startTime (newest connection), or first in
    # list if no startTime is found.  [filter_ppp_device_statuses_single does this.]

    return filter_ppp_device_statuses_single([_f1, _f2])
    
def parse_product_version(vers):
    t = re.split('\D+', vers)   # '1.0.0-whatever' => ['1', '0', '0', 'whatever']

    try:
        ret = [int(t[0]), int(t[1]), int(t[2])]
    except:
        raise Exception('invalid version number: %s' % vers)
    
    return ret

def compare_product_versions(v1, v2):
    [v1_major, v1_minor, v1_revision] = parse_product_version(v1)
    [v2_major, v2_minor, v2_revision] = parse_product_version(v2)

    if v1_major > v2_major:
        return 1
    if v1_major < v2_major:
        return -1
    if v1_minor > v2_minor:
        return 1
    if v1_minor < v2_minor:
        return -1
    if v1_revision > v2_revision:
        return 1
    if v1_revision < v2_revision:
        return -1
    return 0

def change_unix_password(username, password, md5=True):
    """Change UNIX password for a certain user.

    This uses the chpasswd command internally.
    """

    cmd = [constants.CMD_CHPASSWD]
    if md5:
        cmd.append('-m')

    txt = '%s:%s\n' % (username, password)

    _log.info('changing password for user %s' % username)

    [rv, stdout, stderr] = run_command(cmd, stdin=txt, retval=runcommand.FAIL)

def check_unix_password_characters(password):
    # password may be unicode or str, we don't care
    for i in xrange(len(password)):
        if not password[i] in constants.ALLOWED_UNIX_PASSWORD_CHARACTERS:
            return False
    return True

def acquire_flock(fname):
    """Wait and get an flock.

    Returns file object used for locking or None if locking failed.

    XXX: may result infinite wait if lock holding process does not
    release the lock or die.
    """

    lockfile = None

    try:
        lockfile = open(fname, 'wb')
        fcntl.flock(lockfile.fileno(), fcntl.LOCK_EX)
    except:
        # Note: caller is assumed to treat None as error
        if lockfile is not None:
            lockfile.close()
            lockfile = None

    return lockfile

def release_flock(lockfile):
    """Release an flock."""
    
    if lockfile is not None:
        lockfile.close()

def acquire_openl2tpconfig_lock():
    return acquire_flock(constants.OPENL2TP_CONFIG_LOCK_FILE)
    
def release_openl2tpconfig_lock(lockfile):
    release_flock(lockfile)

def acquire_iptables_lock():
    return acquire_flock(constants.IPTABLES_LOCK_FILE)

def release_iptables_lock(lockfile):
    release_flock(lockfile)

def get_root_free_space_bytes():
    import os, statvfs
    st = os.statvfs('/')
    available = st[statvfs.F_BSIZE]*st[statvfs.F_BAVAIL]
    return available

def increment_global_status_counter(counter_uri):
    try:
        st = get_global_status()
        if not st.hasS(counter_uri):
            st.setS(counter_uri, rdf.Integer, 1)
        else:
            st.setS(counter_uri, rdf.Integer, st.getS(counter_uri, rdf.Integer) + 1)
        _log.info('increment_global_status_counter: %s incremented to %d' % (counter_uri, st.getS(counter_uri, rdf.Integer)))
    except:
        _log.exception('cannot increase global counter: %s' % counter_uri)

def get_uptime():
    """Get uptime from as reliable source as possible.

    Currently uses boot timestamp compared to current time if we successfully
    time synced on this boot, and the difference between last time sync from
    web GUI is small enough to make us believe that current timestamp provides
    accurate information for uptime.

    If either condition fails, we use /proc/uptime.
    """

    now = datetime.datetime.utcnow()
    uptime = None

    # boot timestamp exists + boot-time timesync in update check successful on this boot + webui has time synced at least once
    try:
        if os.path.exists(constants.BOOT_TIMESTAMP_FILE) and \
               os.path.exists(constants.UPDATE_TIMESYNC_TIMESTAMP_FILE) and \
               os.path.exists(constants.WEBUI_LAST_TIMESYNC_FILE):
            webui_sync_age = now - read_datetime_marker_file(constants.WEBUI_LAST_TIMESYNC_FILE)
            if webui_sync_age > datetime.timedelta(0, 0, 0) and webui_sync_age < constants.UPTIME_WEBUI_TIMESYNC_AGE_LIMIT:
                t = now - read_datetime_marker_file(constants.BOOT_TIMESTAMP_FILE)
                uptime = timedelta_to_seconds(t)
    except:
        # wide, but we want to fall back to proc gracefully
        _log.exception('get_uptime(): failed to read timestamp, falling back to proc uptime')

    if uptime is None:
        _log.info('using /proc/uptime for uptime, no reliable timesync')
        f = None

        try:
            f = open(constants.PROC_UPTIME, 'rb')
            t = f.read().strip().split(' ')  # 0=uptime (seconds), 1=time in idle process (seconds)
            uptime = float(t[0])
        except:
            pass
            
        if f is not None:
            f.close()
            f = None

    return uptime

def get_public_private_address_from_rdf():
    st = get_status()

    pub_addr = None
    if st.hasS(ns.publicInterface):
        pub = st.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
        if pub.hasS(ns.ipAddress):
            pub_addr = pub.getS(ns.ipAddress, rdf.IPv4AddressSubnet).getAddress().toString()

    priv_addr = None
    if st.hasS(ns.privateInterface):
        priv = st.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
        if priv.hasS(ns.ipAddress):
            priv_addr = priv.getS(ns.ipAddress, rdf.IPv4AddressSubnet).getAddress().toString()

    return pub_addr, priv_addr

def db_flush(dbase=None):
    """Force RDF database flush."""
    if dbase is None:
        dbase = db.get_db().getModel()

    @db.untransact(database=dbase)
    def _dummy():
        _log.info('flushing database')

    _dummy()

def create_rundir():
    """Create/Recreate the directory where l2tp stores the runtime files."""

    run_command(['/bin/rm', '-rf', constants.RUNTIME_DIRECTORY], retval=runcommand.FAIL)

    # XXX: add other directories from /var/lib or from /usr/lib which belong here
    for directory, permissions, owner in [(constants.RUNTIME_DIRECTORY, '0755', 'root:root'),
                                          (constants.FREERADIUS_CONFIG_DIR, '0755', 'root:root'),
                                          (constants.RADIUSCLIENT_CONFIG_DIR, '0755', 'root:root'),
                                          (constants.RADIUSCLIENT_NG_CONFIG_DIR,'0755', 'root:root'),
                                          (constants.DHCP_RUNTIME_DIRECTORY, '0755', 'dhcp:dhcp')]:
        run_command(['/bin/mkdir', '-p', directory], retval=runcommand.FAIL)
        run_command(['/bin/chmod', permissions, directory], retval=runcommand.FAIL)
        run_command(['/bin/chown', owner, directory], retval=runcommand.FAIL)

def compute_password_nt_hash(pw):
    """Compute NT password hash.

    In practice, this is an MD4 of a password.  For details, see:

      * http://en.wikipedia.org/wiki/NTLM
      * http://tools.ietf.org/html/rfc2433
      * http://tools.ietf.org/html/rfc2759

    Note that the MD4 is computed over the UNICODE version of the
    password.  And this UNICODE version is *little endian*!
    """

    from Crypto.Hash import MD4

    pw = unicode(pw)  # if not already unicode

    # little endian unicode buffer
    t = ''
    for c in pw:
        o = ord(c)
        t += chr(o & 0xff)         # lo
        t += chr((o >> 8) & 0xff)  # hi

    return MD4.new(t).digest()

def compute_password_md5(pw):
    import md5

    pw = unicode(pw)  # if not already unicode
    t = ''
    for c in pw:
        o = ord(c)
        if (o > 255):
            raise Exception('invalid password')
        t += chr(o)

    return md5.new(t).digest()

def uri_escape(x):
    """Paranoid URI escaping."""

    # XXX: use 0x20 -> '+' escaping?

    if isinstance(x, str):
        x = x.decode('us-ascii')
    elif isinstance(x, unicode):
        pass
    else:
        raise Exception('invalid argument: %s' % x)

    res = ''
    for i in x:
        o = ord(i)
        if ((o >= ord('a')) and (o <= ord('z'))) or \
               ((o >= ord('A')) and (o <= ord('Z'))) or \
               ((o >= ord('0')) and (o <= ord('9'))):
            res += str(i)
        else:
            for j in i.encode('utf-8'):
                res += '%%%02X' % ord(j)

    return res

def xml_escape(x):
    """Paranoid XML escaping suitable for content and attributes."""
    
    res = ''
    for i in x:
        o = ord(i)
        if ((o >= ord('a')) and (o <= ord('z'))) or \
               ((o >= ord('A')) and (o <= ord('Z'))) or \
               ((o >= ord('0')) and (o <= ord('9'))) or \
               i in ' !#$%()*+,-./:;=?@\^_`{|}~':
            res += i
        else:
            res += '&#%d;' % o
    return res
