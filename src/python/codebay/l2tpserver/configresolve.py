from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig

ns = rdfconfig.ns
_log = logger.get('l2tpserver.configresolve')

class DhcpAddressInfo:
    def __init__(self):
        self.interface = None
        self.address = None
        self.router = None
        self.dns_servers = []
        self.wins_servers = []

    def __str__(self):
        res = 'DhcpAddressInfo: interface: ' + self.interface + ', address: ' + self.address.toString() + ', router: ' + self.router.toString() + ', dns-servers: ['
        t = []
        for i in self.dns_servers:
            t.append(i.toString())
        res += ', '.join(t) + ']'
        res += ', wins-servers: ['
        t = []
        for i in self.wins_servers:
            t.append(i.toString())
        res += ', '.join(t) + ']'

        return res

    def read_dhcp_information(self, filename):
        def _fix(a, i):
            try:
                if a[i] == '':
                    return None
                return a[i]
            except:
                return None

        f = open(filename, 'rb')
        t = f.read().split('\n')
        f.close()

        addr = _fix(t, 0)
        mask = _fix(t, 1)
        router = _fix(t, 2)
        dns_servers = [_fix(t, 3), _fix(t, 4)]
        wins_servers = [_fix(t, 5), _fix(t, 6)]

        _log.info('got dhcp info: ip=%s mask=%s router=%s dns1=%s dns2=%s wins1=%s wins2=%s' % (
            addr, mask, router, dns_servers[0], dns_servers[1], wins_servers[0], wins_servers[1]))

        if addr is None:
            raise Exception('expected IP address not found.')
        if mask is None:
            raise Exception('expected subnet mask not found.')

        self.address = datatypes.IPv4AddressSubnet.fromStrings(addr, mask)

        self.router = None
        if router is not None:
            self.router = datatypes.IPv4Address.fromString(router)

        self.dns_servers = []
        for i in dns_servers:
            if i is not None:
                self.dns_servers.append(datatypes.IPv4Address.fromString(i))

        self.wins_servers = []
        for i in wins_servers:
            if i is not None:
                self.wins_servers.append(datatypes.IPv4Address.fromString(i))

class ResolvedInterface:
    def __init__(self):
        self.address = None       # IPv4AddressSubnet
        self.device = None        # string
        self.rdf_interface = None # rdf.Node

class ResolvedDnsServer:
    def __init__(self):
        self.address = None                  # IPv4Address
        self.rdf_server_list = None          # rdf.Node
        self.from_dhcp = False               # True or False
        self.from_dhcp_rdf_interface = None  # rdf.Node or None (set if from_dhcp=True)

class ResolvedWinsServer:
    def __init__(self):
        self.address = None                  # IPv4Address
        self.rdf_server_list = None          # rdf.Node
        self.from_dhcp = False               # True or False
        self.from_dhcp_rdf_interface = None  # rdf.Node or None (set if from_dhcp=True)

class ResolvedRoute:
    def __init__(self):
        self.rdf_interface = None     # rdf.Node
        self.subnet = None            # IPv4Subnet
        self.devname = None           # devname or None
        self.router = None            # IPv4Address or None
        self.router_from_dhcp = False # True or False
        self.blackhole = False        # True or False
        self.rdf_route = None         # rdf.Node
        
class ResolvedInfo:
    def __init__(self):
        self.public_interface = None  # ResolvedInterface
        self.private_interface = None # ResolvedInterface or None
        self.dns_servers = []         # list of ResolvedDnsServer
        self.gateway_routes = []      # list of ResolvedRoute
        self.client_routes = []       # list of ResolvedRoute
        self.ppp_dns_servers = []     # list of ResolvedDnsServer
        self.ppp_wins_servers = []    # list of ResolvedWinsServer
        self.ppp_forced_router = None # ResolvedRoute
        
    def __str__(self):
        def _srv_to_str(srv):
            if srv is None:
                return 'none'
            addr = srv.address.toString()
            uri = None
            if srv.rdf_server_list is not None:
                uri = str(srv.rdf_server_list.getUri())
            from_dhcp, from_dhcp_uri = False, None
            if srv.from_dhcp:
                from_dhcp = True
                from_dhcp_uri = str(srv.from_dhcp_rdf_interface.getUri())
            return '%s[dhcp=%s:%s][%s]' % (addr, from_dhcp, from_dhcp_uri, uri)

        def _router_to_str(r):
            if r is None:
                return 'none'
            router_str = 'none'
            if r.router is not None:
                router_str = r.router.toString()
            return '(%s/%s -> %s, blackhole=%s, dhcp=%s, rdf_if=%s, rdf_route=%s)' % (r.subnet.toString(),
                                                                                      r.devname,
                                                                                      router_str,
                                                                                      r.blackhole,
                                                                                      r.router_from_dhcp,
                                                                                      r.rdf_interface,
                                                                                      r.rdf_route)

        pub_str, pub_dev, pub_uri = 'none', 'none', 'none'
        if self.public_interface is not None:
            pub_str = self.public_interface.address.toString()
            pub_dev = self.public_interface.device
            pub_uri = str(self.public_interface.rdf_interface.getUri())
        priv_str, priv_dev, priv_uri = 'none', 'none', 'none'
        if self.private_interface is not None:
            priv_str = self.private_interface.address.toString()
            priv_dev = self.private_interface.device            
            priv_uri = str(self.private_interface.rdf_interface.getUri())
        res = 'ResolvedInfo:\n'
        res += '    pubaddr: %s(%s)[%s]\n    privaddr: %s(%s)[%s]' % (pub_str, pub_dev, pub_uri, priv_str, priv_dev, priv_uri)
        
        res += '\n    dns-servers: ['
        t = []
        for i in self.dns_servers:
            t.append(_srv_to_str(i))
        res += ', '.join(t) + ']'

        res += '\n    gateway-routes: ['
        t = []
        for i in self.gateway_routes:
            t.append(_router_to_str(i))
        res += ', '.join(t) + ']'

        res += '\n    client-routes: ['
        t = []
        for i in self.client_routes:
            t.append(_router_to_str(i))
        res += ', '.join(t) + ']'

        res += '\n    ppp-dns-servers: ['
        t = []
        for i in self.ppp_dns_servers:
            t.append(_srv_to_str(i))
        res += ', '.join(t) + ']'

        res += '\n    ppp-wins-servers: ['
        t = []
        for i in self.ppp_wins_servers:
            t.append(_srv_to_str(i))
        res += ', '.join(t) + ']'

        res += '\n    ppp-forced-router: '
        res += _router_to_str(self.ppp_forced_router)
        
        res += '\n    public_dhcp_addrinfo: ' + str(self._pub_addrinfo)
        res += '\n    private_dhcp_addrinfo: ' + str(self._priv_addrinfo)

        return res

    def resolve(self, cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo):
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)

        self._pub_addrinfo = pub_dhcpaddrinfo
        self._priv_addrinfo = priv_dhcpaddrinfo

        pub_addr, priv_addr = self._resolve_addresses(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo)
        if pub_iface is not None:
            self.public_interface = ResolvedInterface()
            self.public_interface.address = pub_addr
            self.public_interface.device = pub_iface_name
            self.public_interface.rdf_interface = pub_iface
        if priv_iface is not None:
            self.private_interface = ResolvedInterface()
            self.private_interface.address = priv_addr
            self.private_interface.device = priv_iface_name            
            self.private_interface.rdf_interface = priv_iface

        self.dns_servers = self._resolve_dns_servers(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo)
        self.gateway_routes = self._resolve_routes(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo, net_cfg.getS(ns.gatewayRoutes, rdf.Seq(rdf.Type(ns.Route))))
        self.client_routes = self._resolve_routes(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo, net_cfg.getS(ns.clientRoutes, rdf.Seq(rdf.Type(ns.Route))))
        self.ppp_dns_servers, self.ppp_wins_servers = self._resolve_ppp_dns_wins_servers(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo)
        self.ppp_forced_router = self._resolve_ppp_forced_router(cfg, pub_dhcpaddrinfo, priv_dhcpaddrinfo)

        # XXX: post checks?
        if len(self.dns_servers) == 0:
            # XXX: this should be converted to a more useful exception
            # XXX: for a 'lenient' startup (e.g. for sending e-mail to fixed IP address SMTP server)
            # this check is too strict
            raise Exception('no dns servers')

    def _resolve_ppp_forced_router(self, cfg, pub_addrinfo, priv_addrinfo):
        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))

        if not net_cfg.hasS(ns.pppForcedRouter):
            return None
        fr = net_cfg.getS(ns.pppForcedRouter, rdf.Type(ns.PppForcedRouter))

        rt = self._resolve_one_route(fr, pub_if, priv_if, pub_addrinfo, priv_addrinfo)

        return rt
                                    
    def _resolve_dns_servers(self, cfg, pub, priv):
        """Determine DNS server list by resolving configured and DHCP-obtained value."""

        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))

        dns = net_cfg.getS(ns.dnsServers)
        if dns.hasType(ns.StaticDnsServers):
            _log.debug('dns servers from configured data')
            dns_servers = []
            for i in dns.getS(ns.addressList, rdf.Seq(rdf.Type(ns.DnsServer))):
                srv = ResolvedDnsServer()
                srv.address = i.getS(ns.address, rdf.IPv4Address)
                srv.rdf_server_list = dns
                srv.from_dhcp = False
                srv.from_dhcp_rdf_interface = None
                dns_servers.append(srv)
            return dns_servers
        elif dns.hasType(ns.DhcpDnsServers):
            iface = dns.getS(ns.interface, rdf.Type(ns.NetworkInterface))
            if iface == pub_if:
                _log.debug('dns servers from dhcp public')
                if pub is not None:
                    dns_servers = []
                    for i in pub.dns_servers:
                        srv = ResolvedDnsServer()
                        srv.address = i  # IPv4Address
                        srv.rdf_server_list = dns
                        srv.from_dhcp = True
                        srv.from_dhcp_rdf_interface = pub_if
                        dns_servers.append(srv)
                    return dns_servers
                else:
                    return []
            elif iface == priv_if:
                _log.debug('dns servers from dhcp private')
                if priv is not None:
                    dns_servers = []
                    for i in priv.dns_servers:
                        srv = ResolvedDnsServer()
                        srv.address = i  # IPv4Address
                        srv.rdf_server_list = dns
                        srv.from_dhcp = True
                        srv.from_dhcp_rdf_interface = priv_if
                        dns_servers.append(srv)
                    return dns_servers
                else:
                    return []
            else:
                raise Exception('unknown interface in dnsServers')                
        else:
            raise Exception('unknown dnsServers variant')

        raise Exception('internal error - unexpected exit from function')
    
    def _resolve_one_route(self, r, pub_iface, priv_iface, pub_addrinfo, priv_addrinfo):
        rt = ResolvedRoute()
        rt.rdf_route = r

        # subnet
        rt.subnet = r.getS(ns.address, rdf.IPv4Subnet)

        # interface and device (site-to-site routes don't have an interface)
        rt.rdf_interface = None
        rt.devname = None
        if r.hasS(ns.interface):
            rt.rdf_interface = r.getS(ns.interface, rdf.Type(ns.NetworkInterface))
            rt.devname = rt.rdf_interface.getS(ns.interfaceName, rdf.String)
                
        # router (& related)
        router = None
        if not r.hasS(ns.gateway):
            raise Exception('no gateway node in route: %s (%s)' % (rt.subnet.toString(), rt.rdf_interface))
        else:
            gw = r.getS(ns.gateway)
            if gw.hasType(ns.StaticRouter):
                router = gw.getS(ns.address, rdf.IPv4Address)
                rt.router = router
                rt.router_from_dhcp = False
                rt.blackhole = False
            elif gw.hasType(ns.DhcpRouter):
                if rt.rdf_interface == pub_iface:
                    router = pub_addrinfo.router   # may be None
                    rt.router = router
                    rt.router_from_dhcp = True
                    rt.blackhole = False
                elif rt.rdf_interface == priv_iface:
                    router = priv_addrinfo.router  # may be None
                    rt.router = router
                    rt.router_from_dhcp = True
                    rt.blackhole = False
                else:
                    raise Exception('cannot figure out dhcp router interface: %s' % rt.rdf_interface.toString())
            elif gw.hasType(ns.SiteToSiteRouter):
                # this is not very nice but suffices for internal use
                rt.router = None
                rt.router_from_dhcp = False
                rt.blackhole = True
            else:
                raise Exception('unknown variant for gateway')

        # debug
        router_str = 'none'
        if router is not None:
            router_str = router.toString()
        _log.debug('route info: addr=%s iface=%s, devname=%s, router=%s' % (rt.subnet.toString(), rt.rdf_interface, rt.devname, router_str))

        return rt

    def _resolve_routes(self, cfg, pub_addrinfo, priv_addrinfo, route_seq):
        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)

        #
        #  XXX: handle overlapping static + dhcp route  (prefer dhcp)
        #  XXX: at least log overlapping routes in general
        #
        
        ret = []

        # figure out unique subnets
        subdict = {}  # dict of subnets -> route list
        subnets = []  # unique subnets
        for r in route_seq:
            subnet = r.getS(ns.address, rdf.IPv4Subnet)
            subnet_str = subnet.toString()
            if not subdict.has_key(subnet_str):
                subdict[subnet_str] = []
                subnets.append(subnet)
            t = subdict[subnet_str]
            t.append(r)

        # sort
        _log.debug('route keys (subnets), no sort:')
        for i in subnets:
            _log.debug('    ' + i.toString())
        subnets.sort()
        _log.debug('route keys (subnets), after sort:')
        for i in subnets:
            _log.debug('    ' + i.toString())

        # resolve routes in sorted order (starting from "widest")
        got_default_route = False
        for subnet in subnets:
            _log.debug('processing subnet %s' % subnet.toString())
            
            # apply first working route for this subnet
            got_route_for_this_subnet = False
            for r in subdict[subnet.toString()]:
                rt = self._resolve_one_route(r, pub_iface, priv_iface, pub_addrinfo, priv_addrinfo)

                # must have router or blackhole
                if rt.router is None and not rt.blackhole:
                    _log.warning('cannot figure out router for route %s, skipping' % rt.subnet.toString())
                    continue

                ret.append(rt)

                if rt.subnet == datatypes.IPv4Subnet.fromString('0.0.0.0/0'):
                    got_default_route = True

                # success, skip other routes with this same subnet
                got_route_for_this_subnet = True
                break

            if not got_route_for_this_subnet:
                # XXX: should this be 'raise'?
                _log.warning('could not resolve a route for subnet %s' % subnet.toString())

        if not got_default_route:
            _log.warning('did not get a default route')

        return ret
    
    def _resolve_addresses(self, cfg, pub_addrinfo, priv_addrinfo):
        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)

        # private interface
        priv_addr = None
        if priv_if is not None:
            addr = priv_if.getS(ns.address)
            if addr.hasType(ns.StaticAddress):
                priv_addr = addr.getS(ns.address, rdf.IPv4AddressSubnet)
            elif addr.hasType(ns.DhcpAddress):
                priv_addr = priv_addrinfo.address
            else:
                raise Exception('invalid address variant')

        # public interface
        pub_addr = None
        if pub_if is not None:
            addr = pub_if.getS(ns.address)
            if addr.hasType(ns.StaticAddress):
                pub_addr = addr.getS(ns.address, rdf.IPv4AddressSubnet)
            elif addr.hasType(ns.DhcpAddress):
                pub_addr = pub_addrinfo.address
            else:
                raise Exception('invalid address variant')

        return pub_addr, priv_addr

    def _resolve_ppp_dns_wins_servers(self, cfg, pub_addrinfo, priv_addrinfo):
        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(cfg)
        ppp_cfg = cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))

        # dns servers
        if ppp_cfg.hasS(ns.pppDnsServers):
            dns_cfg = ppp_cfg.getS(ns.pppDnsServers)
            dns_list = None

            if dns_cfg.hasType(ns.StaticDnsServers):
                dns_list = []
                for i in dns_cfg.getS(ns.addressList, rdf.Seq(rdf.Type(ns.DnsServer))):
                    srv = ResolvedDnsServer()
                    srv.address = i.getS(ns.address, rdf.IPv4Address)
                    srv.rdf_server_list = dns_cfg
                    srv.from_dhcp = False
                    srv.from_dhcp_rdf_interface = None
                    dns_list.append(srv)
            elif dns_cfg.hasType(ns.DhcpDnsServers):
                iface = dns_cfg.getS(ns.interface, rdf.Type(ns.NetworkInterface))
                if iface == pub_if:
                    if pub_addrinfo is not None:
                        dns_list = []
                        for i in pub_addrinfo.dns_servers:
                            srv = ResolvedDnsServer()
                            srv.address = i  # IPv4Address
                            srv.rdf_server_list = dns_cfg
                            srv.from_dhcp = True
                            srv.from_dhcp_rdf_interface = pub_if
                            dns_list.append(srv)
                    else:
                        dns_list = []
                elif iface == priv_if:
                    if priv_addrinfo is not None:
                        dns_list = []
                        for i in priv_addrinfo.dns_servers:
                            srv = ResolvedDnsServer()
                            srv.address = i  # IPv4Address
                            srv.rdf_server_list = dns_cfg
                            srv.from_dhcp = True
                            srv.from_dhcp_rdf_interface = priv_if
                            dns_list.append(srv)
                    else:
                        dns_list = []
                else:
                    raise Exception('unknown interface for dhcp-assigned dns servers for ppp')
            else:
                # XXX: better exception?  InternalError or something?
                raise Exception('unknown dns servers variant for ppp')

        # wins servers
        if ppp_cfg.hasS(ns.pppWinsServers):
            wins_cfg = ppp_cfg.getS(ns.pppWinsServers)
            wins_list = None

            if wins_cfg.hasType(ns.StaticWinsServers):
                wins_list = []
                for i in wins_cfg.getS(ns.addressList, rdf.Seq(rdf.Type(ns.WinsServer))):
                    srv = ResolvedWinsServer()
                    srv.address = i.getS(ns.address, rdf.IPv4Address)
                    srv.rdf_server_list = wins_cfg
                    srv.from_dhcp = False
                    srv.from_dhcp_rdf_interface = None
                    wins_list.append(srv)
            elif wins_cfg.hasType(ns.DhcpWinsServers):
                iface = wins_cfg.getS(ns.interface, rdf.Type(ns.NetworkInterface))
                if iface == pub_if:
                    if pub_addrinfo is not None:
                        wins_list = []
                        for i in pub_addrinfo.wins_servers:
                            srv = ResolvedWinsServer()
                            srv.address = i  # IPv4Address
                            srv.rdf_server_list = wins_cfg
                            srv.from_dhcp = True
                            srv.from_dhcp_rdf_interface = pub_if
                            wins_list.append(srv)
                    else:
                        wins_list = []
                elif iface == priv_if:
                    if priv_addrinfo is not None:
                        wins_list = []
                        for i in priv_addrinfo.wins_servers:
                            srv = ResolvedWinsServer()
                            srv.address = i  # IPv4Address
                            srv.rdf_server_list = wins_cfg
                            srv.from_dhcp = True
                            srv.from_dhcp_rdf_interface = priv_if
                            wins_list.append(srv)
                    else:
                        wins_list = []
                else:
                    raise Exception('unknown interface for dhcp-assigned wins servers for ppp')
            else:
                # XXX: better exception?  InternalError or something?
                raise Exception('unknown wins servers variant for ppp')

        return dns_list, wins_list
