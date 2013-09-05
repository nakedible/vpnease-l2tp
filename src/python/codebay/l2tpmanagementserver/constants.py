"""Various management server related constants.

@var CONFIG_FILE:
    Windows INI file like config file.
@var SERVER_ADDRESS:
    Our IP address.
@var SERVER_PORT:
    Out SSL/TLS port.
@var REPOSITORY_KEYS_FILE:
    File containing repository keys, delivered to clients.
@var LICENSE_MAX_VALIDITY:
    Maximum (temporary) validity period delivered to clients.  Note that this is not
    the validity period of the purchased license; instead, this is the validity time
    that a VPNease server may use without getting an update from the management server.
@var LICENSE_MIN_VALIDITY:
    FIXME: needed?
@var LICENSE_RECHECK_DEFAULT:
    Time from current time at which the management server should recheck the validity
    of its license.  This constant is applied in 'normal' cases, while LICENSE_RECHECK_QUICK
    is applied in exceptional cases.
@var LICENSE_RECHECK_QUICK:
    Like LICENSE_RECHECK_DEFAULT, but applied in exceptional situations to ensure that the
    VPNease server will get timely update on its license parameters.
@var LICENSE_VALIDITY_START_LEEWAY:
    Timedelta subtracted from final calculated validity start to ensure minor time differences
    (in the order of an hour) do not change validity determination.
@var LICENSE_VALIDITY_END_LEEWAY:
    Timedelta added to final calculated validityend to ensure minor time differences
    (in the order of an hour) do not change validity determination.
@var DEMO_LICENSE_TIME:
    Timedelta describing how long a demo license is valid from grant time.
@var DEMO_LICENSE_USER_COUNT:
    Number of user connections in a demo license.
@var DEMO_LICENSE_SITE_TO_SITE_COUNT:
    Number of site-to-site connections in a demo license.
@var CONNECTION_INFO_FILE:
    File to write with connection info.
@var SERVER_VERSION_INFO_STRING:
    Info string sent by server in Version exchange.
@var SERVER_IDENTIFY_SOFTWARE_BUILD_INFO:
    Software build info string sent by server in Identify exchange.
@var SERVER_IDENTIFY_SERVER_INFO:
    Server info string sent by server in Identify exchange.
@var MASTER_CHECK_INTERVAL:
    Interval for status summary logging.
@var KEEPALIVE_INTERVAL:
    Server keepalive interval.
@var KEEPALIVE_TIMEOUT:
    Server keepalive timeout.
"""
__docformat__ = 'epytext en'

import datetime

CONFIG_FILE = '/etc/managementserver.conf'

# FIXME: where-to?
SERVER_ADDRESS = '0.0.0.0'
SERVER_PORT = 443

SERVER_PRIVATE_KEY1 = '/var/lib/vpnease-management-server-private-key-1.pem'
SERVER_CERTIFICATE1 = '/var/lib/vpnease-management-server-certificate-1.pem'
VPNEASE_CA_CERTIFICATE1 = '/var/lib/vpnease-ca-certificate-1.pem'
SERVER_PRIVATE_KEY2 = '/var/lib/vpnease-management-server-private-key-2.pem'
SERVER_CERTIFICATE2 = '/var/lib/vpnease-management-server-certificate-2.pem'
VPNEASE_CA_CERTIFICATE2 = '/var/lib/vpnease-ca-certificate-2.pem'

# Note: order is important here!
_APT_SOURCES_LIST_1_0 = """\
deb http://packages.vpnease.com/vpnease/1.0 dapper main
deb http://packages.vpnease.com/ubuntu/1.0 dapper main restricted
"""
_APT_SOURCES_LIST_1_1 = """\
deb http://packages.vpnease.com/vpnease/1.1 dapper main
deb http://packages.vpnease.com/ubuntu/1.1 dapper main restricted
"""
_APT_SOURCES_LIST_1_2 = """\
deb http://packages.vpnease.com/vpnease/1.2 dapper main
deb http://packages.vpnease.com/ubuntu/1.2 dapper main restricted
"""

# serve by default
STABLE_APT_SOURCES_LIST = _APT_SOURCES_LIST_1_1

# serve to "beta" servers
UNSTABLE_APT_SOURCES_LIST = _APT_SOURCES_LIST_1_2

REPOSITORY_KEYS_FILE = '/usr/lib/vpnease-management/repository-keys.txt'

LICENSE_CSV_FILE = '/var/lib/vpnease-licenses.csv'  # oocalc utf-8 csv save

LICENSE_MAX_VALIDITY = datetime.timedelta(0, 7*24*60*60, 0)        # FIXME: 7 days
LICENSE_MIN_VALIDITY = datetime.timedelta(0, 3*24*60*60, 0)        # FIXME: 3 days
LICENSE_RECHECK_DEFAULT = datetime.timedelta(0, 8*60*60, 0)        # FIXME: 8 hours
LICENSE_RECHECK_QUICK = datetime.timedelta(0, 1*60*60, 0)          # FIXME: hourly
LICENSE_VALIDITY_START_LEEWAY = datetime.timedelta(7, 0, 0)        # FIXME: 1 week backwards leeway
LICENSE_VALIDITY_END_LEEWAY = datetime.timedelta(1, 0, 0)          # FIXME: 1 day forwards leeway

DEMO_LICENSE_DIRECTORY = '/root/demolicenses'
DEMO_LICENSE_TIME = datetime.timedelta(30, 15*60, 0)  # extra 15min for prettier server status page (start count from 30d 0h)
DEMO_LICENSE_USER_COUNT = 10
DEMO_LICENSE_SITE_TO_SITE_COUNT = 10

CONNECTION_INFO_FILE = '/tmp/connections.txt'

SERVER_VERSION_INFO_STRING = u'VPNease Management Server'
SERVER_IDENTIFY_SOFTWARE_BUILD_INFO = u''
SERVER_IDENTIFY_SERVER_INFO = u'%s:%s' % (SERVER_ADDRESS, SERVER_PORT)

MASTER_CHECK_INTERVAL = 5*60

KEEPALIVE_INTERVAL = 5*60
KEEPALIVE_TIMEOUT = 30

