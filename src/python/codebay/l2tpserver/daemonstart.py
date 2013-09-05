"""Generic system daemon start/stop functions."""
__docformat__ = 'epytext en'

from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand

run_command = runcommand.run_command

class Timeout(Exception):
    pass

class DaemonStart:
    def __init__(self, logger):
        self._log = logger

    def _cleanup(self, pidfile=None, cleanup_files=None):
        files = []
        if cleanup_files is not None:
            files.extend(cleanup_files)

        if pidfile is not None:
            files.append(pidfile)

        for i in files:
            run_command([constants.CMD_RM, '-f', i], retval=runcommand.FAIL)

    def _stop(self, command, pidfile, signal, timeout):
        """Stop daemon process with signal 'signal'.

        Uses pidfile if pidfile is given. If stopping with pidfile fails
        or no pidfile is given, tries to stop with process name.

        Returns non-zero if last tried stop method (pidfile, process)
        fails, zero otherwise.
        """

        if command is None:
            raise Exception('No command specified')

        self._log.debug('stopping %s with pidfile %s and signal %s' % (command, pidfile, signal))

        cmd = [constants.CMD_START_STOP_DAEMON, '--stop', '--verbose']
        if timeout is None:
            cmd += ['--signal', str(signal)]
        else:
            cmd += ['--retry', '-%s/%s' % (str(signal), str(timeout))]

        if pidfile is not None:
            [rv, _, _] = run_command(cmd + ['--pidfile', pidfile])
        else:
            [rv, _, _] = run_command(cmd + ['--exec', command])

        if timeout is not None and rv == 2:
            # This means that the start-stop-daemon was unable to kill the process
            raise Timeout('Could not stop process "%s" [pidfile: %s] with signal %s, waited for %s seconds' % (command, pidfile, signal, timeout))

        return rv

    def start_daemon(self, command=None, pidfile=None, args=None, background=False, make_pidfile=False):
        if command is None:
            raise Exception('No command specified')

        self._log.debug('%s starting with args %s.' % (command, args))

        self._cleanup(pidfile, None)

        c = [constants.CMD_START_STOP_DAEMON, '--start', '--verbose', '--exec', command]
        if pidfile is not None:
            c.append('--pidfile')
            c.append(pidfile)
        if background:
            c.append('--background')
        if make_pidfile:
            c.append('--make-pidfile')
        if args is not None:
            c.append('--')
            c.extend(args)
        run_command(c, retval=runcommand.FAIL)

        self._log.debug('%s started.' % command)

    def stop_daemon(self, command=None, pidfile=None, timeout=None):
        if command is None:
            raise Exception('No command specified')
        return self._stop(command, pidfile, 'TERM', timeout)

    # Note: failing command not interesting..
    def hard_stop_daemon(self, command=None, pidfile=None, timeout=None):
        if command is None:
            raise Exception('No command specified')
        self._stop(command, pidfile, 'KILL', timeout)

    def cleanup_daemon(self, pidfile=None, cleanup_files=None):
        self._cleanup(pidfile, cleanup_files)

