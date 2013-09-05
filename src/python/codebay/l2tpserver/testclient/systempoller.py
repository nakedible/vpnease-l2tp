"""System state polling functionality for test client.

Systempoller performs periodic system state polling and provides
the state information to consumers (test client code) through an exposed
API.  This has the benefits of (1) centralizing system state polling
functionality and (2) reducing system load caused by overlapping polling
in individual threads or processes.

To use this module, instantiate a SystemPoller (giving it the period
parameters appropriate) and call that start() method.

FIXME: This is currently on hold, as thread-based approach was abandoned.
Systempoller can still provide useful global stats (such as SA counts etc)
in syslog.  This functionality might also be useful in the actual gateway.
"""
import time, datetime, thread, re

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.testclient import locks

_log = logger.get('l2tpserver.testclient.systempoller')
run_command = runcommand.run_command

# --- SAD regexps ----------------------------------------------------------
# 172.20.0.1[4500] 172.20.100.247[4500]
_re_sad_start = re.compile(r'^(\S+?)(\[(\d+)\])?\s+(\S+?)(\[(\d+)\])?\s*$')
_re_sad_mode = re.compile(r'^.*?mode=(\S+).*?$')
_re_sad_spi = re.compile(r'^.*?spi=\d+\((\S+?)\).*?$')
_re_sad_state = re.compile(r'^.*?state=(\S+).*?$')
_re_sad_seq = re.compile(r'^.*?seq=(\S+)\s+.*?$')
_re_sad_diff = re.compile(r'^.*?diff:\s*(\d+)\s*\(.*?$')

# --- SPD regexps ----------------------------------------------------------
_re_spd_start1 = re.compile(r'^(\S+?)(\[(\d+)\])?\s+(\S+?)(\[(\d+)\])?\s+.*?$')  # NB: matches also per-socket entries..
_re_spd_start2 = re.compile(r'\S+?per-socket.*?$')
_re_spd_dir = re.compile(r'^\s+(in|out)\s+.*?$')
_re_spd_mode = re.compile(r'^\s+.*?/([^/]+)/.*?$')

# --- Pluto regexps --------------------------------------------------------
# 000 "tunnel-172.20.100.4": 172.20.100.4[S?C]:17/1701---172.20.255.254...172.20.100.247[S?C]:17/1701; unrouted; eroute owner\: #0
_re_pluto_template_start = re.compile(r'^\d+\s+"(.*?)":\s+(.*?)\[(.*?)\]:(.*?)---(.*?)\.\.\.(.*?)\[(.*?)\]:(.*?);\s*(.*?)$')
# FIXME: other template info?

# 000 #2: "tunnel-172.20.100.4":4500 STATE_QUICK_I2 (sent QI2, IPsec SA established); EVENT_SA_REPLACE in 27832s; newest IPSE\C; eroute owner
# 000 #1: "tunnel-172.20.100.4":4500 STATE_MAIN_I4 (ISAKMP SA established); EVENT_SA_REPLACE in 27901s; newest ISAKMP; lastdp\d=-1s(seq in:0 out:0)
_re_pluto_connection_start = re.compile(r'^\d+\s+\#\d+:\s+"(.*?)":(.*?)\s+(.*?)\s+\((.*?)\);\s*(.*?)$')
# 000 #2: "tunnel-172.20.100.4" esp.6152a400@172.20.100.247 esp.441a433f@172.20.100.4
# FIXME: do we need this line for anything?

_re_pluto_connection_isakmp_sa_established = re.compile(r'^.*?ISAKMP\ SA\ established.*?$')
_re_pluto_connection_ipsec_sa_established = re.compile(r'^.*?IPsec\ SA\ established.*?$')
_re_pluto_connection_main_mode_state = re.compile(r'^STATE_MAIN.*?$')
_re_pluto_connection_quick_mode_state = re.compile(r'^STATE_QUICK.*?$')

# --- Openl2tp regexps ---
# Connected to server: localhost
_re_openl2tp_server_show_line = re.compile(r'^Connected\sto\sserver.*?$')

#   TunId             Peer            Local  PeerTId ConfigId            State
_re_openl2tp_tunnel_list_header = re.compile(r'^\s*TunId\s*Peer\s*Local\s*PeerTId\s*ConfigId\s*State\s*$')
#       1   172.20.100.247     172.20.100.1        0        1          CLOSING
_re_openl2tp_tunnel_list_line = re.compile(r'^\s*(.*?)\s+(.*?)\s+(.*?)\s+(.*?)\s+(.*?)\s+(.*?)$')

# This is the raw tunnel details dump, many fields are now ignored
#
#   |Tunnel 1, from 172.20.100.1 to 172.20.100.247:-
#   |  state: CLOSING
#   |  created at:  Aug 18 15:03:14 2006
#   |  administrative name: 'tunnel-172.20.100.1'
#   |  interface name: l2tp-1
#   |  created by admin: YES, tunnel mode: LAC
#   |  peer tunnel id: 0, host name: NOT SET
#   |  UDP ports: local 1701, peer 1701
#   |  authorization mode: NONE, hide AVPs: OFF, allow PPP proxy: OFF
#   |  session limit: 0, session count: 0
#   |  tunnel profile: tunnel-prof-172.20.100.1, peer profile: peer-prof-172.20.100.1
#   |  session profile: session-prof-172.20.100.1, ppp profile: ppp-prof-172.20.100.1
#   |  hello timeout: 60, retry timeout: 1, idle timeout: 0
#   |  rx window size: 4, tx window size: 10, max retries: 5
#   |  use udp checksums: ON
#   |  do pmtu discovery: OFF, mtu: 1460
#   |  framing capability: SYNC ASYNC, bearer capability: DIGITAL ANALOG
#   |  use tiebreaker: OFF
#   |  trace flags: NONE
#   |  peer protocol version: 0.0, firmware 0
#   |  peer framing capability: NONE
#   |  peer bearer capability: NONE
#   |  peer rx window size: 0
#   |  Transport status:-
#   |    ns/nr: 1/0, peer 0/0
#   |    cwnd: 1, ssthresh: 1, congpkt_acc: 0
#   |  Transport statistics:-
#   |    out-of-sequence control/data discards: 0/0
#   |    zlbs tx/txfail/rx: 0/0/0
#   |    retransmits: 6, duplicate pkt discards: 0, data pkt discards: 0
#   |    hellos tx/txfail/rx: 0/0/0
#   |    control rx packets: 0, rx bytes: 0
#   |    control tx packets: 0, tx bytes: 0
#   |    data rx packets: 0, rx bytes: 0, rx errors: 0
#   |    data tx packets: 0, tx bytes: 0, tx errors: 0
#   |    establish retries: 0
# Tunnel 1, from 172.20.100.1 to 172.20.100.247:-
# Tunnel 1, from 172.20.100.1 to 172.20.100.247, ...  (another form)
_re_openl2tp_tunnel_details_header = re.compile(r'^Tunnel\s+(\d+),\s+from\s+(.*?)\s+to\s+([0-9\.]+).*?$')
_re_openl2tp_tunnel_details_state = re.compile(r'^\s+state:\s+(.*?)\s*$')
_re_openl2tp_tunnel_details_name = re.compile(r'^\s+administrative\sname:\s\'(.*?)\'\s*$')
_re_openl2tp_tunnel_details_interface = re.compile(r'^\sinterface\sname:\s(.*?)\s*$')


# This is the raw dump for session list
#
#   |1 sessions on tunnel 1:-
#   |   1
#   |Connected to server: localhost
#   |1 sessions on tunnel 2:-
#   |   2
#   |Connected to server: localhost
_re_openl2tp_session_list_header = re.compile(r'^(\d+)\s+sessions\s+on\s+tunnel\s+(\d+).*?$')
_re_openl2tp_session_list_number = re.compile(r'^\s*(\d+)\s*$')

# --------------------------------------------------------------------------

# FIXME: would be nice to have lifetime info, but pluto doesn't give that to the kernel?
# FIXME: more info, such as inbound/outbound, creation time, lifetime, traffic counts, etc.
class SaInfo:
    """Represents the state of one SA in 'setkey -D'."""

    def __init__(self, srcip=None, srcport=None, dstip=None, dstport=None, mode=None, spi=None, state=None, seq=None, diff=None):
        self.srcip = srcip
        self.srcport = srcport
        self.dstip = dstip
        self.dstport = dstport
        self.mode = mode
        self.spi = spi
        self.state = state
        self.seq = seq
        self.diff = diff

    def toString(self):
        return 'src=%s[%s] dst=%s[%s] mode=%s spi=%s state=%s seq=%s diff=%s' % (self.srcip,
                                                                                 self.srcport,
                                                                                 self.dstip,
                                                                                 self.dstport,
                                                                                 self.mode,
                                                                                 self.spi,
                                                                                 self.state,
                                                                                 self.seq,
                                                                                 self.diff)
    
class SpInfo:
    """Represents the state of one SP in 'setkey -DP'."""

    def __init__(self, srcip=None, srcport=None, dstip=None, dstport=None, mode=None, dir=None):
        self.srcip = srcip
        self.srcport = srcport
        self.dstip = dstip
        self.dstport = dstport
        self.mode = mode
        self.dir = dir

    def toString(self):
        return 'src=%s[%s] dst=%s[%s] mode=%s dir=%s' % (self.srcip,
                                                         self.srcport,
                                                         self.dstip,
                                                         self.dstport,
                                                         self.mode,
                                                         self.dir)

class PlutoTemplateInfo:
    """FIXME."""

    def __init__(self, name=None, router=None, srcip=None, srcsel=None, dstip=None, dstsel=None):
        self.name = name
        self.router = router
        self.srcip = srcip
        self.srcsel = srcsel
        self.dstip = dstip
        self.dstsel = dstsel

    def toString(self):
        return 'name=%s router=%s srcip=%s srcsel=%s dstip=%s dstsel=%s' % (self.name,
                                                                            self.router,
                                                                            self.srcip,
                                                                            self.srcsel,
                                                                            self.dstip,
                                                                            self.dstsel)

class PlutoConnectionInfo:
    """FIXME."""

    def __init__(self, name=None, port=None, state=None, description=None, extrainfo=None, mode=None, phase=None, established=None):
        self.name = name
        self.port = port
        self.state = state
        self.description = description
        self.extrainfo = extrainfo
        self.mode = mode
        self.phase = phase
        self.established = established

    def toString(self):
        return 'name=%s port=%s state=%s description=%s extrainfo=%s mode=%s phase=%s established=%s' % (self.name,
                                                                                                         self.port,
                                                                                                         self.state,
                                                                                                         self.description,
                                                                                                         self.extrainfo,
                                                                                                         self.mode,
                                                                                                         self.phase,
                                                                                                         self.established)

class SystemPoller:
    """Polls system for various statistics (SAs, network interfaces, etc)."""

    def __init__(self, target_period=60.0, minimum_sleep=30.0):
        """Constructor.

        Target_period describes the desired interval of system polling 'sweep'.
        The SystemPoller will attempt to honor this value: for instance, if
        target_period is 10.0 (seconds), and scanning takes 3.1 seconds, the
        sleep for next round will be 6.9 seconds.  If the sleep time is too low
        (minimum_sleep parameter), SystemPoller will clamp the value and sleep
        at least that long before making another sweep.
        """
        
        self.target_period = float(target_period)
        self.target_time = None
        self.minimum_sleep = float(minimum_sleep)
        self.lock = thread.allocate_lock()
        self.sa_list = None
        self.sp_list = None
        self.pluto_template_list = None
        self.pluto_p1_list = None
        self.pluto_p2_list = None
        self.openl2tp_dict = None
        self.link_up_list = None
        self.link_down_list = None

    def start(self):
        """Start polling system state.

        Poll system state forever, sleeping between sweeps.  Blocks and never
        exits; should probably be called from a newly spawned thread.

        FIXME: this should have some exit flag.
        """
        
        while True:
            _log.debug('poller activated')
            
            start_time = time.time()

            # store last poll (target) time, bootstrapping from current time
            if self.target_time is None:
                last_poll = start_time
            else:
                last_poll = self.target_time

            # update state
            self.update_state()

            # figure out next target
            now = time.time()
            next = last_poll + self.target_period    # ideal
            to_sleep = next - now
            if to_sleep < self.minimum_sleep:
                _log.warn('poller to_sleep (%s) < minimum_sleep (%s), forcing minimum_sleep' % (to_sleep, self.minimum_sleep))
                to_sleep = self.minimum_sleep
                self.target_time = now + to_sleep   # also adjust target so we don't get behind permanently
            else:
                self.target_time = next

            end_time = time.time()
            _log.debug('total poller time: %s seconds' % (end_time - start_time))

            _log.debug('poller done, sleeping %s seconds' % to_sleep)
            time.sleep(to_sleep)

    def update_state(self):
        """Update (blockingly) state of the SystemPoller object.

        For a snapshot of system state, it is possible to create a SystemPoller() and
        call this function once without spawning a thread.
        """

        self.lock.acquire()

        try:
            self._poll_sad()
        except:
            _log.exception('cannot poll sad')

        try:
            self._poll_spd()
        except:
            _log.exception('cannot poll spd')
            
        try:
            self._poll_pluto()
        except:
            _log.exception('cannot poll pluto')

        try:
            self._poll_openl2tp()
        except:
            _log.exception('cannot poll openl2tp')

        try:
            self._poll_link_list()
        except:
            _log.exception('cannot poll link list')

        try:
            self._log_debug()
        except:
            _log.exception('debug log failed')
                
        try:
            self._log_summary()
        except:
            _log.exception('log summary failed')

        self.lock.release()

    def _poll_sad(self):
        """Update internal SAD info."""
        def _create_sainfo(sa):
            try:
                return SaInfo(srcip=sa['srcip'], 
                              srcport=sa['srcport'], 
                              dstip=sa['dstip'], 
                              dstport=sa['dstport'], 
                              mode=sa['mode'], 
                              spi=sa['spi'], 
                              state=sa['state'], 
                              seq=sa['seq'], 
                              diff=sa['diff'])
            except:
                _log.debug('incomplete sainfo: %s' % sa)
                return None

        [rv, stdout, stderr] = run_command([constants.CMD_SETKEY, '-D'], retval=runcommand.FAIL)

        sa_list = []
        sa = {}

        def _finish_element(sa):
            sainfo = _create_sainfo(sa)
            if sainfo is not None: sa_list.append(sainfo)
            
        for l in stdout.split('\n'):
            # start of new sa?
            m = _re_sad_start.match(l)
            if m is not None:  # new entry
                _finish_element(sa)
                sa = {}
                sa['srcip'] = m.group(1)
                sa['srcport'] = m.group(3)
                sa['dstip'] = m.group(4)
                sa['dstport'] = m.group(6)
                
            # now we just match whatever parts of *any* of the lines comprising the sa info
            # in setkey dump; we don't try to match individual lines and fields from within,
            # as this is less stateful
            m = _re_sad_mode.match(l)
            if m is not None:
                sa['mode'] = m.group(1)
            m = _re_sad_spi.match(l)
            if m is not None:
                sa['spi'] = m.group(1)
            m = _re_sad_state.match(l)
            if m is not None:
                sa['state'] = m.group(1)
            m = _re_sad_seq.match(l)
            if m is not None:
                sa['seq'] = m.group(1)
            m = _re_sad_diff.match(l)
            if m is not None:
                sa['diff'] = m.group(1)

        # final entry
        _finish_element(sa)
        sa = {}

        # store for later use
        self.sa_list = sa_list
        
    def _poll_spd(self):
        """Update internal SPD info."""

        def _create_spinfo(sp):
            try:
                if sp.has_key('ignore'):
                    return None
                return SpInfo(srcip=sp['srcip'], 
                              srcport=sp['srcport'], 
                              dstip=sp['dstip'], 
                              dstport=sp['dstport'], 
                              mode=sp['mode'], 
                              dir=sp['dir'])
            except:
                _log.debug('incomplete spinfo: %s' % sp)
                return None

        [rv, stdout, stderr] = run_command([constants.CMD_SETKEY, '-DP'], retval=runcommand.FAIL)

        sp_list = []
        sp = {}

        def _finish_element(sp):
            spinfo = _create_spinfo(sp)
            if spinfo is not None: sp_list.append(spinfo)

        for l in stdout.split('\n'):
            # start of a per-socket policy (which we ignore)?
            m = _re_spd_start2.match(l)
            if m is not None:  # new entry
                _finish_element(sp)
                sp = {}
                sp['ignore'] = '1'  # this is caught by _create_spinfo

                # skip rest of processing; _re_spd_start1 also matches this line!
                continue
            
            # start of new sp?
            m = _re_spd_start1.match(l)
            if m is not None:  # new entry
                _finish_element(sp)
                sp = {}
                sp['srcip'] = m.group(1)
                sp['srcport'] = m.group(3)
                sp['dstip'] = m.group(4)
                sp['dstport'] = m.group(6)
            
            # now we just match whatever parts of *any* of the lines comprising the sp info
            # in setkey dump; we don't try to match individual lines and fields from within,
            # as this is less stateful
            m = _re_spd_dir.match(l)
            if m is not None:
                sp['dir'] = m.group(1)
            m = _re_spd_mode.match(l)
            if m is not None:
                sp['mode'] = m.group(1)

        # final entry
        _finish_element(sp)
        sp = {}

        # store for later use
        self.sp_list = sp_list

    def _poll_pluto(self):
        """Update internal pluto info."""

        # get stuff from pluto, remembering to get a global lock...

        locks.whack_lock_acquire()

        try:
            # FIXME: can't have retval=FAIL because pluto is careless about retval
            [rv, stdout, stderr] = run_command([constants.CMD_IPSEC, 'whack', '--status'])
        except:
            _log.exception('whack failed')

        locks.whack_lock_release()

        template_list = []
        p1_list = []
        p2_list = []
        template = {}
        connection = {}

        def _create_pluto_template(t):
            try:
                return PlutoTemplateInfo(name=t['name'], 
                                         router=t['router'], 
                                         srcip=t['srcip'], 
                                         srcsel=t['srcsel'], 
                                         dstip=t['dstip'], 
                                         dstsel=t['dstsel'])
            except:
                _log.debug('incomplete template info: %s' % t)
                return None

        def _create_pluto_connection(t):
            try:
                return PlutoConnectionInfo(name=t['name'],
                                           port=t['port'],
                                           state=t['state'],
                                           description=t['description'],
                                           extrainfo=t['extrainfo'],
                                           mode=t['mode'],
                                           phase=t['phase'],
                                           established=t['established'])
            except:
                _log.debug('incomplete template info: %s' % t)
                return None
        
        def _finish_element(template, connection):
            if len(template.keys()) > 0:
                t = _create_pluto_template(template)
                template_list.append(t)
            if len(connection.keys()) > 0:
                t = _create_pluto_connection(connection)
                if connection['phase'] == 1:
                    p1_list.append(t)
                elif connection['phase'] == 2:
                    p2_list.append(t)
                else:
                    _log.error('illegal phase: %s' % connection['phase'])
            
        for l in stdout.split('\n'):
            # start of a template?
            m = _re_pluto_template_start.match(l)
            if m is not None:
                _finish_element(template, connection)
                template = {}
                connection = {}

                template['name'] = m.group(1)
                template['srcip'] = m.group(2)
                template['srcsel'] = m.group(4)
                template['router'] = m.group(5)
                template['dstip'] = m.group(6)
                template['dstsel'] = m.group(7)
                continue

            # start of a connection?
            m = _re_pluto_connection_start.match(l)
            if m is not None:
                _finish_element(template, connection)
                template = {}
                connection = {}

                desc = m.group(4)
                state = m.group(3)
                connection['name'] = m.group(1)
                connection['port'] = m.group(2)
                connection['state'] = state
                connection['description'] = desc
                connection['extrainfo'] = m.group(5)

                mode, phase = None, None
                if _re_pluto_connection_main_mode_state.match(state):
                    mode, phase = 'main', 1
                if _re_pluto_connection_quick_mode_state.match(state):
                    mode, phase = 'quick', 2
                connection['mode'] = mode
                connection['phase'] = phase

                if phase == 1:
                    if _re_pluto_connection_isakmp_sa_established.match(desc):
                        connection['established'] = True
                    else:
                        connection['established'] = False
                elif phase == 2:
                    if _re_pluto_connection_ipsec_sa_established.match(desc):
                        connection['established'] = True
                    else:
                        connection['established'] = False
                else:
                    _log.warning('cannot figure out phase from string: %s' % l)

                continue

        _finish_element(template, connection)
        template = {}
        connection = {}

        self.pluto_template_list = template_list
        self.pluto_p1_list = p1_list
        self.pluto_p2_list = p2_list

    def _poll_openl2tp(self):
        """Update internal openl2tp info.

        The approach to poll openl2tp is a bit convoluted because we need
        interaction with openl2tp to discover and get details of all objects
        maintained by openl2tp.  A particular example is session details:
        to get them, we first need tunnel names (one command), then session
        names *per tunnel* (another command), and finally a command to list
        details of every session&tunnel pair.  This means that a minimum of
        three interactions are required to extract all data.  Because our
        command running facilities in Python are not well suited to interactive
        use, we run commands in a sequence.

        Theoretically three commands are enough, but for simplicity we run
        four separate commands:

           * First command: extract tunnel IDs

           * Second command: extract tunnel details (incl. names)

           * Third command: extract session names for each tunnel

           * Fourth command: extract session details

        One particular problem is that commands are not echoed by openl2tp,
        so it is difficult to determine when the output of one individual
        command ends and another begins.  We use the openl2tp command
        'server show' for this purpose, as it outputs text of the form:

            Connected to server: localhost

        This line in the output divides individual entries.

        Intermediate data is represented as dictionaries:

           tunnels     dictionary of tunnels, key = tunnel id, value is tunnel
           
           tunnel      dictionary with following keys:
                           sessions
                           id
                           from
                           to
                           state
                           name

           sessions    dictionary of sessions, key = session id, value is session

           session     dictionary with following keys:
                           id
                           ...
        """

        tunnels = {}   # tunnels are represented as a dict, key=tunnel name

        # get tunnel ids
        cmd = 'tunnel list\nquit\n'
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=cmd, retval=runcommand.FAIL)
        for l in stdout.split('\n'):
            m = _re_openl2tp_tunnel_list_header.match(l)
            if m is not None:
                continue

            m = _re_openl2tp_tunnel_list_line.match(l)
            if m is not None:
                id = m.group(1)
                tunnel = {}
                tunnels[id] = tunnel
                tunnel['id'] = id
                tunnel['sessions'] = {}
                continue
            
            _log.debug('unknown line: %s' % l)
        _log.debug('tunnel list:\n%s' % tunnels)
        
        # get tunnel details
        cmd = ''
        for i in tunnels.keys():
            cmd += 'tunnel show tunnel_id=%s\n' % i
            cmd += 'server show\n'
        cmd += '\nquit\n'
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=cmd, retval=runcommand.FAIL)

        tun = None
        for l in stdout.split('\n'):
            m = _re_openl2tp_server_show_line.match(l)
            if m is not None:
                continue  # FIXME: don't need this

            m = _re_openl2tp_tunnel_details_header.match(l)
            if m is not None:
                id = m.group(1)
                if tunnels.has_key(id):
                    tun = tunnels[id]
                else:
                    tun = None

                if tun is not None:
                    tun['from'] = m.group(2)
                    tun['to'] = m.group(3)
            
            m = _re_openl2tp_tunnel_details_state.match(l)
            if m is not None:
                if tun is not None:
                    tun['state'] = m.group(1)

            m = _re_openl2tp_tunnel_details_name.match(l)
            if m is not None:
                if tun is not None:
                    tun['name'] = m.group(1)

            m = _re_openl2tp_tunnel_details_interface.match(l)
            if m is not None:
                if tun is not None:
                    tun['interface'] = m.group(1)
        _log.debug('tunnel details:\n%s' % tunnels)

        # get session ids
        cmd = ''
        for i in tunnels.keys():
            cmd += 'session list tunnel_id=%s\n' % i
            cmd += 'server show\n'
        cmd += '\nquit\n'
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=cmd, retval=runcommand.FAIL)

        tun = None
        for l in stdout.split('\n'):
            m = _re_openl2tp_session_list_header.match(l)
            if m is not None:
                session_count = m.group(1)
                tunnel_id = m.group(2)
                if tunnels.has_key(tunnel_id):
                    tun = tunnels[tunnel_id]
                else:
                    tun = None
                continue
            
            m = _re_openl2tp_session_list_number.match(l)
            if m is not None:
                session_id = m.group(1)
                if tun is not None:
                    if tun['sessions'].has_key(session_id):
                        _log.debug('tunnel already has session %s' % session_id)
                    else:
                        session = {}
                        tun['sessions'][session_id] = session
                        session['id'] = session_id
                else:
                    _log.debug('orphan session id: %s' % l)
        _log.debug('tunnel details:\n%s' % tunnels)
        
        # get session details
        #
        # ***
        # FIXME
        # ***
        #
        # This fails for some bizarre reason - even when run manually.  Fix later.
        # We don't get session details now, but do get their count.
        cmd = ''
        for i in tunnels.keys():
            tunnel = tunnels[i]
            sessions = tunnel['sessions']
            for j in sessions.keys():
##                cmd += 'session show tunnel_id=%s session_id=%s\n' % (i, j)
                cmd += 'session show tunnel_name=%s session_id=%s\n' % (tunnel['name'], j)
                cmd += 'server show\n'
        cmd += '\nquit\n'
        [rv, stdout, stderr] = run_command([constants.CMD_OPENL2TPCONFIG], stdin=cmd, retval=runcommand.FAIL)
        _log.debug('tunnel details:\n%s' % tunnels)
                
        # parse into useful internal representation
        #
        # FIXME: not now.. just stash the dict.
        self.openl2tp_dict = tunnels

    def _poll_link_list(self):
        # FIXME: parse and check address, etc.

        link_re = re.compile('\d+: l2tp\d+-\d+: <([^>]+)>')
        link_up_re = re.compile(',UP')
        link_up_list = []
        link_down_list = []

        [rv, out, err] = run_command([constants.CMD_IP, '-o', 'link', 'list'])
        for line in out.split('\n'):
            m = link_re.match(line)
            if m is None:
                continue
            m = link_up_re.search(m.groups()[0])
            if m is None:
                link_down_list.append(line)
            else:
                link_up_list.append(line)

        self.link_up_list = link_up_list
        self.link_down_list = link_down_list

    def _log_debug(self):
        sa_list = self.sa_list
        sp_list = self.sp_list
        pluto_template_list = self.pluto_template_list
        pluto_p1_list = self.pluto_p1_list
        pluto_p2_list = self.pluto_p2_list
        openl2tp_dict = self.openl2tp_dict
        link_up_list = self.link_up_list
        link_down_list = self.link_down_list

        _log.debug('sainfo update')
        if sa_list is not None:
            if len(sa_list) > 0:
                for s in sa_list:
                    _log.debug('    ' + s.toString())
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')
            
        _log.debug('spinfo update')
        if sp_list is not None:
            if len(sp_list) > 0:
                for s in sp_list:
                    _log.debug('    ' + s.toString())
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

        _log.debug('pluto template update')
        if pluto_template_list is not None:
            if len(pluto_template_list) > 0:
                for s in pluto_template_list:
                    _log.debug('    ' + s.toString())
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

        _log.debug('pluto p1 update')
        if pluto_p1_list is not None:
            if len(pluto_p1_list) > 0:
                for s in pluto_p1_list:
                    _log.debug('    ' + s.toString())
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

        _log.debug('pluto p2 update')
        if pluto_p2_list is not None:
            if len(pluto_p2_list) > 0:
                for s in pluto_p2_list:
                    _log.debug('    ' + s.toString())
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

        _log.debug('openl2tp update')
        if openl2tp_dict is not None:
            _log.debug('    ' + str(openl2tp_dict))
        else:
            _log.debug('    unknown (no state)')

        _log.debug('link up list update')
        if link_up_list is not None:
            if len(link_up_list) > 0:
                for l in link_up_list:
                    _log.debug('    ' + str(l))
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

        _log.debug('link down list update')
        if link_down_list is not None:
            if len(link_down_list) > 0:
                for l in link_down_list:
                    _log.debug('    ' + str(l))
            else:
                _log.debug('    no entries')
        else:
            _log.debug('    unknown (no state)')

    def _log_summary(self):
        """Write a one-line summary log."""
        if self.sp_list is not None:
            num_sp = len(self.sp_list)
        else:
            num_sp = '???'
        if self.sa_list is not None:
            num_sa = len(self.sa_list)
        else:
            num_sa = '???'
        if self.pluto_template_list is not None:
            num_pluto_templates = len(self.pluto_template_list)
        else:
            num_pluto_templates = '???'
        if self.pluto_p1_list is not None:
            p1_total = 0
            p1_estab = 0
            for i in self.pluto_p1_list:
                p1_total += 1
                if i.established:
                    p1_estab += 1
        else:
            num_pluto_p1 = '???'
        if self.pluto_p2_list is not None:
            p2_total = 0
            p2_estab = 0
            for i in self.pluto_p2_list:
                p2_total += 1
                if i.established:
                    p2_estab += 1
        else:
            num_pluto_p2 = '???'

        # FIXME: sync with openl2tp session status
        if self.link_up_list is not None:
            num_l2tp_devices_up = str(len(self.link_up_list))
        else:
            num_l2tp_devices_up = '???'

        if self.link_down_list is not None:
            num_l2tp_devices_down = str(len(self.link_down_list))
        else:
            num_l2tp_devices_down = '???'

        if self.openl2tp_dict is not None:
            tunnels = self.openl2tp_dict
            num_l2tp_tunnels = 0
            num_l2tp_sessions = 0
            for i in tunnels.keys():
                num_l2tp_tunnels += 1
                tunnel = tunnels[i]
                for j in tunnel['sessions'].keys():
                    num_l2tp_sessions += 1
        else:
            num_l2tp_tunnels = '???'
            num_l2tp_sessions = '???'

        # FIXME: this could use more detailed l2tp info (e.g. tunnel/session state breakdown)
        _log.info('system status: num_sp=%s, num_sa=%s, num_pluto_templates=%s, num_pluto_p1=%s (established %s), num_pluto_p2=%s (established %s), num_l2tp_tunnels=%s, num_l2tp_sessions=%s, num_l2tp_devices=%s/%s (up/down)' % (num_sp, num_sa, num_pluto_templates, p1_total, p1_estab, p2_total, p2_estab, num_l2tp_tunnels, num_l2tp_sessions, num_l2tp_devices_up, num_l2tp_devices_down))
