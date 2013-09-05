"""Helpers for dealing with UI data."""
__docformat__ = 'epytext en'

import sys, datetime

from twisted.internet import reactor, defer

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.common import passwordgen
from codebay.common import randutil

from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver.rdfconfig import ns
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import pppscripts
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.uidatahelpers')

from codebay.l2tpserver import runcommand
run_command = runcommand.run_command


class Error(Exception):
    """Generic error."""

class DefaultValueMissing(Error):
    """No default value currently defined.

    This is thrown when the database creation code encounters a situation where no default
    has been currently defined.  This is more of a 'FIXME': if defaults are changed so that
    new default values are needed (e.g. public interface changed from DHCP to static address,
    in which case a static default address would be needed) this exception is thrown from
    code branches which are currently unreachable.
    """
    
class RdfDataError(Error):
    """Missing or invalid RDF data in UI (RDF) configuration."""

class FormDataError(Error):
    """Saving data tries to access invalid form field or form selection is unknown."""

class InvalidParameter(Error):
    """Function parameter is not valid."""
    
class UiDataConversionError(Error):
    """Error in UI data to protocol data conversion."""

# --------------------------------------------------------------------------

DESTINATION_NETWORKS = ['internet', 'private']

# --------------------------------------------------------------------------
#
#  UI defaults
#
class _UiDefaults:
    """Placeholder for UI default values."""

    def __init__(self):
        self._fill_defaults()
        
    def _fill_defaults(self):
        self.DEBUG = '0'
        self.INTERNET_CONNECTION_INTERFACE_NAME = 'eth0'
        self.INTERNET_CONNECTION_DHCP_IN_USE = True
        self.INTERNET_CONNECTION_UPLINK = 2048  # XXX - unused
        self.INTERNET_CONNECTION_MTU = 1440
        self.INTERNET_CONNECTION_CLIENT_CONNECTION_NAT = True
        self.INTERNET_CONNECTION_CLIENT_CONNECTION_PROXY_ARP = False
        self.INTERNET_CONNECTION_PUBLIC_NAT_IN_USE = True
        self.INTERNET_CONNECTION_PUBLIC_PROXY_ARP_IN_USE = False
        self.INTERNET_CONNECTION_SOURCE_ROUTE_IN_USE = False

        self.PRIVATE_NETWORK_CONNECTION_INTERFACE_NAME = 'eth1'
        self.PRIVATE_NETWORK_CONNECTION_DHCP_IN_USE = True
        self.PRIVATE_NETWORK_CONNECTION_CLIENT_CONNECTION_NAT = True
        self.PRIVATE_NETWORK_CONNECTION_CLIENT_CONNECTION_PROXY_ARP = False
        self.PRIVATE_NETWORK_CONNECTION_PUBLIC_NAT_IN_USE = True
        self.PRIVATE_NETWORK_CONNECTION_PUBLIC_PROXY_ARP_IN_USE = False
        self.PRIVATE_NETWORK_CONNECTION_SOURCE_ROUTE_IN_USE = False

        self.DNS_SERVERS = 'internet'
        self.ROUTE_GATEWAY = ['nw_default_gw', 'manual_gw']
        self.DEFAULT_ROUTE_DESTINATION = 'internet'
        self.DEFAULT_ROUTE_GATEWAY_ADDRESS = None
        
        # XXX: In lieu of a working logic to add these routes as "conditional" (only when
        # private network exists), default is now set to no additional routes.  Otherwise
        # these will point to the Internet, which is insane.
        #self.ROUTES = [{'subnet':'10.0.0.0/8', 'destination':'internet', 'gateway_address': None},
        #          {'subnet':'172.16.0.0/12', 'destination':'internet', 'gateway_address': None},
        #          {'subnet':'192.168.0.0/16', 'destination':'internet', 'gateway_address': None}]
        self.ROUTES = []

        self.FIREWALL_IN_USE = True

        # Config test page routes
        self.ROUTES_GATEWAY_ROUTE1_ADDRESS = '0.0.0.0/0'
        self.ROUTES_GATEWAY_ROUTE1_INTERFACE = 'public'
        self.ROUTES_GATEWAY_ROUTE1_GATEWAY = ''
        self.ROUTES_GATEWAY_ROUTE2_ADDRESS = ''
        self.ROUTES_GATEWAY_ROUTE2_INTERFACE = ''
        self.ROUTES_GATEWAY_ROUTE2_GATEWAY = ''
        self.ROUTES_GATEWAY_ROUTE3_ADDRESS = ''
        self.ROUTES_GATEWAY_ROUTE3_INTERFACE = ''
        self.ROUTES_GATEWAY_ROUTE3_GATEWAY = ''

        self.ROUTES_CLIENT_ROUTE1_ADDRESS = '0.0.0.0/0'
        self.ROUTES_CLIENT_ROUTE1_INTERFACE = 'public'
        self.ROUTES_CLIENT_ROUTE1_GATEWAY = ''
        self.ROUTES_CLIENT_ROUTE2_ADDRESS = ''
        self.ROUTES_CLIENT_ROUTE2_INTERFACE = ''
        self.ROUTES_CLIENT_ROUTE2_GATEWAY = ''
        self.ROUTES_CLIENT_ROUTE3_ADDRESS = ''
        self.ROUTES_CLIENT_ROUTE3_INTERFACE = ''
        self.ROUTES_CLIENT_ROUTE3_GATEWAY = ''

        # user information
        self.USER_RIGHTS_ADMIN = False
        self.USER_RIGHTS_PPP_USER = True
        self.USER_RIGHTS_CHANGE_PASSWORD = True
        self.USER_RIGHTS_ACCOUNT_ENABLED = True

        # client connection
        self.CLIENT_CONNECTION_DNS_SERVERS = 'network'
        self.CLIENT_SUBNET = '192.168.100.0/24'
        self.CLIENT_RANGE = '192.168.100.1-192.168.100.253'
        self.CLIENT_TO_CLIENT_ROUTING = False
        self.CLIENT_COMPRESSION = True
        self.VPN_SERVER_ADDRESS = ''

        # ipsec
        self.IPSEC_IKE_LIFETIME = datetime.timedelta(0, 8*60*60, 0)
        self.IPSEC_IPSEC_LIFETIME = datetime.timedelta(0, 8*60*60, 0)

        # PPP authentication - PAP and MSCHAPv2 only
        # Some reasons:
        #   - PAP enabled, because it is the fallback method for almost all products.
        #   - CHAP does not work well with RADIUS, it requires RADIUS server to store
        #     plaintext passwords which many want to avoid.
        #   - MSCHAPv1 is not as good as MSCHAPv2 feature-wise; further, all our clients
        #     support neither MSCHAP variant or both, so MSCHAPv1 support is unnecessary.
        #     Finally, there were some earlier problems with pppd + MSCHAPv1 with Pocket PC.
        #   - MSCHAPv2 is supported by Windows IAS and allows even password changing
        #   - EAP didn't work together with some clients and is not supported by all RADIUS
        #     servers.  It is also currently untested.
        self.AUTH_PPP_PAP = True
        self.AUTH_PPP_CHAP = False
        self.AUTH_PPP_MS_CHAP = False
        self.AUTH_PPP_MS_CHAP_V2 = True
        self.AUTH_PPP_EAP = False

        # ppp
        #self.PPP_IDLE_TIMEOUT = datetime.timedelta(0, 30*60, 0)    # 30 mins
        self.PPP_LCP_ECHO_INTERVAL = datetime.timedelta(0, 60, 0)
        self.PPP_LCP_ECHO_FAILURE = 5
        
        # management
        self.TIMEZONE = 'GMT'
        self.KEYMAP = 'us'
        self.REBOOT_DAY = 6  # sunday
        self.REBOOT_TIME = 0 # midnight; reboot right after saturday ends
        self.AUTOMATIC_UPDATES = False
        self.WEB_ACCESS_PUBLIC = True
        self.SSH_ACCESS_PUBLIC = False
        self.WEB_ACCESS_PRIVATE = True
        self.SSH_ACCESS_PRIVATE = False
        self.ROOT_PASSWORD = ''

# XXX: singleton now holds defaults to make this a bit easier
uidefaults = _UiDefaults()

# --------------------------------------------------------------------------
# 
#  Helper functions for filling RDF values to form.
# 

# XXX: needs some commenting... name is misleading; in which case is there a missing
# key and in which case a None value?
def has_form_value(fda, fda_field):
    """Gets a form value.

    Returns true if the value exists and false if the value does not exist.
    """

    if not(fda.has_key(fda_field)):
        raise FormDataError('Field ' + fda_field + ' not found.')
    if fda[fda_field] is None:
        return False
    return True

def fill_optional_field_to_form(rdf_node, predicate, type, fda, fda_field):
    """Checks if the optional field has a value in a database and if the value exists, sets it to form data.

    The value set for form field is in the RDF->Python value space (e.g. datatypes.IPv4Address).
    """
    if rdf_node.hasS(predicate):
        fda[fda_field] = rdf_node.getS(predicate, type)
        
def fill_subnet_list_to_form(rdf_node, rdf_pred, fda, fda_field):
    """Fills a list of subnets to a form field.

    rdf_node predicate rdf_pred should contain an RDF Seq of ns_ui.Subnet type,
    each containing an ns_ui.subnet predicate with rdf.IPv4Subnet type.
    """
    subnet_list = []

    for subnet in rdf_node.getS(rdf_pred, rdf.Seq(rdf.Type(ns_ui.Subnet))):
        subnet_list.append(subnet.getS(ns_ui.subnet, rdf.IPv4Subnet))
    
    fda[fda_field] = subnet_list  

def fill_dynamic_list_to_form(rdf_root, list_predicate, list_type, fda, callback):
    """Handles dynamic list for form fill.

    Assumes that form creation has already made all the elements
    for all the s2s clients. Otherwise form data contains data, but they have no visible components.
    """
    if rdf_root.hasS(list_predicate):
        list_index = 0
        for list_node in rdf_root.getS(list_predicate, rdf.Seq(rdf.Type(list_type))):
            list_fda = fda.descend(str(list_index))
            callback(list_node, list_fda)         
            list_index += 1

# 
# Helper functions for saving form values to rdf.
#
def save_optional_field_to_rdf(rdf_node, predicate, type, fda, fda_field, default=None):
    """Checks if form data has a non-empty value.

    If there is a value, saves it to database.
    If there is no value and default value is given, saves default value to database.
    If there is no value and no default value is given, removes predicate from node.
    """
    if has_form_value(fda, fda_field):
        rdf_node.setS(predicate, type, fda[fda_field])
    else:
        if default is not None:
            rdf_node.setS(predicate, type, default)
        else:
            if rdf_node.hasS(predicate):
                rdf_node.removeNodes(predicate)

def create_rdf_route(route_root, subnet, destination, gateway_address, route_type):
    """Creates a route to rdf database from given parameters."""

    # Check params

    if not(destination in DESTINATION_NETWORKS):
        raise InvalidParameter('Route destination is unknown.')
  
    if destination == 'internet':
        route_node = route_root.setS(route_type, rdf.Type(ns_ui.InternetConnectionRoute))
    else:
        route_node = route_root.setS(route_type, rdf.Type(ns_ui.PrivateNetworkConnectionRoute))    
    
    if subnet is not None:
        route_node.setS(ns_ui.subnet, rdf.IPv4Subnet, subnet)
    else:
        # Note: This is valid configuration: default route and source
        # routes do not have a subnet
        pass

    if gateway_address is None:
        route_node.setS(ns_ui.routeGateway, rdf.Type(ns_ui.RouteGatewayNetworkDefault))
    else:
        route_gw = route_node.setS(ns_ui.routeGateway, rdf.Type(ns_ui.RouteGatewayManual))
        route_gw.setS(ns_ui.ipAddress, rdf.IPv4Address, gateway_address)
       
def save_subnet_list_to_rdf(rdf_node, rdf_pred, fda, fda_field):
    """Save subnet list from a form field to RDF."""
    subnet_root = rdf_node.setS(rdf_pred, rdf.Seq(rdf.Type(ns_ui.Subnet)))
    for subnet in fda[fda_field]:
        subnet_node = subnet_root.new()
        subnet_node.setS(ns_ui.subnet, rdf.IPv4Subnet, subnet)
            
def save_dynamic_list_to_rdf(rdf_node, list_predicate, item_type, fda, callback):
    """Saves dynamic list to RDF.

    Handles dynamic list, calls callback function for saving fields."""

    # nukes old data
    root_node = rdf_node.setS(list_predicate, rdf.Seq(rdf.Type(item_type)))

    list_index = 0
    while True:
        list_fda = fda.descend(str(list_index))
        if len(list_fda.keys()) == 0:
            break

        list_node = root_node.new()
        callback(list_node, list_fda)
        list_index += 1
            

# --------------------------------------------------------------------------
#
#  Default database and import handling
#

@db.transact()
def fix_missing_database_values(initial_database=False):
    """Check and fix missing database values.

    This is used during bootup for various reasons.  Primarily this function
    is intended to fix missing values to default ones after an import.  After
    any missing values have been fixed, it should be possible to generate a
    protocol config; hence the defaults must be acceptable values.  For instance,
    if one pre-shared key is mandatory, this function must (and does) generate a
    random pre-shared key to make the defaulted configuration valid.

    This function is also used to initialize default values to an entirely
    empty web UI configuration root.
    
    This function is not completely bullet-proof.  For instance, it doesn't always
    sanity check rdf getS() calls, and may thus raise an Exception in exceptional
    circumstances (when web UI data is corrupt and not merely missing).  This is
    handled by the startup scripts by catching the Exception, and attempting to
    fix the RDF database by defaulting to known good, or starting from scratch.
    Hence it suffices here to make a best effort, assuming a more or less consistent
    web UI database with possibly missing values.

    There is a slight difference in creating a fresh database, versus fixing
    missing values from older database versions.  For instance, new markers
    such as 'initial config page shown' default to False when creating initial
    database, but otherwise default to True.

    Returns 0 if no fixes were made, and the number of fixes otherwise.
    """

    # This silliness is because of Python scoping rules
    class _FixCount:
        def __init__(self):
            self.fixcount = 0

        def inc(self):
            self.fixcount += 1
            
    fixcount = _FixCount()
    root = db.get_db().getRoot()
    ui_root = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))

    def _check_default(rdf_node, rdf_uri, rdf_type, default_value):
        """Helper for dealing with defaults a bit more conveniently."""
        need_default = False

        if rdf_node is None:
            rdf_node = ui_root

        if rdf_node.hasS(rdf_uri):
            # XXX: not prettiest possible, but hasType does not take the same parameter as getS dataclass
            try:
                n = rdf_node.getS(rdf_uri, rdf_type)
            except:
                need_default = True
        else:
            need_default = True

        if need_default:
            fixcount.inc()
            _log.info('fix_missing_database_values(): filling %s with default value %s' % (rdf_uri, default_value))
            rdf_node.setS(rdf_uri, rdf_type, default_value)

    def _check_internet_connection():
        if ui_root.hasS(ns_ui.internetConnection):
            # XXX: does not check type
            ic_root = ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
        else:
            fixcount.inc()
            _log.info('fix_missing_database_values(): creating %s' % ns_ui.internetConnection)
            ic_root = ui_root.setS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))

        _check_default(ic_root, ns_ui.interface, rdf.String, uidefaults.INTERNET_CONNECTION_INTERFACE_NAME)

        ic_fix_addr = False
        if ic_root.hasS(ns_ui.address):
            ic_addr = ic_root.getS(ns_ui.address)
            if ic_addr.hasType(ns_ui.DhcpAddress):
                pass
            elif ic_addr.hasType(ns_ui.StaticAddress):
                # XXX: check address
                pass
            else:
                ic_fix_addr = True
        else:
            ic_fix_addr = True
        if ic_fix_addr:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing public interface address to dhcp')
            ic_root.setS(ns_ui.address, rdf.Type(ns_ui.DhcpAddress))

        _check_default(ic_root, ns_ui.mtu, rdf.Integer, uidefaults.INTERNET_CONNECTION_MTU)
        _check_default(ic_root, ns_ui.clientConnectionNat, rdf.Boolean, uidefaults.INTERNET_CONNECTION_CLIENT_CONNECTION_NAT)
        _check_default(ic_root, ns_ui.clientConnectionProxyArp, rdf.Boolean, uidefaults.INTERNET_CONNECTION_CLIENT_CONNECTION_PROXY_ARP)

    def _check_private_network_connection():
        pn_root = None
        
        if ui_root.hasS(ns_ui.privateNetworkConnection):
            # XXX: does not check type
            pn_root = ui_root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
        else:
            pass

        if pn_root is None:
            # missing, that's ok
            return

        _check_default(pn_root, ns_ui.interface, rdf.String, uidefaults.PRIVATE_NETWORK_CONNECTION_INTERFACE_NAME)
                       
        pn_fix_addr = False
        if pn_root.hasS(ns_ui.address):
            pn_addr = pn_root.getS(ns_ui.address)
            if pn_addr.hasType(ns_ui.DhcpAddress):
                pass
            elif pn_addr.hasType(ns_ui.StaticAddress):
                # XXX: check address
                pass
            else:
                pn_fix_addr = True
        else:
            pn_fix_addr = True
        if pn_fix_addr:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing private interface address to dhcp')
            pn_root.setS(ns_ui.address, rdf.Type(ns_ui.DhcpAddress))

        _check_default(pn_root, ns_ui.clientConnectionNat, rdf.Boolean, uidefaults.PRIVATE_NETWORK_CONNECTION_CLIENT_CONNECTION_NAT)
        _check_default(pn_root, ns_ui.clientConnectionProxyArp, rdf.Boolean, uidefaults.PRIVATE_NETWORK_CONNECTION_CLIENT_CONNECTION_PROXY_ARP)
    
    def _check_dyndns():
        if ui_root.hasS(ns_ui.dynDnsServer):
            ddns_root = ui_root.getS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))

            # new in 1.1 2008/q2
            _check_default(ddns_root, ns_ui.dynDnsAddress, rdf.String, '')
        else:
            pass
    
    def _check_dns_servers():
        dns_fix = False
        
        if ui_root.hasS(ns_ui.dnsServers):
            dns = ui_root.getS(ns_ui.dnsServers)
            if dns.hasType(ns_ui.SetDnsServers):
                pass
            elif dns.hasType(ns_ui.InternetConnectionDhcp):
                pass
            elif dns.hasType(ns_ui.PrivateNetworkConnectionDhcp):
                pass
            else:
                dns_fix = True
        else:
            dns_fix = True

        if dns_fix:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing dns servers to %s' % uidefaults.DNS_SERVERS)
            if uidefaults.DNS_SERVERS == 'internet':
                ui_root.setS(ns_ui.dnsServers, rdf.Type(ns_ui.InternetConnectionDhcp))
            elif uidefaults.DNS_SERVERS == 'private':
                ui_root.setS(ns_ui.dnsServers, rdf.Type(ns_ui.PrivateNetworkConnectionDhcp))
            else:
                raise DefaultValueMissing('Default DNS server address has not been defined.')

    def _check_route(r, has_subnet):
        fix_route = False
        
        if r.hasType(ns_ui.InternetConnectionRoute):
            pass
        elif r.hasType(ns_ui.PrivateNetworkConnectionRoute):
            pass
        else:
            fix_route = True

        if r.hasS(ns_ui.subnet):
            # XXX: type
            if has_subnet:
                pass
            else:
                fix_route = True
        else:
            if has_subnet:
                fix_route = True
            else:
                pass
            
        if r.hasS(ns_ui.routeGateway):
            gw = r.getS(ns_ui.routeGateway)
            if gw.hasType(ns_ui.RouteGatewayNetworkDefault):
                pass
            elif gw.hasType(ns_ui.RouteGatewayManual):
                if gw.hasS(ns_ui.ipAddress):
                    # XXX: type
                    pass
                else:
                    fix_route = True
            else:
                fix_route = True
        else:
            fix_route = True

        return fix_route
    
    def _check_routes():
        fix_default_route = False
        if ui_root.hasS(ns_ui.defaultRoute):
            fix_default_route = _check_route(ui_root.getS(ns_ui.defaultRoute), has_subnet=False)
        else:
            fix_default_route = True

        if fix_default_route:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing default route')
            create_rdf_route(ui_root, None, uidefaults.DEFAULT_ROUTE_DESTINATION, uidefaults.DEFAULT_ROUTE_GATEWAY_ADDRESS, ns_ui.defaultRoute)   

        fix_source_route = False
        if ui_root.hasS(ns_ui.sourceRouting):
            fix_source_route = _check_route(ui_root.getS(ns_ui.sourceRouting), has_subnet=False)
        else:
            # missing is OK
            pass

        if fix_source_route:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing source route to none')
            ui_root.removeNodes(ns_ui.sourceRouting)

        # XXX: source routing (forced routing) is off by default, which is signaled by missing ns_ui.sourceRouting node (!)
        fix_routes = False   # fix = nuke them
        if ui_root.hasS(ns_ui.routes):
            try:
                for ui_route in ui_root.getS(ns_ui.routes, rdf.Seq(rdf.Type(ns_ui.Route))):
                    if ui_route.hasS(ns_ui.route):
                        tmp = _check_route(ui_route.getS(ns_ui.route), has_subnet=True)
                        if tmp:
                            fix_routes = True
                    else:
                        fix_routes = True
            except:
                _log.exception('route check failed, fixing routes')
                fix_routes = True
        else:
            fix_routes = True

        if fix_routes:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing additional routes to empty list')
            
            # XXX: this is currently an empty routes list, because we cannot have a good default now
            # (with single interface setup)
            routes_root = ui_root.setS(ns_ui.routes, rdf.Seq(rdf.Type(ns_ui.Route)))
            for route in uidefaults.ROUTES:
                route_node = routes_root.new() 
                create_rdf_route(route_node, route['subnet'], route['destination'], route['gateway_address'], ns_ui.route)      

    def _check_client_connection():
        fix_dns = False
        if ui_root.hasS(ns_ui.clientDnsServers):
            t = ui_root.getS(ns_ui.clientDnsServers)
            if t.hasType(ns_ui.NetworkConnectionDns):
                pass
            elif t.hasType(ns_ui.SetDnsServers):
                # XXX: check values
                pass
            else:
                fix_dns = True
        else:
            fix_dns = True
            
        if fix_dns:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing client dns to network dns')

            if uidefaults.CLIENT_CONNECTION_DNS_SERVERS == 'network':
                ui_root.setS(ns_ui.clientDnsServers, rdf.Type(ns_ui.NetworkConnectionDns))
            else:
                raise DefaultValueMissing('Client connection default dns servers has not been defined.')

        # there is no easy check for wins - if present, we could check for types
        fix_wins = False
        if ui_root.hasS(ns_ui.clientPrimaryWins):
            # XXX: could check address and type
            pass
        else:
            pass  # ok
        if ui_root.hasS(ns_ui.clientSecondaryWins):
            # XXX: could check address and type
            pass
        else:
            pass  # ok

        if fix_wins:
            # XXX: nothing to do
            pass

        _check_default(ui_root, ns_ui.clientSubnet, rdf.IPv4Subnet, uidefaults.CLIENT_SUBNET)
        _check_default(ui_root, ns_ui.clientAddressRange, rdf.IPv4AddressRange, uidefaults.CLIENT_RANGE)
        _check_default(ui_root, ns_ui.vpnServerAddress, rdf.String, uidefaults.VPN_SERVER_ADDRESS)
        _check_default(ui_root, ns_ui.clientCompression, rdf.Boolean, uidefaults.CLIENT_COMPRESSION)

        fix_psks = False
        if ui_root.hasS(ns_ui.preSharedKeys):
            try:
                for psk in ui_root.getS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey))):
                    # XXX: any reasonable checks?
                    pass
            except:
                _log.exception('failed in checking psk_seq')
                fix_psks = True                
        else:
            fix_psks = True

        if fix_psks:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing psk list')
            psk_seq = ui_root.setS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey)))
            psk = psk_seq.new()
            psk.setS(ns_ui.preSharedKey, rdf.String, passwordgen.generate_password())

    def _check_firewall():
        _check_default(ui_root, ns_ui.firewallInUse, rdf.Boolean, uidefaults.FIREWALL_IN_USE)

        fix_fwrule = False
        if ui_root.hasS(ns_ui.pppFirewallRules):
            # XXX: checks
            pass
        else:
            fix_fwrule = True

        if fix_fwrule:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing ppp firewall rules')
            ui_root.setS(ns_ui.pppFirewallRules, rdf.Seq(rdf.Type(ns_ui.PppFirewallRule)))

        fix_forw = False
        if ui_root.hasS(ns_ui.portForwards):
            # XXX checks
            pass
        else:
            fix_forw = True

        if fix_forw:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing port forwarding entries')
            ui_root.setS(ns_ui.portForwards, rdf.Seq(rdf.Type(ns_ui.PortForward)))

    def _check_convert_prohibited_services_to_ppp_firewall_rules():
        if not ui_root.hasS(ns_ui.prohibitedServices):
            return

        fixcount.inc()
        _log.info('fix_missing_database_values(): converting prohibited services to firewall rules')

        try:
            fwrule_seq = ui_root.setS(ns_ui.pppFirewallRules, rdf.Seq(rdf.Type(ns_ui.PppFirewallRule)))
            for proh in ui_root.getS(ns_ui.prohibitedServices, rdf.Seq(rdf.Type(ns_ui.ProhibitedService))):
                fr = fwrule_seq.new()
                fr.setS(ns_ui.subnet, rdf.IPv4Subnet, proh.getS(ns_ui.subnet, rdf.IPv4Subnet))
                if proh.hasS(ns_ui.protocol):
                    fr.setS(ns_ui.protocol, rdf.String, proh.getS(ns_ui.protocol, rdf.String))
                else:
                    pass
                if proh.hasS(ns_ui.port):
                    fr.setS(ns_ui.port, rdf.Integer, proh.getS(ns_ui.port, rdf.Integer))
                else:
                    pass
                fr.setS(ns_ui.action, rdf.String, 'deny')
        except:
            _log.exception('failed to convert prohibited services, ignoring (prohibited firewall rules will be deleted)')

        try:
            ui_root.removeNodes(ns_ui.prohibitedServices)
        except:
            _log.exception('failed to delete prohibited services list, ignoring')
            
    def _check_users():
        fix_users = False
        if ui_root.hasS(ns_ui.users):
            try:
                for usr in ui_root.getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User))):
                    # convert passwords to hashed form
                    if not usr.hasS(ns_ui.password):
                        # already converted
                        continue

                    username = usr.getS(ns_ui.username, rdf.String)
                    password = usr.getS(ns_ui.password, rdf.String)

                    _log.info('converting user %s password to hashed form' % username)
                    
                    uihelpers.set_user_password_hashes(usr, password)

                    fixcount.inc()
            except:
                _log.exception('failed users check, fixing')
                fix_users = True
        else:
            fix_users = True

        if fix_users:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing users list')
            ui_root.setS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User)))

    def _check_sitetosite():
        fix_s2s = False
        if ui_root.hasS(ns_ui.siteToSiteConnections):
            try:
                for s2s in ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection))):
                    # XXX: checks?

                    # NB: site-to-site passwords are *not* hashed
                    pass
            except:
                _log.exception('failed s2s check, fixing')
                fix_s2s = True
        else:
            fix_s2s = True

        if fix_s2s:
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing site-to-site list')
            ui_root.setS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection)))

    def _check_radius():
        _check_default(ui_root, ns_ui.radiusPrimaryServer, rdf.String, '')
        _check_default(ui_root, ns_ui.radiusPrimaryServerPort, rdf.Integer, 1812)
        _check_default(ui_root, ns_ui.radiusPrimarySecret, rdf.String, '')
        _check_default(ui_root, ns_ui.radiusSecondaryServer, rdf.String, '')
        _check_default(ui_root, ns_ui.radiusSecondaryServerPort, rdf.Integer, 1812)
        _check_default(ui_root, ns_ui.radiusSecondarySecret, rdf.String, '')
        _check_default(ui_root, ns_ui.radiusNasIdentifier, rdf.String, '')
        
    def _check_snmp():
        _check_default(ui_root, ns_ui.snmpAccessPublic, rdf.Boolean, False)
        _check_default(ui_root, ns_ui.snmpAccessPrivate, rdf.Boolean, False)
        _check_default(ui_root, ns_ui.snmpCommunity, rdf.String, 'public')

    def _check_management():
        _check_default(ui_root, ns_ui.licenseKey, rdf.String, '')
        _check_default(ui_root, ns_ui.timezone, rdf.String, uidefaults.TIMEZONE)
        _check_default(ui_root, ns_ui.keymap, rdf.String, uidefaults.KEYMAP)
        _check_default(ui_root, ns_ui.periodicRebootDay, rdf.Integer, uidefaults.REBOOT_DAY)
        _check_default(ui_root, ns_ui.periodicRebootTime, rdf.Integer, uidefaults.REBOOT_TIME)
        _check_default(ui_root, ns_ui.automaticUpdates, rdf.Boolean, uidefaults.AUTOMATIC_UPDATES)
        _check_default(ui_root, ns_ui.webAccessPublic, rdf.Boolean, uidefaults.WEB_ACCESS_PUBLIC)
        _check_default(ui_root, ns_ui.sshAccessPublic, rdf.Boolean, uidefaults.SSH_ACCESS_PUBLIC)
        _check_default(ui_root, ns_ui.webAccessPrivate, rdf.Boolean, uidefaults.WEB_ACCESS_PRIVATE)
        _check_default(ui_root, ns_ui.sshAccessPrivate, rdf.Boolean, uidefaults.SSH_ACCESS_PRIVATE)
        # XXX: add private later
        _check_default(ui_root, ns_ui.publicSslCertificateChain, rdf.String, '')
        _check_default(ui_root, ns_ui.publicSslPrivateKey, rdf.String, '')
        # XXX: not yet implemented
        #_check_default(ui_root, ns_ui.adminEmailSmtpServer, rdf.String, '')
        #_check_default(ui_root, ns_ui.adminEmailFromAddress, rdf.String, '')
        #_check_default(ui_root, ns_ui.adminEmailToAddresses, rdf.String, '')
        
    def _check_misc():
        _check_default(ui_root, ns_ui.welcomePageShown, rdf.Boolean, False)
        if initial_database:
            _check_default(ui_root, ns_ui.initialConfigSaved, rdf.Boolean, False)
        else:
            _check_default(ui_root, ns_ui.initialConfigSaved, rdf.Boolean, True)

    def _check_retired_devices():
        # XXX: not strictly a web UI value
        global_status = root.getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))
        if not global_status.hasS(ns.retiredPppDevices):
            fixcount.inc()
            _log.info('fix_missing_database_values(): fixing missing retired ppp devices node')
            retiredpppdevs = global_status.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))

    _check_internet_connection()
    _check_private_network_connection()
    _check_dyndns()
    _check_dns_servers()
    _check_routes()
    _check_client_connection()
    _check_firewall()
    _check_convert_prohibited_services_to_ppp_firewall_rules()
    _check_firewall()  # do this twice intentionally, again after possible conversion
    _check_users()
    _check_sitetosite()
    _check_radius()
    _check_snmp()
    _check_management()
    _check_misc()
    _check_retired_devices()
    
    return fixcount.fixcount

@db.transact()
def create_default_database():        
    try: 
        root = db.get_db().getRoot()

        # Create uiConfig dataroot
        ui_root = root.setS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))

        # Fix missing data values => creates a full default config
        fix_missing_database_values(initial_database=True)

        # Convert uidata to protocol data
        pd = CreateProtocolData()
        pd.save_protocol_data(use_current_config=True)
        pd.activate_protocol_data(use_current_config=True)

    except:
        _log.exception('failed to create default database')
        raise
            
# --------------------------------------------------------------------------
# 
#  Save UI (RDF) data to protocol data.
#

class CreateProtocolData:
    """Creates a protocol rdf data from UI rdf data.

    Call save_protocol_data() to convert uidata to protocol data.  This converts
    ui config from newUiConfig to newL2tpDeviceConfig.  When satisfied, call
    activate_protocol_data() to make the configuration current.
    """

    @db.transact()
    def __init__(self):
        root = db.get_db().getRoot()
        self.ui_root = None
        self.l2tp_root = None

    def update_initial_config_saved(self, value=True):
        ui_root = helpers.get_ui_config()
        ui_root.setS(ns_ui.initialConfigSaved, rdf.Boolean, value)

    def clone_ui_config(self):
        """Deep copy current UI config to 'new' config."""

        _log.info('clone_ui_config()')
        
        root = db.get_db().getRoot()
        new_ui_root = root.setS(ns_ui.newUiConfig, rdf.Type(ns_ui.UiConfig))
        curr_ui_root = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
        rdf.deepCopy(curr_ui_root, new_ui_root)
        
        _log.info('clone_ui_config() successful')

    def _save_network_connections(self, pr_net_root, pr_pub_if):
        """Saves network connection data.

        Returns private interface node, if exists in config.  One interface setup returns none.
        """

        # XXX: why this somewhat non-obvious return value thing?  wouldn't it
        # be better to use a separate helper function for checking whether a private
        # interface exists?

        def _save_address(pr_network_node, ui_address_node):
            if ui_address_node.hasType(ns_ui.DhcpAddress):
                pr_network_node.setS(ns.address, rdf.Type(ns.DhcpAddress))
            elif ui_address_node.hasType(ns_ui.StaticAddress):
                pr_address = pr_network_node.setS(ns.address, rdf.Type(ns.StaticAddress))
                ui_ip = ui_address_node.getS(ns_ui.ipAddress, rdf.IPv4Address).toString()
                ui_subnet = ui_address_node.getS(ns_ui.subnetMask, rdf.IPv4Address).toString()
                ui_ip_cidr = datatypes.IPv4AddressSubnet.fromStrings(ui_ip, ui_subnet)
                pr_address.setS(ns.address, rdf.IPv4AddressSubnet, ui_ip_cidr)
            else:
                raise UiDataConversionError("Address type is neither dhcp nor static.")        
        
        def _save_client_traffic(pr_network_node, ui_network_node):
            pr_network_node.setS(ns.proxyArp, rdf.Boolean, ui_network_node.getS(ns_ui.clientConnectionProxyArp, rdf.Boolean))
            pr_network_node.setS(ns.nat, rdf.Boolean, ui_network_node.getS(ns_ui.clientConnectionNat, rdf.Boolean))    

        # Public interface
        ui_pub_if = self.ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
        pr_pub_if.setS(ns.interfaceName, rdf.String, ui_pub_if.getS(ns_ui.interface, rdf.String))
        ui_address = ui_pub_if.getS(ns_ui.address)
        _save_address(pr_pub_if, ui_address)
        public_mtu = ui_pub_if.getS(ns_ui.mtu, rdf.Integer)
        pr_pub_if.setS(ns.mtu, rdf.Integer, public_mtu)
        _save_client_traffic(pr_pub_if, ui_pub_if)
        uplink_root = pr_net_root.setS(ns.qosConfig, rdf.Type(ns.QosConfig))
        if ui_pub_if.hasS(ns_ui.vpnUplink):
            # XXX: How to convert from ui float to protocol integer?
            uplink_kb = int(1000 * ui_pub_if.getS(ns_ui.vpnUplink, rdf.Float))
            uplink_root.setS(ns.globalUplinkRateLimit, rdf.Integer, uplink_kb)

        # Private interface
        pr_priv_if = None
        if self.ui_root.hasS(ns_ui.privateNetworkConnection):
            ui_priv_if = self.ui_root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
            pr_priv_if = pr_net_root.setS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
            pr_priv_if.setS(ns.interfaceName, rdf.String, ui_priv_if.getS(ns_ui.interface, rdf.String))
            ui_address = ui_priv_if.getS(ns_ui.address)
            _save_address(pr_priv_if, ui_address)

            # If private_mtu is smaller, we will have trouble with mss negotiations: for outbound
            # tcp connections, our TCPMSS rule will only compare mss against the public MTU.  This
            # leads to a 100% certain need for ICMP frag needed when "routing through".  Setting
            # the MTU to the same value (or higher) as public eliminates this problem.  See #944.
            private_mtu = public_mtu

            pr_priv_if.setS(ns.mtu, rdf.Integer, private_mtu)
            _save_client_traffic(pr_priv_if, ui_priv_if)
        
        return pr_priv_if
    
    def _save_dynamic_dns(self, pr_pub_if):
        """Save dynamic dns setup to protocol RDF."""
        if self.ui_root.hasS(ns_ui.dynDnsServer):
            pr_ddns_root = pr_pub_if.setS(ns.dynamicDnsConfig, rdf.Type(ns.DynamicDnsConfig))
            ui_ddns_root = self.ui_root.getS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))
            pr_ddns_root.setS(ns.provider, rdf.String, ui_ddns_root.getS(ns_ui.dynDnsProvider, rdf.String))
            pr_ddns_root.setS(ns.username, rdf.String, ui_ddns_root.getS(ns_ui.dynDnsUsername, rdf.String))
            pr_ddns_root.setS(ns.password, rdf.String, ui_ddns_root.getS(ns_ui.dynDnsPassword, rdf.String))
            pr_ddns_root.setS(ns.hostname, rdf.String, ui_ddns_root.getS(ns_ui.dynDnsHostname, rdf.String))

            if ui_ddns_root.hasS(ns_ui.dynDnsAddress):
                tmp = ui_ddns_root.getS(ns_ui.dynDnsAddress, rdf.String)
                if tmp == 'natted':
                    da = pr_ddns_root.setS(ns.dynDnsAddress, rdf.Type(ns.DynDnsManagementConnectionAddress))
                elif tmp == '':
                    da = pr_ddns_root.setS(ns.dynDnsAddress, rdf.Type(ns.DynDnsInterfaceAddress))
                else:
                    da = pr_ddns_root.setS(ns.dynDnsAddress, rdf.Type(ns.DynDnsStaticAddress))
                    da.setS(ns.ipAddress, rdf.IPv4Address, datatypes.IPv4Address.fromString(tmp))
            else:
                da = pr_ddns_root.setS(ns.dynDnsAddress, rdf.Type(ns.DynDnsInterfaceAddress))

    def _save_firewall(self, pr_net_root, pr_pub_if, pr_priv_if):
        """Save firewall settings to protocol RDF."""
        pr_fw_root = pr_net_root.setS(ns.firewallConfig, rdf.Type(ns.FirewallConfig))

        pr_fw_root.setS(ns.allowNonClientRouting, rdf.Boolean, self.ui_root.getS(ns_ui.firewallInUse, rdf.Boolean))

        # port forwarding
        pr_port_forward_seq = pr_fw_root.setS(ns.portForward, rdf.Seq(rdf.Type(ns.PortForwardRule)))
        if self.ui_root.hasS(ns_ui.portForwards):
            for ui_pf in self.ui_root.getS(ns_ui.portForwards, rdf.Seq(rdf.Type(ns_ui.PortForward))):
                pr_pf = pr_port_forward_seq.new()
                # XXX: currently port forwarding is not possible from private interface; protocol code
                # supports it but UI doesn't have a selection
                pr_pf.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_pub_if)
                protocol = ui_pf.getS(ns_ui.protocol, rdf.String)
                if protocol == 'tcp':
                    pr_pf.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
                elif protocol == 'udp':
                    pr_pf.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_UDP)
                else:
                    raise UiDataConversionError("Firewall port forward protocol is neither tcp nor udp.")
                if ui_pf.hasS(ns_ui.incomingPort):
                    pr_pf.setS(ns.port, rdf.Integer, ui_pf.getS(ns_ui.incomingPort, rdf.Integer))
                pr_pf.setS(ns.destinationAddress, rdf.IPv4Address, ui_pf.getS(ns_ui.ipAddress, rdf.IPv4Address))
                if ui_pf.hasS(ns_ui.destinationPort):
                    pr_pf.setS(ns.destinationPort, rdf.Integer, ui_pf.getS(ns_ui.destinationPort, rdf.Integer)) 

        # input accept rules
        hardcoded_ports = [['tcp', constants.WEBUI_PORT_HTTP_INT], ['tcp', constants.WEBUI_PORT_HTTPS_INT]]
        pr_input_accept_seq = pr_fw_root.setS(ns.inputAccept, rdf.Seq(rdf.Type(ns.InputAcceptRule)))
        for proto, port in hardcoded_ports:
            if pr_pub_if is not None:
                pr_ia = pr_input_accept_seq.new()
                pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_pub_if)  # XXX: resets type?
                pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
                pr_ia.setS(ns.port, rdf.Integer, port)
            if pr_priv_if is not None:
                pr_ia = pr_input_accept_seq.new()
                pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_priv_if)  # XXX: resets type?
                pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
                pr_ia.setS(ns.port, rdf.Integer, port)

        pub_ssh = self.ui_root.getS(ns_ui.sshAccessPublic, rdf.Boolean)
        priv_ssh = self.ui_root.getS(ns_ui.sshAccessPrivate, rdf.Boolean)
        if pr_priv_if is not None and priv_ssh:
            pr_ia = pr_input_accept_seq.new()
            pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_priv_if)  # XXX: resets type?
            pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
            pr_ia.setS(ns.port, rdf.Integer, 22)
        if pr_pub_if is not None and pub_ssh:
            pr_ia = pr_input_accept_seq.new()
            pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_pub_if)  # XXX: resets type?
            pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
            pr_ia.setS(ns.port, rdf.Integer, 22)

        # XXX: snmpd does not listen to tcp/161 (snmp), but does tcp/199 which is 'smux'
        pub_snmp = self.ui_root.getS(ns_ui.snmpAccessPublic, rdf.Boolean)
        priv_snmp = self.ui_root.getS(ns_ui.snmpAccessPrivate, rdf.Boolean)
        if pr_priv_if is not None and priv_snmp:
            pr_ia = pr_input_accept_seq.new()
            pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_priv_if)  # XXX: resets type?
            pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_UDP)
            pr_ia.setS(ns.port, rdf.Integer, 161)
        if pr_pub_if is not None and pub_snmp:
            pr_ia = pr_input_accept_seq.new()
            pr_ia.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_pub_if)  # XXX: resets type?
            pr_ia.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_UDP)
            pr_ia.setS(ns.port, rdf.Integer, 161)
            
        # ppp firewall rules
        pr_ppp_fwrule_seq = pr_fw_root.setS(ns.pppFirewallRules, rdf.Seq(rdf.Type(ns.PppFirewallRule)))

        for fwrule in self.ui_root.getS(ns_ui.pppFirewallRules, rdf.Seq(rdf.Type(ns_ui.PppFirewallRule))):
            pr_fr = pr_ppp_fwrule_seq.new()
            pr_fr.setS(ns.subnet, rdf.IPv4Subnet, fwrule.getS(ns_ui.subnet, rdf.IPv4Subnet))

            has_port = False
            if not fwrule.hasS(ns_ui.protocol):
                pass
            elif fwrule.getS(ns_ui.protocol, rdf.String) == 'udp':
                has_port = True
                pr_fr.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_UDP)
            elif fwrule.getS(ns_ui.protocol, rdf.String) == 'tcp':
                has_port = True
                pr_fr.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_TCP)
            elif fwrule.getS(ns_ui.protocol, rdf.String) == 'icmp':
                pr_fr.setS(ns.protocol, rdf.Integer, constants.IP_PROTOCOL_ICMP)
            else:
                _log.warning('unknown protocol %s in firewall rule, using "any"', fwrule.getS(ns_ui.protocol, rdf.String))
                
            if fwrule.hasS(ns_ui.port) and has_port:
                pr_fr.setS(ns.port, rdf.Integer, fwrule.getS(ns_ui.port, rdf.Integer))

            if fwrule.getS(ns_ui.action, rdf.String) == 'allow':
                pr_fr.setS(ns.action, rdf.Type(ns.ActionAllow))
            elif fwrule.getS(ns_ui.action, rdf.String) == 'deny':
                pr_fr.setS(ns.action, rdf.Type(ns.ActionDeny))
            else:
                raise Exception('unknown firewall rule action %s', fwrule.getS(ns_ui.action, rdf.String))

        # compatibility - client reject list; this is required for naftalin compatibility
        pr_client_reject_seq = pr_fw_root.setS(ns.clientReject, rdf.Seq(rdf.Type(ns.ClientRejectRule)))

    def _save_dns(self, pr_node, pr_predicate, pr_pub_if, pr_priv_if):
        """Save dns settings to protocol rdf."""
        ui_dns_root = self.ui_root.getS(ns_ui.dnsServers)
        if ui_dns_root.hasType(ns_ui.SetDnsServers):
            # manual dns servers
            pr_dns_root = pr_node.setS(pr_predicate, rdf.Type(ns.StaticDnsServers))
            pr_dns_seq = pr_dns_root.setS(ns.addressList, rdf.Seq(rdf.Type(ns.DnsServer)))
            if ui_dns_root.hasS(ns_ui.primaryDns):
                pr_dns_seq.new().setS(ns.address, rdf.IPv4Address, ui_dns_root.getS(ns_ui.primaryDns, rdf.IPv4Address))
            if ui_dns_root.hasS(ns_ui.secondaryDns):
                pr_dns_seq.new().setS(ns.address, rdf.IPv4Address, ui_dns_root.getS(ns_ui.secondaryDns, rdf.IPv4Address))
        else:
            pr_dns_root = pr_node.setS(pr_predicate, rdf.Type(ns.DhcpDnsServers))
            if ui_dns_root.hasType(ns_ui.InternetConnectionDhcp):
                pr_dns_root.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_pub_if)
            elif ui_dns_root.hasType(ns_ui.PrivateNetworkConnectionDhcp):
                pr_dns_root.setS(ns.interface, rdf.Type(ns.NetworkInterface), pr_priv_if)
            else:
                raise UiDataConversionError('DHCP DNS is neither internet connection nor private network connection DHCP.')

    def _save_route(self, pr_route, ui_route, pr_pub_if, pr_priv_if, default_route=False):
        """Saves a ui_route to protocol data."""

        def _save_network_default_gw(ui_nw_node):
            """Called when route has been configured to use 'network default'.

            This figures out what the network default is and configures it to the route.
            """
            address_node = ui_nw_node.getS(ns_ui.address)

            if ui_nw_node.hasS(ns_ui.defaultGateway):
                # If has defaultGateway, always use it regardless of whether interface has static or DHCP address
                pr_gw_node = pr_route.setS(ns.gateway, rdf.Type(ns.StaticRouter))
                pr_gw_node.setS(ns.address, rdf.IPv4Address, ui_nw_node.getS(ns_ui.defaultGateway, rdf.IPv4Address))
            elif address_node.hasType(ns_ui.DhcpAddress):
                pr_gw_node = pr_route.setS(ns.gateway, rdf.Type(ns.DhcpRouter))
            elif address_node.hasType(ns_ui.StaticAddress):
                # We checked for defaultGateway above, so interface does not have it -> error
                raise UiDataConversionError('Network interface is missing a default route.')
            else:
                raise UiDataConversionError('Network address type is neither dhcp nor static.')
        
        # Default route and source route do not have subnet defined in uidata
        if default_route:
            subnet = '0.0.0.0/0'
        else:
            subnet = ui_route.getS(ns_ui.subnet, rdf.IPv4Subnet).toString()
        pr_route.setS(ns.address, rdf.IPv4Subnet, subnet)
        destination = None
        if ui_route.hasType(ns_ui.InternetConnectionRoute):
            destination = pr_pub_if
        elif ui_route.hasType(ns_ui.PrivateNetworkConnectionRoute):
            if not(pr_priv_if is None):
                destination = pr_priv_if
            else:
                raise UiDataConversionError('Route is a private interface route although private interface is none.')
        else:
            raise UiDataConversionError("Route's destination is neither internet nor private network connection.")    
        pr_route.setS(ns.interface, rdf.Type(ns.NetworkInterface), destination)    

        # Gateway
        ui_gw_node = ui_route.getS(ns_ui.routeGateway)
        if ui_gw_node.hasType(ns_ui.RouteGatewayNetworkDefault):
            if destination == pr_pub_if:
                _save_network_default_gw(self.ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection)))
            else:
                _save_network_default_gw(self.ui_root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection)))
        else:
            pr_route.setS(ns.gateway, rdf.Type(ns.StaticRouter)).setS(ns.address, rdf.IPv4Address, ui_gw_node.getS(ns_ui.ipAddress, rdf.IPv4Address))
        
    def _save_routes(self, pr_net_root, pr_pub_if, pr_priv_if):
        """Saves user defined routes in to both client and gw routes table."""

        pr_cli_routes_seq = pr_net_root.setS(ns.clientRoutes, rdf.Seq(rdf.Type(ns.Route)))
        pr_gw_routes_seq = pr_net_root.setS(ns.gatewayRoutes, rdf.Seq(rdf.Type(ns.Route)))

        # Source routing (forced routing) of client traffic?
        source_route = False
        if self.ui_root.hasS(ns_ui.sourceRouting):
            source_route = True

        # "Additional" (non-default) routes first
        if self.ui_root.hasS(ns_ui.routes):
            for ui_route in self.ui_root.getS(ns_ui.routes, rdf.Seq(rdf.Type(ns_ui.Route))):
                if source_route:
                    pass
                else:
                    self._save_route(pr_cli_routes_seq.new(), ui_route.getS(ns_ui.route), pr_pub_if, pr_priv_if)
                self._save_route(pr_gw_routes_seq.new(), ui_route.getS(ns_ui.route), pr_pub_if, pr_priv_if)

        # Default route
        if source_route:
            # source route replaces default gateway; no additional routes are added for clients either above
            self._save_route(pr_cli_routes_seq.new(), self.ui_root.getS(ns_ui.sourceRouting), pr_pub_if, pr_priv_if, True)
        else:
            self._save_route(pr_cli_routes_seq.new(), self.ui_root.getS(ns_ui.defaultRoute), pr_pub_if, pr_priv_if, True)
        self._save_route(pr_gw_routes_seq.new(), self.ui_root.getS(ns_ui.defaultRoute), pr_pub_if, pr_priv_if, True)

        # Client-to-client routing
        #
        # Ideally this would be a separate setting; currently this is never used, see #828.
        # The first approximation of this would be that client-to-client routing is disabled
        # if source route is enabled, as this supports the operator multicustomer case.
        #
        # However, because of #828, this is now always disabled.
        pr_net_root.setS(ns.clientToClientRouting, rdf.Boolean, True)

        # Forced router.
        #
        # This is used to force routing of all inbound PPP traffic to a specific router.
        # We share UI code here, and encode this as a 'default route'.
        if source_route:
            pr_fr = pr_net_root.setS(ns.pppForcedRouter, rdf.Type(ns.PppForcedRouter))
            self._save_route(pr_fr, self.ui_root.getS(ns_ui.sourceRouting), pr_pub_if, pr_priv_if, True)
        else:
            pr_net_root.removeNodes(ns.pppForcedRouter)
        
    def _save_userlist(self, pr_users_seq):
        """Convert ui -userlist to protocol userlist."""
        for ui_user in self.ui_root.getS(ns_ui.users, rdf.Seq(rdf.Type(ns.User))):
            # Check if the user has vpn rights.
            if not(ui_user.getS(ns_ui.vpnRights, rdf.Boolean)):
                continue
            pr_user = pr_users_seq.new()

            pr_user.setS(ns.username, rdf.String, ui_user.getS(ns_ui.username, rdf.String))

            # MD5 and NT hashes expected
            pr_user.setS(ns.passwordMd5, rdf.String, ui_user.getS(ns_ui.passwordMd5, rdf.String))
            pr_user.setS(ns.passwordNtHash, rdf.String, ui_user.getS(ns_ui.passwordNtHash, rdf.String))

            if ui_user.hasS(ns_ui.fixedIp):
                pr_user.setS(ns.fixedIp, rdf.IPv4Address, ui_user.getS(ns_ui.fixedIp, rdf.IPv4Address))

            # XXX: these are fixed for now
            pr_user.setS(ns.forceWebRedirect, rdf.Boolean, False)
            pr_user.setS(ns.forceNonPrimaryPskWebRedirect, rdf.Boolean, False)

    def _save_s2s_route(self, pr_net_root, pr_s2s_node, ui_s2s_node):
        """Save site-to-site route to client and gateway routes table."""
        def _save_s2s_subnet(pr_route, item_type, subnet):
            pr_route.setS(ns.address, item_type, subnet)
            pr_route.setS(ns.gateway, rdf.Type(ns.SiteToSiteRouter)).setS(ns.user, rdf.Type(ns.User), pr_s2s_node)
        
        # Client and gw routes must be created already.
        if not(pr_net_root.hasS(ns.clientRoutes) and pr_net_root.hasS(ns.gatewayRoutes)):
            raise UiDataConversionError('Site-to-site routes save failed, because client or gateway routing table is missing.')
        
        pr_cli_routes_seq = pr_net_root.getS(ns.clientRoutes, rdf.Seq(rdf.Type(ns.Route)))
        pr_gw_routes_seq = pr_net_root.getS(ns.gatewayRoutes, rdf.Seq(rdf.Type(ns.Route)))           
        
        for ui_subnet in ui_s2s_node.getS(ns_ui.subnetList, rdf.Seq(rdf.Type(ns_ui.Subnet))):
            _save_s2s_subnet(pr_cli_routes_seq.new(), rdf.IPv4Subnet, ui_subnet.getS(ns_ui.subnet, rdf.IPv4Subnet).toString())
            _save_s2s_subnet(pr_gw_routes_seq.new(), rdf.IPv4Subnet, ui_subnet.getS(ns_ui.subnet, rdf.IPv4Subnet).toString())

    def _save_s2s_connections(self, pr_net_root, pr_users_seq):
        """Add site-to-site connections to protocol userlist."""
        for ui_s2s_connection in self.ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection))):
            pr_s2s_connection = pr_users_seq.new()
            pr_s2s_connection.setS(ns.username, rdf.String, ui_s2s_connection.getS(ns_ui.username, rdf.String))

            # NB: plaintext passwords used for s2s
            pr_s2s_connection.setS(ns.password, rdf.String, ui_s2s_connection.getS(ns_ui.password, rdf.String))

            pr_s2s_connection.setS(ns.forceWebRedirect, rdf.Boolean, False)
            pr_s2s_connection.setS(ns.forceNonPrimaryPskWebRedirect, rdf.Boolean, False)
            pr_s2s_node = pr_s2s_connection.setS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))

            mode = ui_s2s_connection.getS(ns_ui.mode, rdf.String)
            if mode == 'client':
                pr_s2s_node.setS(ns.role, rdf.Type(ns.Client))
                psk = str(ui_s2s_connection.getS(ns_ui.preSharedKey, rdf.String))
                pr_s2s_node.setS(ns.preSharedKey, rdf.Binary, psk)
                pr_s2s_node.setS(ns.destinationAddress, rdf.String, ui_s2s_connection.getS(ns_ui.serverAddress, rdf.String))
            elif mode == 'server':
                pr_s2s_node.setS(ns.role, rdf.Type(ns.Server))
            else:
                raise Exception('unknown mode: %s' % mode)

            self._save_s2s_route(pr_net_root, pr_s2s_connection, ui_s2s_connection)    
                
    def _save_l2tp_data(self):
        # XXX: no config now, but need the root
        pr_l2tp_root = self.l2tp_root.setS(ns.l2tpConfig, rdf.Type(ns.L2tpConfig))
        
    def _save_ipsec_data(self):
        pr_ipsec_root = self.l2tp_root.setS(ns.ipsecConfig, rdf.Type(ns.IpsecConfig))
        pr_psk_seq = pr_ipsec_root.setS(ns.preSharedKeys, rdf.Seq(rdf.Type(ns.PreSharedKey)))
        for ui_psk in self.ui_root.getS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey))):
            pr_psk = pr_psk_seq.new()
            pr_psk.setS(ns.preSharedKey, rdf.Binary, str(ui_psk.getS(ns_ui.preSharedKey, rdf.String)))
        pr_ipsec_root.setS(ns.ikeLifeTime, rdf.Timedelta, uidefaults.IPSEC_IKE_LIFETIME)
        pr_ipsec_root.setS(ns.ipsecLifeTime, rdf.Timedelta, uidefaults.IPSEC_IPSEC_LIFETIME)
    
    def _save_ppp_dns_wins(self, pr_ppp_root, pr_pub_if, pr_priv_if):
        """Save ppp dns and wins."""
        def _save_static_dns_list(ui_dns_server_list):
            pr_dns_root = pr_ppp_root.setS(ns.pppDnsServers, rdf.Type(ns.StaticDnsServers))
            pr_dns_seq = pr_dns_root.setS(ns.addressList, rdf.Seq(rdf.Type(ns.DnsServer)))
            for ui_dns_server in ui_dns_server_list:
                pr_dns_server = pr_dns_seq.new()
                pr_dns_server.setS(ns.address, rdf.IPv4Address, ui_dns_server)
        # DNS
        ui_dns_root = self.ui_root.getS(ns_ui.clientDnsServers)
        ui_dns_list = []
        if ui_dns_root.hasType(ns_ui.NetworkConnectionDns):
            # Get dns information from network dns info.
            self._save_dns(pr_ppp_root, ns.pppDnsServers, pr_pub_if, pr_priv_if)
        elif ui_dns_root.hasType(ns_ui.SetDnsServers):
            # Set manual dns addresses.
            if ui_dns_root.hasS(ns_ui.primaryDns):
                ui_dns_list.append(ui_dns_root.getS(ns_ui.primaryDns, rdf.IPv4Address))
            if ui_dns_root.hasS(ns_ui.secondaryDns):
                ui_dns_list.append(ui_dns_root.getS(ns_ui.secondaryDns, rdf.IPv4Address))
            _save_static_dns_list(ui_dns_list) 
        else:
            raise UiDataConversionError('Client connection DNS is neither use network connection ' +
                                        'DNS servers nor set DNS servers.')
                        
        # WINS
        # XXX: Current UI does not have an option for dhcp wins settings.
        # wins_cfg = cfg_ppp.setS(ns.pppWinsServers, rdf.Type(ns.DhcpWinsServers))
        # wins_cfg.setS(ns.interface, rdf.Type(ns.NetworkInterface), pub_if)
        pr_wins_root = pr_ppp_root.setS(ns.pppWinsServers, rdf.Type(ns.StaticWinsServers))
        pr_wins_seq = pr_wins_root.setS(ns.addressList, rdf.Seq(rdf.Type(ns.WinsServer)))
        if self.ui_root.hasS(ns_ui.clientPrimaryWins) or self.ui_root.hasS(ns_ui.clientSecondaryWins):
            if self.ui_root.hasS(ns_ui.clientPrimaryWins):
                pr_wins_seq.new().setS(ns.address, rdf.IPv4Address, self.ui_root.getS(ns_ui.clientPrimaryWins, rdf.IPv4Address)) 
            if self.ui_root.hasS(ns_ui.clientSecondaryWins):
                pr_wins_seq.new().setS(ns.address, rdf.IPv4Address, self.ui_root.getS(ns_ui.clientSecondaryWins, rdf.IPv4Address))

    def _save_ppp_compression(self, pr_ppp_root):
        """Saves compression configuration."""
        pr_compression_root = pr_ppp_root.setS(ns.pppCompression, rdf.Type(ns.PppCompression))

        # XXX: ppp compression options does not affect initiated
        # site-to-site connections, but server settings still have
        # effect on site-to-site clients.

        if self.ui_root.hasS(ns_ui.clientCompression) and self.ui_root.getS(ns_ui.clientCompression, rdf.Boolean):
            # These defaults have been "battle tested", and should set this way
            # if global compression is enabled
            pr_compression_root.setS(ns.pppMppc, rdf.Boolean, True)
            pr_compression_root.setS(ns.pppMppe, rdf.Boolean, False)   # NB: MUST be disabled
            pr_compression_root.setS(ns.pppAccomp, rdf.Boolean, True)
            pr_compression_root.setS(ns.pppPcomp, rdf.Boolean, False)  # NB: MUST NOT be enabled! Breaks things!
            pr_compression_root.setS(ns.pppBsdcomp, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppDeflate, rdf.Boolean, True)
            pr_compression_root.setS(ns.pppPredictor1, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppVj, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppCcompVj, rdf.Boolean, False)
        else:
            # Selected no-compression option
            pr_compression_root.setS(ns.pppMppc, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppMppe, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppAccomp, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppPcomp, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppBsdcomp, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppDeflate, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppPredictor1, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppVj, rdf.Boolean, False)
            pr_compression_root.setS(ns.pppCcompVj, rdf.Boolean, False)
        
    def _save_ppp_auth_data(self, pr_ppp_root):
        """Save protocol auth settings. These settigns are not shown in user interface."""
        pr_auth_root = pr_ppp_root.setS(ns.pppAuthentication, rdf.Type(ns.PppAuthentication))
        pr_auth_root.setS(ns.pppPap, rdf.Boolean, uidefaults.AUTH_PPP_PAP)
        pr_auth_root.setS(ns.pppChap, rdf.Boolean, uidefaults.AUTH_PPP_CHAP)
        pr_auth_root.setS(ns.pppMschap, rdf.Boolean, uidefaults.AUTH_PPP_MS_CHAP)
        pr_auth_root.setS(ns.pppMschapV2, rdf.Boolean, uidefaults.AUTH_PPP_MS_CHAP_V2)
        pr_auth_root.setS(ns.pppEap, rdf.Boolean, uidefaults.AUTH_PPP_EAP)    
        
    def _save_ppp_data(self, pr_pub_if, pr_priv_if):
        """Save protocol ppp data."""
        pr_ppp_root = self.l2tp_root.setS(ns.pppConfig, rdf.Type(ns.PppConfig))    
        # client subnet and iprange
        pr_ppp_root.setS(ns.pppSubnet, rdf.IPv4Subnet, self.ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet).toString())
        pr_ppp_root.setS(ns.pppRange, rdf.IPv4AddressRange, self.ui_root.getS(ns_ui.clientAddressRange, rdf.IPv4AddressRange))
        self._save_ppp_compression(pr_ppp_root)
        self._save_ppp_dns_wins(pr_ppp_root, pr_pub_if, pr_priv_if)
        # ppp config not in UI, default values used
        ui_ic_mtu = self.ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection)).getS(ns_ui.mtu, rdf.Integer)
        pr_ppp_root.setS(ns.pppMtu, rdf.Integer, ui_ic_mtu-constants.TOTAL_L2TP_IPSEC_OVERHEAD)
        pr_ppp_root.setS(ns.pppLcpEchoInterval, rdf.Timedelta, uidefaults.PPP_LCP_ECHO_INTERVAL)
        pr_ppp_root.setS(ns.pppLcpEchoFailure, rdf.Integer, uidefaults.PPP_LCP_ECHO_FAILURE)
        # Protocol auth settings. These are not in ui.
        self._save_ppp_auth_data(pr_ppp_root)

    def _save_radius_data(self):
        pr_radius_root = self.l2tp_root.setS(ns.radiusConfig, rdf.Type(ns.RadiusConfig))
        pr_radius_servers = pr_radius_root.setS(ns.radiusServers, rdf.Seq(rdf.Type(ns.RadiusServer)))

        server1 = None
        if self.ui_root.hasS(ns_ui.radiusPrimaryServer):
            server1 = self.ui_root.getS(ns_ui.radiusPrimaryServer, rdf.String)
        port1 = 1812
        if self.ui_root.hasS(ns_ui.radiusPrimaryServerPort):
            port1 = self.ui_root.getS(ns_ui.radiusPrimaryServerPort, rdf.Integer)
        secret1 = None
        if self.ui_root.hasS(ns_ui.radiusPrimarySecret):
            secret1 = self.ui_root.getS(ns_ui.radiusPrimarySecret, rdf.String)

        server2 = None
        if self.ui_root.hasS(ns_ui.radiusSecondaryServer):
            server2 = self.ui_root.getS(ns_ui.radiusSecondaryServer, rdf.String)
        port2 = 1812
        if self.ui_root.hasS(ns_ui.radiusSecondaryServerPort):
            port2 = self.ui_root.getS(ns_ui.radiusSecondaryServerPort, rdf.Integer)
        secret2 = None
        if self.ui_root.hasS(ns_ui.radiusSecondarySecret):
            secret2 = self.ui_root.getS(ns_ui.radiusSecondarySecret, rdf.String)

        for srv, port, sec in [ (server1, port1, secret1), (server2, port2, secret2) ]:
            if (srv is not None) and (srv != '') and (sec is not None) and (sec != ''):
                t = pr_radius_servers.new()
                t.setS(ns.address, rdf.String, srv)
                t.setS(ns.secret, rdf.String, sec)
                t.setS(ns.port, rdf.Integer, port)

        val = ''
        if self.ui_root.hasS(ns_ui.radiusNasIdentifier):
            val = self.ui_root.getS(ns_ui.radiusNasIdentifier, rdf.String)
        pr_radius_root.setS(ns.radiusNasIdentifier, rdf.String, val)

    def _save_snmp_data(self):
        pr_snmp_root = self.l2tp_root.setS(ns.snmpConfig, rdf.Type(ns.SnmpConfig))
        snmp_community = self.ui_root.getS(ns_ui.snmpCommunity, rdf.String)
        if snmp_community == '':
            # configuration won't allow an empty community string, so we use a random UUID in this case
            # firewall should prevent access anyway
            snmp_community = randutil.random_uuid()
        pr_snmp_root.setS(ns.snmpCommunity, rdf.String, snmp_community)

    def _save_management_connection_data(self):
        """Saves management connection data. Currently not in ui."""
        pr_management_root = self.l2tp_root.setS(ns.managementConfig, rdf.Type(ns.ManagementConfig))

        # XXX: currently empty; license stuff is now read directly from UI's licenseInfo instead
        
    def _save_debug_mode_state(self):
        """Saves debug mode state into protocol data."""
        if self.ui_root.hasS(ns_ui.debug):
            debug_mode = self.ui_root.getS(ns_ui.debug, rdf.Integer)
            if debug_mode == 0:
                self.l2tp_root.setS(ns.debug, rdf.Type(ns.DebugNone))
            elif debug_mode == 1:
                self.l2tp_root.setS(ns.debug, rdf.Type(ns.DebugNormal))
            elif debug_mode == 2:
                self.l2tp_root.setS(ns.debug, rdf.Type(ns.DebugHeavy))    
            else:
                raise UiDataConversionError('Unknown debug mode in UI data.')
        
    @db.transact()
    def activate_protocol_data(self, use_current_config=False):
        """Make 'new' config into 'current' one, and remove 'new' config."""
        root = db.get_db().getRoot()

        _log.info('activate_protocol_data()')
        
        if use_current_config:
            pass
        else:
            new_ui_root = root.getS(ns_ui.newUiConfig, rdf.Type(ns_ui.UiConfig))
            root.removeNodes(ns_ui.newUiConfig)
            root.setS(ns_ui.uiConfig, rdf.Resource, new_ui_root)

        new_cfg_root = root.getS(ns.newL2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))
        root.removeNodes(ns.newL2tpDeviceConfig)
        root.setS(ns.l2tpDeviceConfig, rdf.Resource, new_cfg_root)

        _log.info('activate_protocol_data() successful')

    @db.transact()
    def save_protocol_data(self, use_current_config=False):
        """Convert 'new' UI config into 'new' protocol config.

        This process should be pretty robust, but there are some corner case bugs
        which is why the separation between 'new' and 'current' config was made.
        Any exceptions thrown by this function are turned into 'unknown errors',
        which prevent configuration from being corrupted.

        In the future, validation logic can be moved here bit by bit - as we can
        throw validation errors from this function too.
        """

        _log.info('save_protocol_data()')

        # Create new protocol config node
        root = db.get_db().getRoot()
        if use_current_config:
            self.ui_root = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
        else:
            self.ui_root = root.getS(ns_ui.newUiConfig, rdf.Type(ns_ui.UiConfig))
        self.l2tp_root = root.setS(ns.newL2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))

        # Convert network ui data to protocol data.
        pr_net_root = self.l2tp_root.setS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        pr_pub_if = pr_net_root.setS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
        pr_priv_if = self._save_network_connections(pr_net_root, pr_pub_if)
        
        self._save_dynamic_dns(pr_pub_if)
        self._save_firewall(pr_net_root, pr_pub_if, pr_priv_if)
        self._save_dns(pr_net_root, ns.dnsServers, pr_pub_if, pr_priv_if)
        self._save_routes(pr_net_root, pr_pub_if, pr_priv_if)
        
        # Convert ui users to protocol users. Protocol userlist includes vpn users,
        # site-to-site clients, site-to-site servers.
        pr_users_root = self.l2tp_root.setS(ns.usersConfig, rdf.Type(ns.UsersConfig))
        pr_users_seq = pr_users_root.setS(ns.users, rdf.Bag(rdf.Type(ns.User)))

        # Save userlist if it exists.
        if self.ui_root.hasS(ns_ui.users):
            self._save_userlist(pr_users_seq)

        # Forwarding ports are shared now
        pr_users_root.setS(ns.httpForcedRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_UIFORCED_HTTP)
        pr_users_root.setS(ns.httpsForcedRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_UIFORCED_HTTPS)
        pr_users_root.setS(ns.httpLicenseRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_LICENSE_HTTP)
        pr_users_root.setS(ns.httpsLicenseRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_LICENSE_HTTPS)
        pr_users_root.setS(ns.httpNonPrimaryPskRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_OLDPSK_HTTP)
        pr_users_root.setS(ns.httpsNonPrimaryPskRedirectPort, rdf.Integer, constants.WEBUI_FORWARD_PORT_OLDPSK_HTTPS)

        # Save site-to-site connections (updates both user list and routes list)
        # XXX: site-to-site routes will follow normal routes; this is OK as the rdf.Seq
        # is not really a sequence; but it's still a bit ugly
        if self.ui_root.hasS(ns_ui.siteToSiteConnections):
            self._save_s2s_connections(pr_net_root, pr_users_seq)

        # Save local settings -- currently no protocol dependencies

        # Legacy admin config root - no contents, but some previous code assumes this exists
        # (naftaliini)
        pr_admin_root = self.l2tp_root.setS(ns.adminConfig, rdf.Type(ns.AdminConfig))

        # Protocol ipsec data
        self._save_ipsec_data()

        # Protocol l2tp data
        self._save_l2tp_data()

        # Protocol ppp data
        self._save_ppp_data(pr_pub_if, pr_priv_if)

        # Management connection settings
        self._save_management_connection_data()

        # RADIUS
        self._save_radius_data()
        
        # SNMP
        self._save_snmp_data()
        
        # Debug options
        self._save_debug_mode_state()

        _log.info('save_protocol_data() successful')

    def restart_freeradius(self):
        """Regenerate freeradius configuration and restart the server.

        Do it indirectly using runner marker file and signal.

        This must be done every time the user config has changed: when
        users are added/removed/changed in admin interface and when the
        user changes his/her password from web interface.
        """

        _log.info('regenerating freeradius config and restarting server')

        # XXX: is there a more direct way using the ProcessProtocol?
        f = None
        try:
            helpers.write_datetime_marker_file(constants.FREERADIUS_RESTART_MARKER)
            f = open(constants.RUNNER_PIDFILE)
            pid = int(f.read().strip())
            [rv, out, err] = run_command([constants.CMD_KILL, '-SIGALRM', str(pid)], retval=runcommand.FAIL)
        except:
            _log.error('restarting freeradius failed, changes in radius/user configuration not applied')

        if f is not None:
            f.close()

    # XXX: will not work correctly with site-to-site connections:
    # currently it just ignores all but normal users.
    def recheck_and_drop_ppp_connections(self):
        """Check existing PPP connections against currently configured users.

        Drop any connections that no longer have corresponding configured user,
        or whose current IP address is unacceptable (not equal to fixed IP).
        """

        _log.info('checking existing ppp devices against new user configuration')

        # We're a bit paranoid in this loop.  We want to process all users regardless
        # of failures with specific users.  Caller is assumed to wrap this function
        # call in a try-except block to make sure that UI configuration edit doesn't
        # fail; it's important to be able to change even a broken configuration so the
        # admin doesn't get stuck.

        rdfdevs = helpers.get_ppp_devices()
        for i, d in enumerate(rdfdevs):
            ppp_username = None
            ppp_devname = None
            ppp_address = None
            ui_user = None
            ui_address = None
            needs_nuking = False

            try:
                # Exclude site-to-site connections from the check
                if not d.getS(ns.connectionType).hasType(ns.NormalUser):
                    continue

                # Exclude remotely authenticated users from the check
                if d.hasS(ns.locallyAuthenticated) and (not d.getS(ns.locallyAuthenticated, rdf.Boolean)):
                    # XXX: check fixed address stuff for RADIUS users here?
                    continue

                # Locally authenticated user
                ppp_username = d.getS(ns.username, rdf.String)
                ppp_devname = d.getS(ns.deviceName, rdf.String)
                ppp_address = d.getS(ns.pppRemoteAddress, rdf.IPv4Address)
                ui_user = uihelpers.find_user(ppp_username)

                if ui_user is None:
                    _log.info('ppp device %s with username %s no longer exists in configuration, nuking' % (ppp_devname, ppp_username))
                    needs_nuking = True
                else:
                    # Fixed IP sanity checks:
                    # 
                    # 1. check if user has IP outside of the current PPP
                    #    IP range and currently has no fixed IP set
                    #
                    # 2. check if user has fixed IP set and current IP
                    #    does not match configured fixed IP
                    #

                    if not ui_user.hasS(ns.fixedIp):
                        ppp_cfg = helpers.get_config().getS(ns.pppConfig, rdf.Type(ns.PppConfig))
                        ip_range = ppp_cfg.getS(ns.pppRange, rdf.IPv4AddressRange)
                        if not ip_range.inRange(ppp_address):
                            _log.info('ppp device %s with username %s has address %s outside of the configured ppp address range %s and no static address, nuking', (ppp_devname, ppp_username, ppp_address.toString(), ip_range.toString()))
                            needs_nuking = True

                        # Note: there is no need to check that the user is not using the fixed
                        # IP of another user, because fixed IPs cannot currently be inside the
                        # allowed range; so the check above would drop the connection anyway.

                    if ui_user.hasS(ns.fixedIp):
                        ui_address = ui_user.getS(ns.fixedIp, rdf.IPv4Address)
                        if ui_address != ppp_address:
                            _log.info('ppp device %s with username %s has address %s different from configured fixed address %s, nuking' % (ppp_devname, ppp_username, ppp_address.toString(), ui_address.toString()))
                            needs_nuking = True

            except:
                _log.exception('ppp connection recheck failed for device %s with username %s, node %s, nuking just in case' % (ppp_devname, ppp_username, d))
                needs_nuking = True

            if needs_nuking:
                try:
                    pppscripts.nuke_ppp_device(ppp_devname, silent=True, kill_ppp=True)
                except:
                    _log.exception('nuking device %s failed, ignoring')

# --------------------------------------------------------------------------
# 
#  Runner restart stuff
#

# NB: this would fit better in uihelpers.py, but is currently here to
# break a cyclic import between uihelpers and uidatahelpers.
def reconfigure_and_restart_runner(master):
    _log.debug('reconfigure_and_restart_runner()')

    master.set_activate_configuration_state('Activating configuration', finished=False, success=False, active=True)

    def _stop_service(res):
        _log.debug('reconfigure_and_restart_runner/_stop_service()')
        master.set_activate_configuration_state('Stopping VPN service', finished=False, success=False, active=True)
        return master.stop_l2tp_service(wait=True)

    def _save_protocol_data(res):
        _log.debug('reconfigure_and_restart_runner/_save_protocol_data()')
        master.set_activate_configuration_state('Reconfiguring VPN service', finished=False, success=False, active=True)
        pd = CreateProtocolData()

        pd.save_protocol_data(use_current_config=True)
        pd.activate_protocol_data(use_current_config=True)
        return None
    
    def _start_service(res):
        _log.debug('reconfigure_and_restart_runner/_start_service()')
        master.set_activate_configuration_state('Restarting VPN service', finished=False, success=False, active=True)
        return master.start_l2tp_service(wait=True)
        
    def _complete(res):
        _log.debug('reconfigure_and_restart_runner/_complete()')
        master.set_activate_configuration_state('Activation complete', finished=True, success=True, active=False)
        return None
    
    def _failed(reason):
        _log.debug('reconfigure_and_restart_runner/_failed')
        _log.error('management config activation failed: %s' % reason)
        master.set_activate_configuration_state('Activation failed', finished=True, success=False, active=False)
        return None

    def _kickstart_deferred(d):
        _log.debug('reconfigure_and_restart_runner/_kickstart_deferred()')
        d.callback(None)

    # XXX: block request for how long??        
    d = defer.Deferred()
    d.addCallback(_stop_service)
    d.addCallback(_save_protocol_data)
    d.addCallback(_start_service)
    d.addCallback(_complete)
    d.addErrback(_failed)

    # magic artificial delay to avoid browser rendering problems
    ks_call = reactor.callLater(1.0, _kickstart_deferred, d)
    return d


