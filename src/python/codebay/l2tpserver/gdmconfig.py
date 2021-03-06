#!/usr/bin/python

import re, textwrap

from codebay.common import logger, helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants

run_command = runcommand.run_command

_log = logger.get('l2tpserver.gdmconfig')

custom_config = textwrap.dedent("""
# This file is automatically generated, do not edit.

[daemon]

AutomaticLoginEnable=%(autologin)s
AutomaticLogin=%(autologin_user)s

TimedLoginEnable=%(autologin)s
TimedLogin=%(autologin_user)s
TimedLoginDelay=10

[security]
[xdmcp]
[gui]

GtkTheme=HighContrast
AllowGtkThemeChange=false
GtkThemesToAllow=HighContrast

[greeter]
BackgroundType=2
BackgroundColor=%(back_color)s
GraphicalThemedColor=%(back_themed_color)s

GraphicalTheme=happygnome

SoundOnLogin=false
ConfigAvailable=false
ChooserButton=false

[chooser]
[debug]
[servers]
""")


def run(autologin=False, autologin_user=None):
    gdm_conf = '/etc/gdm/gdm.conf-custom'

    config_vars = {'back_color': constants.GDM_BACKGROUND_COLOR, 'back_themed_color': constants.GDM_GRAPHICAL_THEMED_COLOR}

    if autologin:
        _log.info('Setting GDM autologin to user %s' % autologin_user)
        config_vars.update({'autologin':'true', 'autologin_user': autologin_user})
    else:
        _log.info('Unsetting GDM autologin')
        config_vars.update({'autologin':'false', 'autologin_user': 'nobody'})

    helpers.write_file(gdm_conf, custom_config % config_vars, append=False, perms=0644)
        
if __name__ == "__main__":
    run(autologin=True, autologin_user='admin')
