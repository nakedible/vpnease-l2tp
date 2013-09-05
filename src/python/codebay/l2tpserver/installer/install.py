#!/usr/bin/python

#
# L2TP Gateway Live-CD Installer
#
# arguments: device, hostname, username, password
#

from ubiquity.components import install
from ubiquity import progressposition

from codebay.common import logger
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import mediahelper
from codebay.l2tpserver import runcommand

import os, sys, time, shutil, subprocess, textwrap, posix, datetime, re

run_command = runcommand.run_command

# TODO:
# - copy user home directory to installed system!!!
#   - includes at least .gconf .gnome* directories
# 
# - usb-stick setup: is it ok to pass just the device from UI to grub in this case?
# - filecopy to installed system (logs, etc)
# - set timezone to UTC, set locale to US?
# - cdrom to fstab
# - ext3 tuning
# - swap size down after cd shrink
# - cylinder boundary problem with partitions
# - testuse case (not lowmem, is there any marker if testuse actually was attempted?):
#   - database stop and copy, maybe use export/import functions from UI?
#   - GUI test use system config setup? copy to installed system
#   - set timezone? copy code to set timezone to startup scripts? (to be set at every boot)

class Install:
    def __init__(self):
        self.install_stage = ''
        self.install_info = None
        self.hostname = None
        self.starttime = None
        self.large_install = False
        
        self.position = progressposition.ProgressPosition()
        self._log = logger.get('l2tpserver.installer.install')

    def info (self, msg):
        self._log.info(msg)
        print 'info: %s' % msg

    def error (self, msg):
        self._log.error(msg)
        print 'error: %s' % msg

    def write_status(self, status):
        try:
            helpers.write_file(constants.INSTALL_STATUS_FILE, status, append=False, perms=0644)
        except:
            self.error ('writing installation status failed, ignored.')

    def write_progress(self):
        progress = float(self.position.fraction()*100)
        status = '%d\n%s' % (progress, self.install_stage)

        self.info('set install progress: %s %s' % (progress, self.install_stage))

        if self.starttime is None:
            self.starttime = datetime.datetime.utcnow()

        delta = datetime.datetime.utcnow() - self.starttime

        self.info('progress meter: %s %s %s' % (delta.seconds, progress, self.install_stage))

        if self.install_info is not None:
            status += '\n%s' % self.install_info
        else:
            status += '\n'

        self.write_status (status)

    # Helper funtions to play a role of a UI for Ubiquity installer.
    def get_hostname(self):
        self.info('install get_hostname')
        return self.hostname

    def debconf_progress_cancellable(self, a):
        self.info('debconf progress cancellable')
        return True

    def debconf_progress_start(self, p_min, p_max, p_title):
        self.info('install progress start: %d - %d, %s' % (p_min, p_max, p_title))
        self.position.start(p_min, p_max, p_title)
        self.debconf_progress_set (0)
        return True

    def debconf_progress_region(self, r_start, r_end):
        self.info('install progress region: %d - %d' % (r_start, r_end))
        self.position.set_region(r_start, r_end)
        return True

    def debconf_progress_set(self, val):
        self.info('install progress set: %d' % val)
        self.position.set(val)
        self.write_progress()
        return True

    def debconf_progress_step(self, val):
        self.info('install progress step: %d' % val)
        self.position.step(val)
        self.write_progress()
        return True

    def debconf_progress_info(self, info):
        self.info('install info: %s' % info)
        self.install_info = info
        return True

    def debconf_progress_stop(self):
        self.info('install progress stop')
        self.position.stop()
        self.install_info = None
        return True

    def refresh(self):
        # self.info('install refresh')
        return True

    # Other internal helpers
    def install_stage_set(self, stage):
        self.info('install stage set: %s' % stage)
        self.install_stage = stage
        self.install_info = None

    # We assume clean state when install starts
    # More prepare stuff required by newer ubiquity added
    def prepare(self):
        log_file = '/var/log/installer/syslog'
        version_file = '/var/log/installer/version'
        partman_file = '/var/log/partman'
        # NOTE: this is only to mimic ubiquity script, nothing to do with product version
        # and not really used anywhere except in logs.
        VERSION='1.0.17'

        # This is required only so that ubiquity may copy it to target
        if not os.path.exists(os.path.dirname(log_file)):
            os.makedirs(os.path.dirname(log_file))

        log = open(log_file, 'w')
        print >>log, "Ubiquity %s" % VERSION
        print >>log, "Empty logfile, see /var/run/l2tpgw/install.* files for logs."
        log.close()

        version_log = open(version_file, 'w')
        print >>version_log, 'ubiquity %s' % VERSION
        version_log.close()

        part_log = open(partman_file, 'w')
        print >>part_log, 'empty, partman not run'
        part_log.close()

        self.prepend_path('/usr/lib/ubiquity/compat')

        if os.path.exists("/var/lib/ubiquity/apt-installed"):
            os.unlink("/var/lib/ubiquity/apt-installed")
        if os.path.exists("/var/lib/ubiquity/remove-kernels"):
            os.unlink("/var/lib/ubiquity/remove-kernels")
        shutil.rmtree("/var/lib/partman", ignore_errors=True)

        # Ensure environment for debconf is sane
        if 'DEBIAN_HAS_FRONTEND' in os.environ:
            del os.environ['DEBIAN_HAS_FRONTEND']
        if 'DEBCONF_USE_CDEBCONF' in os.environ:
            del os.environ['DEBCONF_USE_CDEBCONF']
        os.environ['DEBIAN_FRONTEND'] = 'noninteractive'


    # Cleanup after install trying to umount target at least
    def cleanup(self):
        if os.path.exists("/var/lib/ubiquity/apt-installed"):
            os.unlink("/var/lib/ubiquity/apt-installed")
        if os.path.exists("/var/lib/ubiquity/remove-kernels"):
            os.unlink("/var/lib/ubiquity/remove-kernels")
        shutil.rmtree("/var/lib/partman", ignore_errors=True)

        umount_list = ['/target/proc', '/target/dev', '/target/sys', '/target-fat']

        if self.large_install:
            umount_list.append('/target/boot')

        # Try to find "volatile" mount
        [rv, out, err] = run_command(['/bin/uname', '-r'])
        if rv == 0 and out != '':
            umount_list.append('/target/lib/modules/' + out.strip() + '/volatile')

        umount_list.append('/target')
        for i in umount_list:
            try:
                run_command([constants.CMD_UMOUNT, i], retval=runcommand.FAIL)
            except:
                print 'could not umount %s, ignoring' % i

        # nuke target after umount
        #
        # NB: this is a bit dangerous if target umount fails and e.g.
        # /target/dev is still mounted.  This will also nuke the host's
        # own /dev (tmpfs, udev), on install failures.  Thus, an install
        # failure is a pretty undoable event at the moment.
        # run_command([constants.CMD_RM, '-rf', '/target'])

    def wait_for_partition_devices_to_disappear(self, partitions):
        # Wait for the partition devices (if any) to disappear.. sigh.
        for i in xrange(constants.INSTALL_PARTITION_WAIT_DISAPPEAR):
            print 'waiting for partition devices %s to disappear (loop %s)' % (str(partitions), i)
            exists = False
            for j in partitions:
                if os.path.exists(j):
                    exists = True
            if not exists:
                break
            time.sleep(1)

    def wait_for_partition_devices_to_appear(self, partitions):
        # Wait for the partition devices to appear.. sigh.
        for i in xrange(constants.INSTALL_PARTITION_WAIT_APPEAR):
            print 'waiting for partition devices %s to appear (loop %s)' % (str(partitions), i)
            exists = True
            for j in partitions:
                if not os.path.exists(j):
                    exists = False
            if exists:
                break
            time.sleep(1)

    def nuke_and_create_disklabel(self, device):
        # just nuke 1MB from start of disk
        run_command(['/bin/dd', 'if=/dev/zero', 'of=%s' % device, 'bs=512', 'count=2048'], retval=runcommand.FAIL)

        self.debconf_progress_info('Creating new disklabel')
        run_command(['/sbin/parted', '-s', device, 'mklabel', 'msdos'], retval=runcommand.FAIL)

    def create_filesystems(self, device):
        """Repartition the device, create filesystems and /etc/fstab."""

        self.debconf_progress_start(0, 100, '')
        self.debconf_progress_set(0)

        self.debconf_progress_info('Finding target device: %s' % device)

        m = mediahelper.get_media()
        target = m.get_medium_by_device_name(device)
        if target is None:
            self.error('failed to find installation target device: %s' % device)
            raise Exception('failed to find installation target device: %s' % device)

        # determine various parameters for later partitioning and fs setup
        create_swap = True
        part_fat = None
        part_boot = None
        part_swap = None
        part_root = None
        if create_swap:
            if self.large_install:
                part_fat = target.get_partition_devicename(1)
                part_boot = target.get_partition_devicename(2)
                part_swap = target.get_partition_devicename(3)
                part_root = target.get_partition_devicename(4)
                partitions = [part_fat, part_boot, part_swap, part_root]
            else:
                part_fat = target.get_partition_devicename(1)
                part_swap = target.get_partition_devicename(2)
                part_root = target.get_partition_devicename(3)
                partitions = [part_fat, part_swap, part_root]
        else:
            if self.large_install:
                part_fat = target.get_partition_devicename(1)
                part_boot = target.get_partition_devicename(2)
                part_root = target.get_partition_devicename(3)
                partitions = [part_fat, part_boot, part_root]
            else:
                part_fat = target.get_partition_devicename(1)
                part_root = target.get_partition_devicename(2)
                partitions = [part_fat, part_root]

        disk_min_size = (constants.DISK_SIZE_MINIMUM - constants.DISK_SIZE_SAFETY_MARGIN) / 512 * 512 # disk size with safety margin
        disk_size = (target.get_size() - constants.DISK_SIZE_SAFETY_MARGIN) / 512 * 512

        # partition "end points"
        fat_end = '1MB'
        disk_min_end = '%ss' % (disk_min_size / 512)  # sectors
        disk_end = '%ss' % (disk_size / 512)  # sectors

        try:
            self.debconf_progress_info('Wiping target device: %s' % device)

            self.nuke_and_create_disklabel(device)

            # Just in case
            time.sleep(1)
            self.debconf_progress_set(5)
        
            self.wait_for_partition_devices_to_disappear(partitions)

            self.debconf_progress_set(10)

            # MBR is at sector 0, and the first partition should begin at sector 63.
            # This leaves sectors 1...62 as "no man's land" (31kiB) which is used
            # for Grub stage 1.5
            #
            # See: http://en.wikipedia.org/wiki/GNU_GRUB
            #
            # XXX: currently partitions don't end at cylinder
            # boundaries.  It would probably be best to round the
            # partitions up to cylinder boundaries, as a
            # "conservative" partitioning is typically done so.
            # However, this should not matter as long as we only run
            # Grub and Linux itself.
            #
            # NOTE: Even Windows Vista partitions USB sticks without
            # caring about cylinders. Probably not an issue anymore.

            # Just in case
            time.sleep(1)
            self.debconf_progress_set(15)

            # XXX: endpoint is exclusive in parted

            self.debconf_progress_info('Creating partitions')                
            if create_swap:
                if self.large_install:
                    boot_end = '256MB'
                    swap_end = '768MB'
                    parted_cmds = [ ['mkpart', 'primary', 'fat32', '63s', fat_end],
                                    ['mkpart', 'primary', 'ext2', fat_end, boot_end],
                                    ['mkpart', 'primary', 'linux-swap', boot_end, swap_end],
                                    ['mkpart', 'primary', 'ext2', swap_end, disk_end],
                                    ['set', '2', 'boot', 'on'] ]
                else:
                    swap_end = '512MB'
                    parted_cmds = [ ['mkpart', 'primary', 'fat32', '63s', fat_end],
                                    ['mkpart', 'primary', 'linux-swap', fat_end, swap_end],
                                    ['mkpart', 'primary', 'ext2', swap_end, disk_min_end],
                                    ['set', '3', 'boot', 'on'] ]
            else:
                if self.large_install:
                    boot_end = '256MB'
                    parted_cmds = [ ['mkpart', 'primary', 'fat32', '63s', fat_end],
                                    ['mkpart', 'primary', 'ext2', fat_end, boot_end],
                                    ['mkpart', 'primary', 'ext2', boot_end, disk_end],
                                    ['set', '2', 'boot', 'on'] ]
                else:
                    parted_cmds = [ ['mkpart', 'primary', 'fat32', '63s', fat_end],
                                    ['mkpart', 'primary', 'ext2', fat_end, disk_min_end],
                                    ['set', '2', 'boot', 'on'] ]
                
            for i in parted_cmds:
                run_command(['/sbin/parted', '-s', device] + i, retval=runcommand.FAIL)

            self.debconf_progress_set(20)

            # Just in case
            time.sleep(1)
            self.debconf_progress_set(25)

            self.wait_for_partition_devices_to_appear(partitions)

            self.debconf_progress_set(30)

            # Sleep for a while to ensure that there is no "flicker" of device nodes.
            # For some reason this happens with at least native hardware and USB sticks.
            # See #435.
            time.sleep(5)

            self.debconf_progress_set(55)

            self.debconf_progress_info('Creating partitions and filesystems')
            run_command(['/sbin/mkfs.vfat', '-n', constants.PRODUCT_NAME.upper(), part_fat], retval=runcommand.FAIL)

            self.debconf_progress_set(60)

            if part_swap is not None:
                run_command(['/sbin/mkswap', '-L', 'SWAP', part_swap], retval=runcommand.FAIL)

            if part_boot is not None:
                # XXX: opts here?
                run_command(['/sbin/mkfs.ext3',
                             '-L', 'ROOT',
                             '-b', str(1024),
                             '-i', str(4096),
                             '-m', str(0),
                             '-O', 'sparse_super,filetype,resize_inode,dir_index',
                             '-v',
                             part_boot], retval=runcommand.FAIL)
                [rc, stdout, stderr] = run_command(['/sbin/dumpe2fs', part_boot])
                self._log.info('dumpe2fs dump of boot filesystem:\n%s' % stdout)
            else:
                self._log.info('no boot partition, skipping mkfs')
                
            run_command(['/sbin/mkfs.ext3',
                         '-L', 'ROOT',
                         '-b', str(1024),
                         '-i', str(4096),
                         '-m', str(0),
                         '-O', 'sparse_super,filetype,resize_inode,dir_index',
                         '-v',
                         part_root], retval=runcommand.FAIL)
            [rc, stdout, stderr] = run_command(['/sbin/dumpe2fs', part_root])
            self._log.info('dumpe2fs dump of root filesystem:\n%s' % stdout)

            self.debconf_progress_set(95)

        except:
            self.error('failed to create partitions, exiting.')
            raise

        # Create targets and fstab.
        self.debconf_progress_info('Mounting target and creating fstab')

        # Note: not using -p because the target should not exist at this point (cleanup done)
        run_command([constants.CMD_MKDIR, '/target'], retval=runcommand.FAIL)
        run_command([constants.CMD_MKDIR, '/target-fat'], retval=runcommand.FAIL)
            
        run_command([constants.CMD_MOUNT, part_root, '/target'], retval=runcommand.FAIL)
        run_command([constants.CMD_MOUNT, part_fat, '/target-fat'], retval=runcommand.FAIL)

        if part_boot is not None:
            run_command([constants.CMD_MKDIR, '/target/boot'], retval=runcommand.FAIL)
            run_command([constants.CMD_MOUNT, part_boot, '/target/boot'], retval=runcommand.FAIL)

        # Write fstab now (it will not be overwritten by copy process)
        run_command([constants.CMD_MKDIR, '/target/etc/'], retval=runcommand.FAIL)

        fstab = textwrap.dedent("""\
        # /etc/fstab: static file system information.
        #
        # <file system> <mount point>   <type>  <options>       <dump>  <pass>
        proc            /proc           proc    defaults        0       0
        %(part_root)s       /               ext3    defaults,errors=remount-ro,noatime 0       1
        """)
        if part_swap is not None:
            fstab += textwrap.dedent("""\
            %(part_swap)s       none            swap    sw              0       0
            """)
        if part_boot is not None:
            fstab += textwrap.dedent("""\
            %(part_boot)s       /boot           ext3    defaults        0       2
            """)
    
        fstab = fstab % {'part_swap':part_swap, 'part_root':part_root, 'part_boot':part_boot, 'part_fat':part_fat}
        helpers.write_file('/target/etc/fstab', fstab)
        self.debconf_progress_set(100)

        # XXX: cdrom to fstab? nope for now
        # /dev/hdc        /media/cdrom0   iso9660 ro,user,noauto  0       0

        self.debconf_progress_stop()

    def create_and_format_fatdevice(self, device):
        """Repartition the device, create and format one FAT32 partition."""

        self.debconf_progress_start(0, 100, '')
        self.debconf_progress_set(0)
        self.debconf_progress_info('Finding target device: %s' % device)

        m = mediahelper.get_media()
        target = m.get_medium_by_device_name(device)
        if target is None:
            self.error('failed to find formatting target device: %s' % device)
            raise Exception('failed to find formatting target device: %s' % device)

        # determine various parameters for later partitioning and fs setup
        part_fat = target.get_partition_devicename(1)
        partitions = [ part_fat ]
        disk_size = (target.size - constants.INSTALL_FATDEVICE_SAFETY_MARGIN) / 512 * 512
        disk_end = '%ss' % ((disk_size / 512) - 1)  # sectors
        fat_part_name = constants.INSTALL_FATDEVICE_PARTITION_NAME
        
        # XXX: this loop could share code with installer counterpart
        try:
            self.debconf_progress_info('Wiping target device: %s' % device)
            self.nuke_and_create_disklabel(device)
            time.sleep(1)  # just in case
            self.debconf_progress_set(10)
        
            self.wait_for_partition_devices_to_disappear(partitions)
            self.debconf_progress_set(20)

            # See MBR and partition cylinder-alignment related notes above
            time.sleep(1)  # just in case
            self.debconf_progress_set(30)

            self.debconf_progress_info('Creating partitions')                
            parted_cmds = [ ['mkpart', 'primary', 'fat32', '63s', disk_end] ]
            for i in parted_cmds:
                run_command(['/sbin/parted', '-s', device] + i, retval=runcommand.FAIL)
            self.debconf_progress_set(40)

            time.sleep(1)  # just in case
            self.debconf_progress_set(50)

            self.wait_for_partition_devices_to_appear(partitions)
            self.debconf_progress_set(60)

            # Sleep for a while to ensure that there is no "flicker" of device nodes.
            # For some reason this happens with at least native hardware and USB sticks.
            # See #435.
            time.sleep(5)

            self.debconf_progress_set(70)

            self.debconf_progress_info('Creating partitions and filesystems')
            run_command(['/sbin/mkfs.vfat', '-n', fat_part_name, part_fat], retval=runcommand.FAIL)

            self.debconf_progress_set(90)

        except:
            self.error('failed to create partitions, exiting.')
            raise

        self.debconf_progress_set(100)
        self.debconf_progress_stop()

    def setup_fat_partition(self, targetdir):
        """Autorun setup for Windows, OSX, and Linux."""

        # Extract ZIP file with files
        run_command([constants.CMD_UNZIP, constants.INSTALL_AUTORUN_ZIPFILE, '-d', targetdir], retval=runcommand.FAIL)
        
    def set_debconf_variable(self, variable, value):
        if value is None: value = ''
        run_command(['/usr/bin/debconf-communicate'], stdin='set %s %s\n' % (variable, value), retval=runcommand.FAIL)

    def copy_debconf(self):
        """Copy a few important questions into the installed system.
        """

        targetdb = '/target/var/cache/debconf/config.dat'
        for q in ['^debian-installer/keymap$']:
            run_command(['debconf-copydb', 'configdb', 'targetdb', '-p', q, '--config=Name:targetdb', '--config=Driver:File', '--config=Filename:%s' % targetdb], retval=runcommand.FAIL)

    def prepend_path(self, directory):
        if 'PATH' in os.environ and os.environ['PATH'] != '':
            os.environ['PATH'] = '%s:%s' % (directory, os.environ['PATH'])
        else:
            os.environ['PATH'] = directory

    def copy_recovery_data(self, recovery_data):
        if recovery_data is None:
            print 'no recovery data'
            return

        rec_fname = '/target/var/lib/l2tpgw/exported-rdf-database.xml'  # XXX: hardcoded
        print 'copying recovery data from %s to %s' % (recovery_data, rec_fname)

        # create target dir if necessary (on first time it is)
        target_dir = '/target/var/lib/l2tpgw/'
        if not os.path.exists(target_dir):
            print 'creating missing target directory %s' % target_dir
            run_command([constants.CMD_MKDIR, '-p', target_dir], retval=runcommand.FAIL)

        f1, f2 = None, None
        try:
            f1 = open(recovery_data, 'rb')
            f2 = open(rec_fname, 'wb')
            f2.write(f1.read())
        finally:
            if f1 is not None:
                f1.close()
                f1 = None
            if f2 is not None:
                f2.close()
                f2 = None

        print 'recovery data copied ok'
        
    def run_install(self, target, hostname, adminuser, adminpassword, recovery_data=None, large_install=False):
        """Perform normal product install."""
        try:
            # Set umask to be the same as normal ubuntu user umask (0022) that ubuquity install assumes
            # instead of default root umask (0066) that we are otherwise using.
            posix.umask(022)

            self.prepare()
            self.hostname = hostname
            self.large_install = large_install
            
            self.install_stage_set('Preparing target disk')
            self.debconf_progress_start(0, 100, '')
            self.debconf_progress_set(0)

            self.debconf_progress_region(0, 4)
            self.create_filesystems(target)
            self.setup_fat_partition('/target-fat')
            self.debconf_progress_set(4)

            # Copy recovery data for the first time, to ensure that the data is available
            # in case this recovery fails
            self.copy_recovery_data(recovery_data)
            
            self.install_stage_set('Copying files')

            # Note: resume partition setup is not a problem
            # because we do not use swap in live-cd => ubiquity
            # cannot find a swap partition to use for resume..

            # Set configuration values to the debconf database so that
            # Ubiquity can find them.

            # Grub boot device
            self.set_debconf_variable('grub-installer/bootdev', target)

            # Disable os-prober so that grub installer will not find other
            # devices to boot from. This is not configurable from debconf
            # and requires this hack (or menu.lst cleanup afterwards).
            os_prober = '/usr/bin/os-prober'
            os_prober_orig = '/usr/bin/os-prober.orig'

            # Note: first move command in unionfs system changes the directory permissions,
            # avoiding this by doing a copy/delete instead of move.
            run_command([constants.CMD_CP, '-f', os_prober, os_prober_orig], retval=runcommand.FAIL)
            run_command([constants.CMD_RM, '-f', os_prober], retval=runcommand.FAIL)

            helpers.write_file(os_prober, '#!/bin/sh\nexit 0\n', append=False, perms=0755)

            # Admin user and passwd
            self.set_debconf_variable('passwd/username', adminuser)
            self.set_debconf_variable('passwd/user-fullname', 'Administrator')
            self.set_debconf_variable('passwd/user-uid', '999')

            # Note: here we could use real password received from UI (currently cleartext)
            # eg.: self.set_debconf_variable('passwd/user-password', adminpassword)
            # For now the admin password is disabled.
            self.set_debconf_variable('passwd/user-password-crypted', '*')

            # Set root password disabled.
            self.set_debconf_variable('passwd/root-password-crypted', '*')

            # Disable unwanted parts of Ubiquity
            # 1. language_apply (first two)
            # 2. apt_setup
            # 3. timezone_apply (zone and clock)
            # 4. keyboard_chooser
            for i in ['/usr/lib/ubiquity/localechooser/post-base-installer',
                      '/usr/lib/ubiquity/localechooser/prebaseconfig',
                      '/usr/share/ubiquity/apt-setup',
                      '/usr/lib/ubiquity/tzsetup/prebaseconfig',
                      '/usr/share/ubiquity/clock-setup',
                      '/usr/lib/ubiquity/kbd-chooser/prebaseconfig']:
                helpers.write_file(i, textwrap.dedent("""\
                #!/bin/sh
                exit 0
                """))

            # Run Ubiquity to do the main part of installation
            self.debconf_progress_region(4, 97)
            if install.Install(self).run_command():
                raise Exception('Ubiquity installer failed')

            # Set back os-prober
            # Note: first move command in unionfs system changes the directory permissions,
            # avoiding this by doing a delete/copy/delete instead of move.
            run_command([constants.CMD_RM, '-f', os_prober], retval=runcommand.FAIL)
            run_command([constants.CMD_CP, '-f', os_prober_orig, os_prober], retval=runcommand.FAIL)
            run_command([constants.CMD_RM, '-f', os_prober_orig], retval=runcommand.FAIL)

            # Clear debconf database
            for i in ['grub-installer/bootdev',
                      'passwd/user-password',
                      'passwd/user-password-crypted',
                      'passwd/root-password-crypted',
                      'passwd/username',
                      'passwd/user-fullname',
                      'passwd/user-uid']:
                self.set_debconf_variable(i, None)

            # Ensure that the default user has sudo rights because
            # user-setup-apply fails when username is "admin".
            helpers.write_file('/target/etc/sudoers', textwrap.dedent("""\
            # Ensure that the default user has admin rights always.
            %s ALL=(ALL) NOPASSWD: ALL
            """ % adminuser), append=True, perms=None)

            # Add GRUB options to /boot/grub/menu.lst:
            #   * recover from kernel panic (panic=60)
            #   * force a 16-bit VESA mode for Virtual PC 2007 compatibility
            #     (affects only startup)
            
            f = open('/target/boot/grub/menu.lst')
            grub_menu = f.read()
            f.close()

            def_re = re.compile(r'^# defoptions=')
            alt_re = re.compile(r'^# altoptions=')

            updated_grub_menu = ''
            for l in grub_menu.split('\n'):
                if (def_re.match(l) is not None) or (alt_re.match(l) is not None):
                    updated_grub_menu += '%s panic=60 vga=785' % l
                else:
                    updated_grub_menu += l

                updated_grub_menu += '\n'

            f = open('/target/boot/grub/menu.lst', 'wb')
            f.write(updated_grub_menu)
            f.close()

            run_command(['/usr/sbin/chroot', '/target', '/sbin/update-grub'], retval=runcommand.FAIL)

            # Fix permissions of all ubiquity-created files on target system.
            # These permissions are broken because of root umask (0066) is used
            # when running installer instead of ubuntu-user umask (0022))
            #
            # Files affected include at least: /etc/hosts, /etc/iftab, /etc/kernel-img.conf, /boot/grub, /boot/grub/*
            #
            # The following files already have proper permissions (files do exist before write),
            # but setting anyways: /etc/hostname, /etc/network/interfaces
            #
            # Note: this is still in place as a safeguard even when the umask is now set
            # in script start.

            for f, p in [['etc/hosts', 0644],
                         ['etc/iftab', 0644],
                         ['etc/hostname', 0644],
                         ['etc/network/interfaces', 0644],
                         ['etc/kernel-img.conf', 0644]]:
                os.chmod(os.path.join('/target', f), p)

            for r, d, files in os.walk('/target/boot/grub'):
                os.chmod(r, 0755)
                for f in files:
                    os.chmod(os.path.join(r, f), 0644)

            # Note: Use this if the login stuff gets broken again and
            # debugging is required.
            # helpers.write_file('/target/etc/sudoers', textwrap.dedent("""\
            # debug ALL=(ALL) NOPASSWD: ALL
            # """), append=True, perms=None)
            # run_command(['/usr/sbin/chroot', '/target', 'adduser', '--disabled-password', '--gecos', 'Debug', '--uid', '1020', 'debug'])
            # run_command(['/usr/sbin/chroot', '/target', 'chpasswd'], stdin='debug:debug\n')

            self.install_stage_set('Finishing installation')

            if not os.path.exists(constants.LOWMEM_MARKER_FILE):
                # XXX: database stuff: (when testusage is implemented)
                # - stop database
                # - stop cron scripts from accessing database
                # - copy database to installed system
                # - copy marker files to installed system?
                #   - configured marker, other marker files
                #   - whole /var/lib/l2tpgw/ ?
                # - copy uuid file to installed system?
                # - copy logfiles to installed system
                # - remove/nocopy: fastboot marker
                pass

            self.debconf_progress_region(97, 99)

            # Recreate ssh keys
            for f, t in [['/etc/ssh/ssh_host_rsa_key', 'rsa'], ['/etc/ssh/ssh_host_dsa_key', 'dsa']]:
                run_command(['/usr/sbin/chroot', '/target', '/bin/rm', '-f', f], retval=runcommand.FAIL)
                run_command(['/usr/sbin/chroot', '/target', '/usr/bin/ssh-keygen', '-q', '-N', '', '-f',f, '-t', t, '-C', 'root@%s' % self.hostname], retval=runcommand.FAIL)

            # Copy recovery data (again)
            self.copy_recovery_data(recovery_data)

            self.copy_debconf()
            self.cleanup()
            self.debconf_progress_set(100)

            self.write_status('success\nInstall completed')
            self.info('installation success')
        except:
            self.cleanup()
            self.write_status('failure\nInstall failed')
            self.error('installation failed')
            raise

    def run_fatformat(self, target):
        """Partition and format a device (presumably USB stick) into a single-partition FAT format."""
        try:
            # Set umask to be the same as normal ubuntu user umask (0022) that ubuquity install assumes
            # instead of default root umask (0066) that we are otherwise using.
            posix.umask(022)

            self.prepare()  # does stuff we don't need, but it doesn't hurt

            self.install_stage_set('Partitioning and formatting device')
            self.debconf_progress_start(0, 100, 'Partitioning and formatting device')
            self.debconf_progress_set(0)
            self.create_and_format_fatdevice(target)
            self.debconf_progress_set(100)
            self.write_status('success\nFormat completed')
            self.info('formatting success')
        except:
            self.cleanup()
            self.write_status('failure\nFormatting failed')
            self.error('formatting failed')
            raise
    
    def run(self, args):
        # check and get args
        if len(args) < 6:
            raise Exception('too few arguments')
        command = args[1]
        target = args[2]
        hostname = args[3]
        adminuser = args[4]
        adminpassword = args[5]
        large_install = (args[6] == '1')

        recovery_data = None
        if len(args) >= 8:
            recovery_data = args[7]
                
        if not os.path.exists(constants.LIVECD_MARKER_FILE):
            # Nothing to do if not run from live-cd
            self.error('not on livecd, not installing')
            raise Exception('live-cd not detected')

        if command == 'install':
            return self.run_install(target, hostname, adminuser, adminpassword, recovery_data, large_install)
        elif command == 'fatformat':
            return self.run_fatformat(target)
        else:
            raise Exception('unknown command: %s' % command)

if __name__ == '__main__':
    Install().run(sys.argv)
