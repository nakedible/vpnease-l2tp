"""Monit wartchdog daemon configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap

from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import helpers
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

#
# NOTE: Monit currently *not* in use!
#

class MonitConfig(daemon.DaemonConfig):
    name = 'monit'
    command = constants.CMD_MONIT
    pidfile = constants.MONIT_PIDFILE
    cleanup_files=[constants.MONIT_STATE]

    def get_args(self):
        if self.debug_on:
            d = ['-v']
        else:
            d = []

        return ['-c', constants.MONIT_CONF,
                '-d', str(constants.MONIT_TIMEOUT),
                '-p', constants.MONIT_PIDFILE,
                '-s', constants.MONIT_STATE] + d

    def create_config(self, cfg, resinfo):
        # XXX: watchdog
        # - process status
        # - could also: use monit to run the process
        # - check process health (cpu usage, memory usage, etc.)

        self.debug_on = helpers.get_debug(cfg)

        params = {}
        params['webui_pid'] = constants.WEBUI_PIDFILE
        params['openl2tp_pid'] = constants.OPENL2TP_PIDFILE
        params['l2tpd_pid'] = constants.L2TPD_PIDFILE
        params['ippool_pid'] = constants.IPPOOL_PIDFILE
        params['pluto_pid'] = constants.PLUTO_PIDFILE
        params['ezipupdate_pid'] = constants.EZIPUPDATE_PIDFILE
        params['dhclient_pid'] = constants.DHCLIENT_PIDFILE
# XXX: reboot script?
#        params['fail_action'] = '/usr/bin/l2tpgw-reboot'
        params['fail_action'] = '/bin/true'
        params['stop_action'] = '/bin/true'

        dhcp_conf = ''
        if helpers.get_public_dhcp_interface(cfg) is not None or helpers.get_private_dhcp_interface(cfg) is not None:
            dhcp_conf = textwrap.dedent("""\

            # dhclient3
            check process dhclient3
                with pidfile \"%(dhclient_pid)s\"
                start program = \"%(fail_action)s\"
                stop program = \"%(stop_action)s\"
            """) % params


        # Note: not using monit httpd server:
        # set
        # set httpd port 2812 and use address localhost
        #     allow localhost
        #     allow admin:monit
        # Note: process health check, pluto cpu usage: if cpu > 90%, etc

        ezipupdate_conf = ''
        if helpers.get_dyndns_config(cfg) is not None:
            ezipupdate_conf = textwrap.dedent("""\

            # ez-ipupdate
            check process ez-ipupdate
                with pidfile \"%(ezipupdate_pid)s\"
                start program = \"%(fail_action)s\"
                stop program = \"%(stop_action)s\"
            """) % params

        conf = textwrap.dedent("""\
        set daemon 60
        set logfile syslog facility log_daemon

        check process twistd
            with pidfile \"%(webui_pid)s\"
            start program = \"%(fail_action)s\"
            stop program = \"%(stop_action)s\"

        check process openl2tp
            with pidfile \"%(openl2tp_pid)s\"
            start program = \"%(fail_action)s\"
            stop program = \"%(stop_action)s\"

        check process ippoold
            with pidfile \"%(ippool_pid)s\"
            start program = \"%(fail_action)s\"
            stop program = \"%(stop_action)s\"

        check process pluto
            with pidfile \"%(pluto_pid)s\"
            start program = \"%(fail_action)s\"
            stop program = \"%(stop_action)s\"
        """) % params
        
        self.configs = [{'file': constants.MONIT_CONF,
                         'cont': conf + dhcp_conf + ezipupdate_conf,
                         'mode': 0700}]
