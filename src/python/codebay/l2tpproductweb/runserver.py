
import os, sys, optparse, tempfile

from OpenSSL import SSL
from twisted.application import service, internet
from twisted.internet import reactor, ssl

from codebay.common import logger
from codebay.l2tpproductweb import website

_log = logger.get('l2tpproductweb.runserver')

def _run_server():
    # options
    opt = optparse.OptionParser(usage='%prog', version='%prog')
    opts, args = opt.parse_args(sys.argv[1:])

    port = website.HTTP_PORT

    master = None
    #master.start() # XXX
    site = website.WebSite(master)
    application = service.Application('vpnease.com')
    _log.info('Binding to port %d' % port)
    srv = internet.TCPServer(port, site.createMainSite())
    srv.setServiceParent(application)
    srv.startService()
    _log.info('Reactor starting')
    reactor.run()
    _log.info('Reactor exited')

if __name__ == '__main__':
    _run_server()
