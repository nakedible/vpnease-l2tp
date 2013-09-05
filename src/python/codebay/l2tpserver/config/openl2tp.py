"""OpenL2tp daemon configuration wrapper."""
__docformat__ = 'epytext en'

import re, textwrap

from codebay.common import rdf
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon
from codebay.l2tpserver import db

ns = rdfconfig.ns
run_command = runcommand.run_command

# Note: svc_unregister() is not called in openl2tpd start (l2tp_api.c),
# but pmap_unset() is used instead. It seems to work better anyways.

# Debug mask:
# PROTOCOL    1             L2TP control protocol messages
# FSM         2             State Machine events and state changes
# API         4             Management interface
# AVP         8             L2TP message attributes
# AVP_HIDE    16            AVP hiding mechanism
# AVP_DATA    32            AVP contents
# FUNC        64            Low level operations
# XPRT        128           Transport
# DATA        256           Protocol data
# SYSTEM      512           Internal system functions
# PPP         1024          PPP operations

_re_openl2tp_created_tunnel = re.compile(r'^.*?Created\stunnel\s+(\d+)\s*$')
_re_openl2tp_created_session = re.compile(r'^.*?Created\ssession\s+(\d+)/(\d+)\s*$')

_re_openl2tp_tunnel_details_header = re.compile(r'^Tunnel\s+(\d+),\s+from\s+(.*?)\s+to\s+([0-9\.]+).*?$')
_re_openl2tp_tunnel_details_udpports = re.compile(r'^\s+UDP\s+ports:\s+local\s+(\d+?),\s+peer\s+(\d+?)\s*$')


def get_server_ppp_address():
    """Get server (local) endpoint PPP address.

    This address is constant for all client connections when runner
    is active.  This helper is used by at least web UI for its
    redirection logic.

    Calling this function only makes sense when runner is active,
    as the configuration is otherwise not guaranteed to be correct.
    """

    cfg = helpers.get_config()
    ppp_cfg = cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))
    ppp_subnet = ppp_cfg.getS(ns.pppSubnet, rdf.IPv4Subnet)
    if ppp_subnet.getCidr() > 30:
        raise Exception('PPP subnet does not contain enough usable addresses')
    local_ip = ppp_subnet.getLastUsableAddress()
    return local_ip


class Openl2tpConfig(daemon.DaemonConfig):
    name = 'openl2tp'
    command = constants.CMD_OPENL2TP
    pidfile = constants.OPENL2TP_PIDFILE
    cleanup_files = []
    ip_address = None

    def get_args(self):
        return ['-u', '1701', '-a', self.ip_address]

    def create_config(self, cfg, res_info):
        """Create OpenL2tp configuration file as string."""

        # This is for get_args() to later pick up
        self.ip_address = res_info.public_interface.address.getAddress().toString()

        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        ppp_cfg = cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))
        ppp_auth = ppp_cfg.getS(ns.pppAuthentication, rdf.Type(ns.PppAuthentication))
        ppp_comp = ppp_cfg.getS(ns.pppCompression, rdf.Type(ns.PppCompression))
        l2tp_cfg = cfg.getS(ns.l2tpConfig, rdf.Type(ns.L2tpConfig))

        # XXX:  (do we need a patch for these?)
        # - noipx, crtscts, lock: are not used by openl2tp

        # Note:
        # - noipdefault, nodetach, local: always passed to pppd by openl2tp


        # Note: The receive port is not changeable and no point in
        # setting the local port because of the one-udp-port -patch.

        # Note: could set the openl2tp local sending port which would
        # disable the ephemeral port use, but this is not required while
        # we use the one-socket patch.

        self.debug_on = helpers.get_debug(cfg)

        # XXX: it seems like openl2tp has *ppp* profile trace flags
        # all enabled by default and others (tunnel, session, system) not..
        # there could be other debug flags, too, which would affect f.ex
        # openl2tp and pluto

        ppp_subnet = ppp_cfg.getS(ns.pppSubnet, rdf.IPv4Subnet)
        if ppp_subnet.getCidr() > 30:
            raise Exception('PPP subnet does not contain enough usable addresses')
        local_ip = ppp_subnet.getLastUsableAddress()

        # Note: hostname is not settable, but openl2tp derives it from
        # system hostname.

        # Note: vendor_name is not settable (and not used for anything more
        # than testing code) in openl2tp

        # Note: tunnelrws option does not exist in openl2tp
        # but could set the tx/rx window sizes

        # Note: not settable through openl2tp.
        # this has effect only when connect or pty options are used
        # in pppd config and thus is not required here.
        # connect_delay = '5000'

        # Note: openl2tp always uses lenght bit, so "length bit = yes"
        # or similar is not required in config.

        # PPP profile
        params = {}
        params['prefix'] = 'ppp profile modify profile_name=default'

        params['idle_timeout'] = '0'
        if ppp_cfg.hasS(ns.pppIdleTimeout):
            # short timeouts (less than 10 seconds, say) are not sane, but we
            # assume the user interface checks for sanity
            params['idle_timeout'] = str(ppp_cfg.getS(ns.pppIdleTimeout, rdf.Timedelta).seconds)  # truncate
            self._log.warning('idle timeout specified, not robust with many clients')
            
        params['mtu'] = str(ppp_cfg.getS(ns.pppMtu, rdf.Integer))
        params['mru'] = params['mtu']

        params['local_ipaddr'] = local_ip.toString()


        # XXX: if no echo failure specified, then the tunnels may never die.
        # - tunnels have hello_interval but it only controls of the
        #   frequency of the sent HELLO messages
        # - tunnels have idle timeout, but it has meaning only when all the
        #   sessions for tunnel have died out
        # - sessions themselves do not die unless pppd terminates because
        #   they have no timeout..

        # Note: be careful with PPP options -> delete or empty config files!
        # - some options in the /etc/ppp/options file have priority over
        #   command-line options
        # - openl2tp options are always command-line options
        # - this may lead to strange behaviour if there are old config
        #   files still hanging around..

        params['lcp_echo_interval'] = '0'
        params['lcp_echo_failure'] = '0'
        if ppp_cfg.hasS(ns.pppLcpEchoInterval):
            params['lcp_echo_interval'] = str(ppp_cfg.getS(ns.pppLcpEchoInterval, rdf.Timedelta).seconds)
            params['lcp_echo_failure'] = str(ppp_cfg.getS(ns.pppLcpEchoFailure, rdf.Integer))

        params['auth_pap'] = 'no'
        if ppp_auth.hasS(ns.pppPap) and ppp_auth.getS(ns.pppPap, rdf.Boolean):
            params['auth_pap'] = 'yes'

        params['auth_chap'] = 'no'
        if ppp_auth.hasS(ns.pppChap) and ppp_auth.getS(ns.pppChap, rdf.Boolean):
            params['auth_chap'] = 'yes'

        # MSCHAPv1 had problems with pppd RADIUS support
        params['auth_mschapv1'] = 'no'
        if ppp_auth.hasS(ns.pppMschap) and ppp_auth.getS(ns.pppMschap, rdf.Boolean):
            self._log.warn('auth mschapv1 enabled in config but not supported, ignoring')

        params['auth_mschapv2'] = 'no'
        if ppp_auth.hasS(ns.pppMschapV2) and ppp_auth.getS(ns.pppMschapV2, rdf.Boolean):
            params['auth_mschapv2'] = 'yes'

        params['auth_eap'] = 'no'
        if ppp_auth.hasS(ns.pppEap) and ppp_auth.getS(ns.pppEap, rdf.Boolean):
            self._log.warn('eap enabled in config but not supported, ignoring')

        # compression options
        params['comp_mppc'] = 'no'
        if ppp_comp.hasS(ns.pppMppc) and ppp_comp.getS(ns.pppMppc, rdf.Boolean):
            params['comp_mppc'] = 'yes'
        params['comp_mppe'] = 'no'
        if ppp_comp.hasS(ns.pppMppe) and ppp_comp.getS(ns.pppMppe, rdf.Boolean):
            params['comp_mppe'] = 'yes'
        params['comp_accomp'] = 'no'
        if ppp_comp.hasS(ns.pppAccomp) and ppp_comp.getS(ns.pppAccomp, rdf.Boolean):
            params['comp_accomp'] = 'yes'
        params['comp_pcomp'] = 'no'
        if ppp_comp.hasS(ns.pppPcomp) and ppp_comp.getS(ns.pppPcomp, rdf.Boolean):
            params['comp_pcomp'] = 'yes'
        params['comp_bsdcomp'] = 'no'
        if ppp_comp.hasS(ns.pppBsdcomp) and ppp_comp.getS(ns.pppBsdcomp, rdf.Boolean):
            params['comp_bsdcomp'] = 'yes'
        params['comp_deflate'] = 'no'
        if ppp_comp.hasS(ns.pppDeflate) and ppp_comp.getS(ns.pppDeflate, rdf.Boolean):
            params['comp_deflate'] = 'yes'
        params['comp_predictor1'] = 'no'
        if ppp_comp.hasS(ns.pppPredictor1) and ppp_comp.getS(ns.pppPredictor1, rdf.Boolean):
            params['comp_predictor1'] = 'yes'
        params['comp_vj'] = 'no'
        if ppp_comp.hasS(ns.pppVj) and ppp_comp.getS(ns.pppVj, rdf.Boolean):
            params['comp_vj'] = 'yes'
        params['comp_ccomp_vj'] = 'no'
        if ppp_comp.hasS(ns.pppCcompVj) and ppp_comp.getS(ns.pppCcompVj, rdf.Boolean):
            params['comp_ccomp_vj'] = 'yes'

        # sanity checks
        if params['comp_pcomp'] == 'yes':
            self._log.warning('pcomp enabled - this breaks in mppc: disabling')
            params['comp_pcomp'] = 'no'
        if params['comp_mppe'] == 'yes':
            self._log.warning('mppe enabled - not handled by protocol: disabling')
            params['comp_mppe'] = 'no'

        # dns servers
        params['dns_ipaddr_pri'] = '0'
        params['dns_ipaddr_sec'] = '0'
        dns_list = res_info.ppp_dns_servers
        if len(dns_list) > 0:
            params['dns_ipaddr_pri'] = dns_list[0].address.toString()
            if len(dns_list) > 1:
                params['dns_ipaddr_sec'] = dns_list[1].address.toString()

        # wins servers
        params['wins_ipaddr_pri'] = '0'
        params['wins_ipaddr_sec'] = '0'
        wins_list = res_info.ppp_wins_servers
        if len(wins_list) > 0:
            params['wins_ipaddr_pri'] = wins_list[0].address.toString()
            if len(wins_list) > 1:
                params['wins_ipaddr_sec'] = wins_list[1].address.toString()

        # XXX: check and set sensible values, these are defaults
        params['max_connect_time'] = '0'
        params['max_failure_count'] = '10'

        # NB: This is actually not set, because it causes problems in Openl2tp
        # (boolean argument doesn't work correctly; it will actually be set!)
        params['default_route'] = 'no'
        params['multilink'] = 'no'

        # NB: always use only radius, also local users are from the local radius server
        params['use_radius'] = 'yes'

        # Force radius plugin to use proper config file of radiusclient-ng
        params['radius_hint'] = constants.RADIUSCLIENT_CONFIG

        # Note: there seems to be quite real disagreement between
        # openl2tp configration interface and actual used/set configuration
        # values in openl2tpd:
        # - dns1=0 seems to work in configuration client, but actually it
        # sets the IP address as 0.0.0.0 in pppd config
        # - the zero IP:s do not seem to have any effect because pppd is
        #   resilient.
        # - etc..

        if self.debug_on:
            params['trace_flags'] = '2047' # Full trace
        else:
            params['trace_flags'] = '0'

        ppp_conf = textwrap.dedent("""\

        %(prefix)s ip_pool_name=clientpool

        %(prefix)s default_route=%(default_route)s
        %(prefix)s multilink=%(multilink)s
        %(prefix)s use_radius=%(use_radius)s
        %(prefix)s radius_hint=%(radius_hint)s

        %(prefix)s idle_timeout=%(idle_timeout)s

        %(prefix)s mtu=%(mtu)s
        %(prefix)s mru=%(mru)s

        %(prefix)s local_ipaddr=%(local_ipaddr)s

        %(prefix)s lcp_echo_interval=%(lcp_echo_interval)s
        %(prefix)s lcp_echo_failure_count=%(lcp_echo_failure)s

        # Note: all auth options must be on one line
        %(prefix)s \
        req_none=no \
        auth_pap=no \
        auth_chap=no \
        auth_mschapv1=no \
        auth_mschapv2=no \
        auth_eap=no \
        req_pap=%(auth_pap)s \
        req_chap=%(auth_chap)s \
        req_mschapv1=%(auth_mschapv1)s \
        req_mschapv2=%(auth_mschapv2)s \
        req_eap=%(auth_eap)s

        %(prefix)s \
        mppe=%(comp_mppe)s

        %(prefix)s \
        comp_mppc=%(comp_mppc)s \
        comp_accomp=%(comp_accomp)s \
        comp_pcomp=%(comp_pcomp)s \
        comp_bsdcomp=%(comp_bsdcomp)s \
        comp_deflate=%(comp_deflate)s \
        comp_predictor1=%(comp_predictor1)s \
        comp_vj=%(comp_vj)s \
        comp_ccomp_vj=%(comp_ccomp_vj)s

        %(prefix)s dns_ipaddr_pri=%(dns_ipaddr_pri)s
        %(prefix)s dns_ipaddr_sec=%(dns_ipaddr_sec)s
        %(prefix)s wins_ipaddr_pri=%(wins_ipaddr_pri)s
        %(prefix)s wins_ipaddr_sec=%(wins_ipaddr_sec)s

        %(prefix)s max_connect_time=%(max_connect_time)s
        %(prefix)s max_failure_count=%(max_failure_count)s

        %(prefix)s trace_flags=%(trace_flags)s
        """) % params


        # Tunnel profile
        params = {}
        params['prefix'] = 'tunnel profile modify profile_name=default'

        # Default responder port
        params['our_port'] = '1701'

        # XXX: better values, these are defaults.
        # NB: this works ok in practice, and no need to change if no problems seen.
        params['mtu'] = '1460' # This might affect socket behaviour or the pppol2tp kernel module..

        # XXX: this is default in openl2tp code
        # do we need to configure this?
        params['hello_timeout'] = '60'
        params['retry_timeout'] = '1'

        # Note: must set this to some value other than zero to prevent
        # tunnels from hanging when all connections (sessions) are dead
        params['idle_timeout'] = '1800' # 30 minutes

        params['rx_window_size'] = '4'
        params['tx_window_size']= '10'
        params['max_retries'] = '5'
        
        # XXX: better values, these are defaults
        # possible: none,digital,analog,any
        params['framing_caps'] = 'any'
        params['bearer_caps'] = 'any'

        if self.debug_on:
            params['trace_flags'] = '2047' # Full trace
        else:
            params['trace_flags'] = '0'

        tunnel_conf = textwrap.dedent("""\
        %(prefix)s our_udp_port=%(our_port)s
        %(prefix)s mtu=%(mtu)s
        %(prefix)s hello_timeout=%(hello_timeout)s
        %(prefix)s retry_timeout=%(retry_timeout)s
        %(prefix)s idle_timeout=%(idle_timeout)s

        %(prefix)s rx_window_size=%(rx_window_size)s
        %(prefix)s tx_window_size=%(tx_window_size)s
        %(prefix)s max_retries=%(max_retries)s

        %(prefix)s framing_caps=%(framing_caps)s
        %(prefix)s bearer_caps=%(bearer_caps)s

        %(prefix)s trace_flags=%(trace_flags)s
        """) % params


        # Session profile
        params = {}
        params['prefix'] = 'session profile modify profile_name=default'

        # XXX: should we use sequence numbers for data? maybe not.
        # ppp will receive the packets anyway. reordering might matter
        # for control packets, but that should not happen anyway.
        params['sequencing_required'] = 'no'
        params['use_sequence_numbers'] = 'no'

        if self.debug_on:
            params['trace_flags'] = '2047' # Full trace
        else:
            params['trace_flags'] = '0'

        session_conf = textwrap.dedent("""\
        %(prefix)s sequencing_required=%(sequencing_required)s
        %(prefix)s use_sequence_numbers=%(use_sequence_numbers)s

        %(prefix)s trace_flags=%(trace_flags)s
        """) % params

        # Peer profile
        # Note: no trace flags available for peer profile.. duh.
        params = {}
        params['prefix'] = 'peer profile modify profile_name=default'

        peer_conf = textwrap.dedent("""\
        """) % params

        self.configs = [{'file': constants.OPENL2TP_CONF,
                         'cont': ppp_conf + tunnel_conf + session_conf + peer_conf}]

    def start(self):
        """Start openl2tp."""

        # this does not hurt at all..
        run_command([constants.CMD_MODPROBE, 'pppol2tp'])

        daemon.DaemonConfig.start(self)

    def post_start(self):
        # XXX: need to sleep before configure?

        # XXX: retval is zero when f.ex. config file is missing!
        # check srderr for error messages?

        lock = helpers.acquire_openl2tpconfig_lock()
        if lock is None:
            raise Exception('failed to acquire openl2tp config lock')

        try:
            run_command([constants.CMD_OPENL2TPCONFIG, 'config', 'restore', 'file=' + constants.OPENL2TP_CONF], retval=runcommand.FAIL)
        finally:
            helpers.release_openl2tpconfig_lock(lock)

    def hard_stop(self):
        daemon.DaemonConfig.hard_stop(self)
        self.d.hard_stop_daemon(command=constants.CMD_OPENL2TPCONFIG)

    @db.untransact()
    def determine_tunnel_remote_address_and_port(self, tunnelid):
        """Determine remote IPv4 address and port of a specific tunnel."""

        config = textwrap.dedent("""\
        tunnel show tunnel_id=%s
        quit
        """) % tunnelid

        lock = helpers.acquire_openl2tpconfig_lock()
        if lock is None:
            raise Exception('failed to acquire openl2tp config lock')
        try:
            [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=str(config), retval=runcommand.FAIL)
        finally:
            helpers.release_openl2tpconfig_lock(lock)

        got_tunnelid, srcaddr, srcport, dstaddr, dstport = None, None, None, None, None
        for l in stdout.split('\n'):
            m = _re_openl2tp_tunnel_details_header.match(l)
            if m is not None:
                got_tunnelid, srcaddr, dstaddr = m.group(1), m.group(2), m.group(3)
                continue

            m = _re_openl2tp_tunnel_details_udpports.match(l)
            if m is not None:
                srcport, dstport = m.group(1), m.group(2)

        if dstaddr is None or dstport is None:
            raise Exception('cannot determine endpoint for tunnelid %s' % tunnelid)

        return dstaddr, int(dstport)

    # XXX: refactor configuration so that untranscat may be used here
    # XXX: untransact may help if l2tpconfig blocks
    def start_client_connection(self, identifier, myip, gwip, username, password):
        l2tp_cfg = helpers.get_db_root().getS(ns.l2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))
        ppp_cfg = l2tp_cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))
        
        debug = helpers.get_debug(l2tp_cfg)

        def _run_config(config, failmsg, successmsg):
            rv, out, err = 1, '', ''

            lock = helpers.acquire_openl2tpconfig_lock()
            if lock is None:
                raise Exception('failed to acquire openl2tp config lock')
            try:
                [rv, out, err] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=str(config))
            except:
                pass
            helpers.release_openl2tpconfig_lock(lock)
            if rv != 0:
                self._log.error('%s: %s, %s, %s' % (str(failmsg), str(rv), str(out), str(err)))
                raise Exception(str(failmsg))
            else:
                self._log.debug('%s: %s, %s, %s' % (str(successmsg), str(rv), str(out), str(err)))

            return rv, out, err

        our_port = 1702   # NB: yes, 1702; we differentiate client and site-to-site connections based on local port
        peer_port = 1701

        ppp_profile_name = 'ppp-prof-%s' % identifier
        tunnel_profile_name = 'tunnel-prof-%s' % identifier
        session_profile_name = 'session-prof-%s' % identifier
        peer_profile_name = 'peer-prof-%s' % identifier
        tunnel_name = 'tunnel-%s' % identifier
        session_name = 'session-%s' % identifier

        # we allow openl2tp to select these and "snoop" them from stdout
        tunnel_id = None
        session_id = None

        # ppp profile
        trace_flags = '0'
        if debug:
            trace_flags = '2047'
        config = 'ppp profile create profile_name=%s\n' % ppp_profile_name

        # XXX: take MRU and MTU like normal config?
        # XXX: should we have separate lcp echo etc settings for site-to-site?
        mtu = ppp_cfg.getS(ns.pppMtu, rdf.Integer)
        mru = mtu
        lcp_echo_interval = 0
        lcp_echo_failure = 0
        if ppp_cfg.hasS(ns.pppLcpEchoInterval):
            lcp_echo_interval = ppp_cfg.getS(ns.pppLcpEchoInterval, rdf.Timedelta).seconds
            lcp_echo_failure = ppp_cfg.getS(ns.pppLcpEchoFailure, rdf.Integer)

        for i in [ ['default_route', 'no'],
                   ['multilink', 'no'],
                   ['use_radius', 'no'],
                   ['idle_timeout', '0'],  # no limit
                   ['mtu', str(mtu)],
                   ['mru', str(mru)],
                   ['lcp_echo_interval', str(lcp_echo_interval)],
                   ['lcp_echo_failure_count', str(lcp_echo_failure)],
                   ['max_connect_time', '0'],  # no limit
                   ['max_failure_count', '10'],
                   ['trace_flags', trace_flags] ]:
            config += 'ppp profile modify profile_name=%s %s=%s\n' % (ppp_profile_name, i[0], i[1])

        # Note: all auth options must be on one line
        config += 'ppp profile modify profile_name=%s req_none=yes auth_pap=yes auth_chap=yes auth_mschapv1=no auth_mschapv2=no auth_eap=no req_pap=no req_chap=no req_mschapv1=no req_mschapv2=no req_eap=no\n' % ppp_profile_name

        # no encryption
        config += 'ppp profile modify profile_name=%s mppe=no\n' % ppp_profile_name

        # Note: all compression options must be on one line
        # Request deflate or bsdcomp compression.
        config += 'ppp profile modify profile_name=%s comp_mppc=no comp_accomp=yes comp_pcomp=no comp_bsdcomp=no comp_deflate=yes comp_predictor=no comp_vj=no comp_ccomp_vj=no comp_ask_deflate=yes comp_ask_bsdcomp=no\n' % ppp_profile_name

        # tunnel profile
        config += 'tunnel profile create profile_name=%s\n' % tunnel_profile_name

        trace_flags = '0'
        if debug:
            trace_flags = '2047'

        # XXX: 1460 is hardcoded here, like in normal l2tp connections
        for i in [ ['our_udp_port', str(our_port)],
                   ['peer_udp_port', str(peer_port)],
                   ['mtu', '1460'],
                   ['hello_timeout', '60'],
                   ['retry_timeout', '3'],
                   ['idle_timeout', '0'],
                   ['rx_window_size', '4'],
                   ['tx_window_size', '10'],
                   ['max_retries', '5'],
                   ['framing_caps', 'any'],
                   ['bearer_caps', 'any'],
                   ['trace_flags', trace_flags] ]:
            config += 'tunnel profile modify profile_name=%s %s=%s\n' % (tunnel_profile_name, i[0], i[1])
            
        # session profile
        config += 'session profile create profile_name=%s\n' % session_profile_name

        trace_flags = '0'
        if debug:
            trace_flags = '2047'

        for i in [ ['sequencing_required', 'no'],
                   ['use_sequence_numbers', 'no'],
                   ['trace_flags', trace_flags] ]:
            config += 'session profile modify profile_name=%s %s=%s\n' % (session_profile_name, i[0], i[1])

        # peer profile
        config += 'peer profile create profile_name=%s\n' % peer_profile_name

        # XXX: 'lac_lns', 'netmask'
        # 'peer_port' has no effect for some reason
        for i in [ ['peer_ipaddr', gwip.toString()],
                   ['peer_port', str(peer_port)],  # XXX: dup from above
                   ['ppp_profile_name', ppp_profile_name],
                   ['session_profile_name', session_profile_name],
                   ['tunnel_profile_name', tunnel_profile_name] ]:
            config += 'peer profile modify profile_name=%s %s=%s\n' % (peer_profile_name, i[0], i[1])

        config += '\nquit\n'

        # create profiles
        self._log.debug('openl2tp config:\n%s' % config)
        rv, stdout, stderr = _run_config(config, 'failed to create client-mode profiles', 'create client-mode profiles ok')

        # create tunnel - this triggers openl2tp
        #
        # NOTE: 'interface_name' would make life easier, but is not currently
        # supported by Openl2tp.
        #
        # XXX: 'persist', 'interface_name'
        config = 'tunnel create tunnel_name=%s' % tunnel_name  # NB: all on one line here
        for i in [ ['src_ipaddr', myip.toString()],
                   ['our_udp_port', str(our_port)],   # XXX: dup from above
                   ['peer_udp_port', str(peer_port)], # XXX: dup from above
                   ['dest_ipaddr', gwip.toString()],
                   ['peer_profile_name', peer_profile_name],
                   ['profile_name', tunnel_profile_name],
                   ['session_profile_name', session_profile_name],
                   ['tunnel_name', tunnel_name],
###                ['tunnel_id', tunnel_id], # XXX: for some reason can't be used, fetched below!
                   ['use_udp_checksums', 'yes'] ]: # XXX: probably doesn't do anything now
            config += ' %s=%s' % (i[0], i[1])

        config += '\nquit\n'

        # activate tunnel
        self._log.debug('openl2tp config for tunnel:\n%s' % config)
        rv, stdout, stderr = _run_config(config, 'failed to create client-mode tunnel', 'create client-mode tunnel ok')
        
        for l in stderr.split('\n'):
            m = _re_openl2tp_created_tunnel.match(l)
            if m is not None:
                if tunnel_id is not None:
                    self._log.warning('second tunnel id (%s), old one was %s; ignoring' % (m.group(1), tunnel_id))
                else:
                    tunnel_id = m.group(1)

        self._log.debug('figured out tunnel id %s' % tunnel_id)
        if tunnel_id is None:
            raise Exception('could not figure tunnel id of new site-to-site tunnel (username %s) [rv: %s, out: %s, err: %s]' % (username, rv, stdout, stderr))

        config = 'session create session_name=%s' % session_name
        for i in [ ['tunnel_name', tunnel_name],
                   ['tunnel_id', tunnel_id],
###                ['session_id', session_id], # XXX: for some reason can't be used, fetched below!
                   ['profile_name', session_profile_name],
                   ['ppp_profile_name', ppp_profile_name],
                   ['user_name', username],
                   ['user_password', password] ]:
            config += ' %s=%s' % (i[0], i[1])

        config += '\nquit\n'

        # activate session
        self._log.debug('openl2tp config for session:\n%s' % config)
        rv, stdout, stderr = _run_config(config, 'failed to create client-mode session', 'create client-mode session ok')

        for l in stderr.split('\n'):
            m = _re_openl2tp_created_session.match(l)
            if m is not None:
                if session_id is not None:
                    self._log.warning('second session id (%s), old one was %s; ignoring' % (m.group(2), session_id))
                else:
                    tun = m.group(1)
                    if tun != tunnel_id:
                        self._log.warning('tunnel id differs from earlier (earlier %s, found %s), ignoring' % (tunnel_id, tun))
                    else:
                        session_id = m.group(2)
                        
        self._log.debug('figured out session id %s' % session_id)
        if session_id is None:
            raise Exception('could not figure session id of new site-to-site tunnel (username %s) [rv: %s, out: %s, err: %s]' % (username, rv, stdout, stderr))

        self._log.info('created new tunnel and session (%s/%s) for site-to-site client (username %s)' % (tunnel_id, session_id, username))

    @db.untransact()
    def stop_client_connection(self, identifier):
        """Cleanup Openl2tp state."""

        ppp_profile_name = 'ppp-prof-%s' % identifier
        tunnel_profile_name = 'tunnel-prof-%s' % identifier
        session_profile_name = 'session-prof-%s' % identifier
        peer_profile_name = 'peer-prof-%s' % identifier
        tunnel_name = 'tunnel-%s' % identifier
        session_name = 'session-%s' % identifier

        # delete existing profiles just to be sure

        lock = helpers.acquire_openl2tpconfig_lock()
        if lock is None:
            raise Exception('failed to acquire openl2tp config lock')
        try:
            for i in [ 'session delete tunnel_name=%s session_name=%s' % (tunnel_name, session_name),
                       'tunnel delete tunnel_name=%s' % tunnel_name,
                       'ppp profile delete profile_name=%s' % ppp_profile_name,
                       'tunnel profile delete profile_name=%s' % tunnel_profile_name,
                       'session profile delete profile_name=%s' % session_profile_name,
                       'peer profile delete profile_name=%s' % peer_profile_name ]:
                cmd = '%s\nquit\n' % i
                [rv, out, err] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=str(cmd)) # ignore errors
                if rv != 0:
                    self._log.debug('client connection cleanup command failed:\n command: %s, rv: %s, out: %s, err: %s' % (cmd, rv, out, err))
                else:
                    self._log.debug('client connection cleanup command succeeded:\n command: %s, rv: %s, out: %s, err: %s' % (cmd, rv, out, err))
        finally:
            helpers.release_openl2tpconfig_lock(lock)

        # XXX: nuke pppd devices with our l2tp interface name...
        # XXX: at start of connection, nuke own ppp and ppp device ... look at ps awxuf .. look for ppp device? (pppop2tp_ifname)
