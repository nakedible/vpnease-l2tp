"""L2TP/IPsec server protocol level functionality.

Initializes daemon configuration from configuration files, starts
daemons, configures interfaces and firewalls, and enters a monitoring
loop.  Monitoring loop watches over processes, checks and (re)initiates
site-to-site connections, etc.  Status and failures are reported to web
UI through RDF status tree, but independent panic actions are not taken
here.
"""
__docformat__ = 'epytext en'

# About configuration sanity checking
# -----------------------------------
# 
# The code in this module expects the RDF configuration to be correctly formed
# and already sanity checked.  The code *will* raise an exception if nodes or
# arcs are missing from the RDF graph.  However, the code *will not* raise an
# exception if some parameter value is insane, e.g., if PPP lcp-echo-timeout
# is 1 second.  The expectation is that the web user interface or another
# external entity performs a sanity check before a configuration is committed.
# 
# L2TP plaintext leakage
# ----------------------
# 
# XXX: L2TP plaintext leakage is difficult to prevent in all corner cases.
# This is difficult because packets are not seen in places where filtering
# would be done.  Black hole routes can prevent some problems.

import re
import os
import sys
import signal
import time
import datetime
import select
import textwrap

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver.rdfconfig import ns
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import configresolve
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver import pppscripts
from codebay.l2tpserver import db

from codebay.l2tpserver.config import \
     dhclient, \
     ezipupdate, \
     firewall, \
     interface, \
     ippool, \
     openl2tp, \
     pluto, \
     portmap, \
     pppd, \
     freeradius, \
     snmpd, \
     dhcp

run_command = runcommand.run_command
_log = logger.get('l2tpserver.startstop')

# ----------------------------------------------------------------------------

class Error(Exception):
    pass

class InternalError(Error):
    pass

class GotSigTermError(Error):
    pass

class StartFailedError(Error):
    pass

class StartFailedInterfaceError(StartFailedError):
    pass

class RuntimeError(Error):
    pass

class DhcpNoResponseError(Error):
    pass

class DhcpChangedError(Error):
    pass

class DhcpExpiredError(Error):
    pass

class RecheckSignalsError(Error):
    pass

class RebootRequiredError(Error):
    pass

class RoutersNotRespondingError(Error):
    pass

# ----------------------------------------------------------------------------

_state_starting_preparing = object()
_state_starting_waiting_for_dhcp = object()
_state_starting_network = object()
_state_starting_daemons = object()
_state_running = object()
_state_stopping = object()
_state_stopped = object()

_mode_full = object()
_mode_network_only = object()

# ----------------------------------------------------------------------------

class L2tpRunnerBase:
    """Process startup for L2TP.

    This class is subclassed to provide specialized runners for test modes
    etc.
    """

    _enable_forwarding = True
    _poll_interval_mainloop = constants.POLL_INTERVAL_MAINLOOP * 1000
    _dhcp_try_count = constants.DHCP_TRY_COUNT
    _dhcp_acquire_timeout = constants.DHCP_ACQUIRE_TIMEOUT
    _dhcp_poll_interval = constants.DHCP_POLL_INTERVAL * 1000
    _poll_interval_mainloop_sigusr1_sanity = constants.POLL_INTERVAL_MAINLOOP_SIGUSR1_SANITY * 1000
    _timeout_mainloop_sigusr1_sanity = constants.TIMEOUT_MAINLOOP_SIGUSR1_SANITY

    _mode = None

    def __init__(self, mode=_mode_full, nodistrorestart=False, importpath='system'):
        """Constructor."""
        self._mode = mode
        self._nodistrorestart = nodistrorestart
        self._importpath = importpath
        self.dhcp_running = False
        self.started_daemons = []
        self.pluto_config = None
        self.openl2tp_config = None

        self._flag_sigterm = False
        self._flag_sigusr1 = False
        self._flag_sigusr2 = False
        self._flag_sighup = False
        self._flag_sigalrm = False
        self._old_sigterm_handler = None
        self._old_sigusr1_handler = None
        self._old_sigusr2_handler = None
        self._old_sighup_handler = None
        self._old_sigalrm_handler = None

        self._resolved_info = None
    
    def _signal_handlers_ok(self):
        """Check whether signal handlers are OK (caught)."""

        return (self._old_sigterm_handler is not None) and \
               (self._old_sigusr1_handler is not None) and \
               (self._old_sigusr2_handler is not None) and \
               (self._old_sighup_handler is not None) and \
               (self._old_sigalrm_handler is not None)
               
    def _setup_signal_handlers(self):
        """Setup signal handlers.

        These signal handlers simply set instance flags to reflect received
        signals.  For instance, if SIGTERM is received, the instance
        variable _flag_sigterm is set to True.  Caller may set the flag
        back to False and wait for a new signal, though there is a slight
        chance of missed signals in this case.
        """

        def _sigterm_handler(signum, stackframe):
            _log.info('Received SIGTERM')
            self._flag_sigterm = True
        def _sigusr1_handler(signum, stackframe):
            _log.info('Received SIGUSR1')
            self._flag_sigusr1 = True
        def _sigusr2_handler(signum, stackframe):
            _log.info('Received SIGUSR2')
            self._flag_sigusr2 = True
        def _sighup_handler(signum, stackframe):
            _log.info('Received SIGHUP')
            self._flag_sighup = True
        def _sigalrm_handler(signum, stackframe):
            _log.info('Received SIGALRM')
            self._flag_sigalrm = True

        self._old_sigterm_handler = signal.getsignal(signal.SIGTERM)
        self._old_sigusr1_handler = signal.getsignal(signal.SIGUSR1)
        self._old_sigusr2_handler = signal.getsignal(signal.SIGUSR2)
        self._old_sighup_handler = signal.getsignal(signal.SIGHUP)
        self._old_sigalrm_handler = signal.getsignal(signal.SIGALRM)

        _log.debug('setting SIGTERM handler')
        signal.signal(signal.SIGTERM, _sigterm_handler)
        _log.debug('setting SIGUSR1 handler')
        signal.signal(signal.SIGUSR1, _sigusr1_handler)
        _log.debug('setting SIGUSR2 handler')
        signal.signal(signal.SIGUSR2, _sigusr2_handler)
        _log.debug('setting SIGHUP handler')
        signal.signal(signal.SIGHUP, _sighup_handler)
        _log.debug('setting SIGALRM handler')
        signal.signal(signal.SIGALRM, _sigalrm_handler)

    def _remove_signal_handlers(self):
        """Remove signal handlers."""

        signal.signal(signal.SIGTERM, self._old_sigterm_handler)
        signal.signal(signal.SIGUSR1, self._old_sigusr1_handler)
        signal.signal(signal.SIGUSR2, self._old_sigusr2_handler)
        signal.signal(signal.SIGHUP, self._old_sighup_handler)
        signal.signal(signal.SIGALRM, self._old_sigalrm_handler)

        self._old_sigterm_handler = None
        self._old_sigusr1_handler = None
        self._old_sigusr2_handler = None
        self._old_sighup_handler = None
        self._old_sigalrm_handler = None

    def _get_dhcp_address_information(self, iface, filename):
        """Read DHCP address information from a state file written by DHCP scripts."""

        if iface is None:
            return None

        _log.debug('Retrieve dhcp information from file: %s' % filename)

        rs = configresolve.DhcpAddressInfo()
        rs.interface = helpers.get_iface_name(iface)
        try:
            rs.read_dhcp_information(filename)
            _log.debug('Found dhcp information.')
        except:
            _log.debug('DHCP information not found from file')
            return None

        return rs

    def _wait_for_dhcp_address(self, cfg, pub_iface, priv_iface):
        """Wait for DHCP address.

        Start dhclient and wait for signal(s) from our dhclient script.

        Returns (ret, public_iface_addrinfo, private_iface_addrinfo),
        where ret is non-None if getting address(es) failed. If success,
        addrinfo(s) contain acquired DHCP addresses for public and/or
        private interfaces.
        """

        if pub_iface is None and priv_iface is None:
            return ('No DHCP interfaces', None, None)

        _log.info('Waiting for dhcp address(es)')

        # check sig handlers
        if not self._signal_handlers_ok():
            raise InternalError('signal handlers not initialized, but required by _wait_for_dhcp_address()')

        dh = dhclient.DhclientConfig()
        dh.create_config(cfg, None, importpath=self._importpath)
        dh.pre_stop()
        dh.soft_stop(silent=True)
        try:
            dh.hard_stop()
        except:
            raise RebootRequiredError('DHCP hard stop failed')

        dh.post_stop()

        dh.write_config()

        # XXX: clear signal statuses?
        # - this may lose some critical signal like sigterm even
        #   if we first check the signal flags before clearing them
        # - the signal flags should not be set at this point because
        #   in addition to main loop break, they are not used for
        #   anything else then dhcp checking.
        # - if we do not clear flags here, then signal flag meaning
        #   could be misunderstood in the dhcp wait loop.. no big deal..

        dh.pre_start()
        dh.start()
        dh.post_start()

        p = select.poll()

        start_time = time.time()
        while True:
            # Check for global timeout
            curr_time = time.time()
            if int(curr_time - start_time) > self._dhcp_acquire_timeout:
                m = 'DHCP acquire timeout reached without address(es)'
                return (m, None, None)

            # Check signal flags first before waiting.

            if self._flag_sigterm:
                self._flag_sigterm = False
                raise GotSigTermError()

            # Dhclient script has detected address change.
            if self._flag_sighup:
                self._flag_sighup = False
                raise DhcpChangedError()

            # This means that one of the dhclient interfaces has failed
            # (no DHCP lease found) and we should try again.
            if self._flag_sigusr2:
                self._flag_sigusr2 = False
                m = 'Got SIGUSR2: Unable to find DHCP address'
                _log.debug(m)
                return (m, None, None)

            # Dhclient script has found a *new* lease.
            if self._flag_sigusr1:
                self._flag_sigusr1 = False
                m = 'Got SIGUSR1: checking for acquired DHCP address.'
                _log.info(m)

                pub_status, pub_addr = None, None
                if pub_iface is not None:
                    pub_status = True
                    pub_addr = self._get_dhcp_address_information(pub_iface, constants.DHCP_INFORMATION_PUBLIC)
                    if pub_addr is None: pub_status = False

                priv_status, priv_addr = None, None
                if priv_iface is not None:
                    priv_status = True
                    priv_addr = self._get_dhcp_address_information(priv_iface, constants.DHCP_INFORMATION_PRIVATE)
                    if priv_addr is None: priv_status = False

                if (pub_status is None or pub_status) and (priv_status is None or priv_status):
                    m = 'DHCP address(es) acquired.'
                    _log.info(m)
                    return (None, pub_addr, priv_addr)

                m = 'DHCP status incomplete: pub: %s, priv: %s' % (pub_status, priv_status)
                _log.info(m)

            if self._flag_sigalrm:
                self._flag_sigalrm = False
                _log.info('Got SIGALRM while waiting for DHCP address, ignoring')

            # XXX: The second signal for another DHCP address may arrive
            # at this point and we wait without reason.  However, we won't
            # deadlock and will recover properly.

            # No signals yet, wait for signal ortimeout.
            @db.untransact()
            def _poll_func():
                try:
                    p.poll(self._dhcp_poll_interval)
                except select.error, (errno, errmsg):
                    if errno == 4:
                        _log.debug('Poll interrupted with signal.')
                    else:
                        _log.exception('Poll returned unexpected error')
                        raise StartFailedError('poll returned unexpected errno=%s' % errno)

            _poll_func()

    def _vmware_promisc_flip_fix(self, cfg):
        """Workaround for VMware problems on Windows platforms.

        In short, VMware on Windows has some problems with networking at least without
        VMware Tools.  For some reason, networking will not work correctly about 60-70%
        of the time.  In particular, DHCP usually succeeds, ARP requests can be sent
        but ARP responses are received.  The cause of this problem is not fully known
        and VMware does not offer any particular fix (or even admit the problem) at
        this point.  The problem is only apparent with bridged networking, not with
        NAT networking.

        After some investigation, it was noticed that manually configuring and de-
        configuring network interfaces works more or less robustly.  The triggering
        problem in our startup seems to be the writing of the 'proxy_arp' /proc
        files.  The write apparently causes some communication with the driver
        (virtual) hardware and hence VMware bridge, which remains in some bogus
        state.  The workaround which was manually detected was to flip the interface
        to promiscuous mode and immediately back to non-promiscuous mode.  This
        also interacts with the hardware, apparently fixing the VMware bridge
        problem.

        So, this function is called before DHCP (to ensure any proxy_arp writes
        from a previous stop have no effect) and after proxy_arp writing (to ensure
        the bridge is fixed afterwards).  Finally, if arping checks fail run-time,
        this is called just in case to 'nudge' VMware if necessary.  The nudging
        is done unconditionally (in non-VMware environments) as well, because
        it should not have side effects.

        Unfortunately even this fix does not seem 100%.  The remaining cases are
        handled by (a) runner restart if arping failure is consistent, and if
        that doesn't help, (b) guest reboot due to successive unclean runner
        restarts.  If that doesn't help, there is not automatic recourse.

        See: #890.
        """

        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)

        if pub_if_name is not None:
            # XXX: sleep between these commands? did not seem to have an effect.
            _log.info('running promisc flip fix for public interface %s' % pub_if_name)
            run_command([constants.CMD_IP, 'link', 'set', str(pub_if_name), 'on'])
            run_command([constants.CMD_IP, 'link', 'set', str(pub_if_name), 'off'])

        if priv_if_name is not None:
            # XXX: sleep between these commands? did not seem to have an effect.
            _log.info('running promisc flip fix for private interface %s' % priv_if_name)
            run_command([constants.CMD_IP, 'link', 'set', str(priv_if_name), 'on'])
            run_command([constants.CMD_IP, 'link', 'set', str(priv_if_name), 'off'])
    
    def _start_network_stage1(self, cfg):
        """Start networking, stage 1.

        Configures interfaces as far as possible without
        having interface addresses.
        """

        # vmware flip fix before anything to reset situation
        self._vmware_promisc_flip_fix(cfg)

        i = interface.InterfaceConfig()
        if not i.check_interface_existences(cfg):
            raise StartFailedInterfaceError()
        i.prepare_interfaces(cfg)

    def _update_intermediate_rdf_status(self, cfg, res_info):
        """Update resolved configuration into RDF state before configuring interfaces.

        The intent is to ensure that RDF status contains IP address information before
        interfaces are actually brought up.  This is important because some system
        components may be expecting to get accurate address information from RDF even
        at this early stage.

        A particular example is the web UI, which compares the local address of incoming
        connections against RDF state to determine which interface received the incoming
        connection.  If RDF state is not up-to-date *before* interfaces are activated,
        this determination could fail.  (See #479.)

        Currently we just update the IP address, but we could write more information
        here in the future.
        """

        now = datetime.datetime.utcnow()

        def _update_iface(st, ipaddr, macaddr, devname):
            st.setS(ns.ipAddress, rdf.IPv4AddressSubnet, ipaddr)
            #st.setS(ns.macAddress, rdf.String, macaddr)  # XXX: not known atm
            st.setS(ns.deviceName, rdf.String, devname)

        pub_if, priv_if = res_info.public_interface, res_info.private_interface
        
        st_root = helpers.get_status()

        if pub_if is not None:
            pub_addr = pub_if.address
            pub_mac = '00:00:00:00:00:00'  # XXX: not known at this point
            pub_dev = pub_if.device
            if st_root.hasS(ns.publicInterface):
                pub_if_st = st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
                _log.info('updating initial state of public interface: address=%s, mac=%s' % (pub_addr.toString(), pub_mac))
                _update_iface(pub_if_st, pub_addr, pub_mac, pub_dev)
        if priv_if is not None:
            priv_addr = priv_if.address
            priv_mac = '00:00:00:00:00:00'  # XXX: not known at this point
            priv_dev = priv_if.device
            if st_root.hasS(ns.privateInterface):
                priv_if_st = st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
                _log.info('updating initial state of private interface: address=%s, mac=%s' % (priv_addr.toString(), priv_mac))
                _update_iface(priv_if_st, priv_addr, priv_mac, priv_dev)
        
    def _start_network_stage2(self, cfg, res_info):
        """Start networking, stage 2.

        Configures the rest of networking, when interface addresses have been
        received from DHCP.  Adds addresses to interfaces and configures routes
        and DNS as well as the rest of the firewall config.
        """

        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
 
        f = firewall.FirewallConfig()
        _log.info('modprobing nat and conntrack modules')
        f.modprobe_nat_conntrack_modules()
        pub_addr = None
        if res_info.public_interface is not None:
            pub_addr = res_info.public_interface.address
        priv_addr = None
        if res_info.private_interface is not None:
            priv_addr = res_info.private_interface.address
        ppp_forced_iface = None
        ppp_forced_gw = None
        if res_info.ppp_forced_router is not None:
            ppp_forced_iface = res_info.ppp_forced_router.devname
            ppp_forced_gw = res_info.ppp_forced_router.router
        f.up_firewall_rules(cfg, pub_addr, priv_addr, ppp_forced_iface, ppp_forced_gw)

        i = interface.InterfaceConfig()
        if priv_addr is not None:
            i.interface_set_address(priv_if_name, priv_addr)
        if pub_addr is not None:
            i.interface_set_address(pub_if_name, pub_addr)

        # proxy arp
        i.up_proxyarp(cfg, res_info)

        # vmware flip fix after proxy ARP
        self._vmware_promisc_flip_fix(cfg)

        # dns servers
        i.up_dns(res_info.dns_servers)

        # routing
        i.up_routes(cfg, res_info)
        i.flush_route_cache()
        i.arping_routers(res_info)
        i.send_gratuitous_arps(res_info)
        
        # firewall
        f = firewall.FirewallConfig()
        f.up_qos_rules(cfg)

        # NB: We could check DNS servers and other network stuff here, too.
        # We don't, because they are checked in periodic monitoring wherever
        # that is appropriate and we don't want to slow down startup any more
        # than we have to.  Arpings are sent because they really are critical
        # to starting up reliably.

    @db.untransact()  # may take some time
    def _restart_distro_networking(self):
        """Restart networking of host Linux distribution."""
        
        _log.info('stopping distro networking (just in case)')
        (retval, retout, reterr) = run_command([constants.CMD_INITD_NETWORKING, 'stop'])

        _log.info('starting distro networking (may take several minutes if DHCP does not respond)')
        (retval, retout, reterr) = run_command([constants.CMD_INITD_NETWORKING, 'start'])

    def _get_start_daemons(self):
        """Return a list of daemons to start.

        Override in a subclass.
        """

        return []
    
    def _get_stop_daemons(self):
        """Return a list of daemons to stop.

        This list would typically be a reverse of start daemons, but may also
        contain 'paranoia' kills.

        Override in a subclass.
        """

        return []

    def _clear_runtime_state(self):
        """Reset (and re-initialize) runtime monitoring state.

        Note that this does *not* recreate the status node.  This is the UI's
        requirement.  We only call this for sanity, and for development
        convenience; the state should already be empty.
        """

        now = datetime.datetime.utcnow()

        def _init_iface(st):
            st.setS(ns.rxBytesCounter, rdf.Integer, 0)
            st.setS(ns.txBytesCounter, rdf.Integer, 0)
            st.setS(ns.rxPacketsCounter, rdf.Integer, 0)
            st.setS(ns.txPacketsCounter, rdf.Integer, 0)
            st.setS(ns.rxLastChange, rdf.Datetime, now)
            st.setS(ns.txLastChange, rdf.Datetime, now)
            st.setS(ns.rxRateMaximum, rdf.Float, 0.0)  # bytes/second
            st.setS(ns.txRateMaximum, rdf.Float, 0.0)
            st.setS(ns.rxRateCurrent, rdf.Float, 0.0)
            st.setS(ns.txRateCurrent, rdf.Float, 0.0)

        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(helpers.get_config())

        st_root = helpers.get_status()
        pppdevs = st_root.setS(ns.pppDevices, rdf.Type(ns.PppDevices))                       # nodeset

        # XXX: this is simply for compatibility; some code expects this node to exist
        # (e.g. exported configuration files)
        retiredpppdevs = st_root.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))  # nodeset

        if pub_if is not None:
            pub_if_st = st_root.setS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
            _init_iface(pub_if_st)
        if priv_if is not None:
            priv_if_st = st_root.setS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
            _init_iface(priv_if_st)

        # this initial update of state will get rx/tx counters correct for later
        # rate estimation and tracking
        try:
            lm = licensemanager.LicenseMonitor()
            lm.reconcile_system_and_rdf_state(first_time=True)
        except:
            # XXX: this happened when there was a bug in reconcile_system_and_rdf_state()
            # should we be lenient here?  probably not
            _log.exception('initial run of reconcile_system_and_rdf_state() failed')
            raise
            
    def _set_runner_state(self, st):
        """Set runner state.

        Sets runner state to RDF.  Also outputs the state to stdout for web UI.
        """

        def _print_state(st1, st2=None):
            str = '%s %s' % (constants.RUNNER_STATE_STRING_PREFIX, st1)
            if st2 is not None:
                str += ' %s' % st2
            print str
            
        st_root = helpers.get_status()
        if st == _state_starting_preparing:
            _print_state(constants.RUNNER_STATE_STRING_STARTING, constants.RUNNER_STATE_STRING_PREPARING)
            st_root.setS(ns.state, rdf.Type(ns.StateStarting)).setS(ns.subState, rdf.Type(ns.StateStartingPreparing))
        elif st == _state_starting_waiting_for_dhcp:
            _print_state(constants.RUNNER_STATE_STRING_STARTING, constants.RUNNER_STATE_STRING_WAITING_FOR_DHCP)
            st_root.setS(ns.state, rdf.Type(ns.StateStarting)).setS(ns.subState, rdf.Type(ns.StateStartingWaitingForDhcp))
        elif st == _state_starting_network:
            _print_state(constants.RUNNER_STATE_STRING_STARTING, constants.RUNNER_STATE_STRING_STARTING_NETWORK)
            st_root.setS(ns.state, rdf.Type(ns.StateStarting)).setS(ns.subState, rdf.Type(ns.StateStartingNetwork))
        elif st == _state_starting_daemons:
            _print_state(constants.RUNNER_STATE_STRING_STARTING, constants.RUNNER_STATE_STRING_STARTING_DAEMONS)
            st_root.setS(ns.state, rdf.Type(ns.StateStarting)).setS(ns.subState, rdf.Type(ns.StateStartingDaemons))
        elif st == _state_running:
            _print_state(constants.RUNNER_STATE_STRING_RUNNING)
            st_root.setS(ns.state, rdf.Type(ns.StateRunning))
        elif st == _state_stopping:
            _print_state(constants.RUNNER_STATE_STRING_STOPPING)
            st_root.setS(ns.state, rdf.Type(ns.StateStopping))
        elif st == _state_stopped:
            _print_state(constants.RUNNER_STATE_STRING_STOPPED)
            st_root.setS(ns.state, rdf.Type(ns.StateStopped))
        else:
            raise Exception('invalid state object: %s' % st)
        st_root.setS(ns.lastStateUpdate, rdf.Datetime, datetime.datetime.utcnow())

    def _set_start_time(self):
        st_root = helpers.get_status()
        st_root.setS(ns.startTime, rdf.Datetime, datetime.datetime.utcnow())

    def _set_stop_time(self):
        st_root = helpers.get_status()
        st_root.setS(ns.stopTime, rdf.Datetime, datetime.datetime.utcnow())

    def _restart_freeradius(self):
        p = freeradius.FreeradiusConfig()
        p.create_config(helpers.get_config(), self._resolved_info)

        p.pre_stop()
        try:
            p.soft_stop(silent=False)
        except:
            _log.warning('soft stop for freeradius failed, ignoring')

        p.hard_stop() # Will except if failing which is ok
        p.post_stop()

        p.write_config()

        p.pre_start()
        p.start()
        p.post_start()

    def _check_freeradius_restart_marker(self):
        try:
            if os.path.exists(constants.FREERADIUS_RESTART_MARKER):
                os.unlink(constants.FREERADIUS_RESTART_MARKER)
                self._restart_freeradius()
        except:
            _log.exception('freeradius restart check failed')

    def _process_pending_tasks(self):
        """Called when SIGALRM is received and in every mainloop iteration."""

        self._check_freeradius_restart_marker()

    def _mainloop_sig_checks(self):
        if self._flag_sigterm:
            self._flag_sigterm = False
            raise GotSigTermError()

        if self._flag_sighup:
            self._flag_sighup = False
            raise DhcpChangedError()

        if self._flag_sigusr2:
            self._flag_sigusr2 = False
            raise DhcpExpiredError()

        if self._flag_sigusr1:
            self._flag_sigusr1 = False
            raise RecheckSignalsError()

        if self._flag_sigalrm:
            self._flag_sigalrm = False
            self._process_pending_tasks()
            raise RecheckSignalsError()

    def _mainloop_callback(self):
        """Called on every mainloop iteration.

        Guaranteed to be called within self._poll_interval_mainloop seconds,
        but can also be called much, much sooner.  Any code here which
        performs periodic heavy operations must therefore track its
        own time.
        """

        # Process tasks which are pending and for which a signal is lost
        self._process_pending_tasks()
    
    def _get_mainloop_sleep(self):
        """Return next sleep in milliseconds.

        Default: self._poll_interval_mainloop.
        """
        return self._poll_interval_mainloop
    
    def _post_start(self):
        pass

    def _post_stop(self):
        pass

    def create_pidfile(self):
        """Create a pidfile for L2TP script."""

        f = open(constants.RUNNER_PIDFILE, 'wb')
        _log.debug('create_pidfile: fd=%s' % f.fileno())
        f.write('%s\n' % os.getpid())
        f.close()

    # XXX: refactoring?
    def _acquire_dhcp_address(self, cfg):
        pub_dhcp_if = helpers.get_public_dhcp_interface(cfg)
        priv_dhcp_if = helpers.get_private_dhcp_interface(cfg)

        # If no dhcp interface configured, return success with
        # no address information.
        if pub_dhcp_if is None and priv_dhcp_if is None:
            # Success
            self.dhcp_running = False
            return None, None

        self.dhcp_running = True

        pub_dhcp, priv_dhcp = None, None
        count = 0
        while count < self._dhcp_try_count:
            _log.info('Waiting for DHCP address %d...' % count)
            (ret, pub_dhcp, priv_dhcp) = self._wait_for_dhcp_address(cfg, pub_dhcp_if, priv_dhcp_if)
            if ret is None:
                # Success
                return pub_dhcp, priv_dhcp

            _log.debug('Failed: %s, %d' % (ret, count))
            count += 1

        # Failed to get all dhcp addresses.
        # This leads to runner exiting with error code; GUI will
        # iterate if necessary.
        raise DhcpNoResponseError('DHCP_TRY_COUNT reached (last error: %s)' % ret)

    def _remove_sainfo_dir(self):
        run_command([constants.CMD_RM, '-rf', constants.PLUTO_SAINFO_DIR])

    def _create_sainfo_dir(self):
        run_command([constants.CMD_MKDIR, '-p', constants.PLUTO_SAINFO_DIR])

    @db.transact()
    def start(self, cfg):
        """Start L2TP: networking, firewall, daemons.

        Blocks for DHCP address if necessary.  If interrupted through
        a signal, raises an Exception.  Exits when daemons are up and
        running.

        Assume that signal handlers are in place.  Also assumes that RDF
        status tree exists and is in good shape.  This is done by the UI
        in the product.
        """

        # check sig handlers
        if not self._signal_handlers_ok():
            raise InternalError('signal handlers not initialized, but required by start()')

        # init vars
        f = firewall.FirewallConfig()
        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))

        # log start with debug level
        _log.info('*** START, debug=%s ***' % helpers.get_debug_level_string(cfg))
        
        try:
            m = 'Cleaning up'
            _log.info(m)

            m = 'Creating Pluto sainfo directory'
            _log.info(m)
            self._create_sainfo_dir()

            m = 'Disabling forwarding'
            _log.info(m)
            f.disable_forwarding()

            m = 'Starting network stage 1'
            _log.info(m)
            self._start_network_stage1(cfg)

            self._set_runner_state(_state_starting_waiting_for_dhcp)

            m = 'Acquire DHCP address (if configured)'
            _log.info(m)
            pub_dhcp, priv_dhcp = self._acquire_dhcp_address(cfg)

            self._set_runner_state(_state_starting_network)

            m = 'Resolving configuration'
            _log.info(m)
            res_info = configresolve.ResolvedInfo()
            res_info.resolve(cfg, pub_dhcp, priv_dhcp)
            self._resolved_info = res_info
            
            _log.info('Resolved configuration dump:')
            _log.info(str(res_info))

            m = 'Writing intermediate RDF status before network stage 2'
            _log.info(m)
            self._update_intermediate_rdf_status(cfg, res_info)
            
            m = 'Starting network stage 2'
            _log.info(m)
            self._start_network_stage2(cfg, res_info)

            self._set_runner_state(_state_starting_daemons)

            if self._mode == _mode_full:
                m = 'Creating and writing daemon configurations'
                _log.info(m)
                self.started_daemons = self._get_start_daemons()
                for i in self.started_daemons:
                    i.create_config(cfg, res_info)
                    i.write_config()

                m = 'Pre-starting daemons'
                _log.info(m)
                for i in self.started_daemons:
                    i.pre_start()

                m = 'Starting daemons'
                _log.info(m)
                for i in self.started_daemons:
                    i.start()

                m = 'Post-starting daemons'
                _log.info(m)
                for i in self.started_daemons:
                    i.post_start()

                m = 'Enabling forwarding'
                _log.info(m)
                if self._enable_forwarding:
                    f.enable_forwarding()
            elif self._mode == _mode_network_only:
                m = 'Network only - no daemon start'
                _log.info(m)
            else:
                raise Exception('invalid mode: %s' % self._mode)
                    
            m = 'Post start'
            _log.info(m)
            self._post_start()
        except:
            _log.exception(m)
            raise

        # log start complete with debug level
        _log.info('*** START COMPLETE, debug=%s ***' % helpers.get_debug_level_string(cfg))

    @db.transact()
    def stop(self, silent=False, restart_distro_networking=True, all_daemons=False):
        """Stop and return system to a usable state."""

        f = firewall.FirewallConfig()
        i = interface.InterfaceConfig()

        # log stop
        _log.info('*** STOP, silent=%s, distronetworking=%s ***' % (silent, restart_distro_networking))
        
        def _retire_ppp_devices():
            pppscripts.nuke_all_ppp_devices(silent=silent)
            
        def _stop_daemons():
            daemons = self._get_stop_daemons(all_daemons=all_daemons)
            for d in daemons:
                try:
                    d.pre_stop()
                except:
                    _log.exception('Ignored failed pre stop')

            time.sleep(2) # XXX
            for d in daemons:
                try:
                    d.soft_stop(silent=silent)
                except:
                    _log.exception('Ignored failed stop')

            time.sleep(2) # XXX
            for d in daemons:
                try:
                    d.hard_stop()
                except:
                    _log.exception('Hard stop failed for daemon: %s' % d.get_name())
                    raise RebootRequiredError('Daemon hard stop failed')

            time.sleep(2) # XXX
            for d in daemons:
                try:
                    d.post_stop()
                except:
                    _log.exception('Ignored failed post stop')

        def _maybe_stop_daemons():
            if self._mode == _mode_full:
                return _stop_daemons()
            elif self._mode == _mode_network_only:
                _log.info('Network only - no daemon stop')
            else:
                raise Exception('invalid mode: %s' % self._mode)
            
        actions = [[lambda: i.down_proxyarp(), 'Disabling proxy ARP'],
                   [lambda: f.disable_forwarding(), 'Disabling forwarding'],
                   [lambda: f.down_qos_rules(), 'Removing QoS rules'],
                   [lambda: f.down_firewall_rules(), 'Shutting down firewall'],
                   [lambda: i.down_routes(), 'Removing routes'],
                   [lambda: i.down_interfaces(), 'Setting interfaces down'],
                   [lambda: i.flush_route_cache(), 'Flushing route cache'],
                   [lambda: _maybe_stop_daemons(), 'Stopping daemons (maybe)'],
                   [lambda: f.flush_conntrack(), 'Flushing conntrack state'],
                   [lambda: f.enable_forwarding(), 'Enabling forwarding'],
                   [lambda: self._remove_sainfo_dir(), 'Removing Pluto sainfo directory'],
                   [lambda: _retire_ppp_devices(), 'Retiring left-over PPP devices']]

        # don't reset RDF status tree here; it is left intact after exit, too.

        if restart_distro_networking:
            actions.append([lambda: self._restart_distro_networking(), 'Restarting distro networking'])

        actions.append([lambda: self._post_stop(), 'Post stop'])

        for act, msg in actions:
            _log.info(msg)
            try:
                act()
            except RebootRequiredError:
                _log.exception('*** STOP FAILED, action=%s ***' % msg)
                raise
            except:
                _log.exception(msg + ' failed: ignoring')

        # log stop complete
        _log.info('*** STOP COMPLETE, silent=%s, distronetworking=%s ***' % (silent, restart_distro_networking))

    def _run_raw(self, cfg):
        """Run, raising exceptions when ready to exit."""
        
        _log.info('L2TP starting')
        try:
            self._set_runner_state(_state_starting_preparing)
            self._setup_signal_handlers()
            self.stop(silent=True, restart_distro_networking=False, all_daemons=True)
            self.start(cfg)
        except StartFailedInterfaceError:
            _log.error('one or more interfaces do not exist')
            raise
        except RebootRequiredError:
            _log.error('start failed and requires a reboot')
            raise
        except:
            _log.exception('L2TP startup failed')
            raise StartFailedError()

        p = select.poll()

        # XXX: Eat away pending sigusr1 signals for DHCP success.
        start_time = time.time()
        while True:
            @db.untransact()
            def _poll_func1():
                try:
                    p.poll(self._poll_interval_mainloop_sigusr1_sanity)
                except select.error, (errno, errmsg):
                    if errno == 4:
                        _log.debug('Poll interrupted with signal.')
                    else:
                        _log.exception('Poll returned unexpected error')
                        raise StartFailedError('poll returned unexpected errno=%s' % errno)

            _poll_func1()
            
            if self._flag_sigusr1:
                _log.debug('Ignoring sigusr1 signal')

            curr_time = time.time()
            if int(curr_time - start_time) < self._timeout_mainloop_sigusr1_sanity:
                break
    
        # Prevent premature poll break
        self._flag_sigusr1 = False

        # Update state
        self._set_runner_state(_state_running)

        # Loop forever, waiting for signals
        while True:
            try:
                self._mainloop_sig_checks()
            except RecheckSignalsError:
                continue
            
            try:
                self._mainloop_callback()
            except RecheckSignalsError:
                continue

            # recheck signals before sleeping; this speeds up signal handling if
            # something is ignored in mainloop callback
            try:
                self._mainloop_sig_checks()
            except RecheckSignalsError:
                continue

            _log.info('L2TP: waiting for signals or events')

            # XXX: make this poll customizable
            #    1. poll FD registration (needed for testing connections)
            #    2. FD handling
            @db.untransact()
            def _poll_func2(wait_time):
                try:
                    p.poll(wait_time)
                except select.error, (errno, errmsg):
                    if errno == 4:
                        _log.debug('Poll interrupted with signal.')
                    else:
                        _log.exception('Poll returned unexpected error')
                        raise RuntimeError('poll returned unexpected errno=%s' % errno)

            t = self._get_mainloop_sleep()
            t = max(t, 0)
            t = min(t, self._poll_interval_mainloop)
            _poll_func2(t)

    @db.transact()
    def run(self):
        """Run the gateway: start, mainloop, stop.

        Cleans up previous state and starts L2TP gateway with the
        current configuration.  Loops forever, waiting for signals
        and other events.  Cleans up state on its way out.  This is
        the "main loop" of the L2TP gateway or other helpers.

        Exit reasons are implemented as Exceptions.  Code should
        throw a suitable exception, which is caught by this wrapper,
        and converted into appropriate process retval.

        Subclasses may customize behavior by setting instance
        booleans etc.
        """

        retval = constants.STARTSTOP_RETVAL_UNKNOWN
        silent_stop = True

        self._clear_runtime_state()
        self._set_start_time()

        try:
            try:
                try:
                    # four try-levels: we want generic logging first
                    try:
                        self._run_raw(helpers.get_config())
                    except:
                        _log.exception('run() caught exception')
                        raise

                except KeyboardInterrupt:
                    retval = constants.STARTSTOP_RETVAL_GOT_SIGTERM  # XXX
                    silent_stop = False

                except GotSigTermError:
                    retval = constants.STARTSTOP_RETVAL_GOT_SIGTERM
                    silent_stop = False

                except StartFailedInterfaceError:
                    retval = constants.STARTSTOP_RETVAL_START_INTERFACE_FAILED

                except StartFailedError:
                    retval = constants.STARTSTOP_RETVAL_START_FAILED

                except RuntimeError:
                    retval = constants.STARTSTOP_RETVAL_UNKNOWN
                    silent_stop = False

                except DhcpNoResponseError:
                    retval = constants.STARTSTOP_START_FAILED

                except DhcpChangedError:
                    retval = constants.STARTSTOP_RETVAL_DHCP_CHANGED
                    silent_stop = False

                except DhcpExpiredError:
                    retval = constants.STARTSTOP_RETVAL_DHCP_EXPIRED
                    silent_stop = False

                except RecheckSignalsError:
                    retval = constants.STARTSTOP_RETVAL_UNKNOWN

                except RebootRequiredError:
                    retval = constants.STARTSTOP_RETVAL_REBOOT_REQUIRED

                except RoutersNotRespondingError:
                    retval = constants.STARTSTOP_RETVAL_ROUTERS_NOT_RESPONDING

            finally:
                _log.info('L2TP stopping')

                # XXX: update status: stopping, reason
                try:
                    self._set_runner_state(_state_stopping)
                    if self._nodistrorestart:
                        self.stop(silent=silent_stop, restart_distro_networking=False)
                    else:
                        self.stop(silent=silent_stop)
                    self._remove_signal_handlers()
                except:
                    retval = constants.STARTSTOP_RETVAL_UNKNOWN
                    _log.exception('stopping failed')
        finally:
            try:
                self._set_runner_state(_state_stopped)
                self._set_stop_time()
            except:
                _log.exception('setting final runner state failed')

        sys.exit(retval)

# --------------------------------------------------------------------------

# XXX: generalize to helpers? we may need this elsewhere too
# XXX: send larger packets - we had earleir problem with small packets working but large ones not
# XXX: random padding to ping? otherwise compresses "too well"

@db.untransact()
def _ping_check(addr, interval=1.0, max_wait=5, dev=None):
    # From ping man page
    #
    #    If ping does not receive any reply packets at all it will exit with code 1.
    #    If a packet count and deadline are both specified, and fewer than count
    #    packets are received by the time the deadline has arrived, it will also exit
    #    with code 1.  On other error it exits with  code 2. Otherwise it exits with
    #    code 0. This makes it possible to use the exit code to see if a host is alive
    #    or not.
    #
    # We want to send multiple pings, and check whether any of the pings gets a
    # response.  Thus, we don't want to detect "partially working" configs.
    #
    # -i 1.0, -c 1, -w 5 will send 5 ping packets and be satisfied if at least
    # one response is received.  It will exit immediately after first response has
    # been received.

    dev_opt = []
    if dev is not None:
        dev_opt += ['-I', dev]
        
    [rv, ign1, ign2] = run_command([constants.CMD_PING, '-i', str(interval), '-c', '1', '-w', str(max_wait)] +
                                   dev_opt + [addr])
    return (rv == 0)

# XXX: generalize to helpers? we may need this elsewhere too
# we might use this to probe arp our dhcp address
@db.untransact()
def _arping_check(addr, interface=None, src_addr=None, max_wait=3):
    # Arpings are sent once per second, so max_wait is both timeout
    # and count. We also quit on first reply.
    [rv, ign1, ign2] = run_command([constants.CMD_ARPING, '-f', '-c', str(max_wait), '-s', str(src_addr), '-I', str(interface), addr])
    return (rv == 0)

@db.untransact()
def _wrapped_dns_resolve_host(dest):
    return helpers.dns_resolve_host(dest)

# --------------------------------------------------------------------------

class Monitor:
    def __init__(self, runner, interval=None):
        self.name = self.__class__.__name__
        self.runner = runner
        self.config = helpers.get_config()
        self.status = helpers.get_status()
        self.resolved_info = runner._resolved_info
        self.interval = interval
        self.last_update = None

        self.init()

    def check_monitor(self):
        now = time.time()

        do_update = False
        diff = None
        if self.last_update is not None:
            diff = now - self.last_update
            if diff < 0 or diff > self.interval:
                do_update = True
        else:
            do_update = True

        if not do_update:
            _log.debug('skipping update for %s, diff %s' % (self.name, diff))
            return None

        _log.debug('running update for %s, diff %s' % (self.name, diff))

        self.last_update = now
        return self.update()

    def init(self):
        pass
    
    def update(self):
        raise Exception('%s: unimplemented' % (self.name))

class ProcessMonitor(Monitor):
    def __init__(self, runner, daemons, interval=None):
        self.daemons = daemons
        Monitor.__init__(self, runner, interval=interval)

    def update(self):
        failures = 0

        for d in self.daemons:
            if not d.check_process():
                _log.warning('process is missing: %s' % d.get_name())
                failures += 1
        
        # update rdf
        health = (failures == 0)
        status = helpers.get_status()
        status.setS(ns.processHealthCheck, rdf.Boolean, health)
        
        # log & return
        if not health:
            _log.info('process monitor: failures=%d' % failures)
        else:
            _log.debug('process monitor: failures=%d' % failures)

        return health

class Router:
    def __init__(self):
        self.router_address = None
        self.devname = None
        self.rdf_status_node = None
        
class RouterMonitor(Monitor):
    """Monitor configured routers using arping.

    In addition to individual router status in RDF, this updater also
    updates self.no_responses_public and self.no_responses_private, which
    are set if no router for the interface had a successful arping check.
    Similarly self.last_success_public and self.last_success_private
    are set, timestamping the last time we got at least one response.
    If an interface is not configured or has zero routers, we pretend that
    the interface is successful.

    The intent here is to recover from network interface driver or similar
    problems, where the network interface is apparently up but still not
    functioning.  If at least one router is responding, the interface is
    probably OK.  This does not catch an interface which starts dropping
    e.g. 50% of packets systematically.

    This additional check was originally added due to suspected network
    interface problems related to VMware Server 1.0.5 on Windows XP SP2
    (Fujitsu-Siemens OEM).
    """

    def init(self):
        now = datetime.datetime.utcnow()

        status = helpers.get_status()
        router_statuses = status.setS(ns.routerStatuses, rdf.Bag(rdf.Type(ns.RouterStatus)))

        # figure out unique routers
        ri = self.resolved_info
        t = {}
        for r in ri.gateway_routes + ri.client_routes:
            router = r.router
            if router is not None:
                routerstr = router.toString()
                if not t.has_key(routerstr):
                    # XXX: we take devname from first match; if same
                    # IP appears on two devices, we miss the second
                    # one.  Perhaps this is no issue in practice.
                    rtr = t[routerstr] = Router()
                    rtr.router_address = router
                    rtr.devname = r.devname
                    st = router_statuses.new()
                    st.setS(ns.routeConfigs, rdf.Bag(rdf.Resource))
                    st.setS(ns.routerAddress, rdf.IPv4Address, router)
                    rtr.rdf_status_node = st
                        
                rtr = t[routerstr]
                rtr.rdf_status_node.getS(ns.routeConfigs, rdf.Bag(rdf.Resource)).append(r.rdf_route)
        routerlist = t.values()

        _log.debug('routerlist:')
        for r in routerlist:
            _log.debug('  addr=%s,dev=%s,st=%s' % (r.router_address, r.devname, r.rdf_status_node))

        self._routerlist = routerlist

        self.no_responses_public = False
        self.no_responses_private = False

        # Without a useful initial value, we never get a reasonable timestamp
        # here if the arping never works (i.e., we've tried for 1h).
        self.last_success_public = now
        self.last_success_private = now
        
    def update(self):
        """Check that all (unique) routers respond to arping."""

        now = datetime.datetime.utcnow()

        pubif = None
        if self.resolved_info.public_interface is not None:
            pubif = self.resolved_info.public_interface.device
        privif = None
        if self.resolved_info.private_interface is not None:
            privif = self.resolved_info.private_interface.device

        pub_success = False
        priv_success = False
        failed = []
        num_pub_routers = 0
        num_priv_routers = 0
        for rtr in self._routerlist:
            router = rtr.router_address
            iface = rtr.devname
            st = rtr.rdf_status_node
            
            srcaddr = None
            is_pub = False
            if iface == pubif:
                is_pub = True
                srcaddr = self.resolved_info.public_interface.address.getAddress().toString()
                num_pub_routers += 1
            elif iface == privif:
                is_pub = False
                srcaddr = self.resolved_info.private_interface.address.getAddress().toString()
                num_priv_routers += 1
            else:
                # XXX: this error handling is probably incorrect
                _log.error('do not know how to check router: cannot figure out src addr (router=%s, iface=%s)' % (router.toString(), iface))

            if not _arping_check(router.toString(), interface=iface, src_addr=srcaddr):
                failed.append(router.toString())
                st.setS(ns.routerHealthCheck, rdf.Boolean, False)
            else:
                if is_pub:
                    pub_success = True
                else:
                    priv_success = True
                st.setS(ns.routerHealthCheck, rdf.Boolean, True)

        self.no_responses_public = (num_pub_routers > 0) and (not pub_success)
        self.no_responses_private = (num_priv_routers > 0) and (not priv_success)
        
        run_flip_fix = False

        if self.no_responses_public:
            run_flip_fix = True
            _log.warn('no successful arpings for any routers in public interface')
        else:
            self.last_success_public = now
            
        if self.no_responses_private:
            run_flip_fix = True
            _log.warn('no successful arpings for any routers in private interface')
        else:
            self.last_success_private = now

        # vmware flip fix before anything to reset situation
        if run_flip_fix:
            # XXX: should be the same as startup config, currently potentially wrong
            cfg = helpers.get_config()
            self.runner._vmware_promisc_flip_fix(cfg)

        if len(failed) > 0:
            _log.warn('routers failed arping check: %s' % ', '.join(failed))
            return False
        else:
            _log.debug('all routers passed arping check')
            return True

class SiteToSiteTunnel:
    def __init__(self, user, tunnel_index, status_node):
        self.user = user
        self.username = user.getS(ns.username, rdf.String)
        self.tunnel_index = tunnel_index
        self.incarnation = 0 # how many restarts
        self.status_node = status_node

    def get_tunnel_id(self):
        return 's2s-%d-%d' % (self.tunnel_index, self.incarnation)

    def bump_incarnation(self):
        self.incarnation += 1

    def has_incarnation(self):
        return self.incarnation > 0  # 0 = no prev incarnation
    
class SiteToSiteTunnelMonitor(Monitor):
    # This dictionary is used to track resolved endpoints of site-to-site
    # (client role) connections.  We need to prevent initiations to the
    # same IP address, as both Pluto and Openl2tp will croak if this happens.
    # The dictionary is maintained to track currently active site-to-site
    # endpoints.  The key is the URI string of the site-to-site user,
    # and the value is datatypes.IPv4Address.  This state is maintained
    # fully internally here, and is not exposed to RDF status (except for
    # detected errors).
    _sitetosite_resolved_endpoints = {}

    def _update_dns_mapping(self, tunnel):
        """Resolve remote site-to-site endpoint, updating internal resolved endpoints.

        Performs sanity checks; in particular, prevents multiple resolutions to match
        the same endpoint, and resolution to match public or private address.  Only
        resolved addresses matching sanity criteria end up in the resolved dictionary.
        Return True if resolution is successful (= safe to reinit), False otherwise.
        """
        user = tunnel.user
        s2s = user.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
        user_uri = str(user.getUri())
            
        # remove rdf endpoint address
        tunnel.status_node.removeNodes(ns.tunnelRemoteAddress)

        # remove previous dns mapping if exists
        if self._sitetosite_resolved_endpoints.has_key(user_uri):
            _log.debug('removing old mapping %s -> %s' % (user_uri,
                                                          self._sitetosite_resolved_endpoints[user_uri].toString()))
            del self._sitetosite_resolved_endpoints[user_uri]

        # resolve DNS name of endpoint from scratch (to recover from DNS changes)
        dest = s2s.getS(ns.destinationAddress, rdf.String)
        addrs = _wrapped_dns_resolve_host(dest)
        if len(addrs) == 0:
            _log.warning('site-to-site endpoint %s cannot be resolved, skipping' % dest)
            return False

        # select first mapping
        addr = addrs[0]
        _log.debug('using the endpoint address %s for site-to-site dest %s' % (addr.toString(), dest))
            
        # also update rdf -- XXX: only update if matches sanity?
        tunnel.status_node.setS(ns.tunnelRemoteAddress, rdf.IPv4Address, addr)

        # check whether conflicting mappings exist
        for i in self._sitetosite_resolved_endpoints.keys():
            res_addr = self._sitetosite_resolved_endpoints[i]
            if res_addr == addr:
                # XXX: we may want to propagate this error to UI in some fashion
                _log.error('site-to-site: resolved endpoint %s->%s conflicts with previously resolved endpoint, skipping' % (dest, addr.toString()))
                return

        # prevent reiniting to own public or private address
        ownaddr = self.resolved_info.public_interface.address.getAddress()

        if addr == ownaddr:
            _log.warning('insane resolution, resolves to own public address (%s), site-to-site client %s' % (addr.toString(), tunnel.username))
            return False
        if self.resolved_info.private_interface is not None:
            if addr == self.resolved_info.private_interface.address.getAddress():
                _log.warning('insane resolution, resolves to own private address (%s), site-to-site client %s' % (addr.toString(), tunnel.username))
                return False

        # update mappings
        self._sitetosite_resolved_endpoints[user_uri] = addr
        _log.debug('adding mapping %s -> %s' % (user_uri,
                                                self._sitetosite_resolved_endpoints[user_uri].toString()))
        return True
    
    def _stop_tunnel(self, tunnel):
        if tunnel.has_incarnation():
            ol = openl2tp.Openl2tpConfig()
            ol.stop_client_connection(tunnel.get_tunnel_id())
            pc = pluto.PlutoConfig()
            pc.stop_client_connection(tunnel.get_tunnel_id(), silent=True)  # may fail
        else:
            _log.debug('tunnel %s does not have a previous incarnation, skipping' % (tunnel.username))
            
    def _start_tunnel(self, tunnel):
        user = tunnel.user
        s2s = user.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
        user_uri = str(user.getUri())

        ownaddr = self.resolved_info.public_interface.address.getAddress()

        addr = self._sitetosite_resolved_endpoints[user_uri]
        if addr is None:
            _log.warning('cannot reinit to unknown endpoint, site-to-site client %s (should not happen)' % tunnel.username)
            return

        # XXX: if untransact required here, the parameters to pluto
        # and openswan connection starts cannot be rdf nodes
        pc = pluto.PlutoConfig()
        pc.start_client_connection(tunnel.get_tunnel_id(), ownaddr, addr)
        ol = openl2tp.Openl2tpConfig()
        ol.start_client_connection(tunnel.get_tunnel_id(), ownaddr, addr, user.getS(ns.username, rdf.String), user.getS(ns.password, rdf.String))

    def _rewrite_pluto_psks(self):
        extra_psks = []
        for t in self._sitetositetunnels:
            user = t.user
            user_uri = str(user.getUri())
            s2s = user.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
            role = s2s.getS(ns.role)
            is_client = role.hasType(ns.Client)

            # NB: because we never accept a DNS resolution matching to our own address,
            # such site-to-site tunnels should never make it here
            if is_client and self._sitetosite_resolved_endpoints.has_key(user_uri):
                extra_psks.append([ self._sitetosite_resolved_endpoints[user_uri].toString(),
                                    s2s.getS(ns.preSharedKey, rdf.Binary) ])

        _log.debug('extra psks: %s' % str(extra_psks))

        pc = pluto.PlutoConfig()
        pc.create_config_pluto(self.config, self.resolved_info, extra_psks)
        pc.write_config()
        pc.reread_psks()

    def init(self):
        status = helpers.get_status()
        s2s_statuses = status.setS(ns.siteToSiteStatuses, rdf.Bag(rdf.Type(ns.SiteToSiteStatus)))

        # figure out site-to-site connections to watch
        index = 1  # start from 1
        res = []
        users_cfg = helpers.get_config().getS(ns.usersConfig, rdf.Type(ns.UsersConfig))
        for u in users_cfg.getS(ns.users, rdf.Bag(rdf.Type(ns.User))):
            if not u.hasS(ns.siteToSiteUser):
                continue

            st = s2s_statuses.new()
            st.setS(ns.tunnelConfig, rdf.Resource, u)
            st.setS(ns.addressCheckFailure, rdf.Boolean, False)
            res.append(SiteToSiteTunnel(u, index, st))
            index += 1

        # log monitored names
        t = []
        for i in res:
            t.append(i.username)
        _log.info('list of site-to-site usernames to monitor: %s' % ', '.join(t))

        self._sitetositetunnels = res

    def update(self):
        """Check site-to-site connections for liveness and take appropriate
        action if not.

        The check we use for site-to-site liveness is simply ping the remote
        endpoint of the PPP connection.  If there is no response, we reinitialize
        the site-to-site connection.

        XXX: We're doing a slow O(n^2) lookup here by first iterating through
        site-to-site connections; and then, per site to site connection, iterating
        through all ppp device statuses.  The latter could be optimized by proper
        cross-referencing.

        XXX: We should report status of client and server connections separately,
        as the recovery action is different; for client connections, we reinit.
        For server connections, we cannot do anything unless the cause is within
        our control (e.g. process failure).  Server site-to-sites might be down for
        a good reason, e.g. remote endpoint is down for maintenance.

        XXX: report status back to UI.
        """

        success = []
        failure = []
        reinit = []
        
        for t in self._sitetositetunnels:
            user = t.user
            username = t.username
            user_uri = str(user.getUri())
            s2s = user.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
            role = s2s.getS(ns.role)
            is_client = role.hasType(ns.Client)
            _log.debug('site-to-site aliveness check for %s' % username)

            # check role; only client connections are reinited
            role = s2s.getS(ns.role)
            is_client = role.hasType(ns.Client)

            # first check whether a ppp device exists; if not, reinit
            dev_ok = False
            devstatus = None
            for d in helpers.get_ppp_devices():
                if d.hasS(ns.username) and d.getS(ns.username, rdf.String) == username:
                    dev_ok = True
                    devstatus = d
                    break
            _log.debug('dev_ok=%s' % dev_ok)

            if not dev_ok: 
                _log.debug('no device, failed')
                failure.append(username)
                t.status_node.setS(ns.tunnelHealthCheck, rdf.Boolean, False)
                
                if is_client:
                    reinit.append(t)
                continue

            # if ppp device exists, try pinging remote endpoint
            addr = devstatus.getS(ns.pppRemoteAddress, rdf.IPv4Address)
            devname = devstatus.getS(ns.deviceName, rdf.String)
            if _ping_check(addr.toString(), dev=devname):
                _log.debug('ping ok')
                success.append(username)
                t.status_node.setS(ns.tunnelHealthCheck, rdf.Boolean, True)

                # clear here just in case
                t.status_node.setS(ns.addressCheckFailure, rdf.Boolean, False)
            else:
                _log.debug('no ping response, failed')
                failure.append(username)
                t.status_node.setS(ns.tunnelHealthCheck, rdf.Boolean, False)
                if is_client:
                    reinit.append(t)

        # reinit: stop all failed connections
        for t in reinit:
            self._stop_tunnel(t)
            
        # reinit: reresolve endpoints
        _log.debug('old dns mappings: %s' % str(self._sitetosite_resolved_endpoints))
        new_reinit = []
        for t in reinit:
            # Tunnels end up on new_reinit list only if they can actually be reinited.
            # For instance, a tunnel may be stopped because it is not responding, but
            # it's possible it cannot be reinited if it doesn't resolve or it resolves
            # to one of our own IP addresses.
            if self._update_dns_mapping(t):
                new_reinit.append(t)
            else:
                _log.debug('not reiniting to %s because did not resolve (or conflicts)' % t)
        reinit = new_reinit
        _log.debug('new reinit: %s' % reinit)
        _log.debug('new dns mappings: %s' % str(self._sitetosite_resolved_endpoints))

        # reinit: rewrite pluto psks
        if len(reinit) > 0:
            self._rewrite_pluto_psks()
        
        # reinit: bump incarnations
        for t in reinit:
            t.bump_incarnation()
            
        # reinit: (re)start all failed connections
        for t in reinit:
            self._start_tunnel(t)

        # final logging, and return value
        if len(failure) > 0:
            _log.warning('some site to site failures; success=%s, failure=%s' % (', '.join(success),
                                                                                 ', '.join(failure)))
            return False
        else:
            _log.debug('all site-to-site connections pass checks')
            
        return True

class PingableServer:
    """Represents one server that we want to monitor using ping (DNS, WINS, RADIUS)."""
    def __init__(self):
        self.server_address = None
        self.rdf_status_node = None

class PingableServerMonitor(Monitor):
    def init(self):
        config = helpers.get_config()
        status = helpers.get_status()
        server_statuses = status.setS(ns.serverStatuses, rdf.Bag(rdf.Type(ns.ServerStatus)))

        ri = self.resolved_info
        srvlist = []

        used_server_addresses = []
        
        # dns/wins
        for s in ri.dns_servers + ri.ppp_dns_servers + ri.ppp_wins_servers:
            if s.address in used_server_addresses:
                continue
            srv = PingableServer()
            srv.server_address = s.address
            st = server_statuses.new()
            st.setS(ns.serverAddress, rdf.IPv4Address, s.address)
            st.setS(ns.serverConfig, rdf.Resource, s.rdf_server_list)
            srv.rdf_status_node = st
            srvlist.append(srv)
            used_server_addresses.append(s.address)
            

        # radius, if available (we check because we need to work with 1.0 rdf too)
        # XXX: this is from config, not from resolvedinfo, which would be better
        if config.hasS(ns.radiusConfig):
            for s in config.getS(ns.radiusConfig, rdf.Type(ns.RadiusConfig)).getS(ns.radiusServers, rdf.Seq(rdf.Type(ns.RadiusServer))):
                try:
                    # XXX: currently we assume that the RADIUS server has a fixed IP address for several reasons
                    # but the RDF type is still a String.
                    addr = s.getS(ns.address, rdf.String)
                    ipaddr = datatypes.IPv4Address.fromString(addr)
                    if ipaddr in used_server_addresses:
                        continue
                    srv = PingableServer()
                    srv.server_address = ipaddr
                    st = server_statuses.new()
                    st.setS(ns.serverAddress, rdf.IPv4Address, ipaddr)
                    st.setS(ns.serverConfig, rdf.Resource, s)
                    srv.rdf_status_node = st
                    srvlist.append(srv)
                    used_server_addresses.append(ipaddr)
                except:
                    _log.exception('failed to add radius server to pingable server list')
                
        _log.debug('dns/wins/radius list:')
        for s in srvlist:
            _log.debug('  %s,%s' % (s.server_address, s.rdf_status_node))

        self._srvlist = srvlist

    def update(self):
        """Check that all DNS/WINS/RADIUS servers respond to ping.

        Ping is not the best approach.  However, testing DNS or WINS server
        reachability at application level is not very nice either: bogus DNS
        resolutions cause annoying admin logs, and WINS resolution is not
        trivial from Linux.  Hence ping.
        """
        
        failed = []
        for srv in self._srvlist:
            addr = srv.server_address
            if not _ping_check(addr.toString()):
                failed.append(addr.toString())
                srv.rdf_status_node.setS(ns.serverHealthCheck, rdf.Boolean, False)
            else:
                srv.rdf_status_node.setS(ns.serverHealthCheck, rdf.Boolean, True)
                
        if len(failed) > 0:
            _log.warn('dns/wins/radius servers failed ping check: %s' % ', '.join(failed))
            return False
        else:
            _log.debug('all dns/wins/radius servers passed arping check')
            return True

class LicenseMonitor(Monitor):
    def init(self):
        # NB: need a persistent instance, because lm maintains state about failure counts
        self._lm = licensemanager.LicenseMonitor()

    def update(self):
        # This ignores devices not 'up', thus sparing larval ppp devices
        self._lm.reconcile_system_and_rdf_state()  # XXX: long transaction, but difficult to fix
        return True

class DynDnsAddressMonitor(Monitor):
    def __init__(self, runner, interval=None):
        self.runner = runner
        self._addr_re = re.compile(r'^address\s*=\s*(.*?)\s*$')
        Monitor.__init__(self, runner, interval=interval)

    def update(self):
        #
        #  To avoid all possible races, re-read the currently configured
        #  static address from the ez-ipupdate config file.
        #

        if not os.path.exists(constants.EZIPUPDATE_CONF):
            _log.debug('no dyndns config, no action')
            return True

        #
        #  Skip all checks if we're not in 'NATted' mode
        #
        cfg = helpers.get_config()
        pub_dyndns_cfg = helpers.get_dyndns_config(cfg)
        if pub_dyndns_cfg is None:
            _log.debug('no dyndns rdf config, no action')
            return True

        if not pub_dyndns_cfg.hasS(ns.dynDnsAddress):
            _log.debug('no dyndns rdf config / dynDnsAddress, no action')
            return True

        need_to_check = False
        addr = pub_dyndns_cfg.getS(ns.dynDnsAddress)
        if addr.hasType(ns.DynDnsInterfaceAddress):
            pass
        elif addr.hasType(ns.DynDnsStaticAddress):
            pass
        elif addr.hasType(ns.DynDnsManagementConnectionAddress):
            need_to_check = True

        if not need_to_check:
            _log.debug('dyndns is not configured to use natted management connection address, no action')
            return True

        #
        #  Figure out currently configured address
        #
        prev_addr = None
        f = None
        try:
            f = open(constants.EZIPUPDATE_CONF, 'rb')
            for i in f.readlines():
                i = i.strip()
                m = self._addr_re.match(i)
                if m is not None:
                    prev_addr = m.group(1).strip()
                    break
        finally:
            if f is not None:
                f.close()
                f = None

        if prev_addr is None:
            _log.debug('no dyndns configured address, no action')
            return True
        prev_addr = datatypes.IPv4Address.fromString(prev_addr)

        #
        #  Figure out current 'NATted' address (as seen by mgmt server
        #
        global_st = helpers.get_global_status()
        if not global_st.hasS(ns.managementConnectionOurNattedAddress):
            _log.debug('no global status natted address, no action')
            return True
        curr_addr = global_st.getS(ns.managementConnectionOurNattedAddress, rdf.IPv4Address)

        #
        #  Address changed?
        #
        if prev_addr == curr_addr:
            _log.debug('old and current addresses match: %s vs. %s' % (prev_addr.toString(), curr_addr.toString()))
            return True
        _log.info('DynDnsAddressMonitor: address changed: %s -> %s, reconfiguring and restarting ez-ipupdate' % (prev_addr.toString(), curr_addr.toString()))

        #
        #  Yes, reconfigure and restart ez-ipupdate
        #
        ez = ezipupdate.EzipupdateConfig()
        try:
            ez.pre_stop()
            ez.soft_stop(silent=True)
            ez.hard_stop()
            ez.post_stop()
        except:
            _log.exception('ezipupdate stopping failed')
            raise
        
        try:
            ez.create_config(cfg, self.runner._resolved_info)
            ez.write_config()
        except:
            _log.exception('ezipupdate configuration creation failed')
            raise

        try:
            ez.pre_start()
            ez.start()
            ez.post_start()
        except:
            _log.exception('ezipupdate start failed')
            raise

        _log.info('DynDnsAddressMonitor: stop, reconfigure, start ok')

        return True


# --------------------------------------------------------------------------

class L2tpRunner(L2tpRunnerBase):
    arping_restart_limit = datetime.timedelta(0, 15*60, 0)  # 15 mins
    arping_warning_limit = datetime.timedelta(0, 5*60, 0)   # 5 mins
    
    def _get_start_daemons(self):
        if self._mode == _mode_full:
            self.pluto_config = pluto.PlutoConfig()
            self.openl2tp_config = openl2tp.Openl2tpConfig()

            return [portmap.PortmapConfig(),
                    freeradius.FreeradiusConfig(),
                    self.pluto_config,
                    pppd.PppdConfig(),
                    self.openl2tp_config,
                    ippool.IppoolConfig(),
                    ezipupdate.EzipupdateConfig(),
                    snmpd.SnmpdConfig(),
                    dhcp.DhcpConfig()] # MonitConfig not included
        elif self._mode == _mode_network_only:
            return []
        else:
            raise Exception('unknown mode: %s' % self._mode)

    # Note: although pppd is stopped *after* openl2tp, the pppd pre-stop takes
    # care of trying a clean pppd stop (silently) so that the clients have
    # a chance for a normal disconnect.
    # Note: pppd could also be stopped before openl2tp, but it would not
    # guarantee that pppd processes are not spawned by openl2tp after the
    # pppd stop (post-stop could be used in that case, though).
    def _get_stop_daemons(self, all_daemons=False):
        if self._mode == _mode_full:
            if all_daemons:
                d = [dhcp.DhcpConfig(),
                     ezipupdate.EzipupdateConfig(),
                     ippool.IppoolConfig(),
                     openl2tp.Openl2tpConfig(),
                     pppd.PppdConfig(),
                     pluto.PlutoConfig(),
                     freeradius.FreeradiusConfig(),
                     snmpd.SnmpdConfig(),
                     portmap.PortmapConfig()] # MonitConfig not included
            else:
                # Note: intentionally using the same instances but in reverse order
                d = list(self.started_daemons)
                d.reverse()

            # Dhclient always stopped, because: just in case :-)
            # Note: dhclient config is not preserved from start which is ok
            # XXX: this generates warning if dhclient is not started.
            d.append(dhclient.DhclientConfig())
            return d
        elif self._mode == _mode_network_only:
            return [dhclient.DhclientConfig()]
        else:
            raise Exception('unknown mode: %s' % self._mode)

    def _get_monitored_daemons(self):
        # XXX: ez-ipupdate exits when config is not exactly correct
        # (eg. wrong password or expired account, etc).  It is not
        # desirable to panic from that kind of errors and there is no
        # "soft" errors in monitoring: all errors eventually cause
        # service restart or reboot. The short-term fix is now to
        # remove ez-ipupdate from monitored daemons.

        # Note: must use a copy of the original list here!
        d = []
        for i in self.started_daemons:
            if not isinstance(i, ezipupdate.EzipupdateConfig):
                d.append(i) 

        # XXX: hack: dhclient is not included in start daemons because
        # it is started separately
        if self.dhcp_running:
            d.append(dhclient.DhclientConfig())
        return d

    def _post_start(self):
        t = []

        self._router_monitor = None

        if self._mode == _mode_full:
            rtr_mon = RouterMonitor(self, interval=300.0)
            self._router_monitor = rtr_mon
            for i in [ ProcessMonitor(self, self._get_monitored_daemons(), interval=60.0),
                       rtr_mon,
                       PingableServerMonitor(self, interval=300.0),
                       SiteToSiteTunnelMonitor(self, interval=150.0),   # 2.5 minutes
                       DynDnsAddressMonitor(self, interval=300.0),
                       LicenseMonitor(self, interval=60.0) ]:
                t.append(i)
        elif self._mode == _mode_network_only:
            for i in [ ProcessMonitor(self, self._get_monitored_daemons(), interval=60.0),
                       RouterMonitor(self, interval=300.0),
                       PingableServerMonitor(self, interval=300.0),
                       LicenseMonitor(self, interval=60.0) ]:
                t.append(i)
        else:
            raise Exception('unknown mode: %s' % self._mode)

        self._monitored_things = t
        
    def _update_rdf_status_timestamp(self, now):
        status = helpers.get_status()
        status.setS(ns.lastPollTime, rdf.Datetime, now)
        
    def _mainloop_callback(self):
        _log.debug('_mainloop_callback')

        now = datetime.datetime.utcnow()

        # gather successes and failures as strings for logging later
        success = []
        failure = []
        nocheck = []
        
        # NB: It is important to start with process check; an openl2tp problem
        # may manifest itself as very long RPC timeouts, making the entire cycle
        # take several minutes (even tens of minutes).  We thus want to flag
        # process errors ASAP.

        for m in self._monitored_things:
            got_exception = False
            rv = None
            try:
                rv = m.check_monitor()
            except:
                got_exception = True
                _log.exception('checking excepted for %s' % m.name)

            if got_exception:
                failure.append(m.name)
                _log.debug('check failed (exception) for %s' % m.name)
            elif rv is None:
                nocheck.append(m.name)
                _log.debug('no check for %s' % m.name)
            elif rv is True:
                success.append(m.name)
                _log.debug('check ok for %s' % m.name)
            elif rv is False:
                failure.append(m.name)
                _log.debug('check failed for %s' % m.name)
            else:
                raise Exception('invalid rv: %s' % rv)
                failure.append(m.name)

        #
        #  Router monitor watchdog check: if no successful arping
        #  for a period of time, assume network interface is dead
        #  and exit runner.  This will cause web UI to restart runner
        #  hopefully fixing the situation.  If runner restart is not
        #  enough to fix it, there will be an eventual web UI watchdog
        #  reboot because of too many unclean runner restarts.
        #
        arping_failure = False
        if self._router_monitor is not None:
            rtr_mon = self._router_monitor

            pub_diff = now - rtr_mon.last_success_public
            if pub_diff > self.arping_restart_limit:
                _log.error('arping failure for public interface, time %s' % pub_diff)
                arping_failure = True
            elif pub_diff > self.arping_warning_limit:
                _log.warning('arping warning for public interface, time %s' % pub_diff)

            priv_diff = now - rtr_mon.last_success_private
            if priv_diff > self.arping_restart_limit:
                _log.error('arping failure for private interface, time %s' % priv_diff)
                arping_failure = True
            elif priv_diff > self.arping_warning_limit:
                _log.warning('arping warning for private interface, time %s' % priv_diff)
            
        #
        #  XXX: handle stale firewall rules here as well?
        #
        
        #
        #  XXX: how about stale pppds?
        #
        
        # log summary as info
        _log.info('mainloop check summary: %s/%s errors; success=%s, failure=%s, nocheck=%s' % (len(failure),
                                                                                                len(success) + len(failure) + len(nocheck),
                                                                                                ','.join(success),
                                                                                                ','.join(failure),
                                                                                                ','.join(nocheck)))

        # update last status check timestamp to rdf
        self._update_rdf_status_timestamp(datetime.datetime.utcnow())

        # arping failure?
        if arping_failure:
            _log.error('arping failure - raising RoutersNotRespondingError')
            raise RoutersNotRespondingError()

# XXX XXX
class L2tpPublicInterfaceTester(L2tpRunnerBase):
    def _get_start_daemons(self):
        """
        XXX: need a conn test daemon here for server mode.
        Alternatively: run this in the main eventloop instead..
        """

        return []
#        return [ezipupdate.EzipupdateConfig()]

    def _get_stop_daemons(self):
        return []

            # Running management connection test ?
            #   * Initial idea: gui control
            #   * One possibility: execute test client into background, wait for it to die
            #   * Meanwhile, respond to UDP/TCP test packets
            #   * Probably better idea: run (in blocking style) a twisted test command,
            #     which handles port bindings and management connection in the same
            #     event loop



