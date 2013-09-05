/*
 *  Ajax update code for Live CD pages.
 *
 *  (C) Copyright Codebay Oy, 2006-2008.  All Rights Reserved.
 */

function _update_progress(resp, xhr) {
  try {
    /*
     *  Resp is e.g.  (or null if timeout / other error)
     *    in-progress   (one of: in-progress, failure, success)
     *    (99%)
     *    [Formatting media]
     *    99.4          (raw percents)
     *
     *  We detect if install is complete and redirect.
     *
     */
    var t = resp.split('\n');
    var n = null;
    var st = t[0];
    var p_text = t[1];
    var p_act = t[2];
    var p_pct = t[3];

    try {
      n = document.getElementById("progress-percentage");
      if(n) {
        var pct_text = parseInt(p_pct);
        dom_remove_all_children(n);
        n.appendChild(document.createTextNode("" + pct_text + "%"));
      }
    } catch(e) {
      ;
    }

    try {
      n = document.getElementById("progress-image");
      if(n) {
        var pix_width = parseInt(parseFloat(p_pct) / 100.0 * 300.0);
        n.width = pix_width;
      }
    } catch(e) {
      ;
    }
    
    if (st == 'in-progress') {
      ;
    } else if (st == 'success') {
      window.location = _livecd_ajax_success_uri;
    } else {
      window.location = _livecd_ajax_failure_uri;
    }
  } catch(e) {
    ;
  }

  try {
    _launch_update_timer();
  } catch(e) {
    /* may fail when page is unloading */
    ;
  }
  
  // Message is delayed 2000 ms, so do not increase delay with errors in update.
  return true; 
}

addDOMLoadEvent(function() {
                  if(cb_ajax_supported()) {
                    create_continuous_ajax_request_with_delay(_livecd_ajax_update_uri, _update_progress, 10000, 2000)
                  } else {
                    alert('Missing AJAX support!')
                  }
                })
