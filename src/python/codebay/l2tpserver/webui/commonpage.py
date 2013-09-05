"""
Common page logic for all pages.
"""
__docformat__ = 'epytext en'

import os, datetime, textwrap

from nevow import inevow, rend, guard, stan, tags as T, flat
from twisted.cred import credentials
from twisted.internet import defer
try:
    from twisted.web import http
except ImportError:
    from twisted.protocols import http

from codebay.common import logger # inits siteconf

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import doclibrary
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import l2tpmanager
from codebay.l2tpserver.webui import renderers

_log = logger.get('l2tpserver.webui.commonpage')

_pagedir = constants.WEBUI_PAGES_DIR

doclib = doclibrary.DocLibrary(_pagedir)

# --------------------------------------------------------------------------
#
#  XXX: Currently unused.  Rendering exceptions is currently quite
#  useless: exceptions in Formal form rendering result in an "unhandled
#  exception in Deferred" and page loading remains incomplete.
#

class ExceptionRenderingMixin:
    def renderHTTP_exception(self, ctx, reason):
        _log.error('rendering exception: %s' % reason)
        request = inevow.IRequest(ctx)
        request.setResponseCode(http.INTERNAL_SERVER_ERROR)
        request.write("<html><head><title>Exception</title></head><body>")
        from nevow import failure
        result = failure.formatFailure(reason)
        request.write(''.join(flat.flatten(result)))
        request.write("</body></html>")
        request.finishRequest( False )

    def renderInlineException(self, context, reason):
        from nevow import failure
        formatted = failure.formatFailure(reason)
        desc = str(reason)
        return flat.serialize([
            stan.xml("""<div style="border: 1px dashed red; color: red; clear: both" onclick="this.childNodes[1].style.display = this.childNodes[1].style.display == 'none' ? 'block': 'none'">"""),
            desc,
            stan.xml('<div style="display: none">'),
            formatted,
            stan.xml('</div></div>')
        ], context)

# --------------------------------------------------------------------------

class SharedNav:
    """Navigation helper shared by page templates in this file."""
    def create_nav_list(self, ctx, items, uri_builder, external=False, disabled=False):
        tmp = inevow.IRequest(ctx).URLPath()
        tmp = tmp.clear()  # remove query parameters
        pageuri = str(tmp)

        ul = T.ul()
        for [text, urilist] in items:
            classes = []
            if disabled:
                classes.append('disabled')
                li = T.li[text]
            else:
                # first uri in list is the 'primary' URI (in menu)
                href = uri_builder(urilist[0])
                a = T.a(href=href)[text]
                if external:
                    a(target='_blank')
                li = T.li[a]
            for u in urilist:
                # any uri in the list is recognized as 'current' page
                if pageuri.endswith(u):  # XXX: could be better
                    classes.append('current')
                    break
            if len(classes) > 0:
                li(_class=' '.join(classes))
            ul[li]

        return ul

# --------------------------------------------------------------------------

class CommonPage(rend.Page):
    """Common page ancestor for all product pages.

    Contains no layout related functionality.
    """

    class __metaclass__(type):
        # XXX: hack to convert a template member that is a string to a
        # doclib.getDocument instance. Is here until we have a solid idea
        # on which way around we want it to be.
        def __new__(cls, name, bases, cdict):
            if isinstance(cdict.get('template', None), (str, unicode)):
                cdict['template'] = doclib.getDocument(cdict['template'])
            return type.__new__(cls, name, bases, cdict)
    
    docFactory = None
    template = None

    def __init__(self, original=None, *args, **kw):
        self.master = kw.pop('master', None)
        self.mind = kw.pop('mind', None)
        rend.Page.__init__(self, original, *args, **kw)

    def get_master(self):
        return self.master

    def get_mind(self):
        return self.mind

    def get_product_name(self):
        return helpers.get_product_name()

    def get_product_version(self):
        return helpers.get_product_version()

    def get_date_and_time(self):
        tzh = uihelpers.get_timezone_helper()
        time_text = tzh.render_datetime(datetime.datetime.utcnow())
        return time_text
    
    def build_uri(self, ctx, suffix):
        return uihelpers.build_uri(ctx, suffix)

    def get_logged_in_username(self):
        mind = self.get_mind()
        username = None
        if mind is not None:
            cred = mind.credentials
            if mind.isLocal():
                username = constants.LOCAL_ADMINISTRATOR_NAME
            elif isinstance(cred, credentials.UsernamePassword):
                username = str(cred.username)
            else:
                raise Exception('unexpected mind credentials: %s' % cred)
        return username

    def is_mind_local(self):
        mind = self.get_mind()
        if mind is None:
            return False
        return mind.isLocal()
    
    def service_active(self):
        mgr = self.master.l2tpmanager

        if mgr is None:
            return False
        if mgr.isRunning():
            return True
        return False

    def macro_productname(self, ctx):
        return constants.PRODUCT_NAME

    def macro_productversion(self, ctx):
        return self.get_product_version()

    @db.transact()
    def renderHTTP(self, ctx):
        # defined here so we can wrap it in @db.transact()
        return rend.Page.renderHTTP(self, ctx)

# --------------------------------------------------------------------------

class AdminPage(CommonPage, renderers.CommonRenderers, SharedNav):
    """Page layout for actual configuration when admin has logged in."""

    docFactory = doclib.getDocument('admin/adminpage.xhtml')
    pagetitle = 'No Title'
    nav_disabled = False

    def render_page_title(self, ctx, data):
        return self.pagetitle
    
    def render_logout_uri(self, ctx, data):
        # Logout for local administrator is different, because we handle the
        # portal/avatar a bit differently.
        if self.is_mind_local():
            logout_uri = '/locallogin.html'
        else:
            uri_after_logout = ''
            logout_uri = '/admin/' + guard.LOGOUT_AVATAR + uri_after_logout
        return ctx.tag(href=logout_uri)
 
    def render_nav_heading_disabled_class(self, ctx, data):
        if self.nav_disabled:
            ctx.tag(_class='disabled')
        return ctx.tag

    def render_nav_status(self, ctx, data):
        items= [ ['Overview', ['status/main.html']],
                 ['User Connections', ['status/users.html', 'status/usershistory.html']],
                 ['Site-to-Site Connections', ['status/sitetosites.html', 'status/sitetositeshistory.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)
    
    def render_nav_config(self, ctx, data):
        items = [ ['Network', ['config/networkconfig.html']],
                  ['Routing & Firewall', ['config/routingfirewall.html']],
                  ['User Accounts', ['users/userconfig.html']],
                  ['Site-to-Site Connections', ['config/sitetositeconfig.html']],
                  ['License & Maintenance', ['management/management.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)

    def render_nav_management(self, ctx, data):
        items = [ ['Reboot', ['management/confirmreboot.html', 'management/waitreboot.html']],
                  ['Shut Down', ['management/confirmshutdown.html', 'management/waitshutdown.html']],
                  ['Product Updates', ['management/confirmupdate.html', 'management/waitupdate.html']],
                  ['Import Configuration', ['management/configimport.html', 'management/waitconfigimport.html']],
                  ['Export Configuration', ['management/configexport.html']],
                  ['Export Diagnostics', ['management/diagnosticsexport.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)

    # Debug nav is conditional to a magic marker file
    def render_nav_debug_maybe(self, ctx, data):
        try:
            if os.path.exists(constants.WEBUI_DEBUG_NAV_MARKERFILE):
                return ctx.tag
        except:
            pass
        return ''
    
    def render_nav_debug(self, ctx, data):
        items = [ ['Debug Settings', ['config/debugconfig.html']],
                  ['Dump L2TP Config', ['dumpconfig.html']],
                  ['Dump L2TP Status', ['dumpstatus.html']],
                  ['Dump UI Config', ['dumpuiconfig.html']],
                  ['Dump All', ['dumpall.html']],
                  ['Dump SNMP', ['dumpsnmp.html']],
                  ['Dump Syslog', ['dumpsyslog.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)

    def macro_content(self, ctx):
        return doclibrary.patternLoader(self.template, 'content')

# --------------------------------------------------------------------------

class UserPage(CommonPage, renderers.CommonRenderers, SharedNav):
    """Page layout for logged in end-users."""

    docFactory = doclib.getDocument('user/userpage.xhtml')
    pagetitle = 'No Title'
    nav_disabled = False

    def render_page_title(self, ctx, data):
        return self.pagetitle
    
    def render_logout_uri(self, ctx, data):
        uri_after_logout = ''
        logout_uri = '/user/' + guard.LOGOUT_AVATAR + uri_after_logout
        return ctx.tag(href=logout_uri)

    def macro_content(self, ctx):
        return doclibrary.patternLoader(self.template, 'content')

    def render_headextras(self, ctx, data):
        return doclibrary.patternLoader(self.template, 'headextras', default='')
        
    def render_nav_heading_disabled_class(self, ctx, data):
        if self.nav_disabled:
            ctx.tag(_class='disabled')
        return ctx.tag

    def render_nav_config(self, ctx, data):
        items = [ ['Windows Vista', ['installation/vista/autodetect.html',
                                     'installation/vista/configuration.html',
                                     'installation/vista/finished.html']],
                  ['Windows XP', ['installation/winxp/autodetect.html',
                                  'installation/winxp/configuration.html',
                                  'installation/winxp/finished.html']],
                  ['Windows 2000', ['installation/win2000/autodetect.html',
                                    'installation/win2000/configuration1.html',
                                    'installation/win2000/configuration2.html',
                                    'installation/win2000/configuration3.html',
                                    'installation/win2000/finished.html']],
                  ['Windows Mobile', ['installation/winmobile/configuration.html',
                                      'installation/winmobile/finished.html']],
                  ['Mac OS X 10.5 (Leopard)', ['installation/osx105/autodetect.html',
                                               'installation/osx105/autofinished.html',
                                               'installation/osx105/configuration.html',
                                               'installation/osx105/finished.html']],
                  ['Mac OS X 10.4 (Tiger)', ['installation/osx104/configuration.html',
                                             'installation/osx104/finished.html']],
                  ['Other Operating System', ['installation/other/information.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)

    def render_nav_home(self, ctx, data):
        items = [ ['Welcome', ['welcome.html']],
                  ['Change Password', ['changepassword.html']] ]
        return self.create_nav_list(ctx, items, lambda x: self.build_uri(ctx, x), external=False, disabled=self.nav_disabled)

# --------------------------------------------------------------------------

class UserPopupPage(UserPage, renderers.CommonRenderers, SharedNav):
    """Page layout for logged in end-users, small popups."""

    docFactory = doclib.getDocument('user/userpopuppage.xhtml')

# --------------------------------------------------------------------------

class PlainPage(CommonPage, renderers.CommonRenderers):
    """Page layout for non-configuration pages where no wizard is used.

    Used for instance for login page, password change page, etc.
    """

    docFactory = doclib.getDocument('plainpage.xhtml')
    pagetitle = 'No Title'
    
    def render_page_title(self, ctx, data):
        return self.pagetitle
    
    def macro_content(self, ctx):
        return doclibrary.patternLoader(self.template, 'content')

# --------------------------------------------------------------------------

class LiveCdPage(CommonPage, renderers.CommonRenderers, SharedNav):
    docFactory = doclib.getDocument('livecd/livecdpage.xhtml')
    pagetitle = 'No Title'
    nav_disabled = False
    
    def render_page_title(self, ctx, data):
        return self.pagetitle
    
    def macro_content(self, ctx):
        return doclibrary.patternLoader(self.template, 'content')

    def render_nav_heading_disabled_class(self, ctx, data):
        if self.nav_disabled:
            ctx.tag(_class='disabled')
        return ctx.tag

    def render_nav_home(self, ctx, data):
        items = [ ['Welcome', ['welcome.html']],
                  ['Install / Recovery', ['installlicense.html',
                                          'installtarget.html',
                                          'installconfirm.html',
                                          'installcopying.html',
                                          'installcomplete.html',
                                          'installfailed.html']],
                  ['Format USB Stick', ['formattarget.html',
                                        'formatconfirm.html',
                                        'formatprogress.html',
                                        'formatcomplete.html',
                                        'formatfailed.html']] ]
        return self.create_nav_list(ctx, items, lambda x: '/livecd/%s' % x, external=False, disabled=self.nav_disabled)

    def render_link_maybe(self, ctx, data):
        from codebay.l2tpserver import interfacehelper
        from nevow.flat.ten import flatten

        have_network_connection = False

        try:
            ifname = 'eth0'  # XXX: hardcoded in livecd
            ifaces = interfacehelper.get_interfaces()
            iface = ifaces.get_interface_by_name(ifname)
            if iface is not None:
                addr = iface.get_current_ipv4_address_info()
                if addr is not None:
                    have_network_connection = True
        except:
            _log.exception('livecd cannot determine whether we have a network connection or not')

        if have_network_connection:
            return ctx.tag
        else:
            # XXX: ugly hack, but without this markup would need heavier elements
            txt = flatten(ctx.tag.children)
            return T.strong(_class='cb-strong')[txt]

# --------------------------------------------------------------------------

class RegFile(rend.Page):
    """Serve registry files, cleaning up the lines, adding CR-LFs etc."""
    raw_regfile = None
    
    # XXX: this needs to eat master, mind, etc; it's nice to have reg files
    # in the same hierarchy though
    def __init__(self, original=None, *args, **kw):
        kw.pop('master', None)
        kw.pop('mind', None)
        rend.Page.__init__(self, original, *args, **kw)
    
    def renderHTTP(self, ctx):
        f = None
        regfile = None
        try:
            f = open(self.raw_regfile, 'rb')
            lines = f.readlines()
            f.close()
            f = None

            t = []
            for l in lines:
                l = l.strip()
                l = l + '\x0d\x0a'  # CR-LF
                t.append(l)

            regfile = ''.join(t)
        except:
            if f is not None:
                f.close()
                f = None
            raise
        
        # XXX: expiry
        return uihelpers.ExpiringData(regfile, 'application/octet-stream')
    
# --------------------------------------------------------------------------

class AjaxPage(CommonPage):
    @db.transact()
    def renderHTTP(self, ctx):
        def _prevent_caching(request):
            uihelpers.set_nocache_headers(request)

        @db.transact()
        def _complete(res):
            # XXX: dunno how to do this in practice - we want to return raw data, not html...
            request = inevow.IRequest(ctx)
            _log.debug('ajax request %s successful, returns:\n%s' % (request.URLPath(), res))
            _prevent_caching(request)
            request.setResponseCode(200, 'OK')
            request.write(res)
            request.finish()
            return ''

        @db.transact()
        def _failed(reason):
            request = inevow.IRequest(ctx)
            _log.info('ajax request %s failed, reason: %s' % (request.URLPath(), reason))
            _prevent_caching(request)
            request.setResponseCode(500, 'Internal Server Error')
            request.write('')
            request.finish()
            return reason

        d = defer.maybeDeferred(self.handle_request, ctx)
        d.addCallback(_complete).addErrback(_failed)
        return d
    
    def handle_request(self, ctx):
        raise Exception('unimplemented')

# --------------------------------------------------------------------------

# XXX: relocate?
class AjaxStatus(AjaxPage, renderers.CommonRenderers):
    def handle_request(self, ctx):
        @db.transact()
        def _render(res):
            return self.get_ajax_status()

        # wait until status has (potentially) changed; someone will wake us.
        d = defer.Deferred()
        d.addCallback(_render)
        self.master.add_status_change_waiter(d)
        return d

# --------------------------------------------------------------------------

class CheckPage(rend.Page):
    """Dummy page which can be loaded to check that the web server is up."""

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)
        uihelpers.set_nocache_headers(request)
        request.setResponseCode(200, 'OK')
        request.write('OK')
        request.finish()
        return ''

# --------------------------------------------------------------------------

class GraphPage(CommonPage):
    """Return graph."""

    graphs = { 'usercount':constants.RRDGRAPH_USER_COUNT,
               'sitetositecount':constants.RRDGRAPH_SITETOSITE_COUNT }

    def renderHTTP(self, ctx):
        request = inevow.IRequest(ctx)
        uihelpers.set_nocache_headers(request)

        if not request.args.has_key('name'):
            return rend.NotFound
        name = request.args['name'][0]  # XXX: take first

        if not self.graphs.has_key(name):
            return rend.NotFound
        filename = self.graphs[name]
        
        return uihelpers.UncachedFile(filename, defaultType='image/png')

# --------------------------------------------------------------------------

class RobotsTxtPage(rend.Page):
    """Robots.txt for preventing search engine spiders.

    See:
      * http://www.robotstxt.org/
      * http://www.nextthing.org/archives/2007/03/12/robotstxt-adventure
    """

    def renderHTTP(self, ctx):
        robots = textwrap.dedent("""\
            User-agent: *
            Disallow: /
        """)
        
        # XXX: expiry
        return uihelpers.ExpiringData(robots, 'text/plain')
