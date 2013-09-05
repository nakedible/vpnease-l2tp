"""dhcp3-server configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap, os

from codebay.common import rdf
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

class DhcpConfig(daemon.DaemonConfig):
    name = 'dhcp'
    command = constants.CMD_DHCPD3
    pidfile = constants.DHCPD3_PIDFILE
    cleanup_files=[]
    do_start = False

    def get_args (self):
        return ['-cf', constants.DHCP_CONF,
                '-q', # quiet
                # XXX: use normal hard-coded lease file location for now
                '-pf', constants.DHCPD3_PIDFILE] + self.interfaces

    def create_config(self, cfg, resinfo):

        pub_iface, pub_iface_name = helpers.get_public_iface(cfg)
        priv_iface, priv_iface_name = helpers.get_private_iface(cfg)

        conf = textwrap.dedent("""\
        # intentionally empty
        """)

        self.do_start = False

        # XXX: write config file and enable starting if dhcp enabled in configuration
        self._log.debug('No dhcp server configured')

        self.configs = [{'file': constants.DHCP_CONF,
                         'cont': conf,
                         'mode': 0644}]

    def check_process(self):
        if self.do_start:
            return daemon.DaemonConfig.check_process(self)
        else:
            return True

    def soft_stop(self, silent=False):
        if self.do_start:
            daemon.DaemonConfig.soft_stop(self, silent=silent)
        else:
            daemon.DaemonConfig.soft_stop(self, silent=True)

    def _prepare_lease_files(self):
        if not os.path.exists('/var/lib/dhcp3/dhcpd.leases'):
            self._log.info('dhcp server lease file not found, re-creating from scratch')
            run_command([constants.CMD_TOUCH, '/var/lib/dhcp3/dhcpd.leases'], retval=runcommand.FAIL)

        run_command([constants.CMD_CHMOD, '0644',  '/var/lib/dhcp3/dhcpd.leases'], retval=runcommand.FAIL)
        run_command([constants.CMD_CHOWN, 'dhcpd:dhcpd',  '/var/lib/dhcp3/dhcpd.leases'], retval=runcommand.FAIL)

        if os.path.exists('/var/lib/dhcp3/dhcpd.leases~'):
            run_command([constants.CMD_CHMOD, '0644',  '/var/lib/dhcp3/dhcpd.leases~'], retval=runcommand.FAIL)
            run_command([constants.CMD_CHOWN, 'dhcpd:dhcpd', '/var/lib/dhcp3/dhcpd.leases~'], retval=runcommand.FAIL)

    def pre_start(self):
        self._prepare_lease_files()

    def clear_leases(self):
        run_command([constants.CMD_RM, '-f', '/var/lib/dhcp3/dhcpd.leases', '/var/lib/dhcp3/dhcpd.leases~']) # Ignore errors
        self._prepare_lease_files()

    def start(self):
        if self.do_start:
            daemon.DaemonConfig.start(self)
