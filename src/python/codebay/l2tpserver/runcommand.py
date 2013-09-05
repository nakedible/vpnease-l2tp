"""
L2tpserver run wrapper.
"""
__docformat__ = 'epytext en'

import datetime

from codebay.common import runcommand
from codebay.common import logger

PASS = runcommand.PASS
FAIL = runcommand.FAIL
STDOUT = runcommand.STDOUT

_log = logger.get('l2tpserver.runcommand')

warning_log_time_limit = datetime.timedelta(0, 1, 0)

def _log_runtime(starttime, msg):
    runtime = datetime.datetime.utcnow() - starttime
    if runtime > warning_log_time_limit:
        _log.warning('%s and took long: %s' % (msg, runtime))

def run_command(args, executable=None, cwd=None, env=None, stdin=None, stdout=None, stderr=None, shell=False, preexec=None, retval=None, nologonerror=False, nologruntime=False):
    _log.debug("run_command: [%s], executable=%s, cwd=%s, env=%s, shell=%s, preexec=%s, retval=%s" % (str(args), str(executable), str(cwd), str(env), str(shell), str(preexec), str(retval)))

    for name, value in [['stdin', stdin], ['stdout', stdout], ['stderr', stderr]]:
        if value is None:
            _log.debug("%s:%s" % (name, str(value)))
        else:
            _log.debug("%s:\n%s" % (name, str(value)))

    def _log_result(msg, onlydebug=False, rv=None, out=None, err=None):
        m = msg
        if rv is not None:
            m += ':\n  retval: %s' % rv
        if out is not None:
            m += ':\n  stdout: %s' % out
        if err is not None:
            m += ':\n  stderr: %s' % err

        if not onlydebug:
            _log.error(m)
        else:
            _log.debug(m)

    try:
        start_time = datetime.datetime.utcnow()
        ret = runcommand.run(args, executable, cwd, env, stdin, stdout, stderr, shell, preexec, retval)
        if not nologruntime:
            _log_runtime(start_time, "run_command succeeded")
    except runcommand.RunException, e:
        _log_result(' ==> FAILED with RunException', onlydebug=nologonerror, rv=e.rv, out=e.stdout, err=e.stderr)
        if not nologruntime:
            _log_runtime(start_time, "run_command failed")
        raise
    except Exception, e:
        _log_result(' ==> FAILED with %s: %s' % (e.__class__, e), onlydebug=nologonerror)
        if not nologruntime:
            _log_runtime(start_time, "run_command failed")
        raise
    except:
        _log_result(' ==> FAILED with unknown exception', onlydebug=nologonerror)
        if not nologruntime:
            _log_runtime(start_time, "run_command failed")
        raise

    _log_result(' ==> SUCCESS', onlydebug=True, rv=ret[0], out=ret[1], err=ret[2])

    return ret

