"""Crontab functions.

Wrapper scripts are supposed to import this module and run appropriate
crontab functions from here.  All the main functionality w.r.t. to crontab
should reside here.

"""

import os, time, signal
import datetime

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import interfacehelper
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import graphs
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui

run_command = runcommand.run_command

# See discussion fo run_minutely() why we want to delay obtaining a logger.
# _setup_logging() must be called before any log calls.
_log = None
def _setup_logging():
    global _log
    if _log is None:
        _log = logger.get('l2tpserver.crontab')

# --------------------------------------------------------------------------

def _check_draw_graph(graph_file):
    """Check whether the specified graph file should be redrawn.

    Currently we use the following heuristic: (1) if graph is older than N
    minutes, redraw it;  (2) if admin has active session(s), redraw on every
    cron run (we detect this by ajax active timestamp).

    We could also redraw if an interesting parameter has changed (user or s2s
    count, license limits, timezones, etc).  But because these entail RRD accesses,
    we just use the simpler heuristic above.
    """

    now = datetime.datetime.utcnow()

    # consider ajax "off-line" if timestamp older than this (or negative)
    ajax_limit = datetime.timedelta(0, 5*60, 0)   # XXX: constants?

    # redraw graphs if graph age below zero or over limit below
    graph_zero = datetime.timedelta(0, 0, 0)
    graph_maxage = datetime.timedelta(0, 15*60, 0) # XXX: constants?
    
    if helpers.check_marker_file(constants.WEBUI_ADMIN_ACTIVE_TIMESTAMP):
        dt = helpers.read_datetime_marker_file(constants.WEBUI_ADMIN_ACTIVE_TIMESTAMP)
        diff = now - dt
        if diff < ajax_limit:
            # ajax active, draw
            _log.info('ajax active, redraw graph %s' % graph_file)
            return True
        else:
            # fall through, check graph file
            pass
        
    if os.path.exists(graph_file):
        mtime = datetime.datetime.utcfromtimestamp(os.stat(graph_file).st_mtime)
        diff = now - mtime
        if (diff < graph_zero) or (diff > graph_maxage):
            # bogus or too old, redraw
            _log.info('graph too old, redraw graph %s' % graph_file)
            return True
        else:
            _log.info('graph not too old, skipping redraw for %s' % graph_file)
            return False
        
    # no graph file, redraw always
    _log.info('graph does not exist, redraw graph %s' % graph_file)
    return True

# --------------------------------------------------------------------------

def _update_graphs(quick=False):
    """Update RRD data and web UI graphs."""

    if os.path.exists(constants.LOWMEM_MARKER_FILE):
        _log.debug('lowmem marker exists, not updating graphs')
        return

    # measure and update rrd data
    g = graphs.Graphs()
    try:
        if helpers.check_marker_file(constants.TIMESYNC_TIMESTAMP_FILE) or \
           helpers.check_marker_file(constants.WEBUI_LAST_TIMESYNC_FILE):
            _log.debug('timesync ok, updating rrd')
            update_rrd = True
        else:
            # If rrdtool is updated with a future timestamp (say Jan 1, 2010) it will
            # refuse to update values in the 'past' (say Jan 1, 2007); so we only want
            # to run rrd updates if we do have a server-based timesync.
            _log.info('no timesync, not updating rrd information to avoid confusing rrdtool')
            update_rrd = False

        g.measure_and_update(update_rrd=update_rrd, update_rdf=True, quick=quick)
    except:
        _log.exception('measure_and_update() failed')

    # draw graphs required by web UI here, but only if it "makes a difference"
    try:
        if _check_draw_graph(constants.RRDGRAPH_USER_COUNT):
            g.draw_user_graph()
        else:
            _log.info('not drawing user graph on this cron run')
    except:
        _log.exception('draw_user_graph() failed')
    try:
        if _check_draw_graph(constants.RRDGRAPH_SITETOSITE_COUNT):
            g.draw_sitetosite_graph()
        else:
            _log.info('not drawing user graph on this cron run')
    except:
        _log.exception('draw_sitetosite_graph() failed')

def _draw_debug_graphs():
    g = graphs.Graphs()
    try:
        g.draw_debug_graphs()
    except:
        _log.exception('draw_debug_graphs() failed')
        
@db.transact()
def _update_snmp():
    """Update SNMP data."""

    from codebay.l2tpserver import licensemanager
    from codebay.l2tpserver import helpers
    from codebay.l2tpserver.webui import uihelpers

    now = datetime.datetime.utcnow()
    st = helpers.get_status()
    global_st = helpers.get_global_status()
    license_info = helpers.get_license_info()

    def _timeticks(td):
        return int(helpers.timedelta_to_seconds(td) * 100.0)

    def _timestamp(dt):
        return datatypes.encode_datetime_to_iso8601_subset(dt)

    def _get_management_conn():
        # XXX: not the best place for this
        if global_st.hasS(ns.managementServerConnection):
            if global_st.getS(ns.managementServerConnection, rdf.Boolean):
                return 1
        return 0
        
    vals = {}

    lm = licensemanager.LicenseMonitor()
    usr_count, usr_limit, usr_limit_leeway, s2s_count, s2s_limit, s2s_limit_leeway = None, None, None, None, None, None
    try:
        usr_count, usr_limit, usr_limit_leeway, s2s_count, s2s_limit, s2s_limit_leeway = lm.count_both_users()
    except:
        _log.exception('cannot get ppp counts for snmp')

    # XXX: this sharing of status code is quite unclean; see uihelpers.get_status_and_substatus() for suggestions
    health_errors = 0
    try:
        status_class, status_text, substatus_class, substatus_text, status_ok = uihelpers.get_status_and_substatus()
        if status_ok:
            health_errors = 0
        else:
            health_errors = 1
    except:
        _log.exception('cannot determine health errors')
    
    for k, l in [ ('vpneaseHealthCheckErrors',       lambda: health_errors),
                  ('vpneaseUserCount',               lambda: usr_count),
                  ('vpneaseSiteToSiteCount',         lambda: s2s_count),
                  ('vpneaseLastMaintenanceReboot',   lambda: _timestamp(helpers.read_datetime_marker_file(constants.LAST_AUTOMATIC_REBOOT_MARKER_FILE))),
                  ('vpneaseNextMaintenanceReboot',   lambda: _timestamp(uihelpers.compute_periodic_reboot_time())),
                  ('vpneaseLastSoftwareUpdate',      lambda: _timestamp(helpers.read_datetime_marker_file(constants.LAST_SUCCESSFUL_UPDATE_MARKER_FILE))),
                  ('vpneaseSoftwareVersion',         lambda: helpers.get_product_version(cache=True, filecache=True)),
                  ('vpneaseCpuUsage',                lambda: int(global_st.getS(ns.cpuUsage, rdf.Float))),
                  ('vpneaseMemoryUsage',             lambda: int(global_st.getS(ns.memoryUsage, rdf.Float))),
                  ('vpneaseVirtualMemoryUsage',      lambda: int(global_st.getS(ns.swapUsage, rdf.Float))),
                  ('vpneaseServiceUptime',           lambda: _timeticks(now - st.getS(ns.startTime, rdf.Datetime))),
                  ('vpneaseHostUptime',              lambda: _timeticks(datetime.timedelta(0, helpers.get_uptime(), 0))),
                  ('vpneasePublicAddress',           lambda: st.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).getAddress().toString()),
                  ('vpneasePublicSubnet',            lambda: st.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).getMask().toString()),
                  ('vpneasePublicMac',               lambda: st.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.macAddress, rdf.String)),
                  ('vpneasePrivateAddress',          lambda: st.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).getAddress().toString()),
                  ('vpneasePrivateSubnet',           lambda: st.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).getMask().toString()),
                  ('vpneasePrivateMac',              lambda: st.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.macAddress, rdf.String)),
                  ('vpneaseLicenseKey',              lambda: license_info.getS(ns_ui.licenseKey, rdf.String)),
                  ('vpneaseLicenseString',           lambda: license_info.getS(ns_ui.licenseString, rdf.String)),
                  ('vpneaseLicenseUserLimit',        lambda: usr_limit),
                  ('vpneaseLicenseSiteToSiteLimit',  lambda: s2s_limit),
                  ('vpneaseMaintenanceReboots',      lambda: global_st.getS(ns.periodicReboots, rdf.Integer)),
                  ('vpneaseWatchdogReboots',         lambda: global_st.getS(ns.watchdogReboots, rdf.Integer)),
                  ('vpneaseLicenseServerConnection', _get_management_conn),
                  ]:
        try:
            val = l()
            if val is not None:
                vals[k] = val
        except:
            # these are expected in several cases, so don't spew too much log about them
            # XXX: it would be better if the checkers would figure these out for themselves
            # (when a value is expected and when not)
            _log.info('failed to get snmp value for key %s' % k)
            #_log.exception('failed to get snmp value for key %s' % k)
                  
    keys = vals.keys()
    keys.sort()
    res = ''
    for k in keys:
        res += '%s=%s\n' % (k, vals[k])

    # to ASCII, escaping any non-ASCII chars with XML escapes
    res = res.encode('US-ASCII', 'xmlcharrefreplace')

    f = None
    try:
        f = open(constants.SNMP_DATA_FILE, 'wb')
        f.write(res)
    finally:
        if f:
            f.close()
        f = None

def _check_ui_health():
    """Check UI process health and reboot if required.
    """

    def _reset_failure_count():
        try:
            run_command([constants.CMD_RM, '-f', constants.CRON_WEBUI_FAILURE_COUNT_FILE])
        except:
            _log.exception('_reset_failure_count failed')

    def _reboot():
        """Reboot system after web UI health check failure.

        Only reboot if the boot timestamp is old enough to ensure that (a) we don't panic
        when the system is just starting up, and (b) if there is a reboot loop, slow it
        down to something manageable.

        Resets the failure count even when reboot is not done so that later errors would
        not cause immediate reboot after.
        """

        try:
            if os.path.exists(constants.BOOT_TIMESTAMP_FILE):
                f = open(constants.BOOT_TIMESTAMP_FILE, 'r')
                boottime = datatypes.parse_datetime_from_iso8601_subset(f.readline().strip())
                _log.info('_reboot: last boot timestamp: %s' % boottime)
                currenttime = datetime.datetime.utcnow()
                _log.info('_reboot: current time %s' % currenttime)
                runtime = currenttime - boottime
                _log.info('_reboot: running time: %s (limit: %s)' % (runtime, constants.CRON_BOOTTIME_FAILURE_WAIT))
                if runtime < constants.CRON_BOOTTIME_FAILURE_WAIT and runtime > constants.ZERO_TIMEDELTA:
                    _log.info('_reboot: too soon to reboot despite UI health check failures')
                    _reset_failure_count()
                    return
        except:
            _log.exception('_reboot: failed to check boot timestamp, rebooting anyway')

        _log.warning('_reboot: rebooting due to UI health check failures')
        _reset_failure_count()

        # Launch a notify in the background: may or may not work
        try:
            run_command(['%s watchdognotify 1>/dev/null 2>/dev/null &' % constants.CMD_L2TPGW_CRON], shell=True)
        except:
            _log.exception('failed to launch notify in the background')

        # Simulate normal update behaviour and force fsck on next
        # boot
        try:
            if os.path.exists(constants.UPDATE_FORCE_MARKER_FILE):
                os.unlink(constants.UPDATE_FORCE_MARKER_FILE)
            if os.path.exists(constants.UPDATE_SKIP_MARKER_FILE):
                os.unlink(constants.UPDATE_SKIP_MARKER_FILE)
            if os.path.exists(constants.FASTBOOT_MARKER_FILE):
                os.unlink(constants.FASTBOOT_MARKER_FILE)
            helpers.write_datetime_marker_file(constants.FORCE_FSCK_MARKER_FILE)
        except:
            _log.exception('marker file cleanup failed, but we reboot anyway')

        # Give some time for notify to show
        try:
            _log.info('sleeping %s seconds before rebooting' % constants.CRON_WATCHDOG_REBOOT_DELAY)
            time.sleep(constants.CRON_WATCHDOG_REBOOT_DELAY)
        except:
            _log.exception('failed to sleep in cron watchdog action, ignoring')

        # Flush syslog to disk
        try:
            _log.info('flushing syslog to disk')
            pid = int(open(constants.SYSLOG_PIDFILE, 'rb').read().strip()) # do not care of fd leak here
            os.kill(pid, signal.SIGHUP)
            time.sleep(1)
        except:
            _log.exception('failed to flush syslog, ignoring')

        # Sync disk and force reboot: this avoids possible start/stop
        # system script blocking
        try:
            run_command(constants.CMD_SYNC)
            run_command(constants.CMD_SYNC)
            run_command(constants.CMD_SYNC)
        except:
            _log.exception('failed to do filesystem sync, ignoring')

        run_command([constants.CMD_REBOOT, '-f', '-d'])

    def _failure(reason='unknown reason'):
        """Update failure count and reboot if limit is reached."""

        _log.warning('web UI health check failed: %s' % reason)

        try:
            if not os.path.exists(constants.CRON_WEBUI_FAILURE_COUNT_FILE):
                count = 1
                f = open(constants.CRON_WEBUI_FAILURE_COUNT_FILE, 'w')
                f.write('%s\n' % str(count))
                f.close()

                _log.info('web UI health check failure count now: %s' % count)
            else:
                f = open(constants.CRON_WEBUI_FAILURE_COUNT_FILE, 'r')
                count = int(f.readline().strip())
                f.close()

                count += 1

                _log.info('web UI health check failure count now: %s' % count)
                
                f = open(constants.CRON_WEBUI_FAILURE_COUNT_FILE, 'w')
                f.write('%s\n' % str(count))
                f.close()

                if count > 3 or count < 1:
                    _reboot()
        except:
            _log.warning('failed to handle health check failure properly, rebooting')
            _reboot()

    # skip checks if Live CD
    if os.path.exists(constants.LIVECD_MARKER_FILE):
        return

    # web UI should always be running
    if not os.path.exists(constants.WEBUI_PIDFILE):
        _failure('UI pidfile missing')
        return

    # check that web UI process is alive
    try:
        f = open(constants.WEBUI_PIDFILE, 'r')
        pid = int(f.readline().strip())
        f.close()
        if os.system(constants.CMD_KILL + " -0 " + str(pid)) != 0:
            _failure('UI process missing')
            return
    except:
        _failure('Invalid UI pidfile')
        return

    # check that web UI watchdog is active enough
    if not os.path.exists(constants.WEBUI_WATCHDOG_LAST_UPDATED_FILE):
        _failure('UI watchdog markerfile missing')
        return
    f = open(constants.WEBUI_WATCHDOG_LAST_UPDATED_FILE, 'r')
    checktime = datatypes.parse_datetime_from_iso8601_subset(f.readline().strip())
    _log.debug('last webui watchdog timestamp: %s' % checktime)
    currenttime = datetime.datetime.utcnow()
    _log.debug('current time: %s' % currenttime)
    age = currenttime - checktime
    _log.debug('webui watchdog timestamp age: %s (limit: %s)' % (age, constants.CRON_WEBUI_WATCHDOG_TIMEOUT))
    if age > constants.CRON_WEBUI_WATCHDOG_TIMEOUT or age <= constants.ZERO_TIMEDELTA:
        _failure('UI watchdog markerfile too old.')
        return

    # health check ok
    _reset_failure_count()
    _log.debug('UI health check passed')
    
@db.transact()
def _rdf_database_stats():
    """Log useful statistics about RDF database to syslog."""

    try:
        root = db.get_db().getRoot()
        model = root.model  # XXX: cleaner?
        count, reachable = model.getPruneStatistics(root)
        unreachable = count - reachable
        
        db_size = os.stat(constants.PRODUCT_DATABASE_FILENAME).st_size

        # XXX: division by zero is not a real concern, and we're in try-except anyway

        _log.info('DATABASEINFO: ' \
                  'filesize=%.1f MiB (%d), ' \
                  'total stmts %d, reachable stmts %d (%.1f%%), unreachable stmts %d (%.1f%%), ' \
                  'bytes per reachable stmt avg %.1f, bytes per any stmt avg %.1f' % \
                  (db_size/(1024.0*1024.0), db_size,
                   count, reachable, float(reachable)/float(count)*100.0, unreachable, float(unreachable)/float(count)*100.0,
                   float(db_size)/float(reachable), float(db_size)/float(count)))
    except:
        _log.exception('failed to get rdf database stats')

def _interface_stats():
    try:
        up_ifaces = interfacehelper.get_interfaces().get_interface_list()
        all_ifaces = interfacehelper.get_all_interfaces().get_interface_list()

        [rv, raw_table, err] = run_command([constants.CMD_IPTABLES_SAVE, '-t', 'raw'], retval=runcommand.FAIL)
        [rv, mangle_table, err] = run_command([constants.CMD_IPTABLES_SAVE, '-t', 'mangle'], retval=runcommand.FAIL)
        [rv, nat_table, err] = run_command([constants.CMD_IPTABLES_SAVE, '-t', 'nat'], retval=runcommand.FAIL)
        [rv, filter_table, err] = run_command([constants.CMD_IPTABLES_SAVE, '-t', 'filter'], retval=runcommand.FAIL)

        raw_len = len(raw_table.split('\n'))
        mangle_len = len(mangle_table.split('\n'))
        nat_len = len(nat_table.split('\n'))
        filter_len = len(filter_table.split('\n'))

        _log.info('NETWORKINFO: ' \
                  'all interfaces: %d, ' \
                  'up interfaces: %d, ' \
                  'iptables size: %d (raw: %d, mangle: %d, nat: %d, filter: %d)',
                  len(all_ifaces),
                  len(up_ifaces),
                  raw_len + mangle_len + nat_len + filter_len,
                  raw_len, mangle_len, nat_len, filter_len)

    except:
        _log.exception('failed to get network stats')

# --------------------------------------------------------------------------

def run_prerun():
    _setup_logging()
    if helpers.is_live_cd():
        _log.info('live cd, skipping cron action')
        return
    
    _update_graphs(quick=True)

def run_minutely():
    # We want to do the cron watchdog check immediately for two reasons
    # First, we don't want to do any RDF operations before we're happy
    # with the watchdog check, as we may get stuck otherwise.  Second,
    # we don't want to do any log operations either, as opening the log
    # device when the syslog daemon is missing causes trouble.  Hence,
    # we run watchdog checks, and try to log any interesting things
    # after a possible watchdog action has been initiated.
    #
    # Also, sqlite-based RDF database may cause some trouble here.  Watchdog
    # check is not dependent on RDF, but graph update is and may block for a
    # long time if a lock is held by someone.  Further, sqlite does not ensure
    # fairness for those competing for database access, so we may starve or
    # become a bit hungry here.
    #
    # However, cron happily starts multiple instances of this script in parallel
    # (once every minute), so even if we deadlock to RDF database, the watchdog
    # here will successfully reboot.

    # XXX: _check_ui_health() is currently not fixed to work with it, but
    # this would ideally happen after the _check_ui_health() call
    _setup_logging()
    if helpers.is_live_cd():
        _log.info('live cd, skipping cron action')
        return

    _check_ui_health()

    # XXX: graphs update may take time in which case we do not want to start
    # new update again while the old is still running
    if os.path.exists(constants.CRON_MINUTELY_RUNNING_MARKERFILE):
        _log.warning('detected cron run_minutely still running, stopping before actual operations')
        return

    try:
        helpers.write_datetime_marker_file(constants.CRON_MINUTELY_RUNNING_MARKERFILE)
        try:
            _update_graphs(quick=False)
        except:
            _log.exception('graph update failed')
        try:
            _update_snmp()
        except:
            _log.exception('snmp update failed')
    finally:
        if os.path.exists(constants.CRON_MINUTELY_RUNNING_MARKERFILE):
            os.unlink(constants.CRON_MINUTELY_RUNNING_MARKERFILE)

def run_everyfiveminutes():
    _setup_logging()
    if helpers.is_live_cd():
        _log.info('live cd, skipping cron action')
        return
    
    if os.path.exists(constants.DEBUGGRAPHS_MARKERFILE):
        _draw_debug_graphs()

def run_hourly():
    _setup_logging()
    if helpers.is_live_cd():
        _log.info('live cd, skipping cron action')
        return
    
    _rdf_database_stats()
    _interface_stats()

def show_cron_watchdog_notify():
    _setup_logging()
    if helpers.is_live_cd():
        _log.info('live cd, skipping cron action')
        return
    _log.warning('trying to show cron watchdog notify')

    try:
        from codebay.l2tpserver import gnomehelpers
        gnomehelpers.show_notification(constants.CRON_WATCHDOG_WARNING_TITLE,
                                       constants.CRON_WATCHDOG_WARNING_TEXT,
                                       timeout=constants.CRON_WATCHDOG_WARNING_TIMEOUT,
                                       critical=True)
    except:
        _log.exception("show_cron_watchdog_notify() failed")

