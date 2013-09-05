"""Testclient locking functionality."""

import os, time

_WHACK_LOCK_FILE = '/tmp/whacklock.bin'
_L2TPCONFIG_LOCK_FILE = '/tmp/l2tpconfiglock.bin'

_whack_fd = None
_l2tpconfig_fd = None

def _acquire(fname, fdnow):
#   print "*** acquire: fname %s (fd %s) ***" % (fname, fdnow)
    
    if fdnow is not None:
        raise Exception('lock already taken, bug in your code')

    fd = None
    while fd is None:
        try:
            fd = os.open(fname, os.O_CREAT | os.O_EXCL)
        except:
            pass

        time.sleep(1)

    return fd

def _release(fname, fdnow):
#   print "*** release: fname %s (fd %s) ***" % (fname, fdnow)

    if fdnow is None:
        raise Exception('release without lock fd, bug in your code')

    os.close(fdnow)
    os.unlink(fname)
    return None

def cleanup():
    try:
        os.unlink(_WHACK_LOCK_FILE)
    except:
        pass
    try:
        os.unlink(_L2TPCONFIG_LOCK_FILE)
    except:
        pass
    
def whack_lock_acquire():
    global _whack_fd
    _whack_fd = _acquire(_WHACK_LOCK_FILE, _whack_fd)
        
def whack_lock_release():
    global _whack_fd
    _whack_fd = _release(_WHACK_LOCK_FILE, _whack_fd)

def l2tpconfig_lock_acquire():
    global _l2tpconfig_fd
    _l2tpconfig_fd = _acquire(_L2TPCONFIG_LOCK_FILE, _l2tpconfig_fd)

def l2tpconfig_lock_release():
    global _l2tpconfig_fd
    _l2tpconfig_fd = _release(_L2TPCONFIG_LOCK_FILE, _l2tpconfig_fd)
