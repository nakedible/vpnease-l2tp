"""Check update policy from server and run update if necessary; also do timesync.

Configuration network up, gets a management connection, identifies to the management
server, and gets update policy.  If update is required, executes external update script.
Both this script and the update script must be able to work with system python files, or
backup python files (from a zip file).  This difference must be set up to sys.path before
calling stuff here.

If management connection cannot be established, no update is performed.  This is because
we want to centralize update policy to the management server.  It is further unlikely
that the package repository is available but the management server is not.

When an update - successful or not - has been initiated, the host is rebooted.  This
reboot action is done by our caller, based on return values or marker files (see below for
details).  An update is considered to be initiated if the update script has been executed
and the update script has determined that some updates are available.  Merely starting the
update script does not indicate that update has been initiated.

Thist script also does time synchronization, and will be expanded in the future to cover
any network or management server dependent boot-time tasks, since we don't want to set up
and tear down networking and management connection multiple times during boot (simply
because it takes too much time).

Depends on various "side states":
  * RDF database snapshot, written by Web UI from a working configuration.
    This contains network configuration, license key information, etc.
  * Installation and boot UUIDs, read from external files
"""

import os, sys, textwrap, signal, datetime

from twisted.internet import reactor, task, defer, protocol, error

from codebay.common import logger
_log = logger.get('l2tpserver.update.update')

from codebay.common import rdf

from codebay.l2tpserver import constants
from codebay.l2tpserver import versioninfo
from codebay.l2tpserver import aptsource
from codebay.l2tpserver import helpers
from codebay.l2tpserver import timesync
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui

from codebay.l2tpserver import managementconnection
from codebay.l2tpserver.webui import l2tpmanager
from codebay.l2tpserver.webui import master

from codebay.l2tpmanagementprotocol import managementprotocol

run_command = runcommand.run_command


class UpdateError(Exception):
    """Update related error."""

class RdfDatabaseMissingError(UpdateError):
    """Web UI exported RDF database cannot be read, fatal."""
    
class UpdateFailedError(UpdateError):
    """Executed external update script which failed to update properly."""

class UpdateUnknownError(UpdateError):
    """Unknown error."""

class UpdateNotDoneError(UpdateError):
    """Update not done."""

class UpdateDone(UpdateError):
    """Update performed successfully."""
    
class UpdateNotRequired(UpdateError):
    """Update not required."""


class UpdateProcessProtocol(protocol.ProcessProtocol):
    """Handle running of update process."""

    def __init__(self):
        self._waiter = None

    def waitCompleted(self):
        d = defer.Deferred()
        self._waiter = d
        return d
    
    def outReceived(self, data):
        _log.debug('outReceived(): %s' % data)

    def connectionMade(self):
        _log.debug('connectionMade()')

    def processEnded(self, reason):
        e = reason.check(error.ProcessDone, error.ProcessTerminated)
        if e == error.ProcessDone:
            _log.debug('processEnded() -> no errors')
            
            if self._waiter is not None:
                self._waiter.callback(0)
            return
        elif e == error.ProcessTerminated:
            ecode = reason.value.exitCode
            _log.debug('processEnded() -> terminated, exit code %s' % ecode)

            if self._waiter is not None:
                self._waiter.callback(ecode)
            return
        else:
            # unexpected
            _log.debug('processEnded() -> failure: %s' % reason)
            
            if self._waiter is not None:
                self._waiter.errback(reason)

    def sendTerm(self):
        _log.debug('sendTerm()')

        # TERM needs to be sent as an integer (see twisted/internet/interfaces.py)
        self.transport.signalProcess(signal.SIGTERM)


# CommonMaster gives stub implementations to avoid constant method missing errors
class Update(master.CommonMaster):
    """Miscellaneous functionality for running update checks and updates."""
    def __init__(self, importpath, scriptspath, force_update=False, do_update_check=True, do_timesync=True, authenticate=False):
        self.importpath = importpath       # e.g. 'xxx.zip' or 'system'
        self.scriptspath = scriptspath     # directory which holds necessary scripts, e.g. actual update script
        self.force_update = force_update
        self.do_update_check = do_update_check
        self.do_timesync = do_timesync
        self.authenticate = authenticate
        self.rdf_database = None           # rdf.Model
        self.rdf_root = None
        self.sources = None
        self.repokeys = None
        self.version_string = None
        self.version_cached = None
        self.update_exit_code = None
        self.update_failed = False
        self.l2tpmanager = None
        self.managementconnection = None
        self.update_timeout_call = None
        self.script_timeout_call = None
        self.network_connection_ready = False
        self.top_level_deferred = None
        self.run_update_deferred = None
        self.server_utctime = None
        self.server_utctime_received_at = None
        self.stopping = False

    def log_update_info(self):
        """Log useful update information concisely."""

        str = 'own version is %s' % helpers.get_product_version()

        if self.do_update_check:
            str += ', update check'
        else:
            str += ', no update check'
        if self.force_update:
            str += ', update forced'
        else:
            str += ', update not forced'
        if self.do_timesync:
            str += ', timesync'
        else:
            str += ', no timesync'
        str += ', importpath %s' % self.importpath
        str += ', scriptspath %s' % self.scriptspath

        _log.info('UPDATEINFO: %s' % str)
        
    def prepare(self):
        """Gather offline information.

        Checks availability of web UI exported RDF database.  This is critical to success, as it
        contains network configuration.  If the exported RDF database is missing, the update
        process fails.
        """

        try:
            helpers.create_rundir()
        except:
            raise UpdateUnknownError('failed to create runtime directory')

        # Parse RDF database, export temporary (pruned) version
        try:
            _log.info('parsing rdf database')

            # parse database
            self.rdf_database = rdf.Model.fromFile(constants.EXPORTED_RDF_DATABASE_FILE, name='rdfxml')
            if self.rdf_database is None:
                raise Exception('cannot read exported rdf database from file (rdf_database is None')

            # cleanup etc
            @db.transact(database=self.rdf_database)
            def _f1():
                self.rdf_root = self.rdf_database.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
                if self.rdf_root is None:
                    raise Exception('cannot find rdf global root (rdf_root is None')

                # clean up l2tpDeviceStatus; this needs to be done before runner starts
                l2tp_status = self.rdf_root.setS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))
            _f1()

            # export to a temporary RDF file for runner
            @db.transact(database=self.rdf_database)
            def _f2():
                # XXX: prune will take too much time on big database,
                # removed for now before better solution is found.
                # return self.rdf_database.makePruned(self.rdf_root)
                return self.rdf_database
            m = _f2()
            
            @db.transact(database=m)
            def _f3():
                s = m.toString(name='rdfxml')
                f = None
                try:
                    f = open(constants.TEMPORARY_RDF_DATABASE_FILE, 'wb')  # XXX: potential leak, don't care
                    f.write(s)
                finally:
                    if f is not None:
                        f.close()
                        f = None
            _f3()
        except:
            _log.exception('cannot read rdf database')
            raise RdfDatabaseMissingError('rdf database cannot be read')

        # VPNease package version info = product version
        _log.info('checking product version info')
        self.version_string, self.version_cached = versioninfo.get_version_info()

        # Determine fallback sources.list (in case management server cannot provide one)
        #
        # NOTE: this is not currently used because update is not done without management
        #       connection and sources list from management server is preferred.  Untested.
        _log.info('determining fallback apt source')
        self.sources = aptsource.get_cached_aptsource()
        if self.sources is None:
            self.sources = aptsource.get_current_aptsource()
            if self.sources is None:
                # NOTE: hardcoded components and suite!
                # Note: order is important here!
                sources = textwrap.dedent("""\
                deb http://%s dapper main
                deb http://%s dapper main restricted
                """ % (constants.PRODUCT_DEFAULT_VPNEASE_REPOSITORY, constants.PRODUCT_DEFAULT_UBUNTU_REPOSITORY))

    def run_twisted(self):
        """Manage the twisted run required to check and get updates.

        Starts a reactor, and runs the update process inside a "top level" Deferred chain.
        At the end of the chain we always shut down twisted's reactor.  Uses run_update()
        to do the actual update.
        """

        def _update_timeout():
            """Network setup and/or management connection timed out."""
            _log.warning('_update_timeout()')
            self.update_timeout_call = None
            if self.network_connection_ready:
                _log.info('network connection ok, management connection timed out')
            else:
                _log.info('network connection timed out')

            # this is not nice, but what else to do here?
            self.update_failed = True
            self.stop_twisted()
            
        def _update_done(res):
            """Update script completed."""
            _log.debug('_update_done()')
        
        def _management_connection_up(res):
            """Management connection up.

            When only time syncing, the management connection is not authenticated
            (i.e., is susceptible to man-in-the-middle attacks), so we don't want to
            write anything to the filesystem or RDF, unless an update is happening!
            """
            _log.debug('_management_connection_up()')
            _log.debug('identify result: %s' % res)
            if self.update_timeout_call is not None:
                self.update_timeout_call.cancel()
                self.update_timeout_call = None

            # NB: license status is not checked here because server
            # commands the update behaviour and may restrict update
            # based on licence status when required.

            # save for later use - we don't want to do time sync while protocol is running
            # because there is a sizable delay, we need to keep track of the difference
            self.server_utctime = res['currentUtcTime']
            self.server_utctime_received_at = datetime.datetime.utcnow()
            _log.debug('received server utc time:%s at local time:%s' % (self.server_utctime, self.server_utctime_received_at))
            
            if self.do_update_check:
                # simply follow what server says
                _log.info('server update info: available=%s, needed=%s, forced=%s' % \
                          (res['updateAvailable'], res['updateNeeded'], res['updateForced']))

                # apt source.list is only cached *if* we use it, otherwise we may cache wrong version
                if res['updateNeeded']:
                    _log.info('server requested update, running update')

                    self.sources = str(res['aptSourcesList'])
                    aptsource.store_aptsource(self.sources)

                    self.repokeys = str(res['repositoryKeys'])
                    
                    #
                    #  We're committed to trying an update here
                    #
                    
                    d = self.run_update()
                    d.addCallback(_update_done)
                else:
                    _log.info('server did not request an update')
                    d = defer.succeed(None)
                return d

            return defer.succeed(None)
                
        def _running(res):
            """Runner is running."""
            _log.debug('_running()')
            self.network_connection_ready = True
            d = self.managementconnection.connect_wait() # connects and waits, does not reconnect
            d.addCallback(_management_connection_up)
            return d

        def _shutdown(res):
            _log.debug('_shutdown()')
            return self.stop_twisted()

        def _failed(reason):
            """Something failed (errback), shut down."""
            _log.debug('_failed()')
            _log.error('update failed: %s' % reason)
            self.update_failed = True
            return self.stop_twisted()

        _log.info('running twisted for checking policy')

        # start network and management connection
        self.l2tpmanager = l2tpmanager.L2TPManager(self)
        self.managementconnection = managementconnection.ManagementConnection(self.mgmt_version_args, self.mgmt_identify_args, master=self)
        self.managementconnection.set_authenticated(self.authenticate)
        self.l2tpmanager.start(mode=self.l2tpmanager.MODE_NETWORK_ONLY, rdf_file=constants.TEMPORARY_RDF_DATABASE_FILE, importpath=self.importpath, scriptspath=self.scriptspath, nodistronetworking=True)

        d = self.l2tpmanager.waitRunning()
        self.top_level_deferred = d  # store for errback invocation

        # chain actions to that deferred
        d.addCallback(_running)      # --> called when runner is RUNNING
        d.addCallback(_shutdown)
        d.addErrback(_failed)
        
        # failure timer for getting network + management connection
        self.update_timeout_call = reactor.callLater(constants.UPDATE_POLICY_CHECK_TIMEOUT, _update_timeout)

        # run reactor
        _log.debug('running reactor')
        reactor.run()
        _log.debug('reactor exited')
        return None
    
    def mgmt_version_args(self):
        args = {}
        args['version'] = managementprotocol.PROTOCOL_VERSION
        args['info'] = ''  # XXX: some sort of build info here?
        return args

    def mgmt_identify_args(self):
        @db.transact(database=self.rdf_database)
        def _f():
            return self._do_mgmt_identify_args()
        return _f()
    
    def _do_mgmt_identify_args(self):
        root = self.rdf_root
        licinfo = self.rdf_root.getS(ns_ui.licenseInfo, rdf.Type(ns_ui.LicenseInfo))
        uiconfig = self.rdf_root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
        
        args = {}
        try:
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

        args['address'] = '0.0.0.0'       # overridden by managementconnection
        args['port'] = 0                  # overridden by managementconnection

        try:
            args['softwareVersion'] = helpers.get_product_version()
        except:
            args['softwareVersion'] = ''

        args['softwareBuildInfo'] = ''    # XXX
        args['hardwareType'] = ''         # XXX
        args['hardwareInfo'] = ''         # XXX

        try:
            if self.force_update:
                args['automaticUpdates'] = True
            else:
                args['automaticUpdates'] = uiconfig.getS(ns_ui.automaticUpdates, rdf.Boolean)
        except:
            args['automaticUpdates'] = True

        try:
            args['isLiveCd'] = helpers.is_live_cd()
        except:
            args['isLiveCd'] = False

        return args
        
    def stop_twisted(self):
        #
        #  Avoid problems with multiple reactor.stop() calls - these cause twisted
        #  eventloop errors.  See: http://osdir.com/ml/gmane.comp.python.twisted.bugs/2006-12/msg00013.html
        #
        if self.stopping:
            _log.debug('stop_twisted(): already stopping, ignoring call')
            return
        self.stopping = True

        def _shutdown_reactor(res):
            _log.debug('_shutdown_reactor()')
            reactor.stop()
            
        if self.managementconnection is not None:
            self.managementconnection.disconnect()

        if self.l2tpmanager is not None:
            self.l2tpmanager.stop()
            d = self.l2tpmanager.waitStopped()
            d.addCallback(_shutdown_reactor)
            return d
        else:
            d = defer.succeed(None)
            d.addCallback(_shutdown_reactor)
            return d
        
    def run_update(self):
        """Run update script.

        Returns a Deferred, which either raises an update-related exception (ending up
        in caller's errback), or returns None if the update completes normally.
        """

        def _script_timeout():
            _log.warning('_script_timeout()')
            self.script_timeout_call = None

            # this is not nice, but what else to do here?
            if self._update_process_protocol is not None:
                self._update_process_protocol.sendTerm()
            self.update_failed = True
            self.update_exit_code = 3 # XXX: fake update exit code to cause UpdateFailedError
            self.stop_twisted()
        
        def _update_completed(res):
            _log.debug('_update_completed()')
            if self.script_timeout_call is not None:
                self.script_timeout_call.cancel()
                self.script_timeout_call = None

            # XXX: In a script timeout case, we get here with 'res' not being
            # an integer.  This is not nice, but causes no actual problems.

            self.update_exit_code = int(res)  # store exit code
            _log.info('update exit code: %s' % self.update_exit_code)
            return None
        
        _log.info('update needed, starting update process')

        # export configuration before update from sqlite so that new code after
        # update has the option of re-creating the sqlite database or switch to
        # a new backend format without resorting to ugly sqlite dependencies
        try:
            _log.info('exporting rdf/xml for update')
            self._export_rdfxml_for_update()
            _log.info('export rdf/xml for update successful')
        except:
            _log.exception('_export_rdfxml_for_update() failed, ignoring')
            try:
                if os.path.exists(constants.UPDATE_PROCESS_RDFXML_EXPORT_FILE):
                    os.unlink(constants.UPDATE_PROCESS_RDFXML_EXPORT_FILE)                
            except:
                _log.exception('_export_rdfxml_for_update(), cleanup failed')

        # set sources.list
        helpers.write_file('/etc/apt/sources.list', self.sources)

        # set repository keys
        helpers.write_file(constants.UPDATE_REPOSITORY_KEYS_FILE, self.repokeys, perms=0600, append=False)

        # determine parameters for update
        cmd = constants.CMD_PYTHON
        if self.scriptspath is not None:
            pyfile = os.path.join(self.scriptspath, os.path.basename(constants.CMD_L2TPGW_UPDATE_PRODUCT))
        else:
            pyfile = constants.CMD_L2TPGW_UPDATE_PRODUCT
        _log.info('update command: %s, script: %s, arguments: %s' % (cmd, pyfile, self.importpath))

        # failure timer for running script
        self.script_timeout_call = reactor.callLater(constants.UPDATE_SCRIPT_TIMEOUT, _script_timeout)

        # start update process
        u = UpdateProcessProtocol()
        self._update_process_protocol = u
        reactor.spawnProcess(u,
                             executable=cmd,
                             args=[cmd, pyfile, '--import-path', self.importpath],
                             env=None, # Uses os.environ if set to None, default is empty
                             usePTY=1)
        d = u.waitCompleted()
        d.addCallback(_update_completed)
        self.run_update_deferred = d
        return d

    def run(self):
        # remove default database just in case
        from codebay.l2tpserver import db
        db.remove_database()

        # log informative stuff into log first
        try:
            self.log_update_info()
        except:
            _log.exception('log_update_info() failed, ignoring')

        # prepare; may raise exceptions which propagate directly to caller
        try:
            self.prepare()
        except:
            _log.exception('prepare() failed')
            raise

        # run twisted, exits when protocol run complete
        try:
            self.run_twisted()
        except:
            _log.exception('run_twisted() failed')
            raise

        # do timesync last, to avoid disrupting timers
        if self.server_utctime_received_at is None:
            _log.info('management server connection time not available, ignoring timesync.')
        else:
            if self.do_timesync:
                try:
                    # adjust server supplied time with local difference
                    # this is not very nice, but we want to do timesync last
                    now = datetime.datetime.utcnow()
                    diff = now - self.server_utctime_received_at
                    if diff > datetime.timedelta(0, 60*60, 0):  # 1 hour
                        # Something's badly wrong, system time apparently jumped.
                        # This can happen e.g. if system time is updated by distro
                        # scripts when runner restarts distro networking.
                        #
                        # If this happens, we just zero the diff: this causes inaccuracy
                        # in time sync (<1 min) but is better than jumping arbitrarily.

                        _log.warning('time jump when attempting to sync time, diff is %s; zeroing' % diff)
                        diff = datetime.timedelta(0, 0, 0)

                    dt = self.server_utctime + diff
                    _log.debug('doing timesync: server time before adjustment: %s, server time after adjustment: %s, received-at: %s, time-now:%s, diff: %s' % (self.server_utctime, dt, self.server_utctime_received_at, now, diff))

                    # update time, don't cap (allow arbitrary time jumps)
                    timesync.update_system_time(dt, cap_backwards=None, cap_forwards=None)
                    helpers.write_datetime_marker_file(constants.UPDATE_TIMESYNC_TIMESTAMP_FILE)
                except:
                    _log.exception('timesync with management server failed, ignoring.')

        # return value handling
        #
        # Overall the deferred chain started by runner and management connection
        # ends up in success or failure.  We may or may not get a process exit
        # code, depending on what is executed.  Finally, if a timeout occurs,
        # this error is flagged specially in self.update_failed.
        if isinstance(self.update_exit_code, (int, long)):
            if self.update_exit_code == 0:
                # update run, did not try update => signaled as error (but supported case)
                raise UpdateNotDoneError('policy requires update, but update cannot be performed')
            else:
                if self.update_exit_code == 2:
                    # update run, update succeeded => signaled as no exception, success case
                    raise UpdateDone('policy requires update and update was successful')
                else:
                    # update run, update failed or unknown error
                    raise UpdateFailedError('update script failed with exit code: %s' % self.update_exit_code)
        else:
            # update was not executed [or exit code is corrupted (should not happen)]
            # typically we come here after a connection timeout when we try to update and/or timesync
            if self.update_failed:   # from global errback
                # update not run, but failure (probably timeout)
                raise UpdateUnknownError('unknown error (errback)')
            else:
                # policy does not require an update, no action was taken, success
                raise UpdateNotRequired('update not required by policy')

        raise UpdateUnknownError('should not be here')

    # these are for "master" callbacks from webui code

    def runner_starting(self):
        _log.debug('runner_starting()')

    def runner_ready(self):
        _log.debug('runner_ready()')

    def runner_stopping(self):
        _log.debug('runner_stopping()')

    def runner_stopped(self):
        _log.debug('runner_stopped()')

    def management_connection_up(self, identify_result):
        _log.debug('management_connection_up()')
        if identify_result is None:
            _log.warning('identify result is None, connect() or start_primary() called twice? ignoring')
            return

        # XXX: we don't write cookie UUID here
        
    def management_connection_down(self, reason=None):
        _log.debug('management_connection_down(), reason: %s' % reason)
        
    def management_connection_reidentify(self, identify_result):
        _log.debug('management_connection_reidentify()')

    def _export_rdfxml_for_update(self):
        """Export product RDF database to RDF/XML for update.

        This is a raw export, directly from the Sqlite database without l2tpserver.db
        wrapping.
        """
        
        dbase = rdf.Database.open(constants.PRODUCT_DATABASE_FILENAME)

        @db.transact(database=dbase)
        def _f1():
            tmp = dbase.toString(name='rdfxml')     # a bit large
            f = None
            try:
                f = open(constants.UPDATE_PROCESS_RDFXML_EXPORT_FILE, 'wb')
                f.write(tmp)
            finally:
                if f is not None:
                    f.close()
                    f = None
            tmp = None
        _f1()
