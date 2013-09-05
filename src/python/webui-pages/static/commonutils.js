/*
 *  Common Javascript helpers.  Loading this file should have no side-effects
 *  on any supported browser.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 */

/* ------------------------------------------------------------------------ */

/* http://www.howtocreate.co.uk/tutorials/javascript/domstructure */
/* http://www.zytrax.com/tech/dom/nodetype.html */
var JS_DOM_NODE_TYPE_ELEMENT_NODE = 1;
var JS_DOM_NODE_TYPE_ATTRIBUTE_NODE = 2;
var JS_DOM_NODE_TYPE_TEXT_NODE = 3;  // or undefined
var JS_DOM_NODE_TYPE_CDATA_SECTION_NODE = 4;
var JS_DOM_NODE_TYPE_ENTITY_REFERENCE_NODE = 5;
var JS_DOM_NODE_TYPE_ENTITY_NODE = 6;
var JS_DOM_NODE_TYPE_PROCESSING_INSTRUCTION_NODE = 7;
var JS_DOM_NODE_TYPE_COMMENT_NODE = 8;
var JS_DOM_NODE_TYPE_DOCUMENT_NODE = 9;
var JS_DOM_NODE_TYPE_DOCUMENT_TYPE_NODE = 10;
var JS_DOM_NODE_TYPE_DOCUMENT_FRAGMENT_NODE = 11;
var JS_DOM_NODE_TYPE_NOTATION_NODE = 12;

/* http://www.w3.org/TR/html4/interact/scripts.html#h-18.2.3 */
var HTML4_INTRINSIC_JS_EVENTS = [ 'onload', 'onunload', 'onclick', 'ondblclick',
                                  'onmousedown', 'onmouseup', 'onmouseover', 'onmousemove',
                                  'onmouseout', 'onfocus', 'onblur', 'onkeypress',
                                  'onkeydown', 'onkeyup', 'onsubmit', 'onreset',
                                  'onselect', 'onchange' ];

// show debug message (if debug enabled)
var debug_enabled = true;
function mydebug(str) {
  if (debug_enabled) {
    alert("DEBUG: " + str);
  }
}

// show fatal error
function myfatal(str) {
  alert("FATAL: " + str);
}

// check whether array contains a specific element
function array_contains(arr, elem) {
  for (var x in arr) {  // NB: loops through INDICES
    var arrelem = arr[x];
    if (arrelem == elem) {
      return true;
    }
  }
  return false;
}

// check that reference is non-null and defined
function check_valid_ref(r) {
  if (r == null || r == undefined) {
    myfatal("check_valid_ref failed (" + r + ")");
  }
}

// blocking sleep - DEBUG ONLY
function mysleep(msecs) {
  var done = new Date(new Date().getTime() + msecs);

  while (new Date() < done) {
  }
}

// case insensitive attr getter
function my_get_attribute(node, aname) {
  var lower = aname.toLowerCase();
  var upper = aname.toUpperCase();
  var r = node.getAttribute(aname);
  if (r != null) {
    return r;
  }
  r = node.getAttribute(lower);
  if (r != null) {
    return r;
  }
  r = node.getAttribute(upper);
  if (r != null) {
    return r;
  }
  return null;
}

// find all nodes with a specific class name (class contains supplied string)
function get_elements_by_class_name(classname, node) {
  if(!node) node = document.getElementsByTagName("body")[0];

  var res = [];
  // var re = new RegExp('\\b' + classname + '\\b');   // if class='my-foo-class', would match 'my-foo' with the classname...
  var re = new RegExp('(\\s+|^)' + classname + '(\\s+|$)');
  var all_nodes = node.getElementsByTagName("*");
  var max = all_nodes.length;
  for (var i=0; i < max; i++) {
    if(re.test(all_nodes[i].className)) {
      res.push(all_nodes[i]);
    }
  }
  return res;
}

function dom_remove_all_children(node) {
  if (node == undefined && node == null) {
    return;
  }

  while (node.hasChildNodes()) {
    node.removeChild(node.firstChild);
  }
}

/*  
*   Returns a running index.
*   Index starts from timestamp in order to prevent usage of same index in
*   two following pages. Old pages javascript might in some cases try to manipulate
*   new pages DOM (timers).
*/
var _currIndex = parseInt(new Date().getTime()) % 1000000000;
function get_running_index() {
  _currIndex++;
  return _currIndex;
} 

/* ------------------------------------------------------------------------ */

/* From: http://www.thefutureoftheweb.com/blog/2006/6/adddomloadevent */

/* --- BEGIN --- */
/*
 * (c)2006 Dean Edwards/Matthias Miller/John Resig
 * Special thanks to Dan Webb's domready.js Prototype extension
 * and Simon Willison's addLoadEvent
 *
 * For more info, see:
 * http://dean.edwards.name/weblog/2006/06/again/
 * http://www.vivabit.com/bollocks/2006/06/21/a-dom-ready-extension-for-prototype
 * http://simon.incutio.com/archive/2004/05/26/addLoadEvent
 * 
 * Thrown together by Jesse Skinner (http://www.thefutureoftheweb.com/)
 *
 *
 * To use: call addDOMLoadEvent one or more times with functions, ie:
 *
 *    function something() {
 *       // do something
 *    }
 *    addDOMLoadEvent(something);
 *
 *    addDOMLoadEvent(function() {
 *        // do other stuff
 *    });
 *
 */
 
function addDOMLoadEvent(func) {
  if (!window.__load_events) {
    var init = function () {
      // quit if this function has already been called
      if (arguments.callee.done) return;
      
      // flag this function so we don't do the same thing twice
      arguments.callee.done = true;
      
      // kill the timer
      if (window.__load_timer) {
        clearInterval(window.__load_timer);
        window.__load_timer = null;
      }
          
      // execute each function in the stack in the order they were added
      for (var i=0;i < window.__load_events.length;i++) {
        window.__load_events[i]();
      }
      window.__load_events = null;
    };
   
    // for Mozilla/Opera9
    if (document.addEventListener) {
      document.addEventListener("DOMContentLoaded", init, false);
    }
      
    // for Internet Explorer
    /*@cc_on @*/
    /*@if (@_win32)
          document.write("<scr"+"ipt id=__ie_onload defer src=//0><\/scr"+"ipt>");
          var script = document.getElementById("__ie_onload");
          script.onreadystatechange = function() {
              if (this.readyState == "complete") {
                  init(); // call the onload handler
              }
          };
          /*@end @*/
      
    // for Safari
    if (/WebKit/i.test(navigator.userAgent)) { // sniff
      window.__load_timer = setInterval(function() {
                                          if (/loaded|complete/.test(document.readyState)) {
                                            init(); // call the onload handler
                                          }
                                        }, 10);
    }
      
    // for other browsers
    window.onload = init;
      
    // create event function stack
    window.__load_events = [];
  }
   
  // add function to event stack
  window.__load_events.push(func);
}
/* --- END --- */

/*
*   Adds a function to window unload event. Adding functions trought this helper
*   function allows setting multiple function calls to window unload event.
*/
function add_window_unload_event(func) {
  // Create body unload event function stack.
  if (!window.__window_unload_events) {
    // Init function stack.
    window.__window_unload_events = [];
    // Iterates trough all the functions added to body unload event.
    window.onunload = function() {
      for (var i=0; i<window.__window_unload_events.length; i++) {
        window.__window_unload_events[i]();
      }
      window.__window_unload_events = null;
    }
  }
  
  // Add function to event stack.
  window.__window_unload_events.push(func);
}

/* ------------------------------------------------------------------------ */

/* Based on: http://www.howtocreate.co.uk/emails/AndyBrook.html */

function test_caps_lock(e) {
  if(!e) {
    e = window.event;
  }

  if(!e) {
    return false;
  }

  // what (case sensitive in good browsers) key was pressed
  var theKey = e.which ? e.which : ( e.keyCode ? e.keyCode :
                                     ( e.charCode ? e.charCode : 0 ) );

  // was the shift key was pressed?
  var theShift = e.shiftKey || ( e.modifiers && ( e.modifiers & 4 ) ); // bitWise AND

  // if upper case, check if shift is not pressed. if lower case,
  // check if shift is pressed
  if( ( theKey > 64 && theKey < 91 && !theShift ) ||
      ( theKey > 96 && theKey < 123 && theShift ) ) {
    return true;
  }
  return false;
}

/* ------------------------------------------------------------------------ */

/* A hybrid of various approaches on the web */

function set_selection_range(node, start, end) {
  // range sanity
  if (start == null || start == undefined) {
    start = 0;
  }
  if (end == null || end == undefined) {
    end = start;
  }

  // browser specific setting of selection range
  if ("selectionStart" in node) {
    // Firefox & Safari
    node.setSelectionRange(start, end);
    node.focus();
  } else if (document.selection) {
    // IE (Windows)
    var r = node.createTextRange();
    r.collapse(true);
    r.moveStart("character", start);
    r.moveEnd("character", end - start);  // num chars
    r.select();
  }
}

// Only works for INPUT fields
function get_selection_range(node) {
  var res = {};
  res['start'] = null;
  res['end'] = null;

  if ("selectionStart" in node) {
    // Firefox
    res['start'] = node.selectionStart;
    res['end'] = node.selectionEnd;
  } else if (document.selection) {
    // IE (Windows)
    var r = document.selection.createRange();
    if (r.parentElement() == node) {
      var rs = r.duplicate();
      rs.moveEnd("textedit", 1);
      var re = r.duplicate();
      re.moveStart("textedit", -1);
      res['start'] = node.value.length - rs.text.length;
      res['end'] = re.text.length;
    }
  }

  return res;
}

/* -------------------------------------------------------------------------- */

/* Browser detection: http://www.quirksmode.org/js/detect.html */

/*
 * QuirksMode.org is a free website that gives browser compatibility information
 * and rather a lot of copy-pastable scripts. I will not charge you for the use of
 * this website in any way; no fees, no advertisements, no hidden costs.
 */

var BrowserDetect = {
  init: function () {
    this.browser = this.searchString(this.dataBrowser) || "An unknown browser";
    this.version = this.searchVersion(navigator.userAgent)
    || this.searchVersion(navigator.appVersion)
    || "an unknown version";
    this.OS = this.searchString(this.dataOS) || "an unknown OS";
  },
  searchString: function (data) {
    for (var i=0;i<data.length;i++){
      var dataString = data[i].string;
      var dataProp = data[i].prop;
      this.versionSearchString = data[i].versionSearch || data[i].identity;
      if (dataString) {
        if (dataString.indexOf(data[i].subString) != -1)
          return data[i].identity;
      }
      else if (dataProp)
        return data[i].identity;
    }
  },
  searchVersion: function (dataString) {
    var index = dataString.indexOf(this.versionSearchString);
    if (index == -1) return;
    return parseFloat(dataString.substring(index+this.versionSearchString.length+1));
  },
  dataBrowser: [
  { string: navigator.userAgent,
    subString: "OmniWeb",
    versionSearch: "OmniWeb/",
    identity: "OmniWeb"
  },
  {
    string: navigator.vendor,
    subString: "Apple",
    identity: "Safari"
  },
  {
    prop: window.opera,
    identity: "Opera"
  },
  {
    string: navigator.vendor,
    subString: "iCab",
    identity: "iCab"
  },
  {
    string: navigator.vendor,
    subString: "KDE",
    identity: "Konqueror"
  },
  {
    string: navigator.userAgent,
    subString: "Firefox",
    identity: "Firefox"
  },
  {
    string: navigator.vendor,
    subString: "Camino",
    identity: "Camino"
  },
  {// for newer Netscapes (6+)
    string: navigator.userAgent,
    subString: "Netscape",
    identity: "Netscape"
  },
  {
    string: navigator.userAgent,
    subString: "MSIE",
    identity: "Explorer",
    versionSearch: "MSIE"
  },
  {
    string: navigator.userAgent,
    subString: "Gecko",
    identity: "Mozilla",
    versionSearch: "rv"
  },
  { // for older Netscapes (4-)
    string: navigator.userAgent,
    subString: "Mozilla",
    identity: "Netscape",
    versionSearch: "Mozilla"
  }
  ],
  dataOS : [
  {
    string: navigator.platform,
    subString: "Win",
    identity: "Windows"
  },
  {
    string: navigator.platform,
    subString: "Mac",
    identity: "Mac"
  },
  {
    string: navigator.platform,
    subString: "Linux",
    identity: "Linux"
  }
  ]

};

var _browser_detect = false;
function browser_detect() {
  if (!_browser_detect) {
    _browser_detect = true;
    BrowserDetect.init();
  }
  return BrowserDetect;
}

// XXX: wide detection
function browser_detect_ie() {
  var bd = browser_detect();
  return bd.browser == "Explorer";
}

// XXX: wide detection
function browser_detect_ff() {
  var bd = browser_detect();
  return (bd.browser == "Firefox") || (bd.browser == "Mozilla");
}
