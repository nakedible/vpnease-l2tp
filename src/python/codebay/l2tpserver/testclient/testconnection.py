"""Functionality to start, stop, and perform various tests on the connection."""

import time, datetime, re, random

from codebay.common import logger
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.common import helpers
from codebay.l2tpserver.testclient import locks

import codebay.l2tpserver.testclient.constants as testclientconst # unfortunate naming clash

_log = logger.get('l2tpserver.testclient.testconnection')
run_command = runcommand.run_command

_re_openl2tp_created_tunnel = re.compile(r'^.*?Created\stunnel\s+(\d+)\s*$')
_re_openl2tp_created_session = re.compile(r'^.*?Created\ssession\s+(\d+)/(\d+)\s*$')

_re_openl2tp_tunnel_details_header = re.compile(r'^Tunnel\s+(\d+),\s+from\s+(.*?)\s+to\s+([0-9\.]+).*?$')
_re_openl2tp_tunnel_details_udpports = re.compile(r'^\s+UDP\s+ports:\s+local\s+(\d+?),\s+peer\s+(\d+?)\s*$')


"""
TODO:
- wait for pluto SA
- wait for l2tp tunnel
- wait for l2tp session
- delete session on stop
"""

class TestConnection:
    def __init__(self, debug=False, index=None, srcip=None, dstip=None, router=None, psk=None, username=None, password=None, device=None, min_connect_time=60, max_connect_time=60*30, ping_dest=None, ping_batch=None, ping_size=None, ping_interval=None):
        """Constructor."""

        self.debug = debug
        self.index = index   # a number >= 0, unique for the (alive) TestConnection
        self.srcip = srcip
        self.ip_index = 0
        self.base_ip = self.srcip
        self.dstip = dstip
        self.router = router
        self.psk = psk
        self.username = username
        self.password = password
        self.ppp_local_address = None
        self.ppp_remote_address = None

        self.tunnel_id = None
        self.session_id = None

        # self.ppp_device = 'l2tp%d-%d' % (self.tunnel_id, self.session_id)
        self.ppp_device = None
        
        self.device = device
        self.creation_time = datetime.datetime.now()
        self.min_connect_time = min_connect_time
        self.max_connect_time = max_connect_time
        self.ping_dest = ping_dest
        self.ping_batch = ping_batch
        self.ping_size = ping_size
        self.ping_interval = ping_interval

    def next_ip(self):
        if self.ip_index >= testclientconst.POOL_SIZE:
            _log.info(self._fmt('ip wrapped'))
            self.srcip = self.base_ip
            self.ip_index = 0
        else:
            self.srcip = datatypes.IPv4Address.fromLong(datatypes.IPv4Address.fromString(self.base_ip).toLong() + long(self.ip_index)).toString()
            self.ip_index = self.ip_index + 1
            _log.info(self._fmt('base ip: %s, new ip: %s' % (self.srcip, self.base_ip)))

    def _fmt(self, str):
        """Internal log string formatter, adds creation time etc to log entry."""
        
        return '[%s:%s]: %s' % (self.base_ip, self.srcip, str)
    
    def _pluto_config(self, myip, router, gwip):
        """Configure and start pluto tunnel."""

        _log.debug(self._fmt('_pluto_config, whack params: ip=%s, router=%s' % (myip, router)))

        # Note: whack exit status is unreliable because it tries to
        # deliver pluto progress status (if received) failing to convert
        # some success progress statuses to 0.  There is not much more to do
        # than hope for the best..
        #
        # If pluto fails, ppp will eventually die and the TestConnection
        # will exit.  It would be nice to detect pluto failure, though.

        locks.whack_lock_acquire()

        # FIXME: for now use default port
        our_port = 1701

        try:
            tunnel_name = 'tunnel-%s' % myip
            ike_lifetime = 8*60*60
            ipsec_lifetime = 8*60*60
            keying_tries = 5   # FIXME: 0=persist, but we don't want that

            # --forceencaps is not necessary: gateway will force anyway
            [rv, ig, err] = run_command([constants.CMD_IPSEC, 'whack',
                                         '--name', tunnel_name,
                                         '--host', myip,
                                         '--nexthop', router,
                                         '--clientprotoport', '17/%s' % str(our_port),
                                         '--updown', constants.CMD_TRUE,
                                         '--to', '--host', gwip,
                                         '--clientprotoport', '17/1701',
                                         '--updown', constants.CMD_TRUE,
                                         '--psk',
                                         '--encrypt',
                                         '--ike=aes-128-sha1-160-modp1536',
                                         '--ikelifetime', str(ike_lifetime),
                                         '--ipseclifetime', str(ipsec_lifetime),
                                         '--keyingtries', str(keying_tries)])

            _log.debug(self._fmt('whack (tunnel) return value: %d, stderr: %s' % (rv, err)))

            # initiate sa in an asynchronous manner
            (rv, ig, err) = run_command([constants.CMD_IPSEC, 'whack', '--initiate',
                                         '--asynchronous',
                                         '--name', tunnel_name])
            _log.debug(self._fmt('whack (initiate) return value: %d, stderr: %s' % (rv, err)))
        except:
            _log.exception(self._fmt('_pluto_config failed'))

        locks.whack_lock_release()

    def _pluto_cleanup(self, myip):
        """Remove pluto tunnel.

        This also removes SAs and SPs (Pluto does that.
        """
        
        _log.debug(self._fmt('_pluto_cleanup'))

        locks.whack_lock_acquire()

        try:
            tunnel_name = 'tunnel-%s' % myip
            [rv, ig, err] = run_command([constants.CMD_IPSEC, 'whack',
                                         '--delete', '--name', tunnel_name])
            _log.debug(self._fmt('delete (tunnel) return value: %d, stderr: %s' % (rv, err)))
        except:
            _log.exception(self._fmt('_pluto_cleanup failed'))

        locks.whack_lock_release()

    def _openl2tp_config(self, myip, gwip, index=0):
        """Configure and start Openl2tp through l2tpconfig."""

        _log.debug(self._fmt('_openl2tp_config'))

        locks.l2tpconfig_lock_acquire()

        try:
            self._openl2tp_config_raw(myip, gwip, index)
        except:
            _log.exception(self._fmt('_openl2tp_config failed'))
            locks.l2tpconfig_lock_release()
            return


        _log.info(self._fmt('starting tunnel'))
        try:
            self._openl2tp_start_tunnel(myip, gwip, index)
        except:
            _log.exception('start tunnel failed')
            locks.l2tpconfig_lock_release()
            return

        # Wait for tunnel to come up (tunnel retry timeout is 20 seconds)
        _tunnel_check_re = re.compile('.+\s+%s.*ESTABLISHED.*' % str(self.tunnel_id))
        tunnel_wait_count = 0
        while True:
            [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG, 'tunnel', 'list'])
            found = False
            for l in stdout.split('\n'):
                m = _tunnel_check_re.match(l)
                if m is not None:
                    _log.info(self._fmt('l2tp tunnel found'))
                    found = True

            if found:
                break

            tunnel_wait_count = tunnel_wait_count + 1
            if tunnel_wait_count > 7:
                _log.error(self._fmt('waited too long for l2tp tunnel'))
                locks.l2tpconfig_lock_release()
                raise Exception('failed to setup tunnel')

            locks.l2tpconfig_lock_release()
            time.sleep(10)
            locks.l2tpconfig_lock_acquire()

        _log.info(self._fmt('created new tunnel (%s) ' % str(self.tunnel_id)))

        _log.info(self._fmt('starting session'))
        try:
            self._openl2tp_start_session(myip, gwip, index)
        except:
            _log.exception('start session failed')
            locks.l2tpconfig_lock_release()
            return

        # Wait for session to come up (session timeout is what?)
        _session_check_re = re.compile('\s+%s.*' % str(self.session_id))
        session_wait_count = 0
        while True:
            [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG, 'session', 'list', 'tunnel_id=%s' % self.tunnel_id])
            found = False
            for l in stdout.split('\n'):
                m = _session_check_re.match(l)
                if m is not None:
                    _log.info(self._fmt('l2tp session found'))
                    found = True

            if found:
                break

            session_wait_count = tunnel_wait_count + 1
            if session_wait_count > 5:
                _log.error(self._fmt('waited too long for l2tp sesion'))
                locks.l2tpconfig_lock_release()
                raise Exception('failed to setup session')

            locks.l2tpconfig_lock_release()
            time.sleep(5)
            locks.l2tpconfig_lock_acquire()

        _log.info(self._fmt('created new tunnel and session (%s/%s) ' % (str(self.tunnel_id), str(self.session_id))))

        locks.l2tpconfig_lock_release()

    def _openl2tp_config_raw(self, myip, gwip, index):
        """Actual config."""

        identifier = '%s-%s' % (myip, str(index))

        ppp_profile_name = 'ppp-prof-%s' % identifier
        tunnel_profile_name = 'tunnel-prof-%s' % identifier
        session_profile_name = 'session-prof-%s' % identifier
        peer_profile_name = 'peer-prof-%s' % identifier
        tunnel_name = 'tunnel-%s' % identifier
        session_name = 'session-%s' % identifier

        # FIXME: using now default port without openl2tp patch
        our_port = 1701
        peer_port = 1701

        # ppp profile
        # FIXME: default_route; local_ipaddr; dns_ipaddr_{pri,sec}, wins_ipaddr_{pri,sec}
        trace_flags = '0'
        if self.debug:
            trace_flags = '2047'

        config = 'ppp profile create profile_name=%s\n' % ppp_profile_name

        for i in [ ['default_route', 'no'],
                   ['multilink', 'no'],
                   ['idle_timeout', '0'],  # no limit
                   ['mtu', '1300'],
                   ['mru', '1300'],
                   ['lcp_echo_interval', '60'],
                   ['lcp_echo_failure_count', '5'],
                   ['max_connect_time', '0'],  # no limit
                   ['max_failure_count', '10'],
                   ['trace_flags', trace_flags] ]:
            config += 'ppp profile modify profile_name=%s %s=%s\n' % (ppp_profile_name, i[0], i[1])

        # Note: all auth options must be on one line

        # XXX: this is for original, unpatched openl2tpd: cannot tell
        # which authentications to require and which refuse with
        # separate options, the solution is to simple allow peer not
        # to authenticate and for the rest use pppd defaults
        # config += 'ppp profile modify profile_name=%s auth_none=yes\n' % ppp_profile_name

        # XXX: this is for new patched openl2tp

        # Note: all auth options must be on one line
        config += 'ppp profile modify profile_name=%s req_none=yes auth_pap=yes auth_chap=yes auth_mschapv1=no auth_mschapv2=no auth_eap=no req_pap=no req_chap=no req_mschapv1=no req_mschapv2=no req_eap=no\n' % ppp_profile_name

        # no encryption
        # config += 'ppp profile modify profile_name=%s mppe=no\n' % ppp_profile_name

        # Note: all compression options must be on one line
        # Request deflate or bsdcomp compression.
        # XXX: no compression
        # config += 'ppp profile modify profile_name=%s comp_mppc=no comp_accomp=yes comp_pcomp=no comp_bsdcomp=no comp_deflate=yes comp_predictor=no comp_vj=no comp_ccomp_vj=no comp_ask_deflate=yes comp_ask_bsdcomp=no\n' % ppp_profile_name
        config += 'ppp profile modify profile_name=%s comp_mppc=no comp_accomp=yes comp_pcomp=no comp_bsdcomp=no comp_deflate=no comp_predictor=no comp_vj=no comp_ccomp_vj=no comp_ask_deflate=no comp_ask_bsdcomp=no\n' % ppp_profile_name


        # tunnel profile
        config += 'tunnel profile create profile_name=%s\n' % tunnel_profile_name

        trace_flags = '0'
        if self.debug:
            trace_flags = '2047'


        for i in [ ['our_udp_port', str(our_port)],
                   ['peer_udp_port', str(peer_port)],
                   ['mtu', '1460'],
                   ['hello_timeout', '60'],
                   ['retry_timeout', '3'],
                   ['idle_timeout', '0'],
                   ['rx_window_size', '4'],
                   ['tx_window_size', '10'],
                   ['max_retries', '20'],
                   ['framing_caps', 'any'],
                   ['bearer_caps', 'any'],
                   ['trace_flags', trace_flags] ]:
            config += 'tunnel profile modify profile_name=%s %s=%s\n' % (tunnel_profile_name, i[0], i[1])

        # session profile
        config += 'session profile create profile_name=%s\n' % session_profile_name

        trace_flags = '0'
        if self.debug:
            trace_flags = '2047'

        for i in [ ['sequencing_required', 'no'],
                   ['use_sequence_numbers', 'no'],
                   ['trace_flags', trace_flags] ]:
            config += 'session profile modify profile_name=%s %s=%s\n' % (session_profile_name, i[0], i[1])

        # peer profile
        config += 'peer profile create profile_name=%s\n' % peer_profile_name


        # XXX: 'lac_lns', 'netmask'
        # 'peer_port' has no effect for some reason
        for i in [ ['peer_ipaddr', gwip],
                   ['peer_port', str(peer_port)],  # XXX: dup from above
                   ['ppp_profile_name', ppp_profile_name],
                   ['session_profile_name', session_profile_name],
                   ['tunnel_profile_name', tunnel_profile_name] ]:
            config += 'peer profile modify profile_name=%s %s=%s\n' % (peer_profile_name, i[0], i[1])

        config += '\nquit\n'

        # create profiles
        _log.debug(self._fmt('openl2tp config:\n%s' % config))
        helpers.write_file('/tmp/%s.config' % tunnel_profile_name, config)
        run_command([constants.CMD_OPENL2TPCONFIG], stdin=config, retval=runcommand.FAIL)


    def _openl2tp_start_tunnel(self, myip, gwip, index):

        identifier = '%s-%s' % (myip, str(index))

        ppp_profile_name = 'ppp-prof-%s' % identifier
        tunnel_profile_name = 'tunnel-prof-%s' % identifier
        session_profile_name = 'session-prof-%s' % identifier
        peer_profile_name = 'peer-prof-%s' % identifier
        tunnel_name = 'tunnel-%s' % identifier
        session_name = 'session-%s' % identifier

        # FIXME: using now default port without openl2tp patch
        our_port = 1701
        peer_port = 1701

        # ppp profile
        # FIXME: default_route; local_ipaddr; dns_ipaddr_{pri,sec}, wins_ipaddr_{pri,sec}
        trace_flags = '0'
        if self.debug:
            trace_flags = '2047'


        # create tunnel - this triggers openl2tp
        #
        # NOTE: 'interface_name' would make life easier, but is not currently
        # supported by Openl2tp.
        #
        # XXX: 'persist', 'interface_name'
        config = 'tunnel create tunnel_name=%s' % tunnel_name  # NB: all on one line here
        for i in [ ['src_ipaddr', myip],
                   ['our_udp_port', str(our_port)],   # XXX: dup from above
                   ['peer_udp_port', str(peer_port)], # XXX: dup from above
                   ['dest_ipaddr', gwip],
                   ['peer_profile_name', peer_profile_name],
                   ['profile_name', tunnel_profile_name],
                   ['session_profile_name', session_profile_name],
                   ['tunnel_name', tunnel_name],
###                   ['tunnel_id', str(self.tunnel_id)],
                   ['use_udp_checksums', 'yes'] ]:
            config += ' %s=%s' % (i[0], i[1])

        config += '\nquit\n'

        # activate tunnel
        _log.debug(self._fmt('openl2tp config for tunnel:\n%s' % config))
        helpers.write_file('/tmp/%s.config' % tunnel_name, config)
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=config, retval=runcommand.FAIL)
        tunnel_id = None

        for l in stderr.split('\n'):
            m = _re_openl2tp_created_tunnel.match(l)
            if m is not None:
                if tunnel_id is not None:
                    _log.warning(self._fmt('second tunnel id (%s), old one was %s; ignoring' % (m.group(1), str(tunnel_id))))
                else:
                    tunnel_id = int(m.group(1))

        if tunnel_id is None:
            _log.error(self._fmt('tunnel out: %d, %s, %s' % (rv, stdout, stderr)))
            raise Exception(self._fmt('could not figure tunnel id'))

        _log.info(self._fmt('figured out tunnel id %s' % int(tunnel_id)))

        self.tunnel_id = tunnel_id

    def _openl2tp_start_session(self, myip, gwip, index):
        """Create session."""

        identifier = '%s-%s' % (myip, str(index))

        ppp_profile_name = 'ppp-prof-%s' % identifier
        tunnel_profile_name = 'tunnel-prof-%s' % identifier
        session_profile_name = 'session-prof-%s' % identifier
        peer_profile_name = 'peer-prof-%s' % identifier
        tunnel_name = 'tunnel-%s' % identifier
        session_name = 'session-%s' % identifier

        # FIXME: using now default port without openl2tp patch
        our_port = 1701
        peer_port = 1701

        # ppp profile
        # FIXME: default_route; local_ipaddr; dns_ipaddr_{pri,sec}, wins_ipaddr_{pri,sec}
        trace_flags = '0'
        if self.debug:
            trace_flags = '2047'


        config = 'session create session_name=%s' % session_name
        for i in [ ['tunnel_name', tunnel_name],
                   ['tunnel_id', str(self.tunnel_id)],
###                   ['session_id', str(self.session_id)],
                   ['profile_name', session_profile_name],
                   ['ppp_profile_name', ppp_profile_name],
                   ['user_name', self.username],
                   ['user_password', self.password] ]:
            config += ' %s=%s' % (i[0], i[1])

        config += '\nquit\n'

        # activate session
        _log.debug(self._fmt('openl2tp config for session:\n%s' % config))
        helpers.write_file('/tmp/%s.config' % session_name, config)
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=config, retval=runcommand.FAIL)

        session_id = None
        tunnel_id = self.tunnel_id

        for l in stderr.split('\n'):
            m = _re_openl2tp_created_session.match(l)
            if m is not None:
                if session_id is not None:
                    _log.warning('second session id (%s), old one was %s; ignoring' % (m.group(2), str(session_id)))
                else:
                    tun = int(m.group(1))
                    if tun != tunnel_id:
                        _log.warning('session id differs from earlier (earlier %s, found %s), ignoring' % (str(tunnel_id), str(tun)))
                    else:
                        session_id = int(m.group(2))

        if session_id is None:
            raise Exception(self._fmt('could not figure session id'))
        _log.info(self._fmt('figured out session id %s' % str(session_id)))

        self.session_id = session_id

                       
    def _openl2tp_cleanup(self, myip, gwip, wait=True):
        """Cleanup Openl2tp state."""

        locks.l2tpconfig_lock_acquire()
        
        try:
            self._openl2tp_cleanup_raw(myip, gwip, wait)
        except:
            _log.exception(self._fmt('_openl2tp_cleanup failed'))

        locks.l2tpconfig_lock_release()

    def _openl2tp_cleanup_raw(self, myip, gwip, wait):
        """Actual cleanup."""

        if self.tunnel_id is None or self.session_id is None:
            _log.info(self._fmt('tunnel or session id missing, not doing openl2tp cleanup'))
            return

        ppp_profile_name = 'ppp-prof-%s' % myip
        tunnel_profile_name = 'tunnel-prof-%s' % myip
        session_profile_name = 'session-prof-%s' % myip
        peer_profile_name = 'peer-prof-%s' % myip
        tunnel_name = 'tunnel-%s' % myip
        session_name = 'session-%s' % myip

        _tunnel_deleted_re = re.compile('.*Tunnel not found.*')

        _session_deleted_re = re.compile('.*Session not found.*')

        # Delete session and wait for removal
        run_command([constants.CMD_OPENL2TPCONFIG, 'session', 'delete', 'tunnel_id=%s' % str(self.tunnel_id), 'session_id=%s' % str(self.session_id)]) # ignore errors
        while True:
            [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG, 'session', 'show', 'tunnel_id=%s' % str(self.tunnel_id), 'session_id=%s' % str(self.session_id)]) # ignore errors
            m = _session_deleted_re.match(stderr)
            if m is not None:
                _log.info(self._fmt('session no longer exists, stop complete: %s' % stderr))
                break

            m = _tunnel_deleted_re.match(stderr)
            if m is not None:
                _log.info(self._fmt('tunnel no longer exists, stop complete: %s' % stderr))
                break

            if not wait:
                _log.warning(self._fmt('session %s (in tunnel %s) still exists, ignoring' % (str(self.session_id, str(self.tunnel_id)))))
                break

            _log.info(self._fmt('session %s (in tunnel %s) still exists, waiting' % (str(self.session_id), str(self.tunnel_id))))
            locks.l2tpconfig_lock_release()
            time.sleep(10)
            locks.l2tpconfig_lock_acquire()

        # Delete our tunnel and wait that it is removed
        run_command([constants.CMD_OPENL2TPCONFIG, 'tunnel', 'delete', 'tunnel_id=%s' % str(self.tunnel_id)]) # ignore errors
        while True:
            [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG, 'tunnel', 'show', 'tunnel_id=%s' % str(self.tunnel_id)]) # ignore errors
            m = _tunnel_deleted_re.match(stderr)
            if m is not None:
                _log.info(self._fmt('tunnel no longer exists, stop complete: %s' % stderr))
                break

            if not wait:
                _log.warning(self._fmt('tunnel %s still exists, ignoring' % str(self.tunnel_id)))
                break

            _log.info(self._fmt('tunnel %s still exists, waiting' % str(self.tunnel_id)))
            locks.l2tpconfig_lock_release()
            time.sleep(10)
            locks.l2tpconfig_lock_acquire()

        # delete existing profiles just to be sure
        for i in [ 'ppp profile delete profile_name=%s' % ppp_profile_name,
                   'tunnel profile delete profile_name=%s' % tunnel_profile_name,
                   'session profile delete profile_name=%s' % session_profile_name,
                   'peer profile delete profile_name=%s' % peer_profile_name ]:
            cmd = '%s\nquit\n' % i
            run_command([constants.CMD_OPENL2TPCONFIG], stdin=cmd) # ignore errors

        # FIXME: nuke pppd devices with our l2tp interface name...
        # FIXME: at start of connection, nuke own ppp and ppp device ... look at ps awxuf .. look for ppp device? (pppop2tp_ifname)

    def _check_device(self, devname):
        """Get local and remote addresses of a specific PPP device (or None, None if not found)."""
        
        _re = re.compile('^.*?\s+inet\s+([0-9\.]+).*?\s+peer\s+([0-9\.]+).*?$')

        # FIXME: there is no try wrapping here, which should be ok?
        (rv, stdout, stderr) = run_command([constants.CMD_IP, 'addr', 'show', devname], nologruntime=True)
        for l in stdout.split('\n'):
            m = _re.match(l)
            if m is not None:
                return m.group(1), m.group(2)
        return None, None

    def _wait_and_scan_device(self, max_time=60.0):
        """Wait for l2tp ppp device to come up and extract relevant data."""

        # FIXME: this is not the cleanest way: we add system load by running commands
        # frequently.  However, this would allow working without "central coordination".
        #
        # FIXME: polling also distorts setup time statistics; we try to be slightly
        # clever by backing off and thus getting a bit less distortion.

        start = time.time()
        devname = self.ppp_device
        
        local, remote = None, None
        sleep_current = 2.0
        sleep_backoff_coeff = 1.1
        sleep_backoff_max = 10.0
        while True:
            local, remote = self._check_device(self.ppp_device)

            if (local is not None and remote is not None):
                break

            elapsed = time.time() - start
            if elapsed > float(max_time):
                raise Exception('_wait_and_scan_device: waited too long (%f seconds) for device: %s' % (elapsed, devname))

            sleep_now = sleep_current
            sleep_current *= sleep_backoff_coeff
            if sleep_current > sleep_backoff_max:
                sleep_current = sleep_backoff_max
            _log.debug(self._fmt('sleeping %s seconds' % sleep_now))
            time.sleep(sleep_now)

        return local, remote

    def start_connection(self, keep_ip=False, wait_cleanup=True, index=None):
        """Start connection.

        Assumes that _configure_daemons() has already been called.
        Blocks until connection has been started.
        """

        if keep_ip:
            _log.info(self._fmt('keeping current ip'))
        else:
            self.next_ip()

        _log.info(self._fmt('cleaning up old state'))
        self._pluto_cleanup(self.srcip)
        self._openl2tp_cleanup(self.srcip, self.dstip, wait=wait_cleanup)
    
        _log.info(self._fmt('configuring and triggering daemons'))
        self._pluto_config(self.srcip, self.router, self.dstip)
        time.sleep(3)
        self._openl2tp_config(self.srcip, self.dstip, index=index)

        if self.tunnel_id is None or self.session_id is None:
            raise Exception('failed to config l2tp, stopping')

        self.ppp_device = 'l2tp%d-%d' % (self.tunnel_id, self.session_id)

        _log.info(self._fmt('waiting for ppp device'))
        local, remote = self._wait_and_scan_device(max_time=60.0)  # FIXME
        self.ppp_local_address = local
        self.ppp_remote_address = remote

        _log.info(self._fmt('got ppp device address: %s/%s' % (self.ppp_local_address, self.ppp_remote_address)))
        _log.info(self._fmt('start complete, ppp device: %s' % self.ppp_device))
        
    def stop_connection(self):
        """Stop connection."""

        _log.info(self._fmt('stopping daemons'))
        self._pluto_cleanup(self.srcip)
        self._openl2tp_cleanup(self.srcip, self.dstip)

    def stop_ppp(self, hard=False):
        """Stop pppd."""

        _log.info(self._fmt('stopping ppp, device: %s' % self.ppp_device))

        if self.ppp_device is None:
            _log.info(self._fmt('no device set, not killing any pppd'))
            return

        # Find out ppp pid
        [rv, out, err] = run_command(['ps', 'axuwwww'])
        if rv != 0 or out is None:
            _log.error('cannot get process list, no pppd killed')
            return

        found = False
        ppp_re = re.compile('root\s+(\d+)\s+.+\s+pppol2tp_ifname\s+%s' % self.ppp_device)
        for l in out.split('\n'):
            m = ppp_re.match(l)
            if m is not None:
                if hard:
                    run_command(['/bin/kill', '-KILL', str(int(m.groups()[0].strip()))])
                else:
                    run_command(['/bin/kill', '-HUP', str(int(m.groups()[0].strip()))])
                found = True
                break

        if not found:
            _log.error('no pppd pid found, none killed')
            return

        # Wait for device to disappear
        while True:
            local, remote = self._check_device(self.ppp_device)
            if local is None or remote is None:
                return
            time.sleep(10)

        self.ppp_device = None

    def run_random_connection_test(self):
        """Run random connection/disconnection test."""

        random.seed()
        start_time = None
        timeout = None

        while True:
            now = datetime.datetime.utcnow()
            if start_time is None or timeout is None or now - start_time > timeout:

                _log.info(self._fmt('timeout expired, restarting connection'))

                while True:
                    self.stop_ppp()
                    try:
                        self.start_connection()
                        break
                    except:
                        _log.exception(self._fmt('starting connection failed, sleeping 5 minutes'))
                        time.sleep(5*60)

                start_time = datetime.datetime.utcnow()

                secs = random.randint(self.min_connect_time, self.max_connect_time)
                timeout = datetime.timedelta(0, secs, 0)
                _log.info(self._fmt('setting timeout: %s' % secs))

            try:
                rv = 0; out = ''; err = ''
                [rv, out, err] = self._run_one_ping()
                if rv != 0:
                    raise Exception('return value check failed')
            except:
                _log.error(self._fmt('ping failed: %s, %s, %s' % (str(rv), str(out), str(err))))

            local, remote = self._check_device(self.ppp_device)
            _log.debug(self._fmt('device addresses: %s/%s' % (local, remote)))
            if local is None or remote is None:
                _log.info(self._fmt('device %s no longer exists or no longer has an address, restarting in 30 seconds' % self.ppp_device))
                time.sleep(30)
                start_time = None

    def run_single_reconnect_test(self, daemon_restart=None):
        """Run single client reconnect test."""

        _log.info(self._fmt('running single client reconnection test'))

        if daemon_restart is None:
            raise Exception('requires daemon restart helper')

        index = 0

        while True:
            _log.info(self._fmt('timeout expired, restarting connection'))

            while True:
                self.stop_ppp(hard=True)
                # daemon_restart()
                try:
                    index += 1
                    self.start_connection(keep_ip=True, wait_cleanup=False, index=index)
                    break
                except:
                    _log.exception(self._fmt('starting connection failed, sleeping 15 seconds'))
                    time.sleep(15)

            start_time = datetime.datetime.utcnow()

            secs = random.randint(self.min_connect_time, self.max_connect_time)
            timeout = datetime.timedelta(0, secs, 0)
            _log.info(self._fmt('setting timeout: %s' % secs))
            time.sleep(secs)

    def run_ping_test(self):
        """Run ping test to selected IP address for a period of time.

        Checks that device exists after every 10 pings.  If not, exits."""

        _log.info(self._fmt('running ping test %s -> %s, interval %d, size %d, batch %d' % (self.ppp_device, self.ping_dest, self.ping_interval, self.ping_size, self.ping_batch)))

        while True:
            self._run_one_ping()
            local, remote = self._check_device(self.ppp_device)
            _log.debug(self._fmt('device addresses: %s/%s' % (local, remote)))
            if local is None or remote is None:
                _log.info(self._fmt('device %s no longer exists or no longer has an address, exiting' % self.ppp_device))
                return

    def _run_one_ping(self):
        return run_command(['/bin/ping', '-i', str(self.ping_interval), '-s', str(self.ping_size), '-c', str(self.ping_batch), '-I', self.ppp_device, '-q', str(self.ping_dest)], nologruntime=True)
