"""
Find and return product version infromation.

Also cache version information in case we could not find it later.
Return cached information if no other found and report information
source.
"""

from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
import os, re, datetime

run_command = runcommand.run_command

version_re = re.compile('\s*Version: (.*)$')
changelog_version_re = re.compile('\s*%s \((.*)\)' % constants.PRODUCT_DEBIAN_NAME)
changelog_bullet_re = re.compile(r'^\s*\*\s*(.*?)$')
changelog_bullet_cont_re = re.compile(r'^\s*([^\-\*\s].*)$')
changelog_empty_re = re.compile(r'^\s*$')
changelog_signed_off_re = re.compile(r'^\s*\-\-\s*(.*?)$')

def _get_cached_info():
    version_string = constants.DEFAULT_VERSION_STRING # XXX: or raise?

    f = None
    try:
        f = open(constants.VERSION_INFO_CACHE, 'r')
        version_string = f.readline().strip()
    finally:
        if f is not None: f.close()

    return [version_string, True]

def _store_cached_info(version_string):

    f = None
    try:
        f = open(constants.VERSION_INFO_CACHE, 'w')
        f.write(version_string + '\n')
    finally:
        if f is not None: f.close()

def get_version_info():
    """Returns product version and meta information.
    """

    version_string = None

    try:
        [rv, out, err] = run_command([constants.CMD_DPKG, '-s', constants.PRODUCT_DEBIAN_NAME])
        if rv != 0:
            return _get_cached_info()

        for i in out.split('\n'):
            m = version_re.match(i)
            if m is not None:
                version_string = m.groups()[0]
                break

        if version_string is None:
            return _get_cached_info()

        _store_cached_info(version_string)
    except:
        return _get_cached_info()

    return [version_string, False]

def get_package_version_info(deb_file):
    """Returns version information from a .dpkg file.
    """

    version_string = None

    [rv, out, err] = run_command([constants.CMD_DPKG, '--info', '%s' % deb_file])
    for i in out.split('\n'):
        m = version_re.match(i)
        if m is not None:
            version_string = m.groups()[0]
            break

    return version_string

def get_package_changelog(deb_file):
    # XXX: should be moved to a proper place, but this is used (only) from management server code
    run_command([constants.CMD_RM, '-rf', '/tmp/package_changelog_tmpdir'], retval=runcommand.FAIL)
    run_command([constants.CMD_MKDIR, '-p', '/tmp/package_changelog_tmpdir'], retval=runcommand.FAIL)
    run_command([constants.CMD_DPKG, '-x', deb_file, '/tmp/package_changelog_tmpdir'], retval=runcommand.FAIL)

    # XXX: changelog is in constants as absolute path, using here as relative to extraceted package directory
    [rv, out, err] = run_command(['/bin/zcat', os.path.join('/tmp/package_changelog_tmpdir', constants.PRODUCT_CHANGELOG[1:])], retval=runcommand.FAIL)
    return out

def get_changelog():
    [rv, out, err] = run_command(['/bin/zcat', constants.PRODUCT_CHANGELOG])
    return out

def get_changelog_info(startversion=None, changelog=None):
    """Returns product main debian package changelog entries.

    Format is a list of lists including [version of changelog entry, the changelog entry itself].

    If startversion is specified, then limit returned entries to those
    newer than the startversion.

    Returns empty list on error.
    """

    entries = []    
    try:
        if changelog is None:
            changelog = get_changelog()
        lines = ''
        version = None
        for i in changelog.split('\n'):
            m = changelog_version_re.match(i)
            if m is not None:
                if version is not None:
                    entries.append([version, lines])
                    lines = ''

                version = m.groups()[0]
                if startversion is not None and version == startversion:
                    version = None
                    break
    
            lines += '%s\n' % i

        if version is not None:
            entries.append([version, lines])
    except:
        # XXX: this is a silent error, but raising is not much better anyways.
        return []

    return entries

def parse_changelog_entry(entry):
    version = None
    bullets = []
    signed_off = None
    curr_bullet = None
    
    for l in entry.split('\n'):
        l = l.strip()
        m = changelog_version_re.match(l)
        if m is not None:
            version = m.group(1)
            continue
        m = changelog_signed_off_re.match(l)
        if m is not None:
            if curr_bullet is not None:
                bullets.append(curr_bullet)
                curr_bullet = None
            signed_off = m.group(1)
            continue
        m = changelog_bullet_re.match(l)
        if m is not None:
            if curr_bullet is not None:
                bullets.append(curr_bullet)
            curr_bullet = m.group(1)
            continue
        m = changelog_bullet_cont_re.match(l)
        if m is not None:
            if curr_bullet is not None:
                curr_bullet = curr_bullet + ' ' + m.group(1)
            continue
        m = changelog_empty_re.match(l)
        if m is not None:
            if curr_bullet is not None:
                bullets.append(curr_bullet)
                curr_bullet = None

    return [version, bullets, signed_off]

