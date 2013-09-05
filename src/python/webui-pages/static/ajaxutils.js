/*
 *  AJAX support stuff.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 *
 *  See:
 *    - http://www.w3.org/TR/XMLHttpRequest/
 *    
 *  Reponse states:
 *  XML_HTTP_REQUEST_STATE_NOT_INITIALIZED = 0;
 *  XML_HTTP_REQUEST_STATE_INITIALIZED = 1;
 *  XML_HTTP_REQUEST_STATE_SENT = 2;
 *  XML_HTTP_REQUEST_STATE_IN_PROCESS = 3;
 *  XML_HTTP_REQUEST_STATE_COMPLETE = 4;
 *         
 */

// Internal globals. Object prevents name conflicts.
// xhr objects contains xhr, fail_count, delayed_request_timer and max_wait_timer
var _ajax_utils = new Object();
_ajax_utils.xhr1 = null;
_ajax_utils.xhr2 = null;
_ajax_utils.page_unload = false;
  
   
/*
 * Abort request.
 *
 * Set xhr message abort to true in order to prevent message ready
 * handling (and thus sending potential new message).
 */
function abort_request(xhr) {
  if (xhr.request == null) {
    return;
  }

  xhr.request_aborted = true;
  xhr.request.abort();
  xhr.request_aborted = false;
}   
   
/*
 *  Set XmlHttpRequest object to _ajax_utils.xhr, compatible with most browsers.
 *  Returns false, if object is null and creation failed.
 */
function cb_get_xml_http_request() {
  if (typeof XMLHttpRequest != "undefined") {
    return new XMLHttpRequest();
  } else if (window.ActiveXObject) {
    // 6.0 comes with vista. 3.0 is MS recommended for fallback.
    var axVersions = ["MSXML2.XMLHttp.6.0", "MSXML2.XMLHttp.3.0"];
  
    for (var i=0; i < axVersions.length; i++) {
      try {
        var axo = new ActiveXObject(axVersions[i]);
        return axo;
      } catch(e) {
        ;
      }
    }
  }
  
  return null;  
} 
 
// Initialize xhr object. Return null if new object could not be created.
function init_xhr_object(uri, func, max_timeout, message_interval) {
  if (_ajax_utils.xhr1 != null && _ajax_utils.xhr2 != null) {
    //alert("Both xhr objects already in use.");
    return null;  
  }
  
  var new_xhr = new Object();
  var xhr_identity = null;
  
  if (_ajax_utils.xhr1 == null) {
    _ajax_utils.xhr1 = new_xhr;
    xhr_identity = "xhr1";
  } else if (_ajax_utils.xhr2 == null) {
    _ajax_utils.xhr2 = new_xhr;
    xhr_identity = "xhr2";
  } else {
    //alert("xhr1 and xhr2 not null.");
    return null;
  }
  
  new_xhr.identifier = xhr_identity;
  new_xhr.request = cb_get_xml_http_request();
  if (new_xhr.request == null) {
    //alert("New request creation failed.");
    new_xhr = null;
    return null;
  }
  
  new_xhr.request_aborted = false;
  new_xhr.fail_count = 0;
  new_xhr.message_interval_timer = null;
  new_xhr.max_wait_timer = null;    
  new_xhr.uri = uri;
  new_xhr.func = func;
  new_xhr.max_timeout = max_timeout;
  new_xhr.message_interval = message_interval;

  // If object was created, add clearance to window onunload. IE requirement.
  add_window_unload_event(function() {
      // Mark the page unload. Prevents new requests after abort.
      _ajax_utils.page_unload = true;
      if (new_xhr.request != null) {
        abort_request(new_xhr);
      }
      if (new_xhr.message_interval_timer != null) {
        clearTimeout(new_xhr.message_interval_timer);
        new_xhr.message_interval_timer = null;
      }
      if (new_xhr.max_wait_timer != null) {
        clearTimeout(new_xhr.max_wait_timer);
        new_xhr.max_wait_timer = null;
      }
    })

  return new_xhr;
}  

function cb_ajax_supported() {
  return (cb_get_xml_http_request() != null);
}

/*
 * Starts creating AJAX requests with a message_interval between requests and maximum timeout. 
 * After maximum timeout, or a response a new request is created. Errors increase
 * delay between requests.
 */ 
function _continuous_ajax_request_with_delay(xhr) {  
  function _onreadystatechange() {
    // Readystates:
    // 0 = uninitialized
    // 1 = open
    // 2 = sent
    // 3 = receiving
    // 4 = loaded
    if ((xhr.request.readyState == 0) || (xhr.request.readyState == 1) || 
	(xhr.request.readyState == 2) || (xhr.request.readyState == 3)) {
      // We do not care about states 0-3, they are intermediate, expected states
      ;
    } else if (xhr.request.readyState == 4) {
      // Clear max wait timer.
      if (xhr.max_wait_timer != null) {
	clearTimeout(xhr.max_wait_timer);
	xhr.max_wait_timer = null;
      }
        
      // If aborted request, ignore result.
      if (xhr.request_aborted) {
	return;
      }
        
      try {
	try {
	  // 200 = status ready.
	  // 304 = from cache (currently not included).
	  // XXX: If cached requests are also allowed, add 304 to successful status list.
	  if (xhr.request.status == 200) {
	    xhr.fail_count = 0;
	    xhr.func(xhr.request.responseText, xhr.request);  
	  } else {
	    // Status 0 means aborted message at least in IE. 
	    // Fail count is not increased or new message sent when request is aborted.
	    if (xhr.request.status != 0) {
	      xhr.fail_count += 1;
	    }
	  } 
	} catch(e) {
	  // Note: Firefox abort causes exception.  
	  ;
	}
        
	// Send new request.
	_new_request(xhr);
      } catch(e) {
	  ;
    //alert("New request failed.");
      }   
    } else {
      // XXX: here we don't want to cancel and resend because the real
      // response might be coming later.
      ;
      //alert("Unknown request status received.");
    }
  }

  if (xhr.request == null || _ajax_utils.page_unload) {
    return;
  }
  
  try {
    // Open must be done before setting onreadystatechange. This enabled XMLRequest reuse
    // in IE.
    xhr.request.open("GET", xhr.uri, true);
    xhr.request.onreadystatechange = _onreadystatechange;        
    xhr.request.send(null);
     
    if (xhr.max_wait_timer != null) {
      clear_timeout(xhr.max_wait_timer);
      xhr.max_wait_timer = null;
    } 
    
    // If a request is not received in timeout given, the request is aborted and
    // a new request is sent. Callback function is called with a null response.
    xhr.max_wait_timer = setTimeout(function() {
        xhr.max_wait_timer = null;
        abort_request(xhr);
        xhr.func(null, xhr.request);
        // XXX: _new_request would cause message_interval length extra delay.
        _new_request(xhr);  
      }, xhr.max_timeout);
  } catch(e) {
    // alert("Exception in message creation.");
    xhr.fail_count += 1;
    // XXX Check that request can be aborted even if it has not been created.
    // Currently inside try-catch -> should not cause problems.
    try {
      abort_request(xhr);
    } catch(e) {
      ;
    }
    _new_request(xhr);  
  }
}

/*
 * uri = request uri, func = callback function, max_timeout is the maximum wait
 * time for a response (ms), message_interval = delay between a successful result
 * and a new request.
 */
function create_continuous_ajax_request_with_delay(uri, func, max_timeout, message_interval) {
  var xhr = init_xhr_object(uri, func, max_timeout, message_interval);
  if (xhr == null) {
    //alert("Xhr object is null.");
    return;
  }
  _continuous_ajax_request_with_delay(xhr);
}

function create_continuous_ajax_request(uri, func, timeout) {
  create_continuous_ajax_request_with_delay(uri, func, timeout, 0);
}

// Sends delayed request. Delay depends from the number of sequential errors and
// from the given message delay.
function _new_request(xhr) {
  var SMALL_DELAY = 5 * 1000;
  var SMALL_DELAY_COUNT = 5;
  var LONG_DELAY = 15 * 1000;
  var LONG_DELAY_COUNT = 10;
  var delay = xhr.message_interval;
   
  // determine delay based on fail count
  if (xhr.fail_count >= LONG_DELAY_COUNT) {
    delay = LONG_DELAY;
  } else if (xhr.fail_count >= SMALL_DELAY_COUNT) {
    delay = SMALL_DELAY;
  } else {
    ;
  }

  // ensure it is at least as large as user-specified interval
  if (delay < xhr.message_interval) {
    delay = xhr.message_interval;
  }

  // sanity to prevent busy loop
  if (delay < 50) {
    delay = 50;
  }
    
  xhr.message_interval_timer = setTimeout(function() {
        xhr.delayed_request_timer = null;
        _continuous_ajax_request_with_delay(xhr);
        }, delay); 
}

