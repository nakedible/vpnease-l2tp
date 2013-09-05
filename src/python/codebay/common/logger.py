"""
Codebay logging utility module.
"""
__docformat__ = 'epytext en'

import logging, atexit, sys, os, time, datetime
from logging import handlers

from codebay.common.siteconfig import conf

conf.add('logging_config', 'default')
conf.add('logging_debug', False)
conf.add('logging_stdout', False)
conf.add('logging_stderr', False)
conf.add('logging_syslog', False)

get = logging.getLogger


class SplittingSysLogHandler(handlers.SysLogHandler):
    _vanillaformatter = logging.Formatter('%(message)s')

    def __init__(self, *args, **kw):
        self.unixsocket = 0
        handlers.SysLogHandler.__init__(self, *args, **kw)

    def _split_record(self, rec):
        # XXX: logging the result of raise Exception('') causes a problem with Python
        # logging modules; we should try to fix that here, but it's not completely
        # trivial.

        s = self._vanillaformatter.format(rec)

        lines = s.split('\n')

        res = []
        for l in lines:
            # Escape non-printable characters
            if isinstance(l, str):
                l = l.encode('string_escape')
            elif isinstance(l, unicode):
                l = l.encode('unicode_escape')
            else:
                # NB: should not happen..
                pass

            # crude; we strip exc_info if present
            newrec = logging.LogRecord(rec.name, rec.levelno, rec.pathname, rec.lineno, l, [], None)
            newrec.created = rec.created
            newrec.msecs = rec.msecs
            res.append(newrec)
        return res

    def emit(self, rec):
        for r in self._split_record(rec):
            handlers.SysLogHandler.emit(self, r)

def disableConfig():
    root = logging.getLogger('')
    root.manager.emittedNoHandlerWarning = 1 # Hack to disable nits if nothing at all is configured

def defaultConfig():
    root = logging.getLogger('')
    root.manager.emittedNoHandlerWarning = 1 # Hack to disable nits if nothing at all is configured

    # XXX: some cleaner way to do this?
    if conf.logging_debug or 'CODEBAY_LOGGER_DEBUG' in os.environ or os.path.exists('/tmp/CODEBAY_LOGGER_DEBUG'):
        root.setLevel(logging.DEBUG)
    else:
        root.setLevel(logging.INFO)

    commonformatter = logging.Formatter('[%(asctime)s %(levelname)8s] %(name)s: %(message)s')

    # We want to log timestamps in UTC (GMT); see logging/__init__.py:Formatter.formatTime:
    #
    #   This function uses a user-configurable function to convert the
    #   creation time to a tuple. By default, time.localtime() is
    #   used; to change this for a particular formatter instance, set
    #   the 'converter' attribute to a function with the same
    #   signature as time.localtime() or time.gmtime(). To change it
    #   for all formatters, for example if you want all logging times
    #   to be shown in GMT, set the 'converter' attribute in the
    #   Formatter class.

    commonformatter.converter = time.gmtime

    if conf.logging_syslog or 'CODEBAY_LOGGER_SYSLOG' in os.environ:
        #syslogger = SysLogHandler('/dev/log', handlers.SysLogHandler.LOG_DAEMON)
        try:
            syslogger = SplittingSysLogHandler('/dev/log', handlers.SysLogHandler.LOG_DAEMON)
            syslogger.setFormatter(commonformatter)
            root.addHandler(syslogger)
        except:
            # XXX: report error? syslog is disabled if not working
            pass

    if conf.logging_stdout or 'CODEBAY_LOGGER_STDOUT' in os.environ:
        stdouter = logging.StreamHandler(sys.stdout)
        stdouter.setFormatter(commonformatter)
        root.addHandler(stdouter)

    if conf.logging_stderr or 'CODEBAY_LOGGER_STDERR' in os.environ:
        stderrer = logging.StreamHandler(sys.stderr)
        stderrer.setFormatter(commonformatter)
        root.addHandler(stderrer)

if conf.logging_config == 'disable':
    disableConfig()
elif conf.logging_config == 'default':
    defaultConfig()
elif callable(conf.logging_config):
    conf.logging_config()
else:
    raise ValueError('unknown logging setup "%s".' % conf.logging_config)
