"""Apt helper code for getting product versions and changelog information from package repository."""

import os
import re
import datetime
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import versioninfo

run_command = runcommand.run_command

_log = logger.get('l2tpmanagementserver.aptsupport')

_global_aptcache = None

class AptCacheInfo:
    def __init__(self, cachetime, version, changelog):
        self.cachetime = cachetime
        self.version = version
        self.changelog = changelog
        
class AptCache:
    """Get version and changelog information for requested apt sources.list.

    Retrieves all information from the package repository using apt, and caches
    results for a reasonable period of time to minimize apt traffic.
    """
    def __init__(self, interval=2*60):
        self.tmpsource = '/tmp/tmp_apt_sources_list'  # FIXME
        self.package_name_re = re.compile(r'vpnease_.*\.deb')
        self.aptitude_options = ['-o', 'Dir::Etc::SourceList=%s' % self.tmpsource]
        self.interval = interval
        self.cache = {}     # sources.list contents -> AptCacheInfo

    def get_apt_info(self, apt_sources_list):
        """Get apt information for an apt sources.list.

        Retrieves relevant information (with caching), and returns a tuple
        consisting of: latest version number, changelog.

        FIXME: has some trouble now with downgrade, maybe need to nuke
        /var/lib/apt/lists/vpnease* or something.  Also, could we download
        lists to some temporary file instead?
        """
        try:
            now = datetime.datetime.utcnow()

            # serve from cache?
            if self.cache.has_key(apt_sources_list):
                cinfo = self.cache[apt_sources_list]
                diff = now - cinfo.cachetime
                if (diff >= datetime.timedelta(0, 0, 0)) and (diff <= datetime.timedelta(0, self.interval, 0)):
                    _log.info('serving cached apt info for version %s' % cinfo.version)
                    return cinfo.version, cinfo.changelog
            else:
                pass

            # no, fetch using apt and cache
            _log.info('fetching apt info, apt source:')
            _log.info(apt_sources_list)
            helpers.write_file(self.tmpsource, apt_sources_list, perms=0644)
            run_command(['aptitude'] + self.aptitude_options + ['update'], retval=runcommand.FAIL)
            run_command(['aptitude'] + self.aptitude_options + ['download', 'vpnease'], cwd='/tmp', retval=runcommand.FAIL)
            version = None
            for i in os.listdir('/tmp'):
                if self.package_name_re.match(i):
                    version = versioninfo.get_package_version_info(os.path.join('/tmp', i))
                    changelog = versioninfo.get_package_changelog(os.path.join('/tmp', i))
                    run_command(['/bin/rm', '-f', os.path.join('/tmp', i)], retval=runcommand.FAIL)
            if version is None:
                raise Exception('vpnease package file not found')
            if changelog is None:
                raise Exception('vpnease package changelog not found')
            
            # create a new cache object
            cinfo = AptCacheInfo(now, version, changelog)
            self.cache[apt_sources_list] = cinfo
            
            # return fresh data
            _log.info('serving fresh apt info for version %s' % cinfo.version)
            return cinfo.version, cinfo.changelog
        except:
            _log.exception('failed to get package version info')
            raise

        raise Exception('should not be here')

def get_aptcache():
    global _global_aptcache
    if _global_aptcache is None:
        _global_aptcache = AptCache()
    return _global_aptcache

