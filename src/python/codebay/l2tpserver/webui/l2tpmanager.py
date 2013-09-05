"""
Life cycle management for the runner (startstop) component.

Use by both web UI and update process.
"""
__docformat__ = 'epytext en'

import os
import signal
import re
import datetime

from twisted.internet import protocol, reactor, defer, error

from codebay.l2tpserver import constants
from codebay.l2tpserver import db

from codebay.common import logger

_log = logger.get('l2tpserver.webui.l2tpmanager')

# NOTE: this needs to be in synch with constants.RUNNER_STATE_STRING_PREFIX
_state_re = re.compile(r'^\*\*\*\sSTATE\:\s+(\S+?)(\s+(\S+?))?\s*$')

# --------------------------------------------------------------------------

class L2TPProcessProtocol(protocol.ProcessProtocol):
    """Class handling one start/stop cycle of the L2TP runner.

    No policy relevant issues here.  Assumes a reference to manager (self.manager).
    """

    def __init__(self, manager):
        self.manager = manager
        self._stdout_buffer = ''
        self._stopping = False

    @db.transact()
    def outReceived(self, data):
        # XXX: this is not clean; twisted probably offers something better to parse lines??
        self._stdout_buffer += data

        while True:
            i = self._stdout_buffer.find('\n')
            if i >= 0:
                # complete line found
                line = self._stdout_buffer[:i]
                self._stdout_buffer = self._stdout_buffer[i+1:]

                m = _state_re.match(line)
                if m is not None:
                    st1, st2 = m.group(1), m.group(3)
                    try:
                        ign = self.manager.runner_state_change(st1, st2)
                    except:
                        _log.exception('cannot process state change')
            else:
                break

    @db.transact()
    def connectionMade(self):
        # process is running, but we're not ready yet
        _log.debug('L2TPProcessProtocol/connectionMade()')

    @db.transact()
    def processEnded(self, reason):
        _log.debug('L2TPProcessProtocol/processEnded() [reason=%s]' % reason)
        self.manager.runner_stopped(reason)

    def sendStop(self):
        """Signal the runner to stop.

        The caller should not call this unless the runner is in RUNNING state
        or if the runner is waiting for DHCP which never happens.  The current
        runner implementation cannot necessarily handle the signal correctly
        in other states.
        """

        _log.debug('L2TPProcessProtocol/sendStop()')

        #if self._stopping:
        #    return

        _log.info('Sending SIGTERM to l2tpgw-runner')

        # TERM needs to be sent as an integer (see twisted/internet/interfaces.py)
        self.transport.signalProcess(signal.SIGTERM)

# --------------------------------------------------------------------------
#
#  States:
#
#    STARTING:  Process active, but not yet fully running
#    RUNNING:   Process active, successfully initialized and running
#    STOPPING:  Process active, but shutting down
#    STOPPED:   Process not active
#
#  Possible transitions
#
#    STARTING -> RUNNING -> STOPPING -> STOPPED    Normal case
#    STARTING -> STOPPED                           Error occurred during start
#
#  Automatic restarting and other policy-related issues are the responsibility
#  of the caller (master).
#

class L2TPManager:
    """Class managing the starting and stopping of the L2TP runner ("protocol logic").

    Individual 'runs' of the runner are handled using L2TPProcessProtocol.
    Assumes a "master" object, which can receive several callbacks when
    protocol state changes.  The most relevant are:
      * runner_ready() => runner is RUNNING, time to start e.g. management connection
      * runner_stopping() => pre-actions before stopping runner, e.g. stop
        management connection
      * runner_stopped() => post-actions after stop

    Note that in addition to the web UI, L2TPManager is used by scripts to
    set up and tear down a temporary network configuration including possibly
    a management connection.
    """
    # runner states
    STATE_STARTING = 'STARTING'
    STATE_RUNNING = 'RUNNING'
    STATE_STOPPING = 'STOPPING'
    STATE_STOPPED = 'STOPPED'
    
    # start modes
    MODE_FULL = 'FULL'
    MODE_NETWORK_ONLY = 'NETWORK-ONLY'
    
    def __init__(self, master):
        self.master = master
        self.state = self.STATE_STOPPED
        self.processProtocol = None
        self._runner_mainstate = None
        self._runner_substate = None
        self._runner_ready_waiters = []
        self._runner_stop_waiters = []
        self._start_time = None

    def getState(self):
        return self.state

    def canStart(self):
        return self.state == self.STATE_STOPPED

    def canStop(self):
        return self.isRunning()

    def isRunning(self):
        return self.state == self.STATE_RUNNING
    
    def isStarting(self):
        return self.state == self.STATE_STARTING
    
    def isStopped(self):
        return self.state == self.STATE_STOPPED

    def startTime(self):
        return self._start_time
    
    def start(self, mode=MODE_FULL, rdf_file=None, importpath=None, scriptspath=None, nodistronetworking=False):
        _log.debug('L2TPManager/start() called, mode %s, rdf_file %s, importpath %s, scriptspath %s, nodistronetworking %s' % (mode, rdf_file, importpath, scriptspath, nodistronetworking))
        
        # XXX: license management could affect mode selection or other
        # startup parameters, but currently we are content in starting
        # the runner normally and let the protocol side restrict any
        # connections that are formed.

        # XXX: something better here; e.g. wait for start
        if not self.canStart():
            raise Exception('start() called, but cannot start')
        try:
            self.state = self.STATE_STARTING
            self._start_time = datetime.datetime.utcnow()
            self.processProtocol = L2TPProcessProtocol(self)

            if self.master is not None:
                self.master.runner_starting()

            if scriptspath is not None:
                command = os.path.join(scriptspath, os.path.basename(constants.CMD_L2TPGW_RUNNER))
            else:
                command = constants.CMD_L2TPGW_RUNNER

            args = [command, 'run']
            if True:
                args.append('--mode')
                args.append(mode)
            if rdf_file is not None:
                args.append('--rdf-file')
                args.append(rdf_file)
            if importpath is not None:
                args.append('--import-path')
                args.append(importpath)
            if nodistronetworking:
                args.append('--no-distro-restart')

            _log.debug('starting runner: %s' % args)

            reactor.spawnProcess(self.processProtocol,
                                 executable=command,
                                 args=args,
                                 usePTY=1)
            # Don't call waitRunning() here; if the caller ignores the Deferred,
            # we'll have a nice Deferred "leak"
        except:
            # Note: if we set state to STOPPED here, then subsequent
            # stop call will not try to stop at all and watchdog will
            # not react normally, which is not what we want. The
            # solution is to let the state remain in STARTING.

            # Note: this forces watchdog to consider our startup as
            # failed attempt and may speed up restarting.
            self._start_time = None

            self.processProtocol = None
            raise

    def stop(self):
        _log.debug('L2TPManager/stop() called')

        if self.state == self.STATE_STOPPED:
            return defer.succeed(None)

        # The stopping process is a bit complicated because of runner
        # limitations.  Runner should be able to handle a SIGTERM
        # correctly in all states, and stop cleanly.  However, there
        # are some corner cases where runner will lose the signal.
        # The RUNNING and WAITING_FOR_DHCP states are known to work,
        # though.
        #
        # The overall strategy here is to first send a stop (SIGTERM)
        # once and then wait for runner to go into the RUNNING state.
        # The expected result is for the wait to fail, because runner
        # receives the signal and handles it correctly, stopping before
        # it reaches RUNNING.  (If the runner was in RUNNING state to
        # begin with, this logic is skipped because it is unnecessary.)
        #
        # If runner drops the signal, we simply wait for runner to
        # become RUNNING and signal it normally.  If the runner is
        # stuck waiting for DHCP (no DHCP server), this means an
        # unfortunate long wait here, around a minute or two.  That
        # cannot be currently helped, but it occurs quite rarely.
        
        @db.transact()
        def _send_stop_once_hack(res):
            _log.debug('_send_stop_once_hack')
            if self.state != self.STATE_RUNNING:
                self.processProtocol.sendStop()
                
        @db.transact()
        def _check_and_wait_running(res):
            # NB: if runner stops because of an earlier signal (before
            # it gets to RUNNING state, waitRunning() calls will be
            # launched with an error (errback below).
            _log.debug('_check_and_wait_running')
            return self.waitRunning()

        @db.transact()
        def _set_stopping(res):
            _log.debug('_set_stopping')
            self.state = self.STATE_STOPPING
            
        @db.transact()
        def _runner_stopping(res):
            _log.debug('_runner_stopping')
            # XXX: should we wait here (in practice: wait for management
            # connection to terminate cleanly first)?
            self.master.runner_stopping()
        
        @db.transact()
        def _signal_and_wait_runner(res):
            _log.debug('_signal_and_wait_runner')
            # FIXME
            self.processProtocol.sendStop()
            return self.waitStopped()

        @db.transact()
        def _wait_running_error(reason):
            _log.debug('_wait_running_error: %s' % reason)

            @db.transact()
            def _handle_cause(res):
                # we are expecting that the process has terminated
                if reason.check(error.ProcessTerminated):
                    _log.debug('runner process was terminated before it reached running, this is an expected result')
                    self.state = self.STATE_STOPPED  # just in case process died ugly
                else:
                    _log.info('waitRunning() failed unexpectedly: %s' % reason)

                    # XXX: we probably want to killall -9 runner here just in case
                    # XXX: we should also run runner_stopped() ?
                    self.state = self.STATE_STOPPED

                return None
            
            # something bad happened, runner is probably gone, we need to stop
            # the management protocol first (regardless of the cause)
            d = defer.Deferred()
            d.addCallback(_runner_stopping)
            d.addCallback(_handle_cause)
            d.addErrback(lambda x: _log.warning('_wait_running_error failed: %s' % x))
            d.callback(None)
            return d

        @db.transact()
        def _wait_running_success(res):
            d = defer.Deferred()
            d.addCallback(_runner_stopping)
            d.addCallback(_set_stopping)
            d.addCallback(_signal_and_wait_runner)
            d.addErrback(lambda x: _log.warning('_wait_running_success failed: %s' % x))
            d.callback(None)
            return d

        d = defer.Deferred()
        d.addCallback(_send_stop_once_hack)
        d.addCallback(_check_and_wait_running)
        d.addCallbacks(_wait_running_success, _wait_running_error)
        d.addErrback(lambda x: _log.warning('stop failed: %s' % x))
        d.callback(None)
        return d

    def waitRunning(self):
        if self.state == self.STATE_RUNNING:
            return defer.succeed(None)
        d = defer.Deferred()
        self._runner_ready_waiters.append(d)
        return d

    def waitStopped(self):
        if self.state == self.STATE_STOPPED:
            return defer.succeed(None)
        d = defer.Deferred()
        self._runner_stop_waiters.append(d)
        return d
    
    def runner_state_change(self, mainstate, substate):
        _log.info('runner state change to %s/%s' % (mainstate, substate))
        self._runner_mainstate = mainstate
        self._runner_substate = substate
        if self.master is not None:
            self.master.runner_state_changed(mainstate, substate)
        if mainstate == constants.RUNNER_STATE_STRING_RUNNING:
            self._runner_became_ready()

    def _runner_became_ready(self):
        @db.transact()
        def _set_runner_ready(res):
            _log.debug('_set_runner_ready')
            self.state = self.STATE_RUNNING

        @db.transact()
        def _runner_ready_deferreds(res):
            _log.debug('_runner_ready_deferreds')
            t, self._runner_ready_waiters = self._runner_ready_waiters, []
            for w in t:
                _log.debug('calling ready callback: %s' % t)
                w.callback(None)
                
        @db.transact()
        def _runner_ready_master(res):
            if self.master is not None:
                return self.master.runner_ready()

        d = defer.Deferred()
        d.addCallback(_set_runner_ready)
        d.addCallback(_runner_ready_deferreds)
        d.addCallback(_runner_ready_master)
        d.addErrback(lambda x: _log.warning('_runner_became_ready failed: %s' % x))
        d.callback(None)
        return d

    def runner_stopped(self, reason):
        _log.debug('L2TPManager/runner_stopped() called')

        @db.transact()
        def _set_runner_stopped(res):
            # XXX: act differently based on reason?
            self.state = self.STATE_STOPPED
            self.processProtocol = None

        @db.transact()
        def _runner_ready_deferreds(res):
            # XXX: this is necessary because of how the stopping process
            # works; we need an errback to handle stopping correctly.
            t, self._runner_ready_waiters = self._runner_ready_waiters, []
            for w in t:
                w.errback(reason)

        @db.transact()
        def _runner_stopped_deferreds(res):
            t, self._runner_stop_waiters = self._runner_stop_waiters, []
            for w in t:
                w.callback(None)

        @db.transact()
        def _runner_stopped_master(res):
            if self.master is not None:
                return self.master.runner_stopped()
            
        d = defer.Deferred()
        d.addCallback(_set_runner_stopped)
        d.addCallback(_runner_ready_deferreds)
        d.addCallback(_runner_stopped_deferreds)
        d.addCallback(_runner_stopped_master)
        d.addErrback(lambda x: _log.warning('runner_stopped failed: %s' % x))
        d.callback(None)
        return d
