"""OpenSwan Pluto configuration wrapper."""
__docformat__ = 'epytext en'

import os, re

from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon
from codebay.l2tpserver import db

ns = rdfconfig.ns
run_command = runcommand.run_command

# sainfo file
_re_preshared_secret_index = re.compile(r'^preshared\ssecret\sindex:\s*(\d+)$')

# setkey -D
_re_sad_start = re.compile(r'^(\S+?)(\[(\d+)\])?\s+(\S+?)(\[(\d+)\])?\s*$')
_re_sad_mode = re.compile(r'^.*?mode=(\S+).*?$')
_re_sad_spi = re.compile(r'^.*?spi=\d+\(0x(\S+?)\).*?$')
_re_sad_state = re.compile(r'^.*?state=(\S+).*?$')
_re_sad_seq = re.compile(r'^.*?seq=(\S+)\s+.*?$')
_re_sad_diff = re.compile(r'^.*?diff:\s*(\d+)\s*\(.*?$')

#
# XXX: whack needs locking if they are used in parallel - at the
# moment startstop does all the whacking, so there is no need for
# locks
#

class PlutoConfig(daemon.DaemonConfig):
    name = 'pluto'
    command = constants.CMD_PLUTO
    pidfile = constants.PLUTO_PIDFILE
    cleanup_files=[constants.PLUTO_CTLFILE]

    def get_args(self):
        if self.debug_heavy:
            d = ['--debug-all']
        elif self.debug_on:
            d = ['--debug-klips', '--debug-control', '--debug-lifecycle']
        else:
            d = ['--debug-none']

        return ['--secretsfile',
                constants.PLUTO_CONF,
                '--nat_traversal',
                '--nhelpers', '0'] + d

    def create_config(self, cfg, resinfo):
        self.create_config_pluto(cfg, resinfo)
        
    def create_config_pluto(self, cfg, resinfo, extra_psks=[]):
        def _psk_sanity_check(pskbin):
            for i in xrange(len(pskbin)):  # basic sanity check - XXX: insufficient
                c = ord(pskbin[i])
                if (c <= 0x20) or (c > 0x7e):
                    raise Exception('PSK contains invalid character(s)')

        ipsec_cfg = cfg.getS(ns.ipsecConfig, rdf.Type(ns.IpsecConfig))
        ike_lifetime = ipsec_cfg.getS(ns.ikeLifeTime, rdf.Timedelta).seconds
        ipsec_lifetime = ipsec_cfg.getS(ns.ipsecLifeTime, rdf.Timedelta).seconds
        self.debug_on = helpers.get_debug(cfg)
        self.debug_heavy = helpers.get_debug_heavy(cfg)
        self.ip = resinfo.public_interface.address.getAddress().toString()
        self.ike_lifetime = str(ike_lifetime)
        self.ipsec_lifetime = str(ipsec_lifetime)

        ownaddr = resinfo.public_interface.address.getAddress().toString()

        psks = ipsec_cfg.getS(ns.preSharedKeys, rdf.Seq(rdf.Type(ns.PreSharedKey)))

        # log unusual psk amounts (0, >1)
        if len(psks) == 0:
            self._log.warning('zero psks')
        elif len(psks) > 1:
            self._log.info('more than one psk (%s)' % len(psks))
        else:
            self._log.debug('one psk, good')

        pskfile = ''

        def _encode_hex(s):
            r = '0x'
            for i in s:
                r += '%02x' % ord(i)
            return r

        # start with specific "extra_psks"
        for [addr, pskbin] in extra_psks:
            # XXX: no sanity check because using hex encoding
            # _psk_sanity_check(pskbin)
            pskfile += '%s : PSK %s\n' % (addr, _encode_hex(pskbin))

        # end with generic psks
        for psk in psks:
            pskbin = psk.getS(ns.preSharedKey, rdf.Binary)
            # XXX: no sanity check because using hex encoding
            # _psk_sanity_check(pskbin)
            pskfile += ': PSK %s\n' % _encode_hex(pskbin)

        self.configs = [{'file': constants.PLUTO_CONF,
                         'cont': pskfile,
                         'mode': 0600}]

    def reread_psks(self):
        run_command([constants.CMD_IPSEC, 'whack', '--rereadsecrets'], retval=runcommand.FAIL)
        
    def post_start(self):
        """Whack pluto to set its configuration."""

        self._log.debug('whack_pluto')

        # Note: whack exit status is unreliable because it tries to
        # deliver pluto progress status (if received) failing to convert
        # some success progress statuses to 0.
        # There is not much more to do than hope for the best..
        
        [rv, ig1, err] = run_command([constants.CMD_IPSEC, 'whack', '--listen'])
        self._log.debug('whack --listen return value: %d, stderr: %s' % (rv, err))

        self._log.debug('pluto whack params: ip=%s, router=%s' % (self.ip, self.ip))

        [rv, ig1, err] = run_command([constants.CMD_IPSEC, 'whack',
                                      '--name', 'l2tptunnel',
                                      '--host', self.ip,
                                      '--nexthop', self.ip,
                                      '--clientprotoport', '17/1701',
                                      '--updown', constants.CMD_TRUE,
                                      '--to', '--host', '%any',
                                      '--clientprotoport', '17/0',
                                      '--updown', constants.CMD_TRUE,
                                      '--psk',
                                      '--encrypt',
                                      '--ike=aes-128-sha1-160-modp1536',
                                      '--ikelifetime', self.ike_lifetime,
                                      '--ipseclifetime', self.ipsec_lifetime,
                                      '--dontrekey',
                                      '--forceencaps'])
        self._log.debug('whack (tunnel) return value: %d, stderr: %s' % (rv, err))

    def _flush_ipsec(self):
        self._log.debug('flusing IPsec')

        try:
            run_command([constants.CMD_SETKEY, '-F'], retval=runcommand.FAIL)
        except:
            self._log.exception('IPsec SA flush failed')
            raise

        try:
            run_command([constants.CMD_SETKEY, '-FP'], retval=runcommand.FAIL)
        except:
            self._log.exception('IPsec policy flush failed')
            raise

    def post_stop(self):
        self._log.debug('pluto post stop.')

        try:
            self._flush_ipsec()
        except:
            self._log.warning('Tolerating failed IPsec policy/SA flush in normal stop')
            pass

    def hard_stop(self):
        self._log.debug('pluto hard stop.')

        self.d.hard_stop_daemon(command=self.command, pidfile=self.pidfile)
        self.d.cleanup_daemon(pidfile=self.pidfile, cleanup_files=self.cleanup_files)

        self._flush_ipsec()

    @db.untransact()
    def determine_sainfo_from_address_and_port(self, remaddr, remport):
        # XXX: it would be better to use the latest SA created based
        # on creation time, but currently we use the first matching in
        # the list which is assumed to be latest.

        [rv, stdout, stderr] = run_command([constants.CMD_SETKEY, '-D'], retval=runcommand.FAIL)

        match_rx, match_tx = False, False
        spi_rx, spi_tx = None, None
        is_udp_encaps = None

        for l in stdout.split('\n'):
            m = _re_sad_start.match(l)
            if m is not None:
                match_rx, match_tx = False, False
                txip, txport, rxip, rxport = m.group(1), m.group(3), m.group(4), m.group(6)

                if txport is not None and rxport is not None:  # udp encaps
                    is_udp_encaps = True
                    if txip == remaddr and int(txport) == remport:
                        match_rx = True
                    elif rxip == remaddr and int(rxport) == remport:
                        match_tx = True
                elif txport is None and txport is None:        # plain esp
                    is_udp_encaps = False
                    if txip == remaddr and remport == 1701:
                        match_rx = True
                    elif rxip == remaddr and remport == 1701:
                        match_tx = True
                else:
                    raise Exception('cannot parse setkey line: %s, %s, %s, %s' % (txip, txport, rxip, rxport))

            if match_rx:
                m = _re_sad_spi.match(l)
                if m is not None:
                    if spi_rx is None: # XXX: take first match
                        spi_rx = m.group(1)
            elif match_tx:
                m = _re_sad_spi.match(l)
                if m is not None:
                    if spi_tx is None: # XXX: take first match
                        spi_tx = m.group(1)

            if (spi_rx is not None) and (spi_tx is not None):
                return spi_rx, spi_tx, is_udp_encaps
        
        return None, None, None

    def determine_psk_index_from_spi(self, spi):
        fname = os.path.join(constants.PLUTO_SAINFO_DIR, 'sainfo_%s' % spi)  # spi is an 8-digit hex string
        self._log.debug('spi filename is %s' % fname)

        pss_index = None
        f = None
        try:
            f = open(fname)
            t = f.read()

            pss_index = None
            for l in t.split('\n'):
                m = _re_preshared_secret_index.match(l)
                if m is not None:
                    pss_index = int(m.group(1))
        finally:
            if f is not None:
                f.close()

        return pss_index


    # Note: we *should* stop/start so that the the connection is first
    # deleted and then added again to ensure that the pluto handles
    # the connection correctly. Current patch should handle reinit for
    # the existing connection cleanly, but it is unsure if some code
    # in pluto will confuse it with mainmode rekey start.

    def start_client_connection(self, identifier, ownip, destip):
        """Add a client connection after initial configuration.

        This is complicated slightly by the fact that our product identifies
        the remote endpoint using (optionally) a domain name.  In that case,
        we don't know the remote endpoint IP address statically.  Here we
        assume that the caller has already updated PSK configuration (if
        appropriate).

        The 'identifier' variable is used to identify the site-to-site
        connection despite changes in endpoint address.  The identifier
        must be acceptable as a suffix to a pluto connection name.
        """

        self._log.debug('add_client_connection: %s / %s' % (identifier, destip.toString()))
        
        # Note: whack exit status is unreliable because it tries to
        # deliver pluto progress status (if received) failing to convert
        # some success progress statuses to 0.  There is not much more to
        # do than hope for the best..
        #
        # If pluto fails, site-to-site health check will eventually
        # time out and delete+readd the connection.

        try:
            tunnel_name = identifier
            ike_lifetime = 8*60*60
            ipsec_lifetime = 8*60*60
            keying_tries = 5   # XXX: 0=persist, but we don't want that

            # --forceencaps is not necessary: gateway will force anyway
            [rv, ig, err] = run_command([constants.CMD_IPSEC, 'whack',
                                         '--name', tunnel_name,
                                         '--host', ownip.toString(),
                                         '--nexthop', ownip.toString(),
                                         '--clientprotoport', '17/1702',  # Yes!
                                         '--updown', constants.CMD_TRUE,
                                         '--to', '--host', destip.toString(),
                                         '--clientprotoport', '17/1701',
                                         '--updown', constants.CMD_TRUE,
                                         '--psk',
                                         '--encrypt',
                                         '--ike=aes-128-sha1-160-modp1536',
                                         '--ikelifetime', str(ike_lifetime),
                                         '--ipseclifetime', str(ipsec_lifetime),
                                         '--keyingtries', str(keying_tries)])

            self._log.debug('whack (tunnel) return value: %d, stderr: %s' % (rv, err))

            # initiate sa in an asynchronous manner
            (rv, ig, err) = run_command([constants.CMD_IPSEC, 'whack', '--initiate',
                                         '--asynchronous',
                                         '--name', tunnel_name])
            self._log.debug('whack (initiate) return value: %d, stderr: %s' % (rv, err))

            self._log.info('started site-to-site pluto connection %s to destination %s' % (tunnel_name, destip.toString()))
        except:
            self._log.exception('add_client_connection (%s, %s) failed' % (identifier, destip.toString()))
            
    def stop_client_connection(self, identifier, silent=False):
        """Remove a client connection after initial configuration."""

        self._log.debug('remove_client_connection: %s' % identifier)

        try:
            tunnel_name = identifier
            [rv, ig, err] = run_command([constants.CMD_IPSEC, 'whack',
                                         '--delete', '--name', tunnel_name])
            self._log.debug('delete (tunnel) return value: %d, stderr: %s' % (rv, err))
        except:
            if not silent:
                self._log.exception('remove_client_connection(%s) failed' % identifier)
            else:
                self._log.debug('remove_client_connection(%s) failed (silent)' % identifier)
