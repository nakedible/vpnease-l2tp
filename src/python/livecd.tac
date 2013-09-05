# -*- python -*-
from nevow import guard, inevow, appserver
from twisted.application import strports, service

from codebay.common import logger

from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import master, website

application = service.Application('l2tpserver')

webuimaster = master.LiveCdMaster()
webuimaster.pre_start()

webuiservice = master.LiveCdService(webuimaster)
webuiservice.setServiceParent(application)

# XXX: limit binding to localhost (no network at the moment -> does not matter)
webuisite = website.LiveCdSite(webuimaster)
mainsite = webuisite.createMainSite()
strports.service(constants.WEBUI_STRPORT_HTTP, mainsite).setServiceParent(application)
###strports.service(constants.WEBUI_STRPORT_HTTPS, mainsite).setServiceParent(application)
