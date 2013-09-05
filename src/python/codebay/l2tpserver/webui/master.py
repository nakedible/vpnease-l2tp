"""
L2TP server web UI master class.

The master class is responsible for tying together all the top-level
elements of the web UI process, including the web UI itself, watchdog
features, management protocol connection handling, starting and stopping
the protocol logic, and so on.

The intent is to gather all relevant points of policy control and top
level actions to this class.  Lower level classes should handle events
that are not relevant to overall policy and control internally, but
propagate all policy relevant events ultimately to the master class.
The master class can then dispose of the events in the correct manner,
taking into account, for instance, whether a wizard is executing in the
web UI.

The master class provides several functions which are used as callbacks
by lower level classes (such as ManagementConnection).  The stubs for
this "callback API" are in the CommonMaster class, used by the actual
web UI master but also by update code.  This API design is a bit dubious.
"""
__docformat__ = 'epytext en'

import os, datetime

from twisted.application import service
from twisted.internet import defer, reactor
from twisted.python import failure

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import versioninfo
from codebay.l2tpserver import timesync
from codebay.l2tpserver import managementconnection
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import l2tpmanager, watchdog, uihelpers
from codebay.l2tpmanagementprotocol import managementprotocol

_log = logger.get('l2tpserver.webui.master')

#
#  XXX: the current Ajax approach is two-fold: one part (AjaxUpdateHelper)
#  tracks waiting Ajax requests and polls system status, waking the waiters
#  if necessary.  The second part (Ajax request handlers) will render the
#  response when woken up.  There is no information sharing between the two;
#  it would be simpler if the poll check information would be made available
#  to the Ajax waiters, eliminating redundant re-reading of status data.
#

# --------------------------------------------------------------------------

class AjaxUpdateHelper:
    """Helper class for managing Ajax waiters and status polling."""

    poll_interval = 5

    def __init__(self, master):
        self.master = master
        self._status_waiters = []
        self._status_poll_call = None
        self._status_last_poll_status_values = None

    def add_status_change_waiter(self, d):
        self._status_waiters.append(d)
        self._reschedule_status_poll()

    def have_status_change_waiters(self):
        return len(self._status_waiters) > 0
    
    def get_status_values(self):
        """Summarize status values for easy comparison of (any) status changes.

        Any changes in these will cause Ajax blockers to be awakened.  Note that
        any triggers (such as management connection or state changes) are triggered
        from elsewhere, so they are not taken into account here.  These are strictly
        values that need to be polled and for which we do not get a trigger.

        The format here does not really matter, as long as it can be compared.
        """
        return []
    
    @db.transact()  # reactor callLater
    def _status_poll_timer(self):
        self._status_poll_call = None
        wakeup = False

        # Wake up if some status element has changed
        curr_values = self.get_status_values()
        if self._status_last_poll_status_values is None:
            wakeup = True
        elif self._status_last_poll_status_values != curr_values:
            wakeup = True
        self._status_last_poll_status_values = curr_values

        if wakeup:
            self.wake_status_change_waiters()

        self._reschedule_status_poll()
        
    def _reschedule_status_poll(self):
        # sanity
        if self._status_poll_call is not None:
            self._status_poll_call.cancel()
            self._status_poll_call = None

        # schedule a poll timer if there are waiters
        if len(self._status_waiters) > 0:
            # schedule to next N seconds
            now = datetime.datetime.utcnow()
            interval = self.poll_interval
            secs_now = int(now.second)
            secs_next = ((secs_now + interval) / interval * interval) + 1   # round up to next full interval, add leeway
            delay = float(secs_next - secs_now)
            if delay < 0: delay = 0.0     # sanity
            if delay > 60.0: delay = 60.0
            _log.debug('scheduling status poll to %f seconds' % delay)
            self._status_poll_call = reactor.callLater(delay, self._status_poll_timer)
        else:
            _log.debug('no waiters, not scheduling status poll')
            
    def wake_status_change_waiters(self):
        _log.debug('wake_status_change_waiters()')
        t, self._status_waiters = self._status_waiters, []
        for d in t:
            try:
                d.callback(None)
            except:
                _log.exception('status change waiter failed')

# --------------------------------------------------------------------------

class AjaxUpdateHelperGlobalStatus(AjaxUpdateHelper):
    """Ajax update helper for global status (layout and global status pages)."""
    def get_status_values(self):
        def _get_dyndns_info():
            try:
                return [self.master.get_dyndns_current_address()]
            except:
                return ['']
        
        def _get_license_info():

            # XXX: count both kinds of users at the same time

            lm = licensemanager.LicenseMonitor()
            count, limit, limit_leeway, count_s2s, limit_s2s, limit_leeway_s2s = lm.count_both_users()
            license_name = None
            try:
                license_name = helpers.get_license_info().getS(ns_ui.licenseString, rdf.String)
            except:
                _log.exception('cannot get license name')

            lic_valid = None
            try:
                lm = licensemanager.LicenseMonitor()
                lic_valid = lm.check_license_validity()
            except:
                _log.exception('cannot determine license validity, ignoring')

            have_connection = None
            try:
                # XXX: not the same as being actually connected in the sense of
                # sending Version + Identify, but a fair approximation for now
                have_connection = self.master.managementconnection.is_active()
            except:
                _log.exception('cannot determine whether we have management connection, ignoring')

            return [count, limit, count_s2s, limit_s2s, license_name, lic_valid, have_connection]
            
        def _get_health_info():
            state = None
            last_health_check = None
            failed_servers = None
            watchdog_action = None
            periodic_reboot = None
            try:
                st_root = helpers.get_status()

                mgr = self.master.l2tpmanager
                if mgr is None:
                    state = 'inactive'
                else:
                    state = mgr.getState()

                # XXX: this is a bit inaccurate; we'd ideally want to list all interesting
                # parts of status like public address and mac, router and dns/wins health
                # status etc; but since this changes about once a minute, this will do.
                last_health_check = st_root.getS(ns.lastPollTime, rdf.Datetime)

                failed_servers = []
                if st_root.hasS(ns.serverStatuses):
                    for x in st_root.getS(ns.serverStatuses, rdf.Bag(rdf.Type(ns.ServerStatus))):
                        if x.hasS(ns.serverHealthCheck) and (not x.getS(ns.serverHealthCheck, rdf.Boolean)):
                            failed_servers.append(x.getUri())
                if st_root.hasS(ns.routerStatuses):
                    for x in st_root.getS(ns.routerStatuses, rdf.Bag(rdf.Type(ns.RouterStatus))):
                        if x.hasS(ns.routerHealthCheck) and (not x.getS(ns.routerHealthCheck, rdf.Boolean)):
                            failed_servers.append(x.getUri())

                watchdog_action = self.master.watchdog_action_is_pending()
                periodic_reboot = self.master.periodic_reboot_is_pending()
            except:
                _log.exception('cannot get status related info to poll state')

            return [state, last_health_check, failed_servers, watchdog_action, periodic_reboot]

        def _get_hardware_info():
            cpu_usage = None
            mem_usage = None
            disk_usage = None
            swap_usage = None

            try:
                st_root = helpers.get_global_status()
                cpu_usage = st_root.getS(ns.cpuUsage, rdf.Float)
                mem_usage = st_root.getS(ns.memoryUsage, rdf.Float)
                disk_usage = st_root.getS(ns.diskUsage, rdf.Float)
                swap_usage = st_root.getS(ns.swapUsage, rdf.Float)
            except:
                _log.exception('cannot get values')
                
            return [cpu_usage, disk_usage, mem_usage, swap_usage]

        def _get_datetime_info():
            now = datetime.datetime.utcnow().replace(microsecond=0, second=0)  # minute resolution
            return [now]

        res = _get_license_info() + _get_health_info() + _get_hardware_info() + _get_datetime_info() + _get_dyndns_info()
        _log.debug('status poll result: %s' % res)
        return res
                
# --------------------------------------------------------------------------

class LicenseHelper:
    """Centralized functionality for handling license status changes."""

    def update_license_info(self, res):
        _log.debug('identify response dict: %s' % res)

        lic = helpers.get_license_info()

        # get old license parameters first
        got_old = True
        try:
            old_max_normal = lic.getS(ns_ui.maxNormalConnections, rdf.Integer)
            old_max_s2s = lic.getS(ns_ui.maxSiteToSiteConnections, rdf.Integer)
            old_val_start = lic.getS(ns_ui.validityStart, rdf.Datetime)
            old_val_end = lic.getS(ns_ui.validityEnd, rdf.Datetime)
            old_recheck = lic.getS(ns_ui.validityRecheckLatest, rdf.Datetime)
            old_lic_string = lic.getS(ns_ui.licenseString, rdf.String)
            old_is_demo = lic.getS(ns_ui.isDemoLicense, rdf.Boolean)
            old_demo_val_start = lic.getS(ns_ui.demoValidityStart, rdf.Datetime)
            old_demo_val_end = lic.getS(ns_ui.demoValidityEnd, rdf.Datetime)

            _log.debug('old license parameters: normal=%s, s2s=%s, valstart=%s, valend=%s, recheck=%s, string=%s, isdemo=%s, demostart=%s, demoend=%s' % \
                       (old_max_normal, old_max_s2s, old_val_start, old_val_end, old_recheck, old_lic_string, old_is_demo, old_demo_val_start, old_demo_val_end))
        except:
            _log.exception('cannot get old license parameters')
            got_old = False
            
        # get new license parameters from the result
        got_new = True
        try:
            new_max_normal = res['licenseMaxRemoteAccessConnections']
            new_max_s2s = res['licenseMaxSiteToSiteConnections']
            new_val_start = res['licenseValidityStart']
            new_val_end = res['licenseValidityEnd']
            new_recheck = res['licenseRecheckLatestAt']
            new_lic_string = res['licenseString']
            new_lic_key = helpers.get_ui_config().getS(ns_ui.licenseKey, rdf.String)  # XXX: there is a slight race here, but we don't have the license key present in the request message here
            new_is_demo = res['isDemoLicense']
            new_demo_val_start = res['demoValidityStart']
            new_demo_val_end = res['demoValidityEnd']
        
            _log.debug('new license parameters: normal=%s, s2s=%s, valstart=%s, valend=%s, recheck=%s, string=%s, isdemo=%s, demostart=%s, demoend=%s' % \
                       (new_max_normal, new_max_s2s, new_val_start, new_val_end, new_recheck, new_lic_string, new_is_demo, new_demo_val_start, new_demo_val_end))
        except:
            _log.exception('cannot get new license parameters')
            got_new = False

        # get licenseStatus from protocol: it governs our basic actions
        license_status = None
        try:
            license_status = res['licenseStatus']
        except:
            _log.exception('cannot get licenseStatus from identify result')

        if got_new:
            # check licenseStatus values and act accordingly
            if license_status == 'VALID':
                _log.info('license status is valid (key \'%s\')' % new_lic_key)
                lic.setS(ns_ui.maxNormalConnections, rdf.Integer, new_max_normal)
                lic.setS(ns_ui.maxSiteToSiteConnections, rdf.Integer, new_max_s2s)
                lic.setS(ns_ui.validityStart, rdf.Datetime, new_val_start)
                lic.setS(ns_ui.validityEnd, rdf.Datetime, new_val_end)
                lic.setS(ns_ui.validityRecheckLatest, rdf.Datetime, new_recheck)
                lic.setS(ns_ui.licenseString, rdf.String, new_lic_string)
                lic.setS(ns_ui.licenseKey, rdf.String, new_lic_key)
                lic.setS(ns_ui.isDemoLicense, rdf.Boolean, new_is_demo)
                lic.setS(ns_ui.demoValidityStart, rdf.Datetime, new_demo_val_start)
                lic.setS(ns_ui.demoValidityEnd, rdf.Datetime, new_demo_val_end)
            elif license_status == 'DISABLED':
                _log.info('license status is disabled (key \'%s\')' % new_lic_key)
                self.invalidate_license_status()
            elif license_status == 'UNKNOWN':
                _log.info('license status is unknown (key \'%s\')' % new_lic_key)
                self.invalidate_license_status()
            else:
                _log.warning('license status is unexpected: %s (key \'%s\')' % (license_status, new_lic_key))
                self.invalidate_license_status()
        else:
            _log.warning('cannot find new license parameters')
            self.invalidate_license_status()

        # XXX: Currently license parameter changes or invalid license does not
        # cause any immediate reactions: the protocol side will simply refuse
        # to open up new connections.  Existing connections will not currently
        # be dropped, though that would be easy to do here.

    def process_failure_reason(self, reason):
        invalidate_license = False

        if isinstance(reason, (str, unicode)):
            _log.info('process_failure_reason: reason is string: %s' % reason)
        elif isinstance(reason, Exception):
            if isinstance(reason, managementprotocol.InvalidLicenseError):
                invalidate_license = True
                _log.info('process_failure_reason: reason is Exception, InvalidLicenseError: %s' % reason)
            else:
                _log.info('process_failure_reason: reason is Exception, %s' % reason)
        elif isinstance(reason, failure.Failure):
            e = reason.check(managementprotocol.InvalidLicenseError)
            if e == managementprotocol.InvalidLicenseError:
                _log.info('process_failure_reason: reason is Failure, InvalidLicenseError: %s, %s' % (reason, e))
                invalidate_license = True
            else:
                _log.info('process_failure_reason: reason is Failure: %s, %s' %  (reason, e))
        else:
            _log.info('process_failure_reason: reason is unknown: %s' % reason)

        if invalidate_license:
            self.invalidate_license_status()

    def invalidate_license_status(self):
        """Set current license state as close to 'invalid' as possible.

        This is called whenever license is not deemed valid, and will disable
        connectivity.
        """
        _log.info('invalidate_license_status() called, invalidating license')

        lic = helpers.get_license_info()

        # XXX: recheck from protocol is currently for valid licenses only;
        # what value to use here?  change protocol?
        now = datetime.datetime.utcnow()
        recheck = now + datetime.timedelta(0, 60*60, 0)  # 1 hour

        lic.setS(ns_ui.maxNormalConnections, rdf.Integer, 0)
        lic.setS(ns_ui.maxSiteToSiteConnections, rdf.Integer, 0)
        lic.setS(ns_ui.validityStart, rdf.Datetime, now)
        lic.setS(ns_ui.validityEnd, rdf.Datetime, now)
        lic.setS(ns_ui.validityRecheckLatest, rdf.Datetime, recheck)
        lic.setS(ns_ui.licenseString, rdf.String, '')
        lic.setS(ns_ui.licenseKey, rdf.String, '')
        lic.setS(ns_ui.isDemoLicense, rdf.Boolean, False)
        lic.setS(ns_ui.demoValidityStart, rdf.Datetime, now)
        lic.setS(ns_ui.demoValidityEnd, rdf.Datetime, now)
        
# --------------------------------------------------------------------------

class CommonMaster:
    def pre_start(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def user_login(self, avatar_id, mind):                 # from webui
        pass

    def user_logout(self, avatar_id, mind):                # from webui
        pass

    def runner_state_changed(self, mainstate, substate):   # from l2tpmanager
        pass
    
    def runner_starting(self):                             # from l2tpmanager
        pass

    def runner_ready(self):                                # from l2tpmanager
        pass

    def runner_stopping(self):                             # from l2tpmanager
        pass

    def runner_stopped(self):                              # from l2tpmanager
        pass
        
    def management_connection_up(self, identify_result):   # from managementconnection
        pass

    def management_connection_down(self, reason=None):     # from managementconnection
        pass
    
    def management_connection_reidentify(self, identify_result): # from managementconnection
        pass

# --------------------------------------------------------------------------

class WebUiMaster(CommonMaster):
    """Master class for web UI.

    Contains accessors for all top-level resources of the web UI process.
    """

    def __init__(self):
        self.l2tpmanager = l2tpmanager.L2TPManager(self)
        self.db = None
        self.managementconnection = managementconnection.ManagementConnection(self.mgmt_version_args, self.mgmt_identify_args, master=self)
        self.watchdog = watchdog.WebUiWatchdog(self)
        self._stopping = False
        self._service_active = False
        self._ajax_helper = AjaxUpdateHelperGlobalStatus(self)
        self._license_helper = LicenseHelper()
        self._activate_configuration_state = ['', False, False, False]  # see uihelpers
        self._ssl_cf = None
        self._timesync_notify_shown = False
        self._dyndns_address = None
        self._dyndns_address_timestamp = None
        self._dyndns_resolve_in_progress = False
        self._dyndns_time_limit = datetime.timedelta(0, 5*60, 0)
        self._dyndns_time_limit_error = datetime.timedelta(0, 1*60, 0)
        self._last_rdf_database_export = None  # XXX: accessed by watchdog
        
    # XXX: this is just a stashing place for activateconfiguration.html; some better coordination would be nice
    def set_activate_configuration_state(self, activity, finished=False, success=False, active=False):
        self._activate_configuration_state = [activity, finished, success, active]

    def get_activate_configuration_state(self):
        return self._activate_configuration_state
    
    def get_dyndns_current_address(self):
        res = self._dyndns_address or ''

        # Restart resolve in the background if too old or non-existent
        now = datetime.datetime.utcnow()
        resolve = False
        if self._dyndns_address_timestamp is None:
            _log.info('dyndns address timestamp is None, resolving')
            resolve = True
        else:
            diff = now - self._dyndns_address_timestamp

            time_limit = self._dyndns_time_limit
            if self._dyndns_address == 'ERROR':
                # XXX: not the cleanest possible solution - javascript "magics" this
                _log.info('last resolve failed, applying error time limit')
                time_limit = self._dyndns_time_limit_error
                
            if (diff < datetime.timedelta(0, 0, 0)) or (diff > time_limit):
                _log.info('dyndns diff is too large or negative (%s, vs. %s), resolving' % (diff, time_limit))
                resolve = True

        if resolve:
            try:
                d = self._resolve_dyndns()
                # ignore deferred d
            except:
                _log.exception('dyndns resolution failed')

        return res

    def _resolve_dyndns(self):
        # XXX: some sort of "last attempt timestamp" would be more robust perhaps?
        if self._dyndns_resolve_in_progress:
            _log.info('dyndns resolution already in progress, not starting another one')
            return None

        @db.transact()
        def _f():
            # this is to handle races
            if self._dyndns_resolve_in_progress:
                _log.info('dyndns resolution already in progress, not starting another one')
                return None

            ui_root = helpers.get_ui_config()
            now = datetime.datetime.utcnow()
            
            if ui_root.hasS(ns_ui.dynDnsServer):
                ddns_root = ui_root.getS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))
                if ddns_root.hasS(ns_ui.dynDnsHostname):
                    hostname = ddns_root.getS(ns_ui.dynDnsHostname, rdf.String)
                    _log.info('dyndns configured, resolving %s' % hostname)

                    # NB: not inside transact
                    def _success(res):
                        _log.info('dyndns lookup successful, %s -> %s' % (hostname, res.toString()))
                        self._dyndns_address = res.toString()
                        self._dyndns_address_timestamp = datetime.datetime.utcnow()

                    # NB: not inside transact
                    def _failed(reason):
                        _log.info('dyndns lookup failed, reason: %s' % reason)
                        self._dyndns_address = 'ERROR'
                        self._dyndns_address_timestamp = datetime.datetime.utcnow()

                    # NB: not inside transact
                    def _clear_marker(res):
                        _log.info('dyndns in progress marker cleared')
                        self._dyndns_resolve_in_progress = False

                    self._dyndns_resolve_in_progress = True
                    d = uihelpers.dns_lookup(hostname)
                    d.addCallback(_success)
                    d.addErrback(_failed)  # this intentionally follows _success
                    d.addCallbacks(_clear_marker, _clear_marker)
                    return d
                else:
                    _log.info('dyndns configured, but missing hostname')
                    self._dyndns_address = ''
                    self._dyndns_address_timestamp = now
            else:
                _log.info('dyndns not configured, no need to resolve')
                self._dyndns_address = ''
                self._dyndns_address_timestamp = now

        reactor.callLater(0.1, _f)
        return None
    
    def mgmt_version_args(self):
        args = {}
        args['version'] = managementprotocol.PROTOCOL_VERSION
        args['info'] = ''  # XXX: some sort of build info here?
        return args
    
    def mgmt_identify_args(self):
        args = {}
        try:
            # prefer actual license, then test (demo) license, then anonymous
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.licenseKey) and ui_root.getS(ns_ui.licenseKey, rdf.String) != '':
                args['licenseKey'] = ui_root.getS(ns_ui.licenseKey, rdf.String)
            elif ui_root.hasS(ns_ui.testLicenseKey) and ui_root.getS(ns_ui.testLicenseKey, rdf.String) != '':
                args['licenseKey'] = ui_root.getS(ns_ui.testLicenseKey, rdf.String)
            else:
                raise Exception('no configured license')
        except:
            args['licenseKey'] = ''  # anonymous

        try:
            t = helpers.get_boot_uuid()
            if t is None:
                args['bootUuid'] = ''
            else:
                args['bootUuid'] = t
        except:
            args['bootUuid'] = ''
        
        try:
            t = helpers.get_installation_uuid()
            if t is None:
                args['installationUuid'] = ''
            else:
                args['installationUuid'] = t
        except:
            args['installationUuid'] = ''
        
        try:
            t = helpers.get_cookie_uuid()
            if t is None:
                args['cookieUuid'] = ''
            else:
                args['cookieUuid'] = t
        except:
            args['cookieUuid'] = ''
        
        args['address'] = '0.0.0.0'       # XXX: overwritten
        args['port'] = 0                  # XXX: overwritten

        try:
            args['softwareVersion'] = helpers.get_product_version()
        except:
            args['softwareVersion'] = ''

        args['softwareBuildInfo'] = ''    # XXX
        args['hardwareType'] = ''         # XXX
        args['hardwareInfo'] = ''         # XXX

        try:
            args['automaticUpdates'] = helpers.get_ui_config().getS(ns_ui.automaticUpdates, rdf.Boolean)
        except:
            args['automaticUpdates'] = True

        try:
            args['isLiveCd'] = helpers.is_live_cd()
        except:
            args['isLiveCd'] = False

        return args

    @db.transact()
    def pre_start(self):  # see webui.tac
        _log.debug('WebUiMaster/pre_start()')

    @db.transact()
    def start(self):
        _log.debug('WebUiMaster/start()')

        @db.transact()
        def _open_db(res):
            _log.debug('WebUiMaster/start(): opening db')

            if self.is_live_cd() and self.is_lowmem():
                _log.info('live cd and lowmem, not starting db connection')
                self.db = None
            else:
                _log.debug('opening database connection')
                self.db = db.get_db()
                self.db.open()
            
        @db.transact()
        def _start_watchdog(res):
            _log.debug('WebUiMaster/start(): starting watchdog')
            self.watchdog.start_watchdog()

        @db.transact()
        def _maybe_start_runner(res):
            # start runner if we're configured to do so; otherwise don't

            # XXX: could add checks here to start runner only if it is
            # really startable (e.g. initial configuration scenario)
            self.start_l2tp_service()
            
        @db.transact()
        def _update_license_server_status(res):
            helpers.get_global_status().setS(ns.managementServerConnection, rdf.Boolean, False)
            # XXX - do we want to reset this? rely on previous info instead?
            #helpers.get_global_status().setS(ns.behindNat, rdf.Boolean, False)

        # create a Deferred of shutdown tasks and let Twisted run it
        d = defer.Deferred()
        d.addCallback(_open_db)
        d.addCallback(_start_watchdog)
        d.addCallback(_maybe_start_runner)
        d.addCallback(_update_license_server_status)
        d.callback(None)
        return d

    @db.transact()
    def stop(self):
        _log.debug('WebUiMaster/stop()')

        if self._stopping:
            _log.warning('WebUiMaster/stop(): already stopping, ignoring')
            return

        @db.transact()
        def _update_license_server_status(res):
            helpers.get_global_status().setS(ns.managementServerConnection, rdf.Boolean, False)
            # XXX - do we want to reset this? rely on previous info instead?
            #helpers.get_global_status().setS(ns.behindNat, rdf.Boolean, False)

        @db.transact()
        def _stop_l2tpmanager(res):
            self._dyndns_address = None
            self._dyndns_address_timestamp = None
            self._dyndns_resolve_in_progress = False  # paranoia

            return self.l2tpmanager.stop()
                
        @db.transact()
        def _stop_watchdog(res):
            _log.debug('stopping watchdog')
            self.watchdog.stop_watchdog()
            
        @db.transact()
        def _close_db(res):
            _log.debug('closing db')
            if self.db is not None:
                self.db.close()

        # create a Deferred of shutdown tasks and let Twisted run it
        d = defer.Deferred()
        d.addCallback(_update_license_server_status)
        d.addCallback(_stop_l2tpmanager)
        d.addCallback(_stop_watchdog)
        d.addCallback(_close_db)
        d.callback(None)
        return d
    
    def get_l2tpmanager(self):
        return self.l2tpmanager

    def get_db(self):
        return self.db
    
    def user_login(self, avatar_id, mind):   # website.py calls
        _log.info('user %s logged in' % (avatar_id,))

    def user_logout(self, avatar_id, mind):  # website.py calls
        _log.info('user %s logged out' % (avatar_id,))

    def is_live_cd(self):
        return helpers.is_live_cd()
    
    def is_lowmem(self):
        return helpers.is_lowmem()

    def watchdog_action_is_pending(self):
        return self.watchdog.watchdog_action_is_pending()

    def periodic_reboot_is_pending(self):
        return self.watchdog.periodic_reboot_is_pending()

    def start_primary_management_connection(self):
        _log.debug('WebUiMaster/start_primary_management_connection()')
        self.managementconnection.start_primary(authenticate=True)

    def stop_primary_management_connection(self):
        _log.debug('WebUiMaster/stop_primary_management_connection()')
        self.managementconnection.stop_primary()

    # XXX: currently protocol configuration is only generated by Web UI,
    # not on every runner start.
    @db.transact()
    def start_l2tp_service(self, wait=False):
        _log.debug('WebUiMaster/start_l2tp_service()')
        self._service_active = True

        self._dyndns_address = None
        self._dyndns_address_timestamp = None
        self._dyndns_resolve_in_progress = False  # paranoia

        self.l2tpmanager.start()
        if wait:
            return self.l2tpmanager.waitRunning()
        else:
            return defer.succeed(None)
        
    @db.transact()
    def stop_l2tp_service(self, wait=False):
        _log.debug('WebUiMaster/stop_l2tp_service()')
        self._service_active = False

        self._dyndns_address = None
        self._dyndns_address_timestamp = None
        self._dyndns_resolve_in_progress = False  # paranoia

        self.l2tpmanager.stop()
        if wait:
            return self.l2tpmanager.waitStopped()
        else:
            return defer.succeed(None)

    def runner_state_changed(self, mainstate, substate):
        _log.debug('runner_state_changed()')
        self._ajax_helper.wake_status_change_waiters()
        
    def runner_starting(self):
        _log.debug('runner_starting()')

        # reset device status
        try:
            root = helpers.get_db_root()
            l2tp_status = root.setS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))
        except:
            _log.exception('setting status root failed')

        self._ajax_helper.wake_status_change_waiters()
        
    def runner_ready(self):
        _log.info('l2tp runner ready - service up')

        def _runner_ready_notification(res):
            _log.debug('_runner_ready_notification')
            try:
                from codebay.l2tpserver import gnomehelpers
                gnomehelpers.show_notification(constants.WEBUI_RUNNER_READY_TITLE,
                                               constants.WEBUI_RUNNER_READY_TEXT,
                                               timeout=constants.WEBUI_RUNNER_READY_TIMEOUT,
                                               critical=False)
            except:
                _log.exception("_runner_ready_notification() failed")

        # notification box
        _runner_ready_notification(None)

        # ajax wakeup
        self._ajax_helper.wake_status_change_waiters()

        # schedule dyndns re-resolution
        try:
            d = self._resolve_dyndns()
            # ignore deferred d
        except:
            _log.exception('dyndns resolution failed')

        # start management connection
        return self.start_primary_management_connection()

    def runner_stopping(self):
        _log.debug('_runner_stopping')

        self._ajax_helper.wake_status_change_waiters()
        return self.stop_primary_management_connection()

    def runner_stopped(self):
        _log.info('l2tp runner stopped - service down')

        #
        #  XXX: Check runner exit code, runner may indicate it wants to reboot.
        #
        #  We currently ignore this and mark a runner restart as an unwanted
        #  (unrequested) one.  This causes runner restart count to increase
        #  if the problem reoccurs, and watchdog eventually reboots to recover.
        #  Current behavior is thus OK, just slower than needs be.
        #

        #
        #  Stop primary management connection.  This is usually unnecessary because
        #  runner_stopping() should have been called.  However, if the runner exits
        #  uncleanly, this seems necessary because otherwise management connections
        #  may be multiplied.
        #
        try:
            _log.debug('stopping primary management connection in runner_stopped')
            self.stop_primary_management_connection()
        except:
            _log.exception('primary management connection stop failed in runner_stopped, ignoring')

        def _runner_stopped_notification(res):
            _log.debug('_runner_stopped_notification')
            try:
                from codebay.l2tpserver import gnomehelpers
                gnomehelpers.show_notification(constants.WEBUI_RUNNER_STOPPED_TITLE,
                                               constants.WEBUI_RUNNER_STOPPED_TEXT,
                                               timeout=constants.WEBUI_RUNNER_STOPPED_TIMEOUT,
                                               critical=False)
            except:
                _log.exception("_runner_stopped_notification() failed")

        #
        #  In the activation use case this fails needlessly
        #

        @db.transact()  # reactor callLater
        def _restart_runner(unclean_restart):
            _log.info('restarting l2tp runner: unclean=%s' % unclean_restart)
            if unclean_restart:
                # inform watchdog
                self.watchdog.runner_restart_was_required()

            self._dyndns_address = None
            self._dyndns_address_timestamp = None
            self._dyndns_resolve_in_progress = False  # paranoia

            self.l2tpmanager.start()
            self._ajax_helper.wake_status_change_waiters()

        # XXX: backoff would be good here

        self._ajax_helper.wake_status_change_waiters()

        _runner_stopped_notification(None)
        
        # In activation use case (activateconfiguration.xhtml) the
        # activation code handles restart itself, so do nothing here.
        # This is a pretty ugly check.
        try:
            if self._activate_configuration_state[3]:  # active
                # activation use case handles restart; this is pretty unclean,
                # refactor to better shape
                pass
            elif self._service_active:
                # XXX: fixed 10 second delay
                reactor.callLater(10.0, _restart_runner, True)
            else:
                _log.debug('not restarting runner, service is inactive')
        except:
            _log.exception('failed to check if runner restart was required, service may stay inactive.')

    @db.untransact()
    def _do_timesync(self, utc_time):
        # XXX: if time step is too large, we need to take some measures here to prevent twisted problems
        # (Twisted does not handle time jumps correctly; if time goes backwards, timers become frozen).
        # One relatively benign fix here would be to reschedule all critical timers, such as the watchdog.
        # A more brute force fix would be to restart the web UI.
        try:
            full_sync = timesync.update_system_time(utc_time,
                                                    cap_backwards=constants.WEBUI_TIMESYNC_CAP_BACKWARDS,
                                                    cap_forwards=constants.WEBUI_TIMESYNC_CAP_FORWARDS)

            if full_sync:
                helpers.write_datetime_marker_file(constants.WEBUI_LAST_TIMESYNC_FILE)
            else:
                # probably capped, don't write marker because it would enable RRD with bogus system time
                _log.info('timesync not full (probably capped), not writing webui timesync file')
            
            # notify if time difference is still too large (jump was capped too heavily)
            now = datetime.datetime.utcnow()
            timediff = utc_time - now
            if timediff < datetime.timedelta(0, 0, 0):
                timediff = -timediff
            if (timediff > constants.WEBUI_TIMESYNC_NOTIFY_LIMIT) and (not self._timesync_notify_shown):
                try:
                    from codebay.l2tpserver import gnomehelpers
                    gnomehelpers.show_notification(constants.WEBUI_TIMESYNC_NOTIFY_TITLE,
                                                   constants.WEBUI_TIMESYNC_NOTIFY_TEXT,
                                                   timeout=constants.WEBUI_TIMESYNC_NOTIFY_TIMEOUT,
                                                   critical=False)

                    # NB: it is important to do this after show_notification(); if, for instance,
                    # boot is in progress, the initial notification will fail and a notification
                    # will only be shown on reidentify.  Not ideal, but at least the notification
                    # will not be completely hidden.
                    self._timesync_notify_shown = True
                except:
                    _log.exception("_do_timesync(): failed to show notify of time jump")
        except:
            _log.exception('time sync failed')

    def management_connection_up(self, identify_result):   # from managementconnection
        _log.info('management connection established')

        if identify_result is None:
            _log.warning('identify result is None, connect() or start_primary() called twice? ignoring')
            return

        try:
            helpers.write_cookie_uuid(identify_result['cookieUuid'])
        except:
            _log.exception('failed to write cookie UUID')
            
        try:
            self._license_helper.update_license_info(identify_result)
        except:
            _log.exception('license info update failed')

        try:
            self._update_update_info(identify_result)
        except:
            _log.exception('update update info failed')

        try:
            self._do_timesync(identify_result['currentUtcTime'])
        except:
            _log.exception('timesync failed')

        try:
            self._immediate_auto_update_check(identify_result)
        except:
            _log.exception('immediate auto update check failed')
            
        try:
            self._write_connection_state(identify_result)
        except:
            _log.exception('write connection state failed')
            
        # XXX: If license parameters have changed, we might ideally want to
        # make the protocol part react somehow.  Currently we just apply the
        # changed license to new connections, not old ones.

        # Wake up Ajax waiters
        self._ajax_helper.wake_status_change_waiters()

        # Boot code (update) needs a snapshot of a "known good" network config.
        # If the management connection comes up, we are quite sure the config
        # is good, at least for updating.
        if self.l2tpmanager.isRunning():
            try:
                self._export_rdf_database()
            except:
                _log.exception('failed to export rdf database')

        # If we don't have a test license at this point, request one now
        try:
            self._test_license_check()
        except:
            _log.exception('_test_license_check failed')

        # XXX: to ensure that the test license makes it to the exported "known good"
        # configuration ASAP, we might want to export the known good configuration
        # again when the test license is received.

        try:
            helpers.get_global_status().setS(ns.managementServerConnection, rdf.Boolean, True)
        except:
            _log.exception('cannot set management connection rdf status to up')

    def management_connection_reidentify(self, identify_result):   # from managementconnection
        _log.info('management connection reidentify')

        if identify_result is None:
            _log.warning('identify result is None, connect() or start_primary() called twice? ignoring')
            return

        try:
            helpers.write_cookie_uuid(identify_result['cookieUuid'])
        except:
            _log.exception('failed to write cookie UUID')

        try:
            self._license_helper.update_license_info(identify_result)
        except:
            _log.exception('license info update failed')

        try:
            self._update_update_info(identify_result)
        except:
            _log.exception('update update info failed')

        try:
            self._do_timesync(identify_result['currentUtcTime'])
        except:
            _log.exception('timesync failed')

        try:
            self._immediate_auto_update_check(identify_result)
        except:
            _log.exception('immediate auto update check failed')

        self._ajax_helper.wake_status_change_waiters()

        # no check for test license, no rdf export in reidentify

    def management_connection_down(self, reason=None):  # from managementconnection
        _log.info('management connection down, reason: %s' % reason)

        try:
            helpers.get_global_status().setS(ns.managementServerConnection, rdf.Boolean, False)
        except:
            _log.exception('cannot set management connection rdf status to down')

        # 'reason' can be many things, including protocol errors from Identify(),
        # check for them here
        try:
            self._license_helper.process_failure_reason(reason)
        except:
            _log.exception('failed to check management_connection_down reason')

        self._ajax_helper.wake_status_change_waiters()

    def set_ssl_contextfactory(self, cf):
        self._ssl_cf = cf

    def get_ssl_contextfactory(self):
        return self._ssl_cf

    def reread_ssl_files(self):
        if self._ssl_cf is not None:
            self._ssl_cf.reread_files()
        else:
            _log.warning('reread_ssl_files(): no ssl context factory')

    def get_uptime(self):
        """Get uptime relative to time synchronized boot timestamp file."""

        return helpers.get_uptime()

    def add_status_change_waiter(self, d):
        return self._ajax_helper.add_status_change_waiter(d)

    # XXX: change name to "public", used by watchdog
    def _export_rdf_database(self):
        _log.info('_export_rdf_database() called')

        try:
            uihelpers.export_rdf_database_to_file(constants.EXPORTED_RDF_DATABASE_FILE, remove_status=True)
            self._last_rdf_database_export = datetime.datetime.utcnow()
        except:
            _log.exception('failed to export rdf database file')

    def _update_update_info(self, res):
        root = helpers.get_db_root()
        update = root.getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))

        # update changelog
        update.setS(ns_ui.changeLog, rdf.String, res['changeLog'])

        # update latest known version
        t = versioninfo.get_changelog_info(changelog=res['changeLog'])
        if len(t) < 1:
            # XXX: raise or just ignore with warning?
            raise Exception('changeLog information from server is empty, not updating changelog info')
        
        latest_version = t[0][0]   # first entry is assumed to be latest
        helpers.parse_product_version(latest_version)  # excepts if not valid
        update.setS(ns_ui.latestKnownVersion, rdf.String, latest_version)

    def _immediate_auto_update_check(self, identify_result):
        update_now = identify_result['updateImmediately']

        # XXX: If this debug marker exists, autoupdate is forced if newer is available.
        if os.path.exists(constants.AUTOUPDATE_MARKERFILE):
            curr_ver = helpers.get_product_version()
            latest_ver = uihelpers.get_latest_product_version()
            if (curr_ver is not None) and (latest_ver is not None) and (helpers.compare_product_versions(latest_ver, curr_ver) > 0):
                _log.info('detected that update is available (%s -> %s), immediate automatic update' % (curr_ver, latest_ver))
                update_now = True

        if update_now:
            # take action
            _log.info('management server has requested immediate update, forced check for updates now, rebooting')
            helpers.db_flush()
            uihelpers.ui_reboot('immediate autoupdate', skip_update=False, force_update=True, force_fsck=True, delay=0.0)
        
    def _write_connection_state(self, identify_result):
        behind_nat = identify_result['behindNat']
        our_addr = identify_result['clientAddressSeenByServer']

        global_st = helpers.get_global_status()
        global_st.setS(ns.behindNat, rdf.Boolean, behind_nat)
        global_st.setS(ns.managementConnectionOurNattedAddress, rdf.IPv4Address, datatypes.IPv4Address.fromString(our_addr))
        
    def _test_license_check(self):
        # do we have a test license yet?
        try:
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.testLicenseKey):
                t = ui_root.getS(ns_ui.testLicenseKey, rdf.String)
                if t is not None and t != '':
                    _log.debug('already have a test license (%s), no action needed' % t)
                    return
        except:
            _log.exception('checking for existing test license failed')
            pass

        # no, try to get one (note that we get one even if we have a valid license,
        # because we want to fix the "unique" test license timestamp asap)
        _log.info('no test license yet, requesting a test license')

        @db.transact()
        def _callback(res):
            t = res['licenseKey']
            _log.info('received test license: %s' % t)

            # parse the test license: we don't want to "taint" rdf with an invalid license
            license_ok = False
            try:
                from codebay.common import licensekey
                val, broken = licensekey.decode_license(t)
                if val is None:
                    raise Exception('license is broken, groups: %s' % broken)
                license_ok = True
            except:
                _log.exception('test license is broken, ignoring')
            
            # store test license & force reidentify
            if license_ok:
                _log.info('received test license passes sanity check, storing')
                ui_root = helpers.get_ui_config()
                ui_root.setS(ns_ui.testLicenseKey, rdf.String, t)

                ign = self.managementconnection.trigger_reidentify() # returns deferred

            # re-export database
            if license_ok:
                @db.untransact()
                def _export():
                    try:
                        self._export_rdf_database()
                    except:
                        _log.exception('failed to export rdf database (test license assigned)')
                _export()
                
        @db.transact()
        def _failed(reason):
            _log.info('request for test license failed: %s' % reason)
            
        d = self.managementconnection.request_test_license()
        d.addCallback(_callback)
        d.addErrback(_failed)
        return d
        
# --------------------------------------------------------------------------

class WebUiService(service.Service):
    """Service class for web UI."""
    def __init__(self, original):
        self.master = original

    def startService(self):
        @db.transact()
        def _start_master(res):
            _log.debug('Master service starting.')
            rv = self.master.start()  # may be deferred
            _log.debug('retval=%s' % rv)
            return rv

        @db.transact()
        def _start_complete(res):
            _log.info('Master service start complete')
            return res
        
        # create a Deferred of shutdown tasks and let Twisted run it
        d = defer.Deferred()
        d.addCallback(_start_master)
        d.addCallback(_start_complete)
        d.callback(None)
        return d
    
    def stopService(self):
        @db.transact()
        def _stop_master(res):
            _log.debug('Master service stopping.')
            rv = self.master.stop()  # may be deferred
            _log.debug('retval=%s' % rv)
            return rv
        
        @db.transact()
        def _stop_complete(res):
            _log.info('Master service stop complete')
            return res
        
        # create a Deferred of shutdown tasks and let Twisted run it
        d = defer.Deferred()
        d.addCallback(_stop_master)
        d.addCallback(_stop_complete)
        d.callback(None)
        return d

# --------------------------------------------------------------------------

class LiveCdMaster(CommonMaster):
    """Dummy master for Live CD."""
    def __init__(self):
        pass

# --------------------------------------------------------------------------

class LiveCdService(service.Service):
    """Dummy service for Live CD."""
    def __init__(self, original):
        self.master = original

    def startService(self):
        pass
    
    def stopService(self):
        pass

