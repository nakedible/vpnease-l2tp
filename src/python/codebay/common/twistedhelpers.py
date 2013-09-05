from twisted.internet import defer, reactor

def timeoutDefer(deferred, timeout):
    d = defer.Deferred()
    timeoutCall = reactor.callLater(timeout, defer.timeout, d)
    def _cb(v):
        if timeoutCall.active():
            timeoutCall.cancel()
            return d.callback(v)
        else:
            return None
    deferred.addBoth(_cb)
    return d
