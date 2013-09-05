"""L2TP installation specific helpers."""
__docformat__ = 'epytext en'

import re, os, time

from codebay.common import logger
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants
from codebay.l2tpserver import mediahelper

run_command = runcommand.run_command
_log = logger.get('l2tpserver.installhelpers')

def cache_reboot_command():
    """Cache reboot command.

    Ensures that the files required for rebooting the machine are cached
    and do not require livecd in drive anymore.
    """

    # XXX: there may be a better way to do this, but this works for us
    ldd_static_re = re.compile(r'.*statically.*')
    ldd_link_re = re.compile(r'\s+[^ ]+ => ([^ ]+) ')
    ldd_direct_re = re.compile(r'\s+([^ ]+) ')

    def _cache_path(path):
        if not os.path.exists(path):
            return

        run_command('%s %s > /dev/null' % (constants.CMD_CAT, path), shell=True)

        [rv, out, err] = run_command([constants.CMD_LDD, path])
        for i in out.split('\n'):
            m = ldd_static_re.match(i)
            if m is not None:
                break

            m = ldd_link_re.match(i)
            if m is not None:
                _cache_path(m.groups()[0])
            else:
                m = ldd_direct_re.match(i)
                if m is not None:
                    _cache_path(m.groups()[0])

    for p in [constants.CMD_HALT, constants.CMD_REBOOT]:
        _cache_path(p)

def do_sync():
    """Flush file system buffers."""

    run_command(constants.CMD_SYNC)
    run_command(constants.CMD_SYNC)
    run_command(constants.CMD_SYNC)

def force_eject_cdrom():
    """Eject cdrom forcibly."""

    run_command([constants.CMD_EJECT, '-p', '-m'])

def force_reboot_host():
    """Do forced quick reboot."""

    # Note: the -n flag prevents sync which and caller should run
    # do_sync() before forced reboot. The -n flag also implies -d
    # which prevents wtmp update
    run_command([constants.CMD_REBOOT, '-f', '-n'])

def reboot_host(reason):
    """Reboot the host when running on live-cd, writing 'reason' to log
    and console.

    Returns immediately but reboot is processed in the background.
    """
    
    if reason is None:
        reason = '(unspecified reason)'

    myenv = dict(os.environ)
    myenv['DISPLAY'] = ':0.0'
    myenv['HOME'] = '/home/%s' % constants.ADMIN_USER_NAME   # for .Xauthority
    
    [rv, stdout, stderr] = run_command(['/usr/bin/gdm-signal', '--reboot'], env=myenv)
    _log.info('gdm-signal returned: rv: %d, stdout: %s, stderr: %s' % (int(rv), stdout, stderr))
    time.sleep(5)
    [rv, stdout, stderr] = run_command(['/usr/bin/killall', 'x-session-manager'], env=myenv)

    # XXX: maybe not possible to see this message anymore, because we are
    # killed to quickly..
    _log.info('killall returned: rv: %d, stdout: %s, stderr: %s' % (int(rv), stdout, stderr))

    # XXX: this would be cleaner, but gnome-session-save cannot connect
    # to session manager for some reason.
    # ([constants.CMD_SUDO, '-u', 'admin', '-H', 'gnome-session-save', '--kill', '--silent'], env=myenv)

def recover_existing_configuration(target_dev):
    part_root = None

    try:
        mountpoint = '/target-recovery'

        print 'attempting recovery from %s, mountpoint %s' % (target_dev, mountpoint)
        
        m = mediahelper.get_media()
        target = m.get_medium_by_device_name(target_dev)
        if target is None:
            raise Exception('failed to find installation target device: %s' % target_dev)

        # try a number of partitions; we now have a variable partition scheme
        for i in xrange(1, 10):
            try:
                part_root = target.get_partition_devicename(i)
                if part_root is None:
                    print 'failed to find partition %d from device: %s' % (i, target_dev)
                    continue

                print 'mounting partition %s for recovery' % part_root
        
                run_command([constants.CMD_UMOUNT, mountpoint])  # ignore errors
                run_command([constants.CMD_RMDIR, mountpoint])  # ignore errors
                run_command([constants.CMD_MKDIR, '-p', mountpoint], retval=runcommand.FAIL)
                run_command([constants.CMD_MOUNT, part_root, mountpoint], retval=runcommand.FAIL)

                print 'mounted ok'

                # XXX: here we assume "well known locations"
                exported_known_good = os.path.join(mountpoint, 'var', 'lib', 'l2tpgw', 'exported-rdf-database.xml')
                print 'looking for existing configuration at %s' % exported_known_good

                if os.path.exists(exported_known_good):
                    print 'found existing exported known good file %s' % exported_known_good
                else:
                    print 'did not find existing exported known good file %s, next partition' % exported_known_good
                    continue
                
                f = None
                rdfxml = None
                try:
                    f = open(exported_known_good, 'rb')
                    rdfxml = f.read()
                finally:
                    if f is not None:
                        f.close()
                        f = None

                # try to figure old version opportunistically
                ver_cache = os.path.join(mountpoint, 'var', 'lib', 'l2tpgw', 'version-info-cache')
                prev_version = None
                if os.path.exists(ver_cache):
                    f = None
                    try:
                        f = open(ver_cache, 'rb')
                        prev_version = f.read().strip()
                    finally:
                        if f is not None:
                            f.close()
                            f = None

                return rdfxml, prev_version
            except:
                print 'failed recovery check for one partition, this is quite normal'

        # no results after for loop
        print 'did not find existing exported known good file %s' % exported_known_good
        return None, None
    finally:
        run_command([constants.CMD_UMOUNT, mountpoint])  # ignore errors
        if mountpoint is not None:
            run_command([constants.CMD_RMDIR, '/%s/' % mountpoint]) # ignore errors

    return None, None
