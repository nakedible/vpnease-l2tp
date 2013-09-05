"""Global objects required by testclient."""

from codebay.l2tpserver.testclient import systempoller

_syspoller = None

def get_syspoller():
    global _syspoller
    if _syspoller is None:
        _syspoller = systempoller.SystemPoller()
    return _syspoller

