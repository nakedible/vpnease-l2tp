"""
Run wrapper.

FIXME: this is dup code from l2tpserver.  Unify?
"""
__docformat__ = 'epytext en'

from codebay.common import runcommand
from codebay.common import logger

PASS = runcommand.PASS
FAIL = runcommand.FAIL
STDOUT = runcommand.STDOUT

_log = logger.get('runcommand')

def run_command(args, executable=None, cwd=None, env=None, stdin=None, stdout=None, stderr=None, shell=False, preexec=None, retval=None):
    _log.debug("run_command: [%s], executable=%s, cwd=%s, env=%s, shell=%s, preexec=%s, retval=%s" % (str(args), str(executable), str(cwd), str(env), str(shell), str(preexec), str(retval)))

    for name, value in [['stdin', stdin], ['stdout', stdout], ['stderr', stderr]]:
        if value is None:
            _log.debug("%s:%s" % (name, str(value)))
        else:
            _log.debug("%s:\n%s" % (name, str(value)))

    try:
        ret = runcommand.run(args, executable, cwd, env, stdin, stdout, stderr, shell, preexec, retval)
    except runcommand.RunException, e:
        _log.debug(' ==> FAILED with RunException:\nretval=%s\nstdout:%s\nstderr:%s\n' % (e.rv, e.stdout, e.stderr))
        raise
    except Exception, e:
        _log.debug(' ==> FAILED with %s: %s' % (e.__class__, e))
        raise
    except:
        _log.debug(' ==> FAILED with unknown exception')
        raise
    
    _log.debug(' ==> retval=%s\nstdout:%s\nstderr:%s\n' % (ret[0], ret[1], ret[2]))

    return ret
