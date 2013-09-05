# -*- python -*-
from twisted.application import strports, service

from codebay.common import logger

from codebay.l2tpmanagementserver import managementserver

application = service.Application('l2tpmanagementserver')

mgmtmaster = managementserver.ManagementServerMaster()
mgmtmaster.pre_start()

mgmtservice = managementserver.ManagementServerService(mgmtmaster)
mgmtservice.setServiceParent(application)

strports.service('1234', managementserver.ManagementServerProtocolFactory(mgmtmaster)).setServiceParent(application)

