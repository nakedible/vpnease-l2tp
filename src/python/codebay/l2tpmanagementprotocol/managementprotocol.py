"""
L2TP management protocol.

Commands are all given in CamelCase to match with Python code using
the commands.  Command arguments are likewise given in camelCase but
starting with lowercase characters.
"""
__docformat__ = 'epytext en'

import re, datetime

from codebay.common import twisted_amp as amp

PROTOCOL_VERSION = 4


class UtcDateTime(amp.Argument):
    """UTC datetime argument type for AMP.

    Represented locally as a datetime.datetime, on-the-wire in ISO format.
    Modelled after codebay.common.rdf.Datetime.
    """

    DATETIME_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z')

    def fromString(self, inString):
        m = self.DATETIME_RE.match(inString)
        if not m:
            raise TypeError('Bad UtcDateTime value: %s' % inString)
        try:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            hour = int(m.group(4))
            minute = int(m.group(5))
            second = int(m.group(6))
            if m.group(7) is not None:
                microsecond = int((m.group(7)+'000000')[:6])
            else:
                microsecond = 0
        except ValueError:
            raise TypeError('Bad UtcDateTime value: %s' % inString)
        return datetime.datetime(year, month, day, hour, minute, second, microsecond)

    def toString(self, inObject):
        """Convert UtcDateTime to protocol string.

        Only naive timestamps can be converted (and they are interpreted as UTC).
        """
        if isinstance(inObject, datetime.datetime):
            if inObject.tzinfo is not None:
                raise TypeError('Cannot convert to UtcDateTime from non-naive %s' % repr(inObject))
            return '%sZ' % inObject.isoformat()
        else:
            raise TypeError('Cannot convert to UtcDateTime from %s' % repr(inObject))


class ManagementProtocolError(Exception):
    """Base class for management protocol errors.

    Errors are translated to Python exceptions, but are transmitted on the wire.
    Hence these cannot be altered without caution.
    """

class UnsupportedProtocolVersionError(ManagementProtocolError):
    """Management protocol incompatible."""

class InternalServerError(ManagementProtocolError):
    """Internal server error."""
        
class ProtocolStateError(ManagementProtocolError):
    """Request is invalid in current protocol state."""
    
class LicenseError(ManagementProtocolError):
    """License (key) is invalid."""
        
class InvalidLicenseError(LicenseError):
    """License (key) is invalid, because it cannot be parsed correctly."""

class UnknownLicenseError(LicenseError):
    """License (key) is syntactically valid, but unknown."""

class TestLicenseDeniedError(LicenseError):
    """Request for test license has been denied by server."""


class Version(amp.Command):
    """Identifies protocol version of server and client.

    Client initiates by sending its protocol version (just a running integer).
    If server accepts the version, that protocol version will be used throughout
    the protocol after this exchange.  Note that there is no version negotiation:
    the server either understands or doesn't understand the client version; all
    flexibility is in the server.

    The 'info' strings exchanged are intended to contain software version, build,
    debug/release and other such identifying information.  It could contain, for
    instance, 'vpnease server 1.2.3 rev 12345, built on dapper-builder2 <date>'.
    The info string allows one to identify the client software, should something
    go wrong in the protocol initiation.
    """
    arguments = [('version', amp.Integer()),
                 ('info', amp.Unicode())]

    response = [('info', amp.Unicode())]

    fatalErrors = {UnsupportedProtocolVersionError: 'UnsupportedProtocolVersionError'}

    
class Keepalive(amp.Command):
    """Keepalive requests can be sent by either party at any time after
    the initial Version exchange.

    Since both parties keepalive independently, each party can use the
    interval most appropriate for itself.  Note that keepalives must not
    be resent: TCP takes care of that.

    There are no arguments or response values.
    """
    
    arguments = []

    response = []


class Identify(amp.Command):
    """The Identify command performs several core managements functions in
    the VPNease product.

    If the license key is known to the management server, the connection will
    be associated with the license key and related rights after a successful
    Identify command.  In practice, 'authenticated' commands require a license
    key.  It is possible to distinguish rights associated with a particular
    license key in a more fine grained manner, too.

    Note that all data in the identify is conceptually available to all later
    commands.  For instance, RequestTestLicense() may verify that the same
    installation UUID not be granted two test licenses, etc.  (Whether the data
    is actually copied to any state variables is an implementation matter.)

    License information is always returned, unless the license is
    unparseable. License status will signify whether the license was
    actually accepted.

    A note about validity:
      * licenseValidityStart and licenseValidityEnd are the effective validity
        parameters that a server must obey.  This interval of validity is not
        usually related in any way to the validity of the actual product license
        purchased by the subscriber.  For instance, if the subscriber's license
        is to the end of year 2007, licenseValidityEnd is still typically ~1 week
        from current time until the end of the year is reached.  The intent of
        this validity period is to specify the time during which product license
        can be assumed valid without further checking.

      * For demo licenses, demo validity start and end indicate how the demo
        will last and are 'non-changing': each request should yield the same
        values.  These values allow a gateway to compute demo license expiry
        time for instance ("7 days left").  This information is for display
        purposes only.  The actual service provided by the product should still
        follow licenseValidityStart and licenseValidityEnd.

    """
    
    arguments = [('isPrimary', amp.Boolean()),                                  # primary or non-primary connection
                 ('licenseKey', amp.Unicode()),                                 # e.g. 'AAAAT-ABJ3H-J89W3-YMCMW-XL7VF'
                 ('bootUuid', amp.Unicode()),                                   # e.g. 'e123c692-1b52-48f3-8d53-7325d6bbacb9'
                 ('installationUuid', amp.Unicode()),                           # e.g. '263ac363-6fd5-4065-839e-f8c007c5a4bb'
                 ('address', amp.Unicode()),                                    # e.g. '10.0.0.1', as seen by l2tp server
                 ('port', amp.Integer()),                                       # e.g. 12345, as seen by l2tp server
                 ('softwareVersion', amp.Unicode()),                            # processable, <major>.<minor>.<revision> (%d.%d.%d)
                 ('softwareBuildInfo', amp.Unicode()),                          # freeform
                 ('hardwareType', amp.Unicode()),                               # XXX: currently unused
                 ('hardwareInfo', amp.Unicode()),                               # freeform (memory, macs, etc)
                 ('automaticUpdates', amp.Boolean()),                           # True if admin elected for automatic updates
                 ('isLiveCd', amp.Boolean())]                                   # True if Live CD environment, False if installed

    response = [('softwareBuildInfo', amp.Unicode()),                           # freeform server build info
                ('serverInfo', amp.Unicode()),                                  # freeform to identify a particular server
                ('licenseMaxRemoteAccessConnections', amp.Integer()),           # max # concurrent client connections
                ('licenseMaxSiteToSiteConnections', amp.Integer()),             # max # site-to-site mode connections (client or server)
                ('licenseValidityStart', UtcDateTime()),                        # license invalid before (stop working, recheck); normative
                ('licenseValidityEnd', UtcDateTime()),                          # license invalid after (stop working, recheck); normative
                ('licenseRecheckLatestAt', UtcDateTime()),                      # license valid, but start rechecking asap at this point
                ('licenseString', amp.Unicode()),                               # show in UI, set by subscription admin
                ('licenseStatus', amp.Unicode()),                               # license status: VALID / DISABLED / UNKNOWN
                ('isDemoLicense', amp.Boolean()),                               # is demo license?
                ('demoValidityStart', UtcDateTime()),                           # demo validity start; informative
                ('demoValidityEnd', UtcDateTime()),                             # demo validity end (allows computation of expiry); informative
                ('currentUtcTime', UtcDateTime()),                              # server timestamp (time response was sent) for rough sync
                ('updateAvailable', amp.Boolean()),                             # based on software-version; informative
                ('updateNeeded', amp.Boolean()),                                # if True, client must update; normative
                ('updateImmediately', amp.Boolean()),                           # if True, client must check for updates immediately; normative
                ('updateForced', amp.Boolean()),                                # update forced (regardless of 'automatic-updates'); informative
                ('aptSourcesList', amp.Unicode()),                              # apt sources.list; ignore unless updateNeeded = True!
                ('repositoryKeys', amp.Unicode()),                              # repository keys in ASCII encoded format
                ('changeLog', amp.Unicode())]                                   # changelog of vpnease package

    errors = {InvalidLicenseError: 'InvalidLicenseError'}

class Identify2(amp.Command):
    """The Identify command performs several core managements functions in
    the VPNease product.

    This is a revised Identify with some additions for VPNease 1.1.
    """
    
    arguments = [('isPrimary', amp.Boolean()),                                  # primary or non-primary connection
                 ('licenseKey', amp.Unicode()),                                 # e.g. 'AAAAT-ABJ3H-J89W3-YMCMW-XL7VF'
                 ('bootUuid', amp.Unicode()),                                   # e.g. 'e123c692-1b52-48f3-8d53-7325d6bbacb9'
                 ('installationUuid', amp.Unicode()),                           # e.g. '263ac363-6fd5-4065-839e-f8c007c5a4bb'
                 ('cookieUuid', amp.Unicode()),                                 # e.g. '254434fd-63df-4736-a8dc-0d96d3daf0d1'
                 ('address', amp.Unicode()),                                    # e.g. '10.0.0.1', as seen by l2tp server
                 ('port', amp.Integer()),                                       # e.g. 12345, as seen by l2tp server
                 ('softwareVersion', amp.Unicode()),                            # processable, <major>.<minor>.<revision> (%d.%d.%d)
                 ('softwareBuildInfo', amp.Unicode()),                          # freeform
                 ('hardwareType', amp.Unicode()),                               # XXX: currently unused
                 ('hardwareInfo', amp.Unicode()),                               # freeform (memory, macs, etc)
                 ('automaticUpdates', amp.Boolean()),                           # True if admin elected for automatic updates
                 ('isLiveCd', amp.Boolean())]                                   # True if Live CD environment, False if installed

    response = [('softwareBuildInfo', amp.Unicode()),                           # freeform server build info
                ('serverInfo', amp.Unicode()),                                  # freeform to identify a particular server
                ('cookieUuid', amp.Unicode()),                                  # cookie UUID to be stored and used in later Identify2
                ('licenseMaxRemoteAccessConnections', amp.Integer()),           # max # concurrent client connections
                ('licenseMaxSiteToSiteConnections', amp.Integer()),             # max # site-to-site mode connections (client or server)
                ('licenseValidityStart', UtcDateTime()),                        # license invalid before (stop working, recheck); normative
                ('licenseValidityEnd', UtcDateTime()),                          # license invalid after (stop working, recheck); normative
                ('licenseRecheckLatestAt', UtcDateTime()),                      # license valid, but start rechecking asap at this point
                ('licenseString', amp.Unicode()),                               # show in UI, set by subscription admin
                ('licenseStatus', amp.Unicode()),                               # license status: VALID / DISABLED / UNKNOWN
                ('isDemoLicense', amp.Boolean()),                               # is demo license?
                ('demoValidityStart', UtcDateTime()),                           # demo validity start; informative
                ('demoValidityEnd', UtcDateTime()),                             # demo validity end (allows computation of expiry); informative
                ('currentUtcTime', UtcDateTime()),                              # server timestamp (time response was sent) for rough sync
                ('updateAvailable', amp.Boolean()),                             # based on software-version; informative
                ('updateNeeded', amp.Boolean()),                                # if True, client must update; normative
                ('updateImmediately', amp.Boolean()),                           # if True, client must check for updates immediately; normative
                ('updateForced', amp.Boolean()),                                # update forced (regardless of 'automatic-updates'); informative
                ('aptSourcesList', amp.Unicode()),                              # apt sources.list; ignore unless updateNeeded = True!
                ('repositoryKeys', amp.Unicode()),                              # repository keys in ASCII encoded format
                ('changeLog', amp.Unicode())]                                   # changelog of vpnease package

    errors = {InvalidLicenseError: 'InvalidLicenseError'}

class Identify3(amp.Command):
    """The Identify command performs several core managements functions in
    the VPNease product.

    This is a revised Identify with some additions for VPNease 1.1.
    """
    
    arguments = [('isPrimary', amp.Boolean()),                                  # primary or non-primary connection
                 ('licenseKey', amp.Unicode()),                                 # e.g. 'AAAAT-ABJ3H-J89W3-YMCMW-XL7VF'
                 ('bootUuid', amp.Unicode()),                                   # e.g. 'e123c692-1b52-48f3-8d53-7325d6bbacb9'
                 ('installationUuid', amp.Unicode()),                           # e.g. '263ac363-6fd5-4065-839e-f8c007c5a4bb'
                 ('cookieUuid', amp.Unicode()),                                 # e.g. '254434fd-63df-4736-a8dc-0d96d3daf0d1'
                 ('address', amp.Unicode()),                                    # e.g. '10.0.0.1', as seen by l2tp server
                 ('port', amp.Integer()),                                       # e.g. 12345, as seen by l2tp server
                 ('softwareVersion', amp.Unicode()),                            # processable, <major>.<minor>.<revision> (%d.%d.%d)
                 ('softwareBuildInfo', amp.Unicode()),                          # freeform
                 ('hardwareType', amp.Unicode()),                               # XXX: currently unused
                 ('hardwareInfo', amp.Unicode()),                               # freeform (memory, macs, etc)
                 ('automaticUpdates', amp.Boolean()),                           # True if admin elected for automatic updates
                 ('isLiveCd', amp.Boolean())]                                   # True if Live CD environment, False if installed

    response = [('softwareBuildInfo', amp.Unicode()),                           # freeform server build info
                ('serverInfo', amp.Unicode()),                                  # freeform to identify a particular server
                ('cookieUuid', amp.Unicode()),                                  # cookie UUID to be stored and used in later Identify2
                ('clientAddressSeenByServer', amp.Unicode()),                   # client address as seen by management server (Identify3)
                ('clientPortSeenByServer', amp.Integer()),                      # client port as seen by management server    (Identify3)
                ('behindNat', amp.Boolean()),                                   # client seems to be behind a NAT device      (Identify3)
                ('licenseMaxRemoteAccessConnections', amp.Integer()),           # max # concurrent client connections
                ('licenseMaxSiteToSiteConnections', amp.Integer()),             # max # site-to-site mode connections (client or server)
                ('licenseValidityStart', UtcDateTime()),                        # license invalid before (stop working, recheck); normative
                ('licenseValidityEnd', UtcDateTime()),                          # license invalid after (stop working, recheck); normative
                ('licenseRecheckLatestAt', UtcDateTime()),                      # license valid, but start rechecking asap at this point
                ('licenseString', amp.Unicode()),                               # show in UI, set by subscription admin
                ('licenseStatus', amp.Unicode()),                               # license status: VALID / DISABLED / UNKNOWN
                ('isDemoLicense', amp.Boolean()),                               # is demo license?
                ('demoValidityStart', UtcDateTime()),                           # demo validity start; informative
                ('demoValidityEnd', UtcDateTime()),                             # demo validity end (allows computation of expiry); informative
                ('currentUtcTime', UtcDateTime()),                              # server timestamp (time response was sent) for rough sync
                ('updateAvailable', amp.Boolean()),                             # based on software-version; informative
                ('updateNeeded', amp.Boolean()),                                # if True, client must update; normative
                ('updateImmediately', amp.Boolean()),                           # if True, client must check for updates immediately; normative
                ('updateForced', amp.Boolean()),                                # update forced (regardless of 'automatic-updates'); informative
                ('aptSourcesList', amp.Unicode()),                              # apt sources.list; ignore unless updateNeeded = True!
                ('repositoryKeys', amp.Unicode()),                              # repository keys in ASCII encoded format
                ('changeLog', amp.Unicode())]                                   # changelog of vpnease package

    errors = {InvalidLicenseError: 'InvalidLicenseError'}


class Identify4(amp.Command):
    """The Identify command performs several core managements functions in
    the VPNease product.

    This is a revised Identify for VPNEase 1.2, no changes yet but a separate
    name was allocated because protocol version was bumped for CA key rollover
    anyway.
    """
    
    arguments = [('isPrimary', amp.Boolean()),                                  # primary or non-primary connection
                 ('licenseKey', amp.Unicode()),                                 # e.g. 'AAAAT-ABJ3H-J89W3-YMCMW-XL7VF'
                 ('bootUuid', amp.Unicode()),                                   # e.g. 'e123c692-1b52-48f3-8d53-7325d6bbacb9'
                 ('installationUuid', amp.Unicode()),                           # e.g. '263ac363-6fd5-4065-839e-f8c007c5a4bb'
                 ('cookieUuid', amp.Unicode()),                                 # e.g. '254434fd-63df-4736-a8dc-0d96d3daf0d1'
                 ('address', amp.Unicode()),                                    # e.g. '10.0.0.1', as seen by l2tp server
                 ('port', amp.Integer()),                                       # e.g. 12345, as seen by l2tp server
                 ('softwareVersion', amp.Unicode()),                            # processable, <major>.<minor>.<revision> (%d.%d.%d)
                 ('softwareBuildInfo', amp.Unicode()),                          # freeform
                 ('hardwareType', amp.Unicode()),                               # XXX: currently unused
                 ('hardwareInfo', amp.Unicode()),                               # freeform (memory, macs, etc)
                 ('automaticUpdates', amp.Boolean()),                           # True if admin elected for automatic updates
                 ('isLiveCd', amp.Boolean())]                                   # True if Live CD environment, False if installed

    response = [('softwareBuildInfo', amp.Unicode()),                           # freeform server build info
                ('serverInfo', amp.Unicode()),                                  # freeform to identify a particular server
                ('cookieUuid', amp.Unicode()),                                  # cookie UUID to be stored and used in later Identify2
                ('clientAddressSeenByServer', amp.Unicode()),                   # client address as seen by management server (Identify3)
                ('clientPortSeenByServer', amp.Integer()),                      # client port as seen by management server    (Identify3)
                ('behindNat', amp.Boolean()),                                   # client seems to be behind a NAT device      (Identify3)
                ('licenseMaxRemoteAccessConnections', amp.Integer()),           # max # concurrent client connections
                ('licenseMaxSiteToSiteConnections', amp.Integer()),             # max # site-to-site mode connections (client or server)
                ('licenseValidityStart', UtcDateTime()),                        # license invalid before (stop working, recheck); normative
                ('licenseValidityEnd', UtcDateTime()),                          # license invalid after (stop working, recheck); normative
                ('licenseRecheckLatestAt', UtcDateTime()),                      # license valid, but start rechecking asap at this point
                ('licenseString', amp.Unicode()),                               # show in UI, set by subscription admin
                ('licenseStatus', amp.Unicode()),                               # license status: VALID / DISABLED / UNKNOWN
                ('isDemoLicense', amp.Boolean()),                               # is demo license?
                ('demoValidityStart', UtcDateTime()),                           # demo validity start; informative
                ('demoValidityEnd', UtcDateTime()),                             # demo validity end (allows computation of expiry); informative
                ('currentUtcTime', UtcDateTime()),                              # server timestamp (time response was sent) for rough sync
                ('updateAvailable', amp.Boolean()),                             # based on software-version; informative
                ('updateNeeded', amp.Boolean()),                                # if True, client must update; normative
                ('updateImmediately', amp.Boolean()),                           # if True, client must check for updates immediately; normative
                ('updateForced', amp.Boolean()),                                # update forced (regardless of 'automatic-updates'); informative
                ('aptSourcesList', amp.Unicode()),                              # apt sources.list; ignore unless updateNeeded = True!
                ('repositoryKeys', amp.Unicode()),                              # repository keys in ASCII encoded format
                ('changeLog', amp.Unicode())]                                   # changelog of vpnease package

    errors = {InvalidLicenseError: 'InvalidLicenseError'}


class RequestReidentify(amp.Command):
    """Server requests a reidentify ASAP."""
    
    arguments = [('reason', amp.Unicode())]       # freeform string to explain reason for reidentify (for logging)

    response = []


class RequestTestLicense(amp.Command):
    """Request a test license.

    Requires that an Identify exchange has been run, resulting in at least
    an anonymous state.  Installation UUID in the session state must be set,
    as the server uses the installation UUID as part of deciding what test
    license to give.
    """
    
    arguments = []

    response = [('licenseKey', amp.Unicode())]

    errors = {TestLicenseDeniedError: 'TestLicenseDeniedError'}


class ServerEvent(amp.Command):
    # XXX: 'installation-finished', 'startup-finished', 'shutting-down', 'watchdog-action'
    # XXX, not possible?  'installation-media-booted'
    arguments = []

    response = []


#
#  XXX: this won't work without some file transfer feature, as the 64k
#  limit will bite us in the ankle.
#
class CustomerFeedback(amp.Command):
    """Bug report, enhancement suggestion, etc."""
    arguments = []
    
    response = []


class ConnectivityTest(amp.Command):
    """Connectivity test."""

    # Test client/server mode connectivity for UDP:500/4500, TCP/80, TCP/443, ICMP
    # Also test MTU
    # Dealing with IDN domain names - either (a) send in Unicode, or (b) send in ACE format
    arguments = []
    
    response = []
