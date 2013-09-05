import os

from codebay.common import twisted_amp as amp
from codebay.common import logger

_log = logger.get('common.amphelpers')

class LoggingAMP(amp.AMP):
    def _format_box(self, box):
        items = box.items()
        items.sort()
        a = []
        for k, v in items:
            if k[:1] == '_':
                continue

            # values are utf-8 encoded here (by amp), so decode them using utf-8 for logging
            try:
                esc = unicode(v, encoding='utf-8')
            except:
                esc = '<??? conversion failed ???>'

            if len(esc) > 256:
                esc = esc[:256] + '...'
            esc = esc.encode('unicode_escape')
            a.append('%s=%s' % (k, esc))
        return ', '.join(a)

    def _log_command(self, box):
        _log.info('received command %s: %s' % (box[amp.COMMAND], self._format_box(box)))

    def _log_answer(self, box):
        _log.info('sent answer: %s' % self._format_box(box))

    def _log_error(self, failure):
        _log.info('sent failure: %s' % failure)
        
    def dispatchCommand(self, box):
        # XXX:
        #
        #  - find COMMAND and ASK from box, give those to _log_answer
        #    and _log_error as well so the logs can show nicely which
        #    request produced which reply.
        #
        #  - catch errors from logging functions so they can never
        #    mess up the communication
        #
        #  - better way to represent failures
        #
        #  - allow ignoring of certain commands, for example keepalive
        #
        self._log_command(box)
        d = amp.AMP.dispatchCommand(self, box)
        def _answer(arg):
            self._log_answer(arg)
            return arg
        def _error(arg):
            self._log_error(arg)
            return arg
        d.addCallbacks(_answer, _error)
        return d
