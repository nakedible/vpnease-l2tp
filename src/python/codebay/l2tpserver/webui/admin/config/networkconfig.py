"""Administrator configuration pages."""
__docformat__ = 'epytext en'

import formal

from codebay.common import rdf
from codebay.common import logger
from codebay.common import datatypes

from codebay.nevow.formalutils import formdatatypes as dt
from codebay.nevow.formalutils import formalutils

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns_ui

from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui.admin import uitexts
from codebay.l2tpserver.webui.admin.config import networkconfigvalidation
from codebay.l2tpserver.webui import uidatahelpers
from codebay.l2tpserver.webui import uihelpers

_log = logger.get('l2tpserver.webui.admin.config.networkconfig')


class NetworkPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/config/networkconfig.xhtml'
    pagetitle = 'Configuration / Network'

    nc_uitexts = uitexts.NetworkConfigTexts()
    route_uitexts = uitexts.RoutesTexts()
    cc_uitexts = uitexts.ClientConnectionTexts()
    fw_uitexts = uitexts.FirewallTexts()
        
    def fill_network_config(self, form, ctx, fda):
        def _fill_address_to_form(rdf_node, fda):
            if (rdf_node.getS(ns_ui.address).hasType(ns_ui.DhcpAddress)):
                fda['ip_address_selection'] = 'dhcp'
            elif (rdf_node.getS(ns_ui.address).hasType(ns_ui.StaticAddress)):
                fda['ip_address_selection'] = 'static'
                fda['ip_address'] = rdf_node.getS(ns_ui.address).getS(ns_ui.ipAddress, rdf.IPv4Address)
                fda['subnet_mask'] = rdf_node.getS(ns_ui.address).getS(ns_ui.subnetMask, rdf.IPv4Address)
            else:
                raise uidatahelpers.RdfDataError('ns_ui.address is not dhcp or static')  
            
        def _fill_client_traffic_to_form(rdf_node, fda):
            if rdf_node.getS(ns_ui.clientConnectionNat, rdf.Boolean):
                fda['client_traffic'] = 'nat'
            elif rdf_node.getS(ns_ui.clientConnectionProxyArp, rdf.Boolean):
                fda['client_traffic'] = 'proxyarp'
            else:
                fda['client_traffic'] = 'none'
            
        root = helpers.get_ui_config()

        # interface count (ifcount_group)
        ifc_fda = fda.descend('ifcount_group')
        if root.hasS(ns_ui.privateNetworkConnection):
            ifc_fda['interface_count'] = 'twoif'
            pn_root = root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
        else:
            ifc_fda['interface_count'] = 'oneif'
            pn_root = None
                
        # internet connection (ic_group)
        ic_root = root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
        ic_fda = fda.descend('ic_group')
        ic_fda['if'] = ic_root.getS(ns_ui.interface, rdf.String)
        _fill_address_to_form(ic_root, ic_fda)
        uidatahelpers.fill_optional_field_to_form(ic_root, ns_ui.defaultGateway, rdf.IPv4Address, ic_fda, 'default_gateway')
        ic_fda['mtu'] = ic_root.getS(ns_ui.mtu, rdf.Integer)
        uidatahelpers.fill_optional_field_to_form(ic_root, ns_ui.vpnUplink, rdf.Float, ic_fda, 'uplink')
        _fill_client_traffic_to_form(ic_root, ic_fda)

        # private network connection (pn_group)
        if not(pn_root is None):
            pn_fda = fda.descend('pn_group')
            pn_fda['if'] = pn_root.getS(ns_ui.interface, rdf.String)
            _fill_address_to_form(pn_root, pn_fda)
            uidatahelpers.fill_optional_field_to_form(pn_root, ns_ui.defaultGateway, rdf.IPv4Address, pn_fda, 'default_gateway')
            _fill_client_traffic_to_form(pn_root, pn_fda)

        # dns servers (dns_group)
        dns_root = root.getS(ns_ui.dnsServers)
        dns_fda = fda.descend('dns_group')
        if dns_root.hasType(ns_ui.InternetConnectionDhcp):
            dns_fda['dns_selection'] = 'use_dhcp_ic'
        elif dns_root.hasType(ns_ui.PrivateNetworkConnectionDhcp):
            dns_fda['dns_selection'] = 'use_dhcp_pn'
        elif dns_root.hasType(ns_ui.SetDnsServers):
            dns_fda['dns_selection'] = 'set_manually'
            dns_exists = False
            if dns_root.hasS(ns_ui.primaryDns):
                dns_exists = True
                dns_fda['dns_1'] = dns_root.getS(ns_ui.primaryDns, rdf.IPv4Address)
            if dns_root.hasS(ns_ui.secondaryDns):
                dns_exists = True 
                dns_fda['dns_2'] = dns_root.getS(ns_ui.secondaryDns, rdf.IPv4Address)  
            if not(dns_exists):
                _log.warning('no dns servers when filling form data')
        else:
            raise uidatahelpers.RdfDataError('Unknown DNS server information selection')
                    
        # dynamic dns (ddns_group)
        ddns_fda = fda.descend('ddns_group')
        if root.hasS(ns_ui.dynDnsServer):
            ddns_root = root.getS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))
            ddns_fda['ddns_provider'] = ddns_root.getS(ns_ui.dynDnsProvider, rdf.String)
            ddns_fda['ddns_username'] = ddns_root.getS(ns_ui.dynDnsUsername, rdf.String)
            ddns_fda['ddns_password'] = ddns_root.getS(ns_ui.dynDnsPassword, rdf.String)
            ddns_fda['ddns_hostname'] = ddns_root.getS(ns_ui.dynDnsHostname, rdf.String)
            if ddns_root.hasS(ns_ui.dynDnsAddress):
                tmp = ddns_root.getS(ns_ui.dynDnsAddress, rdf.String)
                if tmp == '':
                    ddns_fda['ddns_address_type'] = 'interface'
                    ddns_fda['ddns_address'] = ''
                elif tmp == 'natted':
                    ddns_fda['ddns_address_type'] = 'natted'
                    ddns_fda['ddns_address'] = ''
                else:
                    ddns_fda['ddns_address_type'] = 'static'
                    ddns_fda['ddns_address'] = tmp
            else:
                ddns_fda['ddns_address_type'] = 'interface'
                ddns_fda['ddns_address'] = ''
        else:
            ddns_fda['ddns_provider'] = 'none'
            
    def fill_client_connection_group(self, form, ctx, cc_fda):
        ui_root = helpers.get_ui_config()

        # Server address & psk
        #if ui_root.hasS(ns_ui.vpnServerAddress):
        #    cc_fda['server_name'] = ui_root.getS(ns_ui.vpnServerAddress, rdf.String)
        #else:
        #    cc_fda['server_name'] = ''
        cc_fda['psk_1'] = ''
        cc_fda['psk_2'] = ''
        psk_seq = ui_root.getS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey)))
        if len(psk_seq) >= 1:
            cc_fda['psk_1'] = psk_seq[0].getS(ns_ui.preSharedKey, rdf.String)
        if len(psk_seq) >= 2:
            cc_fda['psk_2'] = psk_seq[1].getS(ns_ui.preSharedKey, rdf.String)
        dns_root = ui_root.getS(ns_ui.clientDnsServers)

        # DNS
        if dns_root.hasType(ns_ui.NetworkConnectionDns):
            cc_fda['dns'] = 'use_ic_dns'
        elif dns_root.hasType(ns_ui.SetDnsServers):
            cc_fda['dns'] = 'manual_dns'                
            uidatahelpers.fill_optional_field_to_form(dns_root, ns_ui.primaryDns, rdf.IPv4Address, cc_fda, 'dns_1')
            uidatahelpers.fill_optional_field_to_form(dns_root, ns_ui.secondaryDns, rdf.IPv4Address, cc_fda, 'dns_2')
        else:
            raise uidatahelpers.RdfDataError('Client connection dns servers is neither Network connection dns nor set dns servers.')

        uidatahelpers.fill_optional_field_to_form(ui_root, ns_ui.clientPrimaryWins, rdf.IPv4Address, cc_fda, 'wins_1')
        uidatahelpers.fill_optional_field_to_form(ui_root, ns_ui.clientSecondaryWins, rdf.IPv4Address, cc_fda, 'wins_2')
        cc_fda['client_subnet'] = ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet)
        cc_fda['client_address_range'] = ui_root.getS(ns_ui.clientAddressRange, rdf.IPv4AddressRange)
        cc_fda['client_compression'] = ui_root.getS(ns_ui.clientCompression, rdf.Boolean)
            
    def create_iface_count_group(self, form, ctx):
        txt = self.nc_uitexts
        g = formalutils.CollapsibleGroup('ifcount_group', label='Network Setup')
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseInterfaceCount))
        g.add(formalutils.Field('interface_count', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.ifcount_options), 
                                label=txt.ifcount_label))
        return g

    def create_internet_connection_group(self, form, ctx):
        txt = self.nc_uitexts
        g = formalutils.CollapsibleGroup('ic_group', label=txt.ic_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseInternetConnection))
        g.add(formalutils.Field('if', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=uihelpers.interface_options()),
                                label=txt.if_label))
        g.add(formalutils.Field('ip_address_selection', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.ip_selection_options),
                                label=txt.ip_selection_label))
        g.add(formalutils.Field('ip_address', dt.FormIPv4AddressSubnet(required=False), label=txt.ip_label))
        g.add(formalutils.Field('subnet_mask', dt.FormSubnetMask(required=False), label=txt.subnet_label))
        g.add(formalutils.Field('default_gateway', dt.FormIPv4Address(required=False), label=txt.default_gw_label))
        g.add(formalutils.Field('mtu', formal.Integer(required=True, validators=[formal.RangeValidator(min=576, max=1500)]), label=txt.mtu_label))
        g.add(formalutils.Field('uplink', dt.FormFloat(required=False, validators=[formal.RangeValidator(min=0.128)]), label=txt.uplink_label))
        g.add(formalutils.Field('client_traffic', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.client_traffic_options),
                                label=txt.client_traffic_label))
        return g

    def create_private_network_group(self, form, ctx):
        txt = self.nc_uitexts
        g = formalutils.CollapsibleGroup('pn_group', label=txt.pn_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapsePrivateNetwork))
        g.add(formalutils.Field('if', formal.String(required=False),
                                formal.widgetFactory(formal.SelectChoice, options=uihelpers.interface_options()),
                                label=txt.if_label))
        g.add(formalutils.Field('ip_address_selection', formal.String(required=False),
                                formal.widgetFactory(formal.RadioChoice, options=txt.ip_selection_options),
                                label=txt.ip_selection_label))
        g.add(formalutils.Field('ip_address', dt.FormIPv4AddressSubnet(required=False), label=txt.ip_label))
        g.add(formalutils.Field('subnet_mask', dt.FormSubnetMask(required=False), label=txt.subnet_label))
        g.add(formalutils.Field('default_gateway', dt.FormIPv4Address(required=False), label=txt.default_gw_label))
        g.add(formalutils.Field('client_traffic', formal.String(required=False),
                                formal.widgetFactory(formal.RadioChoice, options=txt.client_traffic_options),
                                label=txt.client_traffic_label))
        return g

    def create_dns_group(self, form, ctx):
        txt = self.nc_uitexts
        g = formalutils.CollapsibleGroup('dns_group', label=txt.dns_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseDns))
        g.add(formalutils.Field('dns_selection', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.dns_select_options),
                                label=txt.dns_select_label))
        g.add(formalutils.Field('dns_1', dt.FormIPv4Address(required=False), label=txt.primary_dns_label))
        g.add(formalutils.Field('dns_2', dt.FormIPv4Address(required=False), label=txt.secondary_dns_label))
        return g

    def create_dynamic_dns_group(self, form, ctx):
        txt = self.nc_uitexts
        g = formalutils.CollapsibleGroup('ddns_group', label=txt.ddns_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseDynamicDns))
        # XXX: provider is required, but 'none' option is 'disabled'
        g.add(formalutils.Field('ddns_provider', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=txt.ddns_providers),
                                label=txt.ddns_providers_label))
        g.add(formalutils.Field('ddns_username', formal.String(required=False), label=txt.ddns_username_label))
        g.add(formalutils.Field('ddns_password', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label=txt.ddns_password_label))
        g.add(formalutils.Field('ddns_hostname', formal.String(required=False), label=txt.ddns_hostname_label))

        ddns_address_options = [
            ('interface', 'Use Internet connection IP address'),
            ('natted', 'Use NATted Internet connection IP address'),
            ('static', 'Use the following IP address'),
            ]
        g.add(formalutils.Field('ddns_address_type', formal.String(required=False),
                                formal.widgetFactory(formal.RadioChoice, options=ddns_address_options),
                                label='IP address to update'))

        g.add(formalutils.Field('ddns_address', formal.String(required=False), label='Static IP address'))
        return g

    def create_client_connection_group(self, form, ctx):
        txt = self.cc_uitexts
        
        def create_client_connection_group():
            cc_group = formalutils.CollapsibleGroup('client_connection', label=txt.cc_group_caption)
            cc_group.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseClientConnection))
            #cc_group.add(formalutils.Field('server_name', formal.String(required=False), label=txt.server_address_label))
            cc_group.add(formalutils.Field('psk_1', formal.String(required=True),
                                           formal.widgetFactory(formalutils.SemiHiddenPassword),
                                           label='Primary pre-shared key'))
            cc_group.add(formalutils.Field('psk_2', formal.String(required=False),
                                           formal.widgetFactory(formalutils.SemiHiddenPassword),
                                           label='Secondary pre-shared key'))
            cc_group.add(formalutils.Field('dns', formal.String(required=True),
                                           formal.widgetFactory(formal.RadioChoice, options=txt.client_dns_options),
                                           label=txt.client_dns_options_label))
            cc_group.add(formalutils.Field('dns_1', dt.FormIPv4Address(required=False), label=txt.primary_dns_label))
            cc_group.add(formalutils.Field('dns_2', dt.FormIPv4Address(required=False), label=txt.secondary_dns_label))
            cc_group.add(formalutils.Field('wins_1', dt.FormIPv4Address(required=False), label=txt.primary_wins_label))
            cc_group.add(formalutils.Field('wins_2', dt.FormIPv4Address(required=False), label=txt.secondary_wins_label))
            cc_group.add(formalutils.Field('client_subnet', dt.FormIPv4Subnet(required=True), label=txt.client_subnet_label))
            cc_group.add(formalutils.Field('client_address_range', dt.FormIPv4AddressRange(required=True), label=txt.client_address_range_label))
            cc_group.add(formalutils.Field('client_compression', formal.Boolean(required=True), label='VPN client traffic compression'))
            return cc_group

        # XXX: one level was collapsed, hence wrapping
        client_connection = create_client_connection_group()
        return client_connection  

    @db.transact()
    def form_config(self, ctx):        
        form = formal.Form()

        ifcount = self.create_iface_count_group(form, ctx)
        pubif = self.create_internet_connection_group(form, ctx)
        privif = self.create_private_network_group(form, ctx)
        dns = self.create_dns_group(form, ctx)
        dyndns = self.create_dynamic_dns_group(form, ctx)
        client = self.create_client_connection_group(form, ctx)

        form.add(ifcount)
        form.add(pubif)
        form.add(privif)
        form.add(dns)
        form.add(dyndns)
        form.add(client)

        try:
            # XXX: this data filler is one unit because ifcount, pubif, privif, dns, and dyndns
            # were previously part of one group
            fda = formalutils.FormDataAccessor(form, [], ctx)
            self.fill_network_config(form, ctx, fda)
        except:
            _log.exception('failed to fill in form data, ignoring')

        try:
            cc_fda = formalutils.FormDataAccessor(form, ['client_connection'], ctx)
            self.fill_client_connection_group(form, ctx, cc_fda)
        except:
            _log.exception('failed to fill in form data, ignoring')

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False)        
        return form
    
    def save_network_data(self, ctx, form, data):
        def _save_ip_address(rdf_node, fda):
            if fda['ip_address_selection'] == 'dhcp':
                rdf_node.setS(ns_ui.address, rdf.Type(ns_ui.DhcpAddress))
            elif fda['ip_address_selection'] == 'static':
                static_node = rdf_node.setS(ns_ui.address, rdf.Type(ns_ui.StaticAddress))
                static_node.setS(ns_ui.ipAddress, rdf.IPv4Address, fda['ip_address'])
                static_node.setS(ns_ui.subnetMask, rdf.IPv4Address, fda['subnet_mask']) 
            else:
                raise uidatahelpers.FormDataError('ip_address_selection is neither dhcp nor static') 
            
        def _save_client_traffic(rdf_node, fda):
            client_nat = False
            client_proxy = False
            if fda['client_traffic'] == 'nat':
                client_nat = True    
            elif fda['client_traffic'] == 'proxyarp':
                client_proxy = True    
            rdf_node.setS(ns_ui.clientConnectionNat, rdf.Boolean, client_nat)
            rdf_node.setS(ns_ui.clientConnectionProxyArp, rdf.Boolean, client_proxy)
        
        fda = formalutils.FormDataAccessor(form, [], ctx)
        ui_root = helpers.get_new_ui_config()

        # Interface count
        ic_root = ui_root.setS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
        if fda['ifcount_group.interface_count'] == 'oneif':
            ui_root.removeNodes(ns_ui.privateNetworkConnection)
            pn_root = None
        elif fda['ifcount_group.interface_count'] == 'twoif':
            pn_root = ui_root.setS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
        else:
            raise uidatahelpers.FormDataError('interface_count is neither oneif nor twoif.')
            
        # Internet connection
        ic_fda = fda.descend('ic_group')
        ic_root.setS(ns_ui.interface, rdf.String, ic_fda['if'])
        _save_ip_address(ic_root, ic_fda)
        uidatahelpers.save_optional_field_to_rdf(ic_root, ns_ui.defaultGateway, rdf.IPv4Address, ic_fda, 'default_gateway')
        ic_root.setS(ns_ui.mtu, rdf.Integer, int(ic_fda['mtu']))
        uidatahelpers.save_optional_field_to_rdf(ic_root, ns_ui.vpnUplink, rdf.Float, ic_fda, 'uplink')
        _save_client_traffic(ic_root, ic_fda)
               
        # Private network connection, fill if exists.
        if not(pn_root is None):
            pn_fda = fda.descend('pn_group')
            pn_root.setS(ns_ui.interface, rdf.String, pn_fda['if'])
            _save_ip_address(pn_root, pn_fda)
            uidatahelpers.save_optional_field_to_rdf(pn_root, ns_ui.defaultGateway, rdf.IPv4Address, pn_fda, 'default_gateway')
            _save_client_traffic(pn_root, pn_fda)  
                
        # DNS Servers
        dns_fda = fda.descend('dns_group')
        if dns_fda['dns_selection'] == 'use_dhcp_ic':
            dns_root = ui_root.setS(ns_ui.dnsServers, rdf.Type(ns_ui.InternetConnectionDhcp))
        elif dns_fda['dns_selection'] == 'use_dhcp_pn':
            dns_root = ui_root.setS(ns_ui.dnsServers, rdf.Type(ns_ui.PrivateNetworkConnectionDhcp))
        elif dns_fda['dns_selection'] == 'set_manually':
            dns_root = ui_root.setS(ns_ui.dnsServers, rdf.Type(ns_ui.SetDnsServers))

            # XXX: dns_1 is not really optional here; we should not save dns_2 if we don't have dns_1, it makes no sense
            uidatahelpers.save_optional_field_to_rdf(dns_root, ns_ui.primaryDns, rdf.IPv4Address, dns_fda, 'dns_1')
            uidatahelpers.save_optional_field_to_rdf(dns_root, ns_ui.secondaryDns, rdf.IPv4Address, dns_fda, 'dns_2')

        # Dyndns
        ddns_fda = fda.descend('ddns_group')
        if uidatahelpers.has_form_value(ddns_fda, 'ddns_provider') and \
           (ddns_fda['ddns_provider'] != 'none'):
            ddns_root = ui_root.setS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))
            ddns_root.setS(ns_ui.dynDnsProvider, rdf.String, ddns_fda['ddns_provider'])
            ddns_root.setS(ns_ui.dynDnsUsername, rdf.String, ddns_fda['ddns_username'])
            ddns_root.setS(ns_ui.dynDnsPassword, rdf.String, ddns_fda['ddns_password'])
            ddns_root.setS(ns_ui.dynDnsHostname, rdf.String, ddns_fda['ddns_hostname'])
            
            tmp = ddns_fda['ddns_address_type']
            if tmp == 'interface':
                ddns_root.setS(ns_ui.dynDnsAddress, rdf.String, '')
            elif tmp == 'natted':
                ddns_root.setS(ns_ui.dynDnsAddress, rdf.String, 'natted')
            elif tmp == 'static':
                if (ddns_fda.has_key('ddns_address')) and \
                       (ddns_fda['ddns_address'] is not None) and \
                       (ddns_fda['ddns_address'] != ''):
                    ddns_root.setS(ns_ui.dynDnsAddress, rdf.String, ddns_fda['ddns_address'])
                else:
                    ddns_root.setS(ns_ui.dynDnsAddress, rdf.String, '')            
        else:
            ui_root.removeNodes(ns_ui.dynDnsServer)      
        
    def save_client_connection_data(self, ctx, form, data):
        cc_fda = formalutils.FormDataAccessor(form, ['client_connection'], ctx)
        ui_root = helpers.get_new_ui_config()

        # Server address & psk
        if cc_fda.has_key('server_name') and cc_fda['server_name'] is not None:
            ui_root.setS(ns_ui.vpnServerAddress, rdf.String, cc_fda['server_name'])
        else:
            ui_root.setS(ns_ui.vpnServerAddress, rdf.String, '')
        psk_seq = ui_root.setS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey)))
        if cc_fda.has_key('psk_1') and (cc_fda['psk_1'] != '') and (cc_fda['psk_1'] is not None):
            psk = psk_seq.new()
            psk.setS(ns_ui.preSharedKey, rdf.String, cc_fda['psk_1'])
        if cc_fda.has_key('psk_2') and (cc_fda['psk_2'] != '') and (cc_fda['psk_2'] is not None):
            psk = psk_seq.new()
            psk.setS(ns_ui.preSharedKey, rdf.String, cc_fda['psk_2'])
        # DNS
        if cc_fda['dns'] == 'use_ic_dns':
            ui_root.setS(ns_ui.clientDnsServers, rdf.Type(ns_ui.NetworkConnectionDns))
        elif cc_fda['dns'] == 'manual_dns':
            dns_root = ui_root.setS(ns_ui.clientDnsServers, rdf.Type(ns_ui.SetDnsServers))
            uidatahelpers.save_optional_field_to_rdf(dns_root, ns_ui.primaryDns, rdf.IPv4Address, cc_fda, 'dns_1')
            uidatahelpers.save_optional_field_to_rdf(dns_root, ns_ui.secondaryDns, rdf.IPv4Address, cc_fda, 'dns_2')
        else:
            raise uidatahelpers.FormDataError('Client connection dns is neither network dns nor set dns.')
        # WINS
        # Note: parent node is ui-root, which may already have a value from old config, use empty default
        # value to remove old data in case form value is missing.
        uidatahelpers.save_optional_field_to_rdf(ui_root, ns_ui.clientPrimaryWins, rdf.IPv4Address, cc_fda, 'wins_1', default=None)
        uidatahelpers.save_optional_field_to_rdf(ui_root, ns_ui.clientSecondaryWins, rdf.IPv4Address, cc_fda, 'wins_2', default=None)
        ui_root.setS(ns_ui.clientSubnet, rdf.IPv4Subnet, cc_fda['client_subnet'])
        ui_root.setS(ns_ui.clientAddressRange, rdf.IPv4AddressRange, cc_fda['client_address_range'])

        ui_root.setS(ns_ui.clientCompression, rdf.Boolean, cc_fda['client_compression'])

    @db.transact()
    def submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)
        pd = uidatahelpers.CreateProtocolData()

        # Save collapsed states first, so they feed back to next round
        for [rdf_uri, key] in [ [ ns_ui.collapseInterfaceCount, 'ifcount_group' ],
                                [ ns_ui.collapseInternetConnection, 'ic_group' ],
                                [ ns_ui.collapsePrivateNetwork, 'pn_group' ],
                                [ ns_ui.collapseDns, 'dns_group' ],
                                [ ns_ui.collapseDynamicDns, 'ddns_group' ],
                                [ ns_ui.collapseClientConnection, 'client_connection' ] ]:
            try:
                # XXX: passing of the hidden _collapsedstate_ parameter is not too clean
                uihelpers.update_collapse_setting(rdf_uri, fda['%s._collapsedstate_' % key])
            except:
                _log.exception('error updating collapsed state for %s' % rdf_uri)
            
        # Validation and config generation
        old_vpn_server_address = None
        try:
            # Form global canonicalization
            gc = networkconfigvalidation.ConfigNetworkCanonicalizator(ctx, form, data)
            gc.canonicalize_ip_subnet()
        
            # Form global validation
            gv = networkconfigvalidation.ConfigNetworkValidator(ctx, form, data)
        
            # Check required fields. Some fields may be required because of some other fields value and thus cannot
            # be checked locally.
            gv.check_required_fields()

            gv.ip_and_subnet_match() # Checks public and private.
            gv.public_private_ip_not_same()         # XXX: warning for now only; worth a warning, but still works to some extent
            gv.public_private_eth_not_same()
            gv.check_single_interface_ok()
            gv.check_interface_default_gateways()
            gv.check_public_subnet()                # XXX: warning for now only, overlaps don't cause runner errors
            gv.check_private_subnet()               # XXX: warning for now only, overlaps don't cause runner errors
            gv.check_uplink()
            gv.check_only_one_proxyarp()
            gv.check_dns_dhcp_valid()
            gv.check_client_settings()              # XXX: some checks commented to warnings for now

            # Intermediate early bail out to avoid saving if there are errors
            gv.finalize_validation()

            # XXX: One interface setup could rename the internet connection tab to
            # network connection,  and update all the selections.
              
            # Get old VPN server address for comparison
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.vpnServerAddress):
                old_vpn_server_address = ui_root.getS(ns_ui.vpnServerAddress, rdf.String)
            
            # Deep copy UI config to 'new' UI config
            pd.clone_ui_config()
        
            # Save form data
            self.save_network_data(ctx, form, data)
            self.save_client_connection_data(ctx, form, data)

            # newUiConfig -> newL2tpDeviceConfig
            pd.save_protocol_data()
        except:
            _log.exception('validation failed unexpectedly, adding global error')
            fda.add_global_error('Unknown validation error')

        # Finalize raises exception if there are errors and handles disabled fields as well as copying form data to errors data.
        gv.finalize_validation()

        # Save ok, activate config
        pd.activate_protocol_data()

        # Update initial config saved flag
        pd.update_initial_config_saved()

        # If certificate name has changed, regenerate and re-read cert files
        new_vpn_server_address = None
        ui_root = helpers.get_ui_config()  # reget root after change
        if ui_root.hasS(ns_ui.vpnServerAddress):
            new_vpn_server_address = ui_root.getS(ns_ui.vpnServerAddress, rdf.String)

        # XXX: unnecessary to check for None now, but doesn't hurt
        if (old_vpn_server_address != new_vpn_server_address):
            common_name = None
            if (new_vpn_server_address is not None) and (new_vpn_server_address != ''):
                common_name = new_vpn_server_address
            _log.info('regenerating ssl certificates, common name %s' % common_name)

            @db.untransact()
            def _regenerate():
                helpers.generate_self_signed_certificate(constants.WEBUI_PRIVATE_KEY, constants.WEBUI_CERTIFICATE, common_name=common_name)
            _regenerate()
            
            self.master.reread_ssl_files()
        else:
            _log.debug('certificate name unchanged, not regenerating')

        #
        #  XXX: It would be cleaner if we could first stop the runner, then change the
        #  config, and then restart it.  If we do that with a deferred, then it is possible
        #  that the user changes the config again before we have time to activate it.
        #  Putting the config into some sort of "staging area" might help.  Currently we
        #  simply assume that runner stop (and start) are robust enough.
        #

        # stop, configure, start
        followup = uihelpers.build_uri(ctx, 'status/main.html')
        return uihelpers.reconfigure_and_restart_page(self.master, ctx, followup_uri=followup)
