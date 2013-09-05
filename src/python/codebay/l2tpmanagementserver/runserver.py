"""Wrapper for starting management server."""

import tempfile
import ConfigParser

from OpenSSL import SSL
from twisted.internet import reactor, ssl

from codebay.l2tpmanagementserver import managementserver
from codebay.l2tpmanagementserver import constants as msconstants

class ManagementServerOpenSSLContextFactory(ssl.ContextFactory):
    def __init__(self, private_key, certificate_chain):
        self._context = None
        self._private_key = private_key
        self._certificate_chain = certificate_chain

    def getContext(self):
        if self._context is not None:
            return self._context
        
        ctx = SSL.Context(SSL.SSLv23_METHOD)
        ctx.use_privatekey_file(self._private_key)
        ctx.use_certificate_chain_file(self._certificate_chain)
        
        self._context = ctx
        return self._context

def _create_certificate_chain(idx):
    fname = tempfile.mktemp(suffix='-cert-chain')

    f1 = open(fname, 'wb')

    # XXX: multiple certificate chains, for different ssl server sockets
    # XXX: index approach is probably not the best here
    if idx == 1:
        certfile = msconstants.SERVER_CERTIFICATE1
        cacertfile = msconstants.VPNEASE_CA_CERTIFICATE1
    elif idx == 2:
        certfile = msconstants.SERVER_CERTIFICATE2
        cacertfile = msconstants.VPNEASE_CA_CERTIFICATE2
    else:
        raise Exception('invalid index')
    
    # Certificate chain must be from end entity cert to CA cert
    f2 = open(certfile, 'rb')
    f1.write(f2.read())
    f2.close()

    f3 = open(cacertfile, 'rb')
    f1.write(f3.read())
    f3.close()

    f1.close()
    
    return fname

def _run_server():
    # parse some options from config
    config_file = msconstants.CONFIG_FILE
    parser = ConfigParser.SafeConfigParser()
    parser.read(config_file)
    server_address1 = parser.get('misc', 'address1')
    server_address2 = parser.get('misc', 'address2')
    
    # start up
    master = managementserver.ManagementServerMaster(parser)
    pf1 = managementserver.ManagementServerProtocolFactory(master)
    pf2 = managementserver.ManagementServerProtocolFactory(master)

    # build certificate chain temporary files
    cert_chain1 = _create_certificate_chain(1)
    cert_chain2 = _create_certificate_chain(2)

    # NB: the context cf1 (for management protocol versions 1-3) must accept both
    # SSL 3.0 and TLS 1.0 (SSL 3.1) for backward compatibility
    cf1 = ManagementServerOpenSSLContextFactory(msconstants.SERVER_PRIVATE_KEY1, cert_chain1)
    cf2 = ManagementServerOpenSSLContextFactory(msconstants.SERVER_PRIVATE_KEY2, cert_chain2)

    master.start() # XXX
    reactor.listenSSL(msconstants.SERVER_PORT, pf1, cf1, backlog=50, interface=server_address1)
    reactor.listenSSL(msconstants.SERVER_PORT, pf2, cf2, backlog=50, interface=server_address2)
    reactor.run()

if __name__ == '__main__':
    _run_server()
