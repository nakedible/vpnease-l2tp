import sys

from codebay.common import logger
from codebay.common import rdf
from codebay.common import datatypes

from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver.webui.admin import uitexts
from codebay.l2tpserver.webui import uihelpers
from codebay.nevow.formalutils import formalutils

_log = logger.get('l2tpserver.webui.admin.config.networkconfigvalidation')

class ConfigNetworkParent:
    """Parent class for form validator and canocalizator objects.

    Contains common functions.  Cannot be used without subclassing while form data accessor is missing. 
    """
    
    # Dictionary of fields that are conditionally disabled.  The key identifies a
    # field whose disabled status we're considering.  The value for the key is
    # another dictionary, containing a key->value mapping.  If all keys have the
    # value in the key->value mapping (in form data), the field is enabled.
    #
    # Note: Currently there is no check for options, e.g. one of the radiobuttons is disabled.
    dis_fields = {'ic_group.ip_address': {'ic_group.ip_address_selection':'static'},
                  'ic_group.subnet_mask': {'ic_group.ip_address_selection':'static'},
                  'pn_group.ip_address': {'pn_group.ip_address_selection':'static',
                                          'interface_count':'twoif'},      
                  'pn_group.subnet_mask': {'pn_group.ip_address_selection':'static',
                                           'ifcount_group.interface_count':'twoif'},
                  'pn_group.if': {'ifcount_group.interface_count':'twoif'},
                  'pn_group.ip_address_selection': {'ifcount_group.interface_count':'twoif'},
                  'pn_group.default_gateway': {'ifcount_group.interface_count':'twoif'},
                  'pn_group.client_traffic': {'ifcount_group.interface_count':'twoif'},
                  'ddns_group.ddns_address': {'ddns_group.ddns_address_type':'static'},
                  'dns_group.dns_1':{'dns_group.dns_selection':'set_manually'},
                  'dns_group.dns_2':{'dns_group.dns_selection':'set_manually'},
                  'dr_group.gateway':{'dr_group.gateway_selection':'manual_gw'},
                  'sr_group.network_connection': {'sr_group.source_routing_selection':'on'},
                  'sr_group.gateway_selection': {'sr_group.source_routing_selection':'on'},
                  'sr_group.gateway': {'sr_group.source_routing_selection':'on',
                                       'sr_group.gateway_selection':'manual_gw'},
                  'client_connection.cc_group.dns_1': {'client_connection.cc_group.dns':'manual_dns'},
                  'client_connection.cc_group.dns_2': {'client_connection.cc_group.dns':'manual_dns'}
                  } 
    dyn_list_dis_fields = {'ar_group.*.gateway':{'ar_group.*.gateway_selection':'manual_gw'}}
                                                  
    def _is_disabled(self, fda, fda_key, full_key = None):
        """Returns true if the field is disabled."""
        if full_key is None:
            search_key = fda.combine(fda_key)
        else:
            search_key = full_key
        
        # Check if the field is in the dis_fields list.
        if self.dis_fields.has_key(search_key):        
            # Check the conditions.
            # Uses full key names and main fda in order to give a possibility to disable/enable elements from
            # other groups.
            form_fda = formalutils.FormDataAccessor(self.form, [], self.ctx)
            for k in self.dis_fields[search_key].keys():
                # If k is not found in main fda, k has a local error. Only local error in selection is that
                # selection is missing -> not disabled. Continue with other possible selections.
                if not(form_fda.has_key(k)):
                    continue
                if form_fda[k] != self.dis_fields[search_key][k]:
                    return True         
        else:
            # Check if the key matches to dynamic list entries.
            for key in self.dyn_list_dis_fields.keys():
                dyn_list_name, dyn_list_field = key.split('*')
                if (search_key[:len(dyn_list_name)] == dyn_list_name) and (search_key[-len(dyn_list_field):] == dyn_list_field):
                    # search_key matches, take the list index and check the conditions
                    dyn_list_index = search_key[len(dyn_list_name):-len(dyn_list_field)]
                    
                    for cond_key in self.dyn_list_dis_fields[key].keys():
                        cond_field = dyn_list_name + dyn_list_index + cond_key.split('*')[1]
                        form_fda = formalutils.FormDataAccessor(self.form, [], self.ctx)
                        
                        if not(form_fda.has_key(cond_field)):
                            continue
                        
                        if form_fda[cond_field] != self.dyn_list_dis_fields[key][cond_key]:
                            return True
                    
        return False                                              

    def _key_has_errors(self, fda, key):
        """Returns true if field has errors and cannot be used in global validation."""

        if fda.has_key(key) and fda.has_error(key):
            return True
        return False
                                                  
    def _can_validate(self, fda, keys):
        """Returns true if fields have value, have no errors, are not disabled and thus can be used in global validation; otherwise returns false."""
        for key in keys:
            # Check if there are local errors.
            if self._key_has_errors(fda, key):
                return False
        
            # Check if there is a value
            if (not fda.has_key(key)) or (fda[key] is None):
                return False
        
            # Check if the field is disabled.
            if self._is_disabled(fda, key):
                return False
        return True


class ConfigNetworkValidator(ConfigNetworkParent):   
    """ConfigNetworkValidator contains global validation functions for network configuration page.

    Validation functions uses data accessors to validy data, clear and insert warnings and errors.
    Each function has to check local errors before trying to use field
    data. If a local error exists, the field is not in form data.
    """
    
    def __init__(self, ctx, form, data):
        self.ctx = ctx
        self.form = form
        self.data = data
        self.toplevel_fda = formalutils.FormDataAccessor(form, [], ctx)
        self.client_connection_fda = formalutils.FormDataAccessor(form, ['client_connection'], ctx)
        
    def _walk_through_dynamic_list(self, list_fda, callback):
        """Walks through dynamic list and calls the function for each entry exists with a list item fda and list index as parameters."""
        list_index = 0
        while True:
            list_item_fda = list_fda.descend(str(list_index))
            if len(list_item_fda.keys()) == 0:
                break
            callback(list_item_fda, list_index)
            list_index += 1
    
    def _get_public_address(self):
        fda = self.toplevel_fda
        ic_fda = fda.descend('ic_group')
        if ic_fda.has_key('ip_address_selection') and ic_fda['ip_address_selection'] == 'static' and \
               ic_fda.has_key('ip_address') and ic_fda['ip_address'] is not None and \
               ic_fda.has_key('subnet_mask') and ic_fda['subnet_mask'] is not None:
            return datatypes.IPv4AddressSubnet.fromStrings(ic_fda['ip_address'].toString(), ic_fda['subnet_mask'].toString()), ic_fda
        return None, ic_fda

    def _get_private_address(self):
        fda = self.toplevel_fda
        pn_fda = fda.descend('pn_group')
        if pn_fda.has_key('ip_address_selection') and pn_fda['ip_address_selection'] == 'static' and \
               pn_fda.has_key('ip_address') and pn_fda['ip_address'] is not None and \
               pn_fda.has_key('subnet_mask') and pn_fda['subnet_mask'] is not None:
            return datatypes.IPv4AddressSubnet.fromStrings(pn_fda['ip_address'].toString(), pn_fda['subnet_mask'].toString()), pn_fda
        return None, pn_fda

    def _get_ppp_subnet_and_range(self):
        fda = self.client_connection_fda
        
        subnet = None
        if fda.has_key('client_subnet') and fda['client_subnet'] is not None:
            subnet = fda['client_subnet']

        iprange = None
        if fda.has_key('client_address_range') and fda['client_address_range'] is not None:
            iprange = fda['client_address_range']

        return subnet, iprange

    # XXX: subnet validation rewrite
    def _check_overlap_against_sitetosite_subnets(self, subnet):
        ui_root = helpers.get_ui_config()
        
        if ui_root.hasS(ns_ui.siteToSiteConnections):
            for i in ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection))):
                if i.hasS(ns_ui.subnetList):
                    for j in i.getS(ns_ui.subnetList, rdf.Seq(rdf.Type(ns_ui.Subnet))):
                        s2s_sub = j.getS(ns_ui.subnet, rdf.IPv4Subnet)
                        _log.debug('comparing ppp subnet %s against site-to-site subnet %s' % (subnet.toString(), s2s_sub.toString()))
                        if subnet.overlapsWithSubnet(s2s_sub):
                            return False

        return True
    
    def _network_interface_has_default_router_in_rdf(self, node):
        if node is None:
            return False
        if not node.hasS(ns_ui.address):
            return False
        addr = node.getS(ns_ui.address)
        if addr.hasType(ns_ui.DhcpAddress):
            return True  # assume dhcp assigns default router in some manner
        elif addr.hasType(ns_ui.StaticAddress):
            return node.hasS(ns_ui.defaultGateway)
        else:
            _log.warning('unexpected case')
            return False

    def _check_route_uses_default_gateway_in_rdf(self, rdf_node, is_public):
        if rdf_node.hasType(ns_ui.InternetConnectionRoute):
            if not is_public:
                return False
            if not rdf_node.hasS(ns_ui.routeGateway):
                return False
            if rdf_node.getS(ns_ui.routeGateway).hasType(ns_ui.RouteGatewayNetworkDefault):
                return True
        elif rdf_node.hasType(ns_ui.PrivateNetworkConnectionRoute):
            if is_public:
                return False
            if not rdf_node.hasS(ns_ui.routeGateway):
                return False
            if rdf_node.getS(ns_ui.routeGateway).hasType(ns_ui.RouteGatewayNetworkDefault):
                return True
        else:
            return False  # XXX
        
    def _check_routes_use_default_gateway_in_rdf(self, is_public):
        ui_root = helpers.get_ui_config()

        if ui_root.hasS(ns_ui.routes):
            for r in ui_root.getS(ns_ui.routes, rdf.Seq(rdf.Type(ns_ui.Route))):
                if r.hasS(ns_ui.route):
                    if self._check_route_uses_default_gateway_in_rdf(r.getS(ns_ui.route), is_public):
                        return True

        if ui_root.hasS(ns_ui.defaultRoute):
            if self._check_route_uses_default_gateway_in_rdf(ui_root.getS(ns_ui.defaultRoute), is_public):
                return True

        return False
    
    def _check_source_route_uses_default_gateway_in_rdf(self, is_public):
        ui_root = helpers.get_ui_config()

        if not ui_root.hasS(ns_ui.sourceRouting):
            return False

        return self._check_route_uses_default_gateway_in_rdf(ui_root.getS(ns_ui.sourceRouting), is_public)

    def _get_user_fixed_ips_rdf(self):
        res = []
        for user in helpers.get_ui_config().getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User))):
            if user.hasS(ns_ui.fixedIp):
                res.append(user.getS(ns_ui.fixedIp, rdf.IPv4Address))
        return res
        
    # XXX: This is a bit complicated for what it does; see if it can be generalized
    # or simplified
    def check_required_fields(self):
        """Check required field checks all the required fields, which cannot be checked locally.

        Whether or not these fields are required, depends from some other field(s) value(s).
        """
        txt = uitexts.GlobalValidationTexts()
        
        def _check_required_fields(fda, fda_keys):
            """Add 'Required' error to selected fields if they are empty and already don't have an error."""
            for key in fda_keys:
                if not self._is_disabled(fda, key) and not self._key_has_errors(fda, key):
                    if fda[key] is None or fda[key] == '':
                        fda.add_error(key, txt.e_required)
        
        # For static addresses, subnet is required (even with CIDR; canonicalization adds it)
        def _check_ip_and_subnet(fda):
            if (self._can_validate(fda, ['ip_address_selection'])) and fda['ip_address_selection'] == 'static':
                _check_required_fields(fda, ['ip_address', 'subnet_mask'])

        # Public interface checks
        def _check_public_fields():
            fda = self.toplevel_fda.descend('ic_group')
            _check_required_fields(fda, ['if', 'ip_address_selection', 'client_traffic'])
            
        # If two interface setup, check private interface
        def _check_private_fields():
            if (self._can_validate(self.toplevel_fda, ['ifcount_group.interface_count'])) and self.toplevel_fda['ifcount_group.interface_count'] == 'twoif':
                fda = self.toplevel_fda.descend('pn_group')
                _check_required_fields(fda, ['if', 'ip_address_selection', 'client_traffic'])

        # If manual DNS is used, at least one DNS is required
        def _check_manual_dns():
            fda = self.toplevel_fda.descend('dns_group')

            if fda.has_key('dns_selection') and fda['dns_selection'] == 'set_manually':
                if not fda.has_key('dns_1') or fda['dns_1'] is None or fda['dns_1'] == '':
                    fda.add_error('dns_1', txt.e_required)
        
        # If dyndns provider has been selected, all dyndns fields are required; also check allowed characters
        def _check_dyndns_fields():
            fda = self.toplevel_fda.descend('ddns_group')
            fda_keys = ['ddns_provider', 'ddns_username', 'ddns_password', 'ddns_hostname']
            if not(fda[fda_keys[0]] is None) and (fda[fda_keys[0]] != 'none'):
                # actual provider selected => activate validation
                
                _check_required_fields(fda, fda_keys)
                if fda.has_key('ddns_username') and fda['ddns_username'] is not None and not uihelpers.check_dyndns_username_characters(fda['ddns_username']):
                    fda.add_error('ddns_username', 'Invalid characters')
                if fda.has_key('ddns_password') and fda['ddns_password'] is not None and not uihelpers.check_dyndns_password_characters(fda['ddns_password']):
                    fda.add_error('ddns_password', 'Invalid characters')
                if fda.has_key('ddns_hostname') and fda['ddns_hostname'] is not None and not uihelpers.check_dyndns_hostname_characters(fda['ddns_hostname']):
                    fda.add_error('ddns_hostname', 'Invalid characters')

                tmp = ''
                if fda.has_key('ddns_address_type'):
                    tmp = fda['ddns_address_type'] or ''

                if tmp == 'interface':
                    pass
                elif tmp == 'natted':
                    pass
                elif tmp == 'static':
                    if fda.has_key('ddns_address') and fda['ddns_address'] is not None:
                        addr_str = fda['ddns_address']
                        try:
                            ign = datatypes.IPv4Address.fromString(addr_str)
                        except:
                            fda.add_error('ddns_address', 'Invalid address')
                    else:
                        fda.add_error('ddns_address', 'Required')
                else:
                    fda.add_error('ddns_address_type', 'Required')
                
        _check_ip_and_subnet(self.toplevel_fda.descend('ic_group'))
        _check_ip_and_subnet(self.toplevel_fda.descend('pn_group'))     
        _check_public_fields()
        _check_private_fields()
        _check_manual_dns()
        _check_dyndns_fields()

    def check_required_fields_routingfirewall(self):
        txt = uitexts.GlobalValidationTexts()

        # For each individual route, if gateway is selected manually, address is required
        def _check_route_required(route_fda, list_index = None):
            # Check local errors
            fda_keys = ['gateway_selection', 'gateway']

            # Check that selection does not have errors and gateway does not already have an error (=value exists).
            if (self._can_validate(route_fda, [fda_keys[0]])) and (not(self._key_has_errors(route_fda, fda_keys[1]))):
                if (route_fda[fda_keys[0]] == 'manual_gw') and ((not route_fda.has_key(fda_keys[1])) or (route_fda[fda_keys[1]] is None)):
                    route_fda.add_error(fda_keys[1], txt.e_required)

        def _check_default_route_gateway():
            _check_route_required(self.toplevel_fda.descend('dr_group'))
                    
        def _check_routes_gateway():
            self._walk_through_dynamic_list(self.toplevel_fda.descend('ar_group'), _check_route_required)
        
        def _check_source_route_gateway():
            _check_route_required(self.toplevel_fda.descend('sr_group'))

        _check_default_route_gateway()
        _check_routes_gateway()
        _check_source_route_gateway()
        
    def ip_and_subnet_match(self):
        """Given IP address must be inside subnet."""
        def _check_ip_and_subnet_mask(fda):
            txt = uitexts.GlobalValidationTexts()
            fda_keys = ['ip_address', 'subnet_mask']            
            # Check local errors
            if not(self._can_validate(fda, fda_keys)):
                return
            # Check that ip and subnet matches
            try:
                temp_addr = datatypes.IPv4AddressSubnet.fromStrings(fda[fda_keys[0]].toString(), fda[fda_keys[1]].toString())
                if not(temp_addr.isUsable()):
                    raise Exception('address not usable in subnet')
            except:
                fda.add_error(fda_keys[0], txt.e_ip_and_subnet_does_not_match)
                fda.add_error(fda_keys[1], txt.e_ip_and_subnet_does_not_match)
                
        _check_ip_and_subnet_mask(self.toplevel_fda.descend('ic_group'))
        _check_ip_and_subnet_mask(self.toplevel_fda.descend('pn_group'))   
        
    def public_private_ip_not_same(self):
        """Public and private ip addresses must not be the same."""
        txt = uitexts.GlobalValidationTexts()
        fda_keys = ['ip_address']
        ic_fda = self.toplevel_fda.descend('ic_group')
        pn_fda = self.toplevel_fda.descend('pn_group')
        # Check local errors
        if (self._can_validate(ic_fda, fda_keys)) and (self._can_validate(pn_fda, fda_keys)):
            if (ic_fda[fda_keys[0]] == pn_fda[fda_keys[0]]):
                ic_fda.add_warning(fda_keys[0], 'Address is the same as private network connection address')
                pn_fda.add_warning(fda_keys[0], 'Address is the same as Internet connection address')
            
    def public_private_eth_not_same(self):
        """Public and private network adapters must not be the same in two interface setup."""
        txt = uitexts.GlobalValidationTexts()
        fda_keys = ['if']
        ic_fda = self.toplevel_fda.descend('ic_group')
        pn_fda = self.toplevel_fda.descend('pn_group')
        # Check local errors
        if (self._can_validate(ic_fda, fda_keys)) and (self._can_validate(pn_fda, fda_keys)):
            if (ic_fda[fda_keys[0]] == pn_fda[fda_keys[0]]):
                ic_fda.add_error(fda_keys[0], txt.e_public_and_private_if_same)
                pn_fda.add_error(fda_keys[0], txt.e_public_and_private_if_same)
            
    def check_interface_default_gateways(self):
        txt = uitexts.GlobalValidationTexts()

        def _check_gw_in_ip_subnet(fda):
            txt = uitexts.GlobalValidationTexts()
            fda_keys = ['ip_address', 'ip_address_selection', 'subnet_mask', 'default_gateway']
            # Check local errors
            if not(self._can_validate(fda, fda_keys)):
                return
        
            # Skip the check if dhcp is in use, or gw has not been defined.
            if fda['ip_address_selection'] == 'dhcp':
                return
            
            # Create IPv4AddressSubnet object and check if gw address is in subnet.
            try:
                ip_with_subnet = datatypes.IPv4AddressSubnet.fromStrings(fda[fda_keys[0]].toString(), fda[fda_keys[2]].toString())
                if not(ip_with_subnet.inSubnet(fda[fda_keys[3]])):
                    fda.add_warning(fda_keys[3], txt.w_gw_not_in_ip_subnet)
            except:
                fda.add_error(fda_keys[3], txt.e_unknown)
                _log.exception('exception in validating')
                
        def _check_default_gateway_required(fda, is_public, force_required):
            # Not called for private interface if one interface setup (caller checks)

            if fda.has_key('ip_address_selection') and fda['ip_address_selection'] == 'dhcp':
                return  # OK

            if fda.has_key('default_gateway') and fda['default_gateway'] is not None:
                return  # OK

            # Interface has static IP address but no default router.  Error if
            # some other part of configuration relies on it.
            if force_required:
                fda.add_error('default_gateway', txt.e_required)
            else:
                if self._check_routes_use_default_gateway_in_rdf(is_public):
                    fda.add_error('default_gateway', 'Default gateway used by routes')
                elif self._check_source_route_uses_default_gateway_in_rdf(is_public):
                    fda.add_error('default_gateway', 'Default gateway used by forced routing')
                else:
                    pass

        _check_gw_in_ip_subnet(self.toplevel_fda.descend('ic_group'))
        if (self._can_validate(self.toplevel_fda, ['ifcount_group.interface_count'])) and self.toplevel_fda['ifcount_group.interface_count'] == 'twoif':
            _check_gw_in_ip_subnet(self.toplevel_fda.descend('pn_group'))
        _check_default_gateway_required(self.toplevel_fda.descend('ic_group'), True, True)
        if (self._can_validate(self.toplevel_fda, ['ifcount_group.interface_count'])) and self.toplevel_fda['ifcount_group.interface_count'] == 'twoif':
            _check_default_gateway_required(self.toplevel_fda.descend('pn_group'), False, False)

    def check_single_interface_ok(self):
        if_fda = self.toplevel_fda.descend('ifcount_group')
        if (self._can_validate(if_fda, ['interface_count'])) and if_fda['interface_count'] == 'twoif':
            return

        # single interface setup: cannot go to this if private interface is used somewhere
        if self._check_routes_use_default_gateway_in_rdf(False):
            if_fda.add_error('interface_count', 'Private network connection used by routes')
        elif self._check_source_route_uses_default_gateway_in_rdf(False):
            if_fda.add_error('interface_count', 'Private network connection used by forced routing')
        else:
            pass
        
    def check_uplink(self):
        """Uplink is given as Mb's. Warning limits are < 0.256 and > 100."""
        txt = uitexts.GlobalValidationTexts()
        fda_keys = ['uplink']
        fda = self.toplevel_fda.descend('ic_group')
        
        # Check local errors
        if not(self._can_validate(fda, fda_keys)):
            return
        # Check that value exists
        try:
            uplink = float(fda[fda_keys[0]])
        except:
            return
        # Check uplink warning limits.
        if uplink < 0.256:
            fda.add_warning(fda_keys[0], txt.w_uplink_small)
        elif uplink > 100:
            fda.add_warning(fda_keys[0], txt.w_uplink_big)

    def check_only_one_proxyarp(self):
        """Only one proxyarp is allowed."""
        txt = uitexts.GlobalValidationTexts()
        fda_keys = ['client_traffic']
        ic_fda = self.toplevel_fda.descend('ic_group')
        pn_fda = self.toplevel_fda.descend('pn_group')
        
        # Check local errors
        if not(self._can_validate(ic_fda, fda_keys) and self._can_validate(pn_fda, fda_keys)):
            return
        # Check
        if (ic_fda[fda_keys[0]] == 'proxyarp') and (pn_fda[fda_keys[0]] == 'proxyarp'):
            ic_fda.add_error(fda_keys[0], txt.e_two_proxyarps)
            pn_fda.add_error(fda_keys[0], txt.e_two_proxyarps)
            
    # XXX: If dhcp and static dns are used, a warning should be given.
    # XXX: currently warnings are not implemented.
    
    def check_dns_dhcp_valid(self):
        """If dhcp is selected for a dns source, check that dhcp is selected in the target network.

        If private network dhcp is used, check that two interface setup is used.
        """
        txt = uitexts.GlobalValidationTexts()
        ic_pn_fda_keys = ['ip_address_selection']
        dns_fda_keys = ['dns_selection']
        ic_fda = self.toplevel_fda.descend('ic_group')
        pn_fda = self.toplevel_fda.descend('pn_group')
        dns_fda = self.toplevel_fda.descend('dns_group')
        
        # Check local errors.
        if not(self._can_validate(dns_fda, dns_fda_keys)):
            return
        
        if dns_fda[dns_fda_keys[0]] == 'use_dhcp_ic':
            if not(self._can_validate(ic_fda, ic_pn_fda_keys)):
                return  
            if ic_fda[ic_pn_fda_keys[0]] != 'dhcp':
                dns_fda.add_error(dns_fda_keys[0], txt.e_ic_dhcp_not_in_use)
        elif dns_fda[dns_fda_keys[0]] == 'use_dhcp_pn':
            # Check only errors. Disabled means error situation.
            if self._key_has_errors(pn_fda, ic_pn_fda_keys[0]):
                return
            # If disabled, or not selected -> error
            if (self._is_disabled(pn_fda,ic_pn_fda_keys[0])) or (pn_fda[ic_pn_fda_keys[0]] != 'dhcp'):
                dns_fda.add_error(dns_fda_keys[0], txt.e_pn_dhcp_not_in_use)     
            
    def check_route_destination_valid(self):
        """ Checks following:
            - In one interface setup the destination network cannot be private.
            - If network router is used and nw has static ip, gw must be defined. """
        ui_root = helpers.get_ui_config()

        def _check_interface_and_gateway(route_fda, iface_uri):
            if ui_root.hasS(iface_uri):
                if not route_fda.has_key('gateway') or route_fda['gateway'] is None:
                    if self._network_interface_has_default_router_in_rdf(ui_root.getS(iface_uri, rdf.Type(ns_ui.NetworkConnection))):
                        pass
                    else:
                        route_fda.add_error('network_connection', 'Network interface does not have a default gateway')
                else:
                    pass
            else:
                route_fda.add_error('network_connection', 'Network interface not active')
            
        def _check_destination(route_fda, list_index = None):
            if self._can_validate(route_fda, ['network_connection']):
                # Check that interface and gateways exist
                if route_fda['network_connection'] == 'private':
                    _check_interface_and_gateway(route_fda, ns_ui.privateNetworkConnection)
                elif route_fda['network_connection'] == 'internet':
                    _check_interface_and_gateway(route_fda, ns_ui.internetConnection)
                else:
                    _log.warning('unexpected case')  # XXX: should not happen
                
        txt = uitexts.GlobalValidationTexts()
        _check_destination(self.toplevel_fda.descend('dr_group'))
        self._walk_through_dynamic_list(self.toplevel_fda.descend('ar_group'), _check_destination)
        source_route_fda = self.toplevel_fda.descend('sr_group')
        if source_route_fda['source_routing_selection'] == 'on':
            _check_destination(source_route_fda)
        

    def check_ppp_firewall_rules(self):
        txt = uitexts.GlobalValidationTexts()

        # XXX: check_required_fields() checks for other required fields but doesn't seem
        # to make sense to distribute checking of one field to several places
        def _check_ppp_firewall_rule(fda, list_index = None):
            if fda.has_key('protocol') and fda['protocol'] is not None and fda['protocol'] != '':
                # if protocol is not TCP or UDP, port is not allowed
                if fda['protocol'] == 'tcp' or fda['protocol'] == 'udp':
                    pass
                else:
                    if fda.has_key('port') and (fda['port'] is not None) and (fda['port'] != 0):
                        fda.add_error('port', 'Port cannot be used with selected protocol')
            
        self._walk_through_dynamic_list(self.toplevel_fda.descend('fwrule_group'), _check_ppp_firewall_rule)

    def check_client_settings(self):
        fda = self.client_connection_fda
        txt = uitexts.GlobalValidationTexts()

        def _max_psk_length_checker(psk):
            return len(psk) <= constants.MAX_PRE_SHARED_KEY_LENGTH

        # allowed characters in username, password, psk
        # NB: uihelpers checkers accept empty string
        for fieldname, checker, errortext in [ ('server_name', uihelpers.check_dns_name_characters, 'Invalid characters'),
                                               ('psk_1', uihelpers.check_preshared_key_characters, 'Invalid characters'),
                                               ('psk_1', _max_psk_length_checker, 'Pre-shared key too long'),
                                               ('psk_2', uihelpers.check_preshared_key_characters, 'Invalid characters'),
                                               ('psk_2', _max_psk_length_checker, 'Pre-shared key too long') ]:
            if fda.has_key(fieldname) and fda[fieldname] is not None and not checker(fda[fieldname]):
                fda.add_error(fieldname, errortext)

        # at least one dns required if manual servers set
        if fda.has_key('dns') and fda['dns'] == 'manual_dns':
            # require dns_1, not dns_2  (XXX: this may be inconsistent)
            if not fda.has_key('dns_1') or fda['dns_1'] is None or fda['dns_1'] == '':
                fda.add_error('dns_1', txt.e_required)
        else:
            # no validation
            pass
        
        # subnet and range validation
        subnet, iprange = self._get_ppp_subnet_and_range()
        if subnet is not None and iprange is not None:
            rf = iprange.getFirstAddress().toLong()
            rl = iprange.getLastAddress().toLong()
            nf = subnet.getFirstAddress().toLong()
            nl = subnet.getLastAddress().toLong()
            sf = subnet.getFirstUsableAddress().toLong()
            sl = subnet.getLastUsableAddress().toLong() - 1  # last address is for server

            if subnet.getCidr() > 30:
                fda.add_error('client_subnet', 'Subnet is too small')

            if (rf >= sf) and (rl <= sl):
                pass
            else:
                fda.add_error('client_address_range', 'Address range must be contained in subnet and must not contain last address of subnet')

            # ppp subnet vs. public subnet
            pub_addr, _ = self._get_public_address()
            if pub_addr is not None:
                _log.debug('comparing ppp subnet %s against public subnet %s' % (subnet.toString(), pub_addr.toString()))
                if iprange.inRange(pub_addr.getAddress()):
                    fda.add_error('client_address_range', 'Range must not contain Internet connection address')

                if subnet.overlapsWithSubnet(pub_addr.getSubnet()):
                    # XXX: this check was changed to warning after some thought: it doesn't cause actual problems
                    fda.add_warning('client_subnet', 'Subnet overlaps with Internet connection subnet')

            # ppp subnet vs. private subnet
            priv_addr, _ = self._get_private_address()
            if priv_addr is not None:
                _log.debug('comparing ppp subnet %s against private subnet %s' % (subnet.toString(), priv_addr.toString()))
                if iprange.inRange(priv_addr.getAddress()):
                    fda.add_error('client_address_range', 'Range must not contain private network connection address')
                    
                if subnet.overlapsWithSubnet(priv_addr.getSubnet()):
                    # XXX: this check was changed to warning after some thought: it doesn't cause actual problems
                    fda.add_warning('client_subnet', 'Subnet overlaps with private connection subnet')

            # ppp subnet vs. site-to-site subnets
            if not self._check_overlap_against_sitetosite_subnets(subnet):
                # XXX: this check was removed after some thought; it doesn't cause actual problems
                fda.add_warning('client_subnet', 'Subnet overlaps with remote site-to-site connection subnets')

            # ppp subnet and range vs. configured fixed IP users
            for fixed_ip in self._get_user_fixed_ips_rdf():
                if iprange.inRange(fixed_ip):
                    fda.add_error('client_address_range', 'Range must not contain user fixed IP addresses')
                    break

                fixed_ip_long = fixed_ip.toLong()
                if fixed_ip_long in [nf, nl, nl-1]:  # network, broadcast, last usable
                    fda.add_error('client_address_range', 'Some user fixed IP addresses overlap with reserved subnet addresses')

            # XXX: fixed IPs should also be 
            # XXX: if we add further validation checks here later, check overlap with routes
            
    def check_public_subnet(self):
        # Public subnet should not overlap with private subnet, ppp subnet, or site-to-site subnets

        pub_addr, ic_fda = self._get_public_address()
        if pub_addr is None:
            return

        priv_addr, _ = self._get_private_address()
        if priv_addr is not None:
            if pub_addr.getSubnet().overlapsWithSubnet(priv_addr.getSubnet()):
                # XXX: add different warnings depending on whether subnet is the same or subset;
                # the effect are different (same subnet => public is used, otherwise smaller
                # takes priority).
                ic_fda.add_warning('subnet_mask', 'Subnet overlaps with private connection subnet')

        subnet, _ = self._get_ppp_subnet_and_range()
        if subnet is not None:
            if subnet.overlapsWithSubnet(pub_addr.getSubnet()):
                # XXX: refine warning
                ic_fda.add_warning('subnet_mask', 'Subnet overlaps with client connection subnet')
                
        if not self._check_overlap_against_sitetosite_subnets(pub_addr.getSubnet()):
            ic_fda.add_warning('subnet_mask', 'Subnet overlaps with site-to-site connection subnets')

        # XXX: if we add further validation checks here later, check overlap with routes

    def check_private_subnet(self):
        # Private subnet should not overlap with public subnet, ppp subnet, or site-to-site subnets

        priv_addr, pn_fda = self._get_private_address()
        if priv_addr is None:
            return

        pub_addr, _ = self._get_public_address()
        if pub_addr is not None:
            if priv_addr.getSubnet().overlapsWithSubnet(pub_addr.getSubnet()):
                # XXX: refine warning
                pn_fda.add_warning('subnet_mask', 'Subnet overlaps with Internet connection subnet')

        subnet, _ = self._get_ppp_subnet_and_range()
        if subnet is not None:
            if subnet.overlapsWithSubnet(priv_addr.getSubnet()):
                # XXX: refine warning
                pn_fda.add_warning('subnet_mask', 'Subnet overlaps with client connection subnet')

        if not self._check_overlap_against_sitetosite_subnets(priv_addr.getSubnet()):
            # XXX: refine warning
            pn_fda.add_warning('subnet_mask', 'Subnet overlaps with site-to-site connection subnets')

        # XXX: if we add further validation checks here later, check overlap with routes

    #
    # Disabled field handling. Clear all the errors after validation. Data is cleared after successful submit.
    # -> Form has disabled field data until form has been successfully submitted. Clearing errors and data does
    # no validation.
    #
    
    def _walk_through_disabled_fields(self, func):
        """Iterate trough disabled field keys and call function given as a parameter if a field is disabled."""
        # Dynamic list callback function.
        def _check_dynamic_field(list_item_fda, list_index):
            search_key = dyn_list + str(list_index) + dyn_list_field
            if self._is_disabled(None, None, search_key):
                func(search_key)
            
        
        # Non-dynamic fields
        for key in self.dis_fields.keys():
            if self._is_disabled(None, None, key):
                func(key)
        
        # Dynamic list fields
        for key in self.dyn_list_dis_fields:
            dyn_list, dyn_list_field = key.split('*')
            dyn_list_fda = formalutils.FormDataAccessor(self.form, [dyn_list[:-1]], self.ctx) # Take '.' away from dyn_list end.
            self._walk_through_dynamic_list(dyn_list_fda, _check_dynamic_field)
            
        
    def _clear_errors_from_disabled_fields(self):
        """Clears all the field errors from disabled fields.

        Validation must know which fields are disabled, while all the fields are enabled in the form post.
        """
        form_fda = formalutils.FormDataAccessor(self.form, [], self.ctx)
        self._walk_through_disabled_fields(form_fda.clear_local_errors_and_warnings)
        
    def _clear_data_from_disabled_fields(self):
        """Clears all the data from disabled fields."""
        form_fda = formalutils.FormDataAccessor(self.form, [], self.ctx)
        self._walk_through_disabled_fields(form_fda.clear_key_value)
                
    #
    # Finalizing validation.
    #
    def finalize_validation(self):
        """After global validation is completed, finalize.

        Clears errors from disabled fields, saves form data to errors data, raises 
        an exception if there are errors, removes data from disabled fields if there are no errors.
        """
        self._clear_errors_from_disabled_fields()
        self.toplevel_fda.finalize_validation()
        self._clear_data_from_disabled_fields()
    

class ConfigNetworkCanonicalizator(ConfigNetworkParent):
    """ConfigNetworkCanonicalizator handles config network page global canonicalization."""
    
    def __init__(self, ctx, form, data):
        self.ctx = ctx
        self.form = form
        self.data = data
        self.toplevel_fda = formalutils.FormDataAccessor(form, [], ctx)
    
    def canonicalize_ip_subnet(self):
        """If IP is in CIDR format, strip the subnet and insert it to the subnet -field."""
        def _canonicalize_ip_subnet(fda):
            fda_keys = ['ip_address', 'subnet_mask']
            # If ip -field does have errors, do not canonizalize.
            if not(self._can_validate(fda, [fda_keys[0]])):
                return
            # Check if ip address has subnet.
            try:
                tempIP = fda[fda_keys[0]]
                if isinstance(tempIP, datatypes.IPv4AddressSubnet): 
                    # IP has subnet. Insert new values to the fields, and clear subnet local errors.
                    fda[fda_keys[0]] = tempIP.getAddress()
                    fda[fda_keys[1]] = tempIP.getMask()
                    fda.clear_local_errors_and_warnings(fda_keys[1])
            except:
                _log.exception('canonicalize_ip_subnet() failed')
                return
                
        _canonicalize_ip_subnet(self.toplevel_fda.descend('ic_group'))
        _canonicalize_ip_subnet(self.toplevel_fda.descend('pn_group'))
