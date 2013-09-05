#!/usr/bin/python

import sys, os, re, textwrap, datetime
sys.path.append(os.path.join('src', 'python'))

from codebay.build import build
from codebay.common import helpers

# Notes:
# - linux_restricted_modules currently not built for our kernel version
# - kernel .udeb packages are not installed
# - packages removed automatically because of they dependencies vanish are not purged, but deleted

# maybe TODO:
# - change default kernel options?
#   - f.ex panic=N could be used to recover from temporary kernel panics..
# - preseed debconf database with config for daemons: openswan, monit, etc

# TODO:
# - purge more ubuntu packages: language packs for example
# - usplash customization
# - status information for first virtual console?
# - user/passwd configuration: root password?
# - vpnease package must depend on all essential ubuntu packages: share dependencies with livecd build so that the list is not duplicated..

# changes made by build process which could be done from a debian package to allow update:
# - distro startup modifications (diverts, etc)
# - default config modifications: /etc/default options, syslogd config, etc.


class DebSourceBuild(build.Build):
    name = None
    description = None
    sdir=None
    debname = None
    debver = None
    debprefix = None
    deborigversion=None
    deborigrevision=None
    debnewversion=None
    patchnames=None

    def check_revision(self):
        try:
            self.revision.index(':')
            raise build.BuildError('Cannot build from mixed-version source-tree (%s), please update.' % self.revision)
        except ValueError:
            pass

    def append_revision_to_version(self, ver=None):
        if ver is None:
            ver = self.debver
        return '%s+codebay+r%s' % (ver, self.revision)

    # Overwrite when needed
    def get_plain_deb_ver(self, ver=None):
        self.check_revision()
        return self.append_revision_to_version(ver=ver)

    # Overwrite when needed
    def get_deb_ver(self, ver=None, deb_prefix=None):
        self.check_revision()

        if ver is None:
            ver = self.debver

        if deb_prefix is not None:
            ver = deb_prefix + ':' + ver
        elif self.debprefix is not None:
            ver = self.debprefix + ':' + ver

        return self.append_revision_to_version(ver=ver)

    # Overwrite when needed
    def get_targets(self):
        return [self.get_deb_target()]

    def get_deb_name(self):
        return self.debname

    def get_deb_target(self, arch='i386', name=None, version=None, fileversion=None, deb_prefix=None):
        if name is None: name = self.get_deb_name()
        if version is None: version = self.get_deb_ver(deb_prefix=deb_prefix)
        if fileversion is None: fileversion = self.get_plain_deb_ver()
        return ['%s_%s_%s.deb' % (name, fileversion, arch), name, version]

    def get_deb_srcdir(self):
        return self.sdir

    def get_deb_dsc(self):
        if self.deborigrevision is not None:
            dsc_end = '-' + self.deborigrevision + '.dsc'
        else:
            dsc_end = '.dsc'
        return '%s_%s%s' % (self.debsrcname, self.deborigversion, dsc_end)

    def get_deb_dirname(self):
        return '%s_%s' % (self.debsrcname, self.deborigversion)

    def _parse_dsc(self, dsc_file):
        files_re = re.compile(r'^Files:$')
        empty_re = re.compile(r'^$')
        filename_re = re.compile(r'^\ [^\ ]+\ [^\ ]+\ ([^\ ]+)$')
        files_start = False
        filenames = []

        f = open(dsc_file, 'rb')
        for l in f.read().split('\n'):
            if files_re.match(l.strip()) is not None:
                files_start = True
                continue
            if not files_start:
                continue
            if files_start:
                if empty_re.match(l.strip()) is not None:
                    break
                m = filename_re.match(l) # NB: do not strip..
                if m is not None:
                    filenames.append(m.groups()[0])
                else:
                    raise build.BuildError('mismatched line "%s" in .dsc file "%s"' % (l, dsc_file))

        f.close()
        if len(filenames) < 1:
            raise build.BuileError('no filenames found in .dsc file "%s"' % dsc_file)

        return filenames

    def get_deb_source_files(self):
        dsc = os.path.join(self.get_deb_srcdir(), self.get_deb_dsc())
        filelist = self._parse_dsc(dsc)
        r = [dsc]
        for f in filelist:
            r.append(os.path.join(self.get_deb_srcdir(), f))
        return r

    def _prepare_source(self, b, bd, dscfile, patchfunc, changelog_msg='VPNease specific changes included.'):
        olddebsrcdir = self.debsrcname + '-' + self.deborigversion
        newdebsrcdir = self.debsrcname + '-' + self.get_plain_deb_ver()

        bd.unpack_deb_source(dscfile)

        if patchfunc is not None:
            patchfunc(b, olddebsrcdir)

        for i in self.patchnames:
            bd.patch_dir(olddebsrcdir, [os.path.join(self.srcdir, self.get_deb_srcdir(), self.debsrcname + '_' + self.deborigversion + '-' + i)])

        if self.deborigversion != self.debnewversion:
            if changelog_msg is None:
                logmsg = 'VPNease specific changes included.'
            else:
                logmsg = changelog_msg
            bd.changelog_newversion(olddebsrcdir, self.get_deb_ver(), logmsg)

        return newdebsrcdir

    def _export_revision(self, bd, revision, path, dest=None):
        if dest is None: dest = path
        bd.ex('svn', 'export', '-r', revision, 'http://ode.intra.codebay.fi/svn/codebay/prod/main/l2tp-dev/%s' % path, dest)

    def _get_source_files(self, bd):
        return [os.path.join(bd.env.path, '%s_%s.dsc' % (self.debsrcname, self.get_plain_deb_ver())),
                os.path.join(bd.env.path, '%s_%s.tar.gz' % (self.debsrcname, self.get_plain_deb_ver()))]

    def build_source_deb(self, b, release_revision, patchfunc=None, changelog_msg=None):
        self.revision = release_revision
        self.srcdir = b.srcdir

        bd = b.get_cwd(self.builddir)

        self._export_revision(bd, release_revision, self.sdir)
        newdebsrcdir = self._prepare_source(b, bd, os.path.join(self.sdir, self.get_deb_dsc()), patchfunc, changelog_msg=changelog_msg)
        bd.ex('dpkg-source', '-b', newdebsrcdir, '')

        return self._get_source_files(bd)

    def run_source(self, b, release_revision):
        return self.build_source_deb(b, release_revision, patchfunc=None,)

    def build_deb(self, b, patchfunc=None, nodep=False):
        bd = b.get_cwd(self.builddir)
        newdebsrcdir = self._prepare_source(b, bd, os.path.join(self.srcdir, self.get_deb_srcdir(), self.get_deb_dsc()), patchfunc)
        bd.build_deb_from_source(newdebsrcdir, nodep=nodep)


class VpnEaseHelper:
    def __init__(self, b):
        self.major = '1'
        self.minor = '2'
        self.revision = '0'
        self.b = b

    def get_ubuntu_depends(self):
        # FIXME: pdf-viewer required?
        return ['gawk', 'ipsec-tools', 'portmap', 'exim4', 'python-zopeinterface', 'python-tz', 'ssh', 'libltdl3', 'libmyspell3c2', 'dhcp3-server']

    def get_version_history(self, revision):
        history = []

        # Create past timestamps like this:
        # date -d "`python -c \"import datetime;print str(datetime.datetime(2007,7,6,15,5))\"`"  +%a, %_d %b %Y %T +0000

        now = datetime.datetime.utcnow()
        build_date = datetime.datetime(now.year, now.month, now.day, now.hour, now.minute)

        [rv, out, err] = self.b.ex_c(['/bin/date', '-d', '%s' % str(build_date), '+%a, %_d %b %Y %T +0000'])
        if (out is None) or (out.strip() == ''):
            raise build.BuildError('missing datestamp')
        build_datestamp = out.strip()

        history.append(['1', '0',
                        '5287',
                        ['First release.'],
                        'Fri,  6 Jul 2007 15:05:00 +0000'])

        history.append(['1', '0',
                        '5529',
                        ['Minor improvements to handling of system time synchronization, \nother minor fixes.'],
                        'Thu, 19 Jul 2007 14:58:00 +0000'])

        history.append(['1', '1',
                        '6708',
                        ['RADIUS authentication support.  Users can now be authenticated\n' +
                         'using a remote RADIUS server.  The Internet Authentication Service\n' +
                         '(IAS) component available for Windows servers provides RADIUS ' +
                         'support, and allows existing Windows accounts to be used for VPN\n' +
                         'and web access authentication.',
                         'SNMP support.  VPNease server can now be monitored using an SNMP\n' +
                         'monitoring system.  A custom VPNease Management Information Base\n' +
                         '(MIB) module provides access to VPNease specific monitoring values.',
                         'Automatic VPN connection configuration for Windows XP and Windows Vista \n' +
                         '(available for 32-bit Windows platforms).',
                         'Minor improvements and bug fixes.'
                         ],
                        'Fri, 19 Oct 2007 20:36:00 +0000'])

        history.append(['1', '2',
                        8605,
                        ['Automatic VPN connection configuration improvements.  Check and\n' +
                         're-enable Windows IPsec and RasMan services if disabled, re-enable\n'
                         'L2TP encryption if disabled, support for Windows 2000 and 64-bit\n' +
                         'Windows versions, avoid initial Windows reboot if possible,\n' +
                         'automatic Desktop shortcut, automatic defaulting\n' +
                         'of username, automatic administrative privilege elevation for Vista.\n' +
                         'Mac OS X Leopard configuration using a configuration template.',
                         'Site-to-site error feedback improved.  Address check failures caused\n' +
                         'by overlapping VPN subnets in client and server are now shown on web\n' +
                         'UI status page.',
                         'Installer improvements.  Recovery feature allows configuration from\n' +
                         'a previous installation to be recovered and imported into a new installation.\n' +
                         'Installer now uses separate partitions for boot (/boot) and root (/)\n' +
                         'partitions if installation target is 4 GB or larger.  This improves\n' +
                         'compatibility with old BIOSes unable to boot from partitions larger\n' +
                         'than 512 MB.',
                         'Dynamic DNS improvements.  Addressing options now include forced address\n' +
                         'and NATted address of the server.  More providers supported.\n',
                         'External SSL certificate can be configured to reduce browser warnings for\n' +
                         'administrator and user web user interface connections.\n',
                         'Minor improvements to status views, other cosmetic improvements.',
                         ],
                        'Sat, 12 Jul 2008 17:44:00 +0000'])
                        
        #history.append(['1', '3',
        #                revision,
        #                ['FIXME',
        #                 'FIXME'],
        #                build_datestamp])

        return history

    def build(self, b, bd, targets, revision, srcdir):
        b.info('  Creating vpnease metapackage:')
        workdir = 'vpnease'
        debiandir = os.path.join(workdir, 'debian')
        controlfile = os.path.join(debiandir, 'control')
        bd.makedirs(debiandir)

        bd.ex('/bin/cp',
              os.path.join(srcdir, 'vpnease/debian/rules'),
              os.path.join(srcdir, 'vpnease/debian/changelog'),
              debiandir)

        depends = self.get_ubuntu_depends()
        for i in targets:
            # Remove casper and ubiquity-casper from depends: only used in live-cd
            # Remove linux-headers.. not useful.
            # Note: -dev packages are not strictly required (unless ppp-dev is?), but currently we depend from them
            # and install all such packages

            r = re.compile('casper|ubiquity-casper|linux-headers')
            if r.match(i[1]):
                continue
            depends.append('%s (= %s)' % (i[1], i[2]))

        helpers.write_file(os.path.join(bd.env.path, controlfile),
                           textwrap.dedent("""\
                           Source: vpnease
                           Maintainer: VPNease support <support@vpnease.com>
                           Section: net
                           Priority: optional
                           Standards-Version: 3.6.2

                           Package: vpnease
                           Depends: %(depends)s
                           Architecture: all
                           Description: A clientless VPN product
                            VPNEase is a VPN product which uses the built-in client of several
                            operating systems for remote access.
                            .
                            Supported client operating systems include Mac OS X, all modern Windows
                            versions and Linux.
                           """ % {'depends': ', '.join(depends)}))

        history = self.get_version_history(revision)
        for major, minor, rev, msgs, date in history:
            self.major = major
            self.minor = minor
            self.revision = rev

        history.reverse()
        logs = []
        for major, minor, rev, msgs, date in history:
            infos = ''
            for msg in msgs:
                lines = msg.split('\n')
                infos += '  * %s\n' % lines[0]
                for l in lines[1:]:
                    infos += '    %s\n' % l

            logs.append(textwrap.dedent("""\
            vpnease (%s.%s.%s) dapper; urgency=high

            %s
             -- VPNease support <support@vpnease.com>  %s
            """) % (major, minor, rev, infos, date))

        changelog = '\n'.join(logs)
        bd.write('vpnease/debian/changelog', changelog, append=False, perms=0644)

        bd.build_deb_from_source(workdir, nodep=True)

        ver = '%s.%s.%s' % (self.major, self.minor, self.revision)
        return [[os.path.join(bd.env.path, 'vpnease_%s_all.deb' % ver), 'vpnease', ver]]

class VpnEaseBuild(build.Build):
    name = 'vpneasebuild'
    description = 'Build or update vpnease package repository'

    def get_targets(self):
        name = 'vpnease-repository'
        vers = 'r' + self.revision
        self.repository_path = os.path.join(self.builddir, '%s_%s' % (name, vers))
        self.targets = [[self.repository_path, name, vers]]

    option_list = [build.Option('--module-search-path', type='string', dest='module_search_path', required=False),
                   build.Option('--major', type='string', dest='major', required=False),
                   build.Option('--minor', type='string', dest='minor', required=False),
                   build.Option('--vpnease-repokey', type='string', dest='vpnease_repokey', required=False),
                   build.Option('--ubuntu-repokey', type='string', dest='ubuntu_repokey', required=False),
                   build.Option('--kernel-path', type='string', dest='kernel_path', required=False),
                   build.Option('--openswan-path', type='string', dest='openswan_path', required=False),
                   build.Option('--l2tpgw-path', type='string', dest='l2tpgw_path', required=False),
                   build.Option('--ezipupdate-path', type='string', dest='ezipupdate_path', required=False),
                   build.Option('--basefiles-path', type='string', dest='basefiles_path', required=False),
                   build.Option('--monit-path', type='string', dest='monit_path', required=False),
                   build.Option('--openl2tp-path', type='string', dest='openl2tp_path', required=False),
                   build.Option('--ippool-path', type='string', dest='ippool_path', required=False),
                   build.Option('--twisted-path', type='string', dest='twisted_path', required=False),
                   build.Option('--nevow-path', type='string', dest='nevow_path', required=False),
                   build.Option('--formal-path', type='string', dest='formal_path', required=False),
                   build.Option('--rrd-path', type='string', dest='rrd_path', required=False),
                   build.Option('--ppp-path', type='string', dest='ppp_path', required=False),
                   build.Option('--casper-path', type='string', dest='casper_path', required=False),
                   build.Option('--libnfnetlink-path', type='string', dest='libnfnetlink_path', required=False),
                   build.Option('--libnetfilter-conntrack-path', type='string', dest='libnetfilter_conntrack_path', required=False),
                   build.Option('--conntrack-path', type='string', dest='conntrack_path', required=False),
                   build.Option('--iptables-path', type='string', dest='iptables_path', required=False),
                   build.Option('--usplash-path', type='string', dest='usplash_path', required=False),
                   build.Option('--sqlalchemy-path', type='string', dest='sqlalchemy_path', required=False),
                   build.Option('--matplotlib-path', type='string', dest='matplotlib_path', required=False),
                   build.Option('--pythonapsw-path', type='string', dest='pythonapsw_path', required=False),
                   build.Option('--freeradius-path', type='string', dest='freeradius_path', required=False),
                   build.Option('--radiusclientng-path', type='string', dest='radiusclientng_path', required=False),
                   build.Option('--syslog-path', type='string', dest='syslog_path', required=False),
                   build.Option('--firefox-path', type='string', dest='firefox_path', required=False)]

    defaults = {
        'module_search_path': '_build_temp',
        'major': '1',
        'minor': '2',
        'vpnease_repokey': '5D31534A',
        'ubuntu_repokey': '5D31534A'}

    def init(self, b):
        build.Build.init(self, b)
        self.write_default_buildinfo(b)

    def run(self, b):
        bd = b.get_cwd(self.builddir)
        b.info('Building repository:')

        kernels = [{'name': KernelBuild.get_name(), 'option': 'kernel_path'}]
        modules = [
            {'name': OpenswanBuild.get_name(), 'option': 'openswan_path'},
            {'name': EzipupdateBuild.get_name(), 'option': 'ezipupdate_path'},
            {'name': BasefilesBuild.get_name(), 'option': 'basefiles_path'},
            {'name': MonitBuild.get_name(), 'option': 'monit_path'},
            {'name': IppoolBuild.get_name(), 'option': 'ippool_path'},
            {'name': OpenL2tpBuild.get_name(), 'option': 'openl2tp_path'},
            {'name': TwistedBuild.get_name(), 'option': 'twisted_path'},
            {'name': NevowBuild.get_name(), 'option': 'nevow_path'},
            {'name': FormalBuild.get_name(), 'option': 'formal_path'},
            {'name': RrdBuild.get_name(), 'option': 'rrd_path'},
            {'name': PppBuild.get_name(), 'option': 'ppp_path'},
            {'name': CasperBuild.get_name(), 'option': 'casper_path'},
            {'name': LibNfNetlinkBuild.get_name(), 'option': 'libnfnetlink_path'},
            {'name': LibNetFilterConntrackBuild.get_name(), 'option': 'libnetfilter_conntrack_path'},
            {'name': ConntrackBuild.get_name(), 'option': 'conntrack_path'},
            {'name': IptablesBuild.get_name(), 'option': 'iptables_path'},
            {'name': L2tpgwBuild.get_name(), 'option': 'l2tpgw_path'},
            {'name': UsplashBuild.get_name(), 'option': 'usplash_path'},
            {'name': SqlalchemyBuild.get_name(), 'option': 'sqlalchemy_path'},
            {'name': MatplotlibBuild.get_name(), 'option': 'matplotlib_path'},
            {'name': PythonApswBuild.get_name(), 'option': 'pythonapsw_path'},
            {'name': FreeradiusBuild.get_name(), 'option': 'freeradius_path'},
            {'name': RadiusclientNgBuild.get_name(), 'option': 'radiusclientng_path'},
            {'name': FirefoxBuild.get_name(), 'option': 'firefox_path'},
            {'name': SyslogBuild.get_name(), 'option': 'syslog_path'},
            {'name': SnmpdBuild.get_name(), 'option': 'syslog_path'}]

        extra = [
            ]

        all_depends = kernels + modules

        b.info('Previously built modules included:')
        module_info = ''
        re_name = re.compile(r'buildname: (.*?)$')
        re_version = re.compile(r'revision: (.*?)$')
        re_target = re.compile(r'targets: (.*?)$')
        all_targets = []
        extra_targets = []
        for m in all_depends + extra:
            m['revision'] = 'unknown'
            m['targets'] = []
            opt = getattr(self.options, m['option'])
            if opt is None:
                m['path'] = os.path.join(self.srcdir, os.path.join(self.options.module_search_path, m['name']))
            else:
                m['path'] = os.path.join(self.srcdir, opt)

            info_file = os.path.join(m['path'], 'buildinfo.txt')
            if not os.path.exists(info_file):
                raise build.BuildError('missing buildinfo: %s' % info_file)

            f = open(info_file)
            targets = []
            for l in f.read().split('\n'):
                r = re_name.match(l)
                if r is not None:
                    if m['name'] != r.groups(1)[0]:
                        raise build.BuildError('Found module name: %s, expecting: %s' % (r.groups(1), m['name']))
                    continue

                r = re_version.match(l)
                if r is not None:
                    m['revision'] = r.groups(1)[0]
                    continue

                r = re_target.match(l)
                if r is not None:
                    a = r.groups(1)[0]
                    for t in a[2:len(a)-2].split('], ['):
                        target = []
                        for i in t.split(', '):
                            target.append(i.strip('\'').rstrip('\''))
                        if len(target) != 3:
                            raise build.BuildError(Exception('Module buildinfo.txt broken: %s' % target))
                        targets.append(target)
                        if m not in extra:
                            all_targets.append(target)

            m['targets'] = []
            for t in targets:
                path = os.path.join(m['path'], t[0])
                if not os.path.exists(path):
                    raise build.BuildError('path does not exist: %s' % path)
                m['targets'].append([path] + t[1:])

            module_info += textwrap.dedent("""\

            [included module]
            name: %s
            revision: %s
            targets: %s
            """) % (m['name'], m['revision'], m['targets'])
            b.info('  %s, %s, %s' % (m['name'], m['revision'], m['targets']))

        # Update buildinfo.txt
        self.write_buildinfo(b, module_info, append=True)

        b.info('  all targets: %s' % str(all_targets))

        v = VpnEaseHelper(b)
        vpnease_targets = v.build(b, bd, all_targets, self.revision, self.srcdir)

        b.info('  Creating repository:')

        confdir = os.path.join(self.repository_path, 'conf')

        b.makedirs(confdir)

        helpers.write_file(os.path.join(confdir, 'distributions'), textwrap.dedent("""\
        Label: VPNease
        Suite: dapper
        Codename: dapper
        Version: %s.%s
        Architectures: i386
        Components: main
        Description: VPNease packages
        SignWith: %s
        """ % (self.options.major, self.options.minor, self.options.vpnease_repokey)))

        myenv = os.environ
        myenv['GNUPGHOME'] = os.path.join(b.srcdir, 'gnupg')
        b.ex('reprepro', '-b', self.repository_path, 'check', env=myenv)

        b.info('  Adding packages to repository:')
        debs = vpnease_targets
        for m in modules:
            b.info('  Installing packages: %s' % m['targets'])
            for t in m['targets']:
                if t[0].endswith('.deb'):
                    debs.append(t)
                else:
                    raise build.BuildError('Unknown target file.')

        def _add_package_to_repository(package):
            b.ex('reprepro', '-b', self.repository_path, 'includedeb', 'dapper', package)

        for i in debs:
            _add_package_to_repository(i[0])

        for k in kernels:
            b.info('  Installing patched kernel packages: %s' % k['targets'])
            for i in k['targets']:
                _add_package_to_repository(i[0])

        for e in extra:
            b.info('  Installing extra packages: %s' % e['targets'])
            for i in e['targets']:
                _add_package_to_repository(i[0])

        b.info('New vpnease repository built in %s, copy it to ode:/var/local/data/repositories/vpnease/. If building live-cd, also remember update symlinks in ode or alternatively give a direct path to repository for repositorylivecdbuild' % self.repository_path)

class AutorunHelper:
    """  $ cd l2tp-dev/src/python/webui-pages
    $ PYTHONPATH=:../ python ../codebay/l2tpserver/autorun/renderpages.py
    $ cp generated/autorun-installed.zip autorun-installed-files.zip
    $ cp generated/autorun-livecd.zip autorun-livecd-files.zip
    """

    def __init__(self, i):
        self.interface = i
        self.tmpdir = None

    def build(self, srcdir):
        self.tmpdir = '_autorun_helper'
        self.cleanup()

        self.interface.mkdir(self.tmpdir)
        bi = self.interface.get_cwd(os.path.join(self.interface.env.path, self.tmpdir))

        bi.ex('/bin/cp', '-ar', os.path.join(srcdir, 'src', 'python', 'codebay'), os.path.join(srcdir, 'src', 'python', 'webui-pages'), '.')

        myenv = dict(os.environ)
        myenv['PYTHONPATH'] = '../'

        bw = bi.get_cwd('webui-pages')
        bw.ex('/usr/bin/python', '../codebay/l2tpserver/autorun/renderpages.py', env=myenv)
        bi.ex('/bin/cp', os.path.join('webui-pages', 'generated', 'autorun-installed.zip'), 'autorun-installed-files.zip')
        bi.ex('/bin/cp', os.path.join('webui-pages', 'generated', 'autorun-livecd.zip'), 'autorun-livecd-files.zip')

        # FIXME: this is fragile: all the paths in build environments
        # up to our environment must be absolute for this to work.
        return [os.path.join(bi.env.path, 'autorun-installed-files.zip'), os.path.join(bi.env.path, 'autorun-livecd-files.zip')]

    def cleanup(self):
        if self.tmpdir is not None:
            self.interface.rmrf(self.tmpdir)


class IsolinuxHelper:
    def __init__(self, bi):
        self.bi = bi # Build interface

    # XXX: isolinux background is not used, so this should not be called
    def modify_isolinux_background(self):
        """
        # XXX: 14 or 15 colors? (indexed)
        background_file = os.path.join(self.srcdir, 'src/python/data/isolinux-background.png')
        tmpfile = os.path.join(self.builddir, 'temp_background.ppm') # no need to cleanup
        targetdir = os.path.join(bi.env.path, 'isolinux')

        # cleanup old crud..
        splash_re = re.compile('splash\..+')
        for i in os.listdir(targetdir):
            if splash_re.match(i) is not None:
                self.bi.ex('/bin/rm', os.path.join(targetdir, i))

        self.bi.ex('/usr/bin/convert', background_file, tmpfile)

        # BN: color index 7 is used for text color, index 0 is used for background
        # XXX: the color used here must exist in image palette: the assigment below has no effect for now..
        self.bi.sh("/usr/bin/ppmtolss16 '#ffffff=7' < %s > %s" % (tmpfile, 'isolinux/vpnease.rle'))
        self.bi.ex('cp', os.path.join(self.srcdir, 'src/python/data/isolinux-background.pcx'), 'isolinux/vpnease.pcx')
        """
        raise build.BuildError('do not use, not working')

    def modify_isolinux_config(self):
        """Customize Ubuntu isolinux config."""

        # XXX: could use some suitable color for gfxboot background, but this does not seem to work well..
        # GFXBOOT-BACKGROUND 0xB6875A

        configs = {}

        configs['isolinux.cfg'] = """\
        DEFAULT /casper/vmlinuz
        GFXBOOT bootlogo
        APPEND   boot=casper xforcevesa vga=785 initrd=/casper/initrd.gz ramdisk_size=1048576 root=/dev/ram rw quiet splash --
        LABEL xforcevesa
          menu label Install VPNease in safe ^graphics mode
          kernel /casper/vmlinuz
          append   boot=casper xforcevesa vga=785 initrd=/casper/initrd.gz ramdisk_size=1048576 root=/dev/ram rw quiet splash --
        LABEL install
          menu label ^Install VPNease in native graphics mode
          kernel /casper/vmlinuz
          append   boot=casper initrd=/casper/initrd.gz ramdisk_size=1048576 root=/dev/ram rw quiet splash --
        LABEL check
          menu label ^Check CD for defects
          kernel /casper/vmlinuz
          append  boot=casper integrity-check initrd=/casper/initrd.gz ramdisk_size=1048576 root=/dev/ram rw quiet splash --
        LABEL memtest
          menu label ^Memory test
          kernel /install/mt86plus
          append -
        DISPLAY isolinux.txt
        TIMEOUT 0
        PROMPT 1
        F1 f1.txt
        F2 f2.txt
        """

        """ 78 characters
        ----------------------------------------------------------------------
        """

        intro = """\

        VPNease is a clientless VPN product which uses the built-in client of
        your operating system for IPsec-protected remote access.  VPNease also
        provides site-to-site connectivity and an easy-to-use web UI.

        For more information, please see the product web site:

            http://www.vpnease.com/

        NOTE! You must accept the License Agreement and the Privacy Policy,
        available at the product web site, before using the product."""


        # XXX: all-in-one help file is different from those below..  not possible to merge.

        configs['en.hlp'] = """\
        \x04\x12F1\x14HELP\x10\x11VPNease Live CD\x10

        %(intro)s


        Press Escape to exit help.\x00
        """ % {'intro': intro}

        def _indent(indent, text):
            res = ''
            for l in text.split('\n'):
                res += '%s%s\n' % (indent, l)
            return res

        # XXX: add version information
        configs['f1.txt'] = """\
        \x19\x0c\x0f0fHELP INDEX\x0f07                                                                    \x0f09F1\x0f07

            \x0f0fThis is an install CD-ROM for VPNease.\x0f07

            %(intro)s

            \x0f0fKEY    TOPIC\x0f07
            <\x0f09F1\x0f07>   This page, the help index
            <\x0f09F2\x0f07>   Boot methods for special ways of using this CD-ROM


            Press F2 for boot details, or ENTER to """ % {'intro': _indent('            ', textwrap.dedent(intro))}


        configs['f2.txt'] = """\
        \x19\x0c\x0f0fBOOT METHODS\x0f07                                                                  \x0f09F2\x0f07

            \x0f0fAvailable boot methods:\x0f07

            \x0f0fxforcevesa\x0f07
              Install VPNease in safe graphics mode (default).
            \x0f0finstall\x0f07
              Install VPNease in native graphics mode.
            \x0f0fcheck\x0f07
              Check CD for defects.
            \x0f0fmemtest\x0f07
              Memory test.

            To use one of these boot methods, type it at the prompt, optionally
            followed by any boot parameters. For example:

                boot: install acpi=off





            Press F1 for the help index, or ENTER to """


        # NB: no help other than F1 and F2
        for i in range(3, 11):
            configs['f%s.txt' % str(i)] = None

        """  From syslinux manpage:
        <SI><bg><fg>                            <SI> = <Ctrl-O> = ASCII 15
        Set the display colors to the specified background and
        foreground colors, where <bg> and <fg> are hex digits,
        corresponding to the standard PC display attributes:

        0 = black               8 = dark grey
        1 = dark blue           9 = bright blue
        2 = dark green          a = bright green
        3 = dark cyan           b = bright cyan
        4 = dark red            c = bright red
        5 = dark purple         d = bright purple
        6 = brown               e = yellow
        7 = light grey          f = white
        
        Picking a bright color (8-f) for the background results in the
        corresponding dark color (0-7), with the foreground flashing.

        \x0c -> clear screen
        \x18 -> add splash
        """

        # XXX: this is not used now, text mode is without splash image
        # XXX: version info not available
        # \x18vpnease.rle
        configs['isolinux.txt'] = """\
        \x0c
        \x0f0f

            VPNease Live CD


        \x0f07
            Press <F1> for help and advanced options
            or just press ENTER to """

        for filename, contents in configs.iteritems():
            filepath = os.path.join('isolinux', filename)
            self.bi.ex('/bin/rm', filepath)
            if contents is not None:
                self.bi.write(filepath, textwrap.dedent(contents), perms=0644)


class LiveCDBuild(build.Build):
    name = 'livecdbuild'
    description = 'Ubuntu Live CD image with modifications'

    option_list = [build.Option('--ubuntu-image', type='string', dest='ubuntu_image', required=True),
                   build.Option('--repository-server', type='string', dest='repository_server', required=True),
                   build.Option('--major', type='string', dest='major', required=True),
                   build.Option('--minor', type='string', dest='minor', required=True),
                   build.Option('--vpnease-repokey', type='string', dest='vpnease_repokey', required=False),
                   build.Option('--ubuntu-repokey', type='string', dest='ubuntu_repokey', required=False)]

    defaults = {'repository_server': 'ode.intra.codebay.fi/data/repositories',
                'major': '1',
                'minor': '2',
                'vpnease_repokey': '5D31534A',
                'ubuntu_repokey': '5D31534A'}

    def get_targets(self):
        return [] # FIXME:

    def init(self, b):
        build.Build.init(self, b)

        if self.revision is None:
            if self.options.revision is None:
                raise build.BuildError('Build revision missing.')
            else:
                self.revision = self.options.revision

        try:
            self.revision.index(':')
            raise build.BuildError('Cannot build from mixed-version source-tree (%s), please update.' % self.revision)
        except ValueError:
            pass

        vinfos = VpnEaseHelper(b).get_version_history(self.revision)
        vinfo = vinfos[len(vinfos) - 1]

        self.target = os.path.join(self.builddir, 'vpnease_%s-%s-%s.iso' % (vinfo[0], vinfo[1], vinfo[2]))
        self.write_default_buildinfo(b)


    def install_startup_scripts(self, bi):
        # Note: other startup scritps are updated/installed in l2tpgw
        # package postinstall script, update script is the only
        # permanent script required to be present always.
        bi.ex('/usr/sbin/update-rc.d', 'vpnease-update',
              'stop', '99', '0', '1', '6', '.',
              'start', '12', '2', '3', '4', '5', '.')

    def modify_distro_startup_scripts(self, bi):
        # Note: most of the diversion of startup, etc. is done now in
        # system startup.

        # These are required so that in first live-cd boot the gdm
        # does not start too early and sysklogd is disabled
        # (l2tpgw.postinst tries to do the same thing)
        bi.ex('/usr/sbin/update-rc.d', '-f', 'sysklogd', 'remove')

        bi.ex('/usr/sbin/update-rc.d', '-f', 'gdm', 'remove')
        bi.ex('/usr/sbin/update-rc.d', 'gdm', 'stop', '01', '0', '1', '6', '.',
              'start', '26', '2', '3', '4', '5', '.')

        bi.ex('/usr/sbin/update-rc.d', '-f', 'ssh', 'remove')
        bi.ex('/usr/sbin/update-rc.d', 'ssh', 'stop', '20', '0', '1', '6', '.',
              'start', '27', '2', '3', '4', '5', '.')

    def modify_default_config(self, bi):
        # Note: not actually required anymore because we start portmap
        # ourselves now, but keep this to be safe..
        # Portmapper should bind only to local interface
        bi.write('/etc/default/portmap', '\nOPTIONS="-i 127.0.0.1"\n', append=True, perms=0644)

        # Change default fsck behaviour so that filesystem fixes are
        # done automatically
        bi.write('/etc/default/rcS', '\n# Fix errors automatically\nFSCKFIX=yes\n', append=True, perms=0644)

        # FIXME: rotating logs.
        # - Update /etc/syslog.conf ?
        # - Update/divert /etc/cron.daily/sysklogd ?

        # Remove ssh host keys
        for filename in ['ssh_host_dsa_key.pub', 'ssh_host_dsa_key',
                         'ssh_host_rsa_key.pub', 'ssh_host_rsa_key']:
            bi.ex('/bin/rm', '-f', filename)

    def run(self, b):
        bd = b.get_cwd(self.builddir)
        b.info('Building live-cd image:')

        # Check parameters
        if not os.path.exists(self.options.ubuntu_image):
            raise build.BuildError('Cannot find file: %s' % self.options.ubuntu_image)

        # Update buildinfo.txt
        module_info = '' # XXX: not used for anything.
        self.write_buildinfo(b, module_info, append=True)

        # Start build
        cdlabel = 'VPNease Live CD'  # XXX: version info

        targetdir = 'live-cd-target'
        workdir = 'workdir'

        ubuntu_repo = [{'method': 'http', 'server': '%s/ubuntu/%s.%s' % (self.options.repository_server, self.options.major, self.options.minor), 'suite': 'dapper', 'components': 'main restricted'}]
        vpnease_repo = [{'method': 'http', 'server': '%s/vpnease/%s.%s' % (self.options.repository_server, self.options.major, self.options.minor), 'suite': 'dapper', 'components': 'main'}]

        bd_target = bd.get_cwd(os.path.join(self.builddir, targetdir))
        bd_target_chroot = bd.get_chroot(os.path.join(self.builddir, targetdir))
        bd_work = bd.get_cwd(os.path.join(self.builddir, workdir))
        bd_work_chroot = bd.get_chroot(os.path.join(self.builddir, workdir))

        # Extract livecd
        bd.extract_livecd(os.path.join(self.srcdir, self.options.ubuntu_image))

        # Setup apt-key
        p = bd_work.debian_packages()
        p.remove_packages(['ubuntu-keyring'])
        p.unprepare()

        # Prepare install-time apt keys
        bd.delete_apt_keys(bd_work_chroot)
        bd.setup_apt_keys(os.path.join(self.srcdir, 'gnupg'), bd_work_chroot, [self.options.vpnease_repokey, self.options.ubuntu_repokey])

        # Note: repository order is important!
        bd.prepare_extracted_livecd(sources=vpnease_repo + ubuntu_repo)

        # Autorun setup - see wiki L2tpAutorun
        ah = AutorunHelper(bd)
        [_, autorun_livecd_zip] = ah.build(self.srcdir)
        bd_target.ex('/usr/bin/unzip', autorun_livecd_zip)
        
        # Note: kernel install options seem to be reasonably correct.
        kernels_to_purge = ['2.6.15-26', '2.6.15-25', '2.6.15-23']

        b.info('Modify filesystem:')

        # Install debs

        p = bd_work.debian_packages()

        vpnease_package_list = ['vpnease', 'casper', 'ubiquity-casper']
        b.info('  Installing packages from Ubuntu and VPNease repositories: %s' % vpnease_package_list)
        # Note: repository order is important!
        p.install_packages(vpnease_package_list, vpnease_repo + ubuntu_repo)

        b.info('  Removing old kernel packages: %s' % kernels_to_purge)
        for i in kernels_to_purge:
            p.remove_packages(['linux-image-' + i + '-386'])

        p.unprepare()

        # Set default apt sources.list

        # FIXME: get these from constants? (duplicates)
        package_server = 'packages.vpnease.com'
        default_ubuntu_path = '%s/ubuntu/%s.%s' % (package_server, self.options.major, self.options.minor)
        default_vpnease_path = '%s/vpnease/%s.%s' % (package_server, self.options.major, self.options.minor)

        # FIXME: hardcoded components and suite!
        default_sources = [{'method': 'http', 'server': default_ubuntu_path, 'suite': 'dapper', 'components': 'main restricted'},
                           {'method': 'http', 'server': default_vpnease_path, 'suite': 'dapper', 'components': 'main'}]
        p.set_apt_sources_list(default_sources)

        # Boot stuff
        b.info('  Updating boot-time kernel and initrd')

        # Note: only one kernel image should be installed, find it and copy to casper dir
        kernel_paths = [None, os.path.join(targetdir, 'casper/vmlinuz')]
        initrd_paths = [None, os.path.join(targetdir, 'casper/initrd.gz')]
        for r, d, f in bd.walk(os.path.join(workdir, 'boot')):
            for i in f:
                if i.startswith('vmlinuz-'):
                    kernel_paths[0] =  os.path.join(r, i)
                if i.startswith('initrd.img-'):
                    initrd_paths[0] = os.path.join(r, i)
            break

        for i in [kernel_paths, initrd_paths]:
            if i[0] is None:
                raise build.BuildError('Missing source file for destination: %s' % i[1])
            bd.ex('cp', '-f', i[0], i[1])

        # Helpers scripts (not required)
        # b.info('  Installing helper scripts')
        # bd_work_chroot.install_graphics_scripts()

        # Graphics customizations
        ih = IsolinuxHelper(bd_target)
        ih.modify_isolinux_config()

        # XXX: refactor with above..
        bd.ex('cp', '-ar', os.path.join(self.srcdir, 'gfxboot-theme-ubuntu-0.1.27+codebay'), '.')
        bg = bd.get_cwd('gfxboot-theme-ubuntu-0.1.27+codebay')
        bg.ex('make')
        bg.ex('cp', 'splash.jpg', 'install/back.jpg', 'install/bootlogo', 'install/16x16.fnt', os.path.join(bd_target.env.path, 'isolinux'))

        # Modify system default configuration
        b.info('  Modify default config')
        self.modify_default_config(bd_work_chroot)

        # Distro startup modifs
        b.info('  Distro startup modifications')
        self.modify_distro_startup_scripts(bd_work_chroot)

        # FIMXE: this part could be made by the post-install script of the naftalin-update package

        # Files required for product update are copied to permanent storage
        update_tmp = 'update-tmp'
        backup_store = 'var/lib/l2tpgw-permanent'

        bd.ex('mkdir', '-p', update_tmp)
        bd_work.ex('mkdir', '-p', backup_store)
        bd_work.ex('chmod', '0755', backup_store)
        ud = bd.get_cwd(update_tmp)
        
        # Copy permanent scripts and files into place (NOTE: we want these from the *fixed* repo version!)
        for s, d in [ ['src/python/postupdate/backup-files/update-files.zip', '%s/update-files.zip' % backup_store],
                      ['src/python/postupdate/backup-files/vpnease-init', 'etc/init.d/vpnease-init'],
                      ['src/python/postupdate/backup-files/vpnease-update', 'etc/init.d/vpnease-update'] ]:
            bd.ex('cp', os.path.join(self.srcdir, s), os.path.join(bd_work.env.path, d))
            bd.ex('chmod', '0755', os.path.join(bd_work.env.path, d))

        # Install vpnease startup scripts
        b.info('  Installing server startup scripts')
        self.install_startup_scripts(bd_work_chroot)

        # Build naftalin; this is not directly used in the build, but can be manually stored
        u_files = [ ('usr/lib/python2.4/site-packages/',
                     [ 'Crypto', 'codebay.zip', 'codebay.pth', 'formal', 'nevow', 'OpenSSL', 'RDF.py', 'sqlite', 'twisted']) ]

        u_names = []

        for base, names in u_files:
            for name in names:
                ud.ex('cp', '-r', os.path.join(bd_work.env.path, base, name), '.')
                u_names.append(name)

        ud.ex('mkdir', '-p', 'scripts')
        for i in ['usr/lib/l2tpgw/l2tpgw-update', 'usr/lib/l2tpgw/l2tpgw-update-product', 'usr/lib/l2tpgw/l2tpgw-runner']:
            ud.ex('cp', os.path.join(bd_work.env.path, i), 'scripts')

        ud.ex(['zip', '-r', 'update-files.zip', 'scripts'] + u_names)

        naftalin = 'naftalin'
        bd.ex('mkdir', '-p', naftalin)

        for p, f in [[ud.env.path, 'update-files.zip'],
                     [os.path.join(self.srcdir, 'src', 'python', 'data'), 'vpnease-init'],
                     [os.path.join(self.srcdir, 'src', 'python', 'data'), 'vpnease-update']]:
            bd.ex('cp', os.path.join(p, f), naftalin)
            bn = bd.get_cwd(naftalin)
            bn.sh('/usr/bin/md5sum %s > %s.md5' % (f, f))

        # Remove keys used for installation: update process gets keys from management server
        bd.delete_apt_keys(bd_work_chroot)

        # Package livecd fsimage (squashfs)
        #bd.package_livecd_image(self.builddir, cdlabel, self.target, osx_autorun=osx_autorun_html)  DOESN'T WORK
        bd.package_livecd_image(self.builddir, cdlabel, self.target)


class TestclientLiveCDBuild(build.Build):
    name = 'testclientlivecdbuild'
    description = 'Ubuntu Live CD image with modifications for testclient'

    option_list = [build.Option('--ubuntu-image', type='string', dest='ubuntu_image', required=True),
                   build.Option('--major', type='string', dest='major', required=True),
                   build.Option('--minor', type='string', dest='minor', required=True),
                   build.Option('--repository-server', type='string', dest='repository_server', required=True),
                   build.Option('--ubuntu-repokey', type='string', dest='ubuntu_repokey', required=False)]

    defaults = {'repository_server': 'ode.intra.codebay.fi/data/repositories',
                'major': '1',
                'minor': '2',
                'ubuntu_repokey': '927E0039'}

    def get_targets(self):
        return [] # FIXME:

    def init(self, b):
        build.Build.init(self, b)

        if self.revision is None:
            if self.options.revision is None:
                raise build.BuildError('Build revision missing.')
            else:
                self.revision = self.options.revision

        try:
            self.revision.index(':')
            raise build.BuildError('Cannot build from mixed-version source-tree (%s), please update.' % self.revision)
        except ValueError:
            pass

        self.target = os.path.join(self.builddir, 'testclient_%s.iso' % (self.revision))
        self.write_default_buildinfo(b)

    def run(self, b):
        bd = b.get_cwd(self.builddir)
        b.info('Building testclient image:')

        # Check parameters
        if not os.path.exists(self.options.ubuntu_image):
            raise build.BuildError('Cannot find file: %s' % self.options.ubuntu_image)

        # Update buildinfo.txt
        module_info = '' # XXX: not used for anything.
        self.write_buildinfo(b, module_info, append=True)

        cdlabel = 'Testclient'

        targetdir = 'live-cd-target'
        workdir = 'workdir'

        ubuntu_repo = [{'method': 'http', 'server': '%s/ubuntu/%s.%s' % (self.options.repository_server, self.options.major, self.options.minor), 'suite': 'dapper', 'components': 'main restricted'}]

        bd_target = bd.get_cwd(os.path.join(self.builddir, targetdir))
        bd_target_chroot = bd.get_chroot(os.path.join(self.builddir, targetdir))
        bd_work = bd.get_cwd(os.path.join(self.builddir, workdir))
        bd_work_chroot = bd.get_chroot(os.path.join(self.builddir, workdir))

        # Extract livecd
        bd.extract_livecd(os.path.join(self.srcdir, self.options.ubuntu_image))

        # Setup apt-key
        bd.setup_apt_keys(os.path.join(self.srcdir, 'gnupg'), bd_work_chroot, [self.options.ubuntu_repokey])

        bd.prepare_extracted_livecd(sources=ubuntu_repo)

        # Note: kernel install options seem to be reasonably correct.
        kernels_to_purge = ['2.6.15-25', '2.6.15-23']

        b.info('Modify filesystem:')

        # Install debs

        p = bd_work.debian_packages()

        # XXX: not required anymore, because vpnease package depends on these
        # Install required ubuntu packages
        # p.install_packages(['gawk', 'ssh', 'portmap', 'ipsec-tools', 'libltdl3'], ubuntu_repo)

        # Install kernel and other relevant packages
        pkg_path = os.path.join(self.srcdir, 'testclient', 'binaries')
        p.install_kernels([os.path.join(pkg_path, 'linux-image-2.6.15-27-386_2.6.15-27.testclient+codebay+r5164_i386.deb')])
        pkglist = []

        for pkg in ['openl2tp_0.10+testclient_i386.deb', 'openswan_2.3.0-1_i386.deb', 'ippool_0.4_i386.deb', 'ppp_2.4.4b1+codebay+r5121_i386.deb']:
            pkglist += [os.path.join(pkg_path, pkg)]
        # NB: must install at the same time because of dependencies
        p.install_from_debs(pkglist)

        b.info('  Removing old kernel packages: %s' % kernels_to_purge)
        for i in kernels_to_purge:
            p.remove_packages(['linux-image-' + i + '-386'])

        p.unprepare()

        package_server = 'packages.vpnease.com'
        default_ubuntu_path = '%s/ubuntu/%s.%s' % (package_server, self.options.major, self.options.minor)
        default_sources = [{'method': 'http', 'server': default_ubuntu_path, 'suite': 'dapper', 'components': 'main restricted'}]
        p.set_apt_sources_list(default_sources)

        # Boot stuff
        b.info('  Updating boot-time kernel and initrd')

        # Note: only one kernel image should be installed, find it and copy to casper dir
        kernel_paths = [None, os.path.join(targetdir, 'casper/vmlinuz')]
        initrd_paths = [None, os.path.join(targetdir, 'casper/initrd.gz')]
        for r, d, f in bd.walk(os.path.join(workdir, 'boot')):
            for i in f:
                if i.startswith('vmlinuz-'):
                    kernel_paths[0] =  os.path.join(r, i)
                if i.startswith('initrd.img-'):
                    initrd_paths[0] = os.path.join(r, i)
            break

        for i in [kernel_paths, initrd_paths]:
            if i[0] is None:
                raise build.BuildError('Missing source file for destination: %s' % i[1])
            bd.ex('cp', '-f', i[0], i[1])


        # Graphics customizations
        # self.modify_isolinux_config(bd_target)
        # bd.ex('cp', '-ar', os.path.join(self.srcdir, 'gfxboot-theme-ubuntu-0.1.27+codebay'), '.')
        # bg = bd.get_cwd('gfxboot-theme-ubuntu-0.1.27+codebay')
        # bg.ex('make')
        # bg.ex('cp', 'splash.jpg', 'install/back.jpg', 'install/bootlogo', 'install/16x16.fnt', os.path.join(bd_target.env.path, 'isolinux'))

        # Package livecd fsimage (squashfs)
        bd.package_livecd_image(self.builddir, cdlabel, self.target)


class OpenL2tpBuild(DebSourceBuild):
    name = 'openl2tpbuild'
    description = 'Build patched OpenL2tp debian package.'
    debsrcname = 'openl2tp'
    debname = 'openl2tp'
    debver = '0.10'
    deborigversion = '0.10'

    def run(self, b):
        sources = 'openl2tp-0.10+codebay'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, sources), '.')

        bd.changelog_newversion(sources, '0.10', 'New upstream release.')
        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.build_deb_from_source(sources)

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'openl2tp-0.10+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, sources)

        bd.changelog_newversion(sources, '0.10', 'New upstream release.')
        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

    def get_deb_source_files(self):
        return [os.path.join('openl2tp', 'openl2tp-0.10.tar.gz')]

class UsplashBuild(DebSourceBuild):
    name = 'usplashbuild'
    description = 'Usplash.'
    debsrcname = 'usplash'
    debname = 'usplash'
    debver = '0.2'
    sdir = 'usplash'
    deborigversion = '0.2'
    deborigrevision = '4'

    def run(self, b):
        sources = 'usplash-0.2+codebay'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, sources), '.')

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.build_deb_from_source(sources)

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'usplash-0.2+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

class MatplotlibBuild(DebSourceBuild):
    name = 'matplotlibbuild'
    description = 'Matplotlib'
    sdir = 'matplotlib'
    debsrcname = 'matplotlib'
    debname = None
    debver = '0.82'
    deborigversion = '0.82'
    deborigrevision = '5ubuntu1'
    patchnames = ['control.diff']

    def get_targets(self):
        return [self.get_deb_target(name='python-matplotlib', arch='all'),
                self.get_deb_target(name='python2.4-matplotlib'),
                self.get_deb_target(name='python-matplotlib-data', arch='all')]

    def run(self, b):
        self.build_deb(b)

class SqlalchemyBuild(DebSourceBuild):
    name = 'sqlalchemybuild'
    description = 'Build SQLAlchemy for dapper'
    sdir = 'sqlalchemy'
    debsrcname = 'sqlalchemy'
    debname = None
    debver = '0.3.6'
    deborigversion = '0.3.6'
    deborigrevision = '2'

    def get_targets(self):
        return [self.get_deb_target(name='python-sqlalchemy', arch='all')]

    def run(self, b):
        sources = 'sqlalchemy-0.3.6+codebay'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, os.path.join('sqlalchemy', sources)), '.')

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.build_deb_from_source(sources)

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'sqlalchemy-0.3.6+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, os.path.join('sqlalchemy', sources), dest=sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

class PythonApswBuild(DebSourceBuild):
    name = 'pythonapswbuild'
    description = 'Build python-apsw for dapper'
    debsrcname = 'python-apsw'
    debname = None
    debver = '3.2.7r1'
    sdir = 'apsw'
    deborigversion = '3.2.7r1'
    deborigrevision = '1'
    patchnames = ['pythonver.diff']

    def get_targets(self):
        return [self.get_deb_target(name='python-apsw', arch='all'),
                self.get_deb_target(name='python2.4-apsw', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class IppoolBuild(DebSourceBuild):
    name = 'ippoolbuild'
    description = 'Ippool debian package.'
    debsrcname = 'ippool'
    debname = 'ippool'
    debver = '0.4'
    deborigversion = '0.4'

    def run(self, b):
        sources = 'ippool-0.4+codebay'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, sources), '.')

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.build_deb_from_source(sources)

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'ippool-0.4+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

    def get_deb_source_files(self):
        return [os.path.join('openl2tp', 'ippool-0.4.tar.gz')]

class OpenswanBuild(DebSourceBuild):
    name = 'openswanbuild'
    description = 'Build OpenSwan debian package with patches.'
    debsrcname = 'openswan'
    debname = 'openswan'
    debver = '2.4.0rc4'
    sdir = 'openswan'
    deborigversion = '2.4.0rc4'
    deborigrevision = None

    def run(self, b):
        sources = 'openswan-2.4.0rc4.quilt'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, os.path.join('openswan', sources)), '.')

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included.')
        bd_q = bd.get_cwd(sources)
        bd_q.ex('quilt', 'push', '-a')
        bd.build_deb_from_source(sources, nodep=True)


    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'openswan-2.4.0rc4.quilt'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, os.path.join('openswan', sources), dest=sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd_q = bd.get_cwd(sources)
        bd_q.ex('quilt', 'push', '-a')

        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)


class MonitBuild(DebSourceBuild):
    name = 'monitbuild'
    description = 'Build Monit package for Ubuntu'
    sdir='monit'
    debsrcname = 'monit'
    debname = 'monit'
    debver = '4.8.1'
    debprefix = '1'
    deborigversion='4.8.1'
    deborigrevision='2'
    patchnames=[]

    def run(self, b):
        self.build_deb(b)

class EzipupdateBuild(DebSourceBuild):
    name = 'ezipupdatebuild'
    description = 'Build ez-ipupdate package for Ubuntu'
    debsrcname = 'ez-ipupdate'
    debname = 'ez-ipupdate'
    debver = '3.0.11b8'
    sdir='ez-ipupdate'
    deborigversion='3.0.11b8'
    deborigrevision='10'
    patchnames=['clock.diff', 'daemon-plus-address-fix.diff']

    def run(self, b):
        self.build_deb(b)

class BasefilesBuild(DebSourceBuild):
    name = 'basefilesbuild'
    description = 'Build base-files package for Ubuntu'
    debsrcname = 'base-files'
    debname = 'base-files'
    debver = '3.1.9ubuntu7.2'
    sdir='base-files'
    deborigversion='3.1.9ubuntu7.2'
#    deborigrevision=''
    patchnames=['issue.diff']

    def run(self, b):
        self.build_deb(b)

class FormalBuild(DebSourceBuild):
    name = 'formalbuild'
    description = 'Build formal package for Ubuntu'
    debsrcname = 'formal'
    debname = 'formal'
    debver = '0.9.3'

    def run(self, b):
        sources = 'forms'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, os.path.join('formal/r252', sources)), '.')

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included.')
        bd.build_deb_from_source('forms')

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'forms'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, os.path.join('formal', 'r252', sources), dest=sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

    def get_deb_dirname(self):
        return 'formal_r252'


class RrdBuild(DebSourceBuild):
    name = 'rrdbuild'
    description = 'Build rrdtool and co. packages for Ubuntu dapper'
    debsrcname = 'rrdtool'
    debname = None
    debver = '1.2.11'
    sdir='rrdtool'
    deborigversion='1.2.11'
    deborigrevision='0.5ubuntu3'
    patchnames=[]

    def get_targets(self):
        return [self.get_deb_target(name='rrdtool'),
                self.get_deb_target(name='librrd2'),
                self.get_deb_target(name='python-rrd', arch='all'),
                self.get_deb_target(name='python2.4-rrd')]

    def run(self, b):
        self.build_deb(b)

class PppBuild(DebSourceBuild):
    name = 'pppbuild'
    description = 'Build patched ppp packege for Ubuntu dapper'
    debsrcname = 'ppp'
    debname = None
    debver = '2.4.4b1'
    sdir='ppp'
    deborigversion='2.4.4b1'
    deborigrevision='1ubuntu3.1'
    patchnames=['control.diff']

    def get_targets(self):
        return [self.get_deb_target(name='ppp'),
                self.get_deb_target(name='ppp-dev', arch='all')]

    def _patch(self, b, debdir):
        bd = b.get_cwd(self.builddir)

        # 'chap-preference-2.4.4re1.diff' not needed now
        for p in ['mppe-mppc-1.1-2.4.3-adapted',
                  'auth-result-hook',
                  'wait-child',
                  'radacct-removed']:
            bd.ex('cp', os.path.join(self.srcdir, 'ppp/ppp_2.4.4b1-' + p + '.diff'), os.path.join(debdir, 'debian/patches/'))

    def run(self, b):
        self.build_deb(b, patchfunc=self._patch)

    def run_source(self, b, release_revision):
        return self.build_source_deb(b, release_revision, patchfunc=self._patch,)

class CasperBuild(DebSourceBuild):
    name = 'casperbuild'
    description = 'Build casper package for Ubuntu'
    debsrcname = 'casper'
    debname = 'casper'
    debver = '1.57'
    sdir='casper'
    deborigversion='1.57'
    deborigrevision=None
    patchnames=['l2tpgw.patch']

    def get_targets(self):
        return [self.get_deb_target(name='casper'),
                self.get_deb_target(name='ubiquity-casper', arch='all')]

    def run(self, b):
        self.build_deb(b)


# FIXME: need to install -dev package in build machine before continuing
# For now -dev package are found only in build -dir.
class LibNfNetlinkBuild(DebSourceBuild):
    name = 'libnfnetlinkbuild'
    description = 'Build libnfnetlink for Ubuntu'
    debsrcname = 'libnfnetlink'
    debname = 'libnfnetlink0'
    debver = '0.0.16'
    sdir='netfilter'
    deborigversion='0.0.16'
    deborigrevision=None
    patchnames=[]

    def run(self, b):
        self.build_deb(b)

# FIXME: need to install -dev package in build machine before continuing
# For now -dev package are found only in build -dir.
class LibNetFilterConntrackBuild(DebSourceBuild):
    name = 'libnetfilterconntrackbuild'
    description = 'Build libnetfilter-conntrack for Ubuntu'
    debsrcname = 'libnetfilter-conntrack'
    debname = 'libnetfilter-conntrack1'
    debver = '0.0.31'
    sdir='netfilter'
    deborigversion='0.0.31'
    deborigrevision=None
    patchnames=[]

    def run(self, b):
        self.build_deb(b)

class ConntrackBuild(DebSourceBuild):
    name = 'conntrackbuild'
    description = 'Build conntrack for Ubuntu'
    debsrcname = 'conntrack'
    debname = None
    debver = '1.00beta2'
    sdir='netfilter'
    deborigversion='1.00beta2'
    deborigrevision=None
    patchnames=[]
    
    def get_targets(self):
        return [self.get_deb_target(name='conntrack'),
                self.get_deb_target(name='libconntrack-extensions')]

    def run(self, b):
        self.build_deb(b)

class NevowBuild(DebSourceBuild):
    name = 'nevowbuild'
    description = 'Build python nevow package for Ubuntu'
    debsrcname = 'nevow'
    debname = None
    debver = '0.9.0'
    sdir='dapper_twisted'
    deborigversion='0.9.0'
    deborigrevision=None
    patchnames=[]

    def get_targets(self):
        return [self.get_deb_target(name='python-nevow', arch='all'),
                self.get_deb_target(name='python2.4-nevow', arch='all')]

    def run(self, b):
        self.build_deb(b)

class FreeradiusBuild(DebSourceBuild):
    name = 'freeradiusbuild'
    description = 'Build freeradius package for Ubuntu dapper'
    debsrcname = 'freeradius'
    debname = None
    debver = '1.1.6'
    sdir='freeradius'
    deborigversion='1.1.6'
    deborigrevision='2'
    patchnames=['ssl_depend_and_dpkg_depend.diff',
                'proxy_bind_any_address.diff']

    def get_targets(self):
        # XXX: dbg, iodbc, dialupadmin?
        return [self.get_deb_target(name='freeradius', arch='i386'),
                self.get_deb_target(name='freeradius-krb5', arch='i386'),
                self.get_deb_target(name='freeradius-ldap', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class RadiusclientBuild(DebSourceBuild):
    name = 'radiusclientbuild'
    description = 'Build radiusclient package for Ubuntu dapper'
    debsrcname = 'radiusclient'
    debname = None
    debver = '0.3.2'
    sdir='radiusclient'
    deborigversion='0.3.2'
    deborigrevision='8'
    patchnames=[]

    def get_targets(self):
        return [self.get_deb_target(name='radiusclient1', arch='i386'),
                self.get_deb_target(name='libradius1', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class RadiusclientNgBuild(DebSourceBuild):
    name = 'radiusclientngbuild'
    description = 'Build radiusclient-ng package for Ubuntu dapper'
    debsrcname = 'radiusclient-ng'
    debname = None
    debver = '0.5.5'
    sdir='radiusclient-ng'
    deborigversion='0.5.5'
    deborigrevision='1'
    patchnames=[]

    def get_targets(self):
        return [self.get_deb_target(name='libradiusclient-ng2', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class FirefoxBuild(DebSourceBuild):
    name = 'firefoxbuild'
    description = 'Build firefox 2.x package for Ubuntu dapper'
    debsrcname = 'firefox'
    debname = None
    debver = '2.0.0.13+0nobinonly'
    sdir='firefox'
    deborigversion='2.0.0.13+0nobinonly'
    deborigrevision='0ubuntu0.6.10'
    patchnames=['control.diff']

    def get_targets(self):
        return [self.get_deb_target(name='firefox', arch='i386'),
                self.get_deb_target(name='libnss3', arch='i386',
                                    version=self.get_deb_ver(ver='1.firefox2.0.0.13+0nobinonly', deb_prefix='2'),
                                    fileversion=self.get_plain_deb_ver(ver='1.firefox2.0.0.13+0nobinonly')),
                self.get_deb_target(name='libnspr4', arch='i386',
                                    version=self.get_deb_ver(ver='1.firefox2.0.0.13+0nobinonly', deb_prefix='2'),
                                    fileversion=self.get_plain_deb_ver(ver='1.firefox2.0.0.13+0nobinonly')),
                self.get_deb_target(name='firefox-gnome-support', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class SyslogBuild(DebSourceBuild):
    name = 'syslogbuild'
    description = 'Build patched sysklogd for Ubuntu dapper'
    debsrcname = 'sysklogd'
    debname = None
    debver = '1.4.1'
    sdir='syslog'
    deborigversion='1.4.1'
    deborigrevision='17ubuntu7.1'
    patchnames=['remove-startup.diff']

    def get_targets(self):
        return [self.get_deb_target(name='klogd', arch='i386'),
                self.get_deb_target(name='sysklogd', arch='i386')]

    def run(self, b):
        self.build_deb(b)

class SnmpdBuild(DebSourceBuild):
    name = 'snmpdbuild'
    description = 'Build patched snmpd for Ubuntu dapper'
    debsrcname = 'net-snmp'
    debname = None
    debver = '5.2.1.2'
    sdir='snmp'
    deborigversion='5.2.1.2'
    deborigrevision='4ubuntu2.2'
    patchnames=['ignore_ppp_interfaces.diff',
                'early_pidfile.diff',
                'smux_disabled.diff',
                'disable_ipv6.diff']

    def get_targets(self):
        return [self.get_deb_target(name='snmp', arch='i386'),
                self.get_deb_target(name='snmpd', arch='i386'),
                self.get_deb_target(name='libsnmp9', arch='i386'),
                self.get_deb_target(name='libsnmp-base', arch='all')]

    def run(self, b):
        self.build_deb(b)

class BinaryPackage:
    def __init__(self, name, version, revision, arch, nodep=False, deb_prefix=None):
        self.name = name
        self.version = version
        self.revision = revision
        self.arch = arch
        self.deb_prefix = deb_prefix

    def filename(self):
        n = self.name + '_' + self.version
        if self.revision is not None:
            n += '-' + self.revision
        n += '_' + self.arch + '.deb'
        return n

    def target(self):
        ver = self.version
        if self.deb_prefix is not None:
            ver = self.deb_prefix + ':' + self.version
        return [self.filename(), self.name, ver]

class SourcePackage:
    def __init__(self, name, version, revision, build_revision, binaries=[], nodep=False, deb_prefix=None):
        self.name = name
        self.version = version
        self.revision = revision
        self.build_revision = build_revision
        self.binary_packages = []
        self.patches = []
        for i in binaries:
            self.binary_packages.append(i)
        self.nodep = nodep
        self.deb_prefix = deb_prefix

    def check_revision(self):
        try:
            self.build_revision.index(':')
            raise build.BuildError('Cannot build from mixed-version source-tree (%s), please update.' % self.build_revision)
        except ValueError:
            pass

    def get_deb_ver(self):
        self.check_revision()
        return '%s+codebay+r%s' % (self.version, self.build_revision)

    def get_debprefix(self):
        return self.deb_prefix

    def add_binary(self, name, arch):
        self.binary_packages.append(BinaryPackage(name, self.get_deb_ver(), None, arch, deb_prefix=self.deb_prefix))

    def add_patch(self, patchname):
        self.patches.append(patchname)

    def filename(self):
        n = self.name + '_' + self.version
        if self.revision is not None:
            n += '-' + self.revision
        n += '.dsc'
        return n

    def orig_dirname(self):
        return self.name + '-' + self.version

    def new_dirname(self):
        return self.name + '-' + self.get_deb_ver()

    def binaryfiles(self):
        b = []
        for i in self.binary_packages:
            b.append(i.filename())
        return b

    def binarytargets(self):
        b = []
        for i in self.binary_packages:
            b.append(i.target())
        return b

    def patch_files(self):
        p = []
        for i in self.patches:
            p.append(self.name + '_' + self.version + '-' + i)
        return p

class TwistedBuild(DebSourceBuild):
    name = 'twistedbuild'
    description = 'Build python twisted packages for Ubuntu'
    debver = None

    def get_targets(self):
        self.packages = []
        s = SourcePackage('twisted', '2.4.0', None, self.revision)
        s.add_binary('python2.4-twisted', 'all')
        s.add_binary('python2.4-twisted-bin', 'i386')
        s.add_binary('python2.4-twisted-core', 'all')
        s.add_binary('python-twisted', 'all')
        s.add_binary('python-twisted-core', 'all')

        # Not required
        # s.add_binary('twisted-doc', 'all')
        # s.add_binary('twisted-doc-api', 'all')
        # s.add_patch('diff-syslog-facility-log-daemon.diff')
        self.packages.append(s)

        s = SourcePackage('twisted-conch', '0.7.0', '1', self.revision, nodep=True, deb_prefix='1')
        s.add_binary('python2.4-twisted-conch', 'all')
        s.add_binary('python-twisted-conch', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-lore', '0.2.0', '2', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-lore', 'all')
        s.add_binary('python-twisted-lore', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-mail', '0.3.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-mail', 'all')
        s.add_binary('python-twisted-mail', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-names', '0.3.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-names', 'all')
        s.add_binary('python-twisted-names', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-news', '0.2.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-news', 'all')
        s.add_binary('python-twisted-news', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-runner', '0.2.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-runner', 'i386')
        s.add_binary('python-twisted-runner', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-web', '0.6.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-web', 'all')
        s.add_binary('python-twisted-web', 'all')
        self.packages.append(s)

        s = SourcePackage('twisted-words', '0.4.0', '1', self.revision, nodep=True)
        s.add_binary('python2.4-twisted-words', 'all')
        s.add_binary('python-twisted-words', 'all')
        self.packages.append(s)

        targets = []
        for i in self.packages:
            targets.extend(i.binarytargets())

        return targets

    def run(self, b):
        bd = b.get_cwd(self.builddir)

        sourcedir = 'dapper_twisted'

        binaries = []
        for i in self.packages:
            self.debsrcname = i.name
            self.debname = i.name
            self.debver = i.version
            self.sdir=sourcedir
            self.deborigversion=i.version
            self.deborigrevision=i.revision
            self.debprefix=i.get_debprefix()
            self.patchnames=i.patches
            self.build_deb(bd, nodep=i.nodep)

            binaries.extend(i.binaryfiles())

        b.info('Built binary packages: %s' % binaries)

    def run_source(self, b, release_revision):
        self.revision = release_revision
        self.srcdir = b.srcdir
        self.get_targets() # Note: side-effect, generates self.packages

        bd = b.get_cwd(self.builddir)

        sourcedir = 'dapper_twisted'

        self._export_revision(bd, release_revision, sourcedir)

        res = []
        for i in self.packages:
            self.debsrcname = i.name
            self.debname = i.name
            self.debver = i.version
            self.sdir=sourcedir
            self.deborigversion=i.version
            self.deborigrevision=i.revision
            self.debprefix=i.get_debprefix()
            self.patchnames=i.patches

            newdebsrcdir = self._prepare_source(b, bd, os.path.join(sourcedir, i.filename()), None)
            bd.ex('dpkg-source', '-b', newdebsrcdir, '')

            res.extend(self._get_source_files(bd))

        return res

    def get_deb_dirname(self):
        return 'twisted'

class KernelBuild(DebSourceBuild):
    name = 'kernelbuild'
    description = 'Build Ubuntu kernel debian package with OpenL2TP and L2TP GW patch.'
    debsrcname = 'linux-source-2.6.15'
    sdir = 'kernel'
    debname = None
    deborigversion = '2.6.15-51.66'
    deborigrevision = None
    debver = '2.6.15-51.99'
    patchnames = []

    def get_targets(self):
        return [self.get_deb_target(name='linux-image-2.6.15-51-386'),
                self.get_deb_target(name='linux-headers-2.6.15-51'),
                self.get_deb_target(name='linux-headers-2.6.15-51-386')]

    def _prepare_kernel_sources(self, bd, sdir):
        dsc_file = 'kernel/linux-source-2.6.15_2.6.15-51.66.dsc'
        sources = 'linux-source-2.6.15-2.6.15'

        bd.unpack_deb_source(os.path.join(sdir, dsc_file))

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease patches included.')
        bd.patch_dir(sources, [os.path.join(sdir, 'kernel/linux-source-2.6.15-l2tp.diff'),
                               os.path.join(sdir, 'openl2tp-0.10+codebay/kernel/patches/pppol2tp-linux-2.6.15.patch'),
                               os.path.join(sdir, 'kernel/linux-2.6.15-mppe-mppc-1.3.patch')])

        # patch-o-matic-ng / ROUTE target
        pom_dir = os.path.join(sdir, 'kernel/patch-o-matic-ng-20080316')
        iptables_subdir = 'iptables-1.3.3+codebay'

        # FIXME: iptables is dummy here
        bd.sh('CURR=`pwd`; cd %s ; ./runme --kernel-path $CURR/%s --iptables-path %s/%s --batch ROUTE' % \
              (pom_dir, sources, self.srcdir, iptables_subdir))

        # Note: this is quite a brutal way to do this, but alternative would
        # be to fiddle with split-config and such which is not nice.
        # d-i udeb build seems to require all architectures..
        for arch in ['amd64', 'hppa', 'i386', 'ia64', 'powerpc', 'sparc']:
            # Modify generic config

            bd.sh('echo "CONFIG_PPPOL2TP=m" >> ' + os.path.join(sources, 'debian/config/%s/config' % arch))

            # MPPE/MPPC patch to kernel config
            bd.sh('echo "CONFIG_PPP_MPPE_MPPC=m" >> ' + os.path.join(sources, 'debian/config/%s/config' % arch))
            bd.filter_lines(os.path.join(sources, 'debian/config/%s/config' % arch), [['CONFIG_PPP_MPPE=m', '# CONFIG_PPP_MPPE is not set']])

            # This is required to be set when SOFTWARE_SUSPEND is disabled and
            # KERNEL_DEBUG is enabled.
            bd.sh('echo "# CONFIG_DEBUG_PAGEALLOC is not set" >> ' + os.path.join(sources, 'debian/config/%s/config' % arch))

        # Include mppe/mppc module in d-i module list
        for o, n in [['ppp_mppe', 'ppp_mppe_mppc']]:
            bd.filter_lines(os.path.join(sources, 'debian/d-i/shared/modules/ppp-modules'), [[o, n]])

        # Modify server config for i386

        # options to remove
        for o, v in [['CONFIG_I2O_EXT_ADAPTEC_DMA64', 'y'],
                     ['CONFIG_X86_PAE', 'y'],
                     ['CONFIG_CLUSTER_DLM', 'm'],
                     ['CONFIG_CLUSTER_DLM_PROCLOCKS', 'y'],
                     ['CONFIG_GFS_FS_LOCK_DLM', 'm'],
                     ['CONFIG_GFS_FS_LOCK_GULM', 'm'],
                     ['CONFIG_GFS_FS_LOCK_NOLOCK', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [[o + '=' + v, '']])

        # options to disable
        for o, v in [['CONFIG_HOTPLUG_CPU', 'y'],
                     ['CONFIG_ACPI_HOTPLUG_CPU', 'y'],
                     ['CONFIG_SUSPEND_SMP', 'y'],
                     ['CONFIG_HIGHMEM64G', 'y'],
                     ['CONFIG_CLUSTER', 'm'],
                     ['CONFIG_GFS_FS', 'm'],
                     ['CONFIG_GFS_FS_LOCK_HARNESS', 'm'],
                     ['CONFIG_OCFS2_FS', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [[o + '=' + v, '# ' + o + ' is not set']])

        # options to enable
        for o, v in [['CONFIG_ENABLE_ALT_SMP', 'y'],
                     ['CONFIG_HIGHMEM4G', 'y']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [['# ' + o + ' is not set', o + '=' + v]])

        # Remove modules not present in server config from d-i modules list
        for o, n in [['sbpcd', ''], ['cm206', '']]:
            bd.filter_lines(os.path.join(sources, 'debian/d-i/i386/modules/i386/cdrom-modules'), [[o, n]])
        
        # These modules include "?" in modules file which allows
        # d-i to ignore missing modules.. no need to remove them.
        #d-i/shared/modules/rtc-modules:
        #    gen_rtc: genrtc
        #    rtc: rtc
        #d-i/shared/modules/nic-pcmcia-modules:
        #    pcmcia_xirtulip: xircom_tulip_cb
        #d-i/shared/modules/scsi-modules:
        #    scsi_mca_53c9x: mca_53c9x


        # IPv4 netfilter stuff
        
        # XXX: nonexistent option, so enable this way without filter_lines(); these two ways of
        # adding options should really be unified (set_option, clear_option, remove_option).
        for o, v in [['CONFIG_IP_NF_TARGET_ROUTE', 'm']]:
            bd.sh(('echo "%s=%s" >> ' % (o, v)) + os.path.join(sources, 'debian/config/i386/config'))

        # Modify main config to disable IPv6 support

        for o, v in [['CONFIG_IPV6', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config'), [[o + '=' + v, '# ' + o + ' is not set']])

        for o, v in [['CONFIG_IPV6_PRIVACY', 'y'],
                     ['CONFIG_INET6_AH', 'm'],
                     ['CONFIG_INET6_ESP', 'm'],
                     ['CONFIG_INET6_IPCOMP', 'm'],
                     ['CONFIG_INET6_TUNNEL', 'm'],
                     ['CONFIG_IPV6_TUNNEL', 'm'],
                     ['CONFIG_IP6_NF_QUEUE', 'm'],
                     ['CONFIG_IP6_NF_IPTABLES', 'm'],
                     ['CONFIG_IP6_NF_MATCH_LIMIT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MAC', 'm'],
                     ['CONFIG_IP6_NF_MATCH_RT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_OPTS', 'm'],
                     ['CONFIG_IP6_NF_MATCH_FRAG', 'm'],
                     ['CONFIG_IP6_NF_MATCH_HL', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MULTIPORT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_OWNER', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MARK', 'm'],
                     ['CONFIG_IP6_NF_MATCH_IPV6HEADER', 'm'],
                     ['CONFIG_IP6_NF_MATCH_AHESP', 'm'],
                     ['CONFIG_IP6_NF_MATCH_LENGTH', 'm'],
                     ['CONFIG_IP6_NF_MATCH_EUI64', 'm'],
                     ['CONFIG_IP6_NF_MATCH_PHYSDEV', 'm'],
                     ['CONFIG_IP6_NF_FILTER', 'm'],
                     ['CONFIG_IP6_NF_TARGET_LOG', 'm'],
                     ['CONFIG_IP6_NF_TARGET_REJECT', 'm'],
                     ['CONFIG_IP6_NF_TARGET_NFQUEUE', 'm'],
                     ['CONFIG_IP6_NF_MANGLE', 'm'],
                     ['CONFIG_IP6_NF_TARGET_MARK', 'm'],
                     ['CONFIG_IP6_NF_TARGET_HL', 'm'],
                     ['CONFIG_IP6_NF_RAW', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config'), [[o + '=' + v, '']])

        # IPv6 modules to be removed from d-i module list
        for o, n in [['ipv6', '']]:
            bd.filter_lines(os.path.join(sources, 'debian/d-i/shared/modules/ipv6-modules'), [[o, n]])

        # Because IPv6 modules list is now empty, we must remove the
        # references to it so that d-i build would not try to build it.
        for i in ['amd64', 'hppa', 'i386', 'ia64', 'powerpc', 'sparc']:
            bd.remove(os.path.join(sources, 'debian/d-i/%s/modules/%s/ipv6-modules' % (i, i)))
        # Grr.. braindead directory layout..
        bd.remove(os.path.join(sources, 'debian/d-i/sparc/modules/sparc64/ipv6-modules'))

        return sources

    def run(self, b):
        bd = b.get_cwd(self.builddir)

        sources = self._prepare_kernel_sources(bd, self.srcdir)
        bd.build_kernel(sources)

    def run_source(self, b, release_revision):
        self.revision = release_revision
        self.srcdir = b.srcdir

        bd = b.get_cwd(self.builddir)

        self._export_revision(bd, release_revision, 'kernel')
        self._export_revision(bd, release_revision, 'openl2tp-0.10+codebay') # NB: kernel patch
        self._export_revision(bd, release_revision, 'iptables-1.3.3+codebay') # NB: kernel patch

        sources = self._prepare_kernel_sources(bd, os.path.join(self.srcdir, self.builddir))

        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

class TestclientKernelBuild(DebSourceBuild):
    name = 'testclientkernelbuild'
    description = 'Build Ubuntu kernel debian package with openl2tp kernel patch.'
    debsrcname = 'linux-source'
    debname = None
    deborigversion = '2.6.15-27.48'
    deborigrevision = None
    debver = '2.6.15-27.testclient'

    def get_targets(self):
        return [self.get_deb_target(name='linux-image-2.6.15-27-386'),
                self.get_deb_target(name='linux-headers-2.6.15-27'),
                self.get_deb_target(name='linux-headers-2.6.15-27-386')]

    def run(self, b):
        bd = b.get_cwd(self.builddir)

        dsc_file = 'kernel/linux-source-2.6.15_2.6.15-27.48.dsc'
        sources = 'linux-source-2.6.15-2.6.15'

        bd.unpack_deb_source(os.path.join(self.srcdir, dsc_file))

        bd.changelog_newversion(sources, self.get_deb_ver(), 'OpenL2TP patch included.')
        bd.patch_dir(sources, [os.path.join(self.srcdir, 'openl2tp-0.10+codebay/kernel/patches/pppol2tp-linux-2.6.15.patch')])

        # Note: this is quite a brutal way to do this, but alternative would
        # be to fiddle with split-config and such which is not nice.
        # d-i udeb build seems to require all architectures..
        for arch in ['amd64', 'hppa', 'i386', 'ia64', 'powerpc', 'sparc']:

            # Modify generic config

            bd.sh('echo "CONFIG_PPPOL2TP=m" >> ' + os.path.join(sources, 'debian/config/%s/config' % arch))

            # This is required to be set when SOFTWARE_SUSPEND is disabled and
            # KERNEL_DEBUG is enabled.
            bd.sh('echo "# CONFIG_DEBUG_PAGEALLOC is not set" >> ' + os.path.join(sources, 'debian/config/%s/config' % arch))


        # Modify server config for i386

        # options to remove
        for o, v in [['CONFIG_I2O_EXT_ADAPTEC_DMA64', 'y'],
                     ['CONFIG_X86_PAE', 'y'],
                     ['CONFIG_CLUSTER_DLM', 'm'],
                     ['CONFIG_CLUSTER_DLM_PROCLOCKS', 'y'],
                     ['CONFIG_GFS_FS_LOCK_DLM', 'm'],
                     ['CONFIG_GFS_FS_LOCK_GULM', 'm'],
                     ['CONFIG_GFS_FS_LOCK_NOLOCK', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [[o + '=' + v, '']])

        # options to disable
        for o, v in [['CONFIG_HOTPLUG_CPU', 'y'],
                     ['CONFIG_ACPI_HOTPLUG_CPU', 'y'],
                     ['CONFIG_SUSPEND_SMP', 'y'],
                     ['CONFIG_HIGHMEM64G', 'y'],
                     ['CONFIG_CLUSTER', 'm'],
                     ['CONFIG_GFS_FS', 'm'],
                     ['CONFIG_GFS_FS_LOCK_HARNESS', 'm'],
                     ['CONFIG_OCFS2_FS', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [[o + '=' + v, '# ' + o + ' is not set']])

        # options to enable
        for o, v in [['CONFIG_ENABLE_ALT_SMP', 'y'],
                     ['CONFIG_HIGHMEM4G', 'y']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config.server'), [['# ' + o + ' is not set', o + '=' + v]])

        # Remove modules not present in server config from d-i modules list
        for o, n in [['sbpcd', ''], ['cm206', '']]:
            bd.filter_lines(os.path.join(sources, 'debian/d-i/i386/modules/i386/cdrom-modules'), [[o, n]])
        

        # These modules include "?" in modules file which allows
        # d-i to ignore missing modules.. no need to remove them.
        #d-i/shared/modules/rtc-modules:
        #    gen_rtc: genrtc
        #    rtc: rtc
        #d-i/shared/modules/nic-pcmcia-modules:
        #    pcmcia_xirtulip: xircom_tulip_cb
        #d-i/shared/modules/scsi-modules:
        #    scsi_mca_53c9x: mca_53c9x

        # Modify main config to disable IPv6 support

        for o, v in [['CONFIG_IPV6', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config'), [[o + '=' + v, '# ' + o + ' is not set']])

        for o, v in [['CONFIG_IPV6_PRIVACY', 'y'],
                     ['CONFIG_INET6_AH', 'm'],
                     ['CONFIG_INET6_ESP', 'm'],
                     ['CONFIG_INET6_IPCOMP', 'm'],
                     ['CONFIG_INET6_TUNNEL', 'm'],
                     ['CONFIG_IPV6_TUNNEL', 'm'],
                     ['CONFIG_IP6_NF_QUEUE', 'm'],
                     ['CONFIG_IP6_NF_IPTABLES', 'm'],
                     ['CONFIG_IP6_NF_MATCH_LIMIT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MAC', 'm'],
                     ['CONFIG_IP6_NF_MATCH_RT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_OPTS', 'm'],
                     ['CONFIG_IP6_NF_MATCH_FRAG', 'm'],
                     ['CONFIG_IP6_NF_MATCH_HL', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MULTIPORT', 'm'],
                     ['CONFIG_IP6_NF_MATCH_OWNER', 'm'],
                     ['CONFIG_IP6_NF_MATCH_MARK', 'm'],
                     ['CONFIG_IP6_NF_MATCH_IPV6HEADER', 'm'],
                     ['CONFIG_IP6_NF_MATCH_AHESP', 'm'],
                     ['CONFIG_IP6_NF_MATCH_LENGTH', 'm'],
                     ['CONFIG_IP6_NF_MATCH_EUI64', 'm'],
                     ['CONFIG_IP6_NF_MATCH_PHYSDEV', 'm'],
                     ['CONFIG_IP6_NF_FILTER', 'm'],
                     ['CONFIG_IP6_NF_TARGET_LOG', 'm'],
                     ['CONFIG_IP6_NF_TARGET_REJECT', 'm'],
                     ['CONFIG_IP6_NF_TARGET_NFQUEUE', 'm'],
                     ['CONFIG_IP6_NF_MANGLE', 'm'],
                     ['CONFIG_IP6_NF_TARGET_MARK', 'm'],
                     ['CONFIG_IP6_NF_TARGET_HL', 'm'],
                     ['CONFIG_IP6_NF_RAW', 'm']]:
            bd.filter_lines(os.path.join(sources, 'debian/config/i386/config'), [[o + '=' + v, '']])

        # IPv6 modules to be removed from d-i module list
        for o, n in [['ipv6', '']]:
            bd.filter_lines(os.path.join(sources, 'debian/d-i/shared/modules/ipv6-modules'), [[o, n]])

        # Because IPv4 moduls list is now empty, we must remove the
        # references to it so that d-i build would not try to build it.
        for i in ['amd64', 'hppa', 'i386', 'ia64', 'powerpc', 'sparc']:
            bd.remove(os.path.join(sources, 'debian/d-i/%s/modules/%s/ipv6-modules' % (i, i)))
        # Grr.. braindead directory layout..
        bd.remove(os.path.join(sources, 'debian/d-i/sparc/modules/sparc64/ipv6-modules'))

        bd.build_kernel(sources)

class IptablesBuild(DebSourceBuild):
    name = 'iptablesbuild'
    description = 'Build patched iptables debian package.'
    debsrcname = 'iptables'
    debname = 'iptables'
    debver = '1.3.3'
    deborigversion = '1.3.3'
    deborigrevision = '2ubuntu4.1'
    
    def run(self, b):
        sources = 'iptables-1.3.3+codebay'
        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, sources), '.')

        #bd.changelog_newversion(sources, '1.3.3', 'New upstream release.')
        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.build_deb_from_source(sources)

    #
    #  FIXME - check
    #
    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'iptables-1.3.3+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, sources)

        #bd.changelog_newversion(sources, '1.3.3', 'New upstream release.')
        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

    def get_deb_source_files(self):
        return [os.path.join('iptables', 'iptables-1.3.3.tar.gz')]


class L2tpgwBuild(DebSourceBuild):
    name = 'l2tpgwbuild'
    description = 'Build L2TP Gateway Ubuntu package.'
    debsrcname = 'l2tpgw'
    debname = 'l2tpgw'
    debver = '1.0.0'

    def run(self, b):
        sources = 'python'
        bd = b.get_cwd(self.builddir)

        b.ex('cp', '-ar', os.path.join(self.srcdir, 'src'), self.builddir)
        b.ex('cp', '-ar', os.path.join(self.srcdir, 'vpnease-certificates', 'management-protocol'), self.builddir)

        # Autorun setup - see wiki L2tpAutorun
        ah = AutorunHelper(bd)
        [autorun_installed_zip, _] = ah.build(self.srcdir)
        b.ex('cp', '-f', autorun_installed_zip, os.path.join(self.builddir, 'src', 'python', 'webui-pages'))

        bb = b.get_cwd(os.path.join(self.builddir, 'src'))
        bb.changelog_newversion(sources, self.get_deb_ver(), 'New upstream version.')
        bb.build_deb_from_source(sources)

        for r, d, f in b.walk(os.path.join(self.builddir, 'src')):
            for i in f:
                b.ex('mv', os.path.join(r, i), self.builddir)
            break

class GfxbootBuild(DebSourceBuild):
    name = 'gfxbootbuild'
    description = 'Build gfxboot-theme-ubuntu source package'
    debsrcname = 'gfxboot-theme-ubuntu'
    debname = 'gfxboot-theme-ubuntu'
    debver = '0.1.27'

    def run(self, b):
        raise build.BuildError('not implemented')

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'gfxboot-theme-ubuntu-0.1.27+codebay'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, sources)

        bd.changelog_newversion(sources, self.get_deb_ver(), 'VPNease specific modifications included')
        bd.ex('dpkg-source', '-b', sources, '')

        return self._get_source_files(bd)

    def get_deb_dirname(self):
        return 'gfxboot'

class IsolinuxBuild(DebSourceBuild):
    name = 'isolinuxbuild'
    description = 'Build isolinux source package'

    def run(self, b):
        raise build.BuildError('Not implemented')

    def run_source(self, b, release_revision):
        self.revision = release_revision

        sources = 'isolinux'
        target = 'isolinux-ubuntu-dapper.tar.gz'
        bd = b.get_cwd(self.builddir)
        self._export_revision(bd, release_revision, os.path.join('isolinux', 'ubuntu_dapper'), dest=sources)

        ih = IsolinuxHelper(bd)
        ih.modify_isolinux_config()

        bd.ex('/bin/tar', 'czf', target, sources)
        return [os.path.join(bd.env.path, target)]

    def get_deb_dirname(self):
        return 'isolinux'

class OpenSourceBuild(build.Build):
    name = 'opensourcebuild'
    description = 'Build opensource package'

    """
    FIXME:

    package maintainers still wrong:
    - most notably in twisted packages
    """

    option_list = [
        build.Option('--release-revision', type='string', dest='release_revision', required=True)]

    def get_targets(self):
        return ['vpnease_opensource_r%s.tar.gz' % self.options.release_revision]

    def run(self, b):
        bd = b.get_cwd(self.builddir)

        sources = []
        for d in [
            GfxbootBuild,
            IsolinuxBuild,
            KernelBuild,
            OpenswanBuild,
            EzipupdateBuild,
            OpenL2tpBuild,
            IppoolBuild,
            TwistedBuild,
            NevowBuild,
            FormalBuild,
            RrdBuild,
            PppBuild,
            CasperBuild,
            LibNfNetlinkBuild,
            LibNetFilterConntrackBuild,
            ConntrackBuild,
            UsplashBuild,
            MatplotlibBuild,
            SqlalchemyBuild,
            PythonApswBuild,
            FreeradiusBuild,
            RadiusclientNgBuild,
            FirefoxBuild,
            SyslogBuild,
            SnmpdBuild,
            ]:

            p = d(b)
            bd.ex('mkdir', os.path.join(self.builddir, p.get_name()))
            p.builddir = os.path.join(self.builddir, p.get_name())
            sources.append([p.get_deb_dirname(), p.run_source(bd, self.options.release_revision)])

        dname = 'vpnease-opensource'
        bd.ex(['mkdir', dname])
        for d, files in sources:
            bd.ex(['mkdir', os.path.join(dname, d)])
            for f in files:
                bd.ex(['cp', os.path.join(self.srcdir, f), os.path.join(dname, d)])


        readme_contents = textwrap.dedent("""\

        VPNease 1.2.%s Open Source
        ============================

        This package contains source files for all software packages
        modified for the VPNease server product.  Please see the licenses
        of individual packages for detailed license information.

        """ % self.options.release_revision)

        bd.write(os.path.join(dname, 'readme.txt'), readme_contents, perms=0644)

        bd.ex(['tar', 'czf', self.get_targets()[0], dname])

class ProductServersBuild(DebSourceBuild):
    name = 'productserversbuild'
    description = 'Management, monitoring, and web server packages'
    debsrcname = 'vpnease-productservers'
    debver = '1.0.0'

    def run(self, b):
        sources = 'productservers'
        repokeysfile = 'repository-keys.txt'

        # No need to be options
        vpnease_repokeys = ['927E0039', '5D31534A']
        ubuntu_repokeys = ['927E0039', '5D31534A']

        bd = b.get_cwd(self.builddir)
        bd.ex('cp', '-ar', os.path.join(self.srcdir, sources), '.')
        bd.ex('cp', '-ar', os.path.join(self.srcdir, 'src'), '.')
        bd.ex('cp', '-ar', os.path.join(self.srcdir, 'vpnease-certificates'), '.')

        myenv = dict(os.environ)
        myenv['GNUPGHOME'] = os.path.join(self.srcdir, 'gnupg')

        bd.ex('/bin/rm', '-f', os.path.join(sources, repokeysfile))

        for key in vpnease_repokeys + ubuntu_repokeys:
            [rv, out, err] = bd.ex_c('gpg', '--export', '--armor', key, env=myenv)
            if rv != 0:
                raise build.BuildError('gpg export of repository key %s failed' % key)
            bd.write(os.path.join(sources, repokeysfile), out, append=True)

        bd.build_deb_from_source(sources)

class Gendoc(build.Build):
    name = 'gendoc'
    description = 'Generate documentation'

    def get_targets(self):
        return []

    def run(self, b):
        b.ex('epydoc', '--docformat', 'plaintext', 'codebay', cwd=os.path.join(self.srcdir, 'src', 'python'))

class GendocInstall(build.Build):
    name = 'gendoc-install'
    description = 'Install generated documentation'
    option_list = [build.Option('--destination', type='string', dest='destination', required=True)]

    def get_targets(self):
        return []

    def run(self, b):
        b.run_build(Gendoc)
        b.ex('mkdir', '-p', os.path.join(self.options.destination))
        b.ex('rm', '-rf', os.path.join(self.options.destination, 'python'))
        b.ex('mkdir', os.path.join(self.options.destination, 'python'))
        b.ex('cp', '-r', os.path.join(self.srcdir, 'src', 'python', 'html'),
             os.path.join(self.options.destination, 'python'))
        b.ex('chmod', '-R', 'a+rX', self.options.destination)

class Test(build.Build):
    name = 'test'
    description = 'Run automated tests'

    def get_targets(self):
        return []

    def run(self, b):
        b.info('Running pyflakes')
        b.ex('pyflakes', 'codebay', cwd=os.path.join(self.srcdir, 'src', 'python'))
        b.ex('pyflakes', 'build.py', cwd=self.srcdir)
        b.ex('pyflakes', 'vpnease-postupdate-backup.py', cwd=os.path.join(self.srcdir, 'src', 'python', 'postupdate'))

        scripts = ['cron', 'gnome-autostart', 'update', 'update-product', 'syslogdaemon', 'syslogwrapper'] # FIXME: more?

        for i in scripts:
            b.ex('pyflakes', 'l2tpgw-' + i, cwd=os.path.join(self.srcdir, 'src', 'python', 'data'))

        scripts = ['vpnease-init']
        for i in scripts:
            b.ex('pyflakes', i, cwd=os.path.join(self.srcdir, 'src', 'python', 'data'))

        b.info('Running trial')
        b.ex('trial', 'codebay', cwd=os.path.join(self.srcdir, 'src', 'python'))
        b.ex('trial', 'build.py', cwd=self.srcdir)

        # not working very well..
        #for i in scripts:
        #    b.ex('trial', 'l2tpgw-' + i, cwd=os.path.join(self.srcdir, 'src', 'python', 'data'))

build.register_build(Gendoc)
build.register_build(GendocInstall)
build.register_build(Test)
build.register_build(KernelBuild)
build.register_build(IptablesBuild)
build.register_build(TestclientKernelBuild)
build.register_build(OpenswanBuild)
build.register_build(L2tpgwBuild)
build.register_build(MonitBuild)
build.register_build(EzipupdateBuild)
build.register_build(BasefilesBuild)
build.register_build(OpenL2tpBuild)
build.register_build(IppoolBuild)
build.register_build(TwistedBuild)
build.register_build(NevowBuild)
build.register_build(FormalBuild)
build.register_build(RrdBuild)
build.register_build(PppBuild)
build.register_build(CasperBuild)
build.register_build(LibNfNetlinkBuild)
build.register_build(LibNetFilterConntrackBuild)
build.register_build(ConntrackBuild)
build.register_build(VpnEaseBuild)
build.register_build(LiveCDBuild)
build.register_build(TestclientLiveCDBuild)
build.register_build(UsplashBuild)
build.register_build(MatplotlibBuild)
build.register_build(SqlalchemyBuild)
build.register_build(PythonApswBuild)
build.register_build(OpenSourceBuild)
build.register_build(ProductServersBuild)
build.register_build(FreeradiusBuild)
build.register_build(RadiusclientBuild)
build.register_build(RadiusclientNgBuild)
build.register_build(FirefoxBuild)
build.register_build(SyslogBuild)
build.register_build(SnmpdBuild)

if __name__ == '__main__':
    build.main()
