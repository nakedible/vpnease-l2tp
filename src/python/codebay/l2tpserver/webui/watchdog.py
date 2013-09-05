"""
Web UI watchdog.
"""
__docformat__ = 'epytext en'

import os, datetime

from twisted.internet import task

from codebay.common import rdf
from codebay.common import logger
from codebay.common import randutil

from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.watchdog')

# --------------------------------------------------------------------------

class WebUiWatchdog:
    """Web UI watchdog.

    This is the primary top-level watchdog of the product.  Crontab
    scripts perform a secondary task of ensuring that the web UI
    watchdog is up and running, i.e., that web UI is not stuck waiting
    for RDF access, for instance.

    Watchdog also currently re-exports current configuration periodically
    if the management connection is up and running.  This is to minimize
    the difference between running config and backed up configuration, e.g.
    for configuration recovery situations.
    """
    def __init__(self, master):
        self.master = master
        self._watchdog_call = None
        self._watchdog_rounds = 0
        self._watchdog_strikes = 0
        self._runner_restarts = 0
        self._periodic_reboot_stagger_delta = datetime.timedelta(0, randutil.random_int(45*60), 0)  # 0 to 45 mins
        self._periodic_reboot_started = False
        self._watchdog_action_started = False
        _log.info('periodic reboot stagger timedelta: %s' % self._periodic_reboot_stagger_delta)
        
    def start_watchdog(self):
        """Start watchdog background task."""

        @db.transact()
        def _timer_stopped(res):
            _log.debug('start_watchdog(): timer stopped (deferred called)')    

        self._watchdog_call = task.LoopingCall(self.run_watchdog)
        d = self._watchdog_call.start(constants.WEBUI_WATCHDOG_INTERVAL, now=False)   # don't run immediately
        d.addCallback(_timer_stopped)
        # ignore d

    def stop_watchdog(self):
        """Stop watchdog background task."""
        if (self._watchdog_call is not None) and (self._watchdog_call.running):
            self._watchdog_call.stop()
        self._watchdog_call = None
        
    def get_watchdog_rounds(self):
        return self._watchdog_rounds
    
    def runner_restart_was_required(self):
        """Called by master when protocol runner restart was required for recovery
        (i.e., unclean runner exit).

        Watchdog is responsible for interpreting these events and determine whether
        a watchdog action is required.
        """
        _log.debug('runner_restart_required()')
        self._runner_restarts += 1

        helpers.increment_global_status_counter(ns.uncleanRunnerExits)

    def _watchdog_show_warning(self):
        """Show watchdog warning in any way possible."""

        _log.warning('watchdog warning')
        try:
            from codebay.l2tpserver import gnomehelpers
            gnomehelpers.show_notification(constants.WEBUI_WATCHDOG_WARNING_TITLE,
                                           constants.WEBUI_WATCHDOG_WARNING_TEXT,
                                           timeout=constants.WEBUI_WATCHDOG_WARNING_TIMEOUT,
                                           critical=True)
        except:
            _log.exception("_watchdog_show_warning() failed")
            
    def _watchdog_show_cancel(self):
        """Show watchdog cancellation in any way possible."""

        _log.warning('watchdog cancelled')
        try:
            from codebay.l2tpserver import gnomehelpers
            gnomehelpers.show_notification(constants.WEBUI_WATCHDOG_CANCELLED_TITLE,
                                           constants.WEBUI_WATCHDOG_CANCELLED_TEXT,
                                           timeout=constants.WEBUI_WATCHDOG_CANCELLED_TIMEOUT,
                                           critical=False)
        except:
            _log.exception("_watchdog_show_cancel() failed")

    def _watchdog_action(self):
        """Execute watchdog recovery action."""

        if self._watchdog_action_started:
            _log.warning('_watchdog_action: watchdog action already started, skipping')
        else:
            _log.error('_watchdog_action: too many watchdog failures, taking watchdog action: reboot')
            try:
                self._watchdog_action_started = True
                helpers.increment_global_status_counter(ns.watchdogReboots)
                helpers.db_flush()
            except:
                _log.exception('failed to increment counter')
            uihelpers.ui_reboot(constants.WEBUI_WATCHDOG_SHUTDOWN_MESSAGE, skip_update=False, force_update=False, force_fsck=True, delay=10.0)

    def watchdog_action_is_pending(self):
        """Return True if watchdog action is pending.

        If True, watchdog warning level has been reached and warning message has been
        shown (if possible).  This is used by the web UI to determine when to show a
        "reboot imminent" note on the UI.

        Note that a pending state may be cancelled later if the watchdog checks start
        to work correctly again.
        """
        return self._watchdog_strikes >= constants.WEBUI_WATCHDOG_STRIKES_FOR_WARNING

    def _check_runner_alive(self):
        """Watchdog check: if runner is supposed to be running, is it alive and updating status?"""

        _log.debug('_check_runner_alive')

        if self.master.l2tpmanager is not None:
            if self.master.l2tpmanager.isRunning():
                _log.debug('_check_runner_alive: runner is active and should be updating rdf statistics')

                st_root = helpers.get_status()
                polltime = st_root.getS(ns.lastPollTime, rdf.Datetime)
                pollage = datetime.datetime.utcnow() - polltime
                _log.debug('_check_runner_alive: poll age: %s' % pollage)
                if pollage > constants.WEBUI_WATCHDOG_POLL_AGE_THRESHOLD:
                    _log.error('_check_runner_alive: poll age (%s) is too large, runner seems to be stuck' % pollage)
                    return False
                if pollage < datetime.timedelta(0, 0, 0):   # some timezone problem
                    _log.error('_check_runner_alive: poll age (%s) is negative, considering this a failure' % pollage)
                    return False
            elif self.master.l2tpmanager.isStarting():
                runner_starttime = self.master.l2tpmanager.startTime()
                if runner_starttime is None:
                    _log.error('_check_runner_alive: runner is starting and runner start time not available, assuming runner stuck in starting state and considering this as a failure')
                    return False

                runner_in_starting_state = datetime.datetime.utcnow() - runner_starttime
                if runner_in_starting_state > constants.WEBUI_WATCHDOG_RUNNER_STARTING_TIME_LIMIT:
                    _log.error('_check_runner_alive: runner is starting and runner start time stamp is too old (%s), assuming runner stuck in starting state and considering this as a failure' % runner_in_starting_state)
                    return False
                if runner_in_starting_state < datetime.timedelta(0, 0, 0): # may be timezone problem
                    _log.error('_check_runner_alive: runner is starting and runner start time stamp age (%s) is negative, considering this a failure' % runner_in_starting_state)
                    return False

            else:
                _log.debug('_check_runner_alive: runner is inactive, or active but not (yet) updating rdf statistics')
        return True

    def _check_runner_watchdog_status(self):
        """Watchdog check: runner watchdog status, and whether watchdog failures are indicated.

        Only process failures are considered actual problems here.

        Note that a separate runner restart check is made elsewhere; sometimes the recovery
        action is not to reboot (watchdog) but to e.g. restart runner (not watchdog directly).
        This function only checks for the watchdog part.
        """
        
        _log.debug('_check_runner_watchdog_status')

        st_root = helpers.get_status()  # may fail in rare occasions, does not matter
        if st_root.hasS(ns.processHealthCheck):
            if not st_root.getS(ns.processHealthCheck, rdf.Boolean):
                _log.error('_check_runner_watchdog_status: process health check failed, considering this a failure') 
                return False
        return True

    def _check_runner_restart_limit(self):
        """Watchdog check: too many automatic runner restarts.

        This is currently just a counter which never resets or decreases.
        """
        
        _log.debug('_check_runner_restart_limit')

        # this leads to a delayed reboot when runner restart limit has been reached
        _log.debug('_check_runner_restart_limit: restarts %d, limit %d' % (self._runner_restarts, constants.WEBUI_WATCHDOG_RUNNER_RESTART_LIMIT))
        if self._runner_restarts >= constants.WEBUI_WATCHDOG_RUNNER_RESTART_LIMIT:
            _log.error('_check_runner_restart_limit: too many runner restarts, considering this a failure')
            return False
        return True

    def _check_disk_space(self):
        """Watchdog check: disk space."""

        _log.debug('_check_disk_space')

        free = helpers.get_root_free_space_bytes()
        _log.debug('_check_disk_space: free space: %f MiB' % (free/1024.0/1024.0))
        if free < constants.WEBUI_WATCHDOG_DISK_FREE_SPACE_LIMIT:
            _log.error('_check_disk_space: not enough free space on disk (free %f MiB, limit %f MiB), considering this a failure' % \
                       (free/1024.0/1024.0, constants.WEBUI_WATCHDOG_DISK_FREE_SPACE_LIMIT/1024.0/1024.0))
            return False
        return True

    def _check_artificial_failure_marker(self):
        """Watchdog check: artificial failure marker causes watchdog failures for testing."""

        _log.debug('_check_artificial_failure_marker')

        if os.path.exists(constants.WEBUI_WATCHDOG_FORCE_FAILURE_MARKER):
            _log.error('_check_artificial_failure_marker: marker present, considering this a failure')
            return False
        return True

    def _watchdog_checks(self):
        """Run watchdog checks, taking action if necessary.

        Note that periodic reboot is not a watchdog action and is not checked here.
        """

        _log.debug('_watchdog_checks')

        # Count # failures; failures may cause other failures but we don't care:
        # one failure is the same as two.  Exceptions in watchdog checkers are
        # considered non-fatal and are not counted as failures.

        failures = 0
            
        # Check 1: if runner is supposed to be running, is it alive (updating status)?
        try:
            if not self._check_runner_alive():
                failures += 1
        except:
            _log.exception('_watchdog_checks: _check_runner_alive failed, ignoring')

        # Check 2: check runner status and see whether we're happy with it
        try:
            if not self._check_runner_watchdog_status():
                failures += 1
        except:
            _log.exception('_watchdog_checks: _check_runner_watchdog_status failed, ignoring')
            
        # Check 3: runner restart limit
        try:
            if not self._check_runner_restart_limit():
                failures += 1
        except:
            _log.exception('_watchdog_checks: _check_runner_restart_limit failed, ignoring')

        # Check 4: check disk space
        try:
            if not self._check_disk_space():
                failures += 1
        except:
            _log.exception('_watchdog_checks: _check_disk_space failed, ignoring')
            
        # Check 5: artificial failure marker
        try:
            if not self._check_artificial_failure_marker():
                failures += 1
        except:
            _log.exception('_watchdog_checks: _check_artificial_failure_marker failed, ignoring')

        _log.debug('_watchdog_checks: watchdog final failure count: %d' % failures)
        
        # Check failure count and take appropriate action.  Watchdog "strike count"
        # is handled here, as are warnings, cancellations, etc.
        old_strikes = self._watchdog_strikes
        if failures > 0:
            self._watchdog_strikes += 1
            _log.warning('_watchdog_checks: watchdog failure detected, strikes %d (warning %d, action %d)' % \
                         (self._watchdog_strikes,
                          constants.WEBUI_WATCHDOG_STRIKES_FOR_WARNING,
                          constants.WEBUI_WATCHDOG_STRIKES_FOR_ACTION))
            
            if self._watchdog_strikes >= constants.WEBUI_WATCHDOG_STRIKES_FOR_ACTION:
                self._watchdog_action()
            elif self._watchdog_strikes == constants.WEBUI_WATCHDOG_STRIKES_FOR_WARNING:  # note: check for equality, not >=
                self._watchdog_show_warning()
            else:
                _log.debug('_watchdog_checks: not enough strikes for action yet')
        else:
            self._watchdog_strikes = 0
            if old_strikes >= constants.WEBUI_WATCHDOG_STRIKES_FOR_WARNING:
                self._watchdog_show_cancel()
            if old_strikes > 0:
                _log.info('_watchdog_checks: watchdog failure disappeared, strikes now 0')
        _log.debug('_watchdog_checks: watchdog strikes: before: %d, after: %d' % (old_strikes, self._watchdog_strikes))

    def _periodic_reboot_show_warning(self):
        """Show periodic reboot warning in any way possible."""

        _log.warning('periodic reboot warning')
        try:
            from codebay.l2tpserver import gnomehelpers
            gnomehelpers.show_notification(constants.WEBUI_PERIODIC_REBOOT_PENDING_TITLE,
                                           constants.WEBUI_PERIODIC_REBOOT_PENDING_TEXT,
                                           timeout=constants.WEBUI_PERIODIC_REBOOT_PENDING_TIMEOUT,
                                           critical=False)
        except:
            _log.exception("_periodic_reboot_show_warning() failed")

    def _periodic_reboot_check(self):
        """Check for periodic reboot and take action if necessary.

        Tries to be clever and avoid reboot if connections are up.

        Uptime estimation is annoying: if time is changed on this reboot,
        the estimate may be grossly wrong.  To ensure that we don't reboot
        on the first boot (when time is synchronized) uncontrollably, this
        function also checks that enough watchdog rounds have been run to
        warrant a reboot.  The underlying assumption is that web UI has been
        running continuously, which is currently OK because we don't restart
        it ever (cron watchdog will just reboot if UI is down).

        Staggering of reboot is added by randomizing the "minute" of the
        reboot in the range [0,45] (not [0,60] for leeway).  The "minute"
        is randomized when watchdog is created, so it stays the same every
        time for one reboot.  Note that the stagger is effectively only
        applied to the first reboot attempt; next attempts (e.g. next day
        at designated time) will not have a stagger.

        If more staggering behavior is desired, see XXX below.
        """

        uptime = self.master.get_uptime()
        reboot_required = False
        now = datetime.datetime.utcnow()

        _log.debug('_periodic_reboot_check: uptime=%s' % uptime)
        
        # Check whether UI configuration requires a reboot (time & day match)
        try:
            reboot_limit = uihelpers.compute_periodic_reboot_time()
            reboot_limit += self._periodic_reboot_stagger_delta
            _log.debug('_periodic_reboot_check: reboot limit after stagger: %s' % reboot_limit)
            
            lm = licensemanager.LicenseMonitor()
            count, limit, limit_leeway = lm.count_normal_users()

            # time to periodic reboot (negative = past due)
            diff = reboot_limit - now
            _log.debug('_periodic_reboot_check: periodic reboot diff (limit-now, time to reboot): %s' % str(diff))

            if diff <= datetime.timedelta(0, 0, 0):
                overdue = -diff
                _log.debug('_periodic_reboot_check: periodic reboot is %s overdue' % overdue)
                if count > 0:
                    # there are clients (without license restrictions!), give 24h leeway
                    if overdue < datetime.timedelta(1, 0, 0):  # XXX: hardcoded
                        _log.info('_periodic_reboot_check: want to do a periodic reboot, but there are active clients (%d), skipping' % count)
                    else:
                        _log.warning('_periodic_reboot_check: want to a periodic reboot, active clients (%d), but leeway over, rebooting anyway' % count)
                        reboot_required = True
                else:
                    _log.warning('_periodic_reboot_check: want to do a periodic reboot, and no active clients, ok')
                    reboot_required = True
        except:
            _log.exception('_periodic_reboot_check: failed when checking for periodic reboot policy')

        # If not within periodic reboot time window (e.g. 02:00-03:00 local time),
        # skip periodic reboot.
        if reboot_required:
            # XXX: better stagger check could be applied here (checked every day)
            if not uihelpers.check_periodic_reboot_time_window(now):
                _log.warning('_periodic_reboot_check: want to do a periodic reboot, but not within periodic reboot time window')
                reboot_required = False
            
        # If more than a maximum number of days, reboot, despite configuration
        if uptime > constants.PERIODIC_REBOOT_MAX_UPTIME:
            _log.warning('_periodic_reboot_check: uptime is too large (%s), requires reboot' % uptime)
            reboot_required = True
        elif uptime < 0.0:
            # negative uptime: ignore it for now; if the diff is great, we'll get a periodic reboot anyway later
            _log.warning('_periodic_reboot_check: uptime is negative (%s), ignoring' % uptime)

        # Sanity check: if we want to reboot, check that enough watchdog rounds
        # have elapsed (roughly 24h).
        if reboot_required:
            rounds = self.get_watchdog_rounds()
            if rounds < constants.PERIODIC_REBOOT_MINIMUM_WATCHDOG_ROUNDS:
                _log.warning('_periodic_reboot_check: want to do periodic reboot, but watchdog rounds too low (%d < %d)' % (rounds, constants.PERIODIC_REBOOT_MINIMUM_WATCHDOG_ROUNDS))
                reboot_required = False

        # Take action if necessary
        if reboot_required:
            if self._periodic_reboot_started:
                _log.info('_periodic_reboot_check: reboot required but periodic reboot already in progress, no action needed')
            else:
                try:
                    _log.warning('_periodic_reboot_check: periodic reboot started')
                    self._periodic_reboot_started = True
                    self._periodic_reboot_show_warning()
                    helpers.increment_global_status_counter(ns.periodicReboots)
                    helpers.db_flush()
                except:
                    _log.exception('failed to increment counter')

                try:
                    helpers.write_datetime_marker_file(constants.LAST_AUTOMATIC_REBOOT_MARKER_FILE)
                except:
                    _log.exception('failed to write last automatic reboot marker file')

                uihelpers.ui_reboot(constants.WEBUI_PRODUCT_PERIODIC_REBOOT_MESSAGE, skip_update=False, force_update=False, force_fsck=True, delay=120.0)  # XXX: constants

    def periodic_reboot_is_pending(self):
        """Return True if periodic reboot is pending.

        If True, periodic reboot is pending.  This is used by the web UI to determine
        when to show a "reboot imminent" note on the UI.
        """
        return self._periodic_reboot_started
                
    def _update_admin_timestamp(self):
        """Update Web UI admin active timestamp if web UI is currently polling Ajax.

        Used by crontab for graph redraw optimizations (draw graphs frequently
        if admin sessions (= Ajax) is active).
        """

        # XXX: use actual session info; does not work now because of client-side
        # javascript timeout
        if self.master._ajax_helper.have_status_change_waiters():
            helpers.write_datetime_marker_file(constants.WEBUI_ADMIN_ACTIVE_TIMESTAMP)
        
    def _database_export_check(self):
        if self.master._last_rdf_database_export is None:
            # no previous export, management connection cannot be up, so skip
            _log.info('_database_export_check: no previous export, skipping check')
            return

        now = datetime.datetime.utcnow()
        diff = now - self.master._last_rdf_database_export

        do_export = False
        if diff < datetime.timedelta(0, 0, 0):
            _log.warning('_database_export_check: timedelta (%s) negative, re-export' % diff)
            do_export = True
        elif diff > constants.WEBUI_WATCHDOG_RDF_EXPORT_INTERVAL:
            _log.info('_database_export_check: timedelta exceeded (%s > %s), re-export' % (diff, constants.WEBUI_WATCHDOG_RDF_EXPORT_INTERVAL))
            do_export = True

        if not do_export:
            _log.debug('_database_export_check(): no rdf export check')
            return

        if self.master.managementconnection.state != self.master.managementconnection.STATE_CONNECTED:
            _log.info('_database_export_check(): want to re-export rdf, but management connection not up')
            return

        _log.info('_database_export_check(): want to re-export rdf, management connection up, exporting')
        self.master._export_rdf_database()
        
    @db.transact()  # reactor task
    def run_watchdog(self):
        """Run the Web UI master watchdog (and other periodic checks) and take
        action if necessary.

        Web UI is the top-level watchdog element in the product.  This function
        checks that the system is up and running in an acceptable manner, and if
        not, take action (reboot typically).  In particular, this function checks
        that if the runner should be active and it is not (process has exited or
        is stuck), corrective action is taken.

        In addition to this actual watchdog checking, this function also does
        other periodic checks and respective actions.

        In Live CD the watchdog never runs, so no watch warnings or actions will
        be shown either.
        """

        # increase rounds
        self._watchdog_rounds += 1

        _log.debug('run_watchdog(), round %d' % self._watchdog_rounds)

        # update watchdog-last-update file
        try:
            helpers.write_datetime_marker_file(constants.WEBUI_WATCHDOG_LAST_UPDATED_FILE)
        except:
            _log.exception('cannot update webui watchdog file')
                
        # skip tests on livecd
        if self.master.is_live_cd():
            _log.debug('watchdog on live cd, skipping')
            return
        
        # not live cd, normal watchdog
        try:
            self._watchdog_checks()
        except:
            # this should not happen, at least persistently
            _log.exception('watchdog execution failed, ignoring')

        # periodic reboot check
        try:
            self._periodic_reboot_check()
        except:
            _log.exception('periodic reboot check failed, ignoring')

        # update admin active file, if ajax polling is active (needed by graph
        # redraw optimizations in crontab)
        try:
            self._update_admin_timestamp()
        except:
            _log.exception('admin active file update failed, ignoring')

        # database export check
        try:
            self._database_export_check()
        except:
            _log.exception('database export check failed, ignoring')

        # info log even in success case
        _log.info('webui watchdog completed, strikes %d, round %d' % (self._watchdog_strikes, self._watchdog_rounds))
