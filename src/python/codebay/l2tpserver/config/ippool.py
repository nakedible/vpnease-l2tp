"""IpPool daemon configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap

from codebay.common import rdf
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

# Note: RPC failure every other start was caused by ippoold was
# not calling pmap_unset() at startup. (svc_unregister was not enough).
# Fixed now in ippoold source.

class IppoolConfig(daemon.DaemonConfig):
    name = 'ippool'
    command = constants.CMD_IPPOOL
    pidfile = constants.IPPOOL_PIDFILE
    cleanup_files = []

    def get_args(self):
        if self.debug_on:
            return ['-d']
        else:
            return []

    def create_config(self, cfg, resinfo):
        """Create ippool configuration file as string."""

        self.debug_on = helpers.get_debug(cfg)

        ppp_cfg = cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))

        ppp_subnet = ppp_cfg.getS(ns.pppSubnet, rdf.IPv4Subnet)
        if ppp_subnet.getCidr() > 30:
            raise Exception('PPP subnet does not contain enough usable addresses')
        ip_range = ppp_cfg.getS(ns.pppRange, rdf.IPv4AddressRange)

        conf = textwrap.dedent("""\
        pool create pool_name=clientpool
        pool address add pool_name=clientpool first_addr=%s num_addrs=%s netmask=%s
        """) % (ip_range.getFirstAddress().toString(),
                str(ip_range.size()),
                ppp_subnet.getMask().toString())

        self.configs = [{'file': constants.IPPOOL_CONF,
                         'cont': conf}]

    def post_start(self):
        # XXX: retval is zero when f.ex. config file is missing!
        # check srderr for error messages?
        run_command([constants.CMD_IPPOOLCONFIG, 'config', 'restore', 'file=' + constants.IPPOOL_CONF], retval=runcommand.FAIL)
