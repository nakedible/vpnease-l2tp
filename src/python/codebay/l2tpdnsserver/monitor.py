"""
Monitor a single VPNease server periodically.

Starts an internal task, which monitors a VPNease server periodically.
When a server has been confirmed to have failed, calls a user callback
to notify of a status change.
"""

from twisted.internet import reactor, protocol, defer, error
from twisted.python import failure
from codebay.common import logger

_log = logger.get('l2tpddnsserver.monitor')

class _MonitorPingProtocol(protocol.ProcessProtocol):
    def __init__(self, callback):
        self.callback = callback
        
    def outReceived(self, data):
        pass

    def processEnded(self, reason):
        self.callback(reason)

class Monitor:
    STATUS_UNKNOWN = 'STATUS_UNKNOWN'
    STATUS_OK = 'STATUS_OK'
    STATUS_NOT_RESPONDING = 'STATUS_NOT_RESPONDING'

    def __init__(self, server_address=None, callback=None, interval=60.0):
        self.status = self.STATUS_UNKNOWN
        self.server_address = server_address
        self.callback = callback
        self.interval = interval
        self.timer = None

    def start(self, now=False):
        self.stop()
        if now:
            self.timer = reactor.callLater(0.0, self._monitor_timer)
        else:
            self.timer = reactor.callLater(self.interval, self._monitor_timer)
        
    def stop(self):
        if self.timer is not None:
            self.timer.cancel()
            self.timer = None    
    
    def get_status(self):
        return self.status

    def get_address(self):
        return self.server_address

    def is_ok(self):
        return self.status == self.STATUS_OK
    
    def _monitor_timer(self):
        _log.debug('_monitor_timer(%s)' % self.server_address)
        
        self.timer = None
        old_status = self.status

        def _start_check(res):
            d = defer.Deferred()

            def _ping_done_callback(res):
                _log.debug('_monitor_timer(%s): ping resulted in %s' % (self.server_address, res))
                if isinstance(res, failure.Failure):
                    e = res.check(error.ProcessDone, error.ProcessTerminated)
                    if e == error.ProcessDone:
                        d.callback(True)
                    elif e == error.ProcessTerminated:
                        d.callback(False)
                    else:
                        _log.warning('_monitor_timer(%s): unexpected Failure instance: %s' % (self.server_address, res))
                        d.callback(False)
                else:
                    _log.warning('_monitor_timer(%s): unexpected result: %s' % (self.server_address, res))
                    d.callback(False)
                
            proc = _MonitorPingProtocol(_ping_done_callback)
            cmd = '/bin/ping'
            args = [cmd, '-c', '1', '-w', '10', str(self.server_address)]
            reactor.spawnProcess(proc, executable=cmd, args=args, usePTY=1)

            return d

        def _check_ok(res):
            if res:
                self.status = self.STATUS_OK
            else:
                self.status = self.STATUS_NOT_RESPONDING

            if self.status != old_status:
                self.callback(self)

        def _check_failed(reason):
            _log.warning('_monitor_timer(%s): check failed, reason %s' % reason)

        def _reschedule_check(res):
            self.start()

        d = defer.Deferred()
        d.addCallback(_start_check)
        d.addCallbacks(_check_ok, _check_failed)
        d.addCallback(_reschedule_check)
        d.callback(None)
        return d
