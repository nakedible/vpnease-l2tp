"""Gnome helpers.
"""
__docformat__ = 'epytext en'
import os, sys, string, textwrap

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand

run_command = runcommand.run_command

_log = logger.get('l2tpserver.gnomehelpers')

def show_notification(title, content, timeout=None, critical=False):
    """Show notification through notification-daemon.

    The requirements for sending successful notifications using libnotify
    are: (1) must have DBUS_SESSION_BUS_ADDRESS environment variable set
    correctly, (2) must have correct uid.  In practice, 'sudo -u admin'
    ensures (2), but (1) needs nasty workarounds.  Here we just assume that
    someone has kindly written the Dbus information to a file that we use.

    Note that DISPLAY is not required for notifications.
    """

    FOREVER = 1000000000  # million seconds

    # construct a nice environment
    try:
        myenv = dict(os.environ)
        myenv['HOME'] = '/home/%s' % constants.ADMIN_USER_NAME   # just in case
        f = open(constants.DBUS_SESSION_BUS_ADDRESS_FILE, 'rb')
        t = f.readlines()[0]
        t = t.strip()
        myenv['DBUS_SESSION_BUS_ADDRESS'] = t
    except:
        _log.exception('failed to construct an environment for notification')
    _log.debug('notify environment: %s' % myenv)
    
    # XXX: this won't work now because we would need to 'sudo' this.
    # No need to fix now, as we use notifytool anyway.
    def _try_with_pynotify():
        import pynotify
        pynotify.init("%s Notification" % constants.PRODUCT_NAME)
        n = pynotify.Notification(title, content)
        if critical:
            n.set_urgency(pynotify.URGENCY_CRITICAL)
        else:
            n.set_urgency(pynotify.URGENCY_NORMAL)
        n.set_category("device")  # XXX: correct category? maybe not, but seems to work..
        if timeout is not None:
            n.set_timeout(int(timeout))
        else:
            n.set_timeout(int(FOREVER))
        if not n.show():
            _log.warning("could not show notification, show() failed")

    def _try_with_notifytool():
        if os.path.exists(constants.CMD_NOTIFYTOOL):
            urg = None
            if critical:
                urg = 'CRITICAL'
            else:
                urg = 'NORMAL'

            tout = None
            if timeout is not None:
                tout = str(int(timeout))
            else:
                tout = str(int(FOREVER))

            # must run using sudo
            run_command([constants.CMD_SUDO,
                         '-u', constants.ADMIN_USER_NAME,
                         constants.CMD_NOTIFYTOOL,
                         str(title),     # summary
                         str(content),   # body
                         "icon",         # icon
                         tout,           # timeout (ms)
                         "device",       # category
                         urg             # urgency
                         ], env=myenv, retval=runcommand.FAIL)
        else:
            raise Exception("no notifytool in %s" % constants.CMD_NOTIFYTOOL)
        
    _log.info("showing notification: %s: %s, timeout %s" % (title, content, timeout))

    try:
        _try_with_notifytool()
        return
    except:
        _log.exception('failed to show notification with notifytool')
   
    _log.info("cannot use notifytool, trying pynotify")

    try:
        _try_with_pynotify()
        return
    except:
        _log.exception('failed to show notification with pynotify')
     
    _log.warning("failed to show notification")
