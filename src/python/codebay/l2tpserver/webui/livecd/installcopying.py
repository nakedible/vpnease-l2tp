__docformat__ = 'epytext en'

import datetime

from nevow import inevow, loaders, rend, url

from codebay.l2tpserver.webui import commonpage

from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui.livecd import livecddb
from codebay.l2tpserver.rdfconfig import ns_ui

_state_in_progress = object()
_state_failure = object()
_state_success = object()

#
#  XXX: we're (re)getting installer state a lot here, fix this as well
#

def _get_installer_state():
    try:
        f = open(constants.INSTALL_STATUS_FILE, 'rb')
        t = f.read()
        f.close()

        lines = t.split('\n')
        if lines[0] == 'success':
            return _state_success, 100.0, 'Installation complete', ''
        elif lines[0] == 'failure':
            return _state_failure, 0.0, 'Installation failed', ''
        else:
            return _state_in_progress, float(lines[0]), lines[1], lines[2]
    except:
        return _state_in_progress, 0.0, 'Starting installer', ''

class InstallCopyingPage(commonpage.LiveCdPage):
    template = 'livecd/installcopying.xhtml'
    pagetitle = u'Install / Recovery \u21d2 Installing (Step 4 of 4)'
    nav_disabled = True
    
    def _measure_progress(self):
        st, pct, ign1, ign2 = _get_installer_state()
        return pct

    def _get_activity_name(self):
        st, pct, act1, act2 = _get_installer_state()

        # Don't return a two level text now; the second level is too technical
        ##if act2 is not None and act2 != '':
        ##    return '%s: %s' % (act1, act2)

        return act1
        
    def _check_finished(self):
        st, pct, act1, act2 = _get_installer_state()
        return (st == _state_success)

    def _check_failed(self):
        st, pct, act1, act2 = _get_installer_state()
        return (st == _state_failure)

    def render_check_finished(self, ctx, data):
        # XXX: in the middle of rendering; cf. buffering
        # XXX: unused at the moment because of ajax support
        if self._check_finished():
            request = inevow.IRequest(ctx)
            request.redirect(request.URLPath().sibling('installcomplete.html'))
            request.finish()
            return ''

        if self._check_failed():
            request = inevow.IRequest(ctx)
            request.redirect(request.URLPath().sibling('installfailed.html'))
            request.finish()
            return ''

        return ''
    
    def render_targetmedium(self, ctx, data):
        return livecddb.get_livecd_database_root().getS(ns_ui.targetDevice, rdf.String)

class AjaxProgressPage(commonpage.AjaxPage):
    def handle_request(self, ctx):
        st, pct, act1, act2 = _get_installer_state()

        state = 'failure'
        if st == _state_in_progress:
            state = 'in-progress'
        elif st == _state_success:
            state = 'success'

        # Don't return a two level text now; the second level is too technical
        act = act1
        ##if act2 is not None and act2 != '':
        ##    act = '%s: %s' % (act1, act2)

        return "%s\n(%d%%)\n[%s]\n%.2f" % (state, int(pct), act, float(pct))
