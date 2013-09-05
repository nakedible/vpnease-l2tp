"""Portmap daemon configuration wrapper.

With this configuration, the portmapper start/stop is handled
wihtout system startup scripts. This means that when the l2tp
service is not running, no program may use portmap services.
Currently this is not a problem because no other program requires
it, but this may change in the future.

Portmap saved state is not currently used, but the state is
always cleared in stop/start. Restoring the portmap state
seems not to be so robust operation (a sleep is required in
the system startup scripts after portmap start and before
restoring the state so that pmap_set would work) and we do not
want to risk it going wrong.

The portmap upgrade state is only used for when upgrading
portmap package and storing state. The upgrade state is
currently ignored and deleted with warning if found.
"""
__docformat__ = 'epytext en'

import os

from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

class PortmapConfig(daemon.DaemonConfig):
    name = 'portmap'
    command = constants.CMD_PORTMAP
    # XXX: no option to background and does not write a pidfile, not using pidfile for now
    pidfile = None
    cleanup_files = []

    def get_args(self):
        return ['-i', '127.0.0.1']

    def create_config(self, cfg, state):
        pass

    def write_config(self):
        pass


    def _clear_state(self):
        """Clear portmap state.

        Remove openl2tpd and ippoold PROGRAM numbers from portmap state file
        so that their RPC registering will never fail.

        This is only useful if we want to emulate portmap startup
        script behaviour so that the portmap state is stored/restored in
        start/stop.

        Note: use this only if state-file handling is required, currently it is not done
        """

        progs_to_remove = ['300773', '300774', '300775']

        state = ''
        for line in open(constants.PORTMAP_STATEFILE):
            num = line.strip().split()[0]
            if num in progs_to_remove: continue
            state += line 

        helpers.write_file(constants.PORTMAP_STATEFILE, state, perms=0644)

    def pre_start(self):
        """Pre start actions for portmap. """

        if os.path.exists(constants.PORTMAP_UPGRADE_STATEFILE):
            self._log.warning('pre-start: portmap upgrade statefile found: removing without reading it.')
            os.unlink(constants.PORTMAP_UPGRADE_STATEFILE)

        if os.path.exists(constants.PORTMAP_STATEFILE):
            self._log.warning('pre-start: portmap statefile found: removing without reading it.')
            os.unlink(constants.PORTMAP_STATEFILE)

        # Note: use this only if state-file handling is required, currently it is not done
        #if not os.path.exists(constants.PORTMAP_STATEFILE):
        #    _log.warning('pre-start: no statefile found pormapper propably not stopped cleanly or still running.')
        #else:
        #    self._clear_state()

    def post_stop(self):
        """Post stop actions for portmap."""
        pass

        # Note: use this only if state-file handling is required, currently it is not done
        #if not os.path.exists(constants.PORTMAP_STATEFILE):
        #    self._log.warning('post-stop: no statefile found pormapper propably not stopped cleanly or still running.')
        #else:
        #    self._clear_state()
