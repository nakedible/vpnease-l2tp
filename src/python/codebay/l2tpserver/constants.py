"""Various L2TP related constants.

@var DHCP_POLL_INTERVAL:
    DHCP status file polling interval in seconds.
@var DHCP_TRY_COUNT:
    How many times allow waiting for DHCP address initially before
    giving up.
@var SIGALRM_TIMEOUT_MAIN:
    Timeout in main loop in ready state (no action yet).
@var LICENSE_PPP_IGNORE_IDLE_INTERVAL:
    When to consider a PPP device to be "dead" and ignored for license
    control.  If this interval passes without user traffic in *both*
    directions (both inbound and outbound packets during the period),
    the device is considered dead.
@var LICENSE_CONNECTION_LEEWAY:
    How many extra PPP devices to allow beyond license limit to ensure
    all legitimate connections are served.  Given as a floating point
    multiplier: 0.05 -> 5%.  License limit is multiplied by (1.00 +
    LICENSE_CONNECTION_LEEWAY) and rounded up to form enforced limit.

@var IPSEC_TUNNEL_OVERHEAD:
    IPsec overhead (tunnel mode with UDP encaps).
@var L2TP_OVERHEAD:
    L2TP(v2) overhead (data).
@var PPP_OVERHEAD:
    PPP overhead (data).
@var OVERHEAD_SAFETY_MARGIN:
    Safety margin for overhead estimation.
@var TOTAL_L2TP_IPSEC_OVERHEAD:
    Final data overhead estimate, rounded up to nearest multiple of 4.

@var IP_PROTOCOL_TCP:
    TCP protocol number.
@var IP_PROTOCOL_UDP:
    UDP protocol number.
@var IP_PROTOCOL_ICMP:
    ICMP protocol number.

@var ROUTE_TABLE_GATEWAY:
    Route table identifier to gateway routes (ip command).
@var ROUTE_TABLE_CLIENT:
    Route table identifier for client routes (ip command).
@var ROUTE_TABLE_LOCAL_L2TP:
    Route table identifier for local l2tp traffic routes (ip command).

@var FWMARK_IPSEC:
    Firewall marker for received IPsec traffic.
@var FWMARK_SKIPNAT:
    Firewall marker for outbound traffic that should skip public/private NAT.
@var FWMARK_PPP:
    Firewall marker for PPP traffic, i.e. traffic received from PPP clients.
    May be site-to-site or remote access client.  This mark is applied only
    for packets coming from PPP interfaces.
@var FWMARK_PPP_S2S:
    Traffic which is site-to-site device related: either coming from or going
    to a S2S interface.  Note that this mark is also applied if a packet comes
    from a non-PPP interface and goes into a S2S PPP interface.  In this sense
    this mark differs from FWMARK_PPP, which only applies to traffic coming
    *from* a PPP interface.
@var FWMARK_LOCAL_L2TP:
    Firewall marker for locally generated L2TP traffic; used in a routing
    trick to ensure IPsec gets correct addresses.
@var FWMARK_LICENSE_RESTRICTED:
    Marker for packets which have been license restricted.  Currently used to
    prevent forced routing of license restricted packets.
    
@var DHCP_INFORMATION_PUBLIC:
    Temporary state file used between L2TP dhclient script and L2TP script.
@var DHCP_INFORMATION_PRIVATE:
    Temporary state file used between L2TP dhclient script and L2TP script.
@var L2TP_CONFIGFILE:
    L2TP gateway configuration file (RDF).
@var DHCLIENT_CONF:
    Dhclient configuration file (standard location).
@var DHCLIENT_SCRIPT:
    Dhclient script file used by L2TP (L2TP specific location).
@var DHCLIENT_LEASES:
    Dhclient leases file (standard location).
@var EZIPUPDATE_CONF:
    Configuration file for ez-ipupdate.
@var EZIPUPDATE_CACHE:
    Cache file for ez-ipupdate.
@var PLUTO_CONF:
    Pluto configuration file (shared secret file).
@var IPPOOL_CONF:
    IPpool daemon config file.
@var OPENL2TP_CONF:
    OpenL2tp config file.
@var MONIT_CONF:
    Monit config file.
@var SNMPD_CONF:
    Snmpd confif file.

@var RUNNER_PIDFILE:
    L2TP runner script PID file.
@var WEBUI_PIDFILE:
    L2TP webui PID file.
@var DHCLIENT_PIDFILE:
    (Our) dhclient pidfile.
@var L2TPD_PIDFILE:
    L2tpd pidfile.
@var OPENL2TP_PIDFILE:
    OpenL2tp pidfile.
@var IPPOOL_PIDFILE:
    IPpoold pidfile.
@var PLUTO_PIDFILE:
    Pluto pidfile.
@var PLUTO_CTLFILE:
    Pluto control socket file.
@var EZIPUPDATE_PIDFILE:
    Ez-ipupdate pidfile.
@var SNMPD_PIDFILE:
    Snmpd pidfile.

@var PLUTO_SAINFO_DIR:
    Directory holding Pluto sainfo files.

@var PORTMAP_STATEFILE:
    File containing portmapper saved state between portmapper starts.
    Only exists when portmapper is stopped.

@var PORTMAP_UPGRADE_STATEFILE:
    File containing pormapper saved state when portmap package has
    been upgraded.

@var INSTALL_STATUS_FILE:
    File to deliver installation script progress and return value
    status to parent (GUI). Empty file or single line "failed" means
    installation error, single line "success" means completed installation
    and a number between 0-100 (inclusive) tells installation progress
    followed by an optional description of the installation phase.
@var INSTALL_STDOUT:
    Stdout of installer.
@var INSTALL_STDERR:
    Stderr of installer.

@var INSTALL_PARTITION_WAIT_DISAPPEAR:
    How long to wait (in seconds) for partition devices to disappear
    when partition table has been modified.
@var INSTALL_PARTITION_WAIT_APPEAR:
    How long to wait (in seconds) for partition devices to appear
    when partition table has been modified.

@var INSTALL_AUTORUN_LINUX_SCRIPT:
    Autorun Linux script to be placed in the root of the CD/DVD or USB stick.
    Doesn't work in most Linux systems, unfortunately, because autorunning
    is usually disabled.

@var INSTALL_AUTORUN_ZIPFILE:
    Zip file containing the autorun README files for an installed system.
    
@var INSTALL_FATDEVICE_PARTITION_NAME:
    Partition name for a formatted FAT device (USB stick).

@var INSTALL_FATDEVICE_SAFETY_MARGIN:
    How much space to leave unpartitioned in a FAT format.   For some
    reason sector-accuracy is not feasible.

@var ADMIN_USER_NAME:
    Name of (default) administrator user added by installer.  Also
    expected by startup scripts etc.

@var PRODUCT_NAME:
    Product name for various purposes, with correct capitalization.
    (If caller needs special capitalization, operate on this string.)

@var PRODUCT_DEBIAN_NAME:
    Product name used as a top-level Debian package name.

@var CMD_ECHO:
    Command path.
@var CMD_IPTABLES_RESTORE:
    Command path.
@var CMD_IPTABLES_SAVE:
    Command path.
@var CMD_CONNTRACK:
    Command path.
@var CMD_SH:
    Command path.
@var CMD_CP:
    Command path.
@var CMD_MV:
    Command path.
@var CMD_TC:
    Command path.
@var CMD_IP:
    Command path.
@var CMD_IFCONFIG:
    Command path.
@var CMD_RM:
    Command path.
@var CMD_RMDIR:
    Command path.
@var CMD_MKDIR:
    Command path.
@var CMD_TRUE:
    Command path.
@var CMD_START_STOP_DAEMON:
    Command path.
@var CMD_KILLALL:
    Command path.
@var CMD_IPSEC:
    Command path.
@var CMD_SETKEY:
    Command path.
@var CMD_MONIT:
    Command path.
@var CMD_DHCLIENT:
    Command path.
@var CMD_L2TPD:
    Command path.
@var CMD_OPENL2TP:
    Command path.
@var CMD_OPENL2TPCONFIG:
    Command path.
@var CMD_IPPOOL:
    Command path.
@var CMD_INITD_NETWORKING:
    Command path.
@var CMD_INITD_EZIPUPDATE:
    Command path.
@var CMD_MODPROBE:
    Command path.
@var CMD_DHCLIENT_SIGNAL:
    Command path.
@var CMD_PPPD:
    Command path.
@var CMD_MYSQL:
    Command path.
@var CMD_MYSQLADMIN:
    Command path.
@var CMD_MYSQLDUMP:
    Command path.
@var CMD_PING:
    Command path.
@var CMD_ARPING:
    Command path.
@var CMD_HOST:
    Command path.
@var CMD_RRDTOOL:
    Command path.
@var CMD_RRDUPDATE:
    Command path.
@var CMD_DF:
    Command path.
@var CMD_VMSTAT:
    Command path.
@var CMD_PORTMAP:
    Command path.
@var CMD_LSPCI:
    Command path.
@var CMD_SHUTDOWN:
    Command path.
@var CMD_MOUNT:
    Command path.
@var CMD_UMOUNT:
    Command path.
@var CMD_SLEEP:
    Command path.
@var CMD_SUDO:
    Command path.
@var CMD_GCONFTOOL2:
    Command path.
@var CMD_SHUTDOWN:
    Command path.
@var CMD_OPENSSL:
    Command path.
@var CMD_DPKG:
    Command path.
@var CMD_APTITUDE:
    Command path.
@var CMD_ZIP:
    Command path.
@var CMD_UNZIP:
    Command path.
@var CMD_PYTHON:
    Command path.
@var CMD_DATE:
    Command path.
@var CMD_HWCLOCK:
    Command path.

@var CMD_PASSWD:
    Command path.
@var CMD_CHPASSWD:
    Command path.

@var CMD_XKLAVIERTOOL:
    Command path.
@var CMD_NOTIFYTOOL:
    Command path.
@var CMD_RADAUTHUSER:
    Command path.

@var CMD_L2TPGW_RUNNER:
    Command path.
@var CMD_L2TPGW_INIT:
    Command path.
@var CMD_L2TPGW_INSTALL:
    Command path.
@var CMD_L2TPGW_CRON:
    Command path.
@var CMD_L2TPGW_GNOME_AUTOSTART:
    Command path.
@var CMD_L2TPGW_UPDATE:
    Command path.
@var CMD_L2TPGW_UPDATE_PRODUCT:
    Command path.

@var CMD_APT_GET:
    Command path.
@var CMD_APT_KEY:
    Command path.

@var CMD_SYNC:
    Command path.
@var CMD_REBOOT:
    Command path.
@var CMD_HALT:
    Command path.
@var CMD_LDD:
    Command path.
@var CMD_FILE:
    Command path.
@var CMD_EJECT:
    Command path.
@var CMD_CAT:
    Command path.
@var CMD_DD:
    Command path.
@var CMD_LSHAL:
    Command path.
@var CMD_PIDOF:
    Command path.
@var CMD_SNMPD:
    Command path.
@var CMD_SNMPWALK:
    Command path.
    
@var VERSION_INFO_CACHE:
    Cached product version string.
@var APTSOURCE_CACHE:
    Cached apt sources.list file.
@var DEFAULT_VERSION_STRING:
    Default version string to use when real version information
    is not available.
@var PRODUCT_CHANGELOG:
    Location of the changelog file.

@var PRODUCT_DATABASE_FILENAME:
    Sqlite file of product main database.

@var WEBUI_LEGAL_NOTICE_URI:
    Web URI.
    
@var PRODUCT_WEB_SERVER_ADDRESS:
    Product address/URI constant.
@var PRODUCT_WEB_SERVER_URI:
    Product address/URI constant.
@var PRODUCT_MANAGEMENT_SERVER_ADDRESS:
    Product address/URI constant.
@var PRODUCT_MANAGEMENT_SERVER_ADDRESS_TEMPLATE:
    Product address/URI template.
@var PRODUCT_MANAGEMENT_SERVER_PORT:
    Product address/URI constant.
@var PRODUCT_REPOSITORY_SERVER_ADDRESS:
    Product address/URI constant.
@var PRODUCT_DOWNLOAD_SERVER_ADDRESS:
    Product address/URI constant.
@var PRODUCT_BITTORRENT_TRACKER_SERVER_ADDRESS:
    Product address/URI constant.
@var PRODUCT_SUPPORT_EMAIL:
    Product e-mail constant.

@var MANAGEMENT_CONNECTION_TRUSTED_CERTIFICATE_DIGESTS:
    List of trusted SHA1 certificate digests.  In practice this must contain SHA1
    digest of the trusted VPNease CA certificate.
    See: l2tp-dev/vpnease-certificates/management-protocol/vpnease-ca-certificate.pem.
@var MANAGEMENT_CONNECTION_REVOKED_CERTIFICATES_FILE:
    File containing a list of SHA1 hashes for revoked certificates (SHA1 of their DER X.509 forms),
    one hash per line in hexadecimal encoding.  This is a file, because it must be available to
    both system and naftalin code.

@var RUNTIME_DIRECTORY:
    Runtime stuff stored here.
@var LIVECD_MARKER_FILE:
    Marker file which indicates that we're running in a Live CD environment.
@var LOWMEM_MARKER_FILE:
    Marker file which indicates that we're running in a "low memory" environment
    (typically also in a Live CD environment).
@var WELCOME_BALLOON_SHOWN_MARKER_FILE:
    Marker file which indicates that the 'welcome balloon' has already been shown.
    Mostly relevant for an installed system, not for Live CD (though used with Live
    CD, too).
    
@var RUNNER_STATE_STRING_PREFIX:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_STARTING:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_RUNNING:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_STOPPING:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_STOPPED:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_PREPARING:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_WAITING_FOR_DHCP:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_STARTING_NETWORK:
    Marker string used by runner to communicate with web UI.
@var RUNNER_STATE_STRING_STARTING_DAEMONS:
    Marker string used by runner to communicate with web UI.

@var CRON_WATCHDOG_WARNING_TITLE:
    Title for warning balloon when a cron watchdog error has been detected.
@var CRON_WATCHDOG_WARNING_TEXT:
    Text for warning balloon when a cron watchdog error has been detected.
@var CRON_WATCHDOG_WARNING_TIMEOUT:
    Timeout for a cron watchdog warning balloon.
@var CRON_WATCHDOG_REBOOT_DELAY:
    Delay for showing cron watchdog notify before hard reboot.

@var WEBUI_WATCHDOG_INTERVAL:
    Web UI ("master watchdog") interval in seconds.
@var WEBUI_WATCHDOG_POLL_AGE_THRESHOLD:
    Threshold value for watchdog: if runner poll update time is larger than this,
    conclude that runner is stuck and watchdog action is required.
@var WEBUI_WATCHDOG_WARNING_TITLE:
    Title for warning balloon when a watchdog error has been detected.
@var WEBUI_WATCHDOG_WARNING_TEXT:
    Text for warning balloon when a watchdog error has been detected.
@var WEBUI_WATCHDOG_WARNING_TIMEOUT:
    Timeout (in milliseconds) for watchdog warning balloon.
@var WEBUI_WATCHDOG_CANCELLED_TITLE:
    Title for warning balloon when a watchdog error has cleared before action.
@var WEBUI_WATCHDOG_CANCELLED_TEXT:
    Text for warning balloon when a watchdog error has cleared before action.
@var WEBUI_WATCHDOG_CANCELLED_TIMEOUT:
    Timeout (in milliseconds) for watchdog cleared message.
@var WEBUI_WATCHDOG_STRIKES_FOR_WARNING:
    How many watchdog failures (strikes) until warning is shown to user.
@var WEBUI_WATCHDOG_STRIKES_FOR_ACTION:
    How many watchdog failures (strikes) until action is taken.
@var WEBUI_WATCHDOG_SHUTDOWN_MESSAGE:
    Shutdown message for watchdog action.
@var WEBUI_WATCHDOG_FORCE_FAILURE_MARKER:
    If this file exists, watchdog is forced to assume there is an error.
    Useful for testing.
@var WEBUI_WATCHDOG_LAST_UPDATED_FILE:
    Web UI watchdog updates this file (currently with timestamp content)
    whenever the watchdog runs.  This allows an external process (cron)
    to check that the webui is not stuck.
@var WEBUI_WATCHDOG_RUNNER_RESTART_LIMIT:
    Limit for runner restarts after which watchdog takes action.
    Intended to shield against runner restart loop.
@var WEBUI_WATCHDOG_DISK_FREE_SPACE_LIMIT:
    If less free space than this in root filesystem, watchdog considers
    it a failure.
@var WEBUI_WATCHDOG_RUNNER_STARTING_TIME_LIMIT:
    Limit for runner to stay in starting state before watchdog considers
    runner stuck in startup.
@var WEBUI_WATCHDOG_RDF_EXPORT_INTERVAL:
    If this amount of time has passed since last RDF export, re-export
    RDF database if management connection is active (= known good).
@var WEBUI_ADMIN_ACTIVE_TIMESTAMP:
    File containing timestamp of when admin was (roughly) last active.
    This is now basically the case when Ajax is active (approximation).

@var WEBUI_LAST_TIMESYNC_FILE:
    Indicates when web UI last time synced successfully.
@var WEBUI_TIMESYNC_CAP_BACKWARDS:
    Cap backwards time jumps to this timedelta (None = no limit).
@var WEBUI_TIMESYNC_CAP_FORWARDS:
    Cap forwards time jumps to this timedelta (None = no limit).
@var WEBUI_TIMESYNC_NOTIFY_LIMIT:
    If difference between current time and management server time is larger
    than this timedelta, display a notify to admin.
@var WEBUI_TIMESYNC_NOTIFY_TITLE:
    Title for balloon when timesync difference is too large.
@var WEBUI_TIMESYNC_NOTIFY_TEXT:
    Text for balloon when timesync difference is too large.
@var WEBUI_TIMESYNC_NOTIFY_TIMEOUT:
    Timeout for balloon when timesync difference is too large.

@var UPTIME_WEBUI_TIMESYNC_AGE_LIMIT:
    Web UI timesync older than this is considered stale by helpers.get_uptime().
    
@var WEBUI_PRODUCT_REBOOT_MESSAGE:
    Message for reboot when product is rebooted.
@var WEBUI_PRODUCT_SHUTDOWN_MESSAGE:
    Message for reboot when product is shut down.
@var WEBUI_PRODUCT_UPDATE_MESSAGE:
    Message for reboot when product is updated.
@var WEBUI_PRODUCT_PERIODIC_REBOOT_MESSAGE:
    Message for reboot when periodic reboot done.

@var WEBUI_RUNNER_READY_TITLE:
    Title for balloon when runner becomes active.
@var WEBUI_RUNNER_READY_TEXT:
    Text for balloon when runner becomes active.
@var WEBUI_RUNNER_READY_TIMEOUT:
    Timeout (in milliseconds) for runner ready message.
@var WEBUI_RUNNER_STOPPED_TITLE:
    Title for balloon when runner is stopped.
@var WEBUI_RUNNER_STOPPED_TEXT:
    Text for balloon when runner is stopped.
@var WEBUI_RUNNER_STOPPED_TIMEOUT:
    Timeout (in milliseconds) for runner stopped message.
@var WEBUI_COMMAND:
    Command to start webui.
@var WEBUI_TAC
    Webui process setup file.
@var WEBUI_STOP_TIMEOUT
    Timeout in seconds for waiting webui termination.
@var LIVECD_TAC:
    Livecd webui process setup file.
@var LIVECD_WELCOME_TITLE:
    Title for Live CD welcome notification.
@var LIVECD_WELCOME_TEXT:
    Text for Live CD welcome notification.
@var LIVECD_WELCOME_TIMEOUT:
    Timeout (in milliseconds) for Live CD welcome notification.
@var INSTALLED_WELCOME_TITLE:
    Title for installed welcome notification.
@var INSTALLED_WELCOME_TEXT:
    Text for installed CD welcome notification.
@var INSTALLED_WELCOME_TIMEOUT:
    Timeout (in milliseconds) for installed welcome notification.
@var CRON_WEBUI_FAILURE_COUNT_FILE:
    Failure count for cron scripts to detect missing or stuck web UI.
@var DBUS_SESSION_BUS_ADDRESS_FILE:
    File containing one line (terminated with new line) with the DBUS
    session bus address for the local administrator gnome session.
    This is needed to send notifications to notification-daemon.
@var BOOT_TIMESTAMP_FILE:
    File containing the timestamp of the last boot.

@var DEFAULT_UBUNTU_UPDATE_REPOSITORY:
    Default repository path for ubuntu update mirror.
@var DEFAULT_VPNEASE_UPDATE_REPOSITORY:
    Default repository path for vpnease update.

@var WEBUI_CERTIFICATE:
    Web UI PEM formatted X.509 certificate.
@var WEBUI_PRIVATE_KEY:
    Web UI PEM formatted private key.
@var WEBUI_EXTERNAL_CERTIFICATE_CHAIN:
    Web UI PEM formatted X.509 certificate chain (multiple PEMs in sequence).
@var WEBUI_EXTERNAL_PRIVATE_KEY:
    Web UI PEM formatted private key.

@var MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_INTERVAL:
    Interval (seconds) between keepalives, relative to success of last keepalive.
    Keepalives are never "resent".
@var MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_WAIT:
    Interval after which keepalive response is considered to be too late and
    management connection abandoned.
@var MANAGEMENT_PROTOCOL_REIDENTIFY_MINIMUM_TIME:
    Minimum time for reidentify.  Guards against hammering.
@var MANAGEMENT_PROTOCOL_REIDENTIFY_MAXIMUM_TIME:
    Maximum time for reidentify.

@var EXPORTED_RDF_DATABASE_FILE:
    Filename for the RDF file exported by Web UI when configuration has been confirmed
    to be good.  Used by boot-time update scripts to get network connection.

@var TEMPORARY_RDF_DATABASE_FILE:
    Temporary file for processed exported RDF database during update process.  Internal
    to update process; we don't want to change EXPORTED_RDF_DATABASE_FILE.
    
@var UPDATE_POLICY_CHECK_TIMEOUT:
    When checking for update policy from management server, we need to get network
    connectivity up and then run the management protocol.  This is a global timeout
    for that process; if the timeout is expired, alternative action is taken.
@var UPDATE_SCRIPT_TIMEOUT:
    Timeout for running actual update script.  This cannot be too short, because it
    must accommodate very slow connections.

@var UPDATE_RESULT_MARKER_FILE:
    Marker file.
@var LAST_SUCCESSFUL_UPDATE_MARKER_FILE:
    Marker file, containing timestamp of last successful update (where version changed).
@var LAST_AUTOMATIC_REBOOT_MARKER_FILE:
    Marker file, containing timestamp of the time last periodic reboot was started.

@var INSTALLATION_UUID:
    Installation UUID file.
@var BOOT_UUID:
    Boot UUID file.
@var COOKIE_UUID:
    Cookie UUID file.

@var TIMESYNC_TIMESTAMP_FILE:
    File containing timestamp of timesync with management server if done after last boot.

@var TIMESYNC_PERSISTENT_TIMESTAMP_FILE:
    File containing timestamp of latest (persistent) timesync with management server.

@var UPDATE_SKIP_MARKER_FILE:
    Marker file to tell init scripts to skip update in next boot.

@var UPDATE_FORCE_MARKER_FILE:
    Marker file to tell init scripts to force update in next boot.

@var PRODUCT_ZIPFILE_MAGIC:
    Magic constant for product zipfile 'magic' file.
@var PRODUCT_ZIPFILE_VERSION:
    Current zipfile version.
@var PRODUCT_ZIPFILE_NAME_CONFIG_EXPORT:
    Configuration export name.
@var PRODUCT_ZIPFILE_NAME_DIAGNOSTICS_EXPORT:
    Diagnostics export name.

@var PERIODIC_REBOOT_MAX_UPTIME:
    If uptime reaches this limit (in seconds), reboot forcibly regardless
    of administrative settings or lack thereof.
@var PERIODIC_REBOOT_MINIMUM_WATCHDOG_ROUNDS:
    Cancel periodic reboot request if less than this watchdog rounds have
    been run.  Purpose: prevent against immediate reboots when initial time
    during (first) boot is way off base.
@var WEBUI_PERIODIC_REBOOT_PENDING_TITLE:
    Periodic reboot pending notification: title.
@var WEBUI_PERIODIC_REBOOT_PENDING_TEXT:
    Periodic reboot pending notification: text.
@var WEBUI_PERIODIC_REBOOT_PENDING_TIMEOUT:
    Periodic reboot pending notification: timeout.

@var WEBUI_PORT_HTTP:
    Web UI HTTP port.
@var WEBUI_PORT_HTTPS:
    Web UI HTTPS port.
@var WEBUI_FORWARD_PORT_UIFORCED_HTTP:
    Web UI forwarding port.
@var WEBUI_FORWARD_PORT_UIFORCED_HTTPS:
    Web UI forwarding port.
@var WEBUI_FORWARD_PORT_LICENSE_HTTP:
    Web UI forwarding port.
@var WEBUI_FORWARD_PORT_LICENSE_HTTPS:
    Web UI forwarding port.
@var WEBUI_FORWARD_PORT_OLDPSK_HTTP:
    Web UI forwarding port.
@var WEBUI_FORWARD_PORT_OLDPSK_HTTPS:
    Web UI forwarding port.

@var LOCAL_ADMINISTRATOR_NAME:
    Username of the local administrator.

@var FASTBOOT_MARKER_FILE:
    This marker file causes init scripts to skip fsck. Written always after normal boot.
@var FORCE_FSCK_MARKER_FILE:
    This marker file causes init scripts to force fsck in boot. Written by periodic reboot function.

@var UPDATE_REPOSITORY_KEYS_FILE:
    Temporary storage of update repository keys received from management server.

@var SYSLOG_DEVICE_FILE:
    From where to read syslog messages.

@var SYSLOG_LOGFILE:
    Most recent syslog file.
@var SYSLOG_LOGFILE_BACKUP:
    Backup logfile.
@var SYSLOG_LOGFILE_MAX_SIZE:
    Maximum size of syslog file before rotating.
@var SYSLOG_MSG_MAX_SIZE:
    Maximum size of read syslog msg.

@var SYSLOG_POLL_TIMEOUT:
    Timeout to syslog device poll.
@var SYSLOG_FLUSH_TIMEOUT:
    Timeout to wait before forcing syslog file flush.

@var SYSLOG_EXCEPTION_LOG:
    Syslog writes its own errors to this file and tries to log them to syslog in next syslog start.

@var DMESG_LOGFILE:
    Points to dmesg log file in /var/log.

@var ALLOWED_UNIX_PASSWORD_CHARACTERS:
    Characters allowed into Unix (root) password.

@var DISK_SIZE_MINIMUM:
    Minimum disk size allowed.
@var DISK_SIZE_MINIMUM_FOR_LARGE_INSTALL:
    Minimum disk size required for "large" install with multiple partitions.
@var DISK_SIZE_SAFETY_MARGIN:
    Safety margin to allow slightly smaller media than our required size.

@var RRDGRAPH_USER_COUNT:
    Graph path.
@var RRDGRAPH_SITETOSITE_COUNT:
    Graph path.

@var LIVECD_FORCED_REBOOT_STAGE1_DELAY:
    Delay before forced reboot stage 1 (sync, warmup reboot command, forced eject).
@var LIVECD_FORCED_REBOOT_STAGE2_DELAY:
    Delay after stage1 before forcing a reboot.

@var OPENL2TP_CONFIG_LOCK_FILE:
    Lock file to prevent simultanous calling of openl2tp config process.
@var OPENL2TP_CONFIG_LOCK_TIMEOUT:
    Timeout to wait for openl2tp config lock.

@var GNOME_BACKGROUND_IMAGE:
    Location of Gnome background image.
@var GNOME_SPLASH_IMAGE:
    Location of Gnome splash image.
@var GNOME_DESKTOP_ICON_IMAGE:
    Location of Gnome desktop icon image.
    
@var GDM_BACKGROUND_COLOR:
    GDM color setting.
@var GDM_GRAPHICAL_THEMED_COLOR:
    GDM color setting.

@var PROC_UPTIME:
    Location of proc uptime file.

@var WEBUI_DEBUG_NAV_MARKERFILE:
    If marker file exists, render admin debug nav.
@var AUTOUPDATE_MARKERFILE:
    If marker file exists, force immediate updates whenever newer version available.
@var DEBUGGRAPHS_MARKERFILE:
    If marker file exists, draw debug graphs periodically.
@var NOPWCHANGE_MARKERFILE:
    If marker file exists, prevent password changing for end users.
@var FORCE_NATTREBOOT_MARKERFILE:
    If marker exists, autoconfigure always pretends server is behind port forward.
    
@var USER_GRAPH_WIDTH:
    Graph dimensions.
@var USER_GRAPH_HEIGHT:
    Graph dimensions.
@var SITETOSITE_GRAPH_WIDTH:
    Graph dimensions.
@var SITETOSITE_GRAPH_HEIGHT:
    Graph dimensions.

@var SNMP_DATA_FILE:
    Key-value data file for passing data from Python to VPNease SNMP MIB.
@var SNMP_MIB_MODULE_SO:
    Dynamically loadable module implementing VPNease MIB; loaded by snmpd.

@var PRODUCT_VERSION_CACHE_FILE:
    Cache file for product version to minimize dpkg operations when product
    version is needed from e.g. cron scripts (which are separate processes,
    making memory cache ineffective).

@var DEFAULT_TIMEZONE:
    Default timezone used when actual timezone unavailable.

@var RUNNER_TEMPORARY_SQLITE_DATABASE:
    Temporary Sqlite database used by runner when an RDFXML file is used to
    replace the default database.  Note that also the corresponding journal
    file (same name with '-journal') may exist on the disk.

@var WEBUI_TEMPORARY_SQLITE_DATABASE:
    Temporary Sqlite database for web UI export process.  Note that also the
    corresponding journal file (same name with '-journal') may exist on the
    disk.

@var UPDATE_PROCESS_RDFXML_EXPORT_FILE:
    RDF/XML export of entire configuration created by update code BEFORE
    update.  Code after update can use this export to re-create its sqlite
    (or other) database without necessarily supporting existing sqlite
    format.

@var AUTOCONFIG_EXE_WINXP_32BIT:
    Windows EXE file for autoconfiguration.
@var AUTOCONFIG_EXE_WINXP_64BIT:
    Windows EXE file for autoconfiguration.
@var AUTOCONFIG_EXE_VISTA_32BIT:
    Windows EXE file for autoconfiguration.
@var AUTOCONFIG_EXE_VISTA_64BIT:
    Windows EXE file for autoconfiguration.
@var AUTOCONFIG_EXE_WIN2K_32BIT:
    Windows EXE file for autoconfiguration.
@var AUTOCONFIG_PROFILE_PREFIX_FILE:
    Prefix for autoconfigure VPN profile name; if doesn't exist, product
    name is used by default.

@var MAX_USERNAME_LENGTH:
    Maximum acceptable (PPP) username length.
@var MAX_PASSWORD_LENGTH:
    Maximum acceptable (PPP) password length.
@var MAX_PRE_SHARED_KEY_LENGTH:
    Maximum acceptable IPsec pre-shared key length.
"""
__docformat__ = 'epytext en'

import datetime

RUNTIME_DIRECTORY = '/var/run/l2tpgw'

# return values for statstop.py
STARTSTOP_RETVAL_UNKNOWN = 2
STARTSTOP_RETVAL_START_FAILED = 3
STARTSTOP_RETVAL_START_INTERFACE_FAILED = 4
STARTSTOP_RETVAL_GOT_SIGTERM = 5
STARTSTOP_RETVAL_DHCP_EXPIRED = 6
STARTSTOP_RETVAL_DHCP_CHANGED = 7
STARTSTOP_RETVAL_REBOOT_REQUIRED = 8
STARTSTOP_RETVAL_ROUTERS_NOT_RESPONDING = 9

# constant timeouts
DHCP_ACQUIRE_TIMEOUT = 60
DHCP_POLL_INTERVAL = 10 # XXX: fine-grained enough?
DHCP_TRY_COUNT = 5
POLL_INTERVAL_MAINLOOP_SIGUSR1_SANITY = 2
TIMEOUT_MAINLOOP_SIGUSR1_SANITY = 10
POLL_INTERVAL_MAINLOOP = 60

# license control
LICENSE_PPP_IGNORE_IDLE_INTERVAL = 30*60
LICENSE_CONNECTION_LEEWAY = 0.02

# IPsec overhead (RFC 2406++): UDP + (SPI + seq + iv (aes) + padding + padlen + nexthdr) + auth data (-96 variant)
# XXX: padding length may be one-off
IPSEC_TRANSPORT_OVERHEAD = 8 + (4 + 4 + 16 + 16 + 1 + 1 + 12)

# L2TP overhead (RFC 2661): IP (minimal) + UDP + (max header without offset field)
L2TP_OVERHEAD = 20 + 8 + (4 + 4 + 4)

# PPP overhead (RFC 1661): protocol field (uncompressed)
PPP_OVERHEAD = 2

# total overhead
def _round_to_4(x):
    return ((x + 3) / 4) * 4
OVERHEAD_SAFETY_MARGIN = 8
TOTAL_L2TP_IPSEC_OVERHEAD = _round_to_4(IPSEC_TRANSPORT_OVERHEAD + L2TP_OVERHEAD + PPP_OVERHEAD + OVERHEAD_SAFETY_MARGIN)
# XXX: calculate also overhead to use for openl2tp mtu/mru options

IP_PROTOCOL_TCP = 6
IP_PROTOCOL_UDP = 17
IP_PROTOCOL_ICMP = 1

# ip route tables
ROUTE_TABLE_GATEWAY = 'main'
ROUTE_TABLE_CLIENT = '100'
ROUTE_TABLE_LOCAL_L2TP = '101'

ROUTE_NORMAL_METRIC = '1'
ROUTE_CATCHALL_METRIC = '8'

# firewall markers (strings)
FWMARK_IPSEC = '1'
FWMARK_SKIPNAT = '2'
FWMARK_PPP = '4'
FWMARK_LOCAL_L2TP = '8'
FWMARK_PPP_S2S = '16'               # same as 0x10, iptables input format is decimal (16) or hex (0x10)
FWMARK_LICENSE_RESTRICTED = '32'

# XXX: obsolete
MONIT_LOGFILE = '/tmp/monit.log'
MONIT_TIMEOUT = 60

MANAGEMENT_CONNECTION_TRUSTED_CERTIFICATE_DIGESTS = [ '889719910ed019d4bd14b2635e3f7161da57c85f'.decode('hex') ]
MANAGEMENT_CONNECTION_REVOKED_CERTIFICATES_FILE = '/var/lib/l2tpgw/management-connection-revoked-certificates.txt'

# Main temporary workplace
DHCP_RUNTIME_DIRECTORY = '%s/dhcp' % RUNTIME_DIRECTORY

# main config file
L2TP_CONFIGFILE = '/var/lib/l2tpgw/l2tp-cfg.rdf'

# generated daemon process config files
DHCLIENT_CONF = '%s/l2tp-dhclient.conf' % RUNTIME_DIRECTORY
DHCLIENT_SCRIPT = '%s/l2tp-dhclient-script' % RUNTIME_DIRECTORY
DHCLIENT_LEASES = '%s/l2tp-dhclient.leases' % RUNTIME_DIRECTORY
EZIPUPDATE_CONF = '%s/ez-ipupdate.conf' % RUNTIME_DIRECTORY
EZIPUPDATE_CACHE = '/var/lib/l2tpgw/ez-ipupdate.cache' # Note: must survive restart/reboot
L2TPD_CONF = '%s/l2tpd.conf' % RUNTIME_DIRECTORY
PLUTO_CONF = '%s/psk.txt' % RUNTIME_DIRECTORY
IPPOOL_CONF = '%s/ippool.conf' % RUNTIME_DIRECTORY
OPENL2TP_CONF = '%s/openl2tp.conf' % RUNTIME_DIRECTORY
MONIT_CONF = '%s/monit.conf' % RUNTIME_DIRECTORY
MONIT_STATE = '%s/monit.state' % RUNTIME_DIRECTORY
DHCP_CONF = '%s/dhcp.conf' % RUNTIME_DIRECTORY

# pppd config files
# Note: locations of pppd config files are not configurable.
PPP_PAP_SECRETS = '/etc/ppp/pap-secrets'
PPP_CHAP_SECRETS = '/etc/ppp/chap-secrets'
PPP_OPTIONS = '/etc/ppp/options'
PPP_IP_PRE_UP = '/etc/ppp/ip-pre-up'
PPP_IP_UP = '/etc/ppp/ip-up'
PPP_IP_DOWN = '/etc/ppp/ip-down'
            
# pidfiles
RUNNER_PIDFILE = '/var/run/l2tpgw/l2tpgw-runner.pid'
WEBUI_PIDFILE = '/var/run/l2tpgw/l2tpgw-webui.pid'
DHCLIENT_PIDFILE = '/var/run/dhclient-l2tp.pid'
L2TPD_PIDFILE = '/var/run/l2tpd.pid'
OPENL2TP_PIDFILE = '/var/run/openl2tpd.pid'
IPPOOL_PIDFILE = '/var/run/ippoold.pid'
PLUTO_PIDFILE = '/var/run/pluto/pluto.pid'
PLUTO_CTLFILE = '/var/run/pluto/pluto.ctl'
EZIPUPDATE_PIDFILE = '/var/run/ezipupdate.pid'
MONIT_PIDFILE = '/var/run/monit.pid'
# PORTMAP_PIDFILE = None # Portmap does not generate pidfile.
FREERADIUS_PIDFILE = '/var/run/freeradius/freeradius.pid' # Note: cannot move, not configurable
SNMPD_PIDFILE = '/var/run/snmpd.pid'
DHCPD3_PIDFILE = '/var/run/dhcpd.pid'

# freeradius config files
FREERADIUS_CONFIG_DIR = '%s/freeradius' % RUNTIME_DIRECTORY
FREERADIUS_ACCT_USERS = '%s/acct_users' % FREERADIUS_CONFIG_DIR
FREERADIUS_ATTRS = '%s/attrs' % FREERADIUS_CONFIG_DIR
FREERADIUS_CLIENTS = '%s/clients' % FREERADIUS_CONFIG_DIR
FREERADIUS_CLIENTS_CONF = '%s/clients.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_DICTIONARY = '%s/dictionary' % FREERADIUS_CONFIG_DIR
FREERADIUS_EAP_CONF = '%s/eap.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_EXPERIMENTAL_CONF = '%s/experimental.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_HINTS = '%s/hints' % FREERADIUS_CONFIG_DIR
FREERADIUS_HUNTGROUPS = '%s/huntgroups' % FREERADIUS_CONFIG_DIR
FREERADIUS_LDAP_ATTRMAP = '%s/ldap.attrmap' % FREERADIUS_CONFIG_DIR
FREERADIUS_MSSQL_CONF = '%s/mssql.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_NASLIST = '%s/naslist' % FREERADIUS_CONFIG_DIR
FREERADIUS_NASPASSWD = '%s/naspasswd' % FREERADIUS_CONFIG_DIR
FREERADIUS_ORACLESQL_CONF = '%s/oraclesql.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_OTP_CONF = '%s/otp.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_POSTGRESQL_CONF = '%s/postgresql.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_PREPROXY_USERS = '%s/preproxy_users' % FREERADIUS_CONFIG_DIR
FREERADIUS_PROXY_CONF = '%s/proxy.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_RADIUSD_CONF = '%s/radiusd.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_REALMS = '%s/realms' % FREERADIUS_CONFIG_DIR
FREERADIUS_SNMP_CONF = '%s/snmp.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_SQL_CONF = '%s/sql.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_SQLIPPOOL_CONF = '%s/sqlippool.conf' % FREERADIUS_CONFIG_DIR
FREERADIUS_USERS = '%s/users' % FREERADIUS_CONFIG_DIR

FREERADIUS_RUNPATH = '/var/run/freeradius'

FREERADIUS_RESTART_MARKER = '/var/run/l2tpgw/restart-freeradius'

# snmp
SNMPD_CONF = '/etc/snmp/snmpd.conf'


# pluto sainfos
PLUTO_SAINFO_DIR = '/var/run/l2tpgw/sainfo'

# other state files
PORTMAP_STATEFILE = '/var/run/portmap.state'
PORTMAP_UPGRADE_STATEFILE = '/var/run/portmap.upgrade-state'

# Installation specific constants
INSTALL_STATUS_FILE = '/var/run/l2tpgw/install.state'
INSTALL_STDOUT = '/var/run/l2tpgw/install.stdout'
INSTALL_STDERR = '/var/run/l2tpgw/install.stderr'
INSTALL_PARTITION_WAIT_DISAPPEAR = 60
INSTALL_PARTITION_WAIT_APPEAR = 60

INSTALL_AUTORUN_ZIPFILE = '/usr/lib/l2tpgw/installer/autorun-installed-files.zip'
INSTALL_AUTORUN_LINUX_SCRIPT = '/usr/lib/l2tpgw/installer/autorun-linux-script'

INSTALL_FATDEVICE_PARTITION_NAME = 'FAT'
INSTALL_FATDEVICE_SAFETY_MARGIN = 64*1024  # 64KiB

ADMIN_USER_NAME = 'admin'

PRODUCT_NAME = 'VPNease'
PRODUCT_DEBIAN_NAME = 'vpnease'

# command paths
CMD_ECHO = '/bin/echo'
CMD_IPTABLES_RESTORE = '/sbin/iptables-restore'
CMD_IPTABLES_SAVE = '/sbin/iptables-save'
CMD_CONNTRACK = '/usr/sbin/conntrack'
CMD_SH = '/bin/sh'
CMD_CP = '/bin/cp'
CMD_MV = '/bin/mv'
CMD_TC = '/sbin/tc'
CMD_IP = '/bin/ip'
CMD_IFCONFIG = '/sbin/ifconfig'
CMD_RM = '/bin/rm'
CMD_RMDIR = '/bin/rmdir'
CMD_MKDIR = '/bin/mkdir'
CMD_CHOWN = '/bin/chown'
CMD_CHMOD = '/bin/chmod'
CMD_TRUE = '/bin/true'
CMD_START_STOP_DAEMON = '/sbin/start-stop-daemon'
CMD_KILLALL = '/usr/bin/killall'
CMD_KILL = '/bin/kill'
CMD_IPSEC = '/usr/sbin/ipsec'
CMD_SETKEY = '/usr/sbin/setkey'
CMD_MONIT = '/usr/sbin/monit'
CMD_DHCLIENT = '/sbin/dhclient3'
CMD_L2TPD = '/usr/sbin/l2tpd'
CMD_INITD_NETWORKING = '/etc/init.d/networking'
CMD_EZIPUPDATE = '/usr/sbin/ez-ipupdate'
CMD_PLUTO = '/usr/lib/ipsec/pluto'
CMD_OPENL2TP = '/usr/sbin/openl2tpd'
CMD_OPENL2TPCONFIG = '/usr/bin/l2tpconfig'
CMD_IPPOOL = '/usr/sbin/ippoold'
CMD_IPPOOLCONFIG = '/usr/bin/ippoolconfig'
CMD_MODPROBE = '/sbin/modprobe'
CMD_DHCLIENT_SIGNAL = '/usr/lib/l2tpgw/dhclient_signal'
CMD_PPPD = '/usr/sbin/pppd'
CMD_DHCPD3 = '/usr/sbin/dhcpd3'

CMD_MYSQL = '/usr/bin/mysql'
CMD_MYSQLADMIN = '/usr/bin/mysqladmin'
CMD_MYSQLDUMP = '/usr/bin/mysqldump'

CMD_PING = '/bin/ping'
CMD_ARPING = '/usr/bin/arping'  # iputils-arping
CMD_HOST = '/usr/bin/host'

CMD_RRDTOOL = '/usr/bin/rrdtool'
CMD_RRDUPDATE = '/usr/bin/rrdupdate'
CMD_DF = '/bin/df'
CMD_VMSTAT = '/usr/bin/vmstat'
CMD_PORTMAP = '/sbin/portmap'
CMD_LSPCI = '/usr/bin/lspci'
CMD_SHUTDOWN = '/sbin/shutdown'

CMD_MOUNT = '/bin/mount'
CMD_UMOUNT = '/bin/umount'
CMD_SLEEP = '/bin/sleep'
CMD_SUDO = '/usr/bin/sudo'
CMD_GCONFTOOL2 = '/usr/bin/gconftool-2'

CMD_SHUTDOWN = '/sbin/shutdown'
CMD_OPENSSL = '/usr/bin/openssl'
CMD_DPKG = '/usr/bin/dpkg'
CMD_PYTHON = '/usr/bin/python'
CMD_DATE = '/bin/date'
CMD_HWCLOCK = '/sbin/hwclock'

CMD_PASSWD = '/usr/bin/passwd'
CMD_CHPASSWD = '/usr/sbin/chpasswd'

CMD_APTITUDE = '/usr/bin/aptitude'
CMD_ZIP = '/usr/bin/zip'
CMD_UNZIP = '/usr/bin/unzip'

CMD_XKLAVIERTOOL = '/usr/lib/l2tpgw/xklaviertool'
CMD_NOTIFYTOOL = '/usr/lib/l2tpgw/notifytool'
CMD_RADAUTHUSER = '/usr/lib/l2tpgw/radauthuser'

CMD_L2TPGW_RUNNER = '/usr/lib/l2tpgw/l2tpgw-runner'
CMD_L2TPGW_INIT = '/usr/lib/l2tpgw/l2tpgw-init'
CMD_L2TPGW_INSTALL = '/usr/lib/l2tpgw/l2tpgw-install'
CMD_L2TPGW_CRON = '/usr/lib/l2tpgw/l2tpgw-cron'
CMD_L2TPGW_GNOME_AUTOSTART = '/usr/lib/l2tpgw/l2tpgw-gnome-autostart'
CMD_L2TPGW_UPDATE = '/usr/lib/l2tpgw/l2tpgw-update'
CMD_L2TPGW_UPDATE_PRODUCT = '/usr/lib/l2tpgw/l2tpgw-update-product'

CMD_APT_GET = '/usr/bin/apt-get'
CMD_APT_KEY = '/usr/bin/apt-key'

CMD_SYNC = '/bin/sync'
CMD_REBOOT = '/sbin/reboot'
CMD_HALT= '/sbin/halt'
CMD_LDD = '/usr/bin/ldd'
CMD_FILE = '/usr/bin/file'
CMD_EJECT = '/usr/bin/eject'
CMD_CAT = '/bin/cat'
CMD_DD = '/bin/dd'
CMD_LSHAL = '/usr/bin/lshal'
CMD_PIDOF = '/bin/pidof'
CMD_SNMPD = '/usr/sbin/snmpd'
CMD_SNMPWALK = '/usr/bin/snmpwalk'

CMD_FREERADIUS = '/usr/sbin/freeradius'

CMD_TOUCH = '/usr/bin/touch'

VERSION_INFO_CACHE = '/var/lib/l2tpgw/version-info-cache'
APTSOURCE_CACHE = '/var/lib/l2tpgw/apt-source-cache'
DEFAULT_VERSION_STRING = '1.0.0.0'
PRODUCT_CHANGELOG = '/usr/share/doc/%s/changelog.gz' % PRODUCT_DEBIAN_NAME

PRODUCT_DATABASE_FILENAME = '/var/lib/l2tpgw/database.sqlite'

# XXX: document
PCI_HWDATA_SOURCES = [
    '/var/lib/l2tpgw/pci.ids.20080211',   # own sf.net pci-ids copy (recent)
    '/usr/share/hwdata/pci.ids',          # ubuntu
    '/var/lib/pciutils/pci.ids',          # debian
    '/var/lib/l2tpgw/pcidatabase.ids',    # own www.pcidatabase.com copy (not present, license issues)
    ]
L2TPSERVER_RRDFILE = '/var/lib/l2tpgw/l2tpgw.rrd'

# XXX copied from siteconf, document..
WEBUI_PAGES_DIR = '/usr/lib/l2tpgw/webui-pages'
WEBUI_PORT_HTTP_INT = 80
WEBUI_PORT_HTTPS_INT = 443

WEBUI_STRPORT_HTTP = '80'
WEBUI_STRPORT_HTTPS = 'ssl:443:privateKey=/var/lib/l2tpgw/webui-private-key.pem:certKey=/var/lib/l2tpgw/webui-certificate.pem'
WEBUI_STRPORT_HTTP_FWD1 = '10080'
WEBUI_STRPORT_HTTPS_FWD1 = 'ssl:10443:privateKey=/var/lib/l2tpgw/webui-private-key.pem:certKey=/var/lib/l2tpgw/webui-certificate.pem'
WEBUI_STRPORT_HTTP_FWD2 = '11080'
WEBUI_STRPORT_HTTPS_FWD2 = 'ssl:11443:privateKey=/var/lib/l2tpgw/webui-private-key.pem:certKey=/var/lib/l2tpgw/webui-certificate.pem'
WEBUI_STRPORT_HTTP_FWD3 = '12080'
WEBUI_STRPORT_HTTPS_FWD3 = 'ssl:12443:privateKey=/var/lib/l2tpgw/webui-private-key.pem:certKey=/var/lib/l2tpgw/webui-certificate.pem'

WEBUI_LEGAL_NOTICE_URI = '/legal/legalnotice.html'  # local

PRODUCT_WEB_SERVER_ADDRESS = 'www.vpnease.com'
PRODUCT_WEB_SERVER_URI = 'http://' + PRODUCT_WEB_SERVER_ADDRESS + '/'
PRODUCT_MANAGEMENT_SERVER_ADDRESS = 'management.vpnease.com'
PRODUCT_MANAGEMENT_SERVER_ADDRESS_TEMPLATE = 'v%d.management.vpnease.com'
PRODUCT_MANAGEMENT_SERVER_PORT = 443
PRODUCT_REPOSITORY_SERVER_ADDRESS = 'packages.vpnease.com'
PRODUCT_DOWNLOAD_SERVER_ADDRESS = 'downloads.vpnease.com'
PRODUCT_BITTORRENT_TRACKER_SERVER_ADDRESS = 'bittorrent.vpnease.com'
PRODUCT_SUPPORT_EMAIL = 'support@vpnease.com'

PRODUCT_DEFAULT_UBUNTU_REPOSITORY = '%s/ubuntu/1.0' % PRODUCT_REPOSITORY_SERVER_ADDRESS
PRODUCT_DEFAULT_VPNEASE_REPOSITORY = '%s/vpnease/1.0' % PRODUCT_REPOSITORY_SERVER_ADDRESS

LIVECD_MARKER_FILE = '/var/run/l2tpgw/l2tpgw-livecd'
LOWMEM_MARKER_FILE = '/var/run/l2tpgw/l2tpgw-lowmem'

# temporary marker and info files
DHCP_INFORMATION_PUBLIC = '%s/l2tp-dhcp-info-public.txt' % DHCP_RUNTIME_DIRECTORY
DHCP_INFORMATION_PRIVATE = '%s/l2tp-dhcp-info-private.txt' % DHCP_RUNTIME_DIRECTORY

# XXX: backwards compatible with naftalin scripts in earlier 1.0 version installations
DHCP_INFORMATION_PUBLIC_NAFTALIN_HACK = '/tmp/l2tp-dhcp-info-public.txt'
DHCP_INFORMATION_PRIVATE_NAFTALIN_HACK = '/tmp/l2tp-dhcp-info-private.txt'

# radiusclient config files
RADIUSCLIENT_CONFIG_DIR = '%s/radiusclient' % RUNTIME_DIRECTORY
RADIUSCLIENT_CONFIG = '%s/radiusclient.conf' % RADIUSCLIENT_CONFIG_DIR
RADIUSCLIENT_DICTIONARY = '%s/dictionary' % RADIUSCLIENT_CONFIG_DIR
RADIUSCLIENT_DICTIONARY_MICROSOFT = '%s/dictionary.microsoft' % RADIUSCLIENT_CONFIG_DIR
RADIUSCLIENT_SERVERS = '%s/servers' % RADIUSCLIENT_CONFIG_DIR
RADIUSCLIENT_ISSUE = '%s/issue' % RADIUSCLIENT_CONFIG_DIR
RADIUSCLIENT_MAPFILE = '%s/port-id-map' % RADIUSCLIENT_CONFIG_DIR

# radiusclient-ng config files
RADIUSCLIENT_NG_CONFIG_DIR = '%s/radiusclient-ng' % RUNTIME_DIRECTORY
RADIUSCLIENT_NG_CONFIG = '%s/radiusclient-ng.conf' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_DICTIONARY = '%s/dictionary' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_DICTIONARY_MICROSOFT = '%s/dictionary.microsoft' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_DICTIONARY_VPNEASE = '%s/dictionary.vpnease' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_SERVERS = '%s/servers' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_ISSUE = '%s/issue' % RADIUSCLIENT_NG_CONFIG_DIR
RADIUSCLIENT_NG_MAPFILE = '%s/port-id-map' % RADIUSCLIENT_NG_CONFIG_DIR

# XXX: this needs permissions for admin, now putting this to admin's home...
WELCOME_BALLOON_SHOWN_MARKER_FILE = '/home/%s/l2tpgw-welcome-balloon-shown' % ADMIN_USER_NAME

RUNNER_STATE_STRING_PREFIX = '*** STATE:'
RUNNER_STATE_STRING_STARTING = 'STARTING'
RUNNER_STATE_STRING_RUNNING = 'RUNNING'
RUNNER_STATE_STRING_STOPPING = 'STOPPING'
RUNNER_STATE_STRING_STOPPED = 'STOPPED'
RUNNER_STATE_STRING_PREPARING = 'PREPARING'                 # substate of STARTING
RUNNER_STATE_STRING_WAITING_FOR_DHCP = 'WAITING_FOR_DHCP'   # substate of STARTING
RUNNER_STATE_STRING_STARTING_NETWORK = 'STARTING_NETWORK'   # substate of STARTING
RUNNER_STATE_STRING_STARTING_DAEMONS = 'STARTING_DAEMONS'   # substate of STARTING

CRON_WATCHDOG_WARNING_TITLE = PRODUCT_NAME
CRON_WATCHDOG_WARNING_TEXT = 'An internal error has been detected (cron watchdog). The product will be automatically rebooted shortly to correct the problem. Service should resume after reboot. If the problem persists, please contact support.'
CRON_WATCHDOG_WARNING_TIMEOUT = 3*60*1000  # 3 minutes
CRON_WATCHDOG_REBOOT_DELAY = 20

WEBUI_WATCHDOG_INTERVAL = 75.0
WEBUI_WATCHDOG_POLL_AGE_THRESHOLD = datetime.timedelta(0, 5*60, 0)  # 5 mins
WEBUI_WATCHDOG_WARNING_TITLE = PRODUCT_NAME
WEBUI_WATCHDOG_WARNING_TEXT = 'An internal error has been detected. The product will be automatically rebooted in a few minutes to correct the problem. Service should resume after reboot. If the problem persists, please contact support.'
WEBUI_WATCHDOG_WARNING_TIMEOUT = 3*60*1000  # 3 minutes
WEBUI_WATCHDOG_CANCELLED_TITLE = PRODUCT_NAME
WEBUI_WATCHDOG_CANCELLED_TEXT = 'The internal error has been resolved. Reboot has been cancelled. If the internal error reoccurs, please contact support.'
WEBUI_WATCHDOG_CANCELLED_TIMEOUT = 3*60*1000  # 3 minutes
WEBUI_WATCHDOG_STRIKES_FOR_WARNING = 3
WEBUI_WATCHDOG_STRIKES_FOR_ACTION = 4
WEBUI_WATCHDOG_SHUTDOWN_MESSAGE = 'Watchdog forced reboot'
WEBUI_WATCHDOG_FORCE_FAILURE_MARKER = '/tmp/force-watchdog' # XXX: only for testing
WEBUI_WATCHDOG_LAST_UPDATED_FILE = '/var/run/l2tpgw/webui-watchdog-last-update'
WEBUI_WATCHDOG_RUNNER_RESTART_LIMIT = 10
WEBUI_WATCHDOG_DISK_FREE_SPACE_LIMIT = 64*1024*1024  # 64MiB
WEBUI_WATCHDOG_RUNNER_STARTING_TIME_LIMIT = datetime.timedelta(0, 15*60, 0) # 15 mins
WEBUI_WATCHDOG_RDF_EXPORT_INTERVAL = datetime.timedelta(1, 0, 0)  # 24h
WEBUI_ADMIN_ACTIVE_TIMESTAMP = '/var/run/l2tpgw/webui-admin-active-timestamp'

WEBUI_LAST_TIMESYNC_FILE = '/var/run/l2tpgw/webui-last-timesync'
WEBUI_TIMESYNC_CAP_BACKWARDS = datetime.timedelta(0, 60, 0)
WEBUI_TIMESYNC_CAP_FORWARDS = datetime.timedelta(0, 60, 0)
WEBUI_TIMESYNC_NOTIFY_LIMIT = datetime.timedelta(0, 5*60, 0) # 5 minutes
WEBUI_TIMESYNC_NOTIFY_TITLE = PRODUCT_NAME
WEBUI_TIMESYNC_NOTIFY_TEXT = 'System time is too far from current time. Please reboot the server to synchronize system time. Your product license may not work correctly until you reboot.'
WEBUI_TIMESYNC_NOTIFY_TIMEOUT = 5*60*1000  # 5 minutes

UPTIME_WEBUI_TIMESYNC_AGE_LIMIT = datetime.timedelta(1, 0, 0)  # 24h

WEBUI_PRODUCT_REBOOT_MESSAGE = 'Rebooting'
WEBUI_PRODUCT_SHUTDOWN_MESSAGE = 'Shutting down'
WEBUI_PRODUCT_UPDATE_MESSAGE = 'Checking for product updates'
WEBUI_PRODUCT_PERIODIC_REBOOT_MESSAGE = 'Periodic maintenance reboot'
WEBUI_PRODUCT_IMPORT_REBOOT_MESSAGE = 'Rebooting - importing configuration'

WEBUI_RUNNER_READY_TITLE = PRODUCT_NAME
WEBUI_RUNNER_READY_TEXT = 'VPN service is now active.'
WEBUI_RUNNER_READY_TIMEOUT = 5*1000  # 5 seconds
WEBUI_RUNNER_STOPPED_TITLE = PRODUCT_NAME
WEBUI_RUNNER_STOPPED_TEXT = 'VPN service is now inactive.'
WEBUI_RUNNER_STOPPED_TIMEOUT = 3*1000  # 3 seconds

WEBUI_COMMAND = '/usr/bin/twistd'
WEBUI_TAC = '/usr/lib/l2tpgw/webui.tac'
WEBUI_STOP_TIMEOUT = 30

LIVECD_TAC = '/usr/lib/l2tpgw/livecd.tac'
LIVECD_WELCOME_TITLE = PRODUCT_NAME
LIVECD_WELCOME_TEXT = 'Welcome to %s Live CD!' % PRODUCT_NAME
LIVECD_WELCOME_TIMEOUT = 15*1000
INSTALLED_WELCOME_TITLE = PRODUCT_NAME
INSTALLED_WELCOME_TEXT = 'Welcome!'
INSTALLED_WELCOME_TIMEOUT = 15*1000

# XXX: this is in /tmp to avoid permission problems (written by admin, not root)
DBUS_SESSION_BUS_ADDRESS_FILE = '/tmp/dbus-session-bus-address'

CRON_WEBUI_FAILURE_COUNT_FILE = '/var/run/l2tpgw/cron-webui-failure-count'
CRON_WEBUI_WATCHDOG_SHUTDOWN_MESSAGE = 'Cron webui watchdog forced reboot'
CRON_WEBUI_WATCHDOG_TIMEOUT = datetime.timedelta(0, 2*60, 0)  # 2 mins
BOOT_TIMESTAMP_FILE = '/var/run/l2tpgw/boot-timestamp'
CRON_BOOTTIME_FAILURE_WAIT = datetime.timedelta(0, 15*60, 0)  # 15 mins

CRON_MINUTELY_RUNNING_MARKERFILE = '/var/run/l2tpgw/cron-minutely-running'

ZERO_TIMEDELTA = datetime.timedelta(0, 0, 0) # 0 seconds

WEBUI_CERTIFICATE = '/var/lib/l2tpgw/webui-certificate.pem'
WEBUI_PRIVATE_KEY = '/var/lib/l2tpgw/webui-private-key.pem'
WEBUI_EXTERNAL_CERTIFICATE_CHAIN = '/var/lib/l2tpgw/webui-external-certificate-chain.pem'
WEBUI_EXTERNAL_PRIVATE_KEY = '/var/lib/l2tpgw/webui-external-private-key.pem'

MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_INTERVAL = 5*60
MANAGEMENT_PROTOCOL_CLIENT_KEEPALIVE_WAIT = 30
MANAGEMENT_PROTOCOL_REIDENTIFY_MINIMUM_TIME = datetime.timedelta(0, 5*60, 0)  # 5 mins
MANAGEMENT_PROTOCOL_REIDENTIFY_MAXIMUM_TIME = datetime.timedelta(1, 0, 0)     # 24 hours

EXPORTED_RDF_DATABASE_FILE = '/var/lib/l2tpgw/exported-rdf-database.xml'
TEMPORARY_RDF_DATABASE_FILE = '%s/temporary-rdf-database.xml' % RUNTIME_DIRECTORY
UPDATE_POLICY_CHECK_TIMEOUT = 120
UPDATE_SCRIPT_TIMEOUT = 4*60*60   # 4 hours, see #770

UPDATE_RESULT_MARKER_FILE = '/var/lib/l2tpgw/last-update-result'
LAST_SUCCESSFUL_UPDATE_MARKER_FILE = '/var/lib/l2tpgw/last-successful-update'
LAST_AUTOMATIC_REBOOT_MARKER_FILE = '/var/lib/l2tpgw/last-automatic-reboot'

INSTALLATION_UUID = '/var/lib/l2tpgw/installation-uuid'
BOOT_UUID = '/var/run/l2tpgw/boot-uuid'
COOKIE_UUID = '/var/lib/l2tpgw/cookie-uuid'

TIMESYNC_TIMESTAMP_FILE = '/var/run/l2tpgw/timesync-timestamp'
UPDATE_TIMESYNC_TIMESTAMP_FILE = '/var/run/l2tpgw/update-timesync-timestamp'
TIMESYNC_PERSISTENT_TIMESTAMP_FILE = '/var/lib/l2tpgw/timesync-timestamp'

UPDATE_SKIP_MARKER_FILE = '/var/lib/l2tpgw/skip-update-marker'
UPDATE_FORCE_MARKER_FILE = '/var/lib/l2tpgw/force-update-marker'

CONFIGURATION_IMPORT_BOOT_FILE = '/var/lib/l2tpgw/configuration-import.xml'

PRODUCT_ZIPFILE_MAGIC = 'e404eb46-2773-4f49-b3b6-1958388ffebc'
PRODUCT_ZIPFILE_VERSION = 1
PRODUCT_ZIPFILE_NAME_CONFIG_EXPORT = 'vpnease-configuration-export'
PRODUCT_ZIPFILE_NAME_DIAGNOSTICS_EXPORT = 'vpnease-diagnostics-export'

PERIODIC_REBOOT_MAX_UPTIME = 10*24*60*60  # 10 days
PERIODIC_REBOOT_MINIMUM_WATCHDOG_ROUNDS = int(1*60*60 / WEBUI_WATCHDOG_INTERVAL)
WEBUI_PERIODIC_REBOOT_PENDING_TITLE = PRODUCT_NAME
WEBUI_PERIODIC_REBOOT_PENDING_TEXT = 'Automatic maintenance reboot will occur in a few minutes.'
WEBUI_PERIODIC_REBOOT_PENDING_TIMEOUT = 3*60*1000  # 3 minutes

WEBUI_PORT_HTTP = 80
WEBUI_PORT_HTTPS = 443
WEBUI_FORWARD_PORT_UIFORCED_HTTP = 10080
WEBUI_FORWARD_PORT_UIFORCED_HTTPS = 10443
WEBUI_FORWARD_PORT_LICENSE_HTTP = 11080
WEBUI_FORWARD_PORT_LICENSE_HTTPS = 11443
WEBUI_FORWARD_PORT_OLDPSK_HTTP = 12080
WEBUI_FORWARD_PORT_OLDPSK_HTTPS = 12443

LOCAL_ADMINISTRATOR_NAME = 'Local administrator'

FASTBOOT_MARKER_FILE = '/fastboot'
FORCE_FSCK_MARKER_FILE = '/forcefsck'

UPDATE_REPOSITORY_KEYS_FILE = '/var/run/l2tpgw-repository-keys'

SYSLOG_PIDFILE = '/var/run/vpnease-syslog.pid' # Note: do not change this!!!

SYSLOG_DEVICE_FILE = '/dev/log'
SYSLOG_LOGFILE = '/var/log/vpnease-syslog'
SYSLOG_LOGFILE_BACKUP = '/var/log/vpnease-syslog.0'
SYSLOG_LOGFILE_MAX_SIZE = 32*1024*1024 # 32 MiB
SYSLOG_MSG_MAX_SIZE = 1024 # bytes

SYSLOG_EXCEPTION_LOG = '/var/log/vpnease-syslog.err'

SYSLOG_POLL_TIMEOUT = int(30) # 30 seconds
SYSLOG_FLUSH_TIMEOUT = datetime.timedelta(0, 2*60, 0) # 2 minutes

DMESG_LOGFILE = '/var/log/dmesg'

# XXX: what to allow??    
ALLOWED_UNIX_PASSWORD_CHARACTERS = \
                                 "0123456789" + \
                                 "abcdefghijklmnopqrstuvwxyz" + \
                                 "ABCDEFGHIJKLMNOPQRSTUVWXYZ" + \
                                 ",.-()"

DISK_SIZE_MINIMUM = 2*1000*1000*1000                            # 2GB
DISK_SIZE_MINIMUM_FOR_LARGE_INSTALL = int(3.5*1000*1000*1000)   # 3.5GB
DISK_SIZE_SAFETY_MARGIN = 10*1000*1000                          # 10MB

RRDGRAPH_USER_COUNT = '%s/rrdgraph-usercount.png' % RUNTIME_DIRECTORY
RRDGRAPH_SITETOSITE_COUNT = '%s/rrdgraph-sitetositecount.png' % RUNTIME_DIRECTORY

LIVECD_FORCED_REBOOT_STAGE1_DELAY = 0.5  # warming etc is so slow that this is enough
LIVECD_FORCED_REBOOT_STAGE2_DELAY = 5.0

OPENL2TP_CONFIG_LOCK_FILE = '/var/run/l2tpgw/openl2tp-config.lock'

IPTABLES_LOCK_FILE = '/var/run/l2tpgw/iptables.lock'

GNOME_BACKGROUND_IMAGE = '/usr/lib/l2tpgw/gnome-background.png'
GNOME_SPLASH_IMAGE = '/usr/lib/l2tpgw/gnome-splash.png'
GNOME_DESKTOP_ICON_IMAGE = '/usr/lib/l2tpgw/gnome-desktop-icon.png'

PROC_UPTIME = '/proc/uptime'

CONFIGURED_MARKER = '/var/lib/l2tpgw/l2tp-configured'

MEM_MINSIZE = 1024L*218L # In kilobytes
MEM_LOWSIZE = 1024L*474L # In kilobytes

GDM_BACKGROUND_COLOR = '#000000'
GDM_GRAPHICAL_THEMED_COLOR = '#000000'

WEBUI_DEBUG_NAV_MARKERFILE = '/etc/debugnav'
AUTOUPDATE_MARKERFILE = '/etc/autoupdate'
DEBUGGRAPHS_MARKERFILE = '/etc/debuggraphs'
NOPWCHANGE_MARKERFILE = '/etc/nopwchange'
FORCE_NATTREBOOT_MARKERFILE = '/etc/forcenattreboot'

USER_GRAPH_WIDTH = 710
USER_GRAPH_HEIGHT = 120
SITETOSITE_GRAPH_WIDTH = 710
SITETOSITE_GRAPH_HEIGHT = 120

SNMP_DATA_FILE = '/var/run/l2tpgw/snmp-data.txt'
SNMP_MIB_MODULE_SO = '/usr/lib/l2tpgw/vpneaseMIB.so'

PRODUCT_VERSION_CACHE_FILE = '/var/run/l2tpgw/product-version-cache.txt'

DEFAULT_TIMEZONE = 'GMT'

RUNNER_TEMPORARY_SQLITE_DATABASE = '/var/run/l2tpgw/runner-temporary-database.sqlite'
WEBUI_TEMPORARY_SQLITE_DATABASE = '/var/run/l2tpgw/webui-temporary-database.sqlite'
UPDATE_PROCESS_RDFXML_EXPORT_FILE = '/var/lib/l2tpgw/update-configuration-export.xml'

AUTOCONFIG_EXE_WINXP_32BIT = '/usr/lib/l2tpgw/webui-pages/vpnease_autoconfigure_winxp32.exe'
AUTOCONFIG_EXE_WINXP_64BIT = '/usr/lib/l2tpgw/webui-pages/vpnease_autoconfigure_winxp64.exe'
AUTOCONFIG_EXE_VISTA_32BIT = '/usr/lib/l2tpgw/webui-pages/vpnease_autoconfigure_vista32.exe'
AUTOCONFIG_EXE_VISTA_64BIT = '/usr/lib/l2tpgw/webui-pages/vpnease_autoconfigure_vista64.exe'
AUTOCONFIG_EXE_WIN2K_32BIT = '/usr/lib/l2tpgw/webui-pages/vpnease_autoconfigure_win2k32.exe'

AUTOCONFIG_PROFILE_PREFIX_FILE = '/etc/autoconfig-profile-prefix'

MAX_USERNAME_LENGTH = 100
MAX_PASSWORD_LENGTH = 100
MAX_PRE_SHARED_KEY_LENGTH = 100

CUSTOMER_LOGO = '/etc/customer-logo.png'
