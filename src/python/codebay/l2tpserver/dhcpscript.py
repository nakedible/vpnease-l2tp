"""DHCP script executed by dhclient in various situations.

See man dhclient(8), man dhclient.conf(5), man dhclient-script(8) for
more information.  dhclient-script(8) contains descriptions of the
situations where the script is invoked, and the relevant parameters
in each case.

This script assumes that the dhcp interface has already been configured
to be up before running dhclient.  It also relies on a running l2tp
gateway script: received dhcp parameters are *not* configured to system
directly.  Instead, they are written to a temporary file and a signal
given to the l2tp gateway script to activate the changes.
"""
__docformat__ = 'epytext en'

import os, sys, textwrap
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants
from codebay.common import datatypes
from codebay.common import logger

run_command = runcommand.run_command

class DhcpScript:
    _log = None

    def __init__(self, pub_iface=None, priv_iface=None):
        """Constructor."""

        reason = self._safe_getenv('reason')
        self._log = logger.get('l2tpserver.dhcpscript.%s' % reason)
        self._get_params()

        self.outfile = None
        if pub_iface is not None and self.params['interface'] == pub_iface:
            self.outfile = constants.DHCP_INFORMATION_PUBLIC
            self.outfile_backup = constants.DHCP_INFORMATION_PUBLIC_NAFTALIN_HACK # XXX: required only for 1.0 compatibility
        else:
            if priv_iface is not None and self.params['interface'] == priv_iface:
                self.outfile = constants.DHCP_INFORMATION_PRIVATE
                self.outfile_backup = constants.DHCP_INFORMATION_PRIVATE_NAFTALIN_HACK # XXX: required only for 1.0 compatibility

        if self.outfile is None:
            m = 'Failed to find proper interface to operate on.'
            self._log.exception(m)
            raise Exception(m)

    def _safe_getarg(self, i):
        """Internal helper to get command line arguments."""
        try:
            return sys.argv[i]
        except:
            return None

    def _safe_getenv(self, i):
        """Internal helper to get environment variables."""
        try:
            return os.environ[i]
        except:
            return None

    def _get_params(self):
        """Get DHCP script parameters from the environment.

        See man dhclient-script(8) for a description of (most) environment
        variables.  Unfortunately the man page does not seem to contain
        all variables - see the default /etc/dhclient-script for some
        more variables.  Some variables come from dhclient directly, while
        some are given by the DHCP server and mapped to environment
        variables by dhclient.

        This function gets all environment variables potentially needed
        by any $reason and sets them as instance variables.  Missing
        variables are set to None.
        """

        static_param_list = ['reason', 'interface', 'medium', 'alias_ip_address', 'alias_subnet_mask']

        variable_param_list = ['ip_address', 'subnet_mask', 'routers', 'static_routes', 'broadcast_address', 'domain_name_servers', 'domain_name', 'time_offset', 'interface_mtu', 'network_number', 'dhcp_server_identifier', 'netbios_name_servers']

        self.params = {}
        for i in static_param_list:
            self.params[i] = self._safe_getenv(i)

        for i in variable_param_list:
            self.params['new_' + i] = self._safe_getenv('new_' + i)
            self.params['old_' + i] = self._safe_getenv('old_' + i)

    def _send_signal_to_l2tpgw(self, signame):
        run_command([constants.CMD_DHCLIENT_SIGNAL, signame], retval=runcommand.FAIL)
        self._log.debug('sent %s to l2tpgw' % signame)

    def _handle_medium(self):
        # Debian Unstable ignores MEDIUM
        return 0

    def _handle_preinit(self):
        # Debian Unstable PREINIT ifconfigs interface up to allow packet
        # sending - we assume that has already been done.  It also
        # handles alias interface(s) which we don't care about.
        return 0

    def _handle_bound_renew_rebind_reboot(self):
        # Handling of BOUND, RENEW, REBIND, and REBOOT is very similar
        # so they share a handler (as in Debian Unstable dhclient-script).

        reason = self.params['reason']

        # Address changed?
        addr_changed = False
        if (self.params['old_ip_address'] is not None) and (self.params['old_ip_address'] != self.params['new_ip_address']):
            self._log.info('ip address on interface %s changed: %s -> %s' % (self.interface, self.params['old_ip_address'], self.params['new_ip_address']))
            addr_changed = True

        # Ignore event?
        ignore_event = True
        if (self.params['old_ip_address'] is None) or addr_changed or (reason == 'BOUND') or (reason == 'REBOOT'):
            ignore_event = False
            
        if ignore_event:
            self._log.info('ignoring event')
            return 0
        
        # Write or update DHCP information file and send appropriate signal to L2TP script
        interface = self.params['interface']
        address = self.params['new_ip_address']
        netmask = self.params['new_subnet_mask']

        # Router determination
        #   - If server gives it directly, use it always
        #   - If not, and new_dhcp_server_identifier looks like an IP address, use it
        #   - Otherwise no router (this probably causes problems elsewhere, but we have no info)
        try:
            router = self.params['new_routers'].split(' ')[0]
            self._log.debug('determined router to be %s (own address %s)' % (router, address))
        except:
            try:
                router = datatypes.IPv4Address.fromString(self.params['new_dhcp_server_identifier']).toString()
                self._log.info('defaulting dhcp router to %s for dhcp-assigned address %s (server did not give router address)' % (router, address))
            except:
                self._log.info('cannot determine router for dhcp-assigned address %s' % address)
                router = ''

        dns1, dns2 = '', ''
        if self.params['new_domain_name_servers'] is not None:
            dns_servers = self.params['new_domain_name_servers'].split(' ')
            if len(dns_servers) >= 1:
                dns1 = dns_servers[0]
            if len(dns_servers) >= 2:
                dns2 = dns_servers[1]
            if len(dns_servers) >= 3:
                self._log.info('ignoring extra dns servers')

        wins1, wins2 = '', ''
        if self.params['new_netbios_name_servers'] is not None:
            wins_servers = self.params['new_netbios_name_servers'].split(' ')
            wins1, wins2 = '', ''
            if len(wins_servers) >= 1:
                wins1 = wins_servers[0]
            if len(wins_servers) >= 2:
                wins2 = wins_servers[1]
            if len(wins_servers) >= 3:
                self._log.info('ignoring extra wins servers')

        dhcpinfo = textwrap.dedent("""\
        %s
        %s
        %s
        %s
        %s
        %s
        %s
        """) % (address, netmask, router, dns1, dns2, wins1, wins2)
        
        self._log.info('changed dhcpinfo:\n%s' % dhcpinfo)

        try:
            f = open(self.outfile, 'wb')
            self._log.debug('_handle_bound_renew_rebind_reboot: fd=%s' % f.fileno())
            f.write(dhcpinfo)
            f.close()
        except:
            # XXX: This fails if we are run from old 1.0 naftalin
            # sources (/var/run/l2tpgw/dhcp directory does not exist
            self._log.warning('failed to write dhcp-script output to default location')

        # XXX: this should never fail (writes to /tmp)
        f = open(self.outfile_backup, 'wb')
        self._log.debug('_handle_bound_renew_rebind_reboot (backup file): fd=%s' % f.fileno())
        f.write(dhcpinfo)
        f.close()

        # Send signal to l2tp script
        if addr_changed:
            self._send_signal_to_l2tpgw('SIGHUP')
        else:
            self._send_signal_to_l2tpgw('SIGUSR1')
        return 0

    def _handle_bound(self):
        return self._handle_bound_renew_rebind_reboot()
    
    def _handle_renew(self):
        return self._handle_bound_renew_rebind_reboot()

    def _handle_rebind(self):
        return self._handle_bound_renew_rebind_reboot()

    def _handle_reboot(self):
        self._log.warning('received DHCP REBOOT event which should not happen - but still reporting it.')
        return self._handle_bound_renew_rebind_reboot()

    def _send_sigusr2(self):
        # Send signal to l2tp script
        self._send_signal_to_l2tpgw('SIGUSR2')
        return 0

    def _handle_expire(self):
        return self._send_sigusr2()
    
    def _handle_fail(self):
        return self._send_sigusr2()
    
    def _handle_stop(self):
        # Ignore - dhclient asked to shutdown gracefully (SIGTERM)
        return 0
    
    def _handle_release(self):
        # Ignore - dhclient asked to release (-r flag)
        return 0
    
    def _handle_nbi(self):
        # Ignore - should not happen
        self._log.error('received DHCP NBI (no broadcast interfaces) event - ignoring')
        return 0
    
    def _handle_timeout(self):
        return self._send_sigusr2()

    def run(self):
        try:
            self._run()
        except:
            self._log.exception()
            raise

    def _run(self):
        self._log.debug(os.environ)  # XXX: may be insecure, but do for now

        reason = self.params['reason']

        # Handling of various reasons has been modeled after default
        # /etc/dhclient-script (Debian Unstable)
        if reason == 'MEDIUM': return self._handle_medium()
        elif reason == 'PREINIT': return self._handle_preinit()
        elif reason == 'BOUND': return self._handle_bound()
        elif reason == 'RENEW': return self._handle_renew()
        elif reason == 'REBIND': return self._handle_rebind()
        elif reason == 'REBOOT': return self._handle_reboot()
        elif reason == 'EXPIRE': return self._handle_expire()
        elif reason == 'FAIL': return self._handle_fail()
        elif reason == 'STOP': return self._handle_stop()
        elif reason == 'RELEASE': return self._handle_release()
        elif reason == 'NBI': return self._handle_nbi()
        elif reason == 'TIMEOUT': return self._handle_timeout()
        else:
            self._log_warning('Unknown dhcpscript reason: %s, skipping' % reason)
            return 0
