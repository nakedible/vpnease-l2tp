"""Ez-IPupdate daemon configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap

from codebay.common import rdf
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

# XXX: check that pidfile creation works
# XXX: other options? -h hostname, -i interface, -p period,
# -q, -r retries
# Note: --pidfile option not understood for some reason, use -F

class EzipupdateConfig(daemon.DaemonConfig):
    name = 'ezipupdate'
    command = constants.CMD_EZIPUPDATE
    pidfile = constants.EZIPUPDATE_PIDFILE
    cleanup_files=[]
    do_start = False

    def get_args(self):
        args = ['-c', constants.EZIPUPDATE_CONF]
        args += ['-d', # daemon
                # Note: cannot give cache file here because config is
                # not resolved and public interface name is used for
                # cache file name. See config file below for cache
                # file location.
                # '-b', constants.EZIPUPDATE_CACHE,
                '-F', constants.EZIPUPDATE_PIDFILE]

        return args
    
    def create_config(self, cfg, resinfo):
        """Create configuration file for ez-ipupdate.

        See http://www.shakabuku.org/writing/dyndns.html.
        """

        global_st = helpers.get_global_status()
        pub_iface, pub_iface_name = helpers.get_public_iface(cfg)
        pub_dyndns_cfg = helpers.get_dyndns_config(cfg)

        conf = textwrap.dedent("""\
        # intentionally empty
        """)

        self.do_start = False
        if pub_dyndns_cfg is not None:
            self.debug_on = helpers.get_debug(cfg)
            if self.debug_on:
                debug = 'debug'
            else:
                debug = ''

            self._log.debug('Dynamic DNS configured')
            provider = pub_dyndns_cfg.getS(ns.provider, rdf.String)
            username = pub_dyndns_cfg.getS(ns.username, rdf.String)
            password = pub_dyndns_cfg.getS(ns.password, rdf.String)
            hostname = pub_dyndns_cfg.getS(ns.hostname, rdf.String)

            # address selection is complicated due to many options
            address = None
            if pub_dyndns_cfg.hasS(ns.dynDnsAddress):
                addr = pub_dyndns_cfg.getS(ns.dynDnsAddress)
                if addr.hasType(ns.DynDnsInterfaceAddress):
                    address = None
                elif addr.hasType(ns.DynDnsStaticAddress):
                    address = addr.getS(ns.ipAddress, rdf.IPv4Address).toString()
                elif addr.hasType(ns.DynDnsManagementConnectionAddress):
                    if global_st.hasS(ns.managementConnectionOurNattedAddress):
                        address = global_st.getS(ns.managementConnectionOurNattedAddress, rdf.IPv4Address).toString()
                    else:
                        address = None
                else:
                    raise Exception('invalid dynDnsAddress type')
            if address == '':
                address = None
            address_str = ''
            if address is not None:
                address_str = 'address=%s' % address
                
            interface_str = 'interface=%s' % pub_iface_name
                
            self._log.debug('Dynamic DNS parameters: provider=%s, username=%s, password=%s, hostname=%s, address=%s, interface=%s' % (provider, username, password, hostname, address, pub_iface_name))

            # NB: persistent cache is required for proper dyndns operation
            
            conf = textwrap.dedent("""\
            #!/usr/local/bin/ez-ipupdate -c

            service-type=%(provider)s
            user=%(username)s:%(password)s
            host=%(hostname)s
            %(address)s
            %(interface)s
            max-interval=2073600
            %(debug)s
            cache-file=%(cache_file_stem)s.%(pubif)s
            daemon
            """) % {'provider':provider,
                    'username':username,
                    'password':password,
                    'hostname':hostname,
                    'address':address_str,
                    'interface':interface_str,
                    'cache_file_stem':constants.EZIPUPDATE_CACHE,
                    'pubif':pub_iface_name,
                    'debug':debug}

            self.do_start = True
        else:
            self._log.debug('No dynamic DNS configured')

        self.configs = [{'file': constants.EZIPUPDATE_CONF,
                         'cont': conf,
                         'mode': 0755}]

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

    def start(self):
        """Start ez-ipupdate."""

        # This will be OK even with an empty config file, so no need
        # to check whether dynamic DNS updates are enabled

        # XXX: it seems like this cannot be run without proper config
        # file -> ez-ipupdate complains of missing default service
        # type

        # XXX: it is possible to "force" an address using the -a
        # (--address) option.  This could fix the use case where the
        # gateway is behind a NAT and we would want to register the
        # public address.  To do this, we would need the public
        # address from a rendezvous server, in practice, a management
        # server.

        if self.do_start:
            daemon.DaemonConfig.start(self)
