"""
Codebay process running utils.

@group Running commands: run, call
@group Preexec functions: chroot, cwd

@var PASS:
  Specifies that the given file descriptor should be passed directly
  to the parent. Given as an argument to run.
@var FAIL:
  Specifies that if output is received for the given file descriptor,
  an exception should be signalled. Given as an argument to
  run.
@var STDOUT:
  Specifies that standard error should be redirected to the same file
  descriptor as standard out. Given as an argument to run.
"""
__docformat__ = 'epytext en'

import os

from codebay.common import subprocess

PASS = -1
FAIL = -2
STDOUT = -3

class RunException(Exception):
    """Running command failed.

    @ivar rv: Return value of the command.
    @ivar stdout: Captured stdout of the command or None.
    @ivar stderr: Captured stderr of the command or None.
    """

class chroot:
    """Returns a function that will do a chroot to path when invoked."""

    def __init__(self, path):
        self.path = path

    def __call__(self):
        os.chroot(self.path)

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), repr(self.path))

class cwd:
    """Returns a function that will do a cwd to path when invoked."""

    def __init__(self, path):
        self.path = path

    def __call__(self):
        os.chdir(self.path)

    def __repr__(self):
        return '%s(%s)' % (str(self.__class__), repr(self.path))

def call(*args, **kw):
    """Convenience wrapper for calling run.

    Positional arguments are converted to a list and given to run as
    an argument. Keyword arguments are passed as is to run.

    >>> call('echo','-n','foo')
    [0, 'foo', '']
    >>> call('exit 1', shell=True)
    [1, '', '']
    """
    return run(list(args), **kw)

def run(args, executable=None, cwd=None, env=None, stdin=None, stdout=None, stderr=None, shell=False, preexec=None, retval=None):
    """Wrapper for running commands.

    run takes a lot of arguments and they are explained here.

    >>> run(['echo','-n','foo'])
    [0, 'foo', '']
    >>> run('exit 1', shell=True)
    [1, '', '']

    @param args:
      List of strings or a single string specifying the program and
      the arguments to execute. It is mandatory.
    @param executable:
      Name of the executable to be passed in argv[0]. Defaults to the
      first value of args.
    @param cwd:
      Working directory to execute the program in. Defaults to no
      change. Executes before preexec.
    @param env:
      Environment to execute the process with. Defaults to inheriting
      the environment of the current process.
    @param stdin:
      If None, process is executed with a pipe with no data given. If
      a string, process is executed with a pipe with the string as
      input. If PASS, process stdin is inherited from the current
      process. Defaults to None.
    @param stdout:
      If None, process stdout is captured with a pipe and returned. If
      PASS, process stdout is inherited from the current process. If
      FAIL, process stdout is captured with a pipe and an exception is
      raised if the process prints to stdout. Defaults to None.
    @param stderr:
      Same as above with one addition. If STDOUT, then stderr is
      redirected to the same destination as stdout.
    @param shell:
      If False, the command is executed directly. If True, the
      arguments are passed to the shell for interpretation. Defaults
      to False.
    @param preexec:
      Can be used to specify things to do just before starting the new
      child process. The argument should be a list or tuple, all of
      the callables in the list are executed just before starting the
      child process. Defaults to no function executed.
    @param retval:
      If None, no checks are performed on the child process' return
      value. If FAIL, an exception is raised if the child process
      return value is not zero. If a callable, the callable is invoked
      with the child process return value as an argument and an
      exception is raised if the callable returned False.
    @return:
      List of retval, stdout output string and stderr output
      string. If stdout or stderr is not captured, None is returned
      instead.
    @raise RunException:
      Raised if stdout output, stderr output or return value check
      triggered a failure.
    @raise ValueError:
      Raised if illegal arguments are detected.
    @raise OSError:
      Raised if starting the child process failed.
    """

    if isinstance(args, list):
        popen_args = args
    elif isinstance(args, str):
        popen_args = [args]
    else:
        raise ValueError('Unknown value %s passed as args.' % repr(args))

    if preexec is None:
        preexec_fn = None
    elif isinstance(preexec, (list, tuple)):
        def do_preexec():
            for f in preexec:
                f()
        preexec_fn = do_preexec
    else:
        raise ValueError('Unknown value %s passed as preexec.' % repr(preexec))
    
    if stdin is None:
        popen_stdin = subprocess.PIPE
        popen_input = None
    elif stdin is PASS:
        popen_stdin = None
        popen_input = None
    elif isinstance(stdin, str):
        popen_stdin = subprocess.PIPE
        popen_input = stdin
    else:
        raise ValueError('Unknown value %s passed as stdin.' % repr(stdin))

    if stdout is None:
        popen_stdout = subprocess.PIPE
    elif stdout is PASS:
        popen_stdout = None
    elif stdout is FAIL:
        popen_stdout = subprocess.PIPE
    else:
        raise ValueError('Unknown value %s passed as stdout.' % repr(stdout))

    if stderr is None:
        popen_stderr = subprocess.PIPE
    elif stderr is PASS:
        popen_stderr = None
    elif stderr is FAIL:
        popen_stderr = subprocess.PIPE
    elif stderr is STDOUT:
        popen_stderr = subprocess.STDOUT
    else:
        raise ValueError('Unknown value %s passed as stderr.' % repr(stderr))

    if retval is None:
        rvcheck = None
    elif retval is FAIL:
        def do_check(i):
            return i == 0
        rvcheck = do_check
    elif callable(retval):
        rvcheck = retval
    else:
        raise ValueError('Unknown value %s passed as retval.' % repr(retval))

    handle, rv = None, None
    try:
        handle = subprocess.Popen(popen_args,
                                  executable=executable,
                                  stdin=popen_stdin,
                                  stdout=popen_stdout,
                                  stderr=popen_stderr,
                                  close_fds=True,
                                  cwd=cwd,
                                  env=env,
                                  shell=shell,
                                  preexec_fn=preexec_fn)
        stdout, stderr = handle.communicate(input=popen_input)
    finally:
        if handle is not None:
            rv = handle.wait()

    if stdout is FAIL:
        if stdout != '':
            e = RunException('Process printed to stdout.')
            e.rv = rv
            e.stdout = stdout
            e.stderr = stderr
            raise e

    if stderr is FAIL:
        if stderr != '':
            e = RunException('Process printed to stderr.')
            e.rv = rv
            e.stdout = stdout
            e.stderr = stderr
            raise e

    if rvcheck is not None:
        if not rvcheck(rv):
            e = RunException('Process return value check failed.')
            e.rv = rv
            e.stdout = stdout
            e.stderr = stderr
            raise e

    return [rv, stdout, stderr]
