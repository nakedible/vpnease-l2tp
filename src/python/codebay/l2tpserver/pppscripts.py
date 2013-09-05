"""PPP {ip-pre-up, ip-up, ip-down} script.

Actual /etc/ppp/{ip-pre-up, ip-up, ip-down} scripts create an instance
of PppScripts class, and call a relevant function (ppp_{ip_pre_up, ip_up,
ip_down}) from the instance.  Relevant configuration parameters, especially
public, private, and proxy ARP interfaces, are given as parameters to
the constructor.
"""
__docformat__ = 'epytext en'

import os, sys, datetime, textwrap, re, time

from codebay.common import logger
from codebay.common import rdf
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver import helpers
from codebay.l2tpserver.config import interface, openl2tp, pluto
from codebay.l2tpserver import db

run_command = runcommand.run_command
ns = rdfconfig.ns

_log = logger.get('l2tpserver.pppscripts')  # generic logger; scripts have their own

_re_l2tp_devicename = re.compile(r'^l2tp(\d+)-(\d+)$')

_fwd_reason_ui = object()
_fwd_reason_license_invalid = object()
_fwd_reason_license_exceeded = object()
_fwd_reason_license_prohibits = object()

# --------------------------------------------------------------------------
#
#  A few helpers
#

def _kill_pppd(pid, hard=False):
    if hard:
        run_command([constants.CMD_KILL, '-9', str(pid)], retval=runcommand.FAIL)
    else:
        run_command([constants.CMD_KILL, '-15', str(pid)], retval=runcommand.FAIL)

def _check_pppd_exists(pid):
    rv, stdout, stderr = run_command([constants.CMD_KILL, '-0', str(pid)])
    return (rv == 0)

@db.untransact()
def tear_down_fw(dev, silent=False):
    """Remove existing rules and chains (if exist) for specific PPP device.

    Can be safely called even when no device or chains exist, as a
    cleanup before configuring chains.

    This has been exposed because it may be called from other places besides
    PppScripts() instances.
    """

    _log.info('starting teardown firewall for device %s' % dev)

    commands = [ ['/sbin/iptables', '-t', 'raw', '-D', 'raw_prerouting_ppp', '-i', dev, '-j', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'raw', '-D', 'raw_output_ppp', '-o', dev, '-j', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'raw', '-F', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'raw', '-F', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'raw', '-X', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'raw', '-X', 'ppp_output_%s' % dev],

                 ['/sbin/iptables', '-t', 'filter', '-D', 'filter_input_ppp', '-i', dev, '-j', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-D', 'filter_output_ppp', '-o', dev, '-j', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-D', 'filter_forward_ppp', '-i', dev, '-j', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-D', 'filter_forward_ppp', '-o', dev, '-j', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-F', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-F', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-F', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-X', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-X', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'filter', '-X', 'ppp_forward_%s' % dev],

                 ['/sbin/iptables', '-t', 'nat', '-D', 'nat_prerouting_ppp', '-i', dev, '-j', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-D', 'nat_postrouting_ppp', '-o', dev, '-j', 'ppp_postrt_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-D', 'nat_output_ppp', '-o', dev, '-j', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-F', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-F', 'ppp_postrt_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-F', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-X', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-X', 'ppp_postrt_%s' % dev],
                 ['/sbin/iptables', '-t', 'nat', '-X', 'ppp_output_%s' % dev],
                 
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_prerouting_ppp', '-i', dev, '-j', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_input_ppp', '-i', dev, '-j', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_forward_ppp', '-i', dev, '-j', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_forward_ppp', '-o', dev, '-j', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_output_ppp', '-o', dev, '-j', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-D', 'mangle_postrouting_ppp', '-o', dev, '-j', 'ppp_postrt_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-F', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-F', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-F', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-F', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-F', 'ppp_postrt_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-X', 'ppp_prert_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-X', 'ppp_input_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-X', 'ppp_forward_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-X', 'ppp_output_%s' % dev],
                 ['/sbin/iptables', '-t', 'mangle', '-X', 'ppp_postrt_%s' % dev] ]

    errors, attempts = 0, 0

    # XXX: this locking is probably too heavy here, but try to use
    # it anyways because it could reduce errors
    iptables_lock = helpers.acquire_iptables_lock()

    try:
        for i in commands:
            attempts += 1
            try:
                # _log.info('teardown firewall command: %s' % str(i))
                run_command(i, retval=runcommand.FAIL, nologonerror=silent)
            except:
                if not silent:
                    _log.exception('running command in teardown failed')
                    errors += 1
    finally:
        helpers.release_iptables_lock(iptables_lock)

    if errors > 0 and not silent:
        _log.error('%d errors (%d attempts) in firewall teardown' % (errors, attempts))
    else:
        _log.debug('%d errors (%d attempts) in firewall teardown' % (errors, attempts))

    _log.info('tearing down firewall done: %s/%s' % (errors, attempts)) # XXX

def tear_down_qos(dev, silent=False):
    """Tear down device specific QoS settings.

    Currently no per-ppp-device QoS (tc) configuration is in use.
    """

    pass

def tear_down_ppp_routing(dev, silent=False):
    """Tear down device specific ppp routes.
    
    All routes to the device are automatically removed when the device
    is removed.
    """
    # XXX: teardown should not really be required, but may be added later if needed.
    pass

def nuke_all_ppp_devices(silent=True, kill_ppp=True):
    """Nuke all PPP devices."""
    devs = helpers.get_ppp_devices()

    to_nuke = []
    for i, d in enumerate(devs):
        if d.hasS(ns.deviceName):
            to_nuke.append(d.getS(ns.deviceName, rdf.String))
        else:
            # XXX: retire device node in RDF only? should not happen
            pass

    return nuke_ppp_devices(to_nuke,
                            silent=silent,
                            kill_ppp_soft=kill_ppp,
                            kill_ppp_soft_wait=15.0,
                            kill_ppp_hard=False,
                            kill_ppp_hard_wait=15.0)

def nuke_ppp_device(devname, silent=True, kill_ppp=True):
    return nuke_ppp_devices([devname],
                            silent=silent,
                            kill_ppp_soft=kill_ppp,
                            kill_ppp_soft_wait=15.0,
                            kill_ppp_hard=False,
                            kill_ppp_hard_wait=15.0)
    
@db.transact()
def nuke_ppp_devices(devnames,
                     silent=True,
                     kill_ppp_soft=True,
                     kill_ppp_soft_wait=15.0,
                     kill_ppp_hard=False,
                     kill_ppp_hard_wait=15.0):
    """Nuke a list of PPP devices, clearing interfaces, RDF, and pppd daemons.

    This function is the 'master helper' for cleaning PPP devices from the
    system.  The intent is for this function to clean up various aspects
    in a single place, for instance, to make RDF PPP devices list match with
    system state and so on.  Thus function is used from PPP scripts but also
    from system state reconciliation code.

    The basic steps done by this function are: (1) IP link down for all
    devices, (2) PPP devices are retired from RDF state, (3) soft kill
    is given to pppd processes, (4) soft kill is polled until devices
    disappear.  If devices don't disappear, hard kills are given and
    similarly waited.

    Hard kill timeout should be typically pretty long.  It is expected that
    the pppd instances will die quite soon after a hard kill.  If they don't,
    we should wait until they do, to do the right thing in load situations.
    However, if we believe that we have waited enough to eliminate any load
    issues, and the instance is not dead, it is not likely to die in the
    future either, as it is most likely e.g. stuck in the kernel.

    If, at the end of this function devices haven't been correctly cleaned
    by soft and/or hard kill, the function return False.  Otherwise it returns
    True.

    Because this function may take a lot of time, you should call this in
    most cases from an untransact wrapper.
    """

    now = datetime.datetime.utcnow()

    devnames_str = ','.join(devnames)
    _log.info('nuke_ppp_devices(): starting: devices=[%s], silent=%s, ' \
              'kill_ppp_soft=%s, kill_ppp_soft_wait=%s, kill_ppp_hard=%s, kill_ppp_hard_wait=%s' % \
              (devnames_str, silent, kill_ppp_soft, kill_ppp_soft_wait, \
               kill_ppp_hard, kill_ppp_hard_wait))

    def _check_remaining(pidlist):
        remaining = []
        for ppid in pidlist:
            if _check_pppd_exists(ppid):
                remaining.append(ppid)
        return remaining
    
    def _kill_and_wait(label, pidlist, hard, timeout):
        # we approximate number of integer loops because we don't want dependencies
        # on system time here
        loops = int(timeout)

        # Avoid delay in wait loop
        if len(pidlist) == 0:
            return []
        
        for ppid in pidlist:
            try:
                _kill_pppd(ppid, hard=hard)
            except:
                if not silent:
                    _log.exception('%s failed for pid %s' % (label, ppid))

        while True:
            loops -= 1
            time.sleep(1)
            remaining = _check_remaining(pidlist)
            _log.debug('nuke_ppp_devices(): remaining pids after %s: %s' % (label, remaining))
            if len(remaining) == 0:
                _log.debug('nuke_ppp_devices(): all devices killed (%s)' % label)
                return []
            else:
                if loops <= 0:
                    _log.warning('nuke_ppp_devices(): devices left after %s: %s' % (label, remaining))
                    return remaining

    # Step 1: links down
    @db.untransact()
    def _set_links_down():
        _log.debug('nuke_ppp_devices(): step 1 for devices [%s]: links down' % ','.join(devnames))
        for devname in devnames:
            try:
                _log.debug('nuke_ppp_devices(): ip link down for %s' % devname)
                run_command([constants.CMD_IP, 'link', 'set', devname, 'down'])
            except:
                if not silent:
                    _log.exception('setting ppp device down in nuke ppp device failed')

            try:
                _log.debug('nuke_ppp_devices(): tear down fw for %s' % devname)
                tear_down_fw(devname, silent=silent)
            except:
                if not silent:
                    _log.exception('tear down fw in nuke ppp device failed')
                    
            try:
                _log.debug('nuke_ppp_devices(): tear down qos for %s' % devname)
                tear_down_qos(devname, silent=silent)
            except:
                if not silent:
                    _log.exception('tear down qos in nuke ppp device failed')
    _set_links_down()
    
    # Step 2: retire PPP devices from RDF
    _log.debug('nuke_ppp_devices(): step 2 for devices [%s]: retiring' % devnames_str)
    devs = helpers.get_ppp_devices()
    retired = None
    try:
        retired = helpers.get_retired_ppp_devices()
    except:
        _log.exception('cannot get retired PPP device list, this happens after update')

    # figure out a list of devices to retire; note that we should not edit the
    # list while we are iterating it, because we will be skipping entries if we do
    to_retire = []

    for i, d in enumerate(devs):
        if d.hasS(ns.deviceName):
            if d.getS(ns.deviceName, rdf.String) in devnames:
                to_retire.append(d)
        else:
            _log.warning('nuke_ppp_device(): device %s in rdf does not have deviceName, retiring it' % d)
            to_retire.append(d)

    for t in to_retire:
        if not t.hasS(ns.stopTime):
            # set stopTime if not already set
            t.setS(ns.stopTime, rdf.Datetime, now)
        devs.discard(t)
        if retired is not None:
            retired.add(t)
        else:
            _log.warning('retiring device %s, but no retired devices list, ignoring' % t)

    # find pidlist
    original_kill_pidlist = []
    for t in to_retire:
        try:
            if t.hasS(ns.pppdPid):
                ppid = t.getS(ns.pppdPid, rdf.Integer)
                original_kill_pidlist.append(ppid)
        except:
            _log.warning('failed when finding pid for soft/hard kill')

    @db.untransact()
    def _do_soft_hard_kill():
        kill_pidlist = original_kill_pidlist

        # Step 3: soft kill + wait
        if kill_ppp_soft:
            if len(kill_pidlist) > 0:
                _log.debug('nuke_ppp_devices(): step 3 for devices [%s], pidlist %s: soft kill' % (devnames_str, kill_pidlist))

                # replace kill_pidlist with remaining devices
                kill_pidlist = _kill_and_wait('soft kill', kill_pidlist, False, kill_ppp_soft_wait)

        # Step 4: hard kill + wait
        if kill_ppp_hard:
            if len(kill_pidlist) > 0:
                _log.debug('nuke_ppp_devices(): step 4 for devices [%s], pidlist %s: hard kill' % (devnames_str, kill_pidlist))
                remaining = _kill_and_wait('hard kill', kill_pidlist, True, kill_ppp_hard_wait)

        success = False
        if len(_check_remaining(original_kill_pidlist)) == 0:
            success = True
        _log.info('nuke_ppp_devices(): done, devnames=[%s], success=%s' % (devnames_str, success))
        return success

    return _do_soft_hard_kill()

# --------------------------------------------------------------------------

class Restrictions:
    """Class to encapsulate license restrictions and forwarding information.

    This has been separated to a class because the information may grow later,
    making parameter passing cumbersome.
    """

    def __init__(self, restrict=None, forward=None, forward_http_port=None, forward_https_port=None, forward_reason=None, reason_string=None, drop_connection=False):
        """Constructor."""
        self.restrict = restrict
        self.forward = forward
        self.forward_http_port = forward_http_port
        self.forward_https_port = forward_https_port
        self.forward_reason = forward_reason
        self.reason_string = reason_string
        self.drop_connection = drop_connection

        if self.forward:
            if self.forward_http_port is None or self.forward_https_port is None:
                raise Exception('forwarding required but at least one port is None (%s, %s)' % (self.forward_http_port, self.forward_https_port))

# --------------------------------------------------------------------------
#
#  The main PPP scripts class
#

class PppScripts:
    _log = None

    @db.transact()
    def __init__(self, name=None, public_interface=None, private_interface=None, proxyarp_interface=None):
        """Constructor."""

        # start by getting all PPP parameters; this should never fail (no logging yet)
        self._get_params()

        # l2tpserver.pppscripts.ppp-ip-{preup,up,down} prefix can be used to control
        # logging of all devices (inherited)
        self._log = logger.get('l2tpserver.pppscripts.%s.%s_%s' % (name, self.ppp_interface, self.ppp_pppd_pid))
        self.public_interface = public_interface
        self.private_interface = private_interface
        self.proxyarp_interface = proxyarp_interface

        # enables some verbose internal debugging
        self.debug = False
        if self.debug:
            self._log.warning('ppp debugging enabled, remove from release build')

        # Also start time
        self.now = datetime.datetime.utcnow()

        # NB: user info no longer checked here because it is not much more exception prone
        
    def _get_user_information(self):
        """Gather user related information to self.

        This is now a bit complicated for a couple of reasons and hence isolated here.
        First, we have normal, site-to-site client and site-to-site server users.
        Second, we now have RADIUS authentication, so an RDF user node does not necessarily
        exist at all.

        For normal VPN connections and site-to-site connections terminated by us, the
        user information refers to the remote endpoint and is determined from normal
        PPP parameters.  For site-to-site client connections, the user information refers
        to the local user information (!) and user information is determined from the
        PPP 'ipparam' parameter, which is set by openl2tp to a string formatted as
        "client:<username>:<password>".

        Note that we may not always have user data even for locally authenticated users.
        For instance, ppp teardown might not have user data if user is already removed
        from config.  This doesn't currently work cleanly.  UI tries to avoid this by
        nuking first, then reconfiguring, and then nuking again, but this isn't airtight.
        (Also RADIUS authenticated users have no corresponding RDF node.)
        
        This function is supposed to ensure that all user information is consistent before
        returning.  So, for instance, for client mode connections we are certain that they
        are site-to-site connections present in RDF, and have the correct site-to-site role.
        """

        # eventual result values
        self.user = None
        self.username = None
        self.user_fixed_ip = None
        self.client_mode = None
        self.server_mode = None
        self.site_to_site = None

        try:
            # get user, username, and client_mode from ppp params
            if self.ppp_peername is not None:
                self._log.debug('peername found, apparently server mode connection')
                self.user = self._find_user(self.ppp_peername, clientmode=False)
                self.username = self.ppp_peername
                self.client_mode = False
            else:
                self._log.debug('peername not found, apparently client mode connection')
                if self.ppp_ipparam is not None:
                    t = self.ppp_ipparam.split(':')
                    self._log.debug('ipparam=%s, after split=%s' % (self.ppp_ipparam, t))

                    if len(t) != 3:
                        raise Exception('ipparam has invalid format')
                    if t[0] != 'client':
                        raise Exception('ipparam has invalid format (does not begin with "client")')
                    self.user = self._find_user(t[1], clientmode=True)
                    self.username = self.user.getS(ns.username, rdf.String)
                    self.client_mode = True
                else:
                    raise Exception('no peername or ipparam, cannot determine user')

            # server mode derived value
            self.server_mode = not self.client_mode

            # site-to-site?
            if self.user is None:
                # site-to-site connections must have an RDF node
                self.site_to_site = False

                # sanity
                if self.client_mode:
                    raise Exception('client mode but no rdf node')
            else:
                if self.user.hasS(ns.siteToSiteUser):
                    s2s = self.user.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
                    role = s2s.getS(ns.role)

                    self.site_to_site = True

                    if role.hasType(ns.Client):
                        if not self.client_mode:
                            raise Exception('site-to-site client but not client mode')
                    elif role.hasType(ns.Server):
                        if self.client_mode:
                            raise Exception('site-to-site server but client mode')
                    else:
                        raise Exception('site-to-site role unknown')
                else:
                    self.site_to_site = False
                    
            # fixed ip
            if (self.user is not None) and (self.user.hasS(ns.fixedIp)):
                self.user_fixed_ip = self.user.getS(ns.fixedIp, rdf.IPv4Address)
            else:
                self.user_fixed_ip = None

            # check that PPP environ is missing info only for site-to-site client
            if self.ppp_environ_missing_address_info:
                if self.site_to_site and self.client_mode:
                    pass
                else:
                    raise Exception('ppp environment missing (ippool/radius) address allocation info ' \
                                    'and we are not a site-to-site client, fatal')

            # final sanity
            for i in [self.username, self.client_mode, self.server_mode, self.site_to_site]:
                if i is None:
                    raise Exception('sanity check failed, some value is None')
                # NB: following may be None: self.user, self.user_fixed_ip
        except:
            self._log.exception('failed to determine user info, bailing out')
            raise

        self._log.info('ppp user info: user=%s, ' \
                       'username=%s, ' \
                       'user_fixed_ip=%s, ' \
                       'ippool_allocated=%s, ' \
                       'radius_allocated=%s, ' \
                       'server_allocated=%s, ' \
                       'client_mode=%s, ' \
                       'server_mode=%s, ' \
                       'site_to_site=%s' % (self.user,
                                            self.username,
                                            self.user_fixed_ip,
                                            self.ppp_ippool_allocated_address,
                                            self.ppp_radius_allocated_address,
                                            self.ppp_server_allocated_address,
                                            self.client_mode,
                                            self.server_mode,
                                            self.site_to_site))

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
        """Get PPP script parameters from the environment and command line.

        See man pppd(8) under heading SCRIPTS for description of available
        environment variables and command line arguments.  Note that all
        but the 'ipparam' parameter are available from the environment,
        while only a subset of parameters are available from the command
        line.  We prefer environment variables over command line variables
        (except for the 'ipparam' parameter).

        NB: This function should never log anything, we don't have a logger
        object yet.
        """

        # self.ppp_device = self._safe_getenv('DEVICE')      # = e.g. /dev/ttyp0 , not available when using openl2tp
        self.ppp_ifname = self._safe_getenv('IFNAME')        # = e.g. ppp0 or l2tp12345-12345 XXX: not used, useless with openl2tp
        self.ppp_iplocal = self._safe_getenv('IPLOCAL')
        self.ppp_ipremote = self._safe_getenv('IPREMOTE')
        self.ppp_peername = self._safe_getenv('PEERNAME')    # = username
        #self.ppp_speed = self._safe_getenv('SPEED')         # not available when using openl2tp
        self.ppp_pppd_pid = int(self._safe_getenv('PPPD_PID'))
        self.ppp_orig_uid = self._safe_getenv('ORIG_UID')
        self.ppp_logname = self._safe_getenv('PPPLOGNAME')
        self.ppp_connect_time = self._safe_getenv('CONNECT_TIME')
        self.ppp_bytes_sent = self._safe_getenv('BYTES_SENT')
        self.ppp_bytes_rcvd = self._safe_getenv('BYTES_RCVD')
        self.ppp_linkname = self._safe_getenv('LINKNAME')
        self.ppp_call_file = self._safe_getenv('CALL_FILE')
        self.ppp_dns1 = self._safe_getenv('DNS1')
        self.ppp_dns2 = self._safe_getenv('DNS2')

        # We require both IPPOOL_ALLOCATED_ADDRESS and RADIUS_ALLOCATED_ADDRESS
        # to be set by pppd; if they are not, pppd essentially requests to be
        # killed.  This is used, for instance, when ippool is exhausted.
        self.ppp_environ_missing_address_info = False
        if not (os.environ.has_key('IPPOOL_ALLOCATED_ADDRESS') and \
                os.environ.has_key('RADIUS_ALLOCATED_ADDRESS')):
            # These are not present for site-to-site client.  Mark them as missing;
            # _get_user_information() will check that if they are missing, we are a
            # site-to-site client for sure (if not, raises an Exception).
            self.ppp_environ_missing_address_info = True

        self.ppp_ippool_allocated_address = False
        ippool_addr = self._safe_getenv('IPPOOL_ALLOCATED_ADDRESS')
        if ippool_addr is not None and ippool_addr == 'TRUE':
            self.ppp_ippool_allocated_address = True
        
        self.ppp_radius_allocated_address = False
        radius_addr = self._safe_getenv('RADIUS_ALLOCATED_ADDRESS')
        if radius_addr is not None and radius_addr == 'TRUE':
            self.ppp_radius_allocated_address = True

        self.ppp_server_allocated_address = False
        if (not self.ppp_ippool_allocated_address) and (not self.ppp_radius_allocated_address):
            # XXX: we just assume this now, see #657
            self.ppp_server_allocated_address = True
            
        # mostly duplicates, prefer env if same information from both sources

        self.ppp_device = self._safe_getarg(1)
        #self.ppp_ifname = self._safe_getarg(2)   # this is empty when using openl2tp
        self.ppp_speed = self._safe_getarg(3)     # this is zero always with openl2tp, but we don't need it
        #self.ppp_iplocal = self._safe_getarg(4)  # duplicate
        #self.ppp_ipremote = self._safe_getarg(5) # duplicate
        self.ppp_ipparam = self._safe_getarg(6)

        # Note: real interface name is in ppp_device when using openl2tp and
        # in ppp_ifname when using l2tpd; this is for openl2tp.
        self.ppp_interface = self.ppp_device

    def _dump_params(self):
        """Dump PPP script parameters as a one-line string useful for logging."""

        return ('device=%s ifname=%s iplocal=%s ipremote=%s peername=%s ' +
                'speed=%s orig_uid=%s logname=%s connect_time=%s ' +
                'bytes_sent=%s bytes_rcvd=%s linkname=%s call_file=%s ' +
                'dns1=%s dns2=%s ipparam=%s (using interface: %s)') % \
               (self.ppp_device, self.ppp_ifname, self.ppp_iplocal, self.ppp_ipremote,
                self.ppp_peername, self.ppp_speed, self.ppp_orig_uid, self.ppp_logname,
                self.ppp_connect_time, self.ppp_bytes_sent, self.ppp_bytes_rcvd,
                self.ppp_linkname, self.ppp_call_file, self.ppp_dns1, self.ppp_dns2,
                self.ppp_ipparam, self.ppp_interface)

    @db.transact()
    # XXX: candidate for refactoring
    def _find_user(self, username, clientmode=False):
        users_cfg = helpers.get_config().getS(ns.usersConfig, rdf.Type(ns.UsersConfig))

        for u in users_cfg.getS(ns.users, rdf.Bag(rdf.Type(ns.User))):
            name = u.getS(ns.username, rdf.String)
            if clientmode:
                if not u.hasS(ns.siteToSiteUser):
                    continue

                siteuser = u.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
                if not siteuser.hasS(ns.role):
                    continue

                role = siteuser.getS(ns.role)
                if not role.hasType(ns.Client):
                    continue

            if name == username:
                return u

        return None

    @db.untransact()
    def _setup_device_fw(self, restricted, web_forward, http_fwd_addr, http_fwd_port, https_fwd_addr, https_fwd_port, spoof_prevention, is_site_to_site):
        """Setup device firewall rules for this specific PPP device.

        Assumes that tear_down_fw() has been called first.  The calling chains are configured
        in a way that if the device-specific chain matches no targets, the traffic is accepted.

        Firewall rule structure:
          * Forced forwarding comes first (but only applies to HTTP/HTTPS)
          * DNS and WINS are always allowed, unless (1) restriction is required, and (2) http/https forwarding is *not* required
          * Restricted blocking is done next
          * Finally, customization chains are jumped to from each chain
        """

        # allowed ports in restricted mode
        if restricted and not web_forward:
            allow_tcp_ports = [ ]
            allow_udp_ports = [ ]
        else:
            allow_tcp_ports = [ 53 ]          # dns=53, wins=137
            allow_udp_ports = [ 53, 137 ]

        # collect all parameters
        params = {}
        params['dev'] = self.ppp_interface
        params['peeraddress'] = self.ppp_ipremote
        params['ownaddress'] = self.ppp_iplocal
        
        # add customization chain commands to params dict (if enabled)
        add_custom_chains = False

        t = {'raw': [('prerouting', 'prert', True),
                     ('output', 'output', True)],
             'nat': [('prerouting', 'prert', True),
                     ('output', 'output', True),
                     ('postrouting', 'postrt', True)],
             'mangle': [('prerouting', 'prert', True),
                        ('input', 'input', True),
                        ('forward', 'forward', True),
                        ('output', 'output', True),
                        ('postrouting', 'postrt', True)],
             'filter': [('input', 'input', True),
                        ('forward', 'forward', True),
                        ('output', 'output', True)]}

        for i in ['raw', 'nat', 'mangle', 'filter']:
            for j in t[i]:
                ident = 'custom_%s_%s' % (i, j[0])
                if j[1] and add_custom_chains:
                    # e.g.: -A ppp_prert_l2tp12345-12345 -j raw_prerouting_ppp_cust
                    params[ident] = '-A ppp_%s_%s -j %s_%s_ppp_cust' % (j[1], params['dev'], i, j[0])
                else:
                    params[ident] = ''

        # check web forward
        w = ''
        if web_forward:
            # Own ppp address should be exempt so normal web UI can be used even when
            # web forwarding is on.  This also prevents forwarded connections from being
            # reforwarded.
            w += ('-A ppp_prert_%(dev)s ! -d %(ownaddress)s -p tcp --dport 80 -j DNAT --to-destination ' % params) + '%s:%s-%s\n' % (http_fwd_addr, http_fwd_port, http_fwd_port)
            w += ('-A ppp_prert_%(dev)s ! -d %(ownaddress)s -p tcp --dport 443 -j DNAT --to-destination ' % params) + '%s:%s-%s\n' % (https_fwd_addr, https_fwd_port, https_fwd_port)
        params['portforward_nat'] = w

        # check spoof prevention
        s = ''
        if spoof_prevention:
            s = '-A ppp_prert_%s -s ! %s -j DROP' % (params['dev'], params['peeraddress'])
        params['spoof_raw_prerouting'] = s

        # check restrictions
        r = ''
        if restricted:
            for i in allow_tcp_ports:
                r += ('-A ppp_forward_%(dev)s -p tcp --dport ' % params) + str(i) + ' -j ACCEPT\n'
            for i in allow_udp_ports:
                r += ('-A ppp_forward_%(dev)s -p udp --dport ' % params) + str(i) + ' -j ACCEPT\n'
            r += '-A ppp_forward_%(dev)s -j REJECT --reject-with icmp-port-unreachable\n' % params
        params['restricted_filter_forward'] = r

        r = ''
        if restricted:
            r += ('-A ppp_prert_%(dev)s -j MARK --set-mark ' % params) + ('%s' % constants.FWMARK_LICENSE_RESTRICTED) + '\n'
        params['license_restricted_marking'] = r
        
        # mark site-to-site packets with a separate fwmark for routing purposes; note
        # that this mark is applies for *both* incoming and outgoing packets, unlike
        # the normal FWMARK_PPP.
        s = ''
        if is_site_to_site:
            s += ('-A ppp_prert_%(dev)s -j MARK --set-mark ' % params) + ('%s' % constants.FWMARK_PPP_S2S) + '\n'
            s += ('-A ppp_postrt_%(dev)s -j MARK --set-mark ' % params) + ('%s' % constants.FWMARK_PPP_S2S) + '\n'
        params['site_to_site_marking'] = s
        
        # create iptables-restore script
        tables = textwrap.dedent("""\
        *raw
        :ppp_prert_%(dev)s -
        :ppp_output_%(dev)s -
        -A raw_prerouting_ppp -i %(dev)s -j ppp_prert_%(dev)s
        -A raw_output_ppp -o %(dev)s -j ppp_output_%(dev)s

        %(spoof_raw_prerouting)s
        %(custom_raw_prerouting)s
        %(custom_raw_output)s
        COMMIT
        
        *nat
        :ppp_prert_%(dev)s -
        :ppp_output_%(dev)s -
        :ppp_postrt_%(dev)s -
        -A nat_prerouting_ppp -i %(dev)s -j ppp_prert_%(dev)s
        -A nat_output_ppp -o %(dev)s -j ppp_output_%(dev)s
        -A nat_postrouting_ppp -o %(dev)s -j ppp_postrt_%(dev)s

        %(portforward_nat)s
        %(custom_nat_prerouting)s
        %(custom_nat_output)s
        %(custom_nat_postrouting)s
        COMMIT
        
        *mangle
        :ppp_prert_%(dev)s -
        :ppp_input_%(dev)s -
        :ppp_forward_%(dev)s -
        :ppp_output_%(dev)s -
        :ppp_postrt_%(dev)s -
        -A mangle_prerouting_ppp -i %(dev)s -j ppp_prert_%(dev)s
        -A mangle_input_ppp -i %(dev)s -j ppp_input_%(dev)s
        -A mangle_forward_ppp -i %(dev)s -j ppp_forward_%(dev)s
        -A mangle_forward_ppp -o %(dev)s -j ppp_forward_%(dev)s
        -A mangle_output_ppp -o %(dev)s -j ppp_output_%(dev)s
        -A mangle_postrouting_ppp -o %(dev)s -j ppp_postrt_%(dev)s

        %(license_restricted_marking)s
        %(site_to_site_marking)s
        %(custom_mangle_prerouting)s
        %(custom_mangle_input)s
        %(custom_mangle_forward)s
        %(custom_mangle_output)s
        %(custom_mangle_postrouting)s
        COMMIT

        *filter
        :ppp_input_%(dev)s -
        :ppp_forward_%(dev)s -
        :ppp_output_%(dev)s -
        -A filter_input_ppp -i %(dev)s -j ppp_input_%(dev)s
        -A filter_forward_ppp -i %(dev)s -j ppp_forward_%(dev)s
        -A filter_forward_ppp -o %(dev)s -j ppp_forward_%(dev)s
        -A filter_output_ppp -o %(dev)s -j ppp_output_%(dev)s

        %(custom_filter_input)s
        %(restricted_filter_forward)s
        -A ppp_forward_%(dev)s -i %(dev)s -j filter_forward_ppp_firewall
        %(custom_filter_forward)s
        %(custom_filter_output)s
        COMMIT
        """)
        tables = tables % params

        # debug log of individual lines; this can be removed if
        # logger pre-step for multiline stuff is written
        if self.debug:
            self._log.debug('--- iptables-restore ---')
            for linenum, line in enumerate(tables.split('\n')):
                t = line.strip()
                self._log.debug('%d: %s' % (linenum+1, t))

        iptables_lock = helpers.acquire_iptables_lock()
        # execution
        try:
            (retval, retout, reterr) = run_command([constants.CMD_IPTABLES_RESTORE, '-n'], stdin=tables.encode('ascii'), retval=runcommand.FAIL)
        except:
            helpers.release_iptables_lock(iptables_lock)
            raise

        helpers.release_iptables_lock(iptables_lock)

        self._log.debug('iptables-restore => %s\n%s\n%s' % (retval, retout, reterr))

    def _setup_qos(self):
        """Setup device specific QoS settings.

        Currently no per-ppp-device QoS (tc) configuration is in use.
        """

        pass

    def _find_matching_sitetosite_routes(self, route_seq, user):
        res = []

        for r in route_seq:
            gw = r.getS(ns.gateway)
            if not gw.hasType(ns.SiteToSiteRouter):
                continue

            s2s_user = gw.getS(ns.user, rdf.Type(ns.User))
            if s2s_user == user:
                res.append(r)

        return res

    def _setup_ppp_routing(self):
        """Setup routing for ppp device.

        This only adds a route to the client routing table. The routing
        in main routing table is automatic for ppp device.

        The client routing table entry for ppp device address is required
        so that packets from a site-to-site connection can be routed to
        remote client (ppp) IP.
        """

        address = datatypes.IPv4AddressSubnet.fromStrings(self.ppp_ipremote, '255.255.255.255')

        self._log.debug('adding ppp route: %s -> %s' % (address.toString(), self.ppp_interface))
        run_command([constants.CMD_IP, 'route', 'replace', address.toString(), 'table', constants.ROUTE_TABLE_CLIENT, 'dev', self.ppp_interface], retval=runcommand.FAIL)

    def _setup_sitetosite_routing(self, user):
        """Setup routing for site-to-site tunnel.

        Replace route if it already exists.
        """

        def _setup_routes(route_seq, tableid):
            for r in self._find_matching_sitetosite_routes(route_seq, user):
                self._log.debug('site-to-site: adding route %s, tableid %s' % (r, tableid))
                # this will remove existing route (if exists), and add a new one
                subnet = r.getS(ns.address, rdf.IPv4Subnet)
                devname = self.ppp_interface
                run_command([constants.CMD_IP, 'route', 'replace', subnet.toString(), 'table', tableid, 'dev', devname, 'metric', constants.ROUTE_NORMAL_METRIC], retval=runcommand.FAIL)

        # site-to-site tableid? maybe no
        cfg_net = helpers.get_config().getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        _setup_routes(cfg_net.getS(ns.gatewayRoutes, rdf.Seq(rdf.Type(ns.Route))), constants.ROUTE_TABLE_GATEWAY)
        _setup_routes(cfg_net.getS(ns.clientRoutes, rdf.Seq(rdf.Type(ns.Route))), constants.ROUTE_TABLE_CLIENT)

    def _tear_down_sitetosite_routing(self, user, silent=False):
        """Tear down routes.

        The default blackhole routes are with higher metric and remain
        in place ensuring that site-to-site traffic is not routed as
        plain text after teardown.
        """

        def _teardown_routes(route_seq, tableid):
            for r in self._find_matching_sitetosite_routes(route_seq, user):
                self._log.debug('site-to-site: deleting route %s, tableid %s' % (r, tableid))

                # this will remove existing route (if exists)
                subnet = r.getS(ns.address, rdf.IPv4Subnet)
                devname = self.ppp_interface
                try:
                    run_command([constants.CMD_IP, 'route', 'del', subnet.toString(), 'table', tableid, 'metric', constants.ROUTE_NORMAL_METRIC], retval=runcommand.FAIL)
                except:
                    # This may fail if the device already disappeared.
                    pass
                
        # site-to-site tableid? maybe no
        cfg_net = helpers.get_config().getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        _teardown_routes(cfg_net.getS(ns.gatewayRoutes, rdf.Seq(rdf.Type(ns.Route))), constants.ROUTE_TABLE_GATEWAY)
        _teardown_routes(cfg_net.getS(ns.clientRoutes, rdf.Seq(rdf.Type(ns.Route))), constants.ROUTE_TABLE_CLIENT)

    @db.transact()
    def _nuke_connections(self, filterfunc):
        """Nuke connections which match 'filterfunc' callback function.

        If 'filterfunc' returns True, nuke connections.
        """

        now = datetime.datetime.utcnow()
        
        devs = helpers.get_ppp_devices()
        tokill = []
        for d in devs:
            if filterfunc(d):
                tokill.append(d)

        devnames = []
        for d in tokill:
            try:
                self._log.info('nuking old connection with pid=%s, username=%s' % (d.getS(ns.pppdPid, rdf.Integer),
                                                                                   d.getS(ns.username, rdf.String)))
                devnames.append(d.getS(ns.deviceName, rdf.String))
            except:
                self._log.warning('failed to add connection to to-nuke list')

        nuke_ppp_devices(devnames,
                         silent=True,
                         kill_ppp_soft=True,
                         kill_ppp_soft_wait=15.0,
                         kill_ppp_hard=True,
                         kill_ppp_hard_wait=15.0)

        # XXX: Some possible considerations for future improvement
        #
        #  - We hope here that ppp ip-down will get executed and move the
        #    PPP device to retired.  If not, licensemanager.py will
        #    reconcile the discrepancy eventually and retire the device.
        #    We do set the 'stopTime' for the PPP device here though;
        #    retire will not re-set it if it is already set.
        #    [sva: this seems inaccurate to me, nuke_ppp_devices retires.]
        #
        #  - Remove status nodes here -- or does ip-down get executed?
        #    If not, we'll leave plenty of old state lying around :(
        #    [sva: we give some time for ip-down, but it's not guaranteed.]
        #
        #  - This works in practice, but logs that setting device down etc fails
        #    almost always.. does link set and/or kill return an unexpected retval?

    @db.transact()
    def _nuke_old_connections_with_this_ip(self):
        """Nuke old connections from this IP address.

        Used with fixed IP users.  Needs to clean up any existing, even live,
        connections for this IP address.
        """

        thisaddr = datatypes.IPv4Address.fromString(self.ppp_ipremote)
        self._log.info('nuking previous connections with ip %s' % thisaddr.toString())

        # nuke based on remote address which causes routing problems; ignores overlapping
        # local addresses which are normal e.g. for server-mode remote access connections
        # (all have same local ip)
        self._nuke_connections(lambda d: d.getS(ns.pppRemoteAddress, rdf.IPv4Address) == thisaddr)

    @db.transact()
    def _nuke_old_connections_with_this_user(self):
        """Nuke old connections from this username.

        Used with fixed IP users.  Needs to clean up any existing, even live,
        connections for this IP address.
        """

        thisname = self.username
        self._log.info('nuking previous connections with username %s' % thisname)
        
        self._nuke_connections(lambda d: d.getS(ns.username, rdf.String) == thisname)

    def _kill_parent_pppd(self):
        """Figure out parent pppd pid and kill it.

        We use this in panic situations to drop the PPP connection forcibly.
        """

        try:
            _kill_pppd(self.ppp_pppd_pid)
        except:
            self._log.warning('failed to deliver signal to parent pppd process, pid: %s' % str(self.ppp_pppd_pid))

    @db.transact()
    def _determine_psk_index_etc(self, sitetositeclient):
        """Determine 'PSK index' and some other fields.

        The PSK index indicates which PSK from IPsec PSK list was used in
        IKE negotiation; 0=first, 1=second, etc.  This information is fed
        into status so that UI can determine how many connections use an
        out-of-date PSK.
        """

        psk_index = None
        udp_encaps = None
        addr_ipv4 = None
        port = None
        spi_rx = None
        spi_tx = None

        try:
            self._log.debug('_determine_psk_index: sitetositeclient: %s' % sitetositeclient)

            m = _re_l2tp_devicename.match(self.ppp_interface)
            if m is None:
                raise Exception('cannot determine tunnelid from device name %s' % self.ppp_interface)
            tunnelid = m.group(1)
            self._log.debug('_determine_psk_index: tunnelid is %s' % tunnelid)
            
            ol = openl2tp.Openl2tpConfig()
            addr, port = ol.determine_tunnel_remote_address_and_port(tunnelid)
            addr_ipv4 = datatypes.IPv4Address.fromString(addr)
            self._log.debug('_determine_psk_index: address=%s, port=%s' % (addr, port))

            if sitetositeclient:
                port = 4500 # It's a kind of logic...
                self._log.debug('_determine_psk_index: forcing site-to-site client remote port to %d' % port)

            pc = pluto.PlutoConfig()
            spi_rx, spi_tx, udp_encaps = pc.determine_sainfo_from_address_and_port(addr, port)
            self._log.debug('_determine_psk_index: spi_rx=%s, spi_tx=%s, udp_encaps=%s' % (spi_rx, spi_tx, udp_encaps))
            if spi_rx is None:
                raise Exception('_determine_psk_index: cannot determine spi_rx')
            
            psk_index = pc.determine_psk_index_from_spi(spi_rx)
            self._log.debug('_determine_psk_index: psk_index=%s' % psk_index)
        except:
            self._log.exception('_determine_psk_index: cannot determine psk index')
            return None, None, None, None, None, None
        
        return psk_index, udp_encaps, addr_ipv4, port, spi_rx, spi_tx
    
    # XXX: this should be parameterized with keywords... too many parameters
    def _ippreup_update_rdfdb(self, now, restricted, web_forward, fwd_reason, spoof_prevention, sitetosite, sitetositeclient, psk_index, udp_encaps, remote_addr, remote_port, spi_rx, spi_tx):
        """Update RDF database status in ip-pre-up.

        We update restrictions, web forwarding setup, and other such stuff
        here already.  Final updates are done in ip-up.
        """

        # We're the only entity adding devices to the state,
        # so we don't need to worry about races here (unless two
        # ip-up scripts do stuff for the same device at the same
        # time).

        devs = helpers.get_ppp_devices()

        # Note: previous node for same device should already be deleted

        # create a new node
        node = rdf.Node.make(db.get_db().getModel(), rdf.Resource)   # random UUID
        node.addType(ns.PppDevice)

        # fill in information known at this point
        node.setS(ns.deviceActive, rdf.Boolean, True)
        node.setS(ns.pppdPid, rdf.Integer, int(self.ppp_pppd_pid))
        node.setS(ns.deviceName, rdf.String, self.ppp_interface)
        node.setS(ns.username, rdf.String, self.username)
        node.setS(ns.restrictedConnection, rdf.Boolean, restricted)
        node.setS(ns.webForwardedConnection, rdf.Boolean, web_forward)
        node.setS(ns.spoofPrevention, rdf.Boolean, spoof_prevention)

        if spi_rx is not None:
            node.setS(ns.spiRx, rdf.String, spi_rx)
        else:
            self._log.warning('defaulting to zero spi_rx - spi_rx is None')
            node.setS(ns.spiRx, rdf.String, '0x00000000')

        if spi_tx is not None:
            node.setS(ns.spiTx, rdf.String, spi_tx)
        else:
            self._log.warning('defaulting to zero spi_tx - spi_tx is None')
            node.setS(ns.spiTx, rdf.String, '0x00000000')

        # psk index
        if psk_index is not None:
            node.setS(ns.ipsecPskIndex, rdf.Integer, psk_index)
        else:
            self._log.warning('defaulting to zero psk index - psk_index is None')
            node.setS(ns.ipsecPskIndex, rdf.Integer, 0)

        # udp encaps
        if udp_encaps is not None:
            if udp_encaps:
                node.setS(ns.ipsecEncapsulationMode, rdf.Type(ns.EspOverUdp))
            else:
                node.setS(ns.ipsecEncapsulationMode, rdf.Type(ns.EspPlain))
        else:
            self._log.warning('defaulting to EspOverUdp encapsulation mode - mode is None')
            node.setS(ns.ipsecEncapsulationMode, rdf.Type(ns.EspOverUdp))

        # set connection type
        if not sitetosite:
            node.setS(ns.connectionType, rdf.Type(ns.NormalUser))
        else:
            if sitetositeclient:
                node.setS(ns.connectionType, rdf.Type(ns.SiteToSiteClient))
            else:
                node.setS(ns.connectionType, rdf.Type(ns.SiteToSiteServer))
      
        # web forwarding reason
        if web_forward:
            # XXX: separate reason for old psk
            if fwd_reason == _fwd_reason_ui:
                node.setS(ns.forwardingReason, rdf.Type(ns.UiRequest))
            elif fwd_reason == _fwd_reason_license_exceeded:
                node.setS(ns.forwardingReason, rdf.Type(ns.LicenseExceeded))
            elif fwd_reason == _fwd_reason_license_invalid:
                node.setS(ns.forwardingReason, rdf.Type(ns.LicenseInvalid))
            elif fwd_reason == _fwd_reason_license_prohibits:
                node.setS(ns.forwardingReason, rdf.Type(ns.LicenseProhibits))
            else:
                self._log.error('unknown forwarding reason: %s' % fwd_reason)
        
        # local vs. remote authentication (to deal with #708)
        node.setS(ns.locallyAuthenticated, rdf.Boolean, (self.user is not None))

        node.setS(ns.startTime, rdf.Datetime, now)
        node.setS(ns.rxBytesCounter, rdf.Integer, 0)
        node.setS(ns.txBytesCounter, rdf.Integer, 0)
        node.setS(ns.rxPacketsCounter, rdf.Integer, 0)
        node.setS(ns.txPacketsCounter, rdf.Integer, 0)
        node.setS(ns.rxLastChange, rdf.Datetime, now)
        node.setS(ns.txLastChange, rdf.Datetime, now)
        node.setS(ns.rxRateMaximum, rdf.Float, 0.0)  # bytes/second
        node.setS(ns.txRateMaximum, rdf.Float, 0.0)
        node.setS(ns.rxRateCurrent, rdf.Float, 0.0)
        node.setS(ns.txRateCurrent, rdf.Float, 0.0)
        node.setS(ns.pppLocalAddress, rdf.IPv4Address, self.ppp_iplocal)
        node.setS(ns.pppRemoteAddress, rdf.IPv4Address, self.ppp_ipremote)
        if remote_addr is not None:
            node.setS(ns.outerAddress, rdf.IPv4Address, remote_addr)
        else:
            self._log.warning('defaulting to zero remote address - remote_addr is None')
            node.setS(ns.outerAddress, rdf.IPv4Address, datatypes.IPv4Address.fromString('0.0.0.0'))

        if remote_port is not None:
            node.setS(ns.outerPort, rdf.Integer, remote_port)
        else:
            self._log.warning('defaulting to zero remote port - remote_port is None')
            node.setS(ns.outerPort, rdf.Integer, 0)

        node.setS(ns.comment, rdf.String, self._dump_params())

        # add finished node
        devs.add(node)
        
    def _ipup_update_rdfdb(self, now):
        """Update RDF database status in ip-up."""

        # XXX: update timestamp?
        # XXX: what else?
        pass

    def _ipdown_update_rdfdb(self, now, silent=False):
        """Update RDF database status in ip-down."""

        self._log.info('updating rdf db on ip-down: nuke ppp device') # XXX
        nuke_ppp_device(self.ppp_interface, silent=silent, kill_ppp=False)
        
    def _determine_restrictions(self, psk_index):
        """Helper to determine restrictions, forwarding port, etc."""

        user_cfg = helpers.get_config().getS(ns.usersConfig, rdf.Type(ns.UsersConfig))

        def _get_port(nsname):
            if user_cfg.hasS(nsname):
                return user_cfg.getS(nsname, rdf.Integer)
            return None

        lm = licensemanager.LicenseMonitor()
        
        # Ports (some may be None)
        http_forward_port_forced = _get_port(ns.httpForcedRedirectPort)
        https_forward_port_forced = _get_port(ns.httpsForcedRedirectPort)
        http_forward_port_license = _get_port(ns.httpLicenseRedirectPort)
        https_forward_port_license = _get_port(ns.httpsLicenseRedirectPort)
        http_forward_port_oldpsk = _get_port(ns.httpNonPrimaryPskRedirectPort)
        https_forward_port_oldpsk = _get_port(ns.httpsNonPrimaryPskRedirectPort)

        # Check if license has expired; if so, block connections.
        if not lm.check_license_validity():
            if self.site_to_site:
                return Restrictions(restrict=True, forward=False, reason_string='license invalid (site-to-site)')
            else:
                return Restrictions(restrict=True, forward=True, forward_http_port=http_forward_port_license, forward_https_port=https_forward_port_license, forward_reason=_fwd_reason_license_invalid, reason_string='license invalid')
           
        # Then UI force check (for site-to-sites we assume there is no forced redirect)
        # XXX: RADIUS users cannot have forced redirect now (#659)
        if (self.user is not None) and self.user.getS(ns.forceWebRedirect, rdf.Boolean):
            if self.site_to_site:
                self._log.warning('site-to-site user has forceWebRedirect')
            return Restrictions(restrict=True, forward=True, forward_http_port=http_forward_port_forced, forward_https_port=https_forward_port_forced, forward_reason=_fwd_reason_ui, reason_string='ui forced')

        # Non-primary PSK check
        # XXX: RADIUS users cannot have old psk redirect now (#659)
        if (psk_index is not None) and (psk_index > 0) and \
           (self.user is not None) and \
           self.user.hasS(ns.forceNonPrimaryPskWebRedirect) and \
           self.user.getS(ns.forceNonPrimaryPskWebRedirect, rdf.Boolean):
            if self.site_to_site:
                self._log.warning('site-to-site user has forcedNonPrimaryPskWebRedirect')
            # XXX: should have different reason for this
            return Restrictions(restrict=True, forward=True, forward_http_port=http_forward_port_oldpsk, forward_https_port=https_forward_port_oldpsk, forward_reason=_fwd_reason_ui, reason_string='ui forced, psk index')

        # Separate checks for site-to-site users
        if self.site_to_site:
            license_ok = False
            if self.client_mode:
                self._log.debug('site-to-site client')
                license_ok = lm.check_site_to_site_access()
            else:
                self._log.debug('site-to-site server')
                license_ok = lm.check_site_to_site_access()

            if license_ok:
                return Restrictions(restrict=False, forward=False, reason_string='site-to-site user allowed')
            else:
                # Site-to-site connection and license not OK.  Previously we allowed this but
                # made the connection blocked.  This is probably a bad idea in general, and
                # quite harmful now that site-to-site leeway has been removed.
                return Restrictions(restrict=True, forward=False, reason_string='site-to-site user rejected (license prohibits)', drop_connection=True)

        # Separate checks for non-site-to-site users
        if lm.check_normal_user_access():
            return Restrictions(restrict=False, forward=False, reason_string='normal user allowed')
        else:
            return Restrictions(restrict=True, forward=True, forward_http_port=http_forward_port_license, forward_https_port=https_forward_port_license, forward_reason=_fwd_reason_license_exceeded, reason_string='normal user rejected (license prohibits)')

    def _cleanup(self, silent=False):
        """Cleanup any ppp script related state we can.

        If silent=True, will attempt all cleanups and won't raise exceptions.
        If silent=False, failures cause exceptions and logging.
        """

        # Note: if this is called with silent=False, usually
        # silent=True will be called next.

        #
        #  XXX: nuke conntrack state referring to remote PPP IP address
        #  the conntrack tool does not select entries based on
        #  ip-address properly, so it cannot be used to nuke only one
        #  ppp ip
        #
        
        try:
            if self.proxyarp_interface is not None:
                # Disabled for now, see #730.
                if False:
                    self._log.debug('proxyarp teardown')
                    self._log.info('proxyarp down for peer %s, ppp_iface %s, iface %s' % (self.ppp_ipremote, self.ppp_interface, self.proxyarp_interface))
                    run_command(['/sbin/ip', 'neigh', 'delete', 'proxy', self.ppp_ipremote, 'dev', self.proxyarp_interface], retval=runcommand.FAIL)
        except:
            if not silent:
                self._log.exception('proxyarp teardown failed')
                raise
            else:
                self._log.debug('proxyarp teardown failed (silent)')
                
        # tear down site-to-site routing
        try:
            if self.site_to_site:
                self._log.debug('site-to-site teardown')
                self._tear_down_sitetosite_routing(self.user)
        except:
            if not silent:
                self._log.exception('site-to-site routing teardown failed')
                raise
            else:
                self._log.debug('site-to-site routing teardown failed (silent)')

        # tear down ppp device routing
        try:
            self._log.debug('ppp device routing teardown')
            tear_down_ppp_routing(self.ppp_interface, silent=silent)
        except:
            if not silent:
                self._log.exception('ppp routing teardown failed')
                raise
            else:
                self._log.debug('ppp routing teardown failed (silent)')

        # XXX: this is here for now; we should try to delete device
        # specific information, but if there is any bookkeeping we
        # leave behind, it may be different in cleanup and ip-down.
        #
        # This also runs nuke_ppp_device which will tear down firewall
        # and qos.
        try:
            self._ipdown_update_rdfdb(self.now, silent=silent)
        except:
            if not silent:
                self._log.exception('rdf update failed')
                raise
            else:
                self._log.debug('rdf update failed (silent)')

    def _ppp_address_checks_stage1(self):
        #
        #  PPP address checks are pretty complicated here.  We proceed in two
        #  stages.
        #
        #  In stage 1 we check whether we accept the PPP address assigned to
        #  the device.  If not, we drop the connection without harming other
        #  connections.  There are several reasons why we could end up in
        #  this situation without being able to prevent it earlier.  For instance,
        #  if this connection is a site-to-site client connection, the server may
        #  assign an address that we cannot accept due to a mismatch with our
        #  configuration.  We would ideally want to prevent this in IPCP but we
        #  don't have hooks there right now.  So, stage 1 checks whether we're
        #  allowing the connection to proceed; if not, no other connection is
        #  harmed in the process.
        #
        #  In stage 2 we nuke any existing connections that conflict with this
        #  connection.  We want to get this connection up so we'll just nuke
        #  any conflicting connections.  We can of course bail out at this stage
        #  too if necessary, but we'd prefer to detect any such conditions earlier
        #  to minimize the impact on other connections.
        #
        #  The checks are also complicated by the fact that normal VPN connections
        #  and site-to-site server mode connections are different compared to
        #  site-to-site client mode connections.  Site-to-site client mode
        #  connections have two 'unknown' addresses (local, assigned by server,
        #  and remote, also assigned by server) while other connections only have
        #  one 'unknown' address (remote peer address, dynamically assigned by us).
        #  The checks are therefore a bit different.
        #
        #  The basic complicating factors are:
        #    - pppd / ippool bugs; for instance, pppd may assign an address
        #      from some random network (10/8 presumably) if ippool is out
        #      of addresses
        #    - fixed addresses for locally configured users
        #    - Framed-IP-Address attributes for RADIUS authenticated users
        #    - site-to-site clients whose assigned address is determined by
        #      the site-to-site server; both local and remote PPP addresses
        #      are unknown beforehand

        # === Stage 1: are we happy with both local and remote PPP address? ===

        ppp_local = datatypes.IPv4Address.fromString(self.ppp_iplocal)
        ppp_remote = datatypes.IPv4Address.fromString(self.ppp_ipremote)
        ppp_cfg = helpers.get_config().getS(ns.pppConfig, rdf.Type(ns.PppConfig))
        ppp_range = ppp_cfg.getS(ns.pppRange, rdf.IPv4AddressRange)
        ppp_subnet = ppp_cfg.getS(ns.pppSubnet, rdf.IPv4Subnet)
        users_cfg = helpers.get_config().getS(ns.usersConfig, rdf.Type(ns.UsersConfig))
        users_list = users_cfg.getS(ns.users, rdf.Bag(rdf.Type(ns.User)))
        ppp_our_server_address = ppp_subnet.getLastUsableAddress()
        ppp_reserved_addresses = [ ppp_subnet.getFirstAddress(),         # network
                                   ppp_subnet.getLastAddress(),          # broadcast
                                   ppp_our_server_address ]              # our ppp server address

        if self.site_to_site and self.client_mode:
            # Site-to-site client mode connection
            #
            # PPP address (both local and remote) must:
            #   - not be in the configured PPP address range
            #   - not be a reserved ppp address
            #   - not be the same as any configured client fixed IP address
            #
            # However, if any other connection is currently using this address, it
            # will be nuked.  We could check for this situation, but the correct
            # way to proceed would depend on the type of the connection.  For instance,
            # normal user connections would be dropped but other site-to-site connections
            # would not be dropped.  In any case, no handling of this case is done here.
            #
            # An important note: we need to check both the local and the remote
            # PPP address here.  

            if not self.ppp_server_allocated_address:
                raise Exception('address check stage 1 error: ' \
                                'site-to-site client %s, addresses not server allocated, ' \
                                'seems like an internal error' % \
                                self.username)

            for addr, addrname in [ (ppp_local, 'local'), (ppp_remote, 'remote') ]:
                if ppp_range.inRange(addr):
                    self._set_s2s_error_status(set_address_check_failure=True)
                    raise Exception('address check stage 1 error: ' \
                                    'site-to-site client %s ppp %s address %s in ppp range %s' % \
                                    (self.username, addrname, addr.toString(), ppp_range.toString()))
                
                for u in users_list:
                    if u.hasS(ns.fixedIp):
                        if u.getS(ns.fixedIp, rdf.IPv4Address) == addr:
                            # XXX: could check for existence of ns.username
                            self._set_s2s_error_status(set_address_check_failure=True)
                            raise Exception('address check stage 1 error: ' \
                                            'site-to-site client %s ppp %s address %s ' \
                                            'same as fixed IP address of user %s' % \
                                            (self.username, addrname, addr.toString(), u.getS(ns.username, rdf.String)))
            
                for res_addr in ppp_reserved_addresses:
                    if addr == res_addr:
                        self._set_s2s_error_status(set_address_check_failure=True)
                        raise Exception('address check stage 1 error: ' \
                                        'site-to-site client %s ppp %s address %s ' \
                                        'matches a reserved ppp address %s (subnet %s, range %s)' % \
                                        (self.username, addrname, addr.toString(), res_addr.toString(), ppp_subnet.toString(), ppp_range.toString()))
        else:
            # Normal user or site-to-site server mode connection
            #
            # PPP address (remote) must:
            #   - either: be from the ppp range (sanity check for pppd/ippool bugs)
            #         or: be a fixed IP, in which case it must match the configured fixed IP
            #   - not be a reserved ppp address
            #
            # Note: site-to-site server mode connections cannot have fixed IP addresses
            # at the moment (no such option in web UI), but if they did, the code below
            # would still be correct.
            #
            # The range check tries to guard against undesired default addresses from
            # pppd which may occur because of a filled pool (see #554 for more details).
            # Another reason for such a situation would be from connections which occur
            # before runner restart (with newly written configuration; web UI does that
            # at the moment).

            # the local ppp address must always be our server mode address here
            if ppp_local != ppp_our_server_address:
                raise Exception('address check stage 1 error: ' \
                                'normal user or site-to-site server %s ppp local address %s ' \
                                'is not the expected local address %s' % \
                                (self.username, ppp_local.toString(), ppp_our_server_address))

            # We have to check RADIUS-authenticated and non-RADIUS authenticated
            # cases separately.  For RADIUS users self.user is None.  For fixed
            # IP addresses (either for local users or for RADIUS Framed-IP-Address)
            # self.ppp_ippool_allocated_address is False.
            #
            # self.user can also be None for local users if configuration is out of
            # sync (user has been removed from RDF).

            # Determine what checks to perform
            check_in_ppp_range = False
            check_not_in_ppp_range = False
            check_reserved_ppp_addresses = True
            if self.user is None:
                if self.ppp_ippool_allocated_address:
                    # (apparently) RADIUS user with dynamic address
                    check_in_ppp_range = True
                elif self.ppp_radius_allocated_address:
                    # (apparently) RADIUS user with Framed-IP-Address
                    check_not_in_ppp_range = True
                else:
                    raise Exception('address check stage 1 error: ' \
                                    'normal user or site-to-site server %s has no rdf node (apparently radius), ' \
                                    'but neither radius nor ippool allocated address' % \
                                    self.username)
            else:
                if self.ppp_ippool_allocated_address:
                    # Local user with dynamic address
                    if self.user_fixed_ip is not None:
                        raise Exception('address check stage 1 error: ' \
                                        'normal user or site-to-site server %s has ippool ' \
                                        'allocated address and also a fixed IP' % \
                                        self.username)
                    check_in_ppp_range = True
                else:
                    # Local user with fixed IP
                    if not self.ppp_radius_allocated_address:
                        # NB: local users are authenticated using RADIUS
                        raise Exception('address check stage 1 error: ' \
                                        'normal user or site-to-site server %s has rdf node, but ppp_radius_allocated_address is not set as expected' % \
                                        self.username)
                    if self.user_fixed_ip is None:
                        raise Exception('address check stage 1 error: ' \
                                        'normal user or site-to-site server %s does not have ippool ' \
                                            'allocated address but does not have a fixed IP either' % \
                                        self.username)
                    if ppp_remote != self.user_fixed_ip:
                        raise Exception('address check stage 1 error: ' \
                                        'normal user or site-to-site server %s ppp remote address %s ' \
                                        'should match configured fixed IP address %s' % \
                                        (self.username, ppp_remote.toString(), self.user_fixed_ip.toString()))
                    check_not_in_ppp_range = True
            # end: if self.user is None
            
            # Do the actual checks
            if check_in_ppp_range:
                if not ppp_range.inRange(ppp_remote):
                    raise Exception('address check stage 1 error: ' \
                                    'normal user or site-to-site server %s ppp remote address %s should ' \
                                    'be in ppp range %s, but is not' % \
                                    (self.username, ppp_remote.toString(), ppp_range.toString()))
            if check_not_in_ppp_range:
                if ppp_range.inRange(ppp_remote):
                    raise Exception('address check stage 1 error: ' \
                                    'normal user or site-to-site server %s ppp remote address %s should not ' \
                                    'be in ppp range %s, but is' % \
                                    (self.username, ppp_remote.toString(), ppp_range.toString()))
            if check_reserved_ppp_addresses:
                for res_addr in ppp_reserved_addresses:
                    if res_addr == ppp_remote:
                        raise Exception('address check stage 1 error: ' \
                                        'normal user or site-to-site server %s ppp remote address %s ' \
                                        'matches a reserved ppp address %s (subnet %s, range %s)' % \
                                        (self.username, ppp_remote.toString(), res_addr.toString(), ppp_subnet.toString(), ppp_range.toString()))

    def _ppp_address_checks_stage2(self):
        # === Stage 2: Nuke any conflicting connections ===

        # connections with same (remote) IP are always nuked
        nuke_old_sameip = True
        
        # connections with same username are nuked for fixed IP connections and site-to-site server connections
        nuke_old_sameuser = False
        if (self.user_fixed_ip is not None) or \
           (self.user is None and not self.ppp_ippool_allocated_address) or \
           (self.site_to_site and self.server_mode):
            # (1) local user with fixed IP, (2) RADIUS user with Framed-IP-Address, (3) site-to-site server
            nuke_old_sameuser = True
        
        self._log.debug('nuke_old_sameip=%s, nuke_old_sameuser=%s' % (nuke_old_sameip, nuke_old_sameuser))
        
        if nuke_old_sameip:
            self._log.debug('nuking connections with same IP address')
            try:
                self._nuke_old_connections_with_this_ip()
            except:
                self._log.exception('nuking old connections (same ip) failed')
                raise

        if nuke_old_sameuser:
            self._log.debug('nuking connections with same username')
            try:
                self._nuke_old_connections_with_this_user()
            except:
                self._log.exception('nuking old connections (same user) failed')
                raise

        # It is quite critical that we ensure that previous site-to-site PPP
        # connections involving this same site-to-site username are killed before
        # we proceed to set up routing.  If this were not the case, we could set up
        # routing only to have the routes overwritten (torn down) by a late ip-down
        # script.  Hence hard kills.  See #643.
        #
        # This is actually an interesting nuke: the network device already exists,
        # so we'll be running firewall teardown etc in the nuke function.  However,
        # typically the device does not exist in RDF, so we don't get any pids to
        # kill.  On the other hand, if there are RDF nodes for this device, the
        # pids for them are never our pppd pid, so we're ok.

        _log.debug('nuking previous devices with same name [sanity]')
        nuke_ppp_devices([self.ppp_interface],
                         silent=True,
                         kill_ppp_soft=False,
                         kill_ppp_soft_wait=15.0,
                         kill_ppp_hard=True,
                         kill_ppp_hard_wait=15.0)
        
    def _set_s2s_error_status(self, set_address_check_failure=None, set_license_restricted_failure=None):
        try:
            st_root = helpers.get_status()
            s2s_statuses = st_root.getS(ns.siteToSiteStatuses, rdf.Bag(rdf.Type(ns.SiteToSiteStatus)))
            for i in s2s_statuses:
                try:
                    if not i.hasS(ns.tunnelConfig):
                        continue
                    tun_cfg = i.getS(ns.tunnelConfig)

                    if not tun_cfg.hasS(ns.siteToSiteUser):
                        continue
                    if not tun_cfg.hasS(ns.username):
                        continue
                    username = tun_cfg.getS(ns.username, rdf.String)
                    if username != self.username:
                        continue

                    # apparent match found
                    if set_address_check_failure is not None:
                        _log.info('setting s2s addressCheckFailure to %s for user %s' % (set_address_check_failure, username))
                        i.setS(ns.addressCheckFailure, rdf.Boolean, set_address_check_failure)
                    if set_license_restricted_failure is not None:
                        _log.info('setting s2s licenseRestrictedFailure to %s for user %s' % (set_license_restricted_failure, username))
                        i.setS(ns.licenseRestrictedFailure, rdf.Boolean, set_license_restricted_failure)
                except:
                    self._log.exception('failed to process s2s tunnel')
                
        except:
            self._log.exception('failed to set s2s error flags')
                        
    def _ppp_ip_pre_up_raw(self):
        """Handles actual operations of ip-pre-up.

        If fails, wrapper will cleanup and kill parent pppd.
        """

        # figure out user information and put it into self
        self._get_user_information()

        # clear s2s error statuses
        self._set_s2s_error_status(set_address_check_failure=False, set_license_restricted_failure=False)

        # check that assigned ppp address is acceptable
        self._ppp_address_checks_stage1()

        # nuke any conflicting connections, devices, etc
        self._ppp_address_checks_stage2()

        # determine spoof_prevention / site-to-site type
        spoof_prevention = True
        if self.site_to_site:
            spoof_prevention = False
        self._log.debug('spoof_prevention=%s' % spoof_prevention)
            
        # determine IPsec PSK index
        psk_index, udp_encaps, remote_addr, remote_port, spi_rx, spi_tx = \
                   self._determine_psk_index_etc(self.site_to_site and self.client_mode)
        self._log.debug('psk index: %s, udp_encaps:%s, addr/port:%s:%s, spirx:%s, spitx:%s' % (psk_index, udp_encaps, remote_addr, remote_port, spi_rx, spi_tx))
        if psk_index is None:
            # NB: for client-mode connections no PSK brute forcing is needed and
            # we always get index zero for them from pluto.  Hence this warning
            # is appropriate for both client and server mode connections.
            self._log.warning('cannot determine psk index')
            self._log.warning('default values for psk index, UDP encapsulation mode, remote address/port and SPI:s are now used and they may cause some confusion')
        elif psk_index > 0:
            self._log.info('user %s is using a non-primary psk (index %s)' % (self.username, psk_index))

        # PSK determination may fail in some cases; see ticket #567.  To make the system work
        # acceptably in those situations too, we fill default values here for any missing ones
        if psk_index is None:
            psk_index = 0
        if udp_encaps is None:
            udp_encaps = True
        if remote_addr is None:
            remote_addr = datatypes.IPv4Address.fromString('0.0.0.0')
        if remote_port is None:
            remote_port = 0
        if spi_rx is None:
            spi_rx = '0x00000000'
        if spi_tx is None:
            spi_tx = '0x00000000'

        # setup proxy arp
        #
        # NB: We will also add a proxy ARP entry for site-to-site endpoint PPP
        # address, which is pretty useless.  But we don't care.
        #
        # NB: ip neigh add does not fail
        if self.proxyarp_interface != None:
            # Disabled for now, see #730.
            if False:
                self._log.debug('proxyarp config')
                try:
                    self._log.info('proxyarp up for peer %s, ppp_iface %s, iface %s' % (self.ppp_ipremote, self.ppp_interface, self.proxyarp_interface))
                    run_command(['/sbin/ip', 'neigh', 'add', 'proxy', self.ppp_ipremote, 'dev', self.proxyarp_interface], retval=runcommand.FAIL)
                except:
                    self._log.exception('proxyarp config failed')
                    raise

        # determine web forwarding & restriction
        self._log.debug('determining web forwarding & restriction')
        restrictions = self._determine_restrictions(psk_index)
        do_restricted = restrictions.restrict
        do_web_forward = restrictions.forward
        http_forward_port = restrictions.forward_http_port
        https_forward_port = restrictions.forward_https_port
        fwd_reason = restrictions.forward_reason
        reason_str = restrictions.reason_string
        drop_connection = restrictions.drop_connection
        
        # log forwarding & restriction
        if do_restricted:
            self._log.info('connection restricted for used %s because of: %s' % (self.username, reason_str))
        if do_web_forward:
            self._log.info('forwarding user %s to %d:%d because of: %s' % (self.username, http_forward_port, https_forward_port, reason_str))
        if not (do_restricted or do_web_forward):
            self._log.info('no restrictions for user %s' % self.username)

        # connection drop required by license?
        if drop_connection:
            # yes, *don't* add connection to connection history but flag
            # connection error into status tree
            self._log.info('connection drop required by license, dropping')
            self._set_s2s_error_status(set_license_restricted_failure=True)
            raise Exception('connection drop required by license for site-to-site connection')
            
        # setup firewall rules
        self._log.debug('firewall config')
        try:
            tear_down_fw(self.ppp_interface, silent=True)
            self._setup_device_fw(do_restricted,
                                  do_web_forward,
                                  self.ppp_iplocal,
                                  http_forward_port,
                                  self.ppp_iplocal,
                                  https_forward_port,
                                  spoof_prevention,
                                  self.site_to_site)
        except:
            self._log.exception('firewall config failed')
            raise

        # setup qos rules
        self._log.debug('qos config')
        try:
            tear_down_qos(self.ppp_interface, silent=True)
            self._setup_qos()
        except:
            self._log.exception('qos config failed')
            raise

        # update rdfdb
        try:
            self._ippreup_update_rdfdb(self.now,
                                       do_restricted,
                                       do_web_forward,
                                       fwd_reason,
                                       spoof_prevention,
                                       self.site_to_site,
                                       self.site_to_site and self.client_mode,
                                       psk_index,
                                       udp_encaps,
                                       remote_addr,
                                       remote_port,
                                       spi_rx,
                                       spi_tx)
        except:
            self._log.exception('rdf update failed')
            raise

    def _ppp_ip_up_raw(self):
        """Handles actual operations of ip-up.

        If fails, wrapper will cleanup and kill parent pppd.
        """

        # figure out user information and put it into self
        self._get_user_information()

        # setup routing (cannot be done in pre-up)
        self._log.debug('site-to-site routing check')
        if self.site_to_site:
            try:
                self._setup_sitetosite_routing(self.user)
            except:
                self._log.exception('site-to-site routing setup failed')
                raise

        self._log.debug('ppp routing setup')
        try:
            self._setup_ppp_routing()
        except:
            self._log.exception('ppp routing setup failed')
            raise

        def _setup_rp_filter(iface, rpfilter):
            ic = interface.InterfaceConfig()
            ic.set_rp_filter(iface, rpfilter)

        # remove rp_filter [interface must have an ip address here]
        self._log.debug('rp_filter config')
        _setup_rp_filter(self.ppp_interface, False)

        # update rdfdb
        try:
            self._ipup_update_rdfdb(self.now)
        except:
            self._log.exception('rdf update failed')
            raise
            
        self._log.info('done')

    def _ppp_ip_down_raw(self):
        """Handles actual operations of ip-down.

        If fails, wrapper will cleanup and kill parent pppd.
        """

        # Note: rdfdb is now updated by _cleanup!

        # figure out user information and put it into self
        self._get_user_information()

        self._cleanup(silent=False)

    @db.transact()
    def ppp_ip_pre_up(self):
        """Entry point for '/etc/ppp/ip-pre-up' script."""

        self._log.info(self._dump_params())
        self._log.info(os.environ)  # XXX: may be insecure, but do for now

        try:
            self._ppp_ip_pre_up_raw()
        except:
            self._log.exception('ppp-ip-pre-up failed, killing parent pppd')
            self._cleanup(silent=True)

            # XXX: this causes a long delay, use SIGKILL instead?
            self._kill_parent_pppd()

        self._log.info('done')

    @db.transact()
    def ppp_ip_up(self):
        """Entry point for '/etc/ppp/ip-up' script."""

        self._log.info(self._dump_params())
        self._log.info(os.environ)  # XXX: may be insecure, but do for now

        try:
            self._ppp_ip_up_raw()
        except:
            self._log.exception('ppp-ip-up failed, killing parent pppd')
            self._cleanup(silent=True)

            # XXX: this causes a long delay, use SIGKILL instead?
            self._kill_parent_pppd()

        self._log.info('done')

    @db.transact()
    def ppp_ip_down(self):
        """Entry point for '/etc/ppp/ip-down' script."""

        self._log.info(self._dump_params())
        self._log.info(os.environ)  # XXX: may be insecure, but do for now

        try:
            self._ppp_ip_down_raw()
        except:
            self._log.exception('ppp-ip-down failed, killing parent pppd')
            self._cleanup(silent=True)

            # XXX: this causes a long delay, use SIGKILL instead?
            self._kill_parent_pppd()
            
        self._log.info('done')

