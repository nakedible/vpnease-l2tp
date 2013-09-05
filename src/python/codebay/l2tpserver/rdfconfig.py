"""L2TP configuration handling.

NOTE: Almost all namespaced URIs are property URIs (RDF arrows).
However, root elements (for L2TP device and L2TP config) have an
URI for their node.  This URI is used to fetch the node in question.

@var ns_codebay:
    Codebay (1.0) namespace.
    
@var ns_l2tp:
    L2TP configuration namespace.

@var ns_ui:
    L2TP namespace for web UI, includes both exported configuration data
    and UI temporary attributes (e.g. wizard state).
    
@var ns:
    Convenience name for ns_l2tp.
"""
__docformat__ = 'epytext en'

from codebay.common import rdf

ns_codebay = rdf.NS('http://purl.org/NET/codebay/1.0/')

ns_l2tp = rdf.NS(ns_codebay['l2tp/1.0/'],
                 # Global root for L2TP database state
                 l2tpGlobalRoot = None,
                 L2tpGlobalRoot = None,

		 # UI data (pickle)
		 uiDataPickle = None,

                 # Global root for exported L2TP configuration
                 l2tpExportedConfig = None,
                 L2tpExportedConfig = None,

                 # Property for blank root node
                 l2tpDeviceConfig = None,
                 newL2tpDeviceConfig = None,
                 
                 # rdf:type for blank root node
                 L2tpDeviceConfig = None,

                 # Shared types
                 NetworkInterface = None,
                 Route = None,
                 DnsServer = None,
                 WinsServer = None,
                 User = None,

                 # Interface address variants
                 StaticAddress = None,
                 DhcpAddress = None,

                 # Route gateway variants
                 StaticRouter = None,
                 DhcpRouter = None,
                 SiteToSiteRouter = None,
                 
                 # DNS server variants
                 StaticDnsServers = None,
                 DhcpDnsServers = None,

                 # WINS server variants
                 StaticWinsServers = None,
                 DhcpWinsServers = None,

                 # Debug variants
                 DebugNone = None,
                 DebugNormal = None,
                 DebugHeavy = None,

                 # Firewall nodes
                 PortForwardRule = None,
                 InputAcceptRule = None,
                 PppFirewallRule = None,
                 ClientRejectRule = None,  # 1.0 compatibility
                 
                 # Site-to-site roles
                 Client = None,
                 Server = None,
                 
                 # URIs for node-valued properties and their rdf:types
                 networkConfig = None,       NetworkConfig = None,
                 adminConfig = None,         AdminConfig = None,
                 managementConfig = None,    ManagementConfig = None,
                 ipsecConfig = None,         IpsecConfig = None,
                 l2tpConfig = None,          L2tpConfig = None,
                 pppConfig = None,           PppConfig = None,
                 usersConfig = None,         UsersConfig = None,
                 clientRoutes = None,
                 gatewayRoutes = None,
                 qosConfig = None,           QosConfig = None,
                 firewallConfig = None,      FirewallConfig = None,
                 dnsServers = None,          DnsServers = None,
                 pppDnsServers = None,       PppDnsServers = None,
                 pppWinsServers = None,      PppWinsServers = None,
                 pppAuthentication = None,   PppAuthentication = None,
                 pppCompression = None,      PppCompression = None,
                 users = None,               Users = None,
                 dynamicDnsConfig = None,    DynamicDnsConfig = None,
                 addressList = None,
                 siteToSiteUser = None,      SiteToSiteUser = None,
                 preSharedKey = None,        PreSharedKey = None,
                 preSharedKeys = None,
                 radiusConfig = None,        RadiusConfig = None,
                 radiusServers = None,
                 radiusServer = None,        RadiusServer = None,
                 snmpConfig = None,          SnmpConfig = None,
                 action = None,              ActionAllow = None,
                                             ActionDeny = None,
                 pppForcedRouter = None,     PppForcedRouter = None,

                 # URIs for literal properties
                 debug = None,
                 publicInterface = None,
                 privateInterface = None,
                 interfaceName = None,
                 address = None,
                 secret = None,
                 user = None,
                 subnet = None,
                 interface = None,
                 mtu = None,
                 proxyArp = None,
                 nat = None,
                 gateway = None,
                 protocol = None,
                 port = None,
                 destinationAddress = None,
                 destinationPort = None,
                 role = None,
                 provider = None,
                 hostname = None,
                 clientToClientRouting = None,
                 globalUplinkRateLimit = None,
                 portForward = None,
                 inputAccept = None,
                 pppFirewallRules = None,
                 clientReject = None,   # 1.0 compatibility
                 allowNonClientRouting = None,
                 licenseKey = None,
                 maxNormalConnections = None,
                 maxSiteToSiteConnections = None,
                 ikeLifeTime = None,
                 ipsecLifeTime = None,
                 pppSubnet = None,
                 pppRange = None,
                 pppPap = None,  # auth
                 pppChap = None,
                 pppMschap = None,
                 pppMschapV2 = None,
                 pppEap = None,
                 pppMppc = None, # comp
                 pppMppe = None,
                 pppAccomp = None,
                 pppPcomp = None,
                 pppBsdcomp = None,
                 pppDeflate = None,
                 pppPredictor1 = None,
                 pppVj = None,
                 pppCcompVj = None,
                 pppIdleTimeout = None,
                 pppMtu = None,
                 pppLcpEchoInterval = None,
                 pppLcpEchoFailure = None,
                 username = None,
                 password = None,
                 passwordMd5 = None,     # NB: uppercase hex encoded
                 passwordNtHash = None,  # NB: uppercase hex encoded
                 fixedIp = None,
                 forceWebRedirect = None,
                 forceNonPrimaryPskWebRedirect = None,
                 httpForcedRedirectPort = None,
                 httpsForcedRedirectPort = None,
                 httpLicenseRedirectPort = None,
                 httpsLicenseRedirectPort = None,
                 httpNonPrimaryPskRedirectPort = None,
                 httpsNonPrimaryPskRedirectPort = None,
                 snmpCommunity = None,
                 radiusNasIdentifier = None,

                 # dyndns address
                 dynDnsAddress = None,
                 DynDnsInterfaceAddress = None,             # use address of interface
                 DynDnsStaticAddress = None,                # use static address, 'ipAddress' child
                 DynDnsManagementConnectionAddress = None,  # use address from management connection

                 # device installation uuid
                 installationUuid = None,
                 bootUuid = None,
                 
                 # ----------------------------------------

                 # Status branch for protocol-related status.
                 l2tpDeviceStatus = None,      L2tpDeviceStatus = None,

                 # global status properties
                 startTime = None,
                 stopTime = None,
                 lastPollTime = None,
                 state = None,
                 subState = None,
                 lastStateUpdate = None,

                 # states & substates
                 StateStarting = None,
                 StateStartingPreparing = None,
                 StateStartingWaitingForDhcp = None,
                 StateStartingNetwork = None,
                 StateStartingDaemons = None,
                 StateRunning = None,
                 StateStopping = None,
                 StateStopped = None,

                 # forwarding reasons
                 UiRequest = None,
                 LicenseExceeded = None,
                 LicenseInvalid = None,
                 LicenseProhibits = None,

                 # connection types
                 NormalUser = None,
                 SiteToSiteClient = None,
                 SiteToSiteServer = None,
                 
                 # ipsec encapsulation modes
                 EspPlain = None,
                 EspOverUdp = None,

                 pppDevices = None,
                 pppDevice = None,
                 PppDevices = None,
                 retiredPppDevices = None,
                 RetiredPppDevices = None,
                 PppDevice = None,
                 deviceName = None,
                 # username already exists
                 restrictedConnection = None,
                 webForwardedConnection = None,
                 forwardingReason = None,
                 spoofPrevention = None,
                 ipsecPskIndex = None,
                 pppdPid = None,
                 deviceActive = None,
                 connectionType = None,
                 ipsecEncapsulationMode = None,
                 spiRx = None,
                 spiTx = None,
                 locallyAuthenticated = None,
                 pppLocalAddress = None,
                 pppRemoteAddress = None,
                 outerAddress = None,
                 outerPort = None,  # L2TP port, unless udp_encaps True (in which case IKE port)
                 rxBytesCounter = None,
                 txBytesCounter = None,
                 rxPacketsCounter = None,
                 txPacketsCounter = None,
                 rxLastChange = None,
                 txLastChange = None,
                 rxRateMaximum = None,
                 txRateMaximum = None,
                 rxRateCurrent = None,
                 txRateCurrent = None,
                 macAddress = None,
                 ipAddress = None,
                 
                 # XXX: there are lots of ppp parameters - do we want to put them all here?
                 
                 # health checks
                 processHealthCheck = None,
                 routerStatuses = None,
                 routerHealthCheck = None,
                 routeConfigs = None,
                 routerAddress = None,
                 serverStatuses = None,
                 serverAddress = None,
                 serverConfig = None,
                 serverHealthCheck = None,
                 rrdUpdateSucceeded = None,
                 siteToSiteStatuses = None,
                 tunnelConfig = None,
                 tunnelHealthCheck = None,
                 tunnelRemoteAddress = None,
                 
                 # status types
                 RouterStatus = None,
                 ServerStatus = None,
                 SiteToSiteStatus = None,

                 # misc status values
                 addressCheckFailure = None,
                 licenseRestrictedFailure = None,

                 # ----------------------------------------

                 # Status branch for global, non-protocol related status; persists over reboots!
                 globalStatus = None,
                 GlobalStatus = None,
                 
                 cpuUsage = None,
                 cpuCount = None,
                 diskUsage = None,
                 diskTotal = None,
                 memoryUsage = None,
                 memoryTotal = None,
                 swapUsage = None,
                 swapTotal = None,

                 watchdogReboots = None,
                 periodicReboots = None,
                 uncleanRunnerExits = None,
                 managementServerConnection = None,
                 behindNat = None,
                 managementConnectionOurNattedAddress = None,
                 
                 # ----------------------------------------
                 
                 # Comment property, ignore
                 comment = None,
)

ns_ui = rdf.NS(ns_codebay['l2tp/1.0/'],
               # Live CD global root
               liveCdGlobalRoot = None,
               LiveCdGlobalRoot = None,
               targetDevice = None,
               attemptRecovery = None,
               previousConfigurationRdfXml = None,
               previousInstalledVersion = None,
               installHasBeenStarted = None,
               installLargeDisk = None,

               # Markers
               welcomePageShown = None,
               initialConfigSaved = None,

               # License parameters
               licenseInfo = None,
               LicenseInfo = None,
               maxNormalConnections = None,
               maxSiteToSiteConnections = None,
               validityStart = None,
               validityEnd = None,
               validityRecheckLatest = None,
               licenseString = None,
               isDemoLicense = None,
               demoValidityStart = None,
               demoValidityEnd = None,
               
               # Update and package management
               updateInfo = None,
               UpdateInfo = None,
               changeLog = None,
               latestKnownVersion = None,
               
               # UI config
               uiConfig = None,
               newUiConfig = None,
               UiConfig = None,
               
               # Network configuration
               NetworkConnection = None,
               internetConnection = None,
               privateNetworkConnection = None,
               address = None,

               # Address type is either static or dhcp
               StaticAddress = None,
               DhcpAddress = None,
               
               # General address related
               ipAddress = None,
               subnet = None,
               subnetMask = None,
               port = None,
               protocol = None,
               action = None,
               Subnet = None,

               # Internet (and private network) connection
               interface = None,
               defaultGateway = None,
               mtu = None,
               vpnUplink = None,
               clientConnectionNat = None,
               clientConnectionProxyArp = None,

               # DNS servers
               dnsServers = None,
               InternetConnectionDhcp = None,
               PrivateNetworkConnectionDhcp = None,
               SetDnsServers = None,
               primaryDns = None,
               secondaryDns = None,

               # DynDNS
               dynDnsServer = None,
               DynDnsServer = None,
               dynDnsProvider = None,
               dynDnsUsername = None,
               dynDnsPassword = None,
               dynDnsHostname = None,
               dynDnsAddress = None,    # empty (iface), ip address, or 'natted' (management conn.)
               
               # Routes
               defaultRoute = None,
               InternetConnectionRoute = None,
               PrivateNetworkConnectionRoute = None,
               routeGateway = None,
               RouteGatewayNetworkDefault = None,
               RouteGatewayManual = None,
               routes = None,
               Route = None,
               route = None,

               # Source routing
               sourceRouting = None,

               # Prohibited services
               prohibitedServices = None,   # 1.0 compatibility
               ProhibitedService = None,    # 1.0 compatibility

               # PPP firewal rules
               pppFirewallRules = None,
               PppFirewallRule = None,

               # Client connection
               clientDnsServers = None,
               NetworkConnectionDns = None,
               clientSubnet = None,
               clientAddressRange = None,
               vpnServerAddress = None,
               preSharedKey = None,
               preSharedKeys = None,     PreSharedKey = None,
               clientPrimaryWins = None,
               clientSecondaryWins = None,
               clientCompression = None,
               portForwards = None,
               PortForward = None,
               firewallInUse = None,
               incomingPort = None,
               destinationPort = None,

               # Site to site
               username = None,
               password = None,
               passwordMd5 = None,     # NB: uppercase hex encoded
               passwordNtHash = None,  # NB: uppercase hex encoded
               subnetList = None,
               siteToSiteConnections = None,   SiteToSiteConnection = None,
               serverAddress = None,
               mode = None,

               # Users
               users = None,
               User = None,
               email = None,
               fixedIp = None,
               adminRights = None,
               vpnRights = None,
               passwordChangeRights = None,
               sendInstallationEmail = None,

               # RADIUS
               radiusPrimaryServer = None,
               radiusPrimaryServerPort = None,
               radiusPrimarySecret = None,
               radiusSecondaryServer = None,
               radiusSecondaryServerPort = None,
               radiusSecondarySecret = None,
               radiusNasIdentifier = None,

               # Management
               timezone = None,
               keymap = None,
               periodicRebootDay = None,   # mon=0 ... sun=6
               periodicRebootTime = None,  # hours since midnight, local time; e.g. day=monday, time=0 means reboot right after sunday ends
               automaticUpdates = None,
               webAccessPublic = None,
               webAccessPrivate = None,
               sshAccessPublic = None,
               sshAccessPrivate = None,
               snmpAccessPublic = None,
               snmpAccessPrivate = None,
               snmpCommunity = None,
               adminEmailSmtpServer = None,
               adminEmailFromAddress = None,
               adminEmailToAddresses = None,
               
               # License
               licenseKey = None,
               testLicenseKey = None,

               # SSL certificate(s)
               publicSslCertificateChain = None,
               publicSslPrivateKey = None,
               privateSslCertificateChain = None,  # XXX: unused for now
               privateSslPrivateKey = None,        # XXX: unused for now

               # Collapse settings - these would ideally be user specific but no luck now
               collapseInterfaceCount = None,
               collapseInternetConnection = None,
               collapsePrivateNetwork = None,
               collapseDns = None,
               collapseDynamicDns = None,
               collapseDefaultRoute = None,
               collapseAdditionalRoutes = None,
               collapseSourceRouting = None,
               collapsePppFirewallRules = None,
               collapseClientConnection = None,
               collapseFirewall = None,
               collapsePortForwardingRules = None,
               collapseRadius = None,
               collapseSnmp = None,
               collapseLicense = None,
               collapseLocale = None,
               collapseProductMaintenance = None,
               collapseRemoteManagement = None,
               collapseSslCertificate = None,
               collapseAdminEmail = None,
               
               # Debug
               debug = None
)

# zip file types, see architecture document and L2tpZipFiles
ns_zipfiles = rdf.NS(ns_codebay['l2tp/1.0/'],
                     configurationExport = None,
                     diagnosticsExport = None,
)

# for convenience
ns = ns_l2tp
