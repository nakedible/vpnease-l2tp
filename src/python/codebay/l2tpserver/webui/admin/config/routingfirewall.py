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

_log = logger.get('l2tpserver.webui.admin.config.routingfirewall')


class RoutingFirewallPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/config/routingfirewall.xhtml'
    pagetitle = 'Configuration / Routing & Firewall'

    nc_uitexts = uitexts.NetworkConfigTexts()
    route_uitexts = uitexts.RoutesTexts()
    cc_uitexts = uitexts.ClientConnectionTexts()
    fw_uitexts = uitexts.FirewallTexts()
        
    def fill_routing_group(self, form, ctx, toplevel_fda):
        def _fill_route_to_form(rdf_node, fda, subnet_exist):
            if rdf_node.hasType(ns_ui.InternetConnectionRoute):
                fda['network_connection'] = 'internet'
            elif rdf_node.hasType(ns_ui.PrivateNetworkConnectionRoute):
                fda['network_connection'] = 'private'
            else:
                raise uidatahelpers.RdfDataError('Route\'s destination network is neither internet nor private network connection')

            # Default route does not have subnet
            # XXX: why not 0.0.0.0/0 instead?
            if subnet_exist:
                fda['subnet'] = rdf_node.getS(ns_ui.subnet, rdf.IPv4Subnet)
                
            gw_node = rdf_node.getS(ns_ui.routeGateway)
            if gw_node.hasType(ns_ui.RouteGatewayNetworkDefault):
                fda['gateway_selection'] = 'nw_default_gw'
            elif gw_node.hasType(ns_ui.RouteGatewayManual):
                fda['gateway_selection'] = 'manual_gw'
                fda['gateway'] = gw_node.getS(ns_ui.ipAddress, rdf.IPv4Address)
            else:
                raise uidatahelpers.RdfDataError('Route\'s gateway is neither network default nor set gateway.')
            
        def _fill_additional_route_to_form(rdf_node, fda):
            _fill_route_to_form(rdf_node.getS(ns_ui.route), fda, True)    
            
        def _fill_ppp_firewall_rule_to_form(rdf_node, fda):
            if rdf_node.hasS(ns_ui.ipAddress):
                # XXX: this is never encountered in practice?
                fda['ip_subnet'] = rdf_node.getS(ns_ui.ipAddress, rdf.IPv4Address)
            elif rdf_node.hasS(ns_ui.subnet):
                fda['ip_subnet'] = rdf_node.getS(ns_ui.subnet, rdf.IPv4Subnet)
            else:
                raise uidatahelpers.RdfDataError('Prohibited service ip/subnet is neither ipaddress nor subnet.')

            if rdf_node.hasS(ns_ui.protocol):
                fda['protocol'] = rdf_node.getS(ns_ui.protocol, rdf.String)
            else:
                fda['protocol'] = 'any'

            uidatahelpers.fill_optional_field_to_form(rdf_node, ns_ui.port, rdf.Integer, fda, 'port')

            fda['action'] = rdf_node.getS(ns_ui.action, rdf.String)

        ui_root = helpers.get_ui_config()

        # Default route
        _fill_route_to_form(ui_root.getS(ns_ui.defaultRoute), toplevel_fda.descend('dr_group'), False)

        # Additional routes
        add_route_fda = toplevel_fda.descend('ar_group')
        uidatahelpers.fill_dynamic_list_to_form(ui_root, ns_ui.routes, ns_ui.Route, add_route_fda, _fill_additional_route_to_form)

        # Source routing (forced routing)
        source_fda = toplevel_fda.descend('sr_group')
        if ui_root.hasS(ns_ui.sourceRouting):      
            source_fda['source_routing_selection'] = 'on'
            _fill_route_to_form(ui_root.getS(ns_ui.sourceRouting), source_fda, False)
        else:
            source_fda['source_routing_selection'] = 'off'

        # PPP firewall rules
        fwrule_fda = toplevel_fda.descend('fwrule_group')
        uidatahelpers.fill_dynamic_list_to_form(ui_root, ns_ui.pppFirewallRules, ns_ui.PppFirewallRule, fwrule_fda, _fill_ppp_firewall_rule_to_form)

    def fill_firewall_group(self, form, ctx, fw_fda):
        ui_root = helpers.get_ui_config()
        fw_fda['firewall_in_use'] = ui_root.getS(ns_ui.firewallInUse, rdf.Boolean)

    def fill_port_forwarding_group(self, form, ctx, pf_fda):
        def _fill_port_forward_to_form(rdf_node, fda):
            fda['new_fw_protocol'] = rdf_node.getS(ns_ui.protocol, rdf.String)
            fda['new_fw_port_in'] = rdf_node.getS(ns_ui.incomingPort, rdf.Integer)
            fda['new_fw_ip_out'] = rdf_node.getS(ns_ui.ipAddress, rdf.IPv4Address)
            fda['new_fw_port_out'] = rdf_node.getS(ns_ui.destinationPort, rdf.Integer)
        
        ui_root = helpers.get_ui_config()
        uidatahelpers.fill_dynamic_list_to_form(ui_root, ns_ui.portForwards, ns_ui.PortForward, pf_fda, _fill_port_forward_to_form)
        
    def create_default_route_group(self, form, ctx):
        txt = self.route_uitexts
        g = formalutils.CollapsibleGroup('dr_group', label=txt.default_route_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseDefaultRoute))
        g.add(formalutils.Field('network_connection', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=txt.routing_nw_options),
                                label=txt.routing_nw_label))
        g.add(formalutils.Field('gateway_selection', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.routing_gw_select_options),
                                label=txt.routing_gw_select_label))
        g.add(formalutils.Field('gateway', dt.FormIPv4Address(required=False), label=txt.routing_gw_label))
        return g
        
    def create_additional_routes_group(self, form, ctx):
        txt = self.route_uitexts

        def _create_route_list_entry(index):
            g = formalutils.CollapsibleGroup(str(index), label='')
            g.setCollapsed(False)
            g.add(formalutils.Field('subnet', dt.FormIPv4Subnet(required=True), label=txt.routing_subnet))
            g.add(formalutils.Field('network_connection', formal.String(required=True),
                                    formal.widgetFactory(formal.SelectChoice, options=txt.routing_nw_options),
                                    label=txt.routing_nw_label))
            g.add(formalutils.Field('gateway_selection', formal.String(required=True),
                                    formal.widgetFactory(formal.RadioChoice, options=txt.routing_gw_select_options),
                                    label=txt.routing_gw_select_label))
            g.add(formalutils.Field('gateway', dt.FormIPv4Address(required=False), label=txt.routing_gw_label))
            return g
            
        # Dynamic route list.
        routes_list = formalutils.DynamicList('ar_group', label=txt.additional_routes_caption, childCreationCallback=_create_route_list_entry)
        routes_list.setCollapsible(True)
        routes_list.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseAdditionalRoutes))

        try:
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.routes):
                route_index = 0
                for route in ui_root.getS(ns_ui.routes, rdf.Seq(rdf.Type(ns_ui.Route))):
                    routes_list.add(_create_route_list_entry(str(route_index)))
                    route_index += 1
        except:
            _log.exception('failed to create dynamic routes list')

        return routes_list

    def create_source_routing_group(self, form, ctx):
        txt = self.route_uitexts
        g = formalutils.CollapsibleGroup('sr_group', label=txt.source_routing_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseSourceRouting))
        g.add(formalutils.Field('source_routing_selection', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.source_routing_select_options),
                                label=txt.source_routing_select_label))
        g.add(formalutils.Field('network_connection', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=txt.routing_nw_options),
                                label=txt.routing_nw_label))
        g.add(formalutils.Field('gateway_selection', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=txt.routing_gw_select_options),
                                label=txt.routing_gw_select_label))
        g.add(formalutils.Field('gateway', dt.FormIPv4Address(required=False), label=txt.routing_gw_label))
        return g
         
    def create_ppp_firewall_group(self, form, ctx):
        txt = self.route_uitexts
        def _create_fwrule_list_entry(index):
            g = formalutils.CollapsibleGroup(str(index), label='')
            g.setCollapsed(collapsed=False)
            g.add(formalutils.Field('ip_subnet', dt.FormIPv4Subnet(required=True), label='IP address or subnet'))
            g.add(formalutils.Field('protocol', formal.String(required=True),
                                    formal.widgetFactory(formal.SelectChoice, options=txt.fw_protocol_select_options),
                                    label='Protocol'))
            g.add(formalutils.Field('port', formal.Integer(required=False, validators=[formal.RangeValidator(min=0, max=65535)]), label='Port'))
            g.add(formalutils.Field('action', formal.String(required=True),
                                    formal.widgetFactory(formal.SelectChoice, options=txt.fw_protocol_action_options),
                                    label='Action'))
            return g
            
        fwrule_list = formalutils.DynamicList('fwrule_group', 'VPN Traffic Firewall Rules', childCreationCallback=_create_fwrule_list_entry)
        fwrule_list.setCollapsible(True)
        fwrule_list.setCollapsed(uihelpers.collapse_setting(ns_ui.collapsePppFirewallRules))

        try:
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.pppFirewallRules):
                fwrule_index = 0
                for fwrule in ui_root.getS(ns_ui.pppFirewallRules, rdf.Seq(rdf.Type(ns_ui.PppFirewallRule))):
                    fwrule_list.add(_create_fwrule_list_entry(fwrule_index))
                    fwrule_index += 1
        except:
            _log.exception('failed to create dynamic ppp firewall rule list')

        return fwrule_list

    def create_firewall_group(self, form, ctx):
        txt = self.fw_uitexts

        g = formalutils.CollapsibleGroup('firewall', label=txt.firewall_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseFirewall))
        g.add(formalutils.Field('firewall_in_use', formal.Boolean(required=True), label=txt.enable_routing_label))
        return g

    def create_port_forwarding_group(self, form, ctx):
        txt = self.fw_uitexts
        
        def _create_port_forward_list_entry(index):
            g = formalutils.CollapsibleGroup(str(index), label='')
            g.setCollapsed(collapsed=False)
            g.add(formalutils.Field('new_fw_protocol', formal.String(required=True),
                                    formal.widgetFactory(formal.SelectChoice, options=txt.new_fw_protocol_options),
                                    label=txt.new_fw_protocol_label))
            g.add(formalutils.Field('new_fw_port_in', formal.Integer(required=True, validators=[formal.RangeValidator(min=0, max=65535)]), label=txt.new_fw_port_in_label))
            g.add(formalutils.Field('new_fw_ip_out', dt.FormIPv4Address(required=True), label=txt.new_fw_ip_out_label))
            g.add(formalutils.Field('new_fw_port_out', formal.Integer(required=True, validators=[formal.RangeValidator(min=0, max=65535)]), label=txt.new_fw_port_out_label))
            return g
        
        pf_list = formalutils.DynamicList('port_forwards', label=txt.port_forwards_group_caption, childCreationCallback=_create_port_forward_list_entry)
        pf_list.setCollapsible(True)
        pf_list.setCollapsed(uihelpers.collapse_setting(ns_ui.collapsePortForwardingRules))

        try:
            ui_root = helpers.get_ui_config()
            if ui_root.hasS(ns_ui.portForwards):
                pf_index = 0
                for pf in ui_root.getS(ns_ui.portForwards, rdf.Seq(rdf.Type(ns_ui.PortForward))):
                    pf_list.add(_create_port_forward_list_entry(pf_index))
                    pf_index += 1
        except:
            _log.exception('failed to create dynamic port forwardings list')

        return pf_list

    @db.transact()
    def form_config(self, ctx):        
        form = formal.Form()
        
        dr = self.create_default_route_group(form, ctx)
        ar = self.create_additional_routes_group(form, ctx)
        sr = self.create_source_routing_group(form, ctx)
        fw = self.create_firewall_group(form, ctx)
        fwrule = self.create_ppp_firewall_group(form, ctx)
        pf = self.create_port_forwarding_group(form, ctx)

        form.add(dr)
        form.add(ar)
        form.add(sr)
        form.add(fwrule)
        form.add(fw)
        form.add(pf)

        try:
            toplevel_fda = formalutils.FormDataAccessor(form, [], ctx)
            self.fill_routing_group(form, ctx, toplevel_fda)
        except:
            _log.exception('failed to fill in form data, ignoring')

        try:
            fw_fda = formalutils.FormDataAccessor(form, ['firewall'], ctx)
            self.fill_firewall_group(form, ctx, fw_fda)
        except:
            _log.exception('failed to fill in form data, ignoring')

        try:
            pf_fda = formalutils.FormDataAccessor(form, ['port_forwards'], ctx)
            self.fill_port_forwarding_group(form, ctx, pf_fda)
        except:
            _log.exception('failed to fill in form data, ignoring')

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False)        
        return form

    def save_routes_data(self, ctx, form, data):
        def _save_additional_route_to_rdf(rdf_node, fda):
            uidatahelpers.create_rdf_route(rdf_node, fda['subnet'], fda['network_connection'], fda['gateway'], ns_ui.route)    
        
        def _save_ppp_firewall_rule_to_rdf(rdf_node, fda):
            if isinstance(fda['ip_subnet'], datatypes.IPv4Address):
                rdf_node.setS(ns_ui.ipAddress, rdf.IPv4Address, fda['ip_subnet'])
            elif isinstance(fda['ip_subnet'], datatypes.IPv4Subnet):
                rdf_node.setS(ns_ui.subnet, rdf.IPv4Subnet, fda['ip_subnet'])
            else:
                raise uidatahelpers.FormDataError('Firewall rule IP/subnet is neither IPv4Address nor IPv4Subnet')
                    
            if fda['protocol'] == 'any':
                pass
            else:
                rdf_node.setS(ns_ui.protocol, rdf.String, fda['protocol'])

            uidatahelpers.save_optional_field_to_rdf(rdf_node, ns_ui.port, rdf.Integer, fda, 'port')    

            rdf_node.setS(ns_ui.action, rdf.String, fda['action'])
            
        toplevel_fda = formalutils.FormDataAccessor(form, [], ctx)
        ui_root = helpers.get_new_ui_config()

        # Default route
        droute_fda = toplevel_fda.descend('dr_group') 
        uidatahelpers.create_rdf_route(ui_root, None, droute_fda['network_connection'], droute_fda['gateway'], ns_ui.defaultRoute)

        # Additional routes
        add_route_fda = toplevel_fda.descend('ar_group')
        uidatahelpers.save_dynamic_list_to_rdf(ui_root, ns_ui.routes, ns_ui.Route, add_route_fda, _save_additional_route_to_rdf)

        # Source routing (forced routing)
        source_fda = toplevel_fda.descend('sr_group')
        if source_fda['source_routing_selection'] == 'off':
            ui_root.removeNodes(ns_ui.sourceRouting)
        elif source_fda['source_routing_selection'] == 'on':
            uidatahelpers.create_rdf_route(ui_root, None, source_fda['network_connection'], source_fda['gateway'], ns_ui.sourceRouting)
        else:
            raise uidatahelpers.FormDataError('Forced routing is neither on nor off.')

        # PPP firewall rules
        fwrule_fda = toplevel_fda.descend('fwrule_group')
        uidatahelpers.save_dynamic_list_to_rdf(ui_root, ns_ui.pppFirewallRules, ns_ui.PppFirewallRule, fwrule_fda, _save_ppp_firewall_rule_to_rdf)

    def save_firewall_data(self, ctx, form, data):
        def _save_port_forward_to_rdf(rdf_node, fda):
            rdf_node.setS(ns_ui.protocol, rdf.String, fda['new_fw_protocol'])
            uidatahelpers.save_optional_field_to_rdf(rdf_node, ns_ui.incomingPort, rdf.Integer, fda, 'new_fw_port_in')
            rdf_node.setS(ns_ui.ipAddress, rdf.IPv4Address, fda['new_fw_ip_out'])
            uidatahelpers.save_optional_field_to_rdf(rdf_node, ns_ui.destinationPort, rdf.Integer, fda, 'new_fw_port_out')

        ui_root = helpers.get_new_ui_config()
        fw_fda = formalutils.FormDataAccessor(form, ['firewall'], ctx)
        ui_root.setS(ns_ui.firewallInUse, rdf.Boolean, fw_fda['firewall_in_use'])

        # XXX: separate function
        pf_fda = formalutils.FormDataAccessor(form, ['port_forwards'], ctx)
        uidatahelpers.save_dynamic_list_to_rdf(ui_root, ns_ui.portForwards, ns_ui.PortForward, pf_fda, _save_port_forward_to_rdf)

    @db.transact()
    def submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)
        pd = uidatahelpers.CreateProtocolData()

        # Save collapsed states first, so they feed back to next round
        for [rdf_uri, key] in [ [ ns_ui.collapseDefaultRoute, 'dr_group' ],
                                [ ns_ui.collapseAdditionalRoutes, 'ar_group' ],
                                [ ns_ui.collapseSourceRouting, 'sr_group' ],
                                [ ns_ui.collapsePppFirewallRules, 'fwrule_group' ],
                                [ ns_ui.collapsePortForwardingRules, 'port_forwards' ],
                                [ ns_ui.collapseFirewall, 'firewall' ] ]:
            try:
                # XXX: passing of the hidden _collapsedstate_ parameter is not too clean
                uihelpers.update_collapse_setting(rdf_uri, fda['%s._collapsedstate_' % key])
            except:
                _log.exception('error updating collapsed state for %s' % rdf_uri)
            
        # Validation and config generation
        try:
            # Form global canonicalization
            gc = networkconfigvalidation.ConfigNetworkCanonicalizator(ctx, form, data)
        
            # Form global validation
            gv = networkconfigvalidation.ConfigNetworkValidator(ctx, form, data)
        
            # Check required fields. Some fields may be required because of some other fields value and thus cannot
            # be checked locally.
            gv.check_required_fields_routingfirewall()
        
            # Global checks for internet and private network connection.
            gv.check_route_destination_valid()  # just checks that some destination is defined, not that e.g. private network exists
            gv.check_ppp_firewall_rules()

            # Intermediate early bail out to avoid saving if there are errors
            gv.finalize_validation()

            # XXX: we might want to add warnings here later if route subnets overlap with each other
            # or with site-to-site subnets
        
            # Deep copy UI config to 'new' UI config
            pd.clone_ui_config()

            # Save form data.
            self.save_routes_data(ctx, form, data)
            self.save_firewall_data(ctx, form, data)

            pd.save_protocol_data()
        except:
            _log.exception('validation failed unexpectedly, adding global error')
            fda.add_global_error('Unknown validation error')

        # Finalize raises exception if there are errors and handles disabled fields as well as copying form data to erros data.
        gv.finalize_validation()

        # Save ok, activate config
        pd.activate_protocol_data()

        # Update initial config saved flag
        pd.update_initial_config_saved()

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
