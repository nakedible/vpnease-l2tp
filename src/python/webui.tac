# -*- python -*-
from twisted.application import service, internet
from OpenSSL import SSL

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import master, website

application = service.Application('l2tpserver')

webuimaster = master.WebUiMaster()
webuimaster.pre_start()

webuiservice = master.WebUiService(webuimaster)
webuiservice.setServiceParent(application)

webuisite = website.WebUiSite(webuimaster)
mainsite = webuisite.createMainSite()
fwdsite = webuisite.createForwardingSite()

# http ports
for [port, site] in [ [constants.WEBUI_PORT_HTTP, mainsite],
                      [constants.WEBUI_FORWARD_PORT_UIFORCED_HTTP, fwdsite],
                      [constants.WEBUI_FORWARD_PORT_LICENSE_HTTP, fwdsite],
                      [constants.WEBUI_FORWARD_PORT_OLDPSK_HTTP, fwdsite] ]:
    s = internet.TCPServer(port, site)
    s.setServiceParent(application)

# https ports
privateKey = constants.WEBUI_PRIVATE_KEY
certKey = constants.WEBUI_CERTIFICATE
ssl_cf = website.CustomOpenSSLContextFactory(privateKey, certKey, sslmethod=SSL.SSLv23_METHOD)   # XXX: method?  TLS?
webuimaster.set_ssl_contextfactory(ssl_cf)

# nb: up to this point always self-signed certs, this causes check of external certificate
webuimaster.reread_ssl_files()

for [port, site] in [ [constants.WEBUI_PORT_HTTPS, mainsite],
                      [constants.WEBUI_FORWARD_PORT_UIFORCED_HTTPS, fwdsite],
                      [constants.WEBUI_FORWARD_PORT_LICENSE_HTTPS, fwdsite],
                      [constants.WEBUI_FORWARD_PORT_OLDPSK_HTTPS, fwdsite] ]:
    s = internet.SSLServer(port, site, ssl_cf)
    s.setServiceParent(application)
