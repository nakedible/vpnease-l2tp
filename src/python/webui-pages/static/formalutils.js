/*
 *  Javascript helpers for interacting with server-side Formal fields in
 *  the client-side.  This file provides support for:
 *
 *    * Dynamic list editing in client-side
 *    * Collapsible groups
 *    * Semihidden password fields
 *    * Adorning formal elements
 *
 *  Page must call formal_body_onload_init() in "onload" of <body>.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 *
 * --------------------------------------------------------------------------
 *
 *  The functions in this file manipulate server-side generated DOM
 *  elements: the 'id', 'class', 'name', 'for', etc attributes are
 *  dynamically renumbered, and server-side elements are "adorned"
 *  with extra elements (such as edit buttons).  The code also generates
 *  completely new DOM structure when e.g. the "add" button is pressed.
 *
 *  This code must remain in synchronization with the server side to
 *  a quite large extent.
 *
 *  The support for dynamic list is not fully generalized.  This file
 *  assumes that an external Javascript file provides definitions
 *  for the following functions related to manipulating dynamic lists:
 *
 *    * formal_dynamiclist_create_new_element_for_specific_list()
 *      + Creates a new DOM element for a specific list (by list name)
 *      + This function must know all available lists in the product
 *
 *    * formal_dynamiclist_get_listnames()
 *      + Returns a list of dynamic list names for adorning
 *
 * --------------------------------------------------------------------------
 *
 *  IE fixes marked below, grep for IE.  Some resources:
 *
 *    * getAttribute() problems: http://www.thescripts.com/forum/thread92655.html
 *
 *      The important thing is to *not* use setAttribute() whenever a DOM
 *      object has an attribute that can be accessed directly.  Hence use:
 *         foo.className = "xyz";
 *      instead of:
 *         foo.setAttribute("class", "xyz");  // will not work in IE
 *         
 *      NOTE: className must be set directly, but others are set with setAttribute,
 *      because Safari will not accept direct assingment with name, checked, etc...    
 *
 *      See: http://www.w3.org/TR/DOM-Level-2-HTML/html.html
 *
 *    * insertBefore() problems: http://www.howtocreate.co.uk/emails/KaranSMohite.html
 *
 *    * Setting event handlers (like onclick) to new DOM nodes is not
 *      straightforward: setAttribute("onclick") or node.onclick does not
 *      work in IE. 
 *
 *      See: http://www.javascriptkit.com/domref/elementmethods.shtml,
 *           http://en.wikipedia.org/wiki/DOM_Events.
 *
 */

/* --------------------------------------------------------------------------
 *  General Formal support
 */

// "testform", "foo.bar.baz" => "testform-foo-bar-baz"
function formal_key_to_cssid(form, key) {
  return form + "-" + key.split(".").join("-");
}

// "testform-foo-bar-baz" => ["testform", "foo.bar.baz"]
function formal_cssid_to_key(cssid) {
  var t = cssid.split("-");
  return [t[0], t.slice(1).join(".")];
}

// "foo.bar.baz" => ["foo", "bar", "baz"]
function formal_key_split(key) {
  return key.split(".");
}

// ["foo", "bar", "baz"] => "foo.bar.baz"
function formal_key_join(keyparts) {
  return keyparts.join(".");
}

// "testform-foo-bar-baz" => ["testform", "foo", "bar", "baz"]
function formal_cssid_split(cssid) {
  return cssid.split("-");
}

// ["testform", "foo", "bar", "baz"] => "testform-foo-bar-baz"
function formal_cssid_join(cssidparts) {
  return cssidparts.join("-");
}

// Return number of occurrences of attributes in attributes list found from css class list.
// Trying to optimize enable check. 
// XXX: naming is misleading: class does not have attributes, but multipe classes
function formal_class_has_attributes(aclass, alist) {
  var tmp = aclass.split(" ");
  var occurrences = 0;
  
  for (var idx in tmp) {
    for (var attribute in alist) {
      if (tmp[idx] == alist[attribute])
        occurrences ++;
    }
  }

  return occurrences;
}

// Returns number of occurrences of attribute x in css class list.
// XXX: naming is misleading: class does not have attributes, but multiple classes
function formal_class_has_attribute(aclass, x) {
  return formal_class_has_attributes(aclass, [x]);
}

// add 'x' to class "list", e.g. "foo bar baz" => "foo bar baz x"
// Add x only if the class does not already exist in the class list.
function formal_class_add(aclass, x) {
  var occurrences = formal_class_has_attribute(aclass, x);
  if (occurrences == 1)
    return aclass;
  
  if (occurrences > 1)
    var r = formal_class_remove(aclass, x);
  else
    var r = aclass;
    
  var tmp = r.split(" ").concat([x]);
  return tmp.join(" ");
}

// remove 'x' from class "list", e.g. "foo bar baz x" => "foo bar baz"
// (if x is not in the list, it is not removed; if it is in the list
// multiple times, all occurrences are removed)
function formal_class_remove(aclass, x) {
  var r = [];
  var tmp = aclass.split(" ");

  for (var idx in tmp) {
    var c = tmp[idx];
    if (c != x) {
      r = r.concat([c]);
    }
  }
  return r.join(" ");
}

// replace old_prefix with new_prefix, if string starts with old_prefix;
// if not, return string unchanged
function formal_prefix_replace_maybe(str, old_prefix, new_prefix) {
  var oldlen = old_prefix.length;

  if (str.length < oldlen) {
    return str;
  }

  if (str.substring(0, oldlen) == old_prefix) {
    return new_prefix + str.substring(oldlen);
  }

  return str;
}

/*
 *  Recursive tree walks
 *
 */

function _formal_recursive_preorder_form_node_walk(startnode, func) {
  function __recursive_form_walk(node) {
    if ((node == null) || (node == undefined)) {
      return;
    }
    if (node.nodeType == JS_DOM_NODE_TYPE_ELEMENT_NODE) {
      func(node);
    }

    if (node.childNodes) {
      for (var i = 0; node.childNodes[i]; i++) {
        var t = node.childNodes[i];
        __recursive_form_walk(t);
      }
    }
  }

  __recursive_form_walk(startnode);
}

/*
 *  Workhorse functions for manipulating attribute value prefixes and
 *  substring for e.g. renumbering of list elements.
 *
 */
function formal_recursive_replace_attribute_value_prefix(node, old_prefix, new_prefix, attrlist) {
  if(false) {
    mydebug("formal_recursive_replace_attribute_value_prefix: node=" + node +
        " old_prefix=" + old_prefix +
        " new_prefix=" + new_prefix +
        " attrlist=" + attrlist);
  }

  __formal_recursive_replace_attribute_value(node, old_prefix, new_prefix, attrlist, formal_prefix_replace_maybe);
}

function __formal_recursive_replace_attribute_value(node, old_prefix, new_prefix, attrlist, replacefunc) {
  // first deal with current node's attributes
  for (var elem in attrlist) {
    var attr_name = attrlist[elem];
    // XXX: getNamedItem case sensitivity should be find out.
    var attribute = node.attributes.getNamedItem(attr_name);
    if (attribute != null) {
      attribute.nodeValue = replacefunc(attribute.nodeValue, old_prefix, new_prefix);
    }
  }

  // then recurse through child elements
  for (var x = 0; node.childNodes[x]; x++) {
    var n = node.childNodes[x];
    if (n.nodeType == JS_DOM_NODE_TYPE_ELEMENT_NODE) {
      __formal_recursive_replace_attribute_value(n, old_prefix, new_prefix, attrlist, replacefunc);
    }
  }
}

/* --------------------------------------------------------------------------
 *  Formal Field support routines
 */

// create a new field ("mirror" of formal.form.FieldFragment on server side)
// XXX: does not work correctly with dynamiclists, but we don't have nested lists
function formal_field_create(params) {
  var form = params.form;
  var key = params.key;
  var label = params.label;
  var description = params.description;
  var value = params.value;
  var field_type = params.field_type;
  var input_type = params.input_type;
  var has_error = false;                    // XXX
  var is_required = params.is_required;

  var cssid = formal_key_to_cssid(form, key);

  var div1 = document.createElement("div");
  var classes = [];
  classes = classes.concat(["field"]);
  classes = classes.concat([field_type]);
  classes = classes.concat([input_type]);
  if (is_required) {
    classes = classes.concat(["required"]);
  }
  if (has_error) {
    classes = classes.concat(["error"]);
  }
  div1.className = classes.join(" ");
  div1.setAttribute("id", cssid + "-field");

  var label1 = document.createElement("label");
  label1.className = "label";
  label1.setAttribute("for", cssid);
  label1.appendChild(document.createTextNode(label));
  div1.appendChild(label1);

  var div2 = document.createElement("div");
  div2.className = "inputs";
  div1.appendChild(div2);

  var div3 = document.createElement("div");
  div3.className = "description";
  if (description == undefined) {
    description = "";
  }
  div3.appendChild(document.createTextNode(description));
  div1.appendChild(div3);

  /*
   *  XXX: the "widget" part here has not been implemented fully.
   *  Instead of full widget support, we're only able to create
   *  inputs of specific types.
   */
   
  // setAttribute must be used instead of element.attribute = 
  // The latter does not assign all the attribute values in Safari.
  function __create_text_element() { 
    var input_text = document.createElement("input");
    input_text.setAttribute("id", cssid);
    input_text.setAttribute("value", value);
    input_text.setAttribute("name", key);
    input_text.setAttribute("type", "text");  // NB: input1.type doesn't work in IE6
    input_text.setAttribute("tabIndex", 1);
    div2.appendChild(input_text);
  }

  function __create_semihidden_element() { 
    var input_text = document.createElement("input");
    input_text.setAttribute("id", cssid);
    input_text.setAttribute("value", value);
    input_text.setAttribute("name", key);
    input_text.setAttribute("type", "password");
    input_text.setAttribute("tabIndex", 1);
    input_text.className = "semihidden";

    input_text.onfocus = function() { return function() { formal_semi_hidden_password_show(this.id); } } ();
    input_text.onblur = function() { return function() { formal_semi_hidden_password_hide(this.id); } } ();

    div2.appendChild(input_text);
  }
  
  function __create_checkbox() {
    var input_checkbox = document.createElement("input");
    input_checkbox.setAttribute("type", "checkbox");
    input_checkbox.setAttribute("tabIndex", 1);
    input_checkbox.setAttribute("id", cssid);
    input_checkbox.value = "True"; // XXX: seems like value is always true in checkboxes.
    input_checkbox.setAttribute("name", key);
    if (params.checked) {
      /* NB: .checked may be cleared in IE when the node is added or moved in the DOM; workaround using defaultChecked */
      input_checkbox.setAttribute("checked", true);
      input_checkbox.setAttribute("defaultChecked", true);
    }
    div2.appendChild(input_checkbox);
  }
  
  function __create_select_element() {
    var input_select = document.createElement("select");
    input_select.setAttribute("tabIndex", 1);
    input_select.setAttribute("id", cssid);
    input_select.setAttribute("name", key);
    if (params.select_options == null || params.select_options == undefined) {
      alert("params.options is null or undefined.")
    }
    
    for (x in params.select_options) {
      var opt = params.select_options[x];  
      var input_option = document.createElement("option");
      input_option.setAttribute("value", opt.value);
      input_option.appendChild(document.createTextNode(opt.label));
      if (opt.selected) {
        input_option.setAttribute("selected", "selected");
      }
      input_select.appendChild(input_option);
    }
    div2.appendChild(input_select);
  }
  
  function __create_radio_group() {
    for (x in params.radiobuttons) {
      var rbutton = params.radiobuttons[x];
      
      /*
      * IE 6 requires a special DOM-insertion of radio buttons. The following code works around that lack of support.
      * XXX: The fix is based to the example shown at: http://www.gtalbot.org/DHTMLSection/DynamicallyCreateRadioButtons.html
      */
      if(document.all && !window.opera && document.createElement) {
        // XXX: Defaultchecked value has not been tested. Currently none of the dynamically created radiobuttons is checked by default.
        var defCheck = rbutton.checked ? "true" : "false"; 
        var input_radio = document.createElement("<input type='radio' name='" + key +"' id='"+ cssid + "-" + rbutton.id + "' value='" + rbutton.value + "' defaultChecked='" + defCheck + "'>");
      }
      else {
        var input_radio = document.createElement("input");  
      
        input_radio.type = "radio";
        input_radio.setAttribute("tabIndex", 1);
        input_radio.setAttribute("id", cssid + "-" + rbutton.id);
        input_radio.setAttribute("value", rbutton.value);
        input_radio.setAttribute("name", key);

        if (rbutton.checked) {
          /* NB: .checked may be cleared in IE when the node is added or moved in the DOM; workaround using defaultChecked */
          input_radio.setAttribute("checked", true);
          input_radio.setAttribute("defaultChecked", true);
        }
      }
        
      var radio_label = document.createElement("label");
      radio_label.setAttribute("for", cssid + "-" + rbutton.id);
      radio_label.appendChild(document.createTextNode(rbutton.label));
        
      div2.appendChild(input_radio);
      div2.appendChild(document.createTextNode(" "));  // server generates one space here
      div2.appendChild(radio_label);
      div2.appendChild(document.createElement("br"));
      
    }
  }
  
  switch (input_type) {
  case "textinput":
    __create_text_element();
    break;
  case "semihidden":
    __create_semihidden_element();
    break;
  case "selectchoice":
    __create_select_element();
    break;
  case "radiochoice":
    __create_radio_group();
    break;
  case "checkbox":
    __create_checkbox();
    break;
  default:
    myfatal("Unknown input type in formal_field_create: " + input_type);
  }

  return div1;
}

/* --------------------------------------------------------------------------
 *  Formal dynamiclist buttons
 */

function __listitem_get_listname(cssid) {
  var t = formal_cssid_split(cssid);
  var s = t.slice(0, t.length-1);
  return formal_cssid_join(s);
}

function __listitem_get_listindex(cssid) {
  var t = formal_cssid_split(cssid);
  return t[t.length-1] * 1;  // converts to int
}

function formal_event_button_up_cssid(cssid) {
  formal_dynamiclist_highlight_entry(__listitem_get_listname(cssid),
                     __listitem_get_listindex(cssid),
                     150, 150, 1100);

  formal_dynamiclist_moveup_entry(__listitem_get_listname(cssid),
                  cssid);
}

function formal_event_button_up_node(node) {
  formal_event_button_up_cssid(node.id);
}

function formal_event_button_down_cssid(cssid) {
  formal_dynamiclist_highlight_entry(__listitem_get_listname(cssid),
                     __listitem_get_listindex(cssid),
                     150, 150, 1100);

  formal_dynamiclist_movedown_entry(__listitem_get_listname(cssid),
                    cssid);
}

function formal_event_button_down_node(node) {
  formal_event_button_down_cssid(node.id);
}

// Sets a focus to the first input element in a dynamic list element.
function formal_focus_first_input_element(cssid) {
  var list_element = document.getElementById(cssid);
  if (list_element == null) {
    return;
  }
  var content_elems = list_element.getElementsByTagName("div");
  var focus_elem = null;
  
  for (i=0; i<content_elems.length; i++) {
    if (content_elems[i].className == "collapsible-group-contents") {
      // XXX: assumes that such an input element can be found
      focus_elem = content_elems[i].getElementsByTagName("input")[0];
    }
  }
  
  if (focus_elem != null) {
    focus_elem.hasFocus=true; // XXX
    focus_elem.focus();
    focus_elem.select();  // Safari
  }
}

function formal_event_button_add_cssid(cssid) {
  var listname = __listitem_get_listname(cssid);

  /*
   *  This is the tricky part: we need some helper to create a new DOM entry
   *  with default values etc for the list.  We consult a global helper function
   *  for this purpose; glue must be built there to make this happen.  This is
   *  decidedly ugly, but a more generic solution is probably too complex.
   *
   *  Note that the list index is initially 20000 in order to avoid overlapping
   *  with an existing list group. List will be renumbered in _add_entry.
   */

  var new_node = formal_dynamiclist_create_new_element_for_specific_list(listname);

  formal_dynamiclist_add_entry(listname, cssid, new_node);

  // highlight entry after renumbering (id may have changed)
  var new_cssid = new_node.id;
  formal_dynamiclist_highlight_entry(__listitem_get_listname(new_cssid),
                     __listitem_get_listindex(new_cssid),
                     150, 150, 1100);
                     
  
  
  // formal_dynamiclist_renumber_list(listname);

  // Set focus to first input element in the new object.
  setTimeout(function(){ formal_focus_first_input_element(new_cssid); }, 100);
}

function formal_event_button_add_node(node) {
  formal_event_button_add_cssid(node.id);
}

function formal_event_button_add_last_cssid(cssid) {
  // NB: cssid = list, not element
  var listname = cssid;

  var len = formal_dynamiclist_get_length(listname);
  var new_node = formal_dynamiclist_create_new_element_for_specific_list(listname);
  //formal_dynamiclist_add_entry(listname, len, new_node);
  formal_dynamiclist_add_entry(listname, "", new_node);
  // highlight entry after renumbering etc
  var new_cssid = new_node.id;
  formal_dynamiclist_highlight_entry(__listitem_get_listname(new_cssid),
                     __listitem_get_listindex(new_cssid),
                     150, 150, 1100);

  // Set focus to first input element in the new object.
  setTimeout(function(){ formal_focus_first_input_element(new_cssid); }, 100);
}

function formal_event_button_add_last_node(node) {
  formal_event_button_add_last_cssid(node.id);  // NB: node is list, not elem
}

function formal_event_button_remove_cssid(cssid) {
  formal_dynamiclist_del_entry(__listitem_get_listname(cssid), cssid);
}

function formal_event_button_remove_node(node) {
  formal_event_button_remove_cssid(node.id);
}

/* --------------------------------------------------------------------------
 *  Formal Group support
 */

// create a new group (or dynamiclist)
function formal_group_create(params) {
  var form = params.form;
  var key = params.key;
  var aclass = params.aclass;   // group or dynamiclist
  var legend = params.legend;
  var description = params.description;
  var list_buttons = params.list_buttons;
  if (list_buttons == undefined) {
    list_buttons = false;
  }
  var collapsible = params.collapsible;
  if (collapsible == undefined) {
    collapsible = false;
  }
  var collapsedsummary = params.collapsedsummary;
  if (collapsedsummary == undefined) {
    collapsedsummary = "";
  }

  var cssid = formal_key_to_cssid(form, key);

  var fieldset1 = document.createElement("fieldset");
  fieldset1.className = aclass;
  fieldset1.id = cssid;

  if (collapsible) {
    var hidden_state = document.createElement("span");  // XXX: feeding hidden input of this element to server is pointless
    fieldset1.appendChild(hidden_state);

    var legend1 = document.createElement("legend");
    var controls = document.createElement("span");
    controls.className = "collapse-controls";
    legend1.appendChild(controls);
    legend1.appendChild(document.createTextNode(legend));
    __formal_create_collapse_controls_node(fieldset1, controls, false);
    fieldset1.appendChild(legend1);

    if (list_buttons) {
      var div0 = document.createElement("div");
      div0.className = "listbuttons";
      __formal_append_listbuttons(fieldset1, div0, false);
      fieldset1.appendChild(div0);
    }
    
    var div1 = document.createElement("div");
    div1.className = "description";
    div1.appendChild(document.createTextNode(description));
    fieldset1.appendChild(div1);

    var div2 = document.createElement("div");
    div2.className = "collapsible-group-summary";
    var div3 = document.createElement("div");
    div3.className = "collapsible-hide";
    if (collapsedsummary != "") {
      div3.appendChild(document.createTextNode(collapsedsummary));
    } else {
      // XXX: default contents are now fixed
      var cs_span = document.createElement("span");
      var cs_img = document.createElement("img");
      cs_img.src = "/static/arrow.gif";  // XXX: fixed
      cs_img.width = 8;
      cs_img.height = 10;
      cs_img.alt = ">";
      cs_span.appendChild(document.createTextNode("Click "));
      cs_span.appendChild(cs_img);
      cs_span.appendChild(document.createTextNode(" to expand."));
      div3.appendChild(cs_span);
    }
    div2.appendChild(div3);
    fieldset1.appendChild(div2);

    var div4 = document.createElement("div");
    div4.className = "collapsible-group-contents";
    var div5 = document.createElement("div");
    div5.className = "collapsible-show";
    div4.appendChild(div5);
    fieldset1.appendChild(div4);
  } else {
    var legend1 = document.createElement("legend");
    legend1.appendChild(document.createTextNode(legend));
    fieldset1.appendChild(legend1);

    if (list_buttons) {
      var div0 = document.createElement("div");
      div0.className = "listbuttons";
      __formal_append_listbuttons(fieldset1, div0, false);
      fieldset1.appendChild(div0);
    }
    
    var div1 = document.createElement("div");
    div1.className = "description";
    div1.appendChild(document.createTextNode(description));
    fieldset1.appendChild(div1);
  }

  return fieldset1;
}

/* --------------------------------------------------------------------------
 *  Formal DynamicList support routines
 */

// Locate relevant nodes in the list node DOM; we try to hide actual list
// element structure here, so that server side implementation can be changed
// with minimum pain.
function __formal_dynamiclist_locate_list_nodes(lst) {
  var cont = null;
  for (var i = 0; lst.childNodes[i]; i++) {
    var c = lst.childNodes[i];

    if (c.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
      continue;
    } else if (c.className == "collapsible-group-contents") {
      cont = c;
    }
  }

  // collapsible-group-contents contains exactly one div with what
  // we're interested in; see server-side
  cont = cont.childNodes[0];

  var header = cont.childNodes[0];
  var contents = cont.childNodes[1];
  var footer = cont.childNodes[2];

  return [header, contents, footer];
}

function __formal_dynamiclist_locate_list_header(lst) {
  var t = __formal_dynamiclist_locate_list_nodes(lst);
  if (t) {
    return t[0];
  }
  return null;
}

function __formal_dynamiclist_locate_list_contents(lst) {
  var t = __formal_dynamiclist_locate_list_nodes(lst);
  if (t) {
    return t[1];
  }
  return null;
}

function __formal_dynamiclist_locate_list_footer(lst) {
  var t = __formal_dynamiclist_locate_list_nodes(lst);
  if (t) {
    return t[2];
  }
  return null;
}

// get length of list (based on DOM)
function formal_dynamiclist_get_length(cssid) {
  var lst = document.getElementById(cssid);
  return __formal_dynamiclist_locate_list_contents(lst).childNodes.length;
}

// renumber a selected entry with new_idx
function formal_dynamiclist_renumber_entry(cssid_item, new_idx) {
  var node = document.getElementById(cssid_item);
  formal_dynamiclist_renumber_entry_dom(node, cssid_item, new_idx);
}

// renumber one dynamic list element
function formal_dynamiclist_renumber_entry_dom(node, cssid_item, new_idx) {
  // cssid_item example: 'test_form-test_list-7'
  // cssid_list example: 'test_form-test_list'
  //
  // We need to substitute all cssids and keys in the item and in its children
  // (recursively):
  //
  //    cssids:   test_form-test_list-7(#) => test_form-test_list-<new_idx>(#)
  //    keys:     test_list.7(#)           => test_list.<new_idx>(#)
  //
  // We do this by replacing prefixes in named attributes using a generic
  // helper.

  
  var cssid_parts = formal_cssid_split(cssid_item);
  
  var cssid_list = formal_cssid_join(cssid_parts.slice(0, cssid_parts.length - 1));
  var old_prefix = cssid_item;
  var new_prefix_parts = cssid_parts.slice(0, cssid_parts.length - 1);
  new_prefix_parts = new_prefix_parts.concat(["" + new_idx]);
  var new_prefix = formal_cssid_join(new_prefix_parts);
  var tmp = formal_cssid_to_key(old_prefix);
  var old_key_prefix = tmp[1];
  var tmp = formal_cssid_to_key(new_prefix);
  var new_key_prefix = tmp[1];

  // Change prefix only if it has been changed.
  // XXX: May be used if more performance is needed. Currently no need?
  //if (old_prefix == new_prefix) {
  //  return;
  //}
  
  formal_recursive_replace_attribute_value_prefix(node,
                          old_prefix,
                          new_prefix,
                          [ "id", "for" ]);

  formal_recursive_replace_attribute_value_prefix(node,
                          old_key_prefix,
                          new_key_prefix,
                          [ "name" ]);

}

/*
 *  Renumber the dynamic list based on element occurrence in the
 *  list DOM node.  This operation "normalizes" the list after any
 *  edits have been made to the list (e.g. swapping elements, adding
 *  or removing elements).
 */
function formal_dynamiclist_renumber_list(cssid) {
  var lst = document.getElementById(cssid);
  check_valid_ref(lst);
   
  var curr_idx = 0; // 0 is the first element number.
  
  var cont = __formal_dynamiclist_locate_list_contents(lst);
  
  for (var i = 0; cont.childNodes[i]; i++) {
    var c = cont.childNodes[i];
    var name = c.nodeName.toLowerCase();
    if (name == "div" || name == "fieldset") {  // fields or groups
      var cssid_item = c.id;
      formal_dynamiclist_renumber_entry_dom(c, cssid_item, curr_idx);
      curr_idx ++;
    } else {
      mydebug ("invalid nodename: " + c.nodeName);
    }
  }
}

// delete an entry and renumber
// cssid is the id of the item to be removed.
function formal_dynamiclist_del_entry(list_name, cssid) {
  var lst = document.getElementById(list_name);
  check_valid_ref(lst);

  var cont = __formal_dynamiclist_locate_list_contents(lst);
  var node = document.getElementById(cssid);
  check_valid_ref(node);

  cont.removeChild(node);

  return node;
}

// add an entry to some index
function formal_dynamiclist_add_entry(cssid, next_elem_cssid, new_node) {
  var lst = document.getElementById(cssid);
  check_valid_ref(lst);

  var cont = __formal_dynamiclist_locate_list_contents(lst);
  
  // If next elem is empty, append to the end of list.
  if (next_elem_cssid == "") {
    cont.appendChild(new_node);
  } else {
    // Insert before next_elem_cssid
    var next_elem = document.getElementById(next_elem_cssid);
    if (next_elem == null) {
      alert("Insertion failed. Could not find next list element.");
      return;
    }
    // cont.insertBefore(new_node, next_elem);
    next_elem.parentNode.insertBefore(new_node, next_elem);
  }
}

/*  swap entries
*   
*   Upper and lower (node) refers to the initial order of the nodes.
*   Actual initial order of the nodes is not checked from the DOM.
*
*   NB: IE insertBefore is slightly broken, it doesn't accept "null"
*   as the before (which should cause it to work like appendChild).
*   Workaround below.
*/
function formal_dynamiclist_swap_entries(list_cssid, upper_node, lower_node) {
  if (upper_node == null && lower_node == null) {
    return;
  }
  
  var lst = document.getElementById(list_cssid);
  check_valid_ref(lst);

  // if indices same, nop
  if (upper_node == lower_node) {
    return;
  }

  var cont = __formal_dynamiclist_locate_list_contents(lst);
  var before = lower_node.nextSibling;

  // remove upper and lower nodes.
  cont.removeChild(upper_node);
  cont.removeChild(lower_node);

  // insert initial lower node first (-> becomes upper)
  if (before == null) {  // IE workaround
    cont.appendChild(lower_node);
  } else {
    cont.insertBefore(lower_node, before);
  }

  // insert initial upper node.
  if (before == null) {  // IE workaround
    cont.appendChild(upper_node);
  } else {
    cont.insertBefore(upper_node, before);
  }

}

// move an entry up
function formal_dynamiclist_moveup_entry(list_cssid, cssid) {
  var list_item = document.getElementById(cssid);
  if (list_item == null) {
    return;
  }
  
  var previous_item = list_item.previousSibling;
  
  if (previous_item == null) {
    return;
  }
  
  formal_dynamiclist_swap_entries(list_cssid, previous_item, list_item);
}

// move an entry down
function formal_dynamiclist_movedown_entry(list_cssid, cssid) {
  var list_item = document.getElementById(cssid);
  if (list_item == null) {
    return;
  }
  
  var next_item = list_item.nextSibling;
  
  if (next_item == null) {
    return;
  }

  formal_dynamiclist_swap_entries(list_cssid, list_item, next_item);
}

// highlight an entry after a delay for a few seconds; can be used
// e.g. after add and move to identify which element was added/moved
//
// this just basically adds and removes a 'highlight' property for
// the entry a few times using a timer
//
// for a nice discussion about js closures, see:
//
//    http://www.jibbering.com/faq/faq_notes/closures.html
//
// NB: it is very important NOT to use cssid lookups in the timer
// callbacks, because they may change when the user further edits
// the list.  Instead, we look up the node and tuck the DOM object
// into the closure for the timer functions.
function formal_dynamiclist_highlight_entry(cssid, idx, delay_ms, interval_ms, duration_ms) {
  var start_time = new Date().getTime();
  var end_time = start_time + delay_ms + duration_ms;
  var item_cssid = formal_cssid_join(formal_cssid_split(cssid).concat([idx]));
  var node = document.getElementById(item_cssid);

  if (node == null || node == undefined) {
    return;
  }

  function highlight_on() {
    var classes = node.className;
    classes = formal_class_add(classes, "highlight");
    node.className = classes;
  }
  function highlight_off() {
    var classes = node.className;
    classes = formal_class_remove(classes, "highlight");
    node.className = classes;
  }

  var f2 = function() {
    highlight_off();
    if (new Date() < end_time) {
      setTimeout(f1, interval_ms);
    } else {
      highlight_off();
    }
  }
  var f1 = function() {
    highlight_on();
    if (new Date() < end_time) {
      setTimeout(f2, interval_ms);
    } else {
      highlight_off();
    }
  }

  setTimeout(f1, delay_ms);
}

// Append list manipulation buttons to either (1) a list element, or
// (2) the list itself (last add button).
//
//    elemnode          node targeted by button action: list or node top level element
//    node              node to which buttons are added (a "list buttons" div)
//    cssid             
//    last_buttons      if true, add last buttons (to list)

function __formal_append_listbuttons(elemnode, node, last_buttons) {
  function __add_button(node, name, buttonfunc) {
    /*
     *  Adding dynamic events to nodes is annoyingly different in browsers.
     *  See: http://www.javascriptkit.com/domref/elementmethods.shtml.
     *
     *  Note that we attach a callback programmatically => the callback
     *  must use a closure which refers to a *node*, not a cssid.  Cssids
     *  are renumbered dynamically when they are e.g. in the "onclick"
     *  attribute, but cssids in our closure are not visible to renumbering,
     *  so a DOM node reference *must* be used instead.
     */

    function __clickhandler() {
      buttonfunc(elemnode); return false;
    }

    var a = document.createElement("a");
    a.href = "#";

    if (a.attachEvent) {  // IE
      a.attachEvent("onclick", __clickhandler);
    } else if (a.addEventListener) {  // FF etc
      a.addEventListener("click", __clickhandler, true);
      a.setAttribute("onclick", "return false;");
    } else {
      ;
    }

    var btn = document.createElement("img");
    btn.src = "/static/button_" + name + ".png";
    btn.width = 13;
    btn.height = 13;
    a.appendChild(btn);

    node.appendChild(a);
  }

  if (last_buttons) {
    // NB: last "add" button node refers to the *list*, not to an element
    // hence changes in semantics, separate callbacks, etc.
    __add_button(node, "add",  formal_event_button_add_last_node);
  } else {
    __add_button(node, "up", formal_event_button_up_node);
    __add_button(node, "down", formal_event_button_down_node);
    __add_button(node, "add", formal_event_button_add_node);
    __add_button(node, "remove", formal_event_button_remove_node);
  }
}

function formal_dynamiclist_check_add_buttons(node) {
  var descnode = null;
  var cssid = node.id;  // node cssid

  // already has buttons?
  for (var x = 0; node.childNodes[x]; x++) {
    var c = node.childNodes[x];

    if (c.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
      continue;
    }

    var name = c.nodeName.toLowerCase();

    if (name == "div"  &&  c.className == "description") {
      descnode = c;
    }

    if (name == "div"  &&  c.className == "listbuttons") {
      return;
    }
  }

  // no, add them before descnode
  var div0 = document.createElement("div");
  div0.className = "listbuttons";
  __formal_append_listbuttons(node, div0, false);
  node.insertBefore(div0, descnode);  // XXX: IE fix should be done, but descnode is always non-null
}

function formal_dynamiclist_check_add_last_add_button(lst) {
  var footer = __formal_dynamiclist_locate_list_footer(lst);
  if (!footer) {
    /* broken html document, ignore */
    return;
  }

  // already has last buttons?
  for (var i = 0; footer.childNodes[i]; i++) {
    var c = footer.childNodes[i];

    var name = c.nodeName.toLowerCase();

    if (c.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
      continue;
    }

    if (name == "div"  &&  c.className == "listbuttons-last") {
      return;
    }
  }

  // no, append
  var div0 = document.createElement("div");
  div0.className = "listbuttons-last";
  __formal_append_listbuttons(lst, div0, true);
  footer.appendChild(div0);
}


/* --------------------------------------------------------------------------
 *  Radiobuttons / checkbox routines for enabling / disabling form items.
 */

function formal_set_fields_enabled_status(cssid) {
  function __set_node_status(node, enabled_state) {
    // Set input and select elements disabled state.
    var tag_name = node.tagName.toLowerCase();
    if (tag_name == "input" || tag_name == "select") {
      node.disabled = !enabled_state;
    }

    // If css class contains group or field, modify css class by
    // adding or removing disabled css class.  SELECT and INPUT
    // elements also need this class for styling with CSS1/2
    // selectors (CSS3 style input[disabled] does not work in
    // all browsers).

    // default to empty list of classes
    var classes = node.className;
    if (classes == null || classes == undefined) {
      classes = "";
    }

    if ((formal_class_has_attributes(classes, ['group', 'field']) > 0) ||   /* relevant groups */
        (tag_name == "input" || tag_name == "select")) {                    /* terminal elements */
      if (enabled_state == true) {
        classes = formal_class_remove(classes, "disabled");
      } else {
        classes = formal_class_add(classes, "disabled");
      }
    }

    // If classes becomes empty, remove from node, otherwise update
    if (classes == "") {
      node.className = null;
    } else {
      node.className = classes;
    }
  }
  
  function __disable_node(node) {
    if (node.id != undefined && node.id != null) {
        __set_node_status(node, false);
    }
    
    for( var x = 0; node.childNodes[x]; x++ ) {
      var new_node = node.childNodes[x];
      __disable_node(new_node);
    }
  }
 
  function __handle_node(node) {
    // Check if node is enabled or disabled
    if (node.id != undefined && node.id != null && field_enabled_status(node.id) == false) {
        __disable_node(node);
    }
    else {    
      // Skip undefined and null nodes.
      // XXX: More accurate handling of nodes. Field div -> css class disabled, input field -> disabled.
      if (node.id != undefined && node.id != null) {
        __set_node_status(node, true);
      }
          
      for( var x = 0; node.childNodes[x]; x++ ) {
        var new_node = node.childNodes[x];
        __handle_node(new_node);
      }
    }
  }

  // XXX: Running through all the elements is too slow. Alternatives:
  // Function is given an initial point, e.g. 'config' at form creation 
  // and group name at radiobutton click.
  __handle_node(document.getElementById(cssid));  
}

// Onclick goes through the whole dom and sets the field disabled if needed.
function formal_radio_onclick(e) {
  var targ;
  if (!e) {
    e = window.event;
  }
  if (e.target) {
    targ = e.target;
  } else if (e.srcElement) {
    targ = e.srcElement;
  }

  // Here we would like to only update related groups instead of whole form.
  // Previously we just updated the parent, but this is no longer enough
  // because not all relationships for enable/disable behavior are parent-child
  // relations.

  var id_elements = formal_cssid_split(targ.id);

  // Update parent
  formal_set_fields_enabled_status(formal_cssid_join([id_elements[0]]));
  //formal_set_fields_enabled_status(formal_cssid_join([id_elements[0],id_elements[1]]));
}

/* --------------------------------------------------------------------------
 *  Form submit enables all the elements. Disabled element values does not go
 *  to formal.
 */
function formal_enable_all_nodes() {
  function __enable_node(node) {
    if (node.disabled == true) {
      node.disabled = false;
    }
  }
  
  function __iterate_items(node) {
    __enable_node(node);
    for( var x = 0; node.childNodes[x]; x++ ) {
      __iterate_items(node.childNodes[x]);
    }
  }
  
  __iterate_items(document);
}
 
function formal_hide_all_semihidden_fields() {
  function __fixup_node(node) {
    try {
      if ((node.tagName.toLowerCase() == "input") && (formal_class_has_attribute(node.className, "semihidden"))) {
        if (node.type != "password") {
          // NB: cannot change type directly here in IE either

          if (browser_detect_ie() || browser_detect_ff()) {
            var new_node = __formal_semi_hidden_password_clone_node(node, "password");
            node.parentNode.replaceChild(new_node, node);
          } else {
            // Safari and others
            node.type = "password";
          }
        }
      }
    } catch(e) {
      ;
    }
  }

  _formal_recursive_preorder_form_node_walk(document, __fixup_node);
}

// Dynamic list elemenst has running index based on timestamp. Renumber lists
// starting from 0.
function formal_renumber_all_dynamic_lists() {
  var lists = formal_dynamiclist_get_listnames();
  for (x in lists) {
    var dyn_list = document.getElementById(lists[x]);
    if (dyn_list != null) {
      formal_dynamiclist_renumber_list(lists[x]);  
    }
  }
}

function formal_onsubmit(e) {
  try {
    // XXX: does not work in IE
    document.body.className = "submit-in-progress";
    //document.body.style.cursor = "wait";
    //this.style.cursor = "wait";
  } catch(e) {
    ;
  }
  formal_enable_all_nodes();
  formal_hide_all_semihidden_fields();
  formal_renumber_all_dynamic_lists();
  try {
    // XXX: does not work in IE
    document.body.className = "";
    //document.body.style.cursor = "default";
    //document.getElementsByTagName("body")[0].style="cursor:arrow";
    //this.style.cursor = "default";
  } catch(e) {
    ;
  }
}

/* --------------------------------------------------------------------------
 *  Context help functionality.
 */ 
 
/*
 * Shows context help item defined by cssid.
 * Assumes that context help div exists with id context-help.
 * NOTE: Duplicates context help items to the context help position and
 *       thus ID's cannot be used in context help elements.
 *       If ID's are required, context help must be moved instead of copied.  
 */ 
function formal_show_context_help(cssid) {
  var helpElement = document.getElementById(cssid);
  if (helpElement == null || helpElement == undefined)
    return;
  
  // Context element div. Should exist in every page containing context help.
  var ctxElement = document.getElementById('context-help');
  if (ctxElement == null || helpElement == undefined)
    return;
  
  // Delete existing children
  dom_remove_all_children(ctxElement);

  // Clone children and add to context help element
  for (var i = 0; helpElement.childNodes[i]; i++) {
    ctxElement.appendChild(helpElement.childNodes[i].cloneNode(true));
  }
}

/* --------------------------------------------------------------------------
 *  Formal local validation support
 */

// XXX: unimplemented
function formal_validate_set_field_state(fieldid, state) {
  myfatal("unimplemented");
}

// XXX: unimplemented
function formal_validate_field_input(fieldid, validator) {
  if (validator(fieldid)) {
    formal_validate_set_field_state(fieldid, True);
  } else {
    formal_validate_set_field_state(fieldid, False);
  }
}

/* --------------------------------------------------------------------------
 *  Formal collapsible groups
 */

function __formal_collapsible_group_get_nodes(groupid) {
  var n = document.getElementById(groupid);
  var c_summary = null;
  var c_contents = null;
  var c_controls = null;
  var c_hidden = null;

  if (n) {
    for (var i = 0; n.childNodes[i]; i++) {
      var c = n.childNodes[i];

      if (c.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
        continue;
      }

      /* See codebay.nevow.formalutils.formalutils.CollapsibleGroupFragment for details */
      if (c.className == "collapsible-group-summary") {
        c_summary = c.childNodes[0];
      } else if (c.className == "collapsible-group-contents") {
        c_contents = c.childNodes[0];
      } else if (c.className == "collapsible-group-hidden-state") {
        c_hidden = c;
      } else if (c.tagName.toLowerCase() == "legend") {
        /* label + collapse controls */

        for (var j = 0; j < c.childNodes.length; j++) {
          var t = c.childNodes[j];
          if (t.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
            continue;
          }
          if (t.className=="collapse-controls") {
            c_controls = t;
          }
        }
      }
    }
  }

  return [n, c_summary, c_contents, c_controls, c_hidden];
}

function __formal_create_collapse_controls(groupid) {
  var node = null;
  var c_controls = null;
  var tmp = __formal_collapsible_group_get_nodes(groupid);
  node = tmp[0];
  c_controls = tmp[3];

  current_collapsed = formal_collapsible_group_is_collapsed(groupid);

  __formal_create_collapse_controls_node(node, c_controls, current_collapsed);
}

function __formal_create_collapse_controls_node(node, controls_node, current_collapsed) {
  function __buttonfunc() {
    formal_collapsible_group_toggle(node.id);
  }
  function __clickhandler() {
    __buttonfunc(node); return false;
  }

  var a = document.createElement("a");
  a.href = "#";
  if (a.attachEvent) {  // IE
    a.attachEvent("onclick", __clickhandler);
  } else if (a.addEventListener) {  // FF etc
    a.addEventListener("click", __clickhandler, true);
    a.setAttribute("onclick", "return false;");
  } else {
    ;
  }

  var btn = document.createElement("img");
  if (current_collapsed) {
    btn.src = "/static/button_expand.png";
  } else {
    btn.src = "/static/button_collapse.png";
  }

  btn.width = 13;
  btn.height = 13;
  a.appendChild(btn);

  dom_remove_all_children(controls_node);
  controls_node.appendChild(a);
  controls_node.appendChild(document.createTextNode(" "));
}

function __formal_collapsible_group_set_classes(groupid, class_summary, class_contents, hidden_value) {
  var c_summary = null;
  var c_contents = null;
  var c_hidden = null;
  var tmp = __formal_collapsible_group_get_nodes(groupid);
  c_summary = tmp[1];
  c_contents = tmp[2];
  c_hidden = tmp[4];

  if (c_summary) {
    c_summary.className = class_summary;
  }
  if (c_contents) {
    c_contents.className = class_contents;
  }
  if (c_hidden) {
    c_hidden.value = hidden_value;
  }
}

function formal_collapsible_group_expand(groupid) {
  __formal_collapsible_group_set_classes(groupid, "collapsible-hide", "collapsible-show", "0");
  __formal_create_collapse_controls(groupid);
}

function formal_collapsible_group_collapse(groupid) {
  __formal_collapsible_group_set_classes(groupid, "collapsible-show", "collapsible-hide", "1");
  __formal_create_collapse_controls(groupid);
}

function formal_collapsible_group_is_collapsed(groupid) {
  var c_summary = null;
  var c_contents = null;
  var tmp = __formal_collapsible_group_get_nodes(groupid);
  c_summary = tmp[1];
  c_contents = tmp[2];

  if (c_contents.className == "collapsible-hide") {
    return true;
  }
  return false;
}

function formal_collapsible_group_is_expanded(groupid) {
  return !formal_collapsible_group_is_collapsed(groupid);
}

function formal_collapsible_group_toggle(groupid) {
  if (formal_collapsible_group_is_collapsed(groupid)) {
    formal_collapsible_group_expand(groupid);
  } else {
    formal_collapsible_group_collapse(groupid);
  }
  
  // Changing the collapse state does not cause a layout refresh
  // in IE for some mysterious reasons.  CSS has a "holly hack"
  // for all dynamically edited elements to ensure their layout
  // is updated properly when their size changes.
  //
  // For more IE info:
  //  * http://www.sitepoint.com/blogs/2005/09/01/got-layout-internet-explorers-page-layout-secrets/
  //  * http://www.communitymx.com/content/article.cfm?page=2&cid=C37E0
}

/* --------------------------------------------------------------------------
 *  Formal SemiHiddenPassword
 *
 *  NB: You cannot simply change an <input> type between 'text' and 'password'
 *  in IE; trying to do will result in a Javascript error.  Instead, we create
 *  a new DOM node, carefully copying all necessary attributes, and replace
 *  the old node with the new one.
 *
 *  Replacing the node is also tricky because onblur/onfocus events run amok
 *  when the replacement is in progress.  To prevent this, we use a global
 *  map (Object) to track active replacements and fall out of onblur/onfocus
 *  handlers if a replacement is active for that particular id already.
 *
 *  Final complication: the replacement trick does not work in Safari.  So,
 *  we special case FF and IE, and try to change the node type for the rest
 *  of the browsers.
 */

// map used to prevent recursive onblur/onfocus events during replacement
var __semihidden_replacement_active = new Object();

function __formal_semi_hidden_password_clone_node(old_node, new_type) {
  var new_node = document.createElement("input");

  new_node.type = new_type;

  // XXX: does not work in Safari (X.name should be X.setAttribute("name"...))
  if (old_node.name) new_node.name = old_node.name;
  if (old_node.value) new_node.value = old_node.value;
  if (old_node.id) new_node.id = old_node.id;
  if (old_node.className) new_node.className = old_node.className;
  if (old_node.size) new_node.size = old_node.size;
  if (old_node.tabIndex) new_node.tabIndex = old_node.tabIndex;

  new_node.onfocus = function() { return function() { formal_semi_hidden_password_show(this.id); } } ();
  new_node.onblur = function() { return function() { formal_semi_hidden_password_hide(this.id); } } ();

  return new_node;
}

function __formal_semi_hidden_password_show_ff_ie(id) {
  if (__semihidden_replacement_active[id] == "show") {
    // allow show (onfocus) if already doing one
    return true;
  } else if (__semihidden_replacement_active[id] == "hide") {
    // ignore show (onfocus) if already doing hide
    return false;
  }

  var n = document.getElementById(id);
  if (n) {
    if (n.type != "text") {
      // active, start blocking events
      __semihidden_replacement_active[id] = "show";

      var old_sel_start = null;
      var old_sel_end = null;
      try {
        var tmp = get_selection_range(n);
        old_sel_start = tmp.start;
        old_sel_end = tmp.end;
      } catch(e) {
        ;
      }

      var new_node = __formal_semi_hidden_password_clone_node(n, "text");
      n.parentNode.replaceChild(new_node, n);

      // add focus to new node; needs a delay to avoid focus loops (no first hand experience though)
      function _set_focus() {
        new_node.hasFocus=true;
        new_node.focus();
        new_node.select();  // Safari

        try {
          if (false) {
            // set cursor position based on old range
            if (old_sel_start != null && old_sel_end != null) {
              set_selection_range(new_node, old_sel_start, old_sel_end);
            }
          } else {
            // select whole text and set cursor at end; this is the preferred behavior for semi hidden passwords now
            set_selection_range(new_node, 0, new_node.value.length);
          }
        } catch(e) {
          ;
        }

        // no longer active, stop blocking events
        __semihidden_replacement_active[id] = "";
      }
      setTimeout(_set_focus, 100);
    }
  } else {
    ;
  }
  return true;
}

function __formal_semi_hidden_password_show_rest(id) {
  if (__semihidden_replacement_active[id] == "show") {
    // allow show (onfocus) if already doing one
    return true;
  } else if (__semihidden_replacement_active[id] == "hide") {
    // ignore show (onfocus) if already doing hide
    return false;
  }

  // active, start blocking events
  __semihidden_replacement_active[id] = "show";

  var n = document.getElementById(id);

  if (n) {
    // Note: this delay hack is for Safari handling
    function _delayed_type_change() {
      try {
        if (n.type != "text") { 
          n.type = "text";
          
          function _delayed_focus() {
            // XXX: this hack is needed for Safari, for some reason
            var n2 = document.getElementById(id);
            if (n2) {
              try {
                //n2.blur();
                n2.focus();
                n2.select();  // Safari
                //set_selection_range(n2, 0, n2.value.length);
              } catch(e) {
                ;
              }
            }

            // no longer active, stop blocking events
            __semihidden_replacement_active[id] = "";
          }
          setTimeout(_delayed_focus, 50);
        }
      } catch(e) {
        ;
      }
    }
    setTimeout(_delayed_type_change, 50);
  }
  return false;
}

function formal_semi_hidden_password_show(id) {
  // XXX: this detection is a bit overwide (e.g. IEmac?)
  if (browser_detect_ie() || browser_detect_ff()) {
    return __formal_semi_hidden_password_show_ff_ie(id);
  } else {
    return __formal_semi_hidden_password_show_rest(id);
  }
}

function __formal_semi_hidden_password_hide_ff_ie(id) {
  if (__semihidden_replacement_active[id] == "show") {
    // ignore hide (onblur) if already doing show
    return false;
  } else if (__semihidden_replacement_active[id] == "hide") {
    // allow hide (onblur) if already doing hide
    return true;
  }

  // active, start blocking events
  __semihidden_replacement_active[id] = "hide";

  function _callback() {
    var n = document.getElementById(id);
    if (n) {
      if (n.type != "password") {
        var new_node = __formal_semi_hidden_password_clone_node(n, "password");
        n.parentNode.replaceChild(new_node, n);
      }
    } else {
      ;
    }

    // no longer active, stop blocking events
    __semihidden_replacement_active[id] = "";
  }

  if (true) {
    // Call later so normal browser stuff for 'exiting a field' works;
    // in particular.  This is needed at least for FF 1.5.
    setTimeout(_callback, 10);
    return true;
  } else {
    _callback();
    return true;
  }
}

function __formal_semi_hidden_password_hide_rest(id) {
  if (__semihidden_replacement_active[id] == "show") {
    // ignore hide (onblur) if already doing show
    return false;
  } else if (__semihidden_replacement_active[id] == "hide") {
    // allow hide (onblur) if already doing hide
    return true;
  }

  // active, start blocking events
  __semihidden_replacement_active[id] = "hide";

  function _delayed_type_change() {
    var n = document.getElementById(id);
    if (n) {
      try {
        if (n.type != "password") {
          n.type = "password";
        }
      } catch(e) {
        ;
      }
    }

    // no longer active, stop blocking events
    __semihidden_replacement_active[id] = "";
  }
  setTimeout(_delayed_type_change, 10);

  return true;
}

function formal_semi_hidden_password_hide(id) {
  // XXX: this detection is a bit overwide (e.g. IEmac?)
  if (browser_detect_ie() || browser_detect_ff()) {
    return __formal_semi_hidden_password_hide_ff_ie(id);
  } else {
    return __formal_semi_hidden_password_hide_rest(id);
  }
}

/* --------------------------------------------------------------------------
 *  Formal HiddenPassword
 */

function _formal_hidden_password_find_capslock_span(n) {
  var capslock_span = null;
  var parent = n.parentNode;

  for (var i = 0; parent.childNodes[i]; i++) {
    var t = parent.childNodes[i];
    if ((t.nodeType == JS_DOM_NODE_TYPE_ELEMENT_NODE) &&
        (t.tagName.toLowerCase() == "span") &&
        (t.className == "capslock-warning")) {
      capslock_span = t;
      break;
    }
  }

  return capslock_span;
}

function formal_hidden_password_capslock_show(id) {
  try {
    var n = document.getElementById(id);
    if (n) {
      var capslock_span = _formal_hidden_password_find_capslock_span(n);
      if (capslock_span) {
        capslock_span.style.visibility = "visible";
      }
    }
  } catch(e) {
    ;
  }
}

function formal_hidden_password_capslock_hide(id) {
  try {
    var n = document.getElementById(id);
    if (n) {
      var capslock_span = _formal_hidden_password_find_capslock_span(n);
      if (capslock_span) {
        capslock_span.style.visibility = "hidden";
      }
    }
  } catch(e) {
    ;
  }
}

function formal_hidden_password_capslock_test(id, event) {
  try {
    var n = document.getElementById(id);
    if (n) {
      if (test_caps_lock(event)) {
        formal_hidden_password_capslock_show(id);
      } else {
        formal_hidden_password_capslock_hide(id);
      }
    }
  } catch(e) {
    ;
  }
}

/* --------------------------------------------------------------------------
 *  Adorning formal elements.
 */
function __formal_adorn_dynamic_lists() {
  // Adorn dynamic lists
  function __adorn_list(cssid) {
    var lst = document.getElementById(cssid);
    if (lst == null || lst == undefined) {
      return;
    }
    
    var cont = __formal_dynamiclist_locate_list_contents(lst);

    for (var i = 0; cont.childNodes[i]; i++) {
      var c = cont.childNodes[i];
      formal_dynamiclist_check_add_buttons(c);
    } 
   
    formal_dynamiclist_check_add_last_add_button(lst);
  }
  
  var lists = formal_dynamiclist_get_listnames();
  for (x in lists) {  // indexes!
    var listname = lists[x];
    __adorn_list(listname);
  }  
}

function __formal_adorn_radiobuttons() {
  // Adorn radiobuttons
  function __adorn_radiobutton(cssid) {
    // Add onclick handler.
    var rbutton = document.getElementById(cssid);
    if (rbutton == null || rbutton == undefined) {
      return;
    }
    
    if (rbutton.attachEvent) {  // IE
      rbutton.attachEvent("onclick", formal_radio_onclick);
    } else if (rbutton.addEventListener) {  // FF etc
      rbutton.addEventListener("click", formal_radio_onclick, false);
    }
  }
  
  var radiobuttons = formal_get_radiobuttons_names();
  for (r in radiobuttons) {
    __adorn_radiobutton(radiobuttons[r]);
  } 
   
  /* Find dynamic lists radiobuttons. Only list index (=group name) can be 
   * a wildchar ='*'. Replaces wildchars with numbers as long as nodes are found
   * from the document.
   */
  var dynamic_rbuttons = formal_get_dynamic_radiobuttons_names();
  
  for (dr in dynamic_rbuttons) {
    var dr_button = dynamic_rbuttons[dr]; // "xxx.yyy.*.zzz.0"
    var key_parts = dr_button.split('*'); // ["xxx.yyy.", ".zzz.0"]
    var index = 0;
    var temp_key = key_parts[0] + index + key_parts[1]; // "xxx.yyy.0.zzz.0"
    var node = document.getElementById(temp_key);
    
    while (node != null && node != undefined) {
      __adorn_radiobutton(temp_key);
      index = index + 1;
      temp_key = key_parts[0] + index + key_parts[1];
      node = document.getElementById(temp_key);
    }
  }
}

function __formal_adorn_initial_enable_states() {
  // Set the fields initial enabled/disabled state.
  // Finding out the correct form speeds (hopefully) up a bit disabling.
  // XXX: the form list must be updated.
  var form_name = "";
  var forms = formal_get_form_names();
  for (x in forms) {
    var form = document.getElementById(forms[x]);
    if (form != null && form != undefined) {
      formal_set_fields_enabled_status(forms[x]);
      break;
    }
  }  
}

function __formal_adorn_forms() {
  // Adorn forms. Submit enables all the fields and renumbers dynamic lists.
  function __adorn_form_submit(cssid) {
    // Add onclick handler.
    var form = document.getElementById(cssid);
    if (form == null || form == undefined) {
      return;
    }
    
    if (form.attachEvent) {  // IE
      form.attachEvent("onsubmit", formal_onsubmit);
    } else if (form.addEventListener) {  // FF etc
      form.addEventListener("submit", formal_onsubmit, false);
    }    
  }

  function __recursive_form_walk(node) {
    // if node is not a valid DOM node, skip
    if ((node == null) || (node == undefined) || (node.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE)) {
      return false;
    }

    // determine if children or our node has an error
    var has_errors = formal_class_has_attribute(node.className, "error");
    var has_child_errors = false;
    for (var i = 0; node.childNodes[i]; i++) {
      var t = node.childNodes[i];
      if (t.nodeType != JS_DOM_NODE_TYPE_ELEMENT_NODE) {
        continue;
      }
      if (__recursive_form_walk(t)) {
        has_child_errors = true;
      }
    }

    // if node is a group, mark 'child-error' class if necessary
    if (formal_class_has_attribute(node.className, "group")) {
      if (has_child_errors) {
        node.className = formal_class_add(node.className, "child-error");
      } else {
        ;
      }
    }

    return has_child_errors || has_errors;
  }

  // Propagate child 'error' classes to all relevant parents 
  // (groups and dynamic lists) 'child-error' classes
  function __adorn_form_propagate_child_errors(cssid) {
    var form = document.getElementById(cssid);
    if (form == null || form == undefined) {
      return;
    }

    __recursive_form_walk(form);
  }

  var forms = formal_get_form_names();
  for (f in forms) {
    __adorn_form_submit(forms[f]);
    __adorn_form_propagate_child_errors(forms[f]);
  }
}

function __formal_adorn_default_context_help() {
  // Set pages default context help visible.
  formal_show_context_help('ctx-page');
}

function __formal_adorn_collapsible_groups() {
  var nodes = get_elements_by_class_name('collapsible-group');
  for (var i=0; i < nodes.length; i++) {
    var node = nodes[i];

    __formal_create_collapse_controls(node.id);
  }
}

function formal_adorn_server_side_elements() {
  __formal_adorn_dynamic_lists();
  __formal_adorn_radiobuttons();
  __formal_adorn_initial_enable_states();
  __formal_adorn_forms();
  __formal_adorn_default_context_help();
  __formal_adorn_collapsible_groups();
}

/* --------------------------------------------------------------------------
 *  Formal onload initialization
 */

// adorn server side elements when body loads
function formal_body_onload_init() {
  // add server side elements with buttons, actions, etc
  formal_adorn_server_side_elements();
}

