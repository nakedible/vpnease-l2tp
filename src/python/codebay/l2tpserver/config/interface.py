"""Configure network interfaces."""
__docformat__ = 'epytext en'

import os
from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand

ns = rdfconfig.ns
run_command = runcommand.run_command
_log = logger.get('l2tpserver.config.interface')

# XXX: constants?
MAX_ETH_DEVICES = 10

class InterfaceConfig:
    """Configure network interfaces."""

    def set_rp_filter(self, iface, value):
        """Set RP filter for interface to specific value (boolean).

        This writes to /proc/sys directly; iface='all' is OK.

        NB: Interface must have an IP address before the relevant
        /proc dir will appear.
        """

        _log.debug('set_rp_filter: %s -> %s' % (iface, value))

        t = 0
        if value:
            t = 1

        fname = str('/proc/sys/net/ipv4/conf/%s/rp_filter' % iface)
        f = open(fname, 'wb')
        _log.debug('set_rp_filter: fd=%s' % f.fileno())
        f.write('%d\n' % t)
        f.flush()
        f.close()
        
    def _prepare_interface(self, iface_name, mtu):
        # XXX: add linklocal address?

        # XXX: should this except on fail? If interface doesn't exist,
        # it fails and excepts, which is probably OK (though the
        # second command would fail anyway).  (ip addr flush on an
        # interface without an address does print 'Nothing to flush'
        # but the RC is zero...)

        # XXX: check existence and throw appropriate exception if
        # doesn't exist

        run_command([constants.CMD_IP, 'addr', 'flush', iface_name], retval=runcommand.FAIL)
        run_command([constants.CMD_IP, 'link', 'set', iface_name, 'up', 'mtu', str(mtu)], retval=runcommand.FAIL)

    def prepare_interfaces(self, cfg):
        """Configure interfaces up without IP addresses."""

        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)
        (pub_mtu, priv_mtu) = helpers.get_iface_mtus(cfg)

        self.set_rp_filter('all', False)

        if pub_iface is not None:
            self._prepare_interface(pub_iface_name, pub_mtu)
        if priv_iface is not None:
            self._prepare_interface(priv_iface_name, priv_mtu)

    def _check_interface_existence(self, interface):
        """Check existence of interface."""

        [rv, stdout, stderr] = run_command([constants.CMD_IP, 'link', 'show', interface])
        if rv != 0:
            return False
        return True

    def check_interface_existences(self, cfg):
        """Check existence of interfaces."""

        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)

        if pub_iface is not None:
            if not self._check_interface_existence(pub_iface_name):
                return False

        if priv_iface is not None:
            if not self._check_interface_existence(priv_iface_name):
                return False

        return True
    
    def interface_set_address(self, interface, address):
        """Configure interface with IP address."""

        run_command([constants.CMD_IP, 'addr', 'flush', 'dev', interface], retval=runcommand.FAIL)
        run_command([constants.CMD_IP, 'addr', 'add', address.toString(), 'dev', interface], retval=runcommand.FAIL)

        self.set_rp_filter(interface, False)

    def _set_proxyarp(self, ifname, val):
        """We avoid extra proxy ARP writes here to minimize VMware problems.

        See #890.
        """

        # is the proxy ARP change needed?
        fname = '/var/run/proxyarp-state-%s' % ifname   # XXX: fixed path
        prev_state = None
        try:
            if not os.path.exists(fname):
                prev_state = 0
            else:
                f = None
                try:
                    f = open(fname, 'rb')
                    tmpval = f.read()
                    tmpval = tmpval.strip()
                    prev_state = int(tmpval)
                finally:
                    if f is not None:
                        f.close()
                        f = None
        except:
            _log.exception('failed to read previous proxyarp state')
                    
        if (prev_state is None) or (prev_state != val):
            _log.info('proxyarp value actually changing %s -> %s, iface %s' % (prev_state, val, ifname))

            # XXX: do we want to fail with exceptions here?
            _log.debug('setting proxy ARP for interface %s to %d' % (ifname, val))
            retval, stdout, stderr = run_command(['%s %d > /proc/sys/net/ipv4/conf/%s/proxy_arp' % (constants.CMD_ECHO, val, ifname)], shell=True)
            _log.debug(' --> retval %d' % retval)
        else:
            _log.debug('proxyarp value not changing %s -> %s, iface %s' % (prev_state, val, ifname))

        # write new proxy ARP state
        try:
            f = None
            try:
                f = open(fname, 'wb')
                f.write('%d\n' % val)
            finally:
                if f is not None:
                    f.close()
                    f = None
        except:
            _log.exception('failed to write proxyarp state')
        
    def _down_proxyarp(self, res_info):
        # XXX: how to do this for all interfaces? enumerate directory?
        # this now relies on us knowing the interfaces from res_info
        if (res_info.public_interface is not None) and (res_info.public_interface.device is not None):
            self._set_proxyarp(res_info.public_interface.device, 0)
        if (res_info.private_interface is not None) and (res_info.private_interface.device is not None):
            self._set_proxyarp(res_info.private_interface.device, 0)

    def up_proxyarp(self, cfg, res_info):
        _log.info('proxyarp up')
        self._down_proxyarp(res_info)
        (proxyarp_iface, proxyarp_ifname) = helpers.get_proxyarp_iface(cfg)
        if proxyarp_ifname is not None:
            self._set_proxyarp(proxyarp_ifname, 1)
            
    def down_proxyarp(self):
        _log.info('proxyarp down')
        # XXX: currently we're called without parameters so we can only loop :(
        for i in xrange(MAX_ETH_DEVICES):  # XXX: max devices
            try:
                self._set_proxyarp('eth%d' % i, 0)  # XXX
            except:
                _log.exception('failed to clear proxyarp, not fatal')
        
    def up_dns(self, dns_servers):
        resolvconf = '# automatically generated, do not edit\n'
        for srv in dns_servers:
            addr = srv.address
            if addr is not None:  # XXX: when?
                resolvconf += 'nameserver %s\n' % addr.toString()
        helpers.write_file('/etc/resolv.conf', resolvconf, perms=0644)

    def up_routes(self, cfg, res_info):
        """Setup routes.

        The subnets of our interfaces prevail against route overlaps.  For instance,
        if there is a route with the exactly same subnet as DHCP assigned subnet, the
        DHCP subnet prevails over the route.  However, a warning is logged.  Other
        route overlaps are not checked for, as such checks can be done statically.
        """

        # route tables are created automatically

        # prevent overlapping routes for these (interface subnets); these prevail if
        # routes overlap, and a warning is generated
        avoid_subnets = []
        if res_info.public_interface is not None:
            avoid_subnets.append(res_info.public_interface.address.getSubnet())
        if res_info.private_interface is not None:
            avoid_subnets.append(res_info.private_interface.address.getSubnet())

        def _get_dev_subnet(devname):
            if res_info.public_interface is not None and res_info.public_interface.device == devname:
                return res_info.public_interface.address
            if res_info.private_interface is not None and res_info.private_interface.device == devname:
                return res_info.private_interface.address
            raise Exception('cannot figure out device subnet: dev=%s' % devname)

        def _setup_route(tableid, subnet, devname, gateway, blackhole):
            if blackhole:
                cmd = [constants.CMD_IP, 'route', 'replace', 'blackhole', subnet.toString(), 'table', tableid, 'metric', constants.ROUTE_CATCHALL_METRIC]
            else:
                devsubnet = _get_dev_subnet(devname)
                if not devsubnet.inSubnet(gateway):
                    _log.warning('route (%s) gateway (%s) not in device subnet (%s), tableid %s, dev %s' % (subnet.toString(),
                                                                                                            gateway.toString(),
                                                                                                            devsubnet.toString(),
                                                                                                            tableid,
                                                                                                            devname))
                cmd = [constants.CMD_IP, 'route', 'add', subnet.toString(), 'table', tableid, 'via', gateway.toString(), 'dev', devname, 'onlink']
            run_command(cmd, retval=runcommand.FAIL)

        def _setup_route_direct(tableid, subnet, devname):
            cmd = [constants.CMD_IP, 'route', 'add', subnet.toString(), 'table', tableid, 'dev', devname]
            run_command(cmd, retval=runcommand.FAIL)

        def _check_overlap(subnet):
            for i in avoid_subnets:
                _log.debug('_check_overlap: avoid=%s, subnet=%s' % (i.toString(), subnet.toString()))
                if i == subnet:
                    return True
            return False
        
        # local subnets (directly connected)
        for tableid in [ constants.ROUTE_TABLE_GATEWAY,
                         constants.ROUTE_TABLE_CLIENT ]:
            # ip addr add actually adds the route already, so skip here
            if tableid == constants.ROUTE_TABLE_GATEWAY:
                continue
            
            if res_info.public_interface is not None:
                _setup_route_direct(tableid, res_info.public_interface.address.getSubnet(), res_info.public_interface.device)
            if res_info.private_interface is not None:
                _setup_route_direct(tableid, res_info.private_interface.address.getSubnet(), res_info.private_interface.device)

        # gateway routes
        for r in res_info.gateway_routes:
            subnet, devname, gateway, blackhole = r.subnet, r.devname, r.router, r.blackhole
            if _check_overlap(subnet):
                _log.warning('route (%s) (gateway routes); overlaps with interface subnet, dev=%s, skipping' % (subnet.toString(), devname))
            else:
                _setup_route(constants.ROUTE_TABLE_GATEWAY, subnet, devname, gateway, blackhole)
            
        # client routes
        for r in res_info.client_routes:
            subnet, devname, gateway, blackhole = r.subnet, r.devname, r.router, r.blackhole
            if _check_overlap(subnet):
                _log.warning('route (%s) (client routes); overlaps with interface subnet, dev=%s, skipping' % (subnet.toString(), devname))
            else:
                _setup_route(constants.ROUTE_TABLE_CLIENT, subnet, devname, gateway, blackhole)

        # Note: this is not actually used now, because Openl2tp was patched instead.
        #       this is disabled in firewall by not marking the packets
        #
        # This 'magic' route is used to ensure that all locally generated L2TP traffic
        # is 'routed' through the public interface, thus getting the correct local
        # address for IPsec processing.  IPsec will cause the packet to be rerouted
        # correctly once it has been processed.
        #
        # (NB: don't use 'onlink' when 'via' is own IP.)
        l2tp_gw = res_info.public_interface.address.getAddress().toString()  # bogus router
        run_command([constants.CMD_IP, 'route', 'add', '0.0.0.0/0', 'table', constants.ROUTE_TABLE_LOCAL_L2TP, 'via', l2tp_gw, 'dev', res_info.public_interface.device], retval=runcommand.FAIL)

        # rules for selecting tables (gateway routes defaults correctly)
        for i in [ [constants.CMD_IP, 'rule', 'add', 'fwmark', constants.FWMARK_PPP, 'table', constants.ROUTE_TABLE_CLIENT],
                   [constants.CMD_IP, 'rule', 'add', 'fwmark', constants.FWMARK_LOCAL_L2TP, 'table', constants.ROUTE_TABLE_LOCAL_L2TP] ]:
            run_command(i, retval=runcommand.FAIL)

    def down_interfaces(self):
        """Configure network interfaces down."""

        try:
            dhclient_pid = int(open(constants.DHCLIENT_PIDFILE).read().strip())
            run_command([constants.CMD_KILL, str(dhclient_pid)])
        except:
            _log.debug('failed to kill dhclient, may be OK')

        try:
            # XXX: give some time?
            run_command([constants.CMD_KILLALL, '-9', 'dhclient'])
        except:
            pass
        
        for i in xrange(MAX_ETH_DEVICES):  # XXX: max devices
            dev = 'eth%d' % i
            run_command([constants.CMD_IP, 'addr', 'flush', dev])
            run_command([constants.CMD_IP, 'link', 'set', dev, 'down'])

    def down_routes(self):
        """Tear down routes."""

        _log.debug('down_routes')

        for i, j in [ [constants.ROUTE_TABLE_CLIENT, constants.FWMARK_PPP],
                      [constants.ROUTE_TABLE_LOCAL_L2TP, constants.FWMARK_LOCAL_L2TP] ]:
            run_command([constants.CMD_IP, 'rule', 'del', 'fwmark', j, 'table', i])

        for i in [constants.ROUTE_TABLE_GATEWAY,
                  constants.ROUTE_TABLE_LOCAL_L2TP,
                  constants.ROUTE_TABLE_CLIENT]:
            run_command([constants.CMD_IP, 'route', 'flush', 'table', i], retval=runcommand.FAIL)

        for i in [constants.ROUTE_TABLE_CLIENT,
                  constants.ROUTE_TABLE_LOCAL_L2TP]:
            run_command([constants.CMD_IP, 'route', 'del', 'table', i])

    def flush_route_cache(self):
        """Flush route cache."""
        run_command([constants.CMD_IP, 'route', 'flush', 'cache'])

    # XXX: the arping command itself could be refactored
    def arping_routers(self, res_info):
        """Arping routers to update their ARP tables."""

        pubif = None
        if res_info.public_interface is not None:
            pubif = res_info.public_interface.device
        privif = None
        if res_info.private_interface is not None:
            privif = res_info.private_interface.device

        routers = {}
        for r in res_info.gateway_routes + res_info.client_routes:
            subnet, devname, gateway, blackhole = r.subnet, r.devname, r.router, r.blackhole
            if (gateway is None) or blackhole:
                _log.debug('skipping route in arping, gw is None or blackhole')
                continue

            gw_str = gateway.toString()
            if routers.has_key(gw_str):
                _log.debug('skipping route in arping, already done, gw=%s' % gw_str)
                continue

            routers[gw_str] = 1
            srcaddr = None
            if devname == pubif:
                srcaddr = res_info.public_interface.address.getAddress().toString()
            elif devname == privif:
                srcaddr = res_info.private_interface.address.getAddress().toString()
            else:
                _log.warning('invalid device %s, skipping arping' % devname)
                continue

            # NB: we don't care about the return value.  If the router doesn't
            # respond, we'll arping later in health check anyway.  We are not
            # trying to *check* that the router exists here, but rather to update
            # its ARP cache.
            _log.debug('arpinging router %s' % gw_str)
            run_command(str('%s -f -c 3 -w 0.1 -s %s -I -%s %s &>/dev/null &' % (constants.CMD_ARPING, str(srcaddr), str(devname), gw_str)), shell=True)

    # XXX: grat arp and above arping could be backgrounded to speed up startup
    def send_gratuitous_arps(self, res_info):
        """Send grat ARPs to update everyone's ARP cache."""

        if res_info.public_interface is not None:
            _log.debug('grat arping public interface')
            run_command(str('%s -b -c 3 -w 0.1 -U -I %s %s &>/dev/null &' % (constants.CMD_ARPING, res_info.public_interface.device, res_info.public_interface.address.getAddress().toString())), shell=True)
            run_command(str('%s -b -c 3 -w 0.1 -A -I %s %s &>/dev/null &' % (constants.CMD_ARPING, res_info.public_interface.device, res_info.public_interface.address.getAddress().toString())), shell=True)
            
        if res_info.private_interface is not None:
            _log.debug('grat arping private interface')
            run_command(str('%s -b -c 3 -w 0.1 -U -I %s %s &>/dev/null &' % (constants.CMD_ARPING, res_info.private_interface.device, res_info.private_interface.address.getAddress().toString())), shell=True)
            run_command(str('%s -b -c 3 -w 0.1 -A -I %s %s &>/dev/null &' % (constants.CMD_ARPING, res_info.private_interface.device, res_info.private_interface.address.getAddress().toString())), shell=True)
