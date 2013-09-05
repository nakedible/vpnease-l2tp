#!/usr/bin/python

import os, sys, re

# XXX: how to ensure that kernel update does not require user intervention?
# XXX: for now assume that it will not block..

class UpdateError(Exception):
    """Update failed"""

class PackageUpdate:
    #
    #  XXX: General cleanup comment: this function is way too large and intended
    #  to be easily maintainable.  Piece out individual helpers as separate (private)
    #  methods to make the overall flow of control more readable.
    #

    def run_update(self):
        # Ensure no questions asked
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'

        # XXX: is this ok?
        # os.environ['DEBIAN_PRIORITY'] = 'critical'
        # os.environ['DEBCONF_NOWARNINGS'] = 'yes'

        result = None
        old_version = None
        old_version_cached = None
        new_version = None
        new_version_cached = None

        # Tolerate logger errors
        try:
            from codebay.common import logger
            _log = logger.get('l2tpserver.update.update')
        except:
            _log = None

        try:
            from codebay.l2tpserver import constants
            from codebay.l2tpserver import runcommand
            from codebay.l2tpserver import versioninfo
            from codebay.l2tpserver import helpers
        
            run_command = runcommand.run_command
        except:
            print 'failed to import helpers, cannot update'
            return 3

        try:
            def _run_aptitude(options, cwd=None):
                """Run aptitude with automatic -q and -y options."""
                # XXX: add some option to make aptitude return with error instead of asking to ignore trust violations => may not be possible
                # - if cannot be done, missing repository keys will result in update timeout (aptitude will block)
                cmd = [constants.CMD_APTITUDE, '-q', '-y'] + options
                if _log is not None:
                    _log.info('running: %s' % ' '.join(cmd))
                retval, stdout, stderr = run_command(cmd, cwd=cwd)
                if retval != 0:
                    if _log is not None:
                        _log.warning('aptitude return value: %d' % retval)  
                        _log.warning('stdout:\n%s' % stdout)
                        _log.warning('stderr:\n%s' % stderr)
                return retval, stdout, stderr

            def _dpkg_configure_fixup():
                """Attempt 'dpkg --configure -a' fixup."""

                # XXX: the previous worry here is that something may block, and an update
                # might actually fix the situation anyway.
                try:
                    # XXX: more logging, XXX: path use
                    [rv, out, err] = run_command(['dpkg',
                                                  '--force-depends',
                                                  '--force-confmiss',
                                                  '--force-confdef',
                                                  '--force-confold',
                                                  '--configure', '-a'],
                                                 retval=runcommand.FAIL)
                except:
                    if _log is not None: _log.exception('dpkg --configure -a failed, this is bad')

            def _cleanup_old_package_lists():
                """Cleanup old package lists."""
                try:
                    if _log is not None: _log.info('cleaning up apt sources lists')

                    # Remove all files in partial dir
                    partial_dir = '/var/lib/apt/lists/partial'
                    for f in os.listdir(partial_dir):
                        fpath = os.path.join(partial_dir, f)
                        if os.path.isfile(fpath):
                            run_command(['/bin/rm', '-f', fpath])

                    # Remove all files except lock
                    lists_dir = '/var/lib/apt/lists'
                    for f in os.listdir(lists_dir):
                        fpath = os.path.join(lists_dir, f)

                        m = lockfile_name_re.match(f)
                        if (os.path.isfile(fpath)) and (m is None):
                            run_command(['/bin/rm', '-f', fpath])
                except:
                    if _log is not None: _log.exception('failed to remove package list files')
                
            def _aptitude_force_install():
                """Attempt aptitude install which may clear up some (but not nearly all) error situations."""
                try:
                    # XXX: more logging here
                    # XXX: add -q (quiet) option?
                    run_command([constants.CMD_APTITUDE, '-f', '-y', 'install'], retval=runcommand.FAIL)
                except:
                    if _log is not None: _log.exception('apt-get cleanup failed, ignoring')

            # Figure out version
            v_name_re = re.compile('vpnease_.*\.deb')
            lockfile_name_re = re.compile('^lock$')
            old_version, old_version_cached = versioninfo.get_version_info()
            if _log is not None: _log.info('starting update, current_version: %s (cached: %s)' % (str(old_version), str(old_version_cached)))

            # Remove old repository keys and import new ones

            if _log is not None: _log.info('removing old repository keys')
            [rv, out, err] = run_command([constants.CMD_RM, '-f', '/etc/apt/trustdb.gpg', '/etc/apt/trusted.gpg'])
            # XXX: more logging here
            [rv, out, err] = run_command([constants.CMD_APT_KEY, 'list']) # this recreates the gpg key store files

            if _log is not None: _log.info('importing repository keys')
            # XXX: more logging here
            [rv, out, err] = run_command([constants.CMD_APT_KEY, 'add', constants.UPDATE_REPOSITORY_KEYS_FILE])
            if rv != 0:
                result = [9, 'failed to import repository keys']
                raise UpdateError()

            # Cleanup old package list files, ignore errors
            _cleanup_old_package_lists()

            # Aptitude -f -y install
            _dpkg_configure_fixup()
            _aptitude_force_install()
            
            # In some practical situtions, e.g. in #734, the above command may fail
            # really badly (caused by broken package scripts), leading to a "dpkg
            # interrupted state".  We re-run dpkg --configure -a to recover.
            _dpkg_configure_fixup()

            # Aptitude update
            if _log is not None: _log.info('updating package list')
            [rv, out, err] = _run_aptitude(['update'])
            if rv != 0:
                result = [4, 'package list update failed']
                raise UpdateError()

            # Cleanup possibly confusing files in /tmp, should not be needed
            for f in os.listdir('/tmp'):
                m = v_name_re.match(f)
                if m is not None:
                    [rv, out, err] = run_command([constants.CMD_RM, '-f', os.path.join('/tmp', f)])

            # XXX: sanity
            _dpkg_configure_fixup()

            # Test repository access
            if _log is not None: _log.info('testing repository access')
            [rv, out, err] = _run_aptitude(['download', 'vpnease'], cwd='/tmp')
            if rv != 0:
                result = [5, 'server not available']
                raise UpdateError()

            # If testing for version info fails, it is ignored and it may generate an error
            # later when we check if the product version changed or not.
            for f in os.listdir('/tmp'):
                m = v_name_re.match(f)
                if m is not None:
                    cmp_version = versioninfo.get_package_version_info(os.path.join('/tmp', f))
                    if cmp_version is not None and cmp_version == old_version:
                        result = [0, 'update not run, version in repository matches current version']
                        raise UpdateError()
                    break

            # Aptitude clean
            if _log is not None: _log.info('cleaning up old package files')
            _run_aptitude(['clean'])

            # Aptitude upgrade
            # XXX: should this be dist-upgrade?  dist-upgrade seems to be more forceful...
            _dpkg_configure_fixup()  # XXX: sanity
            [rv1, out, err] = _run_aptitude(['upgrade'])

            # Aptitude  install vpnease
            _dpkg_configure_fixup()  # XXX: sanity
            [rv2, out, err] = _run_aptitude(['install', 'vpnease']) # Ensure vpnease package is still installed

            # Reinstall dependencies of vpnease package (sanity)
            _dpkg_configure_fixup()  # XXX: sanity
            try:
                deps = []
                dep_re = re.compile('^Depends: (.*)$')
                # XXX: better logging here
                # XXX: check that package is installed correctly
                [rv, out, err] = run_command(['dpkg', '-s', 'vpnease'])

                for l in out.split('\n'):
                    m = dep_re.match(l)
                    if m is None:
                        continue
                    for d in m.groups()[0].split(','):
                        ds = d.strip().split(' ')
                        deps.append(ds[0])

                _run_aptitude(['reinstall'] + deps)
            except:
                if _log is not None: _log.info('failed to reinstall vpnease depends')

            # Aptitude reinstall vpnease
            try:
                _run_aptitude(['reinstall', 'vpnease'])
            except:
                if _log is not None: _log.info('failed to reinstall vpnease depends')

            # Aptitude clean
            if _log is not None: _log.info('cleaning up downloaded package files')
            _run_aptitude(['clean'])

            # Get new version, determine whether update succeeded based on version & return values
            new_version, new_version_cached = versioninfo.get_version_info()

            if rv1 != 0 or rv2 != 0:
                result = [6, 'upgrade/install command failed with error value: %s/%s' % (str(rv1), str(rv2))]
                raise UpdateError()
            elif new_version_cached:
                result = [7, 'failed to read version information after update']
                raise UpdateError()
            elif old_version == new_version:
                result = [8, 'product version unchanged after update, update failed']
                raise UpdateError()

        except UpdateError:
            pass
        except:
            result = [32, 'update failed with an exception']

        # At this point, update was successful if result is None

        # Cleanup..
        [rv, out, err] = run_command([constants.CMD_RM, '-f', '/tmp/vpnease_*.deb'])

        # Note: because timesync may be done later in update (after this script is run)
        # this timestamp may not be very accurate.
        def _write_marker_file(msg):
            # XXX: msg is not used for anything here ??

            rv = helpers.write_datetime_marker_file(constants.UPDATE_RESULT_MARKER_FILE)
            if rv is None:
                raise Exception('failed to write update timestamp marker')

        # Handle errors
        if result is not None:
            if result[0] == 32:
                if _log is not None: _log.exception(result[1])
            else:
                if _log is not None: _log.warning(result[1])

            try:
                _write_marker_file('%s %s\nfailed\n%s' % (old_version, new_version, result[1]))
            except:
                if _log is not None: _log.exception('failed to write marker fail after failed update, ignoring')

            return result[0]

        # Update last update result marker file
        try:
            if _log is not None: _log.info('update success: %s -> %s' % (old_version, new_version))
            _write_marker_file('%s %s\nsuccess\nUpdate success' % (old_version, new_version))
        except:
            if _log is not None: _log.exception('failed to write marker file after successful update, ignoring')

        # Update last successful update timestamp, used by Web UI
        try:
            rv = helpers.write_datetime_marker_file(constants.LAST_SUCCESSFUL_UPDATE_MARKER_FILE)
            if rv is None:
                raise Exception('failed to write last successful update timestamp')
        except:
            if _log is not None: _log.exception('failed to write last successful update timestamp, ignoring')

        # Update done with success
        return 2

if __name__ == '__main__':
    sys.exit(PackageUpdate().run_update())
