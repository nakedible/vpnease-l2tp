"""Configuration and start/stop wrapper for a system daemon."""
__docformat__ = 'epytext en'

import os, time
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import daemonstart

run_command = runcommand.run_command

class DaemonConfig:
    """L2TP system daemon configuration.

    Writes configuration files based on configuration root taken as input
    and takes care of stopping and starting of a specific daemon.

    Subclasses are expexted to override create_config, start and *_stop methods
    as well as the optional post_start, pre_stop and get_args method.
    Subclasses are also required to define class variables 'name',
    'command', 'pidfile, 'cleanup_files'.
    """

    # overwrite in subclass
    name = None
    command = None
    pidfile = None

    # overwrite in subclass when required
    def get_args(self):
        return None

    def get_name(self):
        return self.name

    def __init__(self):
        self.configs = []
        self._log = logger.get(self.name + '-daemon')
        self.d = daemonstart.DaemonStart(self._log)

    def write_config(self):
        for i in self.configs:
            mode = 0644
            try:
                mode = i['mode']
            except:
                pass
            helpers.write_file(i['file'], i['cont'], perms=mode)

    def check_process(self):
        """Check existence of the daemon process using pidfile."""

        if self.pidfile is None:
            # XXX: we should warn here if/when all processes use pidfile
            # self._log.warning('check_process: no pidfile, checking based on process name')

            [rv, out, err] = run_command([constants.CMD_PIDOF, self.name])
            if rv != 0 or out is None:
                return False

            pids = out.split(' ')
            if len(pids) != 1:
                return False

            try:
                os.kill(int(pids[0]), 0)
            except OSError:
                return False

            return True

        try:
            if not os.path.exists(self.pidfile):
                self._log.warning('missing pidfile: %s, assume process exited' % self.pidfile)
                return False

            f = open(self.pidfile, 'rb')
            self._log.debug('check_process: fd=%s' % f.fileno())
            pid = int(f.read())
            f.close()

            os.kill(pid, 0)  # 0 = just check existence
        except OSError:
            return False
        except:
            self._log.error('check_process failed unexpectedly')
            return False
        
        return True
    
    # implement in subclass

    def create_config(self, cfg, resinfo):
        raise Exception('not implemented')

    # overwrite in subclass when required

    def pre_start(self):
        pass

    def start(self):
        """Default daemon start."""

        self.d.start_daemon(command=self.command, pidfile=self.pidfile, args=self.get_args())

    def post_start(self, *args):
        pass

    def pre_stop(self):
        pass

    def soft_stop(self, silent=False):
        """Default soft stop daemon."""

        ret = self.d.stop_daemon(command=self.command, pidfile=self.pidfile)

        if ret != 0:
            if not silent:
                # XXX: if process was not started, this generates non-relevant
                # warning message. Override in specific daemon config to prevent
                # that.
                self._log.warning('Process soft stop failed: %d' % ret)
            else:
                self._log.debug('Process soft stop failed (silent): %d' % ret)

    def hard_stop(self):
        """Default hard stop daemon."""

        self.d.hard_stop_daemon(command=self.command, pidfile=self.pidfile)
        self.d.cleanup_daemon(pidfile=self.pidfile, cleanup_files=self.cleanup_files)

    def post_stop(self):
        pass
