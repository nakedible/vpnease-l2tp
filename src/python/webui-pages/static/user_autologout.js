/*
 *  Automatic (optional) logout for user pages
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 *
 */

var USERPAGE_GLOBAL_TIMEOUT = 30*60*1000;

function _global_timeout_timer() {
  window.location = global_timeout_uri;
}

function launch_global_timeout_timer(timeout) {
  var timer = setTimeout(_global_timeout_timer, timeout);
}

addDOMLoadEvent(function() {
		  launch_global_timeout_timer(USERPAGE_GLOBAL_TIMEOUT);
		})
