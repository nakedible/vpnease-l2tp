"""
Management protocol client.

This module is used by multiple callers; currently web UI and the boot
time update process.  The ManagementConnection class is the central
object in this module, managing the starting and stopping of the
management connection.

ManagementConnection calls upwards to a 'master' when siginificant
protocol events occur.  See codebay.l2tpserver.webui.master for a
desription of this expected interface and a stub parent class which
provides empty method implementations.
"""
__docformat__ = 'epytext en'

import os, datetime

from OpenSSL import SSL
from twisted.internet import protocol, reactor, defer, error, ssl

from codebay.common import runcommand
from codebay.common import logger

from codebay.l2tpmanagementprotocol import managementprotocol
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db

from codebay.common import amphelpers

run_command = runcommand.run
_log = logger.get('l2tpserver.managementconnection')

# From VPNease 1.2 onwards, management server DNS name is dependent on version in Version() exchange
SERVER_ADDRESS = constants.PRODUCT_MANAGEMENT_SERVER_ADDRESS_TEMPLATE % managementprotocol.PROTOCOL_VERSION
SERVER_PORT = constants.PRODUCT_MANAGEMENT_SERVER_PORT

SSL_CERTIFICATE_CHAIN_VERIFY_DEPTH = 8

# See: man ciphers(1)
SSL_CIPHER_LIST = ':'.join(['AES256-SHA',                     # TLS_RSA_WITH_AES_256_CBC_SHA
                            'AES128-SHA',                     # TLS_RSA_WITH_AES_128_CBC_SHA
                            'DES-CBC3-SHA'])                  # TLS_RSA_WITH_3DES_EDE_CBC_SHA

# --------------------------------------------------------------------------
#  From: /usr/include/openssl/x509_vfy.h  (verify error codes)
#
#    #define         X509_V_OK                                       0
#    /* illegal error (for uninitialized values, to avoid X509_V_OK): 1 */
#    
#    #define         X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT            2
#    #define         X509_V_ERR_UNABLE_TO_GET_CRL                    3
#    #define         X509_V_ERR_UNABLE_TO_DECRYPT_CERT_SIGNATURE     4
#    #define         X509_V_ERR_UNABLE_TO_DECRYPT_CRL_SIGNATURE      5
#    #define         X509_V_ERR_UNABLE_TO_DECODE_ISSUER_PUBLIC_KEY   6
#    #define         X509_V_ERR_CERT_SIGNATURE_FAILURE               7
#    #define         X509_V_ERR_CRL_SIGNATURE_FAILURE                8
#    #define         X509_V_ERR_CERT_NOT_YET_VALID                   9
#    #define         X509_V_ERR_CERT_HAS_EXPIRED                     10
#    #define         X509_V_ERR_CRL_NOT_YET_VALID                    11
#    #define         X509_V_ERR_CRL_HAS_EXPIRED                      12
#    #define         X509_V_ERR_ERROR_IN_CERT_NOT_BEFORE_FIELD       13
#    #define         X509_V_ERR_ERROR_IN_CERT_NOT_AFTER_FIELD        14
#    #define         X509_V_ERR_ERROR_IN_CRL_LAST_UPDATE_FIELD       15
#    #define         X509_V_ERR_ERROR_IN_CRL_NEXT_UPDATE_FIELD       16
#    #define         X509_V_ERR_OUT_OF_MEM                           17
#    #define         X509_V_ERR_DEPTH_ZERO_SELF_SIGNED_CERT          18
#    #define         X509_V_ERR_SELF_SIGNED_CERT_IN_CHAIN            19
#    #define         X509_V_ERR_UNABLE_TO_GET_ISSUER_CERT_LOCALLY    20
#    #define         X509_V_ERR_UNABLE_TO_VERIFY_LEAF_SIGNATURE      21
#    #define         X509_V_ERR_CERT_CHAIN_TOO_LONG                  22
#    #define         X509_V_ERR_CERT_REVOKED                         23
#    #define         X509_V_ERR_INVALID_CA                           24
#    #define         X509_V_ERR_PATH_LENGTH_EXCEEDED                 25
#    #define         X509_V_ERR_INVALID_PURPOSE                      26
#    #define         X509_V_ERR_CERT_UNTRUSTED                       27
#    #define         X509_V_ERR_CERT_REJECTED                        28
#    /* These are 'informational' when looking for issuer cert */
#    #define         X509_V_ERR_SUBJECT_ISSUER_MISMATCH              29
#    #define         X509_V_ERR_AKID_SKID_MISMATCH                   30
#    #define         X509_V_ERR_AKID_ISSUER_SERIAL_MISMATCH          31
#    #define         X509_V_ERR_KEYUSAGE_NO_CERTSIGN                 32
#    
#    #define         X509_V_ERR_UNABLE_TO_GET_CRL_ISSUER             33
#    #define         X509_V_ERR_UNHANDLED_CRITICAL_EXTENSION         34
#    #define         X509_V_ERR_KEYUSAGE_NO_CRL_SIGN                 35
#    #define         X509_V_ERR_UNHANDLED_CRITICAL_CRL_EXTENSION     36
#    #define         X509_V_ERR_INVALID_NON_CA                       37
#    #define         X509_V_ERR_PROXY_PATH_LENGTH_EXCEEDED           38
#    #define         X509_V_ERR_KEYUSAGE_NO_DIGITAL_SIGNATURE        39
#    #define         X509_V_ERR_PROXY_CERTIFICATES_NOT_ALLOWED       40
#    
#    #define         X509_V_ERR_INVALID_EXTENSION                    41
#    #define         X509_V_ERR_INVALID_POLICY_EXTENSION             42
#    #define         X509_V_ERR_NO_EXPLICIT_POLICY                   43
#    
#    #define         X509_V_ERR_UNNESTED_RESOURCE                    44
#    
#    /* The application is not happy */
#    #define         X509_V_ERR_APPLICATION_VERIFICATION             50


# XXX: are these available from some import?
OPENSSL_VFY_ERR_CERT_SIGNATURE_FAILURE = 7
OPENSSL_VFY_ERR_CERT_NOT_YET_VALID = 9
OPENSSL_VFY_ERR_CERT_HAS_EXPIRED = 10
OPENSSL_VFY_ERR_CERT_UNTRUSTED = 27
OPENSSL_VFY_ERR_CERT_REJECTED = 28

# --------------------------------------------------------------------------

class ManagementConnectionSslContextFactory(ssl.ClientContextFactory):
    """Subclassed SSL context factory.

    We need to subclass the context factory to ensure TLS 1.0 is used
    instead of SSL 3.0, and to provide our own certificate validation
    control - especially the correct root CA, our own revocation list,
    and ignoring of timestamps.

    For a lot of PyOpenSSL documentation, see:
    http://pyopenssl.sourceforge.net/pyOpenSSL.html/openssl.html.
    """
    method = SSL.TLSv1_METHOD
    _revoked = None
    _trusted = None
    _authenticated = False
    
    def _load_revoked(self):
        """Load revoked certificate hashes."""
        revoked = []
        if os.path.exists(constants.MANAGEMENT_CONNECTION_REVOKED_CERTIFICATES_FILE):
            f = open(constants.MANAGEMENT_CONNECTION_REVOKED_CERTIFICATES_FILE, 'rb')
            for l in f.readlines():
                try:
                    l = l.strip()
                    l = l.lower()  # just in case
                    l = str(l)     # just in case
                    if l == '':
                        pass
                    elif len(l) != (2*20):
                        raise Exception('invalid sha1 digest')
                    revoked.append(l.decode('hex'))
                except:
                    _log.exception('ignoring invalid revoked certificate line: "%s"' % l)
        else:
            _log.info('no revoked certificates file %s, ignoring' % constants.MANAGEMENT_CONNECTION_REVOKED_CERTIFICATES_FILE)
        _log.debug('loaded revoked certificate hashes: %s' % self._revoked)
        return revoked

    def _get_pem_certificate_sha1_digest(self, pem_file):
        """Get SHA1 of DER form of a PEM certificate."""

        import sha
        rv, stdout, stderr = run_command([constants.CMD_OPENSSL, 'x509', '-inform', 'PEM', '-in', pem_file, '-outform', 'DER'], retval=runcommand.FAIL)
        return sha.sha(stdout).digest()
        
    def set_authenticated(self, authenticated):
        self._authenticated = authenticated
        
    def getContext(self):
        # We don't want to cache context because the context (especially validation)
        # may vary from connection to connection
        
        # See:
        #   * http://pyopenssl.sourceforge.net/pyOpenSSL.html/openssl-context.html
        #   * http://dsd.lbl.gov/Akenti/codeDocs/libsrc/SSLConstants.html

        _log.info('creating management connection ssl context')

        ctx = SSL.Context(self.method)
        ctx.set_options(SSL.OP_NO_SSLv2)  # accept SSLv3 but not SSLv2
        ctx.set_info_callback(self._info_callback)
        ctx.set_cipher_list(SSL_CIPHER_LIST)
        # XXX: ctx.set_timeout(...)

        if self._authenticated:
            _log.info('authentication enabled for this management connection')
            ctx.set_verify(SSL.VERIFY_PEER | SSL.VERIFY_FAIL_IF_NO_PEER_CERT, self._verify_callback)
            ctx.set_verify_depth(SSL_CERTIFICATE_CHAIN_VERIFY_DEPTH)
            # XXX: This doesn't do anything useful when we verify certificates ourselves
            # ctx.load_verify_locations(constants.MANAGEMENT_CONNECTION_TRUSTED_CERTIFICATES_FILE)
        else:
            _log.info('authentication disabled for this management connection')
            
        # Load revoked certificates file; note that this is 'cached' and not
        # re-read if it changes on disk.
        if self._revoked is None:
            self._revoked = self._load_revoked()

        # Get trusted certificate hashes
        if self._trusted is None:
            self._trusted = constants.MANAGEMENT_CONNECTION_TRUSTED_CERTIFICATE_DIGESTS

        # Log
        trusted_str = []
        revoked_str = []
        for i in self._trusted:
            trusted_str.append(i.encode('hex'))
        for i in self._revoked:
            revoked_str.append(i.encode('hex'))
        _log.info('loaded certificate data, trusted = [%s], revoked=[%s]' % (','.join(trusted_str), ','.join(revoked_str)))
        
        # Done
        return ctx

    def _X509Name_to_string(self, x509name):
        try:
            return '{C=%s, ST=%s, L=%s, O=%s, OU=%s, CN=%s, email=%s}' % (x509name.countryName,
                                                                          x509name.stateOrProvinceName,
                                                                          x509name.localityName,
                                                                          x509name.organizationName,
                                                                          x509name.organizationalUnitName,
                                                                          x509name.commonName,
                                                                          x509name.emailAddress)
        except:
            _log.exception('_X509Name_to_string failed')
            return '{Invalid X509Name: %s}' % x509name

    def _decode_openssl_sha1_digest(self, digest):
        t = ''
        for ch in digest:
            if ch in '0123456789abcdefABCDEF':
                t += ch
        t = t.lower()
        t = str(t)  # out of unicode, just sanity
        if len(t) != (20*2):
            raise Exception('invalid openssl sha1 digest: %s' % digest)
        return t.decode('hex')
        
    # _verify_callback is called by OpenSSL as part of the certificate chain validation
    # process.  This is not a trivial callback; the validation process is driven by
    # OpenSSL but it only provides error feedback (such as signature check errors) to us
    # as parameters.  It is the responsibility of this function to return False to
    # indicate that we 'cared' about OpenSSL's error info and want to fail the validation.
    # Indeed, the idea is that _verify_callback() can deem a certificate valid despite
    # OpenSSL perceived error.
    #
    # Side-note: if certificate chain is broken, i.e. CA certificate does not match
    # end-entity certificate, OpenSSL callback will only provide us with the end-entity
    # certificate.  Apparently the model is that OpenSSL starts from the end-entity cert
    # (available as the first certificate in the SSL packet) and works its way upwards
    # through properly associated certificates.  Certificates not in the chain are ignored
    # even if they are present in the SSL packet.  Finally, OpenSSL starts from the CA
    # certificate and works its way downwards towards the end-entity certificate, calling
    # verify callback for each certificate.
    #
    # See:
    #  * http://pyopenssl.sourceforge.net/pyOpenSSL.html/openssl-context.html
    #  * http://www.openssl.org/docs/ssl/SSL_CTX_set_verify.html
    #  * /usr/include/openssl/x509_vfy.h  (verify error codes)

    def _verify_callback(self, connection, x509, errno, errdepth, returncode):
        _log.debug('_verify_callback: %s, %s, %s, %s, %s' % (connection, x509, errno, errdepth, returncode))

        verify_result = False
        try:
            # Preprocess the OpenSSL feedback into booleans
            openssl_failure = False
            if errno != 0:
                _log.warning('OpenSSL detected a certificate failure in verify callback: errno=%d, errdepth=%d, rc=%d' % (errno, errdepth, returncode))

                # OpenSSL detected an error; mask errors we don't care about
                if errno in [ OPENSSL_VFY_ERR_CERT_NOT_YET_VALID,
                              OPENSSL_VFY_ERR_CERT_HAS_EXPIRED ]:
                    _log.info('OpenSSL error is about certificate validity period, ignoring')
                    openssl_failure = False
                elif errno in [ OPENSSL_VFY_ERR_CERT_SIGNATURE_FAILURE ]:
                    _log.warning('OpenSSL signature check failed')
                    openssl_failure = True
                elif errno in [ OPENSSL_VFY_ERR_CERT_UNTRUSTED,
                                OPENSSL_VFY_ERR_CERT_REJECTED ]:
                    _log.warning('OpenSSL deems certificate untrusted or rejected')
                    openssl_failure = True
                else:
                    openssl_failure = True
            else:
                openssl_failure = False

            issuer = self._X509Name_to_string(x509.get_issuer())
            subject = self._X509Name_to_string(x509.get_subject())
            digest = x509.digest("SHA1")

            # "digest" is an SHA1 hash of the DER form of the certificate in question.
            # It has the string form 'XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX:XX'
            # where each X is from [0-9A-F].  Decode it to a 20 byte binary string for comparison.
            digest = self._decode_openssl_sha1_digest(digest)

            # NB x509 has a method has_expired() which seems pointless (OpenSSL already
            # checks for it); further, it does not seem to care about notBefore, only notAfter!

            # XXX: why does logger fail for binary digest here?
            _log.info('verifying management connection certificate: issuer=%s, subject=%s, digest=%s' % (issuer, subject, digest.encode('hex')))

            # check whether this is a trust root for us
            is_trust_root = False
            for i in self._trusted:
                _log.debug('checking digest %s against trusted digest %s' % (digest.encode('hex'), i.encode('hex')))
                if digest == i:
                    _log.info('certificate is a trust root')
                    is_trust_root = True
                    break

            # check for our own revocation
            is_revoked = False
            for i in self._revoked:
                _log.debug('checking digest %s against revoked digest %s' % (digest.encode('hex'), i.encode('hex')))
                if digest == i:
                    _log.warning('certificate digest is in the revoked list, rejecting certificate')
                    is_revoked = True
                    break

            # determine final verify result, taking into account our own checks as well as
            # errors provided by OpenSSL
            if is_trust_root and not is_revoked:
                # Trusted roots bypass OpenSSL validation failures
                verify_result = True
            elif openssl_failure:
                # OpenSSL already had an error, so we fail validation for non-trust-roots
                verify_result = False
            elif is_revoked:
                # Revoked, fail validation (OpenSSL doesn't know about our revocation stuff)
                verify_result = False
            else:
                # Both OpenSSL and we are happy with this certificate in the chain
                verify_result = True
        except:
            _log.exception('management connection certificate validation failed, rejecting certificate')
            verity_result = False
            
        if not verify_result:
            _log.warning('verify_callback returning validation failure, dropping connection as a result')

        return verify_result

    # See: http://pyopenssl.sourceforge.net/pyOpenSSL.html/openssl-context.html
    def _info_callback(self, connection, handshakeposition, returncode):
        _log.debug('_info_callback: %s, %s, %s' % (connection, handshakeposition, returncode))
        
# --------------------------------------------------------------------------

class ManagementClientProtocol(amphelpers.LoggingAMP):
    """Manage the state of one management protocol connection.

    Activated when transport (TCP) connection is complete and we want to
    establish a full management connection by running the Version exchange
    followed by the Identify exchange.

    After initial exchanges, handles reidentifying according to license
    parameters (recheckLatestAt), and sends and responds to keepalive
    messages.

    Significant protocol events are relayed to the ManagementConnection
    instance through self.connection.
    """
    
    def __init__(self, connection):
        super(ManagementClientProtocol, self).__init__()
        self.connection = connection      # book-keeping: we ref to connection
        self.connection.protocol = self   # book-keeping: connection refs to us
        self._handshake_complete = False
        self._keepalive_send_call = None
        self._keepalive_wait_call = None
        self._reidentify_call = None
        
    def _cancel_keepalive_timers(self):
        if self._keepalive_send_call is not None:
            self._keepalive_send_call.cancel()
            self._keepalive_send_call = None
        if self._keepalive_wait_call is not None:
            self._keepalive_wait_call.cancel()
            self._keepalive_wait_call = None

    def _cancel_reidentify_timer(self):
        if self._reidentify_call is not None:
            self._reidentify_call.cancel()
            self._reidentify_call = None

    def _send_request_test_license(self):
        # self.disconnect() clears self.connection to None
        if self.connection is None:
            _log.warning('_send_request_test_license: self.connection is None, skipping')
            return

        args = {}
        _log.debug('args for request test license: %s' % args)
        return self.callRemote(managementprotocol.RequestTestLicense)

    def _send_identify(self):
        # self.disconnect() clears self.connection to None
        if self.connection is None:
            _log.warning('_send_identify: self.connection is None, skipping')
            return
        
        args = self.connection.get_identify_args()
        _log.debug('args for identify: %s' % args)

        # override a few arguments since (only) we know them
        addr = self.transport.getHost()
        args = dict(args)  # clone before changing
        args['address'] = str(addr.host)
        args['port'] = int(addr.port)
        args['isPrimary'] = self.connection.primary
        
        return self.callRemote(managementprotocol.Identify4,
                               isPrimary=args['isPrimary'],
                               licenseKey=args['licenseKey'],
                               bootUuid=args['bootUuid'],
                               installationUuid=args['installationUuid'],
                               cookieUuid=args['cookieUuid'],
                               address=args['address'],
                               port=args['port'],
                               softwareVersion=args['softwareVersion'],
                               softwareBuildInfo=args['softwareBuildInfo'],
                               hardwareType=args['hardwareType'],
                               hardwareInfo=args['hardwareInfo'],
                               automaticUpdates=args['automaticUpdates'],
                               isLiveCd=args['isLiveCd'])

    def _send_version(self):
        # self.disconnect() clears self.connection to None
        if self.connection is None:
            _log.warning('_send_version: self.connection is None, skipping')
            return

        args = self.connection.get_version_args()
        _log.debug('args for version: %s' % args)

        return self.callRemote(managementprotocol.Version,
                               version=args['version'],
                               info=args['info'])

    def _schedule_reidentify(self, identify_response, immediate=False): 
        # self.disconnect() clears self.connection to None
        if self.connection is None:
            _log.warning('_schedule_reidentify: self.connection is None, skipping')
            return

        # cancel previous timer
        self._cancel_reidentify_timer()

        # non-primary connection, do not reschedule
        if not self.connection.is_primary():
            _log.debug('non-primary connection, no reidentify')
            return
        
        # compute time difference to recheck
        now = datetime.datetime.utcnow()
        try:
            recheck = identify_response['licenseRecheckLatestAt']
        except:
            _log.exception('failed to get licenseRecheckLatestAt, using current time as fallback')
            recheck = now
        diff = recheck - now

        # cap it: minimum and maximum (also takes care of negative bogus diffs)
        cap_diff = diff
        if cap_diff < constants.MANAGEMENT_PROTOCOL_REIDENTIFY_MINIMUM_TIME:
            cap_diff = constants.MANAGEMENT_PROTOCOL_REIDENTIFY_MINIMUM_TIME
        if cap_diff > constants.MANAGEMENT_PROTOCOL_REIDENTIFY_MAXIMUM_TIME:
            cap_diff = constants.MANAGEMENT_PROTOCOL_REIDENTIFY_MAXIMUM_TIME
        if immediate:
            cap_diff = datetime.timedelta(0, 0, 0)
        _log.debug('reidentify diff before capping: %s, after capping and immediate flag check: %s' % (diff, cap_diff))

        # start a timer
        secs = helpers.timedelta_to_seconds(cap_diff)
        self._reidentify_call = reactor.callLater(secs, self._reidentify_timer)
            
    @db.transact()  # reactor callLater
    def _keepalive_send_timer(self):
        _log.debug('_keepalive_send_timer')
        self._keepalive_send_call = None

        # this is relevant on the first keepalive timer call
        if not self._handshake_complete:
            # First keepalive is executed after one keepalive interval has occurred
            # (currently two minutes).  If handshake is not complete by then, we
            # time out this connection.  (Ideally there would be a separate timer
            # for this, but the keepalive timer will do for now.)
            _log.warning('management connection handshake not complete in keepalive timer, aborting connection')
            self.transport.loseConnection()
            return
        
        @db.transact()
        def _failed_keepalive(x):
            _log.warning('keepalive command command failed: %s' % x)
            # NOTE: timeout will reap us, so we don't need to do anything here

        @db.transact()
        def _do_keepalive(res):
            _log.debug('sending keepalive')
            return self.callRemote(managementprotocol.Keepalive)

        @db.transact()
        def _success_keepalive(res):
            _log.debug('_success_keepalive')
            if self._keepalive_wait_call is not None:
                self._keepalive_wait_call.cancel()
                self._keepalive_wait_call = None
            self._keepalive_send_call = reactor.callLater(constants.MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_INTERVAL,
                                                          self._keepalive_send_timer)

        # schedule a timeout for the keepalive; note that AMP does not have timeouts directly
        self._keepalive_wait_call = reactor.callLater(constants.MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_WAIT,
                                                      self._keepalive_wait_timer)

        # build a deferred for the keepalive process
        d = defer.Deferred()
        d.addCallback(_do_keepalive)
        d.addCallback(_success_keepalive)
        d.addErrback(_failed_keepalive)
        d.callback(None)
        return d

    @db.transact()  # reactor callLater
    def _keepalive_wait_timer(self):
        _log.warning('management connection keepalive timed out, aborting connection')
        self._keepalive_wait_call = None
        self.transport.loseConnection()

    @db.transact()  # reactor callLater
    def _reidentify_timer(self):
        _log.info('reidentify timer expired, reidentifying')
        self._reidentify_call = None
        return self._do_reidentify()
    
    def _do_reidentify(self):
        # XXX: we may be called directly (trigger_reidentify in ManagementConnection),
        # so just in case here
        self._cancel_reidentify_timer()
            
        # NB: Identify errors from servers propagate here
        @db.transact()
        def _failed(reason):
            _log.warning('reidentify failed, dropping connection: %s' % reason)
            self.transport.loseConnection()

        @db.transact()
        def _do_send_identify(res):
            _log.debug('sending identify')
            return self._send_identify()

        @db.transact()
        def _callback(res):
            _log.debug('_callback')
            if self.connection is not None:
                self.connection.reidentify_success(res)
            return res
        
        @db.transact()
        def _do_schedule_reidentify(x):
            _log.debug('_do_reidentify')
            self._schedule_reidentify(x)

        d = defer.Deferred()
        d.addCallback(_do_send_identify)
        d.addCallback(_callback)
        d.addCallback(_do_schedule_reidentify)
        d.addErrback(_failed)
        d.callback(None)
        return d

    # ----------------------------------------------------------------------

    @db.transact()
    def connectionMade(self):
        """connectionMade handler for management protocol client.

        Exchange version and identify requests.  When this sequence is
        complete (without errors), we're ready to do individual requests.
        Also starts keepalives and schedules a reidentify (for primary
        connections).

        Returns a deferred.
        """
        _log.debug('ManagementClientProtocol/connectionMade()')
        _log.debug('management transport connection made, starting handshake')

        @db.transact()
        def _connect_success(result):  # called internally
            _log.debug('ManagementClientProtocol/_connect_success(): result=%s' % result)
            if self.connection is not None:
                self.connection.connect_success(result)

        @db.transact()
        def _connect_fail(reason):     # called internally
            _log.debug('ManagementClientProtocol/_connect_fail()')
            if self.connection is not None:
                self.connection.connect_fail(reason)
            self.transport.loseConnection()

        @db.transact()
        def _do_version(res):
            _log.debug('sending version')
            return self._send_version()

        @db.transact()
        def _do_identify(res):
            _log.debug('sending identify')
            return self._send_identify()

        @db.transact()
        def _management_connection_ready(x):
            _log.info('management connection ready (version and identify completed)')
            _log.debug('identify response: %s' % x)
            self._handshake_complete = True
            _connect_success(x)
            return x

        # NB: Identify errors from servers propagate here; connect_fail() can
        # react to them appropriately
        @db.transact()
        def _failed(x):
            _log.warning('management connection setup failed: %s' % x)
            _connect_fail(x)

        @db.transact()
        def _start_keepalives(x):
            _log.debug('_start_keepalives')

            # We start keepalives even before the handshake.  The keepalive timer
            # handler will first check that the handshake is complete before
            # attempting a keepalive check.  If the handshake is not complete, the
            # connection seems to be stuck and is dropped.  This removes the need
            # for new timers for tracking handshake.  This "workaround" is needed
            # because callRemote() does not have a timeout (at least not a reasonable
            # one).
            self._cancel_keepalive_timers()
            self._keepalive_send_call = reactor.callLater(constants.MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_INTERVAL,
                                                          self._keepalive_send_timer)

        @db.transact()
        def _do_reidentify(x):
            _log.debug('_do_reidentify')
            self._schedule_reidentify(x)

        # build a deferred chain
        d = defer.Deferred()
        d.addCallback(_start_keepalives)  # see notes above
        d.addCallback(_do_version)
        d.addCallback(_do_identify)
        d.addCallback(_management_connection_ready)
        d.addCallback(_do_reidentify)
        d.addErrback(_failed)
        
        # launch defer and return
        d.callback(None)
        return d
            
    @db.transact()
    def connectionLost(self, reason):
        _log.debug('ManagementClientProtocol/connectionLost()')
        self._cancel_keepalive_timers()
        self._cancel_reidentify_timer()
        if self.connection is not None:
            self.connection.disconnected(reason)

    def disconnect(self):
        """ManagementConnection calls this to disconnect protocol.

        ManagementConnection does not want to know about protocol
        after this, so we should not keep a reference to it anymore.
        """
        _log.debug('ManagementClientProtocol/disconnect()')
        self._cancel_keepalive_timers()
        self._cancel_reidentify_timer()
        self.connection = None
        self.transport.loseConnection()

    # ----------------------------------------------------------------------

    @db.transact()
    def server_keepalive(self):
        _log.debug('ManagementClientProtocol/server_keepalive()')
        return {}
    managementprotocol.Keepalive.responder(server_keepalive)

    @db.transact()
    def server_request_reidentify(self, **kw):
        reason = None
        if kw.has_key('reason'):
            reason = kw['reason']
        _log.info('server requested reidentify, reason: %s' % reason)

        # XXX: call the reidentify timer function directly; a zero timeout
        # would be a bit cleaner
        self._cancel_reidentify_timer()
        ign = self._reidentify_timer()
        return {}
    managementprotocol.RequestReidentify.responder(server_request_reidentify)
    
# --------------------------------------------------------------------------

# XXX: perhaps resolve DNS names via custom resolver to enable proper
# round-robin or similar.
class ManagementClientReconnectingProtocolFactory(protocol.ReconnectingClientFactory):
    """Factory class for a reconnecting protocol client."""

    protocol = ManagementClientProtocol

    # XXX: these backoff values are reasonable but should be in constants.py
    maxDelay = 5*60
    initialDelay = 3.0
    factor = 1.5
    jitter = 0.2
    continueTrying = 1
    maxRetries = None

    def __init__(self, connection):
        # NB: no __init__ in protocol and not a new-style class, do
        # not call parent __init__
        self.connection = connection

    def buildProtocol(self, addr):
        return ManagementClientProtocol(self.connection)

    @db.transact()
    def startedConnecting(self, connector):
        _log.debug('ManagementClientReconnectingProtocolFactory/startedConnecting()')
        # This is done to ensure that we can stop and restart
        # even when initial connection is being established
        self.connector = connector
        return protocol.ReconnectingClientFactory.startedConnecting(self, connector)

    @db.transact()
    def clientConnectionLost(self, connector, reason):
        _log.debug('ManagementClientReconnectingProtocolFactory/clientConnectionLost()')
        return protocol.ReconnectingClientFactory.clientConnectionLost(self, connector, reason)
    
    @db.transact()
    def clientConnectionFailed(self, connector, reason):
        _log.debug('ManagementClientReconnectingProtocolFactory/clientConnectionFailed()')
        self.connection.connect_fail(reason)
        return protocol.ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)

    def disconnect(self):  # called by ManagementConnection
        _log.debug('ManagementClientReconnectingProtocolFactory/disconnect()')
        self.stopTrying()
        
# --------------------------------------------------------------------------

class ManagementClientProtocolFactory(protocol.ClientFactory):
    """Factory class for a non-reconnecting protocol client."""
    
    def __init__(self, connection):
        self.connection = connection
        self.connector = None

    def buildProtocol(self, addr):
        return ManagementClientProtocol(self.connection)

    def disconnect(self):  # called by ManagementConnection
        _log.debug('ManagementClientProtocolFactory/disconnect()')
        if self.connector:
            try:
                self.connector.stopConnecting()
            except error.NotConnectingError:
                pass
            self.connector = None

    @db.transact()
    def startedConnecting(self, connector):
        _log.debug('ManagementClientProtocolFactory/startedConnecting()')
        self.connector = connector

    @db.transact()
    def clientConnectionLost(self, connector, reason):
        _log.debug('ManagementClientProtocolFactory/clientConnectionLost()')
        
    
    @db.transact()
    def clientConnnectionFailed(self, connector, reason):
        _log.debug('ManagementClientProtocolFactory/clientConnectionFailed()')
        self.connection.connect_fail(reason)

    def resetDelay(self):
        """To keep compatibility with ReconnectingClientFactory"""
        pass
    
# --------------------------------------------------------------------------

class ManagementConnection:
    """Management connection wrapper class.

    Provides a narrow interface for starting, stopping, and interacting
    with the management protocol.  Reconnections and other such issues
    are handled internally.

    Assumes a "master" object with certain callbacks called in relevant
    situations (see codebay.l2tpserver.webui.master).  Particularly important are:
      * management_connection_up() - called when the management connection
        has a successful TCP connection, and has exchanged Version and
        Identify commands.  Gets Identify response as an argument.
      * management_connection_down() - called when the management connection
        is closed down (disconnected) normally, or when connecting failed.
        Gets a reason as parameter.

    XXX: management_connection_down() gets a reason parameter, which can
    currently take many forms: a string, an Exception, or a Twisted
    Failure.  This is probably not good from an API viewpoint.

    XXX: ManagementConnection has a concept of primary and non-primary
    connections, but currently only primary connections are used.
    """
      
    STATE_IDLE = 'IDLE'
    STATE_CONNECTING = 'CONNECTING'
    STATE_CONNECTED = 'CONNECTED'
    
    def __init__(self, cb_version_args, cb_identify_args, master=None):
        self.state = self.STATE_IDLE
        self.master = master
        self.factory = None
        self.protocol = None
        self.primary = False
        self.authenticate = False
        self.connectWaiters = []
        self.cb_version_args = cb_version_args    # callbacks for filling requests
        self.cb_identify_args = cb_identify_args

    def connect(self):
        _log.debug('ManagementConnection/connect() [primary=%s]' % self.primary)
        if self.state == self.STATE_IDLE:
            self.state = self.STATE_CONNECTING
            if self.primary:
                self.factory = ManagementClientReconnectingProtocolFactory(self)
            else:
                self.factory = ManagementClientProtocolFactory(self)

            # XXX: there is no timeout control here

            # Client context factory, need subclassing to get TLS 1.0 (SSL 3.1)
            # instead of default SSL 3.0.
            cf = ManagementConnectionSslContextFactory()
            if self.authenticate:
                cf.set_authenticated(True)
                
            reactor.connectSSL(SERVER_ADDRESS, SERVER_PORT, self.factory, cf)

    def connect_wait(self):
        _log.debug('ManagementConnection/connect_wait()')
        if self.state == self.STATE_CONNECTED:
            # XXX: identify response is given here as None to caller;
            # caller should either avoid making this call or handle the
            # None result correctly (interpret it as "already connected").
            # Alternatively we could cache the identify result and give
            # the previous result to the caller from the cache.
            return defer.succeed(None)
        d = defer.Deferred()
        self.connectWaiters.append(d)
        self.connect()
        return d

    def set_authenticated(self, authenticate):
        self.authenticate = authenticate
        
    # XXX: we would want to wait until TCP FIN has been completed here;
    # we'll be taking the network connection down and we don't want to
    # burden the server with hanging connections.  How to do that?
    # Current answer: not in any reasonable way...

    def disconnect(self):
        _log.debug('ManagementConnection/disconnect()')
        if self.factory is not None:
            self.factory.disconnect()
        if self.protocol is not None:
            self.protocol.disconnect()
        self.disconnected(Exception('user requested disconnect'))

    def start_primary(self, authenticate=False):
        _log.debug('ManagementConnection/start_primary()')
        self.primary = True
        self.authenticate = authenticate
        self.connect()

    def stop_primary(self):
        _log.debug('ManagementConnection/stop_primary()')
        self.primary = False
        self.authenticate = False
        self.disconnect()

        # XXX: there is no management_connection_down() callback when
        # stop_primary() is called, because disconnect() will set
        # connection = None in the protocol -- is this OK (from an API
        # viewpoint)?

    def trigger_reidentify(self):
        # XXX: direct call, add indirection?
        return self.protocol._do_reidentify()
        
    def request_test_license(self):
        # XXX: direct call, add indirection? state check?
        d = self.protocol._send_request_test_license()
        return d
        
    def is_primary(self):
        return self.primary
    
    def is_active(self):
        return self.state == self.STATE_CONNECTED
        

    # --- internal ---

    def connect_success(self, result):       # called by protocol
        _log.debug('ManagementConnection/connect_success()')
        self.state = self.STATE_CONNECTED

        # Reset reconnection back-off delay once we're satisfied; this must called
        # late because we don't want to hammer if e.g. version or identify exchange
        # systematically fails.
        self.factory.resetDelay()

        # make a copy of waiters first to avoid clobbering the list while iterating it
        waiters, self.connectWaiters = self.connectWaiters, []
        for w in waiters:
            w.callback(result)

        if self.master is not None:
            self.master.management_connection_up(result)

    def connect_fail(self, reason):  # called by protocol
        _log.debug('ManagementConnection/connected_fail()')

        if not self.primary:
            self.factory = None
        self.protocol = None
        self.state = self.STATE_IDLE

        # make a copy of waiters first to avoid clobbering the list while iterating it
        waiters, self.connectWaiters = self.connectWaiters, []
        for w in waiters:
            w.errback(reason)

        # NB: identify errors come here in 'reason', so call receiver
        # can react to the result there
        if self.master is not None:
            self.master.management_connection_down(reason)

    def reidentify_success(self, result):  # called by protocol
        _log.debug('ManagementConnection/reidentify_success()')

        if self.master is not None:
            self.master.management_connection_reidentify(result)
        
    def disconnected(self, reason):  # called by protocol
        _log.debug('ManagementConnection/disconnected()')
        if not self.primary:
            self.factory = None
        self.protocol = None
        self.state = self.STATE_IDLE

        waiters, self.connectWaiters = self.connectWaiters, []
        for w in waiters:
            w.errback(reason)

        if self.master is not None:
            self.master.management_connection_down(reason)

    def get_version_args(self):
        return self.cb_version_args()

    def get_identify_args(self):
        return self.cb_identify_args()
