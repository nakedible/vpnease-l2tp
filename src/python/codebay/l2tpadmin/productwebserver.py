#!/usr/bin/python

import os, re, sys, textwrap

from codebay.common import runcommand
from codebay.l2tpserver import constants

WEBSERVER_PIDFILE = '/var/run/l2tp-web-server.pid'

def stop(args):
    cmd = [constants.CMD_START_STOP_DAEMON,
           '--stop',
           '--verbose',
           '--signal', 'TERM',
           '--pidfile', WEBSERVER_PIDFILE]

    runcommand.run(cmd, retval=runcommand.FAIL)

    try:
        os.unlink(WEBSERVER_PIDFILE)
    except:
        pass

def start(args):
    try:
        stop()
    except:
        pass

    try:
        os.unlink(WEBSERVER_PIDFILE)
    except:
        pass
    
    startup_script = textwrap.dedent("""\
    from codebay.l2tpproductweb import runserver
    runserver._run_server()
    """)

    cmd = [constants.CMD_START_STOP_DAEMON,
           '--start',
           '--verbose',
#           '--exec', '/usr/bin/python',
           '--exec', '/usr/bin/python2.4',   # XXX: python 2.4 for now
           '--pidfile', WEBSERVER_PIDFILE,
           '--background',
           '--make-pidfile',
           '--',  # start python options
           '-c',  # execute script from args
           startup_script]

    runcommand.run(cmd, retval=runcommand.FAIL)
    #rv, stdout, stderr = runcommand.run(cmd)
    #print stdout
    #print stderr
    
