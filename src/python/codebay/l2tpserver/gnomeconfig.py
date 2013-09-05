"""Gnome configuration helpers."""
__docformat__ = 'epytext en'
import os, string, textwrap

from codebay.common import logger
_log = logger.get('l2tpserver.update.update')

from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand

run_command = runcommand.run_command


def _get_browser_url(is_livecd):
    """Get default browser URI for autostart and desktop icon.

    This default URI can be different in Live CD and installed system.
    """
    if is_livecd:
        return 'http://localhost/'
    else:
        return 'http://localhost/'

def _create_desktop_entry(is_livecd):
    """Create desktop entry contents."""
    return textwrap.dedent("""\
    [Desktop Entry]
    Encoding=UTF-8
    Name=%(product)s
    Comment=%(product)s Launcher Icon
    Exec=/usr/bin/firefox %(url)s
    Terminal=false
    Icon=%(iconfile)s
    Type=Application
    """) % {'url': _get_browser_url(is_livecd),
            'product': constants.PRODUCT_NAME,
            'iconfile': constants.GNOME_DESKTOP_ICON_IMAGE }

def _create_autostart_entry(is_livecd):
    """Create autostart entry contents."""
    return textwrap.dedent("""\
    [Desktop Entry]
    Encoding=UTF-8
    Name=%(product)s
    Comment=%(product)s Autostart
    Exec=%(cmd)s %(url)s
    Terminal=false
    Icon=%(iconfile)s
    Type=Application
    X-GNOME-Autostart-enabled=true
    """) % {'cmd': constants.CMD_L2TPGW_GNOME_AUTOSTART,
            'url': _get_browser_url(is_livecd),
            'product': constants.PRODUCT_NAME,
            'iconfile': constants.GNOME_DESKTOP_ICON_IMAGE }

def write_desktop_entry(is_livecd, fname):
    """Write desktop entry to specified file for either Live CD or normal system."""
    f = None
    try:
        f = open(fname, 'wb')
        f.write(_create_desktop_entry(is_livecd))
    finally:
        if f is not None:
            f.close()

def write_autostart_entry(is_livecd, fname):
    """Write autostart entry to specified file for either Live CD or normal system."""
    f = None
    try:
        f = open(fname, 'wb')
        f.write(_create_autostart_entry(is_livecd))
    finally:
        if f is not None:
            f.close()
    
def gnomeconfig_firstboot(is_livecd):
    """Do firstboot config for Gnome.

    NB: Desktop & autostart entries are recreated on every boot, so they
    are not needed here.

    Note: User configuration overrides default mandatory options!
    User config is written based on default config when gconf2 starts
    first (not restarted when gnome session restarts) time and user config
    does not already exists. Only part of config is handled this way: panel,
    screensaver, power-manager at least.

    This is run on first boot:
    XXX: we could try to use user config here but it is problematic:
    how to ensure that our (inportant) changes are preferred over user-made
    configuration?
    XXX: to modify conf user config directly:
    --config-source xml:readwrite:/home/admin/.gconf
    XXX: may also purge user panel, etc. config here using:
    --recursive-unset

    Gconf directory locations (from /etc/gconf/2/path):

    # This is empty by default
    # Local admin config file: this should not change even when gnome
    # is update, so better make modifications here.
    xml:readonly:/etc/gconf/gconf.xml.mandatory

    # User settings: readwrite means writable by config tools
    xml:readwrite:$(HOME)/.gconf

    # This seems not to include any ubuntu/debian stuff but only gnome defaults
    # Main default configuration options
    xml:readonly:/etc/gconf/gconf.xml.defaults

    # GTK theme, ubuntu splash, ubuntu colors, sound server on, etc. small stuff
    xml:readonly:/var/lib/gconf/debian.defaults

    # Upstream application defaults
    xml:readonly:/var/lib/gconf/defaults
    """

    defurl = _get_browser_url(is_livecd)
    screensaver_minutes = 30

    class ConfOpt:
        """Gconf options."""

        def __init__(self, path, *args):
            self.path = path
            self.configs = args
            self.children = []

        def prepend_path(self, path):
            if self.path is None:
                self.path = path
            else:
                self.path = os.path.join(path, self.path)

        def add(self, *args):
            for i in args:
                i.prepend_path(self.path)
                self.children.append(i)

            return self

        def get(self):
            res = []
            if len(self.configs) > 0:
                for name, val in self.configs:
                    confloc = os.path.join(self.path, name)
                    if isinstance(val, int):
                        res.append([confloc, str(val), 'int', None])
                    elif isinstance(val, str):
                        res.append([confloc, str(val), 'string', None])
                    elif isinstance(val, bool):
                        if val:
                            res.append([confloc, 'true', 'bool', None])
                        else:
                            res.append([confloc, 'false', 'bool', None])
                    elif isinstance(val, list) and len(val) > 0:
                        def _join_int(val):
                            s = []
                            for i in val:
                                s.append(str(i))
                            return '[' + ','.join(s) + ']'

                        def _join_str(val):
                            return _join_int(val)

                        def _join_bool(val):
                            s = []
                            for i in val:
                                if i:
                                    s.append('true')
                                else:
                                    s.append('false')
                            return '[' + ','.join(s) + ']'

                        if isinstance(val[0], int):
                            res.append([confloc, _join_int(val), 'list', 'int'])
                        elif isinstance(val[0], str):
                            res.append([confloc, _join_str(val), 'list', 'string'])
                        elif isinstance(val[0], bool):
                            res.append([confloc, _join_bool(val), 'list', 'bool'])
                        else:
                            # XXX: raise
                            pass
                    else:
                        # XXX: raise
                        pass

            for i in self.children:
                res.extend(i.get())
            return res

    conf = []
    conf_location = 'xml:readwrite:/etc/gconf/gconf.xml.mandatory'

    def _conf_command(cmd):
        return ['/usr/bin/gconftool-2', '--direct', '--config-source', conf_location] + cmd

    def _conf_set_command(key, value, valuetype, listtype):
        if valuetype == 'list' or listtype is not None:
            cmd = ['--type', 'list', '--list-type', listtype]
        else:
            cmd = ['--type', valuetype]

        cmd += ['--set', key, value]
        return _conf_command(cmd)

    def _conf_purge_command(key):
        return _conf_command(['--recursive-unset', key])

    # Panel config
    # Original Ubuntu config as reference found in #459

    # Remove unused parts:
    conf.append(_conf_purge_command('/apps/panel/default_setup/toplevels/bottom_panel'))

    p1 = ConfOpt('/apps/panel/default_setup').add(ConfOpt('general',
                                                          ['object_id_list', ['menu_bar']],
                                                          ['applet_id_list', ['notification_area', 'window_list']], # note: no clock applet
                                                          ['toplevel_id_list', ['top_panel']]),
                                                  ConfOpt('toplevels/top_panel',
                                                          ['orientation', 'bottom']),
                                                  ConfOpt('applets/window_list',
                                                          ['toplevel_id', 'top_panel']))
                                                  
    p2 = ConfOpt('/apps/panel/global',
                 ['locked_down', True],
                 ['enable_animations', False],
                 ['disable_log_out', True],
                 ['tooltips_enabled', False],
                 ['disable_lock_screen', True])

    for key, value, valuetype, listtype in p1.get() + p2.get():
        conf.append(_conf_set_command(key, value, valuetype, listtype))

    # Desktop and misc applications:

    # XXX: theme and colors, etc.
    # examples: http://cvs.gnome.org/viewcvs/livecd-project/scripts/prepare.sh?view=markup

    background_image = constants.GNOME_BACKGROUND_IMAGE
    splash_image = constants.GNOME_SPLASH_IMAGE

    d1 = ConfOpt('/desktop/gnome').add(ConfOpt('url-handlers').add(ConfOpt('https',
                                                                           ['command', 'firefox %s']),
                                                                   ConfOpt('http',
                                                                           ['command', 'firefox %s'])),
                                       ConfOpt('sound',
                                               ['enable_esd', False],
                                               ['event_sounds', False]),
                                       ConfOpt('peripherals/mouse',
                                               ['cursor_theme', 'Human']),
                                       ConfOpt('interface',
                                               ['icon_theme', 'Human'],
                                               ['gtk_theme', 'Human']),
                                       ConfOpt('background',
                                               ['picture_filename', background_image],
                                               ['primary_color', '#643821'],
                                               ['secondary_color', '#2C160A'],
                                               ['color_shading_type', 'solid'],
                                               ['draw_background', True]),
                                       ConfOpt('applications/browser',
                                               ['exec', 'firefox']))

    d2 = ConfOpt('/apps').add(ConfOpt('epiphany/general',
                                      ['homepage', defurl]),
                              ConfOpt('mozilla-firefox/general',
                                      ['homepage', defurl]),
                              ConfOpt('gnome-session/options',
                                      ['splash_image', splash_image]),
                              ConfOpt('gnome-screensaver',
                                      ['mode', 'blank-only']),
                              ConfOpt('gnome-power-manager',
                                      ['can_hibernate', False]),
                              ConfOpt('gnome-screensaver',
                                      ['idle_delay', int(screensaver_minutes)]),
                              ConfOpt('metacity/general',
                                      ['num_workspaces', 1]))

    for key, value, valuetype, listtype in d1.get() + d2.get():
        conf.append(_conf_set_command(key, value, valuetype, listtype))


    # Fileformat defaults: no gconf values for these so must set
    # from here.
    gnomedef = '/etc/gnome/defaults.list'
    ff = [r's%application/msword=.*%application/msword=abiword.desktop%',
          r's%text/richtext=.*%text/richtext=abiword.desktop%',
          r's%text/rtf=.*%text/rtf=abiword.desktop%',
          r's%application/rtf=.*%application/rtf=abiword.desktop%',
          r's%application/msexcel=.*%application/msexcel=gnumeric.desktop%',
          r's%application/excel=.*%application/excel=gnumeric.desktop%']
    for i in ff:
        conf.append(['/bin/sed', '-i', i, gnomedef])

    for i in conf:
        run_command(i)

def _read_xklaviertool():
    myenv = dict(os.environ)
    myenv['DISPLAY'] = ':0.0'
    myenv['HOME'] = '/home/%s' % (constants.ADMIN_USER_NAME)

    rc, stdout, stderr = run_command([constants.CMD_XKLAVIERTOOL], retval=runcommand.FAIL, env=myenv)

    curr_layout, curr_variant = None, None
    reading_layout, reading_variant = False, False

    curr_layout = None
    layouts = {}
    for l in stdout.split('\n'):
        # last line may be empty
        if l == '':
            continue
        
        t = l.split('^')
        if len(t) != 4:
            raise Exception('syntax error parsing xklaviertool output: %s' % l)
        linetype, name, short, long = t

        if linetype == 'LAYOUT':
            curr_layout = name
            x = layouts[name] = {}
            x['name'] = name
            x['short_description'] = short
            x['long_description'] = long
            x['variants'] = {}
        elif linetype == 'VARIANT':
            if curr_layout is None:
                raise Exception('current layout is None while parsing xklaviertool output')
            x = layouts[curr_layout]['variants'][name] = {}
            x['name'] = name
            x['short_description'] = short
            x['long_description'] = long
            x['layout_name'] = curr_layout
        else:
            raise Exception('syntax error parsing xklaviertool output: %s' % l)

    return layouts

def get_keymap_list():
    """Get a list of keymaps for use with set_keymap_settings().

    Return a list, where each list element contains a Gnome name (e.g. 'fi\\tnodeadkeys')
    which is suitable as a parameter to set_keymap_settings(), a cleaned up Gnome name
    (e.g. 'fi:nodeadkeys' where tabs are replaced by colons), and a user friendly name
    ('Finnish etc').

    Where to get the actual Gnome information?  There are many possible places:
      * /usr/share/libxklavier/xfree86.xml, part of the libxklavier package,
        but this cannot be the Gnome source, as it doesn't differentiate between
        Finnish with and without dead keys (for instance).

      * /usr/share/keymaps, but this cannot be the Gnome source, as it doesn't
        contain some information Gnome has (e.g. Northern Saami string doesn't
        appear anywhere).

      * gnome-control-center package (/usr/bin/gnome-keyboard-properties), source
        files (apt-get source gnome-control-center):
          ./gnome-settings-daemon/gnome-settings-keyboard-xkb.*
          ./gnome-settings-daemon/gnome-settings-keyboard.*
          ./capplets/keyboard/gnome-keyboard-properties*

      * /etc/X11/xkb, particularly the following look promising
        * /etc/X11/xkb/rules/
               base*
               xorg*
               xfree86*

        * These come from xkeyboard-config package

        * E.g. xorg.xml looks promising, it has the same texts as Gnome has.
          Further, Gnome seems to use XKB information when gnome-control-panel
          code was checked.

        * However, we're not supposed to read these directly; one should
          probably use libxklavier (as Gnome seems to do).

      * If we use libxklavier, an external self-written tool (e.g. xklaviertool)
        could be used.

      * See also:
        * http://www.freedesktop.org/wiki/KeyboardInputDiscussion
        * http://www.charvolant.org/~doug/xkb/html/xkb.html
        * http://gswitchit.sourceforge.net/gnome_xkb_tsh.pdf
        * http://gswitchit.sourceforge.net/
        * http://www.freedesktop.org/wiki/Software/LibXklavier
        * http://xlibs.freedesktop.org/xkbdesc/doc/
    """

    try:
        res = []
        layouts = _read_xklaviertool()

        l_keys = layouts.keys()
        l_keys.sort()
        for k in l_keys:
            layout = layouts[k]
            def _escape_gnomename(gname):
                return string.replace(gname, '\t', ':')
            
            # add version without variant first
            gnomename = '%s' % layout['name']
            res.append([gnomename,
                        _escape_gnomename(gnomename),
                        layout['long_description']])

            # then add variants
            v_keys = layout['variants'].keys()
            v_keys.sort()
            for v in v_keys:
                variant = layout['variants'][v]
                gnomename = '%s\t%s' % (layout['name'], variant['name'])
                res.append([gnomename,
                            _escape_gnomename(gnomename),
                            '%s (%s)' % (layout['long_description'],
                                         variant['long_description'])])

        return res
    except:  # XXX: wide except :(
        # failsafe
        _log.error('cannot run xklaviertool to get keymaps, falling back to defaults')
        return [ ['us', 'us', 'US'] ]

def set_keymap_settings(keymap):
    """Activate certain keymap through Gnome, changing settings directly without delay.

    The new keymap will be changed for all windows immediately.  The keymap parameter
    must be directly suitable for Gnome, e.g. 'fi', 'us', or 'fi\\tnodeadkeys' (where
    the separator is a tab.  Use get_keymap_list() to get a list of keymaps (both
    Gnome name and user friently name).

    XXX: for practical reasons we also accept gnome escaped names (e.g.
    'fi\\tnodeadkeys' -> 'fi:nodeadkeys') because they are easier for the web UI
    to deal with.  Should be fixed properly.
    """

    if ':' in keymap:
        _log.warning('colon(s) in keymap, caller is not apparently using gnomename')
        keymap =  string.replace(keymap, ':', '\t')
    
    # running gconf needs environment to be exactly correct, at least the
    # following need to be correctly set:
    #    1. user ID (and group ID)
    #    2. HOME environment variable
    #    3. DISPLAY environment variable
    #
    # without these the commands may well succeed but do nothing.

    myenv = dict(os.environ)
    myenv['HOME'] = '/home/%s' % constants.ADMIN_USER_NAME
    myenv['DISPLAY'] = ':0.0'

    # gconf-editor is best for checking these out
    run_command([constants.CMD_SUDO, '-u', constants.ADMIN_USER_NAME, constants.CMD_GCONFTOOL2, '--set', '/desktop/gnome/peripherals/keyboard/general/defaultGroup', '--type', 'int', '0'], retval=runcommand.FAIL, env=myenv)
    run_command([constants.CMD_SUDO, '-u', constants.ADMIN_USER_NAME, constants.CMD_GCONFTOOL2, '--set', '/desktop/gnome/peripherals/keyboard/kbd/layouts', '--type', 'list', '--list-type', 'string', '[%s]' % keymap], retval=runcommand.FAIL, env=myenv)
    run_command([constants.CMD_SUDO, '-u', constants.ADMIN_USER_NAME, constants.CMD_GCONFTOOL2, '--set', '/desktop/gnome/peripherals/keyboard/general/groupPerWindow', '--type', 'bool', 'false'], retval=runcommand.FAIL, env=myenv)

if __name__ == "__main__":
    gnomeconfig_firstboot(False)
