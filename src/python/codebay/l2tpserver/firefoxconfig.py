"""Firefox configuration from scripts.

This file provides functions to change firefox settings ("preset" configuration)
for the admin user so that Firefox defaults make sense for product use.  In
particular, unnecessary warnings are disabled.

The changes are made through 'user.js'; see:
  * http://kb.mozillazine.org/Editing_configuration
  * http://kb.mozillazine.org/User.js_file
  * http://kb.mozillazine.org/Profile_folder

For various configuration options, see Firefox resources.  You can also use the
URI "about:config" in a Firefox to get configuration entries for that particular
version.

Some customizations are only possible by editing the local RDF store of Firefox
(localstore.rdf) for the default profile (/etc/firefox/profile).  See:
  * http://fxcorp.sanduskycomputers.com/customize_print.php#toolbar

Also see:
  * http://www.computerworld.com/action/article.do?command=viewArticleBasic&articleId=9020880
"""
__docformat__ = 'epytext en'

import textwrap, os

from codebay.common import logger
from codebay.l2tpserver import constants

from codebay.l2tpserver import runcommand
run_command = runcommand.run_command

_log = logger.get('l2tpserver.firefoxconfig')

firefox_global_profile_userjs = '/etc/firefox/profile/user.js'
firefox_global_profile_localstorerdf = '/etc/firefox/profile/localstore.rdf'
firefox_global_profile_bookmarkshtml = '/etc/firefox/profile/bookmarks.html'

_custom_localstore = textwrap.dedent("""\
<?xml version="1.0"?>
<RDF:RDF xmlns:NC="http://home.netscape.com/NC-rdf#"
         xmlns:RDF="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <RDF:Description RDF:about="chrome://browser/content/sanitize.xul">
    <NC:persist RDF:resource="chrome://browser/content/sanitize.xul#SanitizeDialog"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/preferences/fonts.xul#FontsDialog"
                   screenX="60"
                   screenY="43" />
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#PersonalToolbar"
                   collapsed="true"
                   iconsize="small" />
  <RDF:Description RDF:about="chrome://browser/content/preferences/advanced-scripts.xul">
    <NC:persist RDF:resource="chrome://browser/content/preferences/advanced-scripts.xul#AdvancedJSDialog"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#nav-bar"
                   iconsize="small" />
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#toolbar-menubar"
                   iconsize="small" />
  <RDF:Description RDF:about="chrome://browser/content/sanitize.xul#SanitizeDialog"
                   screenX="311"
                   screenY="213" />
  <RDF:Description RDF:about="chrome://browser/content/preferences/advanced-scripts.xul#AdvancedJSDialog"
                   screenX="183"
                   screenY="144" />
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#sidebar-title"
                   value="" />
  <RDF:Description RDF:about="chrome://browser/content/browser.xul">
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#main-window"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#PersonalToolbar"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#sidebar-box"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#sidebar-title"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#navigator-toolbox"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#toolbar-menubar"/>
    <NC:persist RDF:resource="chrome://browser/content/browser.xul#nav-bar"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#main-window"
                   screenX="0"
                   screenY="0"
                   width="994"
                   height="714"
                   sizemode="maximized" />
  <RDF:Description RDF:about="chrome://browser/content/preferences/preferences.xul#BrowserPreferences"
                   screenX="178"
                   screenY="125"
                   lastSelected="paneGeneral" />
  <RDF:Description RDF:about="chrome://browser/content/preferences/fonts.xul">
    <NC:persist RDF:resource="chrome://browser/content/preferences/fonts.xul#FontsDialog"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/preferences/preferences.xul">
    <NC:persist RDF:resource="chrome://browser/content/preferences/preferences.xul#BrowserPreferences"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/preferences/sanitize.xul">
    <NC:persist RDF:resource="chrome://browser/content/preferences/sanitize.xul#SanitizeDialog"/>
  </RDF:Description>
  <RDF:Description RDF:about="chrome://browser/content/browser.xul#navigator-toolbox"
                   iconsize="small" />
  <RDF:Description RDF:about="chrome://browser/content/preferences/sanitize.xul#SanitizeDialog"
                   screenX="133"
                   screenY="55" />
</RDF:RDF>
""")
    
# XXX: timestamps below are not a good idea?
# XXX: www.vpnease.com does not have an icon
_custom_bookmarks = textwrap.dedent("""\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<!-- Automatically generated by VPNease.  DO NOT EDIT! -->
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1 LAST_MODIFIED="1192523554">Bookmarks</H1>

<DL><p>
    <DT><H3 LAST_MODIFIED="1192523509" PERSONAL_TOOLBAR_FOLDER="true" ID="rdf:#$FvPhC3">Bookmarks Toolbar Folder</H3>
<DD>Add bookmarks to this folder to see them displayed on the Bookmarks Toolbar
    <DL><p>
    </DL><p>
    <HR>
    <DT><A HREF="http://www.vpnease.com/" ADD_DATE="1192523056" LAST_VISIT="1192523602" LAST_MODIFIED="1192523594" LAST_CHARSET="UTF-8" ID="rdf:#$dURYU1">VPNease - Home</A>
<DD>VPNease Home
    <DT><A HREF="http://localhost/" ADD_DATE="1192523554" LAST_VISIT="1192523561" LAST_MODIFIED="1192523582" ICON="data:image/gif;base64,R0lGODlhEAAQAOesAAh6Ygl6ZQl5bgl4fAt6bA16dxB+ZxJ7iBWBaheCaxZ9kBl+kx6BiB+FcSCCiCSJdSF/uCF/uSOAvSiLeCSBuimLdyWBuiWBvCqMeSuMeieCvymDtiiDvSmDvy6OfSuEvi+PfziUgTuVhTmPrkWaikecjEqdjUmWxE2ej06fkEuYxlGgklGgk1GhkVKik1SbtFadtVmmlFqml1misFynmV2nnVqgzWKqnWaroGWm0GmuoGmuomqvomqp022xom6wpW6xom+xpXCypnKu0na1qHSv03i1qnaw03m2q3ix1Hu4rH25rYO1z4O7soO2zoW8soS9s4a9tIe62ozCt46725C925K93JLEu5O+3ZLFvJTFvJS/3ZXFu5W/3JbA3pbB3pfB3ZfC35jC3ZnB4JnC4ZnC4pvD4JzJwZ3D4Z7E357LwZ7G35/G4KDF46PMxaPMxqPNxaPJ4KTOxaTOxqTNzKXOxafL4afL4qjQxqnM5KnSyarN5KzO46vTy6zO5azTzK3O5a3TzK7R5bHQ5LHS5rTX0bfZ07rZ07na0rvX7L3b1b7b3r/d1cLe2MLe2cXf28Xf4cni3srf7cvg7s3h7s7h79Dn49Hn4dLk8dPo4tbo5dXn8dbp5Nbo7Njo8Njq5tzp8tvs6eDs+eLv6uPu+ejy8PT5+Pj7/fn8/fn8/vv8/vv9/v///////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////yH+FUNyZWF0ZWQgd2l0aCBUaGUgR0lNUAAh+QQBCgD/ACwAAAAAEAAQAAAI5QBZCRxIsGDBU3u8mEEzxk8qg6wmYYGkBkgMH3TIVCooyQ4jLk9+rPAAYEYeSgNPVcnU6NCbKDhINBjQQwwqgXc6ZSqlqVCWICgqCJAgiI9AK5w+mQpl6IyQFBgIaCgCRuAXRI4sPdKjZUeJBwU6nFgjMEwdOH/mXIEiQ0QCBRxUpBG4BY+SJlPcIGExIcAGC0mqsgK0SM0ZRUZchDCw4AMEQoMEqqIyqs+NJTQQHPhAYUiXVQMxsbkkR0eNERciHImzqaCoMqA85bAhJVEbUgQjEWkBgsELJk5gOMhggkcgiMgFBgQAOw==" LAST_CHARSET="UTF-8" ID="rdf:#$fURYU1">VPNease - Local Administrator</A>
</DL><p>
""")

def _set_firefox_userjs(homedir):
    userjs = textwrap.dedent("""\
    //
    // Automatically generated user preferences (l2tpgw)
    //
    
    // No unnecessary warnings
    user_pref("security.warn_entering_secure", false);
    user_pref("security.warn_leaving_secure", false);
    user_pref("security.warn_submit_insecure", false);

    // Caches
    user_pref("browser.cache.disk.capacity", 1000);
    user_pref("browser.cache.disk.enable", true);
    user_pref("browser.cache.memory.enable", true);

    // No password management
    user_pref("signon.rememberSignons", false);

    // Javascript
    user_pref("javascript.enabled", true);
    user_pref("dom.max_script_run_time", 30);
    
    // Cookies
    user_pref("network.cookie.alwaysAcceptSessionCookies", true);

    // Homepage
    user_pref("browser.startup.homepage", "http://localhost/");

    // Never store or restore sessions
    user_pref("browser.sessionstore.enabled", false);
    user_pref("browser.sessionstore.resume_from_crash", false);

    // Updates disabled
    user_pref("app.update.disable_button.showUpdateHistory", false);
    user_pref("app.update.enabled", false);
    user_pref("browser.history_expire_days.mirror", 9);
    user_pref("browser.search.update", false);
    user_pref("extensions.update.enabled", false);
    user_pref("browser.safebrowsing.enabled", false);
    """)

    f = None
    try:
        f = open(firefox_global_profile_userjs, 'wb')
        f.write(userjs)
    finally:
        if f is not None:
            f.close()

def _set_firefox_localstore(homedir):
    # VPNease customized localstore.rdf, created by editing settings through
    # Firefox menus, and then ripping the localstore.rdf from the .mozilla
    # profile directory.  (This is actually the method suggested in the web.)

    localstore_rdf = _custom_localstore

    f = None
    try:
        f = open(firefox_global_profile_localstorerdf, 'wb')
        f.write(localstore_rdf)
    finally:
        if f is not None:
            f.close()
    
def _set_firefox_bookmarks(homedir):
    # VPNease customized bookmarks.html, created by editing bookmarks
    # manually and then ripping bookmarks.html from the profile.

    bookmarks_html = _custom_bookmarks

    f = None
    try:
        f = open(firefox_global_profile_bookmarkshtml, 'wb')
        f.write(bookmarks_html)
    finally:
        if f is not None:
            f.close()
    
def set_firefox_configuration(homedir):
    _set_firefox_userjs(homedir)
    _set_firefox_localstore(homedir)
    _set_firefox_bookmarks(homedir)

    # Clear users profile to take default configs in use
    run_command([constants.CMD_RM, '-rf', os.path.join(homedir, '.mozilla', 'firefox')])
