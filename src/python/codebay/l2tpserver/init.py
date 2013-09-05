"""
Startup actions.
"""

# Constants for memory and hard-disk limits
# Allow 32M memory to be stolen and assume that system reported memory size
# may be about 6M lower than actual physical memory size.

# Crontab file
crontab_file = '/etc/crontab'

# List of old kernels - these are removed in preinit if they seem to be present.
# Only put *known*, actually deployed VPNease kernel image package names here.
old_kernel_packages = [ 'linux-image-2.6.15-27-386' ]

import os, re, textwrap, tempfile, datetime

# Essential imports
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from twisted.python.util import mergeFunctionMetadata

_log = logger.get('l2tpgw-init')
run_command = runcommand.run_command

def db_autoclose():
    """Decorator which closes the codebay.l2tpserver.db instance before and after a call.

    This ensures that functions which manipulate the shared database close it properly
    so that if direct changes to files on disk are done, they appear to other code correctly
    """
    def _close_db():
        try:
            from codebay.l2tpserver import db
            db.get_db().close()
        except:
            _log.exception('failed to close l2tpserver db')

    def _f(f):
        def g(*args, **kw):
            _close_db()
            try:
                ret = f(*args, **kw)
            finally:
                _close_db()
            return ret
        mergeFunctionMetadata(f, g)
        return g
    return _f
    
def _is_livecd():
    [rv, out, err] = run_command('/bin/cat /proc/mounts | grep unionfs 1>/dev/null 2>/dev/null', shell=True)
    if rv == 0:
        return True
    return False

def _check_livecd(_log):
    is_livecd = _is_livecd()
    if is_livecd:
        helpers.write_datetime_marker_file(constants.LIVECD_MARKER_FILE)
    else:
        run_command(['/bin/rm', '-f', constants.LIVECD_MARKER_FILE], retval=runcommand.FAIL)

    return is_livecd

def _memsize():
    f = os.popen('/bin/cat /proc/meminfo')
    buf = f.read()
    f.close()

    re_mem = re.compile('MemTotal:\s+(\d+)\s+kB')
    return int(re_mem.match(buf).groups()[0])

def _is_livecd_lowmem():
    if _memsize() < constants.MEM_LOWSIZE and _is_livecd():
        return True
    return False

def _check_memory(_log):
    """Check that memory size is over minimum if we are booting
    from live-cd.

    Note: the minimum size of 256M to even boot Ubuntu is already
    checked by initramfs scripts when the system boots to live-cd
    mode but not when the installed system is booted.
    """

    run_command(['/bin/rm', '-f', constants.LOWMEM_MARKER_FILE], retval=runcommand.FAIL)

    if _memsize() < constants.MEM_MINSIZE:
        raise Exception('System memory size is too small (%sMb < %sMb).' % (str(_memsize()/1024), str(constants.MEM_MINSIZE/1024)))

    if _is_livecd_lowmem():
        helpers.write_datetime_marker_file(constants.LOWMEM_MARKER_FILE)

def _record_boot_timestamp(_log):
    """Record boot timestamp to a file."""

    timestamp = helpers.write_datetime_marker_file(constants.BOOT_TIMESTAMP_FILE)
    if timestamp is None:
        raise Exception('boot timestamp write failed')

def _create_installation_uuid(_log, firstboot=False):
    if not firstboot:
        if os.path.exists(constants.INSTALLATION_UUID):
            return
        _log.warning('installation uuid not found, recreating.')

    helpers.write_random_uuid_file(constants.INSTALLATION_UUID)

def _create_boot_uuid(boot_uuid):
    helpers.write_random_uuid_file(constants.BOOT_UUID)

def _recreate_desktop_and_autostart():
    from codebay.l2tpserver import gnomeconfig

    is_livecd = _is_livecd()
    desktop_file = '/home/%s/Desktop/%s.desktop' % (constants.ADMIN_USER_NAME, constants.PRODUCT_DEBIAN_NAME)
    autostart_file = '/home/%s/.config/autostart/%s-autostart.desktop' % (constants.ADMIN_USER_NAME, constants.PRODUCT_DEBIAN_NAME)
    [rv, out, err] = run_command(['/bin/mkdir', '-p', '/home/%s/Desktop' % constants.ADMIN_USER_NAME])
    [rv, out, err] = run_command(['/bin/mkdir', '-p', '/home/%s/.config/autostart' % constants.ADMIN_USER_NAME])
    gnomeconfig.write_desktop_entry(is_livecd, desktop_file)
    gnomeconfig.write_autostart_entry(is_livecd, autostart_file)  # firefox autostart
    [rv, out, err] = run_command(['/bin/chown', '-R', 'admin.admin', '/home/%s/Desktop' % constants.ADMIN_USER_NAME, '/home/%s/.config' % constants.ADMIN_USER_NAME])
    [rv, out, err] = run_command(['/bin/chmod', '0755', desktop_file, autostart_file])

# --------------------------------------------------------------------------

def _firstboot_config(_log):
    if not os.path.exists(constants.CONFIGURED_MARKER):

        from codebay.l2tpserver import gnomeconfig
        is_livecd = _is_livecd()

        # Gnome config is fragile: only done in first boot after install
        # XXX: if update needs to change gnome config, this must be refactored/rewritten in the future
        gnomeconfig.gnomeconfig_firstboot(is_livecd)

        _create_installation_uuid(_log, firstboot=True)

        # No RRD when lowmem.
        if not _is_livecd_lowmem():
            from codebay.l2tpserver import graphs

            g = graphs.Graphs()
            g.create_rrd_files()

        helpers.write_datetime_marker_file(constants.CONFIGURED_MARKER)

    try:
        from codebay.l2tpserver import gdmconfig
        # Overwrite gdm config in every boot to ensure that it is done after update
        gdmconfig.run(autologin=True, autologin_user=constants.ADMIN_USER_NAME)
    except:
        _log.exception('failed to (re)configure gdm, ignoring.')

    try:
        from codebay.l2tpserver import firefoxconfig
        # Overwrite firefox config in every boot to ensure it is done after update
        firefoxconfig.set_firefox_configuration('/home/%s' % constants.ADMIN_USER_NAME)
    except:
        _log.exception('failed to (re)configure firefox, ignoring.')

    # Note: doublecheck on every boot.
    _create_installation_uuid(_log, firstboot=False)

    # (Re)create desktop icon which also enables autostart
    #
    # Two .desktop files are required:
    #   - ~/Desktop/vpnease.desktop is shown on the user desktop,
    #     but has no autostart
    #  - ~/.config/autostart/vpnease-autostart.desktop causes
    #     autostart but is not shown on the desktop
    _recreate_desktop_and_autostart()

def _check_openswan_config(_log):
    """Check that openswan configuration is pruned.

    This ensures that pluto will never use certificates.
    """

    [rv, out, err] = run_command(['/bin/rm', '-f', '/etc/ipsec.secrets'])
    for d in ['certs', 'private']:
        for f in os.listdir(os.path.join('/etc/ipsec.d', d)):
            [rv, out, err] = run_command(['/bin/rm', '-rf', f])

def _check_ssh_keys(_log):
    """Check ssh host keys and recreate missing ones."""

    _log.info('Checking ssh host keys..')

    for f, t in [['/etc/ssh/ssh_host_rsa_key', 'rsa'], ['/etc/ssh/ssh_host_dsa_key', 'dsa']]:
        if not os.path.exists(f):
            run_command(['/usr/bin/ssh-keygen', '-q', '-N', '', '-f',f, '-t', t], retval=runcommand.FAIL)
            _log.warning('recreated missing ssh key: %s' % f)

# Note: currently this is done for livecd also, which is ok
def _check_system_config(_log):
    """Double check system configuration files."""

    _check_ssh_keys(_log)
    _check_openswan_config(_log)

# --------------------------------------------------------------------------

@db_autoclose()
def _check_update_rdfxml_export(_log):
    """Check whether an update related RDF/XML file exists.

    If this file exists, it means that the product was updated and an RDF/XML
    data file was created BEFORE update.  The intent here is that we can, if
    we wish, recreate the database (including the sqlite schema etc) from
    scratch.  This allows us to switch database backends in the future, etc.

    However, currently we ignore the RDF/XML file; it is generated for future
    use by the update code now, though.
    """
    
    if os.path.exists(constants.UPDATE_PROCESS_RDFXML_EXPORT_FILE):
        _log.info('found update rdf/xml export file, but ignoring it in this version')
        os.unlink(constants.UPDATE_PROCESS_RDFXML_EXPORT_FILE)
    else:
        _log.info('no update rdf/xml export file found')

@db_autoclose()
def _check_configuration_import(_log):
    from codebay.l2tpserver import db
    from codebay.common import rdf
    from codebay.l2tpserver.rdfconfig import ns, ns_ui

    import_file = constants.CONFIGURATION_IMPORT_BOOT_FILE

    if os.path.exists(import_file):
        _log.info('configuration import file exists (%s), attempting import' % import_file)

        def _nukeold():
            # Nuke old database
            _log.info('configuration import: creating a fresh database')
            db.get_db().close()
            db.get_db().create()

        @db.transact()
        def _doimport():
            # Read the import.  Prune at the end, just in case.
            _log.info('configuration import: getting model')
            model = db.get_db().getModel()
            _log.info('configuration import: loading import file %s' % import_file)
            model.loadFile(import_file)
            _log.info('configuration import: in-place prune')
            root = model.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
            model.prune(root)
            _log.info('configuration import: prune ok')
            
            # fix configuration version differences
            #
            # Missing values do not have to be fixed here if defaults are ok;
            # caller will use fix_missing_database_values() to set defaults
            # for all missing values.  Caller will also regenerate protocol
            # configuration so that doesn't have to be done here either.

            # reset installation UUID to current system
            _log.info('configuration import: setting installation uuid')
            f = open(constants.INSTALLATION_UUID, 'rb')
            uuid = f.read().strip()
            f.close()
            root.setS(ns.installationUuid, rdf.String, uuid)

        @db.transact()
        def _postops():
            model = db.get_db().getModel()
            root = model.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))

            # attempt to set keymap
            try:
                from codebay.l2tpserver import gnomeconfig
                cfg_ui = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
                gnomeconfig.set_keymap_settings(cfg_ui.getS(ns_ui.keymap, rdf.String))
            except:
                _log.exception('setting keymap failed in import, ignoring')
                
            # XXX: root password is not in configuration, so we cannot import it.
            # This is probably best, so we cannot do anything about it here.
            
        try:
            _nukeold()
            _doimport()
            _postops()

            # done
            _log.info('configuration import: all done')
        except:
            # XXX: show import failure somehow to user after boot
            _log.exception('configuration import failed')

        try:
            # close db just in case
            db.get_db().close()
        except:
            _log.exception('db close failed, ignoring')

        # unlink even if failed, file is probably corrupt
        _log.info('deleting import file %s' % import_file)
        os.unlink(import_file)
        _log.info('deleting of import file successful')
    else:
        _log.debug('no import file')
    
@db_autoclose()
def _rdf_database_sanity_check(_log):
    """Sanity check current global configuration root.

    The sanity check should ensure that nothing breaks fatally at
    run time.  Although this check is probably always incomplete,
    it still needs to catch errors such as missing "structural"
    nodes which cause major problems run time.

    This function may throw exceptions at will - an exception is
    interpreted as an insane config file.  Thus a "getS" with an
    rdf:type is sufficient to ensure that some property exists.
    """

    database_filename = constants.PRODUCT_DATABASE_FILENAME
    
    if not os.path.exists(database_filename):
        _log.info('product sqlite database %s does not exist, skipping sanity check (assuming insane)' % database_filename)
        return False

    dbase = None
    res = False
    try:
        try:
            from codebay.common import rdf
            from codebay.l2tpserver.rdfconfig import ns, ns_ui
            from codebay.l2tpserver import db
        
            dbase = rdf.Database.open(constants.PRODUCT_DATABASE_FILENAME)

            @db.transact(database=dbase)
            def _func():
                root = dbase.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
        
                # L2TP device config root(s)
                l2tp_cfg = root.getS(ns.l2tpDeviceConfig, rdf.Type(ns.L2tpDeviceConfig))

                # Top-level config roots
                cfg_net = l2tp_cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
                cfg_mgmt = l2tp_cfg.getS(ns.managementConfig, rdf.Type(ns.ManagementConfig))
                cfg_ipsec = l2tp_cfg.getS(ns.ipsecConfig, rdf.Type(ns.IpsecConfig))
                cfg_l2tp = l2tp_cfg.getS(ns.l2tpConfig, rdf.Type(ns.L2tpConfig))
                cfg_ppp = l2tp_cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))
                cfg_users = l2tp_cfg.getS(ns.usersConfig, rdf.Type(ns.UsersConfig))
                cfg_radius = l2tp_cfg.getS(ns.radiusConfig, rdf.Type(ns.RadiusConfig))
                cfg_snmp = l2tp_cfg.getS(ns.snmpConfig, rdf.Type(ns.SnmpConfig))
                
                # Protocol status root
                l2tp_status = root.getS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))

                # Global status root
                global_status = root.getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))
                retiredpppdevs = global_status.getS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))

                # License parameters
                license_info = root.getS(ns_ui.licenseInfo, rdf.Type(ns_ui.LicenseInfo))

                # UI data
                # XXX: this list is not comprehensive and it is currently not critical
                # to check all the UI config here.
                update_root = root.getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))
                ui_root = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
                ic_root = ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
                dns_root = ui_root.getS(ns_ui.dnsServers)
                def_gw_node = ui_root.getS(ns_ui.defaultRoute)
                firewall_node = ui_root.getS(ns_ui.firewallInUse, rdf.Boolean)

            _func()

            dbase.close()
            dbase = None

            res = True
        except:
            _log.exception('_rdf_database_sanity_check failed')
    finally:
        try:
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_sanity_check, failed to close db')
        
    return res

@db_autoclose()
def _rdf_database_create_initial(_log):
    """Create empty config root.

    This function is called when our current configuration is
    missing or broken.  The initialized configuration has the
    proper structure (contains the mandatory nodes which pass
    sanity check) but is otherwise empty.

    XXX: We should probably add some warning or cause as to
    why the configuration is empty.
    """
        
    dbase = None
    try:
        try:
            from codebay.common import rdf
            from codebay.l2tpserver.rdfconfig import ns, ns_ui
            from codebay.l2tpserver.webui import uidatahelpers
            from codebay.l2tpserver import db
        
            # close database if open; just sanity
            try:
                db.get_db().close()
            except:
                _log.exception('failed to close database before recreating, ignoring')

            # remove old database
            rdf.Database.delete(constants.PRODUCT_DATABASE_FILENAME)

            # create new one
            dbase = rdf.Database.create(constants.PRODUCT_DATABASE_FILENAME)
            dbase.close()
            dbase = None
            
            @db.transact()
            def _func():
                now = datetime.datetime.utcnow()

                # Global root
                model = db.get_db().getModel()
                root = rdf.Node.make(model, rdf.Type(ns.L2tpGlobalRoot), ns.l2tpGlobalRoot)

                # Global status root
                global_status = root.setS(ns.globalStatus, rdf.Type(ns.GlobalStatus))
                global_status.setS(ns.watchdogReboots, rdf.Integer, 0)
                global_status.setS(ns.periodicReboots, rdf.Integer, 0)
                global_status.setS(ns.uncleanRunnerExits, rdf.Integer, 0)
                retiredpppdevs = global_status.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))

                # Update info
                update_info = root.setS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))
                update_info.setS(ns_ui.changeLog, rdf.String, '')
                update_info.setS(ns_ui.latestKnownVersion, rdf.String, '')
        
                # License parameters
                license_info = root.setS(ns_ui.licenseInfo, rdf.Type(ns_ui.LicenseInfo))
                license_info.setS(ns_ui.maxNormalConnections, rdf.Integer, 0)
                license_info.setS(ns_ui.maxSiteToSiteConnections, rdf.Integer, 0)
                license_info.setS(ns_ui.validityStart, rdf.Datetime, now)
                license_info.setS(ns_ui.validityEnd, rdf.Datetime, now)
                license_info.setS(ns_ui.validityRecheckLatest, rdf.Datetime, now)
                license_info.setS(ns_ui.licenseString, rdf.String, '')
                license_info.setS(ns_ui.isDemoLicense, rdf.Boolean, False)
                license_info.setS(ns_ui.demoValidityStart, rdf.Datetime, now)
                license_info.setS(ns_ui.demoValidityEnd, rdf.Datetime, now)
                
                # XXX: what other roots should we add here?

                f = open(constants.INSTALLATION_UUID, 'rb')
                uuid = f.read().strip()
                f.close()
                root.setS(ns.installationUuid, rdf.String, uuid)

            _func()

            # UI default database (also creates initial protocol config)
            # (separate transaction)
            @db.transact()
            def _func():
                uidatahelpers.create_default_database()
            _func()
        except:
            _log.exception('_rdf_database_create_initial failed, fatal')
    finally:
        try:
            # this is just for sanity
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_create_initial, failed to close db')

    return None

@db_autoclose()
def _rdf_database_update_boot_uuid(_log):
    database_filename = constants.PRODUCT_DATABASE_FILENAME
    
    if not os.path.exists(database_filename):
        _log.info('product sqlite database %s does not exist, skipping boot uuid update' % database_filename)
        return

    try:
        from codebay.common import rdf
        from codebay.l2tpserver.rdfconfig import ns, ns_ui
        from codebay.l2tpserver import db

        @db.transact()  # uses l2tp database by default through l2tpserver.db
        def _func():
            root = db.get_db().getRoot()
            now = datetime.datetime.utcnow()

            f = open(constants.BOOT_UUID, 'rb')
            uuid = f.read().strip()
            f.close()
            root.setS(ns.bootUuid, rdf.String, uuid)

        _func()

    except:
        _log.exception('_rdf_database_update_boot_uuid failed, ignoring')

@db_autoclose()
def _rdf_database_recover_from_known_good(_log):
    database_filename = constants.PRODUCT_DATABASE_FILENAME
    exported_filename = constants.EXPORTED_RDF_DATABASE_FILE
    res = False
    
    if not os.path.exists(exported_filename):
        _log.info('exported known good file %s does not exist, skipping recover from known good' % exported_filename)
        return False

    try:
        try:
            from codebay.common import rdf
            from codebay.l2tpserver import db
    
            # remove old database
            rdf.Database.delete(database_filename)

            # re-create database, read back from pruned file
            dbase = rdf.Database.create(database_filename)
            @db.transact(database=dbase)
            def _f():
                dbase.loadFile(exported_filename)
            _f()
            dbase.close()
            dbase = None

            # post ops - reset keymap (might have changed, e.g. in recovery)
            try:
                from codebay.l2tpserver.rdfconfig import ns, ns_ui
                from codebay.l2tpserver import gnomeconfig

                model = db.get_db().getModel()
                root = model.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
                cfg_ui = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
                gnomeconfig.set_keymap_settings(cfg_ui.getS(ns_ui.keymap, rdf.String))
            except:
                _log.exception('setting keymap failed in recovery from known good, ignoring')

            res = True
        except:
            _log.exception('_rdf_database_recover_from_known_good: recovery from known good failed')
    finally:
        try:
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_recover_from_known_good: failed to close hanging db')
        
    return res

@db_autoclose()
def _rdf_database_prune_retired_devices(_log, root):
    from codebay.common import rdf
    from codebay.l2tpserver.rdfconfig import ns, ns_ui
    from codebay.l2tpserver import db

    now = datetime.datetime.utcnow()
    retired_age_limit = datetime.timedelta(30, 0, 0)  # XXX: 30 days
    retired_max_devices = 1000                        # XXX: max 1000 devices after prune
    global_status = root.getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))

    try:
        # pass 1: old devices
        to_nuke = []
        devs = global_status.getS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices)).getSet(ns.pppDevice, rdf.Type(ns.PppDevice))
        for d in devs:
            if d.hasS(ns.stopTime):
                age = now - d.getS(ns.stopTime, rdf.Datetime)
                if age > retired_age_limit:
                    to_nuke.append(d)
            else:
                _log.warning('retired device %s does not have stopTime' % d)
        for d in to_nuke:
            devs.discard(d)
        _log.info('pruning retired ppp devices, pass 1: old devices (pruned %d devices)' % len(to_nuke))

        # pass 2: limit max count
        count_to_nuke = 0
        devs = global_status.getS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices)).getSet(ns.pppDevice, rdf.Type(ns.PppDevice))

        devlist = []
        for d in devs:
            devlist.append(d)
        def _cmp_stoptime(a, b):  # note order: oldest first
            return cmp([a.getS(ns.stopTime, rdf.Datetime)],
                       [b.getS(ns.stopTime, rdf.Datetime)])
        devlist.sort(cmp=_cmp_stoptime)

        count_to_nuke = len(devlist) - retired_max_devices
        if count_to_nuke > 0:
            for i in xrange(count_to_nuke):
                devs.discard(devlist[i])
        else:
            count_to_nuke = 0
        _log.info('pruning retired ppp devices, pass 2: max devices (pruned %d devices)' % count_to_nuke)
    except:
        _log.info('nuking retired devices failed, recreating retired devices list to empty')
        global_status.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))
    
@db_autoclose()
def _rdf_database_remove_unused_data(_log):
    dbase = None

    database_filename = constants.PRODUCT_DATABASE_FILENAME
    
    if not os.path.exists(database_filename):
        _log.info('product sqlite database %s does not exist, skipping remove unused data' % database_filename)
        return

    try:
        try:
            from codebay.common import rdf
            from codebay.l2tpserver.rdfconfig import ns, ns_ui
            from codebay.l2tpserver import db

            dbase = rdf.Database.open(constants.PRODUCT_DATABASE_FILENAME)

            @db.transact(database=dbase)
            def _func():
                root = dbase.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
        
                # nuke old config and status
                l2tp_config = root.setS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))
                l2tp_status = root.setS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))

                # nuke old retired devices
                _rdf_database_prune_retired_devices(_log, root)

                # misleading management connection state
                if root.hasS(ns.globalStatus):
                    global_st = root.getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))
                    global_st.setS(ns.managementServerConnection, rdf.Boolean, False)
                    # XXX - do we want to reset this? rely on previous info instead?
                    global_st.setS(ns.behindNat, rdf.Boolean, False)

            _func()

            dbase.close()
            dbase = None
        except:
            _log.exception('_rdf_database_remove_unused_data: failed')
    finally:
        try:
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_remove_unused_data: failed to close hanging db')

@db_autoclose()
def _rdf_database_prune(_log):
    """Prune product sqlite database."""
    from codebay.common import rdf
    from codebay.l2tpserver.rdfconfig import ns, ns_ui
    from codebay.l2tpserver import db

    database_filename = constants.PRODUCT_DATABASE_FILENAME
    
    if not os.path.exists(database_filename):
        _log.info('product sqlite database %s does not exist, skipping prune' % database_filename)
        return

    t = tempfile.mktemp(suffix='-rdf-database-prune')

    _size_before = None
    _size_after = None

    try:
        _size_before = os.stat(database_filename).st_size
    except:
        _log.exception('cannot check size before prune')

    # prune (in place) and write to file
    dbase = None
    try:
        try:
            dbase = rdf.Database.open(database_filename)

            @db.transact(database=dbase)
            def _func():
                root = dbase.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
                dbase.prune(root)
                dbase.toFile(t, name='rdfxml')

            _func()

            dbase.close()
            dbase = None
        except:
            _log.exception('_rdf_database_prune: in-place prune failed')
            raise
    finally:
        try:
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_prune: closing hanging database failed')    

    # remove old database
    rdf.Database.delete(database_filename)

    # XXX: This spot is basically broken: if something goes wrong at this point,
    # we've lost the database.  Needs some phased replacement approach.

    # re-create database, read back from pruned file
    dbase = None
    try:
        try:
            dbase = rdf.Database.create(database_filename)

            @db.transact(database=dbase)
            def _func():
                dbase.loadFile(t)
                
            _func()

            dbase.close()
            dbase = None
        except:
            _log.exception('_rdf_database_prune: creation and loading of new database failed')
            raise
    finally:
        try:
            if dbase is not None:
                dbase.close()
                dbase = None
        except:
            _log.exception('_rdf_database_prune: closing hanging database failed')
    
    os.unlink(t)

    try:
        _size_after = os.stat(database_filename).st_size
    except:
        _log.exception('cannot check size after prune')

    _log.info('database size before prune %s, after prune %s' % (_size_before, _size_after))

@db_autoclose()
def _rdf_database_checks(_log, post_import_failures):
    # prune once
    try:
        _rdf_database_prune(_log)
    except:
        _log.exception('_rdf_database_prune failed')

    # check sanity
    sane = False
    try:
        if post_import_failures:
            pass  # assume insane
        else:
            if _rdf_database_sanity_check(_log):
                sane = True
    except:
        _log.exception('_rdf_database_sanity_check failed, assuming insane')

    # attempt to recover from best known good if insane
    recovered = False
    try:
        if not sane:
            _log.warning('database insane, attempting to recover from known good')
            if _rdf_database_recover_from_known_good(_log):
                _log.info('recovery successful')
                recovered = True
            else:
                _log.warning('recovery failed')
    except:
        _log.exception('failed to recover rdf database from known good')

    # XXX: if we successfully recover from known good, we should really
    # run sanity check here again...?

    # recreate from scratch if cannot recover
    try:
        if not sane and not recovered:
            _log.warning('recovery from known good failed, recreating database from scratch')
            _rdf_database_create_initial(_log)
    except:
        _log.exception('failed to recover rdf database by recreating from scratch')

    # remove useless data (e.g. old device info, status tree)
    try:
        _rdf_database_remove_unused_data(_log)
    except:
        _log.exception('_rdf_database_remove_unused_data failed, ignoring')

    # update boot uuid
    try:
        _rdf_database_update_boot_uuid(_log)
    except:
        _log.exception('_rdf_database_update_boot_uuid failed, ignoring')

    # final sanity - check for missing values
    try:
        from codebay.l2tpserver.webui import uidatahelpers
        rv = uidatahelpers.fix_missing_database_values()
        if rv > 0:
            _log.info('final sanity check: uncovered missing webui values')
    except:
        _log.exception('final sanity check of missing values failed')

    # regenerate protocol config
    try:
        from codebay.l2tpserver.webui import uidatahelpers

        pd = uidatahelpers.CreateProtocolData()
        pd.save_protocol_data(use_current_config=True)
        pd.activate_protocol_data(use_current_config=True)
    except:
        _log.exception('create_protocol_data failed')

    # prune for final time
    try:
        _rdf_database_prune(_log)
    except:
        _log.exception('_rdf_database_prune failed')

# --------------------------------------------------------------------------

def _fsck_markers_check(_log):
    [rv, out, err] = run_command(['rm', '-f', constants.FORCE_FSCK_MARKER_FILE])
    helpers.write_datetime_marker_file(constants.FASTBOOT_MARKER_FILE)

def _check_interfaces(_log):
    from codebay.l2tpserver import interfacehelper

    _re_iftab_line = re.compile(r'^([^ #]+)\s+\w{3}\s+(\w{2}:\w{2}:\w{2}:\w{2}:\w{2}:\w{2})')

    infos = interfacehelper.get_all_interfaces()
    current_ifaces = {}
    for i in infos.get_interface_list():
        _log.info('system interface: %s' % i.toString())
        if not i.is_ethernet_device():
            continue
        current_ifaces[i.get_device_name()] = i.get_mac()

    iftab_ifaces = {}
    try:
        iftab = open('/etc/iftab', 'r')
        for l in iftab.read().split('\n'):
            m = _re_iftab_line.match(l)
            if m is None or len(m.groups()) < 2:
                continue
            dev = m.groups()[0]
            mac = m.groups()[1]
            info = interfacehelper.InterfaceInfo(dev, 0, 0, 0, 0, 0, mac, 'ether')
            if info.is_ethernet_device():
                iftab_ifaces[dev] = mac
                _log.info('iftab line: %s, %s' % (dev, mac))

        iftab.close()
    except:
        # Note: file may be missing, do not panic
        _log.exception('Failed to read /etc/iftab, creating from scratch.')
        pass

    for i in set(current_ifaces.keys()) - set(iftab_ifaces.keys()):
        # Note: GUI detects new interfaces by itself, no action
        pass

    for i in set(iftab_ifaces.keys()) - set(current_ifaces.keys()):
        # Note: missing interfaces are ok.. and cannot tell if the
        # interface vanished *just* now because mac locks are not removed.
        pass

    # Note: this removes old interface bindings if any..
    # Note: we do not care of invalid iftab bindinds, they are udev problems
    new_ifaces = iftab_ifaces
    new_ifaces.update(current_ifaces)

    if_lines = ''
    keys = new_ifaces.keys()
    keys.sort()
    for i in keys:
        # XXX: could also try to resolve the arp type and write if to
        # config, but propably not worth the effort?
        if_lines += '%s mac %s\n' % (i, new_ifaces[i])

    helpers.write_file('/etc/iftab', textwrap.dedent("""\
    # This file assigns persistent names to network interfaces.
    # See iftab(5) for syntax.
    
    # This file is autogenerated on system boot, do not edit.
    %s""") % if_lines)

def _cron_tweaks(_log):
    """Tweak crontab to run product related tasks.

    We do not use the cron directories (e.g. /etc/cron.daily) because there
    is no directory for "cron.minutely".  This is not a clean way to do this,
    but because it is done on each boot independently, it is quite robust
    with respect to product updates (which have already been performed prior
    to this tweak check.
    """

    _log.info('updating crontab')
    
    # parse crontab into an array of lines
    f = open(crontab_file, 'rb')
    t1 = f.readlines()
    f.close()

    # remove previous entry (if exists)
    re1 = re.compile(r'^.*?##l2tpgw##.*?$')
    t2 = []
    for l in t1:
        m = re1.match(l)
        if m is None:
            t2.append(l)

    # add new entries
    # XXX: logfile location
    t2.append('* * * * * root /usr/lib/l2tpgw/l2tpgw-cron minutely &>/tmp/l2tpgw-cron-minutely.out  ##l2tpgw##\n')
    t2.append('*/5 * * * * root /usr/lib/l2tpgw/l2tpgw-cron everyfiveminutes &>/tmp/l2tpgw-cron-everyfiveminutes.out ##l2tpgw##\n')
    t2.append('37 * * * * root /usr/lib/l2tpgw/l2tpgw-cron hourly &>/tmp/l2tpgw-cron-hourly.out ##l2tpgw##\n')

    # write back
    f = open(crontab_file, 'wb')
    f.write(''.join(t2))
    f.close()

def _initial_l2tpgw_cron_run(_log):
    """Run crontab script first time during boot.

    The intent here is to get the RDF and graph status up-to-date from
    boot.  This is especially relevant for the Live CD.  Note that cron
    is not running at this point, so there is no race here.  The RDF
    database must be accessible, as the RDF database is updated as a
    side effect.
    """

    _log.info('running l2tp prerun cron script for first time on this boot')

    run_command([constants.CMD_L2TPGW_CRON, 'prerun'])

def _check_and_generate_gui_certificate(_log):
    """Check validity of GUI certificate and if necessary, (re)generate it."""
    _log.info('checking validity of web UI certificate and regenerating if necessary')

    if helpers.check_self_signed_certificate(constants.WEBUI_PRIVATE_KEY, constants.WEBUI_CERTIFICATE):
        _log.debug('certificate is ok')
    else:
        try:
            helpers.generate_self_signed_certificate(constants.WEBUI_PRIVATE_KEY, constants.WEBUI_CERTIFICATE)
            _log.info('generated a new certificate for the web UI')
        except:
            _log.exception('failed to generate a new certificate for the web UI')
            raise

def _update_ssl_files(_log):
    """Update GUI SSL certificate files on disk (or remove them if not needed)."""

    from codebay.l2tpserver import db

    @db.transact()
    def _f():
        from codebay.l2tpserver.webui import uihelpers
        uihelpers.update_ssl_certificate_files()

    _f()

# XXX: direct to webui?
def _update_etc_issue(_log, is_livecd):
    from codebay.l2tpserver import versioninfo

    [version_string, cached] = versioninfo.get_version_info()

    if is_livecd:
        name = 'VPNease'
    else:
        name = 'VPNease'

    issue = textwrap.dedent("""\
    VPNease (version %s)

    """ % version_string)

    helpers.write_file('/etc/issue', issue, append=False, perms=0644)
    helpers.write_file('/etc/issue.net', issue, append=False, perms=0644)


def _check_daemon_startup(_log):
    """Ensure that undesired system daemon startups are disabled.

    Also remove some cron scripts which are not required and move
    startup time of gdm and ssh to later.  Note that in update case
    some of the daemon scripts are already diverted but it does not
    affect the update-rc.d approach here.
    """

    def _cleanup_divert(path):
        # Cleanup possible old diversions
        run_command([constants.CMD_RM, '-f', '%s.real.dpkg-new' % path])
        if os.path.exists('%s.real' % path):
            run_command([constants.CMD_RM, '-f', path])
            run_command(['/usr/sbin/dpkg-divert', '--remove', path])

    for d in ['portmap', 'monit', 'ipsec', 'setkey', 'ez-ipupdate', 'mysql-ndb-mgm', 'mysql', 'mysql-ndb', 'sysklogd', 'snmpd', 'freeradius', 'dhcp3-server']:
        # NB: ignore errors
        run_command(['/usr/sbin/update-rc.d', '-f', d, 'remove'])
        _cleanup_divert(os.path.join('/etc/init.d', d))

    for f in ['find', 'man-db']:
        _cleanup_divert(os.path.join('/etc/cron.daily', f))
        run_command([constants.CMD_RM, '-f', os.path.join('/etc/cron.daily', f)])

    for f in ['man-db', 'scrollkeeper-rebuilddb']:
        _cleanup_divert(os.path.join('/etc/cron.weekly', f))
        run_command([constants.CMD_RM, '-f', os.path.join('/etc/cron.weekly', f)])

    run_command(['/usr/sbin/update-rc.d', '-f', 'gdm', 'remove'])
    run_command(['/usr/sbin/update-rc.d', 'gdm', 'stop', '01', '0', '1', '6', '.',
                 'start', '26', '2', '3', '4', '5', '.'])

    # Note: this is not strictly required, because ssh host keys may
    # be safely modified while ssh is running.
    run_command(['/usr/sbin/update-rc.d', '-f', 'ssh', 'remove'])
    run_command(['/usr/sbin/update-rc.d', 'ssh', 'stop', '20', '0', '1', '6', '.',
                 'start', '27', '2', '3', '4', '5', '.'])    

    # Remove syslogd restart in cron
    run_command(['/bin/rm', '-f', '/etc/cron.daily/sysklogd'])
    run_command(['/bin/rm', '-f', '/etc/cron.weekly/sysklogd'])

def _check_forced_postupdate(_log):
    """Execute postupdate script if we detect an 'old' naftalin.

    This is done because 'old' vpnease-init does not run postupdate after
    update, so we need to run it from a script installed during the
    1.0 -> 1.1 update to bootstrap the update logic which actually
    updates naftalin code.  If we don't do this, the naftalin code
    never gets updated by postupdate.  (This is necessary because the
    preupdate and postupdate packages were removed, so we don't have
    them around anymore to do this for us.)

    Here we simply detect 'old' naftalin versions and if found, execute
    the postupdate script manually.  The script is supposed to replace
    the naftalin file after which this never gets executed again.

    We detect only deployed versions here: 1.0.5529 and 1.1.6423 (rc4).
    Note that we don't want to run this on every boot, because if the
    postupdate script is bad, it increases the risk of naftalin failure
    after update.
    """

    _log.info('checking forced postupdate')
    try:
        retval, stdout, stderr = run_command(['/usr/bin/md5sum',
                                              '/var/lib/l2tpgw-permanent/update-files.zip'],
                                             retval=runcommand.FAIL)

        t = stdout.strip()
        md5sum = t.split(' ')[0]
        md5sum = md5sum.strip()

        md5sums = [ '59015c054f4306c965962e9b9fd043e3',   # 1.0.5529
                    '8605c38b83093e83a173f8b6f06c6d6b',   # 1.1.6423 (rc4)
                    ]

        if md5sum in md5sums:
            _log.info('old naftalin detected, attempting to run postupdate now')

            # Postupdate script needs either 'success' or 'failure', simulate 'success'
            run_command(['/usr/lib/l2tpgw/l2tpgw-postupdate', 'success'], retval=runcommand.FAIL)
        else:
            _log.info('old naftalin not detected, skipping')
    except:
        _log.info('forced postupdate check failed')
        raise

def _remove_old_kernels(_log):
    """Remove old kernels which could not be removed during update process.

    It is in general a bad idea to remove a running kernel from 'underneath'
    a running system.  Hence we remove old kernel(s) on the next boot.  To
    make this check reasonably fast, we check for extra kernels from the
    /boot directory.  If only one kernel is present, no aptitude/dpkg
    operations are done to avoid delays.

    If more than one kernel is present, we purge all known 'old kernels'.
    We explicitly avoid removing the running kernel even if the running
    kernel is 'old'.
    """

    _re_kernel = re.compile(r'^vmlinuz-(.*)$')
    _re_uname = re.compile(r'^Linux\s+\S+\s+(.*?)\s+.*$')

    running_kernel = None

    # Linux ode 2.6.18-4-686 #1 SMP Mon Mar 26 17:17:36 UTC 2007 i686 GNU/Linux
    rv, stdout, stderr = run_command(['/bin/uname', '-a'], retval=runcommand.FAIL)
    stdout = stdout.strip()
    m = _re_uname.match(stdout)
    if m is None:
        raise Exception('cannot figure out running kernel version')
    running_kernel = m.group(1).strip()
    running_kernel_package_name = 'linux-image-%s' % running_kernel
    _log.info('_remove_old_kernels: running kernel is %s' % running_kernel)
    
    try_nuke = False
    for i in os.listdir('/boot'):
        m = _re_kernel.match(i)
        if m is None:
            continue
        kern = m.group(1).strip()
        if kern == running_kernel:
            _log.info('_remove_old_kernels: %s is running kernel (%s)' % (i, running_kernel))
            continue
        _log.info('_remove_old_kernels: %s is NOT running kernel (%s)' % (i, running_kernel))
        try_nuke = True

    if not try_nuke:
        _log.info('_remove_old_kernels: no extra kernels present, no further check')
        return

    _log.info('_remove_old_kernels: extra kernels present, try nuking')
    for i in old_kernel_packages:
        if i == running_kernel_package_name:
            _log.info('_remove_old_kernels: old kernel %s is running kernel, skipping nuke' % i)
            continue
            
        # XXX: more options? some noninteractive force option / env?
        _log.info('_remove_old_kernels: attempting to remove package %s' % i)
        run_command(['/usr/bin/dpkg', '--purge', i], retval=runcommand.FAIL)
        _log.info('_remove_old_kernels: removed package %s' % i)

    _log.info('_remove_old_kernels: nuking done')

# --------------------------------------------------------------------------
#
#  Main command implementations
#

def preinit():
    """Early initialization of l2tpgw.

    Stuff to do:
      * init runtime directory
      * check if this is live-cd and write markerfile if so
      * check system memory size and write lowmem marker
      * re-check and disable system daemon startups
      * live cd: launch opportunistic DHCP client
    """

    _log = logger.get('l2tpgw-init-preinit')

    try:
        helpers.create_rundir()
    except:
        _log.exception('runtime directory creation failed')
        raise

    is_livecd = False
    try:
        is_livecd = _check_livecd(_log)
    except:
        _log.exception('livecd check failed: ignoring')

    try:
        _check_memory(_log)
    except:
        _log.exception('system memory is critically low: ignoring')

    try:
        _check_daemon_startup(_log)
    except:
        _log.exception('system daemon startup check failed: ignoring')

    # This is here to update 1.0 (or 1.1rc4) naftalin when old vpnease-init
    # does not execute l2tpgw-postupdate.
    if not is_livecd:
        try:
            _check_forced_postupdate(_log)
        except:
            _log.exception('forced postupdate check failed, ignoring')

    if not is_livecd:
        try:
            _remove_old_kernels(_log)
        except:
            _log.exception('remove old kernels check failed, ignoring')

    # Live CD: start opportunistic dhclient as early as possible
    if is_livecd:
        try:
            # Paranoid firewall rules
            run_command(['/sbin/iptables', '-F'])
            run_command(['/sbin/iptables', '-P', 'OUTPUT', 'ACCEPT'])
            run_command(['/sbin/iptables', '-P', 'FORWARD', 'DROP'])
            run_command(['/sbin/iptables', '-P', 'INPUT', 'DROP'])
            run_command(['/sbin/iptables', '-A', 'INPUT', '-i', 'lo', '-j', 'ACCEPT'])
            run_command(['/sbin/iptables', '-A', 'INPUT', '-m', 'state', '--state', 'ESTABLISHED,RELATED', '-j', 'ACCEPT'])

            # Dhclient will be launched to background, and will not wait for an address
            run_command(['/sbin/dhclient', '-nw', 'eth0'])  # XXX: eth0 is fixed now
        except:
            _log.exception('failed to start dhclient to background (live cd only)')
    
def postinit():
    """Later initialization stuff.

    All python code must be available and system update/checks done.

    This does the post-install configuration if not done already
    and checks and fixes the database and RDF if possible.

    Here we also write /fastboot to ensure that fsck is done only
    at the periodic reboot time and not on some random reboot.
    """

    #
    #  XXX -- make some operations dependent on 'not livecd' to speed
    #  up live cd startup time?
    #

    _log = logger.get('l2tpgw-init-postinit')

    is_livecd = _is_livecd()

    try:
        _record_boot_timestamp(_log)
    except:
        _log.exception('recording boot timestamp failed: ignoring')

    try:
        _create_boot_uuid(_log)
    except:
        _log.exception('creating boot-time uuid failed: ignoring.')

    try:
        _firstboot_config(_log)
    except:
        _log.exception('failed to prepare configuration')
        raise

    try:
        _check_system_config(_log)
    except:
        _log.exception('checking system config failed: ignoring.')

    try:
        _check_update_rdfxml_export(_log)        
    except:
        _log.exception('update rdfxml import failed: ignoring.')
        
    try:
        _check_configuration_import(_log)
    except:
        _log.exception('configuration import failed: ignoring.')

    post_import_failures = False
    try:
        from codebay.l2tpserver.webui import uidatahelpers
        uidatahelpers.fix_missing_database_values()
    except:
        _log.exception('fix_missing_database_values() failed')
        post_import_failures = True

    try:
        from codebay.l2tpserver.webui import uidatahelpers
        pd = uidatahelpers.CreateProtocolData()
        pd.save_protocol_data(use_current_config=True)
        pd.activate_protocol_data(use_current_config=True)
    except:
        # NB: failure to generate protocol data will cause database reset;
        # this is probably the only sane thing we can do
        _log.exception('save_protocol_data() failed')
        post_import_failures = True
        
    try:
        _rdf_database_checks(_log, post_import_failures)
    except:
        _log.exception('rdf database checks failed: ignoring.')

    try:
        _fsck_markers_check(_log)
    except:
        _log.exception('fsck marker check failed: ignoring.')

    try:
        _check_interfaces(_log)
    except:
        _log.exception('network interface check failed: ignoring.')

    try:
        _cron_tweaks(_log)
    except:
        _log.exception('cron tweaks failed: ignoring.')

    try:
        _initial_l2tpgw_cron_run(_log)
    except:
        _log.exception('initial l2tpgw-cron run failed: ignoring.')

    try:
        _check_and_generate_gui_certificate(_log)
    except:
        _log.exception('failed to check and/or generate gui certificate: ignoring.')

    try:
        _update_ssl_files(_log)
    except:
        _log.exception('failed to update gui ssl files: ignoring.')

    try:
        _update_etc_issue(_log, is_livecd)
    except:
        _log.exception('failed to update /etc/issue: ignoring.')

def webuistart():
    """Start l2tpgw GUI process.

    This assumes that the database and RDF are in good condition.
    """
    _log = logger.get('l2tpgw-init-start')

    from codebay.l2tpserver import daemonstart
    d = daemonstart.DaemonStart(_log)

    if _is_livecd():
        tac_file = constants.LIVECD_TAC
    else:
        tac_file = constants.WEBUI_TAC

    try:
        d.cleanup_daemon(pidfile=constants.WEBUI_PIDFILE)
    except:
        _log.exception('Failed to cleanup before start, trying to start anyway.')
        pass

    d.start_daemon(command=constants.WEBUI_COMMAND,
                   pidfile=constants.WEBUI_PIDFILE, # given to start_daemon even when it doesn't create the pidfile
                   args=['--pidfile=' + constants.WEBUI_PIDFILE,
                         '--rundir=/usr/lib/l2tpgw',
                         '--python=' + tac_file,
                         '--syslog',
                         '--no_save'],
                   background=False,    # twistd will fork
                   make_pidfile=False)  # twistd makes pidfile

def webuistop():
    _log = logger.get('l2tpgw-init-stop')

    from codebay.l2tpserver import daemonstart
    d = daemonstart.DaemonStart(_log)

    try:
        rv = d.stop_daemon(command=constants.WEBUI_COMMAND, pidfile=constants.WEBUI_PIDFILE,
                           timeout=constants.WEBUI_STOP_TIMEOUT)  # give GUI at least this amount of time
    except daemonstart.Timeout:
        _log.warning('_stop_gui() timed out, using hard kill')
        d.hard_stop_daemon(command=constants.WEBUI_COMMAND, pidfile=constants.WEBUI_PIDFILE)
    except:
        _log.exception('Failed to stop, ignore cleanup actions')
        raise

    d.cleanup_daemon(pidfile=constants.WEBUI_PIDFILE)

