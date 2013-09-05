"""Dhclient daemon configuration wrapper."""
__docformat__ = 'epytext en'

import textwrap, time

from codebay.common import rdf
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon

ns = rdfconfig.ns
run_command = runcommand.run_command

# List of dhclient3 options relevant here:
#  -nw: causes dhclient to run entirely as daemon process.
#  -1 : try once -> fail: exit code 2, success: exit code 0?
#  -d : foreground, no-daemon
#  -n : do not configure interfaces
#  -cf: config file location
#  -lf: lease file location
#  -pf: pid file location
#  -sf: script file location
#   -q: only errors to stderr

# Note: -q -flag is not useful when client is not run in the
# foreground at all.

# XXX: use select timeout or not?
# XXX: possible to use debug options?
# XXX: add leases file to cleanup files?

class DhclientConfig(daemon.DaemonConfig):
    name = 'dhclient'
    command = constants.CMD_DHCLIENT
    pidfile = constants.DHCLIENT_PIDFILE
    cleanup_files = [constants.DHCP_INFORMATION_PUBLIC,
                     constants.DHCP_INFORMATION_PRIVATE]

    def get_args(self):
        return ['-nw',
                '-cf', constants.DHCLIENT_CONF,
                '-lf', constants.DHCLIENT_LEASES,
                '-pf', constants.DHCLIENT_PIDFILE,
                '-sf', constants.DHCLIENT_SCRIPT] + self.ifaces

    def _create_config(self, cfg, resinfo, timeout, retry, initial_interval, select_timeout, importpath):
        """Create dhclient configuration files."""

        args = ''
        self.ifaces = []

        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)
        if helpers.is_dhcp_interface(pub_iface):
            self.ifaces.append(pub_iface_name)
            args += "%r" % pub_iface_name
        else:
            args += '%r' % None

        if helpers.is_dhcp_interface(priv_iface):
            self.ifaces.append(priv_iface_name)
            args += ", %r" % priv_iface_name
        else:
            args += ', %r' % None

        if len(self.ifaces) == 0:
            raise Exception('Expected at least one configured DHCP interface, but found none.')

        conf = textwrap.dedent("""\
        # - automatically created file, do not modify.
        timeout %(timeout)s;
        retry %(retry)s;
        initial-interval %(initial_interval)s;
        # select-timeout %(select_timeout)s;
        send dhcp-lease-time 28800; # default is only 3600 seconds
        request subnet-mask, routers, domain-name-servers, netbios-name-servers;
        require subnet-mask;
        """) % {'timeout': timeout,
                'retry': retry,
                'initial_interval': initial_interval,
                'select_timeout': select_timeout}

        do_import = ''
        if importpath != 'system':
            do_import = 'sys.path = "%s".split(' ') + sys.path' % importpath

        script = textwrap.dedent("""\
        #!/usr/bin/python

        import sys

        %(do_import)s

        try:
            from codebay.l2tpserver import dhcpscript
            d = dhcpscript.DhcpScript(%(args)s)
            d.run()
        except:
            pass
        """) % {'do_import': do_import, 'args': args}

        leases = textwrap.dedent("""\
        """)

        self.configs = [{'file': constants.DHCLIENT_CONF,
                         'cont': conf,
                         'mode': 0644},
                        {'file': constants.DHCLIENT_SCRIPT,
                         'cont': script,
                         'mode': 0755},
                        {'file': constants.DHCLIENT_LEASES,
                         'cont': leases,
                         'mode': 0664}]

    def create_config(self, cfg, resinfo, importpath='system'):
        """Create dhclient configuration files."""

        self._create_config(cfg, resinfo, 60, 15, 2, 5, importpath)

    def hard_stop(self):
        """Hard stop dhclient."""

        self.d.hard_stop_daemon(command=self.command, pidfile=self.pidfile)
        self.d.cleanup_daemon(pidfile=self.pidfile, cleanup_files=self.cleanup_files)

        # XXX: ensure that if the system networking is used, the dhclient started
        # from the system scripts is no longer alive after stop. This is mostly
        # relevant in cases where system networking is configured manually and it
        # uses dhclient for configuring and stop is called before start to ensure
        # all relevant processes are down.
        run_command([constants.CMD_KILLALL, self.command])
        time.sleep(2)
        run_command([constants.CMD_KILLALL, '-9', self.command])
