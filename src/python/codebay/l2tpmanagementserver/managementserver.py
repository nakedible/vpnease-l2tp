"""
L2TP management server.

License information is currently tracked as follows:

  * Demo licenses are tracked by storing demo license information
    into the local filesystem with filename equalling the license key.
    These need to be backed up manually, so this is not the best possible
    solution right now.

  * Actual customer licenses are read from a CSV file exported through
    OpenOffice.  If the file is changed, the master will detect the change
    and force re-read of the license information + a re-identify for
    management connection clients.

  * The "targeting" of updates is now pretty poor; it could be keyed
    to license key (maybe), cannot handle more than two versions now,
    etc.
    
Example configuration file (/etc/managementserver.conf):

[misc]
address1=<ip address for <= v3 connections>
address2=<ip address for >= v4 connections>
immediateupdate=false
beta_servers=<comma separated ip addresses of vpnease servers for unstable repo>
stable_version=<e.g. "1.1">
unstable_version=<e.g. "1.1">
"""
__docformat__ = 'epytext en'

import datetime

from twisted.internet import protocol, reactor, defer
from twisted.application import service

from codebay.common import logger
from codebay.common import randutil
from codebay.common import datatypes
#from codebay.common import twisted_amp as amp
from codebay.common import amphelpers
from codebay.l2tpmanagementprotocol import managementprotocol
from codebay.l2tpmanagementserver import licensemanager
from codebay.l2tpmanagementserver import constants as msconstants
from codebay.l2tpmanagementserver import aptsupport

from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand

run_command = runcommand.run_command

_log = logger.get('l2tpmanagementserver.managementserver')

# --------------------------------------------------------------------------

class UpdateManager:
    def __init__(self, master, aptcache):
        self.master = master
        self.aptcache = aptcache
        
    def update_check(self, res, arg_softwareVersion, arg_automaticUpdates, apt_source):
        try:
            update_available, update_needed, update_immediately, update_forced = False, False, False, False

            # FIXME: this must be changed to handle every major version separately (= update "tree")
            current_version, current_changelog = self.aptcache.get_apt_info(apt_source)
            if current_version is None:
                raise Exception('current up-to-date version not available, ignoring update check')

            rc = helpers.compare_product_versions(arg_softwareVersion, current_version)
            _log.debug('comparison result: %s (client version: %s, current version: %s)' % (rc, arg_softwareVersion, current_version))

            if rc == 1:
                # client software is newer than available
                raise Exception('client software version (%s) is newer than ours (%s), unexpected' % \
                                (arg_softwareVersion, current_version))
            elif rc == 0:
                # up-to-date
                update_available, update_needed, update_forced = False, False, False
            elif rc == -1:
                # update exists, policy check
                server_forced_update = False  # FIXME - determine this somehow if we want critical updates
                if arg_automaticUpdates:
                    update_available, update_needed, update_forced = True, True, False
                elif server_forced_update:
                    update_available, update_needed, update_forced = True, True, True
                else:
                    update_available, update_needed, update_forced = True, False, False

                # immediate updates, master option
                if self.master.immediate_update:
                    _log.warning('master.immediate_update is True, forcing immediate update')
                    update_immediately = True
            else:
                raise Exception('unknown result from compare_product_versions: %s' % rc)
        except:
            _log.exception('cannot perform version / update check, skipping')
            update_available, update_needed, update_forced = False, False, False

        _log.debug('update check result: %s, %s, %s' % (update_available, update_needed, update_forced))

        res['updateAvailable'] = update_available
        res['updateNeeded'] = update_needed
        res['updateImmediately'] = update_immediately
        res['updateForced'] = update_forced
        
# --------------------------------------------------------------------------

from twisted.python.util import mergeFunctionMetadata

#
#  XXX: the check below (identify_successful) is not currently exactly correct;
#  we would like to prevent some operations for (a) anonymous licenses, (b)
#  demo licenses.  Add parameters to decorator later for this.
#

def require_successful_identify():
    """Decorator for AMP requests; raises Exception if no previous Identify."""

    def _f(f):
        def g(self, *args, **kw):
            if not hasattr(self, 'identify_successful'):
                raise managementprotocol.InternalServerError('no identify_successful attribute found')
            elif not isinstance(self.identify_successful, bool):
                raise managementprotocol.InternalServerError('identify_successful attribute not boolean')
            elif not self.identify_successful:
                raise managementprotocol.ProtocolStateError('request requires successful Identify')
            else:
                return f(self, *args, **kw)
            
        mergeFunctionMetadata(f, g)
        return g
    return _f

# --------------------------------------------------------------------------

class ManagementServerProtocol(amphelpers.LoggingAMP):
    """Implementations of management server commands.

    The implementation is multi-version; it should be able to handle
    Version exchanges for multiple versions, and handle individual
    commands accordingly.  Decorators are used to wrap functions to
    check for authentication, version, etc.
    """
    def __init__(self, master):
        self.master = master
        self.aptcache = aptsupport.get_aptcache()
        self.licensemanager = licensemanager.LicenseManager(self.master)
        self.updatemanager = UpdateManager(self.master, self.aptcache)
        self.version_successful = False
        self.version_number = 0
        self.identify_successful = False
        self.license_key = None
        self.license_status = None
        self.is_demo_license = None
        self.client_software_version = None
        self.client_boot_uuid = None
        self.client_installation_uuid = None
        self.client_cookie_uuid = None
        self._keepalive_call = None
        self._keepalive_timeout = None
        
    def makeConnection(self, transport):
        self._keepalive_call = reactor.callLater(msconstants.KEEPALIVE_INTERVAL, self._send_keepalive)
        self.master.connection_made(self, transport)
        return super(ManagementServerProtocol, self).makeConnection(transport)

    def connectionLost(self, reason):
        if self._keepalive_timeout is not None:
            self._keepalive_timeout.cancel()
            self._keepalive_timeout = None
        if self._keepalive_call is not None:
            self._keepalive_call.cancel()
            self._keepalive_call = None
        self.master.connection_lost(self, reason)
        return super(ManagementServerProtocol, self).connectionLost(reason)

    def _send_keepalive(self):
        self._keepalive_call = None
        #self._keepalive_call = reactor.callLater(msconstants.KEEPALIVE_INTERVAL, self._send_keepalive)

        def _keepalive_timeout():
            self._keepalive_timeout = None
            _log.warning('keepalive command timed out, losing connection')
            self.transport.loseConnection()

        if self._keepalive_timeout is not None:
            self._keepalive_timeout.cancel()
            self._keepalive_timeout = None
        self._keepalive_timeout = reactor.callLater(msconstants.KEEPALIVE_TIMEOUT, _keepalive_timeout)

        def _failed_keepalive(x):
            _log.warning('keepalive command command failed: %s, losing connection' % x)
            self.transport.loseConnection()

        def _do_keepalive(res):
            _log.debug('sending keepalive')
            return self.callRemote(managementprotocol.Keepalive)

        def _success_keepalive(res):
            _log.debug('_success_keepalive')
            if self._keepalive_timeout is not None:
                self._keepalive_timeout.cancel()
                self._keepalive_timeout = None
            self._keepalive_call = reactor.callLater(msconstants.KEEPALIVE_INTERVAL, self._send_keepalive)

        d = defer.Deferred()
        d.addCallback(_do_keepalive)
        d.addCallback(_success_keepalive)
        d.addErrback(_failed_keepalive)
        d.callback(None)
        return d

    def request_reidentify(self):  # called by master
        return self.callRemote(managementprotocol.RequestReidentify, reason='product update available')
        
    # ----------------------------------------------------------------------
    
    def client_version(self, version, info):
        self.version_successful = True
        self.version_number = int(version)
        return {'info': msconstants.SERVER_VERSION_INFO_STRING}
    managementprotocol.Version.responder(client_version)

    # XXX: suppress logging for this?
    def client_keepalive(self):
        return {}
    managementprotocol.Keepalive.responder(client_keepalive)

    def _handle_identify(self, kw, identify_version):
        """Handle Identify, Identify2, Identify3, Identify4"""
        arg_primary = kw['isPrimary']
        arg_licenseKey = kw['licenseKey']
        arg_bootUuid = kw['bootUuid']
        arg_installationUuid = kw['installationUuid']
        arg_cookieUuid = None
        arg_address = kw['address']
        arg_port = kw['port']
        arg_softwareVersion = kw['softwareVersion']
        arg_softwareBuildInfo = kw['softwareBuildInfo']
        arg_hardwareType = kw['hardwareType']
        arg_hardwareInfo = kw['hardwareInfo']
        arg_automaticUpdates = kw['automaticUpdates']
        arg_isLiveCd = kw['isLiveCd']

        # cookieUuid only present in Identify2
        request_had_cookie = False
        if kw.has_key('cookieUuid'):
            request_had_cookie = True
            arg_cookieUuid = kw['cookieUuid']
        
        res = {}

        # Fill in fixed server info
        res['softwareBuildInfo'] = msconstants.SERVER_IDENTIFY_SOFTWARE_BUILD_INFO
        res['serverInfo'] = msconstants.SERVER_IDENTIFY_SERVER_INFO

        # Check license; either anonymous (no license) or non-anonymous
        self.licensemanager.license_lookup(res, arg_licenseKey)

        # Determine proper aptsource - stable or unstable currently
        aptsource = None
        repokeys = None
        if str(self.transport.getPeer().host) in self.master.beta_servers:
            _log.info('beta server detected, using unstable source')
            aptsource = self.master.unstable_aptsource
        else:
            aptsource = self.master.stable_aptsource

        # Repokeys are currently version independent
        f = open(msconstants.REPOSITORY_KEYS_FILE, 'rb')
        repokeys = f.read()
        f.close()

        # Update check
        self.updatemanager.update_check(res, arg_softwareVersion, arg_automaticUpdates, aptsource)

        # Always send up-to-date sources.list; client must only use if update_needed = True
        res['aptSourcesList'] = aptsource

        # Always send repo keys
        res['repositoryKeys'] = repokeys

        # Always send current changelog
        current_version, current_changelog = self.aptcache.get_apt_info(aptsource)
        if current_changelog is not None:
            res['changeLog'] = current_changelog
        else:
            _log.error('changelog information not available, sending back empty string')
            res['changeLog'] = ''

        # Store basic information to own state
        self.identify_successful = True
        self.license_key = arg_licenseKey
        self.license_status = res['licenseStatus']
        self.is_demo_license = res['isDemoLicense']
        self.client_software_version = arg_softwareVersion
        self.client_installation_uuid = arg_installationUuid
        self.client_boot_uuid = arg_bootUuid
        self.client_cookie_uuid = None

        # Note: self.client_cookie_uuid is set to None initially to ensure that the
        # concurrent cookie check below does not mistakenly match this connection

        # Fill in cookie for Identify2
        if request_had_cookie:
            # FIXME - what to do we actually want to do with the cookie?
            #
            # This is the current heuristic for cookies which doesn't actually do
            # anything useful except that it tries to keep the cookies unique.

            if arg_cookieUuid == '':
                res_cookie = randutil.random_uuid()
            else:
                if self.master.cookie_used_by_a_management_connection(arg_cookieUuid):
                    res_cookie = randutil.random_uuid()
                    _log.warning('cookie %s already in use, generated new cookie %s for client' % (arg_cookieUuid, res_cookie))
                else:
                    res_cookie = arg_cookieUuid
            res['cookieUuid'] = unicode(res_cookie)

            # Update cookie in state
            self.client_cookie_uuid = res_cookie

        # Address processing for Identify3
        if identify_version >= 3:
            local_addr = self.transport.getHost()
            remote_addr = self.transport.getPeer()
            behind_nat = False
            if (arg_address != unicode(remote_addr.host)):
                behind_nat = True
            
            res['clientAddressSeenByServer'] = unicode(remote_addr.host)
            res['clientPortSeenByServer'] = int(remote_addr.port)
            res['behindNat'] = behind_nat

        # Currently no v4 specific stuff
        if identify_version >= 4:
            pass
        
        # Fill in current time (last to minimize time diff)
        res['currentUtcTime'] = datetime.datetime.utcnow()

        return res

    def client_identify(self, **kw):
        return self._handle_identify(kw, 1)
    managementprotocol.Identify.responder(client_identify)

    def client_identify2(self, **kw):
        if self.version_number < 2:
            raise Exception('Identify2 not supported for protocol version %d' % self.version_number)
        return self._handle_identify(kw, 2)
    managementprotocol.Identify2.responder(client_identify2)

    def client_identify3(self, **kw):
        if self.version_number < 3:
            raise Exception('Identify3 not supported for protocol version %d' % self.version_number)
        return self._handle_identify(kw, 3)
    managementprotocol.Identify3.responder(client_identify3)

    def client_identify4(self, **kw):
        if self.version_number < 4:
            raise Exception('Identify4 not supported for protocol version %d' % self.version_number)
        return self._handle_identify(kw, 4)
    managementprotocol.Identify4.responder(client_identify4)

    @require_successful_identify()
    def client_request_test_license(self):
        abuse = self.licensemanager.detect_test_license_request_abuse()
        if abuse:
            raise managementprotocol.TestLicenseDeniedError('test license denied due to possible abuse')
        else:
            # We first try to see whether this server already has a known demo
            # license by installation UUID.  If so, return that license.  Else
            # allocate a new one.  This is not very good with respect to abuse
            # and will be problematic if admin clones VMs, but should be OK for now.

            peer = self.transport.getPeer()

            license_key = None
            try:
                license_key = self.licensemanager.check_existing_demo_license(datatypes.IPv4Address.fromString(peer.host), int(peer.port), self.client_installation_uuid)
            except:
                _log.exception('failed when checking for existing demo license')

            if license_key is None:
                license_key = self.licensemanager.create_new_demo_license(datatypes.IPv4Address.fromString(peer.host), int(peer.port), self.client_installation_uuid)
                _log.info('creating new demo license for peer %s:%s, installation uuid %s -> %s' % (peer.host, peer.port, self.client_installation_uuid, license_key))
            else:
                _log.info('using existing demo license for peer %s:%s, installation uuid %s -> %s' % (peer.host, peer.port, self.client_installation_uuid, license_key))
                
        return {'licenseKey': license_key}
    managementprotocol.RequestTestLicense.responder(client_request_test_license)

    @require_successful_identify()
    def client_server_event(self):
        return {}
    managementprotocol.ServerEvent.responder(client_server_event)

    @require_successful_identify()
    def client_customer_feedback(self):
        return {}
    managementprotocol.CustomerFeedback.responder(client_customer_feedback)

    @require_successful_identify()
    def client_connectivity_test(self):
        return {}
    managementprotocol.ConnectivityTest.responder(client_connectivity_test)

# --------------------------------------------------------------------------

class ManagementServerProtocolFactory(protocol.Factory):
    def __init__(self, master):
        self.master = master

    def buildProtocol(self, addr):
        return ManagementServerProtocol(self.master)

# --------------------------------------------------------------------------

class ManagementServerMaster:
    def __init__(self, config_parser):
        # config parsing
        parser = config_parser
        self.immediate_update = parser.getboolean('misc', 'immediateupdate')
        tmp = parser.get('misc', 'beta_servers')
        self.beta_servers = []
        for i in tmp.split(','):
            i = i.strip()
            if i == '':
                continue
            self.beta_servers.append(i)
        
        # rest of the initialization
        self.connections = []
        self.stable_aptsource = self._aptsource(parser.get('misc', 'stable_version'))
        self.unstable_aptsource = self._aptsource(parser.get('misc', 'unstable_version'))
        self._aptcache = aptsupport.get_aptcache()
        self._current_version, _ = self._aptcache.get_apt_info(self.stable_aptsource)
        self._master_check_call = None
        self._master_check_interval = msconstants.MASTER_CHECK_INTERVAL
        self._master_check_full_count = 0
        self._license_csv_md5 = licensemanager.get_customer_license_csv_md5()
        
    # FIXME: constant names are dumb
    def _aptsource(self, ver):
        if ver == '1.1':
            return msconstants.STABLE_APT_SOURCES_LIST
        elif ver == '1.2':
            return msconstants.UNSTABLE_APT_SOURCES_LIST
        else:
            raise Exception('unknown version %s' % ver)
        
    def pre_start(self):
        pass

    def start(self):
        self._master_check_call = reactor.callLater(self._master_check_interval, self._master_timer_callback)

    def stop(self):
        if self._master_check_call is not None:
            self._master_check_call.cancel()
            self._master_check_call = None

    def cookie_used_by_a_management_connection(self, cookie_uuid):
        for c in self.connections:
            if hasattr(c, 'client_cookie_uuid') and (c.client_cookie_uuid is not None) and (c.client_cookie_uuid != ''):
                if c.client_cookie_uuid == cookie_uuid:
                    return True
        return False
    
    def _master_timer_callback(self):
        self._master_check_call = None
        self._check_product_version_and_reidentify()
        self._check_license_csv_and_reidentify()
        self._log_connection_status()
        self._master_check_call = reactor.callLater(self._master_check_interval, self._master_timer_callback)

    def _check_product_version_and_reidentify(self):
        # FIXME: always from stable aptsource.. should be client dependent
        current_version, current_changelog = self._aptcache.get_apt_info(self.stable_aptsource)
        if current_version != self._current_version:
            _log.info('stable version has changed (%s -> %s), reidentifying clients' % (self._current_version, current_version))
            self._force_reidentify()

        self._current_version = current_version
        
    def _check_license_csv_and_reidentify(self):
        old_md5 = self._license_csv_md5
        new_md5 = licensemanager.get_customer_license_csv_md5()
        _log.info('license csv hash %s -> %s' % (old_md5, new_md5))
        if old_md5 != new_md5:
            _log.info('license csv changed, reread and reidentify')
            self._license_csv_md5 = new_md5
            licensemanager.force_customer_license_reread()
            self._force_reidentify()

    def _force_reidentify(self):
        for c in self.connections:
            try:
                d = c.request_reidentify()
            except:
                _log.exception('cannot reidentify client, conn %s' % c)

    def _log_connection_status(self):
        self._master_check_full_count += 1
        if self._master_check_full_count >= 12:   # XXX: magic: 5*12 = 60 mins
            self._master_check_full_count = 0
            full_status = True
        else:
            full_status = False
            
        tmp = []
        num_all = 0
        num_demo = 0
        num_valid = 0
        num_disabled = 0
        num_unknown = 0
        num_unrecognized = 0
        for c in self.connections:
            num_all += 1
            peer = c.transport.getPeer()
            s = '%s:%s' % (peer.host, peer.port)

            # A license goes into exactly one of these categories: demo, unrecognized, valid, disabled, unknown
            # Note that a demo license may be also valid/disabled, but we don't count expired demo licenses here now
            if (c.is_demo_license is not None) and c.is_demo_license:
                num_demo += 1
                s += '=D'
            elif (c.license_status is None):
                num_unrecognized += 1
                s += '=?'
            elif (c.license_status == 'VALID'):
                num_valid += 1
                s += '=V'
            elif (c.license_status == 'DISABLED'):
                num_disabled += 1
                s += '=I'
            elif (c.license_status == 'UNKNOWN'):
                num_unknown += 1
                s += '=U'
            tmp.append(s)

        summary = ', '.join(tmp)
        _log.info('MASTERSTATUS: %d connections, %d demo, %d valid, software version %s [%s]' % (num_all, num_demo, num_valid, self._current_version, summary))

        if full_status:
            lines = []
            for c in self.connections:
                try:
                    peer = c.transport.getPeer()
                    lines.append('   %s (status %s, demo %s) from %s:%s, software version %s, installation uuid %s, cookie uuid %s' % (c.license_key, c.license_status, c.is_demo_license, peer.host, peer.port, c.client_software_version, c.client_installation_uuid, c.client_cookie_uuid))
                except:
                    _log.exception('failed to log full details for connection %s' % c)

            for l in lines:
                _log.info(l)

            try:
                f = open(msconstants.CONNECTION_INFO_FILE, 'wb')
                for l in lines:
                    f.write(l + '\n')
            finally:
                if f is not None:
                    f.close()
                f = None
                
    def connection_made(self, protocol, transport):
        _log.info('master: connection made: %s, %s' % (protocol, transport))
        self.connections.append(protocol)
        
    def connection_lost(self, protocol, reason):
        _log.info('master: connection lost: %s, %s' % (protocol, reason))
        self.connections.remove(protocol)

    def connectionLost(self, reason):
        self.master.connection_lost(self, reason)

# --------------------------------------------------------------------------

class ManagementServerService(service.Service):
    def __init__(self, original):
        self.master = original

    def startService(self):
        # XXX: deferred?
        _log.debug('Master service starting.')
        try:
            self.master.start()
            _log.debug('Master service started.')
        except:
            _log.exception('Master service start failed.')
            raise

    def stopService(self):
        # XXX: deferred?
        _log.debug('Master service stopping.')
        try:
            self.master.stop()
            _log.debug('Master service stopped.')
        except:
            _log.exc('Master service stop failed.')
            raise

