/*
 *  Ajax update code for all admin pages.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 */

var ADMINPAGE_GLOBAL_TIMEOUT = 30*60*1000;
var ADMINPAGE_AJAX_TIMEOUT = 120*1000;

function _global_timeout_timer() {
  window.location = global_timeout_uri;
}

var global_timer = null;

function launch_global_timeout_timer(timeout) {
  global_timer = setTimeout(_global_timeout_timer, timeout);
}

function _status_update(resp, xhr) {
  var success = true;
  try {
    var t = resp.split('\n');  // resp may be null, in case we except
    var n = null;

    /* Check that we got enough parameters to prevent unnecessary failures below */
    if (t.length < 28) {
      throw("invalid ajax result");
    }

    /* Unpack parameters */
    var idx = 0;
    var username = t[idx++];

    var tmp = t[idx++].split('\t');
    var status_class = tmp[0];
    var status_text = tmp[1];
    var substatus_class = tmp[2];
    var substatus_text = tmp[3];

    var users_text = t[idx++];

    var s2s_text = t[idx++];

    var sw_version = t[idx++];

    var date_time = t[idx++];

    var lic_key = t[idx++];
    var lic_key_or_demo = t[idx++];
    var lic_name = t[idx++];
    var lic_name_or_demo = t[idx++];
    var lic_user = t[idx++];
    var lic_s2s = t[idx++];

    var cpu_usage = t[idx++];
    var disk_usage = t[idx++];
    var memory_usage = t[idx++];
    var swap_usage = t[idx++];

    var service_uptime = t[idx++];
    var latest_sw_version = t[idx++];
    var update_available = t[idx++];

    var public_address = t[idx++];
    var public_interface_string = t[idx++];
    var public_mac = t[idx++];
    var public_rxtx_summary = t[idx++];

    var private_address = t[idx++];
    var private_interface_string = t[idx++];
    var private_mac = t[idx++];
    var private_rxtx_summary = t[idx++];

    var server_uptime = t[idx++];

    var dnswins_status_overview = t[idx++];
    var router_status_overview = t[idx++];
    var s2s_status_overview = t[idx++];

    var management_connection_status = t[idx++];

    var dyndns_line = t[idx++];

    /* XXX: this is not the cleanest approach but works for now */
    var dyndns_class = "";
    if (dyndns_line.length >= 5) {
      /* NB: there is no 'endsWith' in Javascript */
      if (dyndns_line.substring(dyndns_line.length - 5).toLowerCase() == "error") {
        dyndns_class = "warning";
      }
    }

    /* Helper to update a node's content cleanly */
    function _set_node_text(nodeid, text, nodeclass) {
      try {
        var n = document.getElementById(nodeid);
        if(n) {
          dom_remove_all_children(n);
	  if ((text == null) || (text == undefined) || (text == "")) {
	    /* NB: empty string causes "squares" to appear in Konqueror */
	    text = " ";
	  }
          n.appendChild(document.createTextNode(text));
          if ((nodeclass != null) && (nodeclass != undefined)) {
            n.className = nodeclass;
          }
        }
      } catch(e) {
        success = false;
      }
    }

    /* Helper to update server status lists in status overview page */
    function _update_server_status_list(nodeid, ajax_text) {
      try {
        var n = document.getElementById(nodeid);
        if(n) {
          var trip = ajax_text.split('\t');  // 3n elements, triplets of (text, status, class)
          var num = parseInt(trip.length / 3);    // without parseInt(), this will be a float.. beautiful

          dom_remove_all_children(n);

          if (num > 0) {
            for (var i = 0; i < num; i++) {
              s_text = trip[3*i+0];
              s_status = trip[3*i+1];
              s_class = trip[3*i+2];

              if (i > 0) {
                n.appendChild(document.createElement("br"));
              }

              var tmp = document.createElement("span");
              if (s_class != "") {
                tmp.className = s_class;
              }
              tmp.appendChild(document.createTextNode(s_text + " (" + s_status + ")"));

              n.appendChild(tmp);
            }
          } else {
            var none_text = "None";

            // special case: if one element list, take "none" string from there
            if (trip[0]) {
              none_text = trip[0];
            }
            n.appendChild(document.createTextNode(none_text));
          }
        }
      } catch(e) {
        success = false;
      }
    }

    // computed values

    // adminpage.xhtml
    _set_node_text("status-username", username, null);
    _set_node_text("status-text", status_text, status_class);
    _set_node_text("status-substatus-text", substatus_text, substatus_class);
    _set_node_text("status-user-count", users_text, null);
    _set_node_text("status-user-limit", lic_user, null);
    _set_node_text("status-s2s-count", s2s_text, null);
    _set_node_text("status-s2s-limit", lic_s2s, null);
    _set_node_text("status-datetime", date_time, null);
    _set_node_text("status-software-version", sw_version, null);

    // status/main.xhtml
    _set_node_text("status-overview-state", status_text, null);
    _set_node_text("status-overview-user-count", users_text, null);
    _set_node_text("status-overview-sitetosite-count", s2s_text, null);
    _set_node_text("status-overview-service-uptime", service_uptime, null);
    _set_node_text("status-overview-current-software-version", sw_version, null);
    _set_node_text("status-overview-update-available", update_available, null);
    _set_node_text("status-overview-public-address", public_address, null);
    _set_node_text("status-overview-public-interface-string", public_interface_string, null);
    _set_node_text("status-overview-public-mac", public_mac, null);
    _set_node_text("status-overview-public-rxtx-summary", public_rxtx_summary, null);
    _set_node_text("status-overview-private-address", private_address, null);
    _set_node_text("status-overview-private-interface-string", private_interface_string, null);
    _set_node_text("status-overview-private-mac", private_mac, null);
    _set_node_text("status-overview-private-rxtx-summary", private_rxtx_summary, null);
    _set_node_text("status-overview-cpu-usage", cpu_usage, null);
    _set_node_text("status-overview-memory-usage", memory_usage, null);
    _set_node_text("status-overview-swap-usage", swap_usage, null);
    _set_node_text("status-overview-server-uptime", server_uptime, null);
    _set_node_text("status-overview-license-key", lic_key_or_demo, null);
    _set_node_text("status-overview-license-name", lic_name_or_demo, null);
    _set_node_text("status-overview-license-user-limit", lic_user, null);
    _set_node_text("status-overview-license-sitetosite-limit", lic_s2s, null);
    _set_node_text("status-overview-management-connection-status", management_connection_status, null);
    _set_node_text("status-overview-public-dyndns", dyndns_line, dyndns_class);

    // server status lists
    _update_server_status_list("status-overview-dns-wins-overview", dnswins_status_overview);
    _update_server_status_list("status-overview-router-overview", router_status_overview);
    _update_server_status_list("status-overview-sitetosite-overview", s2s_status_overview);

    // status-overview-last-automatic-reboot-time            - static
    // status-overview-next-automatic-reboot-time            - static
    // status-overview-last-successful-product-update-time   - static

  } catch(e) {
    success = false;
    // alert(e);
  }
  
  return success;
}

// Launch global timer and start ajax update.
addDOMLoadEvent(function() {
                  launch_global_timeout_timer(ADMINPAGE_GLOBAL_TIMEOUT);
                  create_continuous_ajax_request(webui_root_uri + "ajaxstatus.html", _status_update, ADMINPAGE_AJAX_TIMEOUT);
                })

// Clear global timer on page exit (just in case...).
add_window_unload_event(function() {
    if (global_timer != null) {
      clearTimeout(global_timer);
    }
  })
