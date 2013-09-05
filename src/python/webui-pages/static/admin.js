/*
 *  Administrator UI specific Javascript functionality.
 *
 *  In particular, contains administrator UI specific dynamiclist functions
 *  required by formalutils.js.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 */

/* --------------------------------------------------------------------------
 *  Product specific formal functions
 */


function formal_dynamiclist_create_new_element_for_specific_list(cssid) {
  // Add new list entry with unique ID in order to avoid checkbox problem. 
  var index = get_running_index();
  var t = formal_cssid_to_key(cssid);
  var form = t[0];
  var key = t[1] + "." + index;

  function __get_collapsible_group_contents(node) {
    for (var i = 0; node.childNodes[i]; i++) {
      var c = node.childNodes[i];

      if (c.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
	continue;
      } else if (c.className == "collapsible-group-contents") {
	return c.childNodes[0];  // first and only inner div
      }
    }

    return null;
  }

  function __create_fieldset(group_key, caption, listbuttons, collapsible, summarystring) {
    var params = new Object();
    params.form = form;
    params.key = group_key;
    if (collapsible != undefined && collapsible) {
      params.aclass = "group collapsible-group";
    } else {
      params.aclass = "group";
    }
    if (caption != undefined)
      params.legend = caption
    else
      params.legend = "";
    params.description = "";
    if (listbuttons != undefined)
      params.list_buttons = listbuttons;
    else
      params.list_buttons = false;  
    if (collapsible != undefined && collapsible) {
      params.collapsible = true;
    } else {
      params.collapsible = false;
    }
    if (summarystring != undefined) {
      params.collapsedsummary = summarystring;
    } else {
      params.collapsedsummary = "";
    }
    return formal_group_create(params);
  }
  
  function __create_field(field_key, label, field_type, input_type, value, required, select_options, radiobuttons) {
    var params = new Object();
    params.form = form;  
    params.key = key + "." + field_key;
    params.label = label;
    params.field_type = field_type;
    params.input_type = input_type;
    params.value = value;
    params.is_required = required;    
    if (select_options != undefined) {
      params.select_options = select_options;
    }
    if (radiobuttons != undefined) {
      params.radiobuttons = radiobuttons;
    }
    // Checkbox uses value for setting checked param.
    if (input_type == "checkbox" && value == "true") {
      params.checked = true;
    }
    
    return formal_field_create(params);
  }

  function __create_select_option(label, value, selected) {
    var option = new Object();
    option.label = label; 
    option.value = value;
    option.selected = selected;
    return option;
  }  
  
  function __create_radiobutton(label, value, checked, id) {
    var rbutton = new Object();
    rbutton.label = label;
    rbutton.value = value;
    rbutton.checked = checked;
    rbutton.id = id;
    return rbutton;
  }

  function __create_route_list_entry(){
    var fieldset = __create_fieldset(key, "", true, true, "");
    var items = __get_collapsible_group_contents(fieldset);

    items.appendChild(__create_field("subnet", "Subnet", "formipv4addresssubnet", "textinput", "", true));
    
    var select_options = [];
    select_options.push(__create_select_option("", "", true));
    select_options.push(__create_select_option("Internet connection", "internet", false));
    select_options.push(__create_select_option("Private network connection", "private", false));
    items.appendChild(__create_field("network_connection", "Destination network", "string", "selectchoice", "", true, select_options));
    
    var radiobuttons = [];
    radiobuttons.push(__create_radiobutton("Use network connection default gateway", "nw_default_gw", false, "0"));
    radiobuttons.push(__create_radiobutton("Set gateway", "manual_gw", false, "1"));
    items.appendChild(__create_field("gateway_selection", "Gateway selection", "string", "radiochoice", "", true, null, radiobuttons));
    items.appendChild(__create_field("gateway", "Gateway IP address", "formipv4address", "textinput", "", true));     
    
    return fieldset;    
  }
  
  function __create_ppp_firewall_rule_list_entry() {
    var fieldset = __create_fieldset(key, "", true, true, "");
    var items = __get_collapsible_group_contents(fieldset);

    items.appendChild(__create_field("ip_subnet", "IP address or subnet", "formipv4addresssubnet", "textinput", "", true));
    
    var select_options = [];
    select_options.push(__create_select_option("", "", true));
    select_options.push(__create_select_option("Any", "any", false));
    select_options.push(__create_select_option("TCP", "tcp", false));
    select_options.push(__create_select_option("UDP", "udp", false));
    select_options.push(__create_select_option("ICMP", "icmp", false));
    items.appendChild(__create_field("protocol", "Protocol", "string", "selectchoice", "", true, select_options));
    items.appendChild(__create_field("port", "Port", "integer", "textinput", "", false));
    var action_options = [];
    action_options.push(__create_select_option("", "", true));
    action_options.push(__create_select_option("Allow", "allow", false));
    action_options.push(__create_select_option("Deny", "deny", false));
    items.appendChild(__create_field("action", "Action", "string", "selectchoice", "", true, action_options));
    
    return fieldset;
  }
  
  function __create_port_forwards_list_entry() {
    var fieldset = __create_fieldset(key, "", true, true, "");
    var items = __get_collapsible_group_contents(fieldset);

    var select_options = [];
    select_options.push(__create_select_option("", "", true));
    select_options.push(__create_select_option("TCP", "tcp", false));
    select_options.push(__create_select_option("UDP", "udp", false));
    items.appendChild(__create_field("new_fw_protocol", "Protocol", "string", "selectchoice", "", true, select_options));
    items.appendChild(__create_field("new_fw_port_in", "Incoming port", "integer", "textinput", "", false));
    items.appendChild(__create_field("new_fw_ip_out", "Destination IP address", "formipv4address", "textinput", "", true));
    items.appendChild(__create_field("new_fw_port_out", "Destination port", "integer", "textinput", "", false));
      
    return fieldset;
  }
  
  function __create_s2s_connections_list_entry() {
    var fieldset = __create_fieldset(key, "", true, true, "");
    var items = __get_collapsible_group_contents(fieldset);

    s2s_mode_client = new Object();
    s2s_mode_client.value = "client";
    s2s_mode_client.id = "0";
    s2s_mode_client.label = "Initiate connection to a remote server";
    s2s_mode_server = new Object();
    s2s_mode_server.value = "server";
    s2s_mode_server.id = "1";
    s2s_mode_server.label = "Respond to a connection from a remote server";
    s2s_mode_radio = [ s2s_mode_server, s2s_mode_client ];

    items.appendChild(__create_field("s2s_username", "Username", "string", "textinput", "", true));
    items.appendChild(__create_field("s2s_password", "Password", "string", "semihidden", "", true));
    items.appendChild(__create_field("s2s_subnets", "Remote subnets", "formipv4addresssubnetlist", "textinput", "", true));
    items.appendChild(__create_field("s2s_mode", "Connection mode", "string", "radiochoice", "", true, null, s2s_mode_radio ));
    items.appendChild(__create_field("s2s_server", "Remote server address", "string", "textinput", "", false));
    items.appendChild(__create_field("s2s_psk", "Remote server pre-shared key", "string", "semihidden", "", false));
    
    return fieldset;
  }

  function __create_userlist_entry() {
    var fieldset = __create_fieldset(key, "", true, true, "");
    var items = __get_collapsible_group_contents(fieldset);

    items.appendChild(__create_field("username", "Username", "string", "textinput", "", true));
    items.appendChild(__create_field("password", "Set password", "string", "semihidden", "", true));
    items.appendChild(__create_field("fixed_ip", "Fixed IP address", "formipv4address", "textinput", "", false));
    items.appendChild(__create_field("admin_rights", "Allow VPNease administration", "boolean", "checkbox", "false", true)); 
    items.appendChild(__create_field("vpn_rights", "Allow VPN access", "boolean", "checkbox", "true", true)); 
    return fieldset;
  }

  // XXX: needs updating
  var listtypes = {
    'config-ar_group': __create_route_list_entry,
    'config-fwrule_group': __create_ppp_firewall_rule_list_entry,
    'config-port_forwards': __create_port_forwards_list_entry,
    'config-s2s_connections': __create_s2s_connections_list_entry,
    'config-userlist_group': __create_userlist_entry
  };

  var f = listtypes[cssid];
  if (f == undefined) {
    myfatal("formal_dynamiclist_create_new_element_for_specific_list: unknown list: " + cssid);
  }

  return f();
}

function formal_dynamiclist_get_listnames() {
  // XXX: needs updating
  return [ "test-test_list", "config-ar_group", "config-fwrule_group", "config-port_forwards",
           "config-s2s_connections",
           "config-userlist_group" ];
}

// Adorning radiobuttons

// Returns true if the field is enabled, false if the field is disabled.
function field_enabled_status(cssid) {
  function __check_radio(cssid, checked_status) {
    var rbutton = document.getElementById(cssid);
    var result = (rbutton.checked == checked_status);
    return result; 
  }
  
  // Dynamic list item elements 0 = key before list index, 1 = list index, 2 = key after list index.
  var dynamic_list_item = []; 

  // Check if the current item is dynamic list element which could be disabled.
  function __check_dynamic_list_item(cssid) {
    var dynamic_items = ["config-ar_group- -gateway"];  
    //alert(check_id);
    
    for (x in dynamic_items) {
      var dyn_elems = dynamic_items[x].split(" ");
      
      if (dyn_elems[0] == cssid.substring(0, dyn_elems[0].length) && 
          dyn_elems[1] == cssid.substring(cssid.indexOf('-', dyn_elems[0].length))) {
        // Dynamic list element found. Fill dynamic_list_item list and return true.
        dynamic_list_item.push(dyn_elems[0]);
        dynamic_list_item.push(cssid.substring(dyn_elems[0].length, cssid.indexOf('-', dyn_elems[0].length)));
        dynamic_list_item.push(dyn_elems[1]);
        return true;
      }
      
      return false;
    }
  }

  if (__check_dynamic_list_item(cssid)) {
    cssid = dynamic_list_item[0] + '*' + dynamic_list_item[2];
  }

  switch (cssid) {
  case "config-pn_group":
    return __check_radio("config-ifcount_group-interface_count-1", true);
  case "config-ic_group-ip_address-field":
  case "config-ic_group-subnet_mask-field":
    return __check_radio("config-ic_group-ip_address_selection-1", true);
  case "config-pn_group-ip_address-field":
  case "config-pn_group-subnet_mask-field":
    return __check_radio("config-pn_group-ip_address_selection-1", true);  
  case "config-dns_group-dns_1":
  case "config-dns_group-dns_2":
    return __check_radio("config-dns_group-dns_selection-2", true);
  case "config-dns_group-dns_selection-0":
    return __check_radio("config-ic_group-ip_address_selection-0", true);
  case "config-dns_group-dns_selection-1":
    return __check_radio("config-pn_group-ip_address_selection-0", true) &&
           __check_radio("config-ifcount_group-interface_count-1", true);
  case "config-dr_group-gateway":
    return __check_radio("config-dr_group-gateway_selection-1", true);
  case "config-ar_group-*-gateway":
    return __check_radio("config-ar_group-" + dynamic_list_item[1] + "-gateway_selection-1", true);
  case "config-sr_group-network_connection":
  case "config-sr_group-gateway_selection-0":
  case "config-sr_group-gateway_selection-1":
    return __check_radio("config-sr_group-source_routing_selection-0", true);  
  case "config-sr_group-gateway":
    return __check_radio("config-sr_group-gateway_selection-1", true) && 
           __check_radio("config-sr_group-source_routing_selection-0", true);
  case "config-client_connection-dns_1":
  case "config-client_connection-dns_2":
    return __check_radio("config-client_connection-dns-1", true);
  case "config-ddns_group-ddns_address":
    return __check_radio("config-ddns_group-ddns_address_type-2", true);
  }
  return true;
}

function formal_get_radiobuttons_names() {
  // XXX: needs updating
  return [ "config-ifcount_group-interface_count-0", "config-ifcount_group-interface_count-1",
           "config-ic_group-ip_address_selection-0", "config-ic_group-ip_address_selection-1",
           "config-pn_group-ip_address_selection-0", "config-pn_group-ip_address_selection-1",
	   "config-ddns_group-ddns_address_type-0", "config-ddns_group-ddns_address_type-1", "config-ddns_group-ddns_address_type-2", 
           "config-dns_group-dns_selection-0", "config-dns_group-dns_selection-1", "config-dns_group-dns_selection-2",
           "config-dr_group-gateway_selection-0", "config-dr_group-gateway_selection-1",
           "config-sr_group-source_routing_selection-0", "config-sr_group-source_routing_selection-1",
           "config-sr_group-gateway_selection-0", "config-sr_group-gateway_selection-1",
           "config-client_connection-dns-0", "config-client_connection-dns-1"];
}

function formal_get_dynamic_radiobuttons_names() {
  // XXX: needs updating
  return [ "config-ar_group-*-gateway_selection-0", "config-ar_group-*-gateway_selection-1" ];
}
    
// Adorning submit buttons
function formal_get_form_names() {
  return ["config", "management"];
}


// Execute when DOM is loaded
addDOMLoadEvent(formal_body_onload_init);


/*
 *  Waiting for product reboot
 *
 *  Wait for at least one check page request failure, and then one success.
 *  This is a relatively OK indication that reboot is complete.  Requires
 *  ajaxutils.
 */

function wait_product_reboot() {
  var _got_fail = 0;

  function _wait_reboot_update(resp, xhr) {
    /*
     *  The connection will be down for some time during activation.
     *  That causes the Ajax requests to time out or fail with some
     *  error; both are propagated here as resp = null.
     */ 
    try {
      if(resp == null) {
        _got_fail = 1;
      } else if((resp != null) && (resp != '')) {
        if(_got_fail) {
          var newLocation = null;
          if (host_root_http_uri.indexOf('http:') == 0) {
            newLocation = 'https://' + host_root_http_uri.substr(7) + 'admin/';
          } else {
            newLocation = host_root_http_uri + 'admin/';
          }

	  // give web ui time to start
	  setTimeout(function(){ window.location = newLocation; }, 5000);
        }
      }
    } catch(e) {
      ;
      // alert(e);
    }
    
    return true;
  }
  
  if(cb_ajax_supported()) {
    // NB: This only works if a HTTPS URI is used (assuming current page is HTTPS).
    // Probably some sort of cross-site scripting protection in client-side implementations.
    check_uri = host_root_https_uri + "check.html";
    create_continuous_ajax_request_with_delay(check_uri, _wait_reboot_update, 5000, 2000);
  }
}
