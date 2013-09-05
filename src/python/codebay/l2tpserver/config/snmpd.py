"""Snmpd configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap

from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

class SnmpdConfig(daemon.DaemonConfig):
    name = 'snmpd'
    command = constants.CMD_SNMPD
    pidfile = constants.SNMPD_PIDFILE
    cleanup_files=[]

    def get_args(self):
        dopts = ['-LS',   # Log to syslog
                 '4',     # Log warning and higher levels
                 'd']     # With LOG_DAEMON facility

        if self.debug_heavy:
            dopts = ['-a',    # Log source address of incoming messages
                     '-d',    # Dump SNMP messages in hex
                     '-DALL', # Turn on debugging output on all tokens
                     '-LS',
                     '7',     # All including debug levels
                     'd']
        elif self.debug_on:
            dopts = ['-LS',
                     '7',
                     'd']

        return dopts + ['-u', 'snmp', '-p', self.pidfile]

    def create_config(self, cfg, resinfo):
        snmp_cfg = cfg.getS(ns.snmpConfig, rdf.Type(ns.SnmpConfig))
        snmp_community = snmp_cfg.getS(ns.snmpCommunity, rdf.String)
        snmp_syslocation = 'VPNease server'
        snmp_syscontact = 'None'
        vpnease_mib = constants.SNMP_MIB_MODULE_SO

        self.debug_on = helpers.get_debug(cfg)
        self.debug_heavy = helpers.get_debug_heavy(cfg)

        # XXX: set syslocation and syscontact more intelligently?
        snmpd_conf = textwrap.dedent("""\
        # Minimal configuration example for VPNease snmpd

        com2sec readonly default %(community)s
        group rogroup v1 readonly
        group rogroup v2c readonly
        group rogroup usm readonly

        #           incl/excl subtree                          mask
        view all    included  .1                               80

        #                context sec.model sec.level match  read   write  notif
        access rogroup   ""      any       noauth    exact  all    none   none

        syslocation %(syslocation)s
        syscontact %(syscontact)s

        dlmod vpneaseMIB %(mibmodule)s
        """ % {'community':snmp_community,
               'syslocation':snmp_syslocation,
               'syscontact':snmp_syscontact,
               'mibmodule':vpnease_mib})
        
        self.configs = [{'file': constants.SNMPD_CONF,
                         'cont': snmpd_conf,
                         'mode': 0600}]

    def post_start(self):
        pass

    def post_stop(self):
        pass
