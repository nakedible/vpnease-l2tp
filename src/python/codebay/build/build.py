"""
Codebay build system
"""

import optparse, tempfile, datetime, logging, sys, os, textwrap
from logging import handlers

from codebay.common import runcommand
from codebay.common import helpers

# TODO:
# - file copy helper
# - need md5sum helper which should work like this:
#   chroot_interface.write(chroot_interface.md5sum_files('.'), 'md5sum.txt')
# - move livecd specific functions somewhere else

class BuildError(Exception):
    """Build error."""

class Option(optparse.Option):
    ATTRS = optparse.Option.ATTRS + ['required']

class CommandLineOptions:
    usage = 'usage: %prog <target> [<options> ...]'
    option_list = [Option('-d', '--debug', action='store_true', dest='debug'),
                   #Option('--clean', action='store_true', dest='clean'),
                   Option('--srcdir', action='store', dest='srcdir'),
                   Option('--tempdir', action='store', dest='tempdir'),
                   Option('--export', action='store_true', dest='export'),
                   Option('--export-base', action='store', dest='export_base'),
                   Option('--work', action='store_true', dest='work'),
                   Option('--revision', action='store', dest='revision'),
                   Option('--branch', action='store', dest='branch'),
                   Option('--buildinfo', action='store', dest='buildinfo'),
                   Option('--buildnote', action='store', dest='buildnote')]
    defaults = {'debug': False,
                'tempdir': None,
                'srcdir': os.path.curdir,
                'export_base': tempfile.gettempdir()}

    def __init__(self):
        self.options = None
        self.args = None
        self.parser = optparse.OptionParser(usage=self.usage)
        self.add(self.option_list, self.defaults)

    def add(self, options, defaults):
        self.parser.set_defaults(**defaults)
        for opt in options:
            self.parser.add_option(opt)

    def parse(self, args=None, values=None):
        self.options, self.args = self.parser.parse_args(args, values)

    def print_usage(self, file=None):
        return self.parser.print_usage(file)

    def error(self, msg):
        return self.parser.error(msg)

class SubbuildOptions(CommandLineOptions):
    def __init__(self, name):
        CommandLineOptions.__init__(self)
        self.inherit_list = self.parser.defaults.keys()
        self.name = name

    def feed(self, parent, values):
        self.options = self.parser.get_default_values()
        self.args = []
        for name in self.inherit_list:
            setattr(self.options, name, getattr(parent, name))
        for key, value in values.iteritems():
            setattr(self.options, key, value)

    def error(self, msg):
        raise BuildError('Subbuild "%s": %s' % (self.name, msg))

class Build:
    name = None
    description = '<unspecified>'
    option_list = []
    defaults = {}

    def __init__(self, options):
        self.options = options

    def get_name(klass):
        return klass.name
    get_name = classmethod(get_name)

    def get_description(klass):
        return klass.description
    get_description = classmethod(get_description)

    def add_options(klass, parser):
        parser.add(klass.option_list, klass.defaults)
    add_options = classmethod(add_options)

    def check_options(klass, parser, options):
        for opt in klass.option_list:
            if not hasattr(options, opt.dest):
                parser.error('option "%s" not present' % opt.dest)
            if opt.required and getattr(options, opt.dest) is None:
                parser.error('required option "%s" missing' % opt.dest)
    check_options = classmethod(check_options)

    def write_buildinfo(self, b, text, append=False):
        b.write(os.path.join(self.builddir, 'buildinfo.txt'), text,
                perms=0644, append=append)

    def write_default_buildinfo(self, b):
        self.write_buildinfo(b, textwrap.dedent("""\
        buildname: %s
        buildinfo: %s
        buildnote: %s
        branch: %s
        revision: %s
        srcdir: %s
        builddir: %s
        work: %s
        export: %s
        targets: %s
        """) % (self.get_name(), self.buildinfo, self.buildnote, self.branch,
                self.revision, self.srcdir, self.builddir,
                str(self.work), str(self.export), self.get_targets()))

    def init(self, b):
        self.build_handle = b
        self.srcdir = b.srcdir
        self.tempdir = b.tempdir
        self.builddir = os.path.join(self.tempdir, self.get_name())

        self.buildinfo = b.buildinfo
        self.buildnote = b.buildnote
        self.branch = b.branch
        self.revision = b.revision
        self.work = b.work
        self.export = b.export
        self.targets = self.get_targets()

        b.rmrf(self.builddir)
        b.makedirs(self.builddir)
        self.write_default_buildinfo(b)

    def get_targets(self):
        raise NotImplementedError()

    def run(self, b):
        raise NotImplementedError()

class BuildEnvironment:
    def __init__(self, build):
        self.build = build

    def run(self, *args, **kw):
        cmdstr = '%s %s' % (args, kw)
        self.build.debug('Executing: %s' % cmdstr)
        kw.setdefault('stdin', runcommand.PASS)
        kw.setdefault('stdout', runcommand.PASS)
        kw.setdefault('stderr', runcommand.PASS)
        kw.setdefault('retval', runcommand.FAIL)
        try:
            if len(args) == 1 and isinstance(args[0], list):
                ret = runcommand.run(args[0], **kw)
            else:
                ret = runcommand.run(list(args), **kw)

        except runcommand.RunException, e:
            errstr = 'Running command failed: %s' % e
            self.build.error(errstr)
            self.build.error('Failed command: %s' % cmdstr)
            self.build.error('Retval: %d' % e.rv)
            if e.stdout is not None:
                self.build.error('Stdout: %s' % e.stdout)
            if e.stderr is not None:
                self.build.error('Stderr: %s' % e.stderr)
            raise BuildError(errstr)

        self.build.debug('Retval: %d' % ret[0])
        if ret[1] is not None:
            self.build.debug('Stdout: %s' % ret[1])
        if ret[2] is not None:
            self.build.debug('Stderr: %s' % ret[2])
        return ret

    def mkdir(self, path):
        self.build.debug('mkdir: %s' % path)
        os.mkdir(path)

    def rmdir(self, path):
        self.build.debug('rmdir: %s' % path)
        os.rmdir(path)

    def remove(self, path):
        self.build.debug('remove: %s' % path)
        os.remove(path)

    def walk(self, path, **kw):
        return os.walk(path, **kw)

    def makedirs(self, path):
        self.build.debug('makedirs: %s' % path)
        os.makedirs(path)

    def create_sparse_file(self, path, size):
        self.build.debug('create_sparse_file: %s %d' % (path, size))
        fd = os.open(path, os.O_WRONLY | os.O_CREAT)
        try:
            os.ftruncate(fd, size)
        finally:
            os.close(fd)

    def write(self, path, text, append=False, perms=0755):
        self.build.debug('write: %s, append=%d, perms=%o' % (path, append, perms)) # FIXME: text might be long.
        helpers.write_file(path, text, append=append, perms=perms)

    def read(self, path):
        self.build.debug('read: %s' % path)
        f = None
        ret = ''
        try:
            f = open(path, 'r')
            ret = f.read()
        except:
            if f is not None:
                f.close()
            raise BuildError('cannot read file: %s' % path)

        f.close()
        return ret

    def chmod(self, path, perms):
        self.build.debug('chmod: %s, %o' % (path, perms))
        os.chmod(path, perms)

    def md5sum_files(self, path):
        for root, dirs, files in os.walk(path):
            # FIXME:
            raise Exception('not implemented')

class ChrootBuildEnvironment:
    def __init__(self, parent, path, cwd = True):
        self.parent = parent
        self.path = path
        self.cwd = cwd

    def _fixpath(self, path):
        if os.path.isabs(path):
            # FIXME: How to make a relative path out of an absolute one?
            return os.path.join(self.path, path[1:])
        else:
            if self.cwd:
                return os.path.join(self.path, path)
            else:
                return path

    def run(self, *args, **kw):
        preexec = [runcommand.chroot(self.path)]
        if self.cwd:
            preexec.append(runcommand.cwd('/')) # FIXME: root path?
        kw.setdefault('preexec', [])[0:0] = preexec
        return self.parent.run(*args, **kw)

    def mkdir(self, path):
        return self.parent.mkdir(self._fixpath(path))

    def rmdir(self, path):
        return self.parent.rmdir(self._fixpath(path))

    def remove(self, path):
        return self.parent.remove(self._fixpath(path))
    
    def walk(self, path, **kw):
        return self.parent.walk(self._fixpath(path), **kw)

    def makedirs(self, path):
        return self.parent.makedirs(self._fixpath(path))

    def create_sparse_file(self, path, size):
        return self.parent.create_sparse_file(self._fixpath(path), size)

    def write(self, path, text, append=False, perms=0755):
        return self.parent.write(self._fixpath(path), text, append=append, perms=perms)

    def read(self, path):
        return self.parent.read(self._fixpath(path))
    
    def chmod(self, path, perms):
        return self.parent.chmod(self._fixpath(path), perms)


class CwdBuildEnvironment: 
    def __init__(self, parent, path):
        self.parent = parent
        self.path = path

    def _fixpath(self, path):
        return os.path.join(self.path, path)

    def run(self, *args, **kw):
        kw.setdefault('preexec', [])[0:0] = [runcommand.cwd(self.path)]
        return self.parent.run(*args, **kw)

    def mkdir(self, path):
        return self.parent.mkdir(self._fixpath(path))

    def rmdir(self, path):
        return self.parent.rmdir(self._fixpath(path))

    def remove(self, path):
        return self.parent.remove(self._fixpath(path))
    
    def walk(self, path, **kw):
        return self.parent.walk(self._fixpath(path), **kw)

    def makedirs(self, path):
        return self.parent.makedirs(self._fixpath(path))

    def create_sparse_file(self, path, size):
        return self.parent.create_sparse_file(self._fixpath(path), size)

    def write(self, path, text, append=False, perms=0755):
        return self.parent.write(self._fixpath(path), text, append=append, perms=perms)

    def read(self, path):
        return self.parent.read(self._fixpath(path))

    def chmod(self, path, perms):
        return self.parent.chmod(self._fixpath(path), perms)

class CleanupDir:
    def __init__(self, intf, path):
        self.intf = intf
        self.path = path

    def cleanup(self):
        self.intf.rmr(self.path)

    def cleanup_error(self):
        self.intf.rmrf(self.path)

class Mount:
    def __init__(self, intf, filename, path, filesystem=None):
        self.intf = intf
        self.filename = filename
        self.path = path
        self.filesystem = filesystem
        self.cwd = self.intf.get_cwd(self.path)
        self.chroot = self.intf.get_chroot(self.path)
        self.mounted = False

    def mount(self):
        self.mounted = True
        if self.filesystem == None:
            self.intf.ex('mount', '-o', 'loop', self.filename, self.path)
        else:
            self.intf.ex('mount', '-t', self.filesystem, '-o', 'loop', self.filename, self.path)

    def umount(self):
        self.intf.ex('umount', self.path)
        self.mounted = False

    def cleanup(self):
        if self.mounted:
            self.intf.ex('umount', self.path)
            raise BuildError('Mount %s was left mounted.' % self.path)

    def cleanup_error(self):
        self.intf.ex('umount', self.path)

class PackageInstall:
    def __init__(self, intf):
        self.intf = intf
        self.prepared = False
        self.env = None
        # FIXME: this breaks relative cwd-paths.
        self.root = self.intf.get_chroot(self.intf.env.path)

    def set_apt_sources_list(self, sources, use_source_packages=False):
        self.root.ex('cp', '/etc/apt/sources.list', '/etc/apt/sources.list.bak')
        repos = ''
        for i in sources:
            r = textwrap.dedent("""\
            deb %(method)s://%(server)s %(suite)s %(components)s
            """ % {'method': i['method'], 'server': i['server'], 'suite': i['suite'], 'components': i['components']})
            repos += r
            if use_source_packages:
                r = textwrap.dedent("""\
                deb-src %(method)s://%(server)s %(suite)s %(components)s
                """ % {'method': i['method'], 'server': i['server'], 'suite': i['suite'], 'components': i['components']})
                repos += r

        self.intf.build.info('Setting following /etc/apt/sources.list:')
        self.intf.build.info(repos)

        self.root.write('/etc/apt/sources.list', repos)

    def prepare(self):
        self.prepared = True

        self.intf.build.info('Preparing package installer')
        self.env = os.environ
        self.env['DEBIAN_FRONTEND'] = 'noninteractive'

        # Note: uname should not be a problem when building on Ubuntu
        # build machine
        for i in ['/sbin/start-stop-daemon', '/usr/sbin/invoke-rc.d', '/sbin/lrm-manager']:
            self.root.add_divert(i)

        # Note: there is no resolv.conf initially in the Ubuntu livecd image.
        # self.root.ex('cp', '/etc/resolv.conf', '/etc/resolv.conf.bak')
        self.intf.ex('cp', '/etc/resolv.conf', os.path.join(self.intf.env.path, 'etc/resolv.conf'))

        self.root.ex('mount', '-t', 'proc', 'proc', 'proc')
        self.root.ex('mount', '-t', 'sysfs', 'sys', 'sys')

    def unprepare(self):
        self.intf.build.info('Unpreparing package installer')

        self._apt_update()
        self._apt_clean()

        for i in ['/sbin/start-stop-daemon', '/usr/sbin/invoke-rc.d', '/sbin/lrm-manager']:
            self.root.remove_divert(i)

        # self.root.ex('mv', '/etc/resolv.conf.bak', '/etc/resolv.conf')
        self.root.remove('/etc/resolv.conf')

        self.root.ex('umount', '/proc')
        self.root.ex('umount', '/sys')

        self.prepared = False

    def cleanup(self):
        if self.prepared:
            self.unprepare()
            raise BuildError('Package install was left prepared.')

    def cleanup_error(self):
        try:
            self.cleanup()
        except:
            self.intf.build.warning('Cleaning up after error failed.')

    def _restore_apt_sources_list(self):
        self.root.ex('mv', '/etc/apt/sources.list.bak', '/etc/apt/sources.list')

    def _apt_update(self):
        self.intf.build.info('Aptitude update: ')
        self.root.ex('aptitude', '-y', '-q', 'update', env=self.env)

    def _apt_clean(self):
        self.intf.build.info('Aptitude clean')
        self.root.ex('aptitude', '-y', '-q', 'clean', env=self.env)

    def _apt_distupgrade(self):
        self._apt_update()
        self.intf.build.info('Apt-get dist-upgrade: ')
        self.root.ex('aptitude', '-q', '-y', 'dist-upgrade', env=self.env)
        self._apt_clean()

    def _apt_upgrade(self):
        self._apt_update()
        self.intf.build.info('Apt-get upgrade: ')
        self.root.ex('aptitude', '-q', '-y', 'upgrade', env=self.env)
        self._apt_clean()

    def _apt_install(self, packages):
        self._apt_update()
        self.intf.build.info('Aptitude install: %s', packages)
        self.root.ex(['aptitude', '-q', '-y', '-o', 'Aptitude::Recommends-Important=false', 'install', '-o', 'Aptitude::ProblemResolver::StepLimit=0', '-o', 'Aptitude::CmdLine::Request-Strictness=999999'] + packages, env=self.env)
        self._apt_clean()

    def _apt_remove(self, packages, options=None):
        self._apt_update()
        opts = []
        if options is not None:
            for i in options:
                opts.extend(['-o', 'Aptitude::%s' % i])

        self.intf.build.info('Aptitude purge: %s', packages)
        self.root.ex(['aptitude', '-q', '-y'] + opts + ['purge'] + packages, env=self.env)
        self._apt_clean()

    def _mark_hold(self, packages):
        self.intf.build.info('Marking package as hold: %s', packages)
        self.root.ex(['aptitude', 'hold', '-q', '-y'] + packages, env=self.env)

    def _mark_noauto(self, packages):
        self.intf.build.info('Unmarking aptitude auto state: %s', packages)
        self.root.ex(['aptitude', 'unmarkauto', '-q', '-y'] + packages, env=self.env)

    def upgrade_packages(self, sources):
        self.set_apt_sources_list(sources)
        self._apt_upgrade()
        self._restore_apt_sources_list()

    def install_packages(self, packages, sources):
        self.set_apt_sources_list(sources)
        self._apt_install(packages)
        self._restore_apt_sources_list()

    def remove_packages(self, packages, aptitude_options=None):
        self.set_apt_sources_list([])
        self._apt_remove(packages, options=aptitude_options)
        self._restore_apt_sources_list()

    def install_debs_from_dir(self, directory):
        for r, d, f in self.root.walk(directory):
            pkgs = []
            files = []
            for i in f:
                files.append(os.path.join(directory, i))
                pkgs.append(i.split('_')[0])

            self.root.ex(['/usr/bin/dpkg', '-i'] + files, env=self.env)
            # FIXME: using hold breaks update in some cases..
            # self._mark_hold(pkgs)
            self._mark_noauto(pkgs)
            break

    def install_debs_from_tar(self, tarred):
        tmpdir = '/tmp/_package_install_tmp/'
        self.root.mkdir(tmpdir)
        self.intf.ex('/bin/tar', '-C', os.path.join(self.root.env.path, tmpdir[1:]), '-xzf', tarred) 
        self.install_debs_from_dir(tmpdir)

        # FIXME: use this until chroot.rmr (ie. chroot.walk) is fixed.
        # self.intf.rmr(os.path.join(self.root.env.path, tmpdir[1:]))
        self.intf.ex('/bin/rm', '-rf', os.path.join(self.root.env.path, tmpdir[1:]))

    def install_from_debs(self, packages):
        if len(packages) == 0: return
        tmpdir = '/tmp/_package_install_tmp/'
        self.root.mkdir(tmpdir)
        self.intf.ex(['/bin/cp'] + packages + [os.path.join(self.root.env.path, tmpdir[1:])])
        self.install_debs_from_dir(tmpdir)

        # FIXME: use this until chroot.rmr (ie. chroot.walk) is fixed.
        # self.intf.rmr(os.path.join(self.root.env.path, tmpdir[1:]))
        self.intf.ex('/bin/rm', '-rf', os.path.join(self.root.env.path, tmpdir[1:]))

    def install_kernels(self, packages):
        # Note: nothing special to do for now.
        self.install_from_debs(packages)

class BuildInterface:
    def __init__(self, build, env):
        self.build = build
        self.env = env

        self.debug = self.build.debug
        self.info = self.build.info
        self.warning = self.build.warning
        self.error = self.build.error
        self.critical = self.build.critical
        self.log = self.build.log
        self.exception = self.build.exception
        self.add_cleanup = self.build.add_cleanup

        self.srcdir = self.build.get_srcdir()
        self.tempdir = self.build.get_tempdir()

        self.buildinfo = self.build.buildinfo
        self.buildnote = self.build.buildnote
        self.branch = self.build.branch
        self.revision = self.build.revision
        self.work = self.build.work
        self.export = self.build.export

        self.mkdir = self.env.mkdir
        self.rmdir = self.env.rmdir
        self.remove = self.env.remove
        self.walk = self.env.walk
        self.makedirs = self.env.makedirs
        self.create_sparse_file = self.env.create_sparse_file
        self.write = self.env.write
        self.read = self.env.read
        self.chmod = self.env.chmod

    def run_build(self, buildclass, **kw):
        return self.build.run_subbuild(buildclass, self, kw)

    def get_chroot(self, path):
        return self.__class__(self.build, ChrootBuildEnvironment(self.env, path))

    def get_cwd(self, path):
        return self.__class__(self.build, CwdBuildEnvironment(self.env, path))

    def ex(self, *args, **kw):
        return self.env.run(*args, **kw)

    def ex_i(self, *args, **kw):
        kw['retval'] = None
        return self.env.run(*args, **kw)

    def ex_c(self, *args, **kw):
        kw['stdout'] = None
        kw['stderr'] = None
        return self.env.run(*args, **kw)

    def ex_ci(self, *args, **kw):
        kw['stdout'] = None
        kw['stderr'] = None
        kw['retval'] = None
        return self.env.run(*args, **kw)

    def sh(self, arg, **kw):
        kw['shell'] = True
        return self.env.run(arg, **kw)

    def rmr(self, path):
        self.build.debug('Rmr path: %s' % path)
        for root, dirs, files in self.env.walk(path, topdown=False):
            self.build.debug('  rmr root now: %s' % root)
            for name in files:
                self.env.remove(os.path.join(root, name))
            for name in dirs:
                if os.path.islink(os.path.join(root, name)):
                    self.env.remove(os.path.join(root, name))
                else:
                    self.env.rmdir(os.path.join(root, name))
        self.env.rmdir(path)

    def rmrf(self, path):
        self.build.debug('Rmrf path: %s' % path)
        for root, dirs, files in self.env.walk(path, topdown=False):
            self.build.debug('  rmrf root now: %s' % root)
            for name in files:
                try:
                    self.env.remove(os.path.join(root, name))
                except OSError, e:
                    if e.errno != 2:
                        self.build.warning('Could not remove file "%s": %s' % (os.path.join(root, name), e))
            for name in dirs:
                if os.path.islink(os.path.join(root, name)):
                    try:
                        self.env.remove(os.path.join(root, name))
                    except OSError, e:
                        if e.errno != 2:
                            self.build.warning('Could not remove link "%s": %s' % (os.path.join(root, name), e))
                else:
                    try:
                        self.env.rmdir(os.path.join(root, name))
                    except OSError, e:
                        if e.errno != 2:
                            self.build.warning('Could not remove directory "%s": %s' % (os.path.join(root, name), e))

        try:
            self.env.rmdir(path)
        except OSError, e:
            if e.errno != 2:
                self.build.warning('Could not remove directory "%s": %s' % (path, e))

    def mount(self, filename, path, filesystem=None):
        m = Mount(self, filename, path, filesystem=filesystem)
        self.add_cleanup(m)
        m.mount()
        return m

    # Filter a line-based textfile.
    # Match at most one time for each filter.
    def filter_lines(self, filename, filters):
        import tempfile, re

        h = open(os.path.join(self.env.path, filename), 'r')
        th, tname = tempfile.mkstemp()

        for line in h.read().split('\n'):
            for pat, repl in filters:
                line, n = re.subn(pat, repl, line)
                if n > 0:
                    print filename + ": substituted: \"" + pat + "\" with: \"" + repl + "\"."
                    break
            os.write(th, line + '\n')

        os.close(th)
        h.close()
        self.ex('mv', tname, filename)

    def create_fs(self, path, fstype = 'ext3'):
        if fstype == 'ext3':
            self.ex('mkfs.ext3', '-F', '-j', path)
        elif fstype == 'ext2':
            self.ex('mkfs.ext2', '-F', path)
        else:
            raise ValueError('Unknown fstype %s.' % repr(fstype))

    def add_divert(self, filename, perms=0755):
        self.ex('/usr/sbin/dpkg-divert', '--add', '--local',
                     '--rename', '--divert', filename + '.real', filename)
        self.write(filename, '#!/bin/sh\nexit 0\n', perms=perms)

    def remove_divert(self, filename):
        self.remove(filename)
        self.ex('/usr/sbin/dpkg-divert', '--remove', filename)

    def debian_packages(self):
        p = PackageInstall(self)
        self.add_cleanup(p)
        p.prepare()
        return p

    def get_dpkg_list(self):
        # FIXME: ... this interface is very ugly..
        workdir = 'workdir'
        bd_work = self.get_cwd(os.path.join(self.env.path, workdir))
        rc, stdout, stderr = bd_work.run(['dpkg', '-l'], env=self.env, retval=runcommand.FAIL)
        return stdout

    def create_isolinux_image(self, source, imagename, target, osx_autorun=None):
        # FIXME: some cleaner way...
        if osx_autorun is not None:
            self.ex('/usr/bin/mkisofs', '-r', '-V', imagename, '-cache-inodes', '-J', '-l', '-b', 'isolinux/isolinux.bin', '-c', 'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table', '-auto', str(osx_autorun), '-o', target, source)
        else:
            self.ex('/usr/bin/mkisofs', '-r', '-V', imagename, '-cache-inodes', '-J', '-l', '-b', 'isolinux/isolinux.bin', '-c', 'isolinux/boot.cat', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table', '-o', target, source)

    def debootstrap(self, path, suite, source):
        self.ex('debootstrap', suite, path, source)

    def unpack_deb_source(self, control):
        self.ex('/usr/bin/dpkg-source', '-x', control)

    def patch_dir(self, srcdir, patches):
        bs = self.get_cwd(os.path.join(self.env.path, srcdir))
        for i in patches:
            self.build.info('Using patch: ' + i)
            bs.ex('test', '-f', i) # The command below does not catch a missing file.
            bs.sh('cat ' + i + ' | patch -p1')

    def _do_changelog(self, srcdir, cmd, text):
        bs = self.get_cwd(os.path.join(self.env.path, srcdir))

        c = ['/usr/bin/debchange', '--noconf', '--no-query', '--distribution', 'dapper', '--urgency', 'high']
        c.extend(cmd)
        c.append(text)

        myenv = os.environ
        myenv['DEBFULLNAME'] = 'VPNease support'
        myenv['DEBEMAIL'] = 'support@vpnease.com'
        bs.ex(c, env=myenv)

    def changelog_create(self, srcdir, revision, text, package=None):
        cmd = ['--create']

        if package is not None:
            cmd.extend(['--package', package])

        cmd.extend(['--newversion', revision, '--preserve'])

        self._do_changelog(srcdir, cmd, text)

    def changelog_newversion(self, srcdir, revision, text):
        cmd = ['--newversion', revision]
        self._do_changelog(srcdir, cmd, text)

    def changelog_append(self, srcdir, text):
        cmd = ['--append']
        self._do_changelog(srcdir, cmd, text)

    def build_deb_from_source(self, srcdir, nodep=False):
        bs = self.get_cwd(os.path.join(self.env.path, srcdir))
        bs.chmod('debian/rules', 0755)
        build = ['/usr/bin/dpkg-buildpackage', '-us', '-uc', '-b', '-rfakeroot']
        if nodep:
            build += ['-d']

        bs.ex(*build)

    def build_kernel(self, srcdir):
        bs = self.get_cwd(os.path.join(self.env.path, srcdir))

        # Note: we use server config as a basis, but do not want
        # to build it as "server" package. Instead we copy it to
        # the default (386) config name. Building server package
        # seems to break d-i build because debian/kernel-versions
        # file is wrong.
        bs.ex('/bin/cp', '-f',
              'debian/config/i386/config.server',
              'debian/config/i386/config.386')

        # Note: server version of config file is 686 -based which
        # is just fine. Other kernel versions are just disabled.
        for r, d, f in bs.walk('debian/config/i386/'):
	    for i in f:
	        if len(i.split('.')) < 2:
                    continue
                if i.split('.')[1] == '386':
                    continue
                bs.ex('/bin/mv', '-f', os.path.join(r, i), os.path.join(r, i + '.disabled'))
            break

        # Note: UBUNTUBUILD not required here, because it is set in the
        # debian/rules anyways
	# Note: cannot use dpkg-buildpackage when some i368 flavours
	# are disabled because genchanges target does not check disabled
	# and panics.
	# Note: .udebs are also built by default even if not used by us

        # Hack warning: remove binary-udebs from targets to build
        # so that problems with d-i packages are avoided.
        bs.filter_lines('debian/rules', [['binary-arch: binary-debs binary-udebs', 'binary-arch: binary-debs']])
        bs.chmod('debian/rules', 0755)

        bs.ex('debian/rules', 'build')
	bs.ex('/usr/bin/fakeroot', 'debian/rules', 'binary-arch')


    # NOTE: Ubuntu grub (namely update-grub) is patched to include default
    # value for "defoptions" variable (quiet splash). This makes it impossible
    # to undefine defoptions from menu.lst because empty variable value
    # is treated as missing -> default is used. Must use some safe dummy
    # kernel option or patch the update-grub.. duh.
    # Quick fix: leave the "quiet" option there.
    # Better fix: use "-z xxx", which is passed to init by kernel
    # and ignored by init :)
    def install_graphics_scripts(self):
        if not isinstance(self.env, ChrootBuildEnvironment):
            raise BuildError('install_graphics_scripts not in chrooted environment.')

        self.write('/etc/disable-graphics', textwrap.dedent("""\
        #!/bin/sh
        # This script disables default splash image from booting
        # kernel and also disables X server in system startup.

        set -e
        mv /boot/grub/menu.lst /boot/grub/menu.lst.orig
        # Note: Ubuntu version of update-grub includes a default for
        # defoptions variable and setting variable to empty value will
        # thus not work. We use -z option which is passed to init by
        # kernel and ignored by init instead of empty string.
        cat /boot/grub/menu.lst.orig | perl -e 'while (<>) { s/^#\s*defoptions=.*$/# defoptions=-z ignored_by_init/; print $_}' > /boot/grub/menu.lst
        /sbin/update-grub
        echo \"Splash image disabled.\"
        /usr/sbin/update-rc.d -f gdm remove
        /usr/sbin/update-rc.d gdm stop 01 0 1 6 . stop 80 2 3 4 5 .
        echo \"X server startup disabled.\"
        echo \"Reboot to see the effects. Run sh /etc/enable-graphics to revert the changes.\"
        """), perms=0755)

        self.write('/etc/enable-graphics', textwrap.dedent("""\
        #!/bin/sh
        # This script (re)enables default splash image in kernel boot
        # and also (re)enables the X server in system startup.

        set -e
        mv /boot/grub/menu.lst /boot/grub/menu.lst.orig
        cat /boot/grub/menu.lst.orig | perl -e 'while (<>) { s/^#\s*defoptions=.*$/# defoptions=quiet splash/; print $_}' > /boot/grub/menu.lst
        /sbin/update-grub
        echo \"Splash image enabled.\"
        /usr/sbin/update-rc.d -f gdm remove
        /usr/sbin/update-rc.d gdm stop 01 0 1 6 . start 99 2 3 4 5 .
        echo \"X server startup enabled.\"
        echo \"Reboot to see the effects. Run sh /etc/disable-graphics to revert the changes.\"
        """), perms=0755)

    def extract_livecd(self, image):
        comp_filesystem = 'casper/filesystem.squashfs'
        sourcemnt = 'ubuntu-iso-mnt'
        targetdir = 'live-cd-target'
        squashmnt = 'squash-mnt'
        workdir = 'workdir'

        self.mkdir(sourcemnt)
        self.mkdir(targetdir)
        self.mkdir(squashmnt)

        bd_target = self.get_cwd(os.path.join(self.env.path, targetdir))
        bd_target_chroot = self.get_chroot(os.path.join(self.env.path, targetdir))

        self.build.info('Extracting live-cd image:')
        m = self.mount(image, sourcemnt)
        self.build.info('  Extracting live-cd contents.')
        cmd = ['/usr/bin/rsync', '-a']
        for i in [comp_filesystem, 'bin', 'disctree', 'pics', 'programs', 'autorun.inf', 'start.*', 'ubuntu.ico']:
            cmd += ['--exclude=' + i]
        cmd += [os.path.join(sourcemnt, ''), targetdir]
        self.ex(*cmd)
        self.build.info('  Extracting compressed filesystem image.')
        m1 = self.mount(os.path.join(sourcemnt, comp_filesystem), squashmnt, filesystem='squashfs')
        self.ex('/bin/cp', '-ar', squashmnt, workdir)
        m1.umount()
        m.umount()

    def delete_apt_keys(self, dest):
        dest.ex('/bin/rm', '-f', '/etc/apt/trusted.gpg', retval=runcommand.FAIL)
        dest.ex('/bin/rm', '-f', '/etc/apt/trustdb.gpg', retval=runcommand.FAIL)
        dest.ex('/usr/bin/apt-key', 'list', retval=runcommand.FAIL) # recreates gpg files
        dest.ex('/usr/bin/apt-key', 'list', retval=runcommand.FAIL)

    def setup_apt_keys(self, gnupg_path, dest, keys):
        for key in keys:
            myenv = os.environ
            myenv['GNUPGHOME'] = gnupg_path
            [rv, out, err] = self.ex_c('/usr/bin/gpg', '-a', '--export', key, retval=runcommand.FAIL)
            [rv, out, err] = dest.ex('/usr/bin/apt-key', 'add', '-', stdin=out, retval=runcommand.FAIL)

    def prepare_extracted_livecd(self, sources=None, ubuntu_packages=None):
        self.build.info('Preparing extracted livecd:')

        if ubuntu_packages is not None:
            if sources is None:
                raise BuildError('Repository source paths required.')

        #
        # FIXME: this list should be somewhere else...
        #
        
        # Note: some packages need to be removed so that the resulting
        # image is not over 700MB
        # Note: the order is significant here because the of the remove-helper
        packages_to_purge = []

        # Ubuntu "top level" packages; pretty problematic, even ubuntu-minimal includes
        # unnecessary stuff like jfsutils, and other (unused) filesystem utils.
        #
        # Leave ubuntu-minimal in for now; this needs fixing later in repo model.
        packages_to_purge += ['ubuntu-base', 'ubuntu-standard', 'ubuntu-desktop', 'ubuntu-live']

        packages_to_purge += ['x-window-system-core']  # metapackage

        packages_to_purge += ['gimp-print', 'gimp-python', 'gimp', 'gimp-data']
        packages_to_purge += ['openoffice.org-common'] # removes most of the openoffice stuff
        packages_to_purge += ['gnome-app-install', 'app-install-data', 'update-notifier', 'unattended-upgrades', 'update-manager']
        packages_to_purge += ['slocate']  # cannot remove findutils, ubuntu-minimal depends on it
        packages_to_purge += ['synaptic', 'language-selector']

        # these from a walkthrough of installed packages
        packages_to_purge += ['anacron']
        packages_to_purge += ['bluez-cups']
        packages_to_purge += ['bluez-pcmcia-support']
        packages_to_purge += ['bluez-utils']
        packages_to_purge += ['brltty']
        packages_to_purge += ['brltty-x11']
        packages_to_purge += ['wvdial']
        packages_to_purge += ['bicyclerepair']
        packages_to_purge += ['bsh']
        packages_to_purge += ['fastjar']
        packages_to_purge += ['gdb']
        packages_to_purge += ['gij-4.1']
        #packages_to_purge += ['mcpp']
        packages_to_purge += ['diveintopython']
        packages_to_purge += ['doc-base']
        packages_to_purge += ['doc-debian']
        packages_to_purge += ['info']
        packages_to_purge += ['openoffice.org-help-en-us']
        packages_to_purge += ['openoffice.org-l10n-common']
        packages_to_purge += ['openoffice.org-l10n-en-gb']
        packages_to_purge += ['openoffice.org-l10n-en-us']
        packages_to_purge += ['openoffice.org-l10n-en-za']
        packages_to_purge += ['openoffice.org-thesaurus-en-us']
        packages_to_purge += ['openoffice.org-gnome']
        packages_to_purge += ['openoffice.org-core']
        packages_to_purge += ['openoffice.org-gnome']
        packages_to_purge += ['openoffice.org-writer']
        packages_to_purge += ['openoffice.org-impress']
        packages_to_purge += ['openoffice.org-draw']
        packages_to_purge += ['openoffice.org-gtk']
        packages_to_purge += ['openoffice.org-evolution']
        packages_to_purge += ['openoffice.org-math']
        packages_to_purge += ['openoffice.org-common']
        packages_to_purge += ['openoffice.org-base']
        packages_to_purge += ['openoffice.org-calc']
        packages_to_purge += ['openoffice.org-java-common']
        packages_to_purge += ['openoffice.org']
        packages_to_purge += ['python-uno']
        packages_to_purge += ['fortune-mod']
        packages_to_purge += ['fortunes-min']
        packages_to_purge += ['gnome-games']
        packages_to_purge += ['gnome-games-data']
        packages_to_purge += ['bug-buddy']
        packages_to_purge += ['at-spi']
        packages_to_purge += ['contact-lookup-applet']
        packages_to_purge += ['ekiga']
        packages_to_purge += ['eog']
        packages_to_purge += ['evolution']
        packages_to_purge += ['evolution-data-server']
        packages_to_purge += ['evolution-exchange']
        packages_to_purge += ['evolution-plugins']
        packages_to_purge += ['evolution-webcal']
        packages_to_purge += ['gnome-accessibility-themes']
        packages_to_purge += ['gnome-cups-manager']
        packages_to_purge += ['gnome-doc-utils']
        packages_to_purge += ['gnome-media']
        packages_to_purge += ['gnome-pilot']
        packages_to_purge += ['gnome-pilot-conduits']
        packages_to_purge += ['gnome-spell']
        packages_to_purge += ['gnome2-user-guide']
        packages_to_purge += ['gthumb']
        packages_to_purge += ['libgdl-1-0']
        packages_to_purge += ['libgdl-1-common']
        packages_to_purge += ['nautilus-cd-burner']
        packages_to_purge += ['nautilus-sendto']
        packages_to_purge += ['rhythmbox']
        packages_to_purge += ['screensaver-default-images']
        packages_to_purge += ['serpentine']
        packages_to_purge += ['sound-juicer']
        packages_to_purge += ['ssh-askpass-gnome']
        packages_to_purge += ['totem']
        packages_to_purge += ['totem-gstreamer']
        packages_to_purge += ['totem-xine']
        packages_to_purge += ['tsclient']
        packages_to_purge += ['vino']
        packages_to_purge += ['gimp']
        packages_to_purge += ['gimp-data']
        packages_to_purge += ['gimp-print']
        packages_to_purge += ['libgimp2.0']
        packages_to_purge += ['gimp-python']
        packages_to_purge += ['min12xxw']
        packages_to_purge += ['libsane']
        packages_to_purge += ['libsane-dev']
        packages_to_purge += ['python2.4-imaging']
        packages_to_purge += ['python2.4-imaging-sane']
        packages_to_purge += ['python-imaging-sane']
        packages_to_purge += ['python-imaging']
        packages_to_purge += ['xsane']
        packages_to_purge += ['xsane-common']
        packages_to_purge += ['gstreamer0.10-alsa']
        packages_to_purge += ['gstreamer0.10-esd']
        packages_to_purge += ['gstreamer0.10-gnomevfs']
        packages_to_purge += ['gstreamer0.10-plugins-base']
        packages_to_purge += ['kamera']
        packages_to_purge += ['libgphoto2-2']
        packages_to_purge += ['libgphoto2-2-dev']
        packages_to_purge += ['libgphoto2-port0']
        packages_to_purge += ['pnm2ppa']
        packages_to_purge += ['gs']
        
        # leave gstreamer0.10-plugins-good installed ?
        packages_to_purge += ['python2.4-gnome2-desktop']
        packages_to_purge += ['python-gnome2-desktop']
        packages_to_purge += ['python2.4-gnome2-extras']
        packages_to_purge += ['deskbar-applet']
        packages_to_purge += ['guile-1.6-libs']
        packages_to_purge += ['libaudio2']
        packages_to_purge += ['libbluetooth1']
        packages_to_purge += ['libbtctl2']
        packages_to_purge += ['bluez-pin']
        packages_to_purge += ['libbrlapi1']
        packages_to_purge += ['gnopernicus']
        packages_to_purge += ['libcupsimage2']
        packages_to_purge += ['libcupsys2']
        packages_to_purge += ['cupsys']
        packages_to_purge += ['cupsys-bsd']
        packages_to_purge += ['cupsys-client']
        packages_to_purge += ['gs-esp']
        packages_to_purge += ['hplip']
        packages_to_purge += ['hplip-data']
        packages_to_purge += ['hplip-ppds']
        packages_to_purge += ['hpijs']
        packages_to_purge += ['cupsys-driver-gimpprint']
        packages_to_purge += ['cupsys-driver-gutenprint']
        packages_to_purge += ['ijsgimpprint']
        packages_to_purge += ['ijsgutenprint']
        packages_to_purge += ['libgutenprint2']
        packages_to_purge += ['libgutenprintui2-1']
        packages_to_purge += ['libsnmp-base']
        packages_to_purge += ['libsnmp-perl']
        packages_to_purge += ['libsnmp-session-perl']
        packages_to_purge += ['libsnmp9']
        packages_to_purge += ['libsnmp9-dev']
        packages_to_purge += ['snmp']
        packages_to_purge += ['snmpd']
        packages_to_purge += ['libgnomecups1.0-1']
        packages_to_purge += ['libgnomecupsui1.0-1c2a']
        packages_to_purge += ['libgnomeprint2.2-0']
        packages_to_purge += ['libgnomeprint2.2-data']
        packages_to_purge += ['libgnomeprintui2.2-0']
        packages_to_purge += ['libgnomeprintui2.2-common']
        packages_to_purge += ['libgtkhtml3.8-15']
        packages_to_purge += ['libgtksourceview1.0-0']
        packages_to_purge += ['gedit']
        packages_to_purge += ['hpijs']
        packages_to_purge += ['language-support-en']
        packages_to_purge += ['gnome-utils']
        packages_to_purge += ['gs-common']
        packages_to_purge += ['gok']
        # packages_to_purge += ['libidl0']  --> firefox...
        packages_to_purge += ['java-gcj-compat']
        packages_to_purge += ['gtkhtml3.8']
        packages_to_purge += ['yelp']
        # packages_to_purge += ['xrdb']  --> gdm
        packages_to_purge += ['python-gnome2-desktop']
        packages_to_purge += ['evince']
        packages_to_purge += ['festival']
        packages_to_purge += ['festival-dev']

        packages_to_purge += ['libgnucrypto-java']
        packages_to_purge += ['libjaxp1.2-java']
        packages_to_purge += ['foomatic-db-gutenprint']
        packages_to_purge += ['python-gnome2-extras']
        packages_to_purge += ['python2.4-gnome2-extras']
        packages_to_purge += ['python-gnome2-desktop']
        packages_to_purge += ['python2.4-gnome2-desktop']
        packages_to_purge += ['python2.4-gnome2']
        packages_to_purge += ['python-gnome2']
        packages_to_purge += ['python-gnome2-desktop']
        packages_to_purge += ['python2.4-gnome2-desktop']
        packages_to_purge += ['hwdb-client']
        packages_to_purge += ['libxt-java']
        #packages_to_purge += ['xbase-clients'] => gdm
        packages_to_purge += ['python2.4-pyorbit']
        packages_to_purge += ['python-pyorbit']
        packages_to_purge += ['thunderbird-locale-en-gb']
        packages_to_purge += ['festlex-cmu']
        packages_to_purge += ['foomatic-db-hpijs']
        packages_to_purge += ['festlex-poslex']
        packages_to_purge += ['libjline-java']
        packages_to_purge += ['libxerces2-java']
        packages_to_purge += ['festvox-kallpc16k']
        packages_to_purge += ['libgnome-speech3']
        packages_to_purge += ['libhsqldb-java']
        packages_to_purge += ['foomatic-filters-ppds']
        packages_to_purge += ['libservlet2.3-java']
        packages_to_purge += ['libjessie-java']
        packages_to_purge += ['libxalan2-java']
        packages_to_purge += ['libxerces2-java']
        packages_to_purge += ['deskbar-applet']
        packages_to_purge += ['serpentine']
        #packages_to_purge += ['libgksu1.2-1'] => gdm
        #packages_to_purge += ['libgksuui1.0-1'] => gdm

        packages_to_purge += ['example-content']
        packages_to_purge += ['xscreensaver']
        packages_to_purge += ['xscreensaver-gl']
        packages_to_purge += ['xscreensaver-data']
        packages_to_purge += ['screensaver-default-images']
        packages_to_purge += ['popularity-contest']

        packages_to_purge += ['samba']
        packages_to_purge += ['samba-common']
        packages_to_purge += ['samba-doc']
        packages_to_purge += ['samba-doc-pdf']
        packages_to_purge += ['smbclient']
        packages_to_purge += ['smbfs']
        packages_to_purge += ['swat']

        packages_to_purge += ['synaptic']
        packages_to_purge += ['update-manager']
        packages_to_purge += ['language-selector']
        packages_to_purge += ['update-notifier']

        packages_to_purge += ['bittornado']
        packages_to_purge += ['bittorrent']
        packages_to_purge += ['gnome-btdownload']

        packages_to_purge += ['cdrtools']
        packages_to_purge += ['cdrecord']
        packages_to_purge += ['cdrtools-doc']
        packages_to_purge += ['dvd+rw-tools']
        packages_to_purge += ['nautilus-cd-burner']
        
        packages_to_purge += ['alacarte']

        packages_to_purge += ['liblockfile1']
        packages_to_purge += ['mailx']
        
        packages_to_purge += ['gaim']
        packages_to_purge += ['gaim-dev']
        packages_to_purge += ['gaim-data']
        
        # packages_to_purge += ['beforelight']  deps
        # packages_to_purge += ['bitmap']  deps
        packages_to_purge += ['cdparanoia']
        packages_to_purge += ['cdrdao']
        packages_to_purge += ['dc']
        
        packages_to_purge += ['dictionaries-common']
        packages_to_purge += ['aspell']
        packages_to_purge += ['aspell-en']
        packages_to_purge += ['myspell-en-gb']
        packages_to_purge += ['myspell-en-us']
        packages_to_purge += ['wamerican']
        packages_to_purge += ['wbritish']

        packages_to_purge += ['dselect']
        # packages_to_purge += ['docbook-xml']  ==> can't purge, deps on many fronts...
        # packages_to_purge += ['editres']   ==> can't purge, deps on many fronts...

        packages_to_purge += ['foo2zjs']
        packages_to_purge += ['foomatic-db']
        packages_to_purge += ['foomatic-db-engine']
        packages_to_purge += ['foomatic-filters']
        packages_to_purge += ['ftp']
        packages_to_purge += ['gcalctool']
        # packages_to_purge += ['ico']  ==> can't purge, xbase-clients
        packages_to_purge += ['irssi']
        packages_to_purge += ['lftp']

        packages_to_purge += ['rdesktop']
        packages_to_purge += ['reportbug']
        packages_to_purge += ['rss-glx']
        # packages_to_purge += ['smproxy']  ==> deps
        # packages_to_purge += ['wireless-tools']  ==> deps
        # packages_to_purge += ['wpasupplicant']  ==> deps
        
        packages_to_purge += ['gnome-themes']
        packages_to_purge += ['gtk2-engines-clearlooks']
        packages_to_purge += ['gtk2-engines-crux']
        packages_to_purge += ['gtk2-engines-highcontrast']
        packages_to_purge += ['gtk2-engines-industrial']
        packages_to_purge += ['gtk2-engines-lighthouseblue']
        packages_to_purge += ['gtk2-engines-mist']
        packages_to_purge += ['gtk2-engines-pixbuf']
        packages_to_purge += ['gtk2-engines-redmond95']
        packages_to_purge += ['gtk2-engines-smooth']
        packages_to_purge += ['gtk2-engines-thinice']
        # FIXME: leaves gtk2-engines-ubuntulooks - NB: vpnease must depend on this theme, or some other theme, since we don't have gnome-themes now

        packages_to_purge += ['evms']
        packages_to_purge += ['evms-ncurses']
        packages_to_purge += ['lvm-common']
        packages_to_purge += ['lvm2']
        packages_to_purge += ['mdadm']

        # FIXME: don't like to nuke these, but do for now
        packages_to_purge += ['gnome-volume-manager']
        packages_to_purge += ['gnome-system-monitor']
        # packages_to_purge += ['gksu']  # can't remove => gdm
        packages_to_purge += ['hal-device-manager']

        # Covered by ubuntu-minimal
        packages_to_purge += ['ubuntu-minimal']
        packages_to_purge += ['jfsutils']
        packages_to_purge += ['reiser4progs']
        packages_to_purge += ['reiserfsprogs']
        packages_to_purge += ['xfsprogs']
        packages_to_purge += ['ntpdate']
        packages_to_purge += ['wireless-tools']
        packages_to_purge += ['wpasupplicant']

        #   all laguage packs except "en"
        for i, j in [['a', 'fmnrsz'], ['b', 'egrs'], ['c', 'aosy'], ['d', 'ae'], ['e', 'lnostu'], ['f', 'ar'], ['h', 'i'], ['j', 'a'], ['p', 't'], ['r', 'u'], ['x', 'h'], ['z', 'h']]:
            for k in j:
                lang = '%s%s' % (i, k)
                packages_to_purge += ['language-pack-%s' % lang]
                packages_to_purge += ['language-pack-%s-base' % lang]
                packages_to_purge += ['language-pack-gnome-%s' % lang]
                packages_to_purge += ['language-pack-gnome-%s-base' % lang]

        # FIXME: some other, untested
        packages_to_purge += ['zenity']
        packages_to_purge += ['gedit-common']
        packages_to_purge += ['tango-icon-theme']
        packages_to_purge += ['tangerine-icon-theme']
        packages_to_purge += ['tango-icon-theme-common']
        packages_to_purge += ['blt']
        packages_to_purge += ['python-epydoc']
        packages_to_purge += ['python-tk']
        packages_to_purge += ['python-unit']
        packages_to_purge += ['python2.4-epydoc']
        packages_to_purge += ['python2.4-tk']
        packages_to_purge += ['python2.4-unit']
        packages_to_purge += ['alsa-base']
        packages_to_purge += ['ubuntu-docs']
        packages_to_purge += ['poppler-utils']

        # FIXME: more packages ubuquity related packages cannot be
        # removed here, but must be sure that they are removed by the
        # ubuquity installer!

        packages_to_purge += ['libopal']
        packages_to_purge += ['ubuntu-artwork']
        packages_to_purge += ['libgcj7-jar']
        packages_to_purge += ['libglew1']
        packages_to_purge += ['libgl1-mesa-dri']


        """
        packages_to_purge += ['']
        packages_to_purge += ['']
        packages_to_purge += ['']
        packages_to_purge += ['']
        packages_to_purge += ['']
        """

        # ttf fonts:
        packages_to_purge += ['ttf-arabeyes']
        packages_to_purge += ['ttf-arphic-ukai']
        packages_to_purge += ['ttf-arphic-uming']
        packages_to_purge += ['ttf-baekmuk']
        packages_to_purge += ['ttf-bengali-fonts']
        packages_to_purge += ['ttf-devanagari-fonts']
        packages_to_purge += ['ttf-gujarati-fonts']
        packages_to_purge += ['ttf-indic-fonts']
        packages_to_purge += ['ttf-kannada-fonts']
        packages_to_purge += ['ttf-kochi-gothic']
        packages_to_purge += ['ttf-kochi-mincho']
        packages_to_purge += ['ttf-lao']
        packages_to_purge += ['ttf-malayalam-fonts']
        packages_to_purge += ['ttf-oriya-fonts']
        packages_to_purge += ['ttf-punjabi-fonts']
        packages_to_purge += ['ttf-tamil-fonts']
        packages_to_purge += ['ttf-telugu-fonts']
        packages_to_purge += ['ttf-thai-tlwg']

        # Firefox related packages must be removed so that new firefox
        # build from sources can be installed.
        packages_to_purge += ['firefox']
        packages_to_purge += ['firefox-gnome-support']
        packages_to_purge += ['mozilla-firefox-locale-en-gb']

        # FIXME: maybe more fonts to purge:
        """
        packages_to_purge += ['ttf-bitstream-vera']
        packages_to_purge += ['ttf-dejavu']
        packages_to_purge += ['ttf-freefont']
        packages_to_purge += ['ttf-gentium']
        packages_to_purge += ['ttf-mgopen']
        packages_to_purge += ['ttf-opensymbol']
        """

        # python-pysqlite2 used instead of this
        packages_to_purge += ['python-sqlite']

        # FIXME: can nuke, but has effects, nuke when no more used.
        #   ubuntu-artwork
        
        # FIXME ... in middle
        
        # FIXME: potential list of further nukes
        #   gamin
        #   gnome-applets
        #   desktop-file-utils
        #   gcc-3.3-base
        #   gcc-4.0-base
        #   man-db
        #   manpages
        #   gnome-keyring
        #   language-support-en
        #   gnome-utils
        #   gtkhtml3.8
        #   libbeagle0
        #   nautilus
        #   mesa-utils
        #   freeglut3
        #   gcj-4.1-base
        #   klibc-utils
        #   libaa1
        #   libdb4.3



        # remove dups but keep order
        t = []
        for i in packages_to_purge:
            if not i in t:
                t.append(i)
        packages_to_purge = t

        # sort - remove_packages issues one command, so sorted is better for logging etc
        packages_to_purge.sort()
        
        workdir = 'workdir'

        # FIXME: PackageInstall assumes absolute paths when it
        # takes chrooted self.. fix it later and use abs paths for now.
        bd_work = self.get_cwd(os.path.join(self.env.path, workdir))

        p = bd_work.debian_packages()
        self.build.info('  Remove unwanted Ubuntu packages to save space on cd: %s' % packages_to_purge)

        # FIXME: This is really a nasty hack to get aptitude to remove
        # packages as we remove their dependencies.
        #
        # See e.g.: http://people.debian.org/~dburrows/aptitude-doc/en/ch02s04s05.html
        opts = ['Aptitude::ProblemResolver::InstallScore=-1000',
                'Aptitude::ProblemResolver::PreserveManualScore=-100',
                'Aptitude::ProblemResolver::BrokenScore=-100',
                'Aptitude::ProblemResolver::ResolutionScore=1000',
                'Aptitude::ProblemResolver::RemoveScore=-300',
                'Aptitude::Recommends-Important=false',
                'Aptitude::ProblemResolver::BreakHoldScore=-1000']
        p.remove_packages(packages_to_purge, aptitude_options=opts)

        self.build.info('  Upgrading installed packages from: %s' % sources)
        p.upgrade_packages(sources=sources)

        if ubuntu_packages is not None:
            self.build.info('  Installing additional Ubuntu packages: %s' % ubuntu_packages)
            p.install_packages(ubuntu_packages, sources=sources)

        p.unprepare()

    def package_livecd_image(self, builddir, label, image, osx_autorun=None):
        comp_filesystem = 'casper/filesystem.squashfs'
        manifest = 'casper/filesystem.manifest'
        manifest_desktop = 'casper/filesystem.manifest-desktop'
        targetdir = 'live-cd-target'
        workdir = 'workdir'
        bd_target = self.get_cwd(os.path.join(builddir, targetdir))
        bd_target_chroot = self.get_chroot(os.path.join(builddir, targetdir))

        bd_work = self.get_cwd(os.path.join(builddir, workdir))
        bd_work_chroot = self.get_chroot(os.path.join(builddir, workdir))

        self.build.info('Compiling live-cd image:')

        # Note: must prevent ubuntu installer from removing our packages!!
        # - it even removes packages installed via aptitude and marked
        #   as hold and noauto..
        # - this is because there are two separate manifest files one
        #   for livecd and one for installed system and the installation
        #   program removes files that are only in livecd system.
        # - it is not clear how to regenerate the installed system manifest
        #   file (filesystem.manifest.desktop) without breaking it
        # - there must be some way to find the differencies between them
        #   automatically (other than comparing the original files, that is..)
        #   but so far it has not been found..
        # - the *significant* differences between the two files seem to be:
        #   casper, ubiquity, ubiquity-casper, ubiquity-frontend-gtk, ubiquity-ubuntu-artwork, ubuntu-live, user-setup
        # - solution: generate the -desktop manifest file as the livecd
        #   manifest but leave out the above list of packages. this does not
        #   produce the manifest files exactly as in original ubuntu livecd
        #   but this should not matter much..
        # - Note: someone commented to Ubuntu livecdbuild instructions that
        #   the -desktop file should simply be copied from the other manifest
        #   file, but this approach is at least somewhat cleaner.
        manifest_difference = ['casper', 'ubiquity', 'ubiquity-casper', 'ubiquity-frontend-gtk', 'ubiquity-ubuntu-artwork', 'ubuntu-live', 'user-setup']

        self.build.info('  Updating package lists (manifest files)')
        bd_target.chmod(manifest, 0644)
        bd_target.chmod(manifest_desktop, 0644)
        manifest_tmp = '/tmp/manifest'

        bd_work_chroot.sh('/usr/bin/dpkg-query -W --showformat=\'${Package} ${Version}\n\' > ' + manifest_tmp)
        self.ex('/bin/cp', os.path.join(workdir, manifest_tmp[1:]), os.path.join(targetdir, manifest))

        manifest_string = ''
        for line in open(os.path.join(bd_work_chroot.env.path, manifest_tmp[1:])):
            p = line.split()[0]
            if not p in manifest_difference:
                manifest_string += line
        self.write(os.path.join(targetdir, manifest_desktop), manifest_string, perms=0644)
        bd_work_chroot.remove(manifest_tmp)

        # Note: just to be sure, because mksquashfs updates file instead of
        # overwriting if it exists.
        bd_target.rmrf(comp_filesystem)

        # Note: cannot use cwd environment with two different relative paths
        self.build.info('  Running mksquahsfs.')
        self.ex('/usr/sbin/mksquashfs', workdir, os.path.join(targetdir, comp_filesystem))

        # Note: this file will be created by mkisofs and if not removed
        # from source, the md5sum will not match.
        bd_target.ex('/bin/rm', '-f', 'isolinux/boot.cat')

        self.build.info('  Updating md5sum file.')
        bd_target.ex('/bin/rm', '-f', 'md5sum.txt')

        # Note: isolinux/isolinux.bin is changed on disk when mkisofs
        # is run => exclude from md5sum.txt file

        bd_target.sh('/usr/bin/find . ! -name isolinux.bin -and -type f -print0 > ../files.txt')
        bd_target.sh('/bin/cat ../files.txt | /usr/bin/xargs -0 md5sum > md5sum.txt')
        self.remove('files.txt')

        self.build.info('  Creating ISOLINUX CD image')
        bd_target.create_isolinux_image('.', label, image, osx_autorun=osx_autorun)

class BuildRunner:
    def __init__(self, p):
        self.parser = p
        self.options = self.parser.options
        self.cleanup = None
        self._init_environment()
        self._init_logging()
    def _init_vc_info(self, buildtype, path):
        if self.options.revision is None:
            rv, out, err = runcommand.call('svnversion', path)
            if rv != 0:
                self.parser.error('could not gather version control information from source directory')
            self.revision = out.strip()
        else:
            self.revision = self.options.revision

        if self.options.branch is None:
            self.branch = '' # FIXME: branch detection
        else:
            self.branch = self.options.branch

        if self.options.buildinfo is None:
            rv, out, err = runcommand.call('hostname')
            if rv != 0:
                self.parser.error('could not get hostname')
            hostname = out.strip()
            self.buildinfo = '%s build on %s' % (buildtype, hostname)
        else:
            self.buildinfo = self.options.buildinfo

        if self.options.buildnote is None:
            self.buildnote = '' # FIXME
        else:
            self.buildnote = self.options.buildnote

    def _init_environment(self):
        self.srcdir = os.path.abspath(self.options.srcdir)
        if not os.path.exists(self.srcdir):
            self.parser.error('"%s" does not exist' % self.srcdir)
        if not os.path.isdir(self.srcdir):
            self.parser.error('"%s" is not a directory' % self.srcdir)

        self.work = True
        self.export = False
        if self.options.export:
            self.work = False
            self.export = True
            self._init_vc_info('Export', self.srcdir)
            export_base = os.path.abspath(self.options.export_base)
            if not os.path.exists(export_base):
                self.parser.error('"%s" does not exist' % export_base)
            if not os.path.isdir(export_base):
                self.parser.error('"%s" is not a directory' % export_base)
            name = 'build-%s' % datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
            newdir = os.path.join(export_base, name)
            rv, out, err = runcommand.call('svn', 'export', self.srcdir, newdir)
            if rv != 0:
                self.parser.error('could not export source directory')
            self.srcdir = newdir
        else:
            self._init_vc_info('Workdir', self.srcdir)

        if self.options.tempdir is not None:
            self.tempdir = os.path.abspath(self.options.tempdir)
        else:
            self.tempdir = os.path.join(self.srcdir, '_build_temp')
        
        if os.path.exists(self.tempdir):
            if not os.path.isdir(self.tempdir):
                self.parser.error('"%s" is not a directory' % self.tempdir)
        else:
            try:
                os.mkdir(self.tempdir)
            except OSError, e:
                self.parser.error('Could not create directory: %s' % e)

    def _init_logging(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.NOTSET)
        
        defaultformat = logging.Formatter('[%(asctime)s %(levelname)8s]: %(message)s')
        output = logging.StreamHandler(sys.stdout)
        output.setFormatter(defaultformat)
        if not self.options.debug:
            output.setLevel(logging.INFO)
        self.logger.addHandler(output)

        output = handlers.RotatingFileHandler(os.path.join(self.tempdir, 'build.log'),
                                              maxBytes=1*1024*1024,
                                              backupCount=10)
        output.setFormatter(defaultformat)
        output.setLevel(logging.INFO)
        self.logger.addHandler(output)

        output = handlers.RotatingFileHandler(os.path.join(self.tempdir, 'debug.log'),
                                              maxBytes=1*1024*1024,
                                              backupCount=10)
        output.setFormatter(defaultformat)
        self.logger.addHandler(output)

        output = logging.FileHandler(os.path.join(self.tempdir, 'latest-build.log'), 'w')
        output.setFormatter(defaultformat)
        output.setLevel(logging.INFO)
        self.logger.addHandler(output)

        output = logging.FileHandler(os.path.join(self.tempdir, 'latest-debug.log'), 'w')
        output.setFormatter(defaultformat)
        self.logger.addHandler(output)

        self.debug = self.logger.debug
        self.info = self.logger.info
        self.warning = self.logger.warning
        self.error = self.logger.error
        self.critical = self.logger.critical
        self.log = self.logger.log
        self.exception = self.logger.exception

    def _do_cleanup(self, is_error=False):
        if not is_error:
            self.info('Cleaning up.')
        else:
            self.info('Cleaning up [ignoring errors].')
        while len(self.cleanup):
            c = self.cleanup.pop()
            if not is_error:
                c.cleanup()
            else:
                try:
                    c.cleanup_error()
                except BuildError, e:
                    self.warning('Error while cleaning up: %s' % e)
                except:
                    self.warning('Error while cleaning up', exc_info=True)

    def add_cleanup(self, o):
        self.cleanup.append(o)

    def _run_build(self, buildclass, options, intf):
        try:
            curbuild = buildclass(options)
            self.debug('+++ Initializing +++')
            curbuild.init(intf)
            self.debug('+++ Running build +++')
            curbuild.run(intf)
            self.debug('+++ Running cleanup +++')
        except BuildError, e:
            self.error('Error while building: %s' % e)
            raise
        except KeyboardInterrupt, e:
            self.error('Build interrupted!')
            raise
        except:
            self.exception('Error while building')
            raise
            
    def run_build(self, buildclass):
        succeeded = False
        name = buildclass.get_name()
        self.cleanup = []
        self.info('*** BUILD "%s" STARTED ***' % name)
        self.info('Source directory: %s' % self.srcdir)
        self.info('Revision:         %s' % self.revision)
        self.info('Branch:           %s' % self.branch)
        self.info('Build info:       %s' % self.buildinfo)
        if self.options.buildnote is not None:
            self.info('Build note:       %s' % self.options.buildnote)
        try:
            env = BuildEnvironment(self)
            intf = BuildInterface(self, env)
            #if self.options.clean:
            #    intf.add_cleanup(CleanupDir(intf, self.tempdir))
            self._run_build(buildclass, self.options, intf)
            self._do_cleanup(is_error=False)
        except:
            self._do_cleanup(is_error=True)
            self.error('*** BUILD "%s" FAILED ***' % name)
        else:
            self.info('*** BUILD "%s" SUCCEEDED ***' % name)
            succeeded = True
        self.cleanup = None
        return succeeded

    def run_subbuild(self, buildclass, intf, values):
        name = buildclass.get_name()
        p = SubbuildOptions(name)
        buildclass.add_options(p)
        p.feed(self.options, values)
        buildclass.check_options(p, p.options)
        self.info('*** SUBBUILD "%s" STARTED ***' % name)
        try:
            self._run_build(buildclass, p.options, intf)
        except:
            self.error('*** SUBBUILD "%s" FAILED ***' % name)
            raise
        else:
            self.info('*** SUBBUILD "%s" SUCCEEDED ***' % name)

    def get_srcdir(self):
        return self.srcdir

    def get_tempdir(self):
        return self.tempdir

_builds = []
def register_build(buildclass):
    _builds.append(buildclass)

def main():
    p = CommandLineOptions()

    if len(sys.argv) <= 1:
        p.parse()
        p.print_usage(sys.stdout)
        print 'targets:'
        for buildclass in _builds:
            print '  %s - %s' % (buildclass.get_name(), buildclass.get_description())
        sys.exit(0)

    curtarget = sys.argv[1]
    curbuildclass = None
    for buildclass in _builds:
        if buildclass.get_name() == curtarget:
            curbuildclass = buildclass
            break
    if curbuildclass is None:
        p.parse(args=sys.argv[2:])
        p.error('no such target')
    else:
        curbuildclass.add_options(p)
        p.parse(args=sys.argv[2:])
        curbuildclass.check_options(p, p.options)
        b = BuildRunner(p)
        failed = False
        if not b.run_build(curbuildclass):
            failed = True
        if failed:
            sys.exit(1)
        else:
            sys.exit(0)
