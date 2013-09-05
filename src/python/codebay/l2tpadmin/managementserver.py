#!/usr/bin/python

import os, re, sys, textwrap

from codebay.common import runcommand
from codebay.l2tpserver import constants
from codebay.l2tpmanagementserver import constants as msconstants

MS_PIDFILE = '/var/run/l2tp-management-server.pid'

def stop(args):
    cmd = [constants.CMD_START_STOP_DAEMON,
           '--stop',
           '--verbose',
           '--signal', 'TERM',
           '--pidfile', MS_PIDFILE]

    runcommand.run(cmd, retval=runcommand.FAIL)

    try:
        os.unlink(MS_PIDFILE)
    except:
        pass

def start(args):
    try:
        stop()
    except:
        pass

    try:
        os.unlink(MS_PIDFILE)
    except:
        pass
    
    startup_script = textwrap.dedent("""\
    from codebay.l2tpmanagementserver import runserver
    runserver._run_server()
    """)

    cmd = [constants.CMD_START_STOP_DAEMON,
           '--start',
           '--verbose',
           '--exec', '/usr/bin/python',
           '--pidfile', MS_PIDFILE,
           '--background',
           '--make-pidfile',
           '--',  # start python options
           '-c',  # execute script from args
           startup_script]

    runcommand.run(cmd, retval=runcommand.FAIL)

def get_demo_license_info():
    my_re_time = re.compile('^grant-time=(.*?)$')
    my_re_addr = re.compile('^remote-address=(.*?)$')

    lst = []
    for i in os.listdir(msconstants.DEMO_LICENSE_DIRECTORY):
        f = None
        try:
            f = open(os.path.join(msconstants.DEMO_LICENSE_DIRECTORY, i), 'rb')
            ip = None
            gt = None
            for l in f.readlines():
                l = l.strip()
                m = my_re_addr.match(l)
                if m is not None:
                    ip = m.group(1)
                m = my_re_time.match(l)
                if m is not None:
                    gt = m.group(1)
            if gt is not None and ip is not None:
                lst.append((gt, ip))
        finally:
            if f is not None:
                f.close()
            f = None

    lst.sort()

    res = ''
    for (gt, ip) in lst:
        rv, stdout, stderr = runcommand.run(['/usr/bin/host', ip])
        stdout = stdout.strip()
        res += '%s: %s -> %s\n' % (gt, ip, stdout)
    return res

def write_backup_file():
    import datetime

    # FIXME: add more files/directories to backup
    # input_files = [msconstants.CONNECTION_INFO_FILE, msconstants.DEMO_LICENSE_DIRECTORY, msconstants.REPOSITORY_KEYS_FILE]
    input_files = [msconstants.DEMO_LICENSE_DIRECTORY]

    n = datetime.datetime.utcnow()
    tmpfile = '/tmp/management-server-backup-%s%s%s-%s%s%s.tar.gz' % (n.year, n.month, n.day, n.hour, n.minute, n.second)

    runcommand.run(['/bin/rm', '-f', tmpfile], retval=runcommand.FAIL)
    runcommand.run(['/bin/tar', 'czf', tmpfile] + input_files, retval=runcommand.FAIL)

    return tmpfile

def get_stats():
    tmp = ''
    demolics = get_demo_license_info()

    tmp += 'Assigned demo licenses\n' + \
           '======================\n\n' + \
           demolics + \
           '\n\n'

    tmp += 'Active management connections\n' + \
           '============================\n\n'

    f = None
    try:
        f = open(msconstants.CONNECTION_INFO_FILE, 'rb')
        tmp += f.read()
        tmp += '\n\n'
    finally:
        if f is not None:
            f.close()
        f = None

    return tmp

def send_stats():
    # NB: sent from outside
    mail_address = 'info@vpnease.com'

    ret, stdout, stderr = runcommand.run(['/usr/bin/mailx', '-s', 'management.vpnease.com stats', mail_address], stdin=get_stats())
