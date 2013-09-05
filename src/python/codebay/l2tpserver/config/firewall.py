"""Firewall startup and shutdown management."""
__docformat__ = 'epytext en'

import textwrap, re

from codebay.common import rdf
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand

ns = rdfconfig.ns
run_command = runcommand.run_command
_log = logger.get('l2tpserver.config.firewall')

# use with l2tpd
#ppp_interfaces = 'ppp+'

# use with openl2tp
ppp_interfaces = 'l2tp+'

# XXX: handle other link types in addition to ether?
_re_ip_linktype_ether = re.compile(r'^\d:\s([^:]*):.*?link/ether\s.*?$')

class FirewallConfig:
    """Firewall startup and shutdown management."""

    def up_firewall_rules(self, cfg, pub_addr, priv_addr, ppp_forced_iface, ppp_forced_gw):
        """Configure and enable firewall rules."""

        _log.debug('up_firewall_rules')

        # ROUTE support through modprobe test
        retval, stdout, stderr = run_command([constants.CMD_MODPROBE, 'ipt_ROUTE'])
        route_target_supported = False
        if retval == 0:
            route_target_supported = True
            _log.info('ROUTE target support detected')
        else:
            _log.warning('ROUTE target support NOT detected')

        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        fw_cfg = net_cfg.getS(ns.firewallConfig, rdf.Type(ns.FirewallConfig))
        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)
        (_, proxyarp_interface) = helpers.get_proxyarp_iface(cfg)
        pub_nat = helpers.is_public_nat(cfg)
        priv_nat = helpers.is_private_nat(cfg)
        # XXX: this could be in firewall rules
        cli_routing = helpers.is_client_routing(cfg)
        
        pub_addr_str = None
        if pub_addr is not None:
            pub_addr_str = pub_addr.getAddress().toString()

        priv_addr_str = None
        if priv_addr is not None:
            priv_addr_str = priv_addr.getAddress().toString()

        if_dict = {'pub_if':pub_iface_name,
                   'priv_if':priv_iface_name,
                   'ppp_if':ppp_interfaces,
                   'pub_ip':pub_addr_str,
                   'priv_ip':priv_addr_str,
                   'fwmark_ipsec':constants.FWMARK_IPSEC,
                   'fwmark_skipnat':constants.FWMARK_SKIPNAT,
                   'fwmark_ppp':constants.FWMARK_PPP,
                   'fwmark_ppp_s2s':constants.FWMARK_PPP_S2S,
                   'fwmark_local_l2tp':constants.FWMARK_LOCAL_L2TP,
                   'fwmark_license_restricted':constants.FWMARK_LICENSE_RESTRICTED,
                   'http_fwd1':constants.WEBUI_FORWARD_PORT_UIFORCED_HTTP,
                   'https_fwd1':constants.WEBUI_FORWARD_PORT_UIFORCED_HTTPS,
                   'http_fwd2':constants.WEBUI_FORWARD_PORT_LICENSE_HTTP,
                   'https_fwd2':constants.WEBUI_FORWARD_PORT_LICENSE_HTTPS,
                   'http_fwd3':constants.WEBUI_FORWARD_PORT_OLDPSK_HTTP,
                   'https_fwd3':constants.WEBUI_FORWARD_PORT_OLDPSK_HTTPS,
                   }
                   
        #
        #  rules for -t raw
        #

        raw_rules = textwrap.dedent("""\
        -A raw_prerouting -i %(ppp_if)s -j raw_prerouting_ppp

        -A raw_output -o %(ppp_if)s -j raw_output_ppp
        """) % if_dict

        #
        #  rules for -t nat
        #
        
        nat_rules = textwrap.dedent("""\
        -A nat_prerouting -i %(ppp_if)s -j nat_prerouting_ppp
        -A nat_postrouting -o %(ppp_if)s -j nat_postrouting_ppp
        -A nat_output -o %(ppp_if)s -j nat_output_ppp
        """) % if_dict

        pf_cfg = fw_cfg.getS(ns.portForward, rdf.Seq(rdf.Type(ns.PortForwardRule)))
        for i in pf_cfg:
            iface = i.getS(ns.interface, rdf.Type(ns.NetworkInterface)).getS(ns.interfaceName, rdf.String)
            proto = str(i.getS(ns.protocol, rdf.Integer))
            port = str(i.getS(ns.port, rdf.Integer))
            daddr = i.getS(ns.destinationAddress, rdf.IPv4Address).toString()
            dport = str(i.getS(ns.destinationPort, rdf.Integer))

            nat_rules += textwrap.dedent("""\
            -A nat_prerouting -i %(iface)s -p %(proto)s --dport %(port)s -j DNAT --to-destination %(daddr)s:%(dport)s-%(dport)s
            """) % {'iface': iface, 'proto': proto, 'port': port, 'daddr': daddr, 'dport': dport}

        # nat all traffic (both ppp and other), because we support routing of non-client traffic
        if pub_nat:
            # These bizarre rules are used to prevent clients which use our gateway as a router/NAT
            # from accidentally getting an unmodified UDP port when they are using IPsec.  This would
            # be hazardous to IKE because our IKE already uses UDP/500 and UDP/4500 (but may not be
            # running due to a startup race when the client connects).
            #
            # The ports are pretty arbitrary; Linux maps >= 1024 starting from 1024; we choose to
            # start higher to make it easier to track NATted and other ports (and also so that all
            # ports we use, namely 500, 4500, 1701, 1702, etc) are below the start point).
            #
            # Mark 2 is used as a "skip NAT" marker: we can add this mark to e.g. site-to-site packets
            # to avoid NAT for them if we wish.
            #
            # We use a two-chain workaround here to implement NAT: our NAT rule must have a match
            # "not public address AND not private address", but iptables does not support multiple
            # -s matches in the same rule.  So, packets are only NATted if they satisfy:
            #    1. Source address != public address
            #    2. Source address != private address
            #    3. Packet is not marked as "skip NAT"
            #
            # We need to exclude private interface address (from public NAT) to avoid NATting
            # IPsec packets when they are used through the private interface.

            nat_rules += textwrap.dedent("""\
            -A nat_postrouting -o %(pub_if)s ! -s %(pub_ip)s -m mark --mark 0/%(fwmark_skipnat)s -j nat_pub1
            """) % if_dict

            if priv_iface is not None:
                nat_rules += textwrap.dedent("""\
                -A nat_pub1 ! -s %(priv_ip)s -j nat_pub2
                """) % if_dict
            else:
                nat_rules += textwrap.dedent("""\
                -A nat_pub1 -j nat_pub2
                """) % if_dict
                
            nat_rules += textwrap.dedent("""\
            -A nat_pub2 -p tcp -j SNAT --to-source %(pub_ip)s:16384-49151
            -A nat_pub2 -p udp -j SNAT --to-source %(pub_ip)s:16384-49151
            -A nat_pub2 -j SNAT --to-source %(pub_ip)s
            """) % if_dict

        if priv_nat:
            nat_rules += textwrap.dedent("""\
            -A nat_postrouting -o %(priv_if)s ! -s %(priv_ip)s -m mark --mark 0/%(fwmark_skipnat)s -j nat_priv1
            """) % if_dict

            if pub_iface is not None:
                nat_rules += textwrap.dedent("""\
                -A nat_priv1 ! -s %(pub_ip)s -j nat_priv2
                """) % if_dict
            else:
                nat_rules += textwrap.dedent("""\
                -A nat_priv1 -j nat_priv2
                """) % if_dict
                
            nat_rules += textwrap.dedent("""\
            -A nat_priv2 -p tcp -j SNAT --to-source %(priv_ip)s:16384-49151
            -A nat_priv2 -p udp -j SNAT --to-source %(priv_ip)s:16384-49151
            -A nat_priv2 -j SNAT --to-source %(priv_ip)s
            """) % if_dict

        #
        #  rules for -t mangle
        #
        
        mangle_rules = textwrap.dedent("""\
        -A mangle_prerouting -i %(ppp_if)s -j MARK --set-mark %(fwmark_ppp)s
        -A mangle_prerouting -i %(ppp_if)s -j mangle_prerouting_ppp
        -A mangle_prerouting -p esp -j MARK --set-mark %(fwmark_ipsec)s
        -A mangle_prerouting -p udp --dport 500 -j MARK --set-mark %(fwmark_ipsec)s
        -A mangle_prerouting -p udp --dport 4500 -j MARK --set-mark %(fwmark_ipsec)s

        -A mangle_input -i %(ppp_if)s -j mangle_input_ppp

        -A mangle_forward -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu
        -A mangle_forward -i %(ppp_if)s -j mangle_forward_ppp
        -A mangle_forward -o %(ppp_if)s -j mangle_forward_ppp

        -A mangle_output -o %(ppp_if)s -j mangle_output_ppp

        # Not necessary, openl2tp patch
        #-A mangle_output -p udp --sport 1701 -j MARK --set-mark %(fwmark_local_l2tp)s
        #-A mangle_output -p udp --sport 1702 -j MARK --set-mark %(fwmark_local_l2tp)s

        -A mangle_postrouting -o %(ppp_if)s -j mangle_postrouting_ppp
        """) % if_dict

        if (ppp_forced_iface is not None) and (ppp_forced_gw is not None):
            if route_target_supported:
                _log.info('forced routing enabled: %s / %s' % (ppp_forced_iface, ppp_forced_gw.toString()))

                # forced routing is applied but only if packets are not license restricted
                mangle_rules += '\n'
                mangle_rules += ('-A mangle_prerouting -m mark --mark 0/%(fwmark_license_restricted)s -i %(ppp_if)s -j ROUTE' % if_dict) + \
                                (' --oif %s --gw %s\n' % (ppp_forced_iface, ppp_forced_gw.toString()))
            else:
                _log.error('forced routing enabled but route target not supported!')

        #
        #  rules for -t filter  (we accept esp, udp/500, udp/4500 from any interface)
        #

        filter_rules = textwrap.dedent("""\
        -A filter_input -i lo -j ACCEPT
        -A filter_input -m state --state ESTABLISHED,RELATED -j ACCEPT
        -A filter_input -i %(ppp_if)s -j filter_input_ppp

        # esp protected traffic (= l2tp) or IKE
        -A filter_input -m mark --mark %(fwmark_ipsec)s/%(fwmark_ipsec)s -j ACCEPT

        # rate limited public icmp
        -A filter_input -i %(pub_if)s -p icmp -m limit --limit 10/second --limit-burst 50 -j ACCEPT
        -A filter_input -i %(pub_if)s -p icmp -j DROP

        -A filter_input -i %(ppp_if)s -p icmp -j ACCEPT

        # all web ui ports
        -A filter_input -i %(ppp_if)s -p tcp --dport 80 -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport 443 -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(http_fwd1)d -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(https_fwd1)d -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(http_fwd2)d -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(https_fwd2)d -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(http_fwd3)d -j ACCEPT
        -A filter_input -i %(ppp_if)s -p tcp --dport %(https_fwd3)d -j ACCEPT
        """) % if_dict

        if priv_iface is not None:
            # Note: we assume that private interface is always different
            # from public interface if it is defined at all.
            filter_rules += textwrap.dedent("""\
            -A filter_input -i %(priv_if)s -p icmp -m limit --limit 10/second --limit-burst 50 -j ACCEPT
            -A filter_input -i %(priv_if)s -p icmp -j DROP
            """) % if_dict

        ia_cfg = fw_cfg.getS(ns.inputAccept, rdf.Seq(rdf.Type(ns.InputAcceptRule)))
        for i in ia_cfg:
            iface = i.getS(ns.interface, rdf.Type(ns.NetworkInterface)).getS(ns.interfaceName, rdf.String())
            proto = str(i.getS(ns.protocol, rdf.Integer))
            port = str(i.getS(ns.port, rdf.Integer))
            filter_rules += textwrap.dedent("""\
            -A filter_input -i %(iface)s -p %(proto)s --dport %(port)s -j ACCEPT
            """) % {'iface': iface, 'proto': proto, 'port': port}

        filter_rules += textwrap.dedent("""\
        -A filter_output -o %(ppp_if)s -j filter_output_ppp

        -A filter_output -o %(ppp_if)s -j ACCEPT

        -A filter_output -j ACCEPT
        """) % if_dict

        ppp_firewall_rules = ''

        if fw_cfg.hasS(ns.pppFirewallRules):
            fr_cfg = fw_cfg.getS(ns.pppFirewallRules, rdf.Seq(rdf.Type(ns.PppFirewallRule)))
        else:
            fr_cfg = []
        for i in fr_cfg:
            dest = '-d ' + i.getS(ns.subnet, rdf.IPv4Subnet).toString()
            if i.hasS(ns.protocol):
                proto = '-p ' + str(i.getS(ns.protocol, rdf.Integer))
                if i.hasS(ns.port):
                    port = '--dport ' + str(i.getS(ns.port, rdf.Integer))
                else:
                    port = ''
            else:
                proto = ''
                port = ''
            fr_action = i.getS(ns.action)
            if fr_action.hasType(ns.ActionAllow):
                action = 'ACCEPT'
            elif fr_action.hasType(ns.ActionDeny):
                action = 'REJECT --reject-with icmp-port-unreachable'
            else:
                raise Exception('invalid firewall action')
            ppp_firewall_rules += textwrap.dedent("""\
            -A filter_forward_ppp_firewall %(dest)s %(proto)s %(port)s -j %(action)s
            """) % {'dest': dest, 'proto': proto, 'port': port, 'action': action}

        # XXX: conn track?  (e.g. pub->ppp ?)
        filter_rules += textwrap.dedent("""\
        -A filter_forward -m conntrack --ctstate DNAT -j ACCEPT
        -A filter_forward -m state --state ESTABLISHED,RELATED -j ACCEPT
        """) % if_dict


        # client-to-client routing: note that we need to separate between
        # true client-to-client and site-to-site related routing
        if cli_routing:
            _log.info('client-to-client routing allowed, no rule added')
        else:
            # XXX -- This doesn't work (see #828) for client-to-s2s packets.
            # Currently never used.
            # match ppp -> ppp packets with *no* s2s mark
            _log.info('client-to-client routing not allowed, adding firewall rule to prevent')
            _log.error('client-to-client routing not allowed -- but unsupported in this build')
            filter_rules += textwrap.dedent("""\
            -A filter_forward -i %(ppp_if)s -o %(ppp_if)s -m mark --mark 0/%(fwmark_ppp_s2s)s -j DROP
            """) % if_dict

        # ppp forwarding rules are only applied if traffic is not blocked
        # by client-to-client restrictions above
        filter_rules += textwrap.dedent("""\
        -A filter_forward -i %(ppp_if)s -j filter_forward_ppp
        -A filter_forward -o %(ppp_if)s -j filter_forward_ppp

        -A filter_forward -i %(ppp_if)s -o %(pub_if)s -j ACCEPT
        -A filter_forward -i %(pub_if)s -o %(ppp_if)s -j ACCEPT
        -A filter_forward -i %(ppp_if)s -o %(ppp_if)s -j ACCEPT
        """) % if_dict

        # non-client routing
        if priv_iface is not None:
            if fw_cfg.getS(ns.allowNonClientRouting, rdf.Boolean):
                filter_rules += textwrap.dedent("""\
                -A filter_forward -i %(pub_if)s -o %(pub_if)s -j ACCEPT
                -A filter_forward -i %(priv_if)s -o %(priv_if)s -j ACCEPT
                -A filter_forward -i %(priv_if)s -o %(pub_if)s -j ACCEPT
                """) % if_dict
        else:
            if fw_cfg.getS(ns.allowNonClientRouting, rdf.Boolean):
                filter_rules += textwrap.dedent("""\
                -A filter_forward -i %(pub_if)s -o %(pub_if)s -j ACCEPT
                """) % if_dict
        
        if priv_iface is not None:
            filter_rules += textwrap.dedent("""\
            -A filter_forward -i %(ppp_if)s -o %(priv_if)s -j ACCEPT
            -A filter_forward -i %(priv_if)s -o %(ppp_if)s -j ACCEPT
            """) % if_dict

        #
        #  finally, build the tables
        #

        tables = textwrap.dedent("""\
        # Iptables restore script

        *raw
        :PREROUTING ACCEPT
        :OUTPUT ACCEPT
        :raw_prerouting -
        :raw_output -
        :raw_prerouting_ppp -
        :raw_output_ppp -
        :raw_prerouting_ppp_cust -
        :raw_output_ppp_cust -
        -A PREROUTING -j raw_prerouting
        -A OUTPUT -j raw_output
        %(raw_rules)s
        COMMIT

        *filter
        :INPUT DROP
        :FORWARD DROP
        :OUTPUT DROP
        :filter_input -
        :filter_forward -
        :filter_forward_ppp_firewall -
        :filter_output -
        :filter_input_ppp -
        :filter_forward_ppp -
        :filter_output_ppp -
        :filter_input_ppp_cust -
        :filter_forward_ppp_cust -
        :filter_output_ppp_cust -
        -A INPUT -j filter_input
        -A FORWARD -j filter_forward
        -A OUTPUT -j filter_output
        %(filter_rules)s
        %(ppp_firewall_rules)s
        COMMIT

        *nat
        :PREROUTING ACCEPT
        :POSTROUTING ACCEPT
        :OUTPUT ACCEPT
        :nat_prerouting -
        :nat_postrouting -
        :nat_output -
        :nat_prerouting_ppp -
        :nat_postrouting_ppp -
        :nat_output_ppp -
        :nat_prerouting_ppp_cust -
        :nat_postrouting_ppp_cust -
        :nat_output_ppp_cust -
        # chains for public/private natting, see above
        :nat_pub1 -
        :nat_pub2 -
        :nat_priv1 -
        :nat_priv2 -
        -A PREROUTING -j nat_prerouting
        -A POSTROUTING -j nat_postrouting
        -A OUTPUT -j nat_output
        %(nat_rules)s
        COMMIT

        *mangle
        :PREROUTING ACCEPT
        :INPUT ACCEPT
        :FORWARD ACCEPT
        :OUTPUT ACCEPT
        :POSTROUTING ACCEPT
        :mangle_prerouting -
        :mangle_input -
        :mangle_forward -
        :mangle_output -
        :mangle_postrouting -
        :mangle_prerouting_ppp -
        :mangle_input_ppp -
        :mangle_forward_ppp -
        :mangle_output_ppp -
        :mangle_postrouting_ppp -
        :mangle_prerouting_ppp_cust -
        :mangle_input_ppp_cust -
        :mangle_forward_ppp_cust -
        :mangle_output_ppp_cust -
        :mangle_postrouting_ppp_cust -
        -A PREROUTING -j mangle_prerouting
        -A INPUT -j mangle_input
        -A FORWARD -j mangle_forward
        -A OUTPUT -j mangle_output
        -A POSTROUTING -j mangle_postrouting
        %(mangle_rules)s
        COMMIT

        # end of script.
        """) % {'raw_rules':raw_rules,
                'filter_rules':filter_rules,
                'nat_rules':nat_rules,
                'mangle_rules':mangle_rules,
                'ppp_firewall_rules':ppp_firewall_rules}

        _log.debug('iptables-restore script dump:')
        for i, l in enumerate(tables.split('\n')):
            _log.debug('%d: %s' % (i+1, l))
            
        (retval, retout, reterr) = run_command([constants.CMD_IPTABLES_RESTORE], stdin=tables.encode('ascii'), retval=runcommand.FAIL)
        _log.debug('iptables-restore => %s\n%s\n%s' % (retval, retout, reterr))

    def up_qos_rules(self, cfg):
        """Configure and enable quality-of-service configuration."""

        #def _compute_burst(kbits, mtu):
        #    assumed_hz = 250
        #    burst = (float(kbits) / float(assumed_hz))  # example: 1024kbit/s, hz=250 => 4kbit
        #    return '%fkbit' % min(burst*2, (mtu*8.0/1000.0))

        _log.debug('up_qos_rules')

        (pub_iface, pub_iface_name), (priv_iface, priv_iface_name) = helpers.get_ifaces(cfg)
        (_, proxyarp_interface) = helpers.get_proxyarp_iface(cfg)
        qos_cfg = helpers.get_qos_config(cfg)

        if qos_cfg.hasS(ns.globalUplinkRateLimit):
            pub_uplink = qos_cfg.getS(ns.globalUplinkRateLimit, rdf.Integer)
        else:
            pub_uplink = None

        # XXX: add to conf?
        pub_downlink = None
        priv_uplink = None
        priv_downlink = None
        pub_mtu, priv_mtu = helpers.get_iface_mtus(cfg)
        
        _log.debug('qos: %s, %s, %s, %s' % (pub_uplink, pub_downlink, priv_uplink, priv_downlink))

        def_tx_limit = 100  # packets
        sfq_perturb = 30    # seconds
        sfq_quantum = None  # XXX: should we set this? defaults to iface mtu

        if pub_iface_name is not None:
            run_command([constants.CMD_TC, 'qdisc', 'del', 'dev', pub_iface_name, 'root'])

        if priv_iface_name is not None:
            run_command([constants.CMD_TC, 'qdisc', 'del', 'dev', priv_iface_name, 'root'])

        if pub_iface_name is not None:
            if pub_uplink is None:
                # this leaves pfifo_fast in place
                pass
            else:
                pub_rate = '%skbit' % pub_uplink  # only uplink rate is relevant
                #pub_ceil = pub_rate
                #pub_burst = _compute_burst(pub_uplink, pub_mtu)
                run_command([constants.CMD_TC, 'qdisc', 'add', 'dev', pub_iface_name, 'root', 'handle', '1:', 'htb', 'default', '1'], retval=runcommand.FAIL)
                run_command([constants.CMD_TC, 'class', 'add', 'dev', pub_iface_name, 'parent', '1:', 'classid', '1:1', 'htb', 'rate', pub_rate, 'quantum', str(pub_mtu)], retval=runcommand.FAIL)
                run_command([constants.CMD_TC, 'qdisc', 'add', 'dev', pub_iface_name, 'parent', '1:1', 'handle', '10:', 'sfq', 'perturb', str(sfq_perturb)],retval=runcommand.FAIL)

        if priv_iface_name is not None:
            if priv_uplink is None:
                # this leaves pfifo_fast in place
                pass
            else:
                priv_rate = '%skbps' % priv_uplink
                #priv_ceil = priv_rate
                #priv_burst = _compute_burst(priv_uplink, priv_mtu)
                run_command([constants.CMD_TC, 'qdisc', 'add', 'dev', priv_iface_name, 'root', 'handle', '2:', 'htb', 'default', '1'], retval=runcommand.FAIL)
                run_command([constants.CMD_TC, 'class', 'add', 'dev', priv_iface_name, 'parent', '2:', 'classid', '2:1', 'htb', 'rate', priv_rate, 'quantum', str(priv_mtu)], retval=runcommand.FAIL)
                run_command([constants.CMD_TC, 'qdisc', 'add', 'dev', priv_iface_name, 'parent', '2:1', 'handle', '20:', 'sfq', 'perturb', str(sfq_perturb)],retval=runcommand.FAIL)

        if helpers.get_debug(cfg):
            run_command([constants.CMD_TC, '-d', 'qdisc', 'show'])
            run_command([constants.CMD_TC, '-d', 'class', 'show'])

    def down_firewall_rules(self):
        """Disable firewall."""

        _log.debug('down_firewall_rules')
        
        tables = textwrap.dedent("""\
        # Iptables restore script

        *raw
        :PREROUTING ACCEPT
        :OUTPUT ACCEPT
        COMMIT

        *filter
        :INPUT ACCEPT
        :FORWARD ACCEPT
        :OUTPUT ACCEPT
        COMMIT

        *nat
        :PREROUTING ACCEPT
        :POSTROUTING ACCEPT
        :OUTPUT ACCEPT
        COMMIT

        *mangle
        :PREROUTING ACCEPT
        :INPUT ACCEPT
        :FORWARD ACCEPT
        :OUTPUT ACCEPT
        :POSTROUTING ACCEPT
        COMMIT

        # end of script.
        """)

        _log.debug('iptables-restore script:\n%s' % tables.encode('ascii'))
        (retval, retout, reterr) = run_command([constants.CMD_IPTABLES_RESTORE], stdin=tables.encode('ascii'), retval=runcommand.FAIL)
        _log.debug('iptables-restore => %s\n%s\n%s' % (retval, retout, reterr))

    def down_qos_rules(self):
        """Disable quality-of-service configuration."""

        _log.debug('down_qos_rules')
        
        # XXX: this is not a clean way to do this, but we need to be prepared to clear
        # rules even for interfaces not currently mentioned in the configuration -- it
        # may be that the configuration changed but "stop" was not executed with old
        # config.

        # XXX: this is not only unclean but potentially incorrect:
        # if interfaces are not type "link/ether" in "ip" output, this will
        # be incorrect.

        (retval, retout, reterr) = run_command([constants.CMD_IP, '-o', '-f', 'link', 'link', 'list'])
        if retval != 0:
            _log.error('Command to get interface list failed.') # XXX: log exception from runcommand?
            raise Exception('Cannot get interface list.')

        devs = []
        for i in retout.split('\n'):
            m = _re_ip_linktype_ether.match(i)
            if m is not None:
                devs.append(m.group(1))

        for i in devs:
            # XXX: perhaps tolerate return value 2 (no setup)?
            run_command([constants.CMD_TC, 'qdisc', 'del', 'dev', i, 'root'])

        # classes are deleted automatically (probably)

    def disable_forwarding(self):
        """Disable packet forwarding."""

        _log.debug('disable_forwarding')
        helpers.write_file ('/proc/sys/net/ipv4/ip_forward', '0', perms=None)

    def enable_forwarding(self):
        """Enable packet forwarding."""

        _log.debug('enable_forwarding')
        helpers.write_file ('/proc/sys/net/ipv4/ip_forward', '1', perms=None)

    def modprobe_nat_conntrack_modules(self):
        for i in [ 'ip_conntrack',
                   'ip_conntrack_ftp',
                   'ip_conntrack_tftp',
                   'ip_nat',
                   'ip_nat_ftp',
                   'ip_nat_tftp',
                   'ip_nat_snmp_basic' ]:
            try:
                _log.debug('modprobing %s' % i)
                run_command([constants.CMD_MODPROBE, i], retval=runcommand.FAIL)
            except:
                _log.exception('failed to modprobe %s, ignoring' % i)
        
    def flush_conntrack(self):
        """Flush conntrack state."""

        try:
            run_command([constants.CMD_CONNTRACK, '-F'], retval=runcommand.FAIL)
        except:
            _log.exception('flush_conntrack failed')
        
