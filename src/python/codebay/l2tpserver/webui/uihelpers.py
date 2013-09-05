"""L2TP UI specific helpers."""

import os
import re
import datetime
import textwrap

import formal

from twisted.internet import reactor, protocol, defer, error
from twisted.python.util import mergeFunctionMetadata
from nevow import inevow, url, appserver, tags as T, static
from twisted.names import client, dns
from twisted.mail import smtp
from zope.interface import implements

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver import db
from codebay.l2tpserver import helpers
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import constants
from codebay.l2tpserver import versioninfo
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver.rdfconfig import ns, ns_ui

run_command = runcommand.run_command
_log = logger.get('l2tpserver.webui.uihelpers')

# --------------------------------------------------------------------------

def saferender(default='', silent=False):
    """Decorator for Nevow render_* and macro_*.

    Wraps execution, catches and logs exceptions, and returns a default
    value if rendering fails.  Hopefully minimizes code clutter in
    renderers.
    """

    def _f(f):
        def g(*args, **kw):
            try:
                return f(*args, **kw)
            except:
                if not silent:
                    _log.exception('render/macro failed, returning default value: \'%s\'' % default)
                return default
        
        mergeFunctionMetadata(f, g)
        return g
    return _f

# --------------------------------------------------------------------------

def _set_expiry_headers(ctx, exp_time):
    request = inevow.IRequest(ctx)

    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.21
    expires = datetime.datetime.utcnow() + datetime.timedelta(0, int(exp_time), 0)
    request.setHeader('expires', smtp.rfc822date(expires.utctimetuple()))

    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9
    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.3
    request.setHeader('cache-control', 'max-age=%d' % int(exp_time))

    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9
    pass

def _set_nocache_headers(ctx):
    request = inevow.IRequest(ctx)

    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9
    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.1
    request.setHeader('cache-control', 'no-cache')

    # extra safety
    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.21
    # "HTTP/1.1 clients and caches MUST treat other invalid date formats,
    # especially including the value "0", as in the past (i.e., "already expired")."
    request.setHeader('expires', '-1')
        
    # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9
    request.setHeader('pragma', 'no-cache')

class ExpiringFile(static.File):
    """Nevow static.File but with expiration headers.

    Default expiration time is 1 hour.
    """

    expiration_time = 3600.0

    def renderHTTP(self, ctx):
        _set_expiry_headers(ctx, self.expiration_time)
        return static.File.renderHTTP(self, ctx)

class UncachedFile(static.File):
    """Nevow static.File but without caching."""

    def renderHTTP(self, ctx):
        _set_nocache_headers(ctx)
        return static.File.renderHTTP(self, ctx)
    
class ExpiringData(static.Data):
    """Nevow static.Data but with expiration headers.

    Default expiration time is 1 hour.
    """

    expiration_time = 3600.0

    def renderHTTP(self, ctx):
        _set_expiry_headers(ctx, self.expiration_time)
        return static.Data.renderHTTP(self, ctx)

class UncachedData(static.Data):
    """Nevow static.Data but without caching."""

    def renderHTTP(self, ctx):
        _set_nocache_headers(ctx)
        return static.Data.renderHTTP(self, ctx)

# --------------------------------------------------------------------------

class TimezoneHelper:
    def __init__(self):
        self.tz = None

    def get_timezones(self):
        import pytz

        # XXX: common should be enough for everyone..
        #return pytz.all_timezones
        return pytz.common_timezones

    def set_timezone(self, tzname):
        self.tz = tzname

    def get_timezone(self):
        return self.tz

    def render_datetime(self, dt, show_seconds=False, show_timezone=False):
        if self.tz is None:
            raise Exception('timezone not set')

        fmt = '%Y-%m-%d %H:%M'
        if show_seconds:
            fmt = fmt + ':%S'
        if show_timezone:
            fmt = fmt + ' %Z%z'

        loc_dt = convert_datetime_to_local_datetime(dt, self.tz)
        return loc_dt.strftime(fmt)

    def convert_datetime_to_local_datetime(self, dt, output_naive=False):
        return convert_datetime_to_local_datetime(dt, self.tz, output_naive=output_naive)

def get_timezone_helper():
    """Get a TimezoneHelper initialized with current GUI settings."""

    # XXX: timezone could be user-specific - change the lookup here if this is done

    tz = TimezoneHelper()
    try:
        root = db.get_db().getRoot()
        tzname = root.getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig)).getS(ns_ui.timezone, rdf.String)
        tz.set_timezone(tzname)
    except:
        _log.warning('Cannot figure out timezone - using %s' % constants.DEFAULT_TIMEZONE)
        tz.set_timezone(constants.DEFAULT_TIMEZONE)
        
    return tz

def render_datetime(dt, show_seconds=False, show_timezone=False):
    return get_timezone_helper().render_datetime(dt, show_seconds=show_seconds, show_timezone=show_timezone)

# --------------------------------------------------------------------------

# Shared form for user information pages
class UserInformationForm:
    next_uri = None
    prev_uri = None
    next_label = 'Next'
    prev_label = 'Back'

    def user_information_form_next_uri(self, ctx):
        request = inevow.IRequest(ctx)
        return request.URLPath().sibling(self.next_uri)

    def user_information_form_prev_uri(self, ctx):
        request = inevow.IRequest(ctx)
        return request.URLPath().sibling(self.prev_uri)

    def form_user_information_form(self, ctx):
        def _submitted_next(ctx, form, data):
            fda = formalutils.FormDataAccessor(form, [], ctx)
            fda.finalize_validation()

            request = inevow.IRequest(ctx)
            request.redirect(self.user_information_form_next_uri(ctx))
            request.finish()
            return ''

        def _submitted_prev(ctx, form, data):
            fda = formalutils.FormDataAccessor(form, [], ctx)
            fda.finalize_validation()

            request = inevow.IRequest(ctx)
            request.redirect(self.user_information_form_prev_uri(ctx))
            request.finish()
            return ''

        form = formal.Form()
        sg = formalutils.SubmitFieldGroup('buttons')
        if self.prev_uri is not None:
            form.addAction(_submitted_prev, name='submitprev', validate=False)
            sg.add(formalutils.SubmitField('submitprev', formal.String(), label=self.prev_label))
        if self.next_uri is not None:
            form.addAction(_submitted_next, name='submitnext', validate=False)
            sg.add(formalutils.SubmitField('submitnext', formal.String(), label=self.next_label))
        form.add(sg)
        return form

# --------------------------------------------------------------------------

class RadauthuserProcessProtocol(protocol.ProcessProtocol):
    def __init__(self, callback):
        _log.info('RadauthuserProcessProtocol: __init__')
        self.callback = callback
        self.stdout = ''
        self.badresp_re = re.compile(r'^BADRESP$')
        self.error_re = re.compile(r'^ERROR$')
        self.ok_re = re.compile(r'^OK$')
        self.timeout_re = re.compile(r'^TIMEOUT$')
        self.unknown_re = re.compile(r'^UNKNOWN$')
        self.avp_re = re.compile(r'^AVP:\s(.*?):(.*?):(.*?):(.*?):(.*?)\s*$')
        
    def outReceived(self, data):
        _log.info('RadauthuserProcessProtocol: outReceived: %s' % data)
        self.stdout += data

    def processEnded(self, reason):
        _log.info('RadauthuserProcessProtocol: processEnded: %s' % reason)
        auth_ok = False
        admin_privs = False
        for line in self.stdout.split('\n'):
            line = line.strip()
            try:
                m = self.badresp_re.match(line)
                if m is not None:
                    pass
                m = self.error_re.match(line)
                if m is not None:
                    pass
                m = self.ok_re.match(line)
                if m is not None:
                    auth_ok = True
                m = self.timeout_re.match(line)
                if m is not None:
                    pass
                m = self.unknown_re.match(line)
                if m is not None:
                    pass
                m = self.avp_re.match(line)
                if m is not None:
                    avp_name, avp_attribute, avp_type, avp_lvalue, avp_strvalue = m.groups()
                    dec_name = avp_name.decode('hex')
                    dec_attribute = avp_attribute.decode('hex')
                    dec_type = avp_type.decode('hex')
                    dec_lvalue = avp_lvalue.decode('hex')
                    dec_strvalue = avp_strvalue.decode('hex')

                    _log.debug('parsed avp: name=%s, attribute=%s, type=%s, lvalue=%s, strvalue=%s' % (dec_name, dec_attribute, dec_type, dec_lvalue, dec_strvalue))

                    # NB: we're dependent on the radiusclient dictionary to get this name
                    # when parsing a vendor specific extension (see dictionary.vpnease).
                    if dec_name == 'VE-User-Administrator-Privileges':
                        if dec_lvalue == '\x00\x00\x00\x01':  # dec 1
                            admin_privs = True
                        
            except:
                _log.exception('failed to parse radauthuser output line: %s' % line)
                
        self.callback(auth_ok, admin_privs)

def radius_authenticate(username, password):
    d = defer.Deferred()
    
    def _auth_done(auth_ok, admin_privs):
        _log.debug('radius_authenticate: _auth_done -> %s, admin %s' % (auth_ok, admin_privs))
        d.callback((auth_ok, admin_privs))
    
    proc = RadauthuserProcessProtocol(_auth_done)
    cmd = constants.CMD_RADAUTHUSER
    args = [cmd, username, password]
    reactor.spawnProcess(proc, executable=cmd, args=args, usePTY=1)

    return d

# --------------------------------------------------------------------------

class UserAgentHelpers:
    """Helpers to deduce platform from User-Agent.

    This class attempts to produce a good guess of the platform (e.g. Windows
    XP, Windows Vista, x86 vs x64) based on the User-Agent string.  This is
    fundamentally impossible, because browsers are free to fill User-Agent as
    they please.  We try to work as well as possible with IE and FF.

    See:
      * http://en.wikipedia.org/wiki/User_agent
      * http://www.user-agents.org/
      * http://msdn2.microsoft.com/en-us/library/ms537503.aspx
      * http://blogs.msdn.com/astebner/archive/2007/02/05/how-to-workaround-install-problems-with-msn-remote-record-on-windows-vista-x64.aspx
      * http://forums.mozillazine.org/viewtopic.php?t=563404

    Safari / OSX:
      * http://developer.apple.com/internet/safari/faq.html
      * http://developer.apple.com/internet/safari/uamatrix.html

    In short, it seems that OSX version cannot be detected based on
    User-Agent string.  Hence, no selection is applied for now.
    """
    
    def detect_platform_from_user_agent(self, useragent):
        platform = None
        architecture = None

        if ('Windows NT 6.0' in useragent) or ('Windows Vista' in useragent):
            platform = 'vista'
            if ('x64' in useragent) or ('Win64' in useragent) or ('WOW64' in useragent):
                # WOW64 = 32-bit browser in a 64-bit platform; we still detect as 64-bit OS
                architecture = 'x64'
            else:
                architecture = 'x86'
        elif ('Windows NT 5.1' in useragent) or ('Windows XP' in useragent):
            platform = 'winxp'

            # this check is guesswork
            if ('x64' in useragent) or ('Win64' in useragent) or ('WOW64' in useragent):
                # WOW64 = 32-bit browser in a 64-bit platform; we still detect as 64-bit OS
                architecture = 'x64'
            else:
                architecture = 'x86'
        elif 'Windows NT 5.2' in useragent:
            # winxp on x64 seems to use Windows NT 5.2 (unfortunately, so does Windows Server 2003)
            platform = 'winxp'
            architecture = 'x64'
        elif ('Windows NT 5.0' in useragent) or ('Windows NT 5.01' in useragent) or ('Windows 2000' in useragent):
            # win2k does not have an x64 version
            platform = 'win2k'
            architecture = 'x86'

        return {'platform': platform, 'architecture': architecture}

    @saferender()
    def render_platform_from_user_agent(self, ctx, data):
        request = inevow.IRequest(ctx)
        useragent = request.getHeader('User-Agent')
        return self.detect_platform_from_user_agent(useragent)

    def get_platform_and_architecture_dropdown(self, useragent=None):
        options = [
            ('vista-32', 'Windows Vista (32-bit)'),
            ('vista-64', 'Windows Vista (64-bit)'),
            ('winxp-32', 'Windows XP (32-bit)'),
            ('winxp-64', 'Windows XP (64-bit)'),
            ('win2k-32', 'Windows 2000 (32-bit)'),
#           ('osx105-any', 'Mac Os X 10.5 (Leopard)'),
#           ('osx104-any', 'Mac Os X 10.4 (Tiger)'),
            ]

        selected = ''
        if useragent is not None:
            pi = self.detect_platform_from_user_agent(useragent)
            tmp = (pi['platform'], pi['architecture'])
            for platform, architecture, selvalue in [
                ('winxp', 'x86', 'winxp-32'),
                ('winxp', 'x64', 'winxp-64'),
                ('vista', 'x86', 'vista-32'),
                ('vista', 'x64', 'vista-64'),
                ('win2k', 'x86', 'win2k-32'),
                ]:
                if tmp == (platform, architecture):
                    selected = selvalue
                    break

        fld = formalutils.Field('platform_and_architecture', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=options),
                                label='Operating system')

        return fld, selected

# --------------------------------------------------------------------------

# NB: requires UserAgentHelpers and CommonPage
class AutoconfigureHelpers:
    def form_autoconfigure(self, ctx):
        request = inevow.IRequest(ctx)
        useragent = request.getHeader('User-Agent')
        if useragent is None:
            useragent = ''

        form = formal.Form()
        g = formalutils.CollapsibleGroup('platform', label='Autoconfiguration')
        dropdown, selected = self.get_platform_and_architecture_dropdown(useragent)
        g.add(dropdown)
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Autoconfigure'))
        g.add(sg)
        form.add(g)
        form.addAction(self.submitted_autoconfigure, name='submit', validate=False)

        fda = formalutils.FormDataAccessor(form, [], ctx)
        fda = fda.descend('platform')
        fda['platform_and_architecture'] = selected

        return form
    
    def render_form_autoconfigure_onsubmit_adder(self, ctx, data):
        # Javascript code to add an onsubmit handler
        #
        # Quite dirty approach:
        #   * Followup page depends on selected value
        #   * Form and input names are fixed, based on prior Nevow knowledge

        jscode = textwrap.dedent("""
            <script type="text/javascript">
                // <![CDATA[
                function _autoconfig_onsubmit() {
                    var n = document.getElementById("autoconfigure-platform-platform_and_architecture");
                    if ((n == null) || (n == undefined)) {
                        return true;
                    }
                    var plat = n.value;
                    var popup_uri = null;
                    if (plat == "win2k-32") {
                        popup_uri = "%(popup_win2k)s";
                    } else if ((plat == "winxp-32") || (plat == "winxp-64")) {
                        popup_uri = "%(popup_winxp)s";
                    } else if ((plat == "vista-32") || (plat == "vista-64")) {
                        popup_uri = "%(popup_vista)s";
                    } else if (plat == "osx104-any") {
                        popup_uri = "%(popup_osx104)s";
                    } else if (plat == "osx105-any") {
                        popup_uri = "%(popup_osx105)s";
                    } else {
                        return true;
                    }

                    if (popup_uri != null) {
                        window.open(popup_uri,
                                    "vpneasepopup",
                                    "left=20,right=20,width=425,height=625,location=no,scrollbars=yes,toolbar=no")
                    }
                    return true;
                }
                
                // addDOMLoadEvent() requires commonutils.js to be loaded
                addDOMLoadEvent(function() {
                    var frm = document.getElementById("autoconfigure");
                    if (frm) {
                        if (frm.attachEvent) { // IE
                            frm.attachEvent("onsubmit", _autoconfig_onsubmit);
                        } else if (frm.addEventListener) { // FF etc
                            frm.addEventListener("submit", _autoconfig_onsubmit, true);  // true = capture instead of bubble phase
                        } else {
                            ;
                        }
                    }
                });
                // ]]>
            </script>
        """) % { 'popup_win2k': self.build_uri(ctx, 'installation/win2000/autodetectdone.html'),
                 'popup_winxp': self.build_uri(ctx, 'installation/winxp/autodetectdone.html'),
                 'popup_vista': self.build_uri(ctx, 'installation/vista/autodetectdone.html'),
                 'popup_osx104': self.build_uri(ctx, 'installation/osx104/autodetectdone.html'),
                 'popup_osx105': self.build_uri(ctx, 'installation/osx105/autodetectdone.html') }

        form_onsubmit_adder = T.raw(jscode)

        return form_onsubmit_adder
    
    def submitted_autoconfigure(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)
        fda = fda.descend('platform')
        selected = ''
        if fda.has_key('platform_and_architecture'):
            selected = fda['platform_and_architecture']
        _log.info('submitted_autoconfigure: selected=%s' % selected)

        fda.finalize_validation()

        # XXX: it's not the cleanest possible option to have the followup URI hardcoded
        # here.  However, because this autoconfigure dropdown is used on the 'welcome'
        # page, the followup URI is dependent on the actual selection; this means it
        # cannot be easily defined by the subclass.
        
        selected_filename = None
        followup_uri = None
        for val, filename, followup in [ ('winxp-32', 'vpnease_autoconfigure_winxp32.exe', 'installation/winxp/autodetectdone.html'),
                                         ('winxp-64', 'vpnease_autoconfigure_winxp64.exe', 'installation/winxp/autodetectdone.html'),
                                         ('vista-32', 'vpnease_autoconfigure_vista32.exe', 'installation/vista/autodetectdone.html'),
                                         ('vista-64', 'vpnease_autoconfigure_vista64.exe', 'installation/vista/autodetectdone.html'),
                                         ('win2k-32', 'vpnease_autoconfigure_win2k32.exe', 'installation/win2k/autodetectdone.html'),
                                         ('osx104-any', 'vpnease_autoconfigure_macosx.networkConnect', 'installation/osx104/autodetectdone.html'),
                                         ('osx105-any', 'vpnease_autoconfigure_macosx.networkConnect', 'installation/osx105/autodetectdone.html') ]:
            if selected == val:
                selected_filename = filename
                followup_uri = followup
                break

        _log.info('submitted_autoconfigure: selected_filename=%s, followup_uri=%s' % (selected_filename, followup_uri))

        if selected_filename is not None:
            request = inevow.IRequest(ctx)

            # unused now, for delayed load
            new_uri = self.build_uri(ctx, followup_uri)
            new_uri = new_uri.add('filename', selected_filename)

            file_uri = self.build_uri(ctx, selected_filename)
            request.redirect(file_uri)
            request.finish()
            return ''

    def _server_ip_ok(self, ctx):
        try:
            request = inevow.IRequest(ctx)
            server_address = str(request.getRequestHostname())
            t = datatypes.IPv4Address.fromString(server_address)
            return True
        except:  # XXX: wide catch
            return False

    def render_autoconfigure_server_ip_ok(self, ctx, data):
        if self._server_ip_ok(ctx):
            return ctx.tag
        else:
            return ''

    def render_autoconfigure_server_ip_not_ok(self, ctx, data):
        if not self._server_ip_ok(ctx):
            return ctx.tag
        else:
            return ''
    
    # For delayed load, unused now
    @saferender()
    def render_autoconfigure_file_uri(self, ctx, data):
        request = inevow.IRequest(ctx)
        args = request.args
        if args.has_key('filename'):
            file_uri = self.build_uri(ctx, '%s' % args['filename'][0])
            return file_uri
        return ''
    
    # For delayed load, unused now
    @saferender()
    def render_autoconfigure_delayed_load(self, ctx, data):
        # http://en.wikipedia.org/wiki/Meta_refresh
        request = inevow.IRequest(ctx)
        args = request.args
        if not args.has_key('filename'):
            return ''
        
        # XXX: sanitize filename

        file_uri = self.build_uri(ctx, '%s' % args['filename'][0])
        delay = 3

        if False:
            # META REFRESH is not suggested because AFAIK there is no easy
            # way to cancel it if Javascript is disabled.  META REFRESH is
            # disabled in some IE security levels and even when it isn't,
            # it produces a barely noticeable "popup blocker" yellow bar
            # instead of asking to save.

            # NB: no escape needed, Nevow handles it
            res = T.meta(**{'http-equiv': "refresh",
                            'content': "%d;url=%s" % (delay, file_uri)})
            return res
        else:
            # Javascript; if no Javascript, user needs to click manually.
            # Probably best compromise

            # XXX: CDATA hack?
            jscode = textwrap.dedent("""
                <script type="text/javascript">
                    // <![CDATA[
                    // addDOMLoadEvent() requires commonutils.js to be loaded
                    addDOMLoadEvent(function() {
                        setTimeout(function() {
                            window.location = "%(uri)s";
                        }, %(delay)d * 1000);
                    });
                    // ]]>
                </script>
            """) % { 'delay': delay,
                     'uri': file_uri }

            res = T.raw(jscode)
            return res
    
# --------------------------------------------------------------------------

class RewritingBinaryResource:

    implements(inevow.IResource)

    """Dynamically re-written binary resource.

    This is used mainly for rewriting EXE files for Windows clients, where
    parameterization is done for each user into the EXE file directly.

    See:
      * http://download.microsoft.com/download/9/c/5/9c5b2167-8017-4bae-9fde-d599bac8184a/pecoff_v8.doc
      * http://msdn.microsoft.com/msdnmag/issues/02/02/PE/print.asp
      * http://msdn.microsoft.com/msdnmag/issues/02/03/PE2/print.asp
      * http://forums.microsoft.com/MSDN/ShowPost.aspx?PostID=1684195&SiteID=1

    Note: if you edit a binary EXE file using xemacs, it will become corrupt
    for some reason even if you just change one character; even if you do it
    in hexl-mode.  This may have something to do with CR-LF line endings,
    but that's just a wild stab in the dark.
    """

    def __init__(self, data, paramdict):
        pbeg, pend = self._find_parameter_area(data)
        if pbeg is None or pend is None:
            raise Exception('cannot find parameter block for injection')
        _log.info('patching parameters into area [%d,%d[ (%d bytes)' % (pbeg, pend, pend-pbeg))
        self.patched_data = self._inject_parameters(data, pbeg, pend, paramdict)

    def _find_parameter_area(self, t):
        marker1 = '##### BEGIN PARAMETER BLOCK #####'
        marker2 = '##### END PARAMETER BLOCK #####'

        idx1 = t.find(marker1)
        idx2 = t.find(marker2)
        ridx1 = t.rfind(marker1)
        ridx2 = t.rfind(marker2)
    
        pbeg = None
        pend = None
        if (idx1 > 0) and (idx2 > 0):
            if (idx2 > idx1) and (idx1 == ridx1) and (idx2 == ridx2):
                pbeg = idx1 + len(marker1)
                pend = idx2
                plen = pend - pbeg
                if plen > 0:
                    return pbeg, pend

        return None, None

    def _inject_parameters(self, t, pbeg, pend, params):
        plen = pend - pbeg
    
        keys = params.keys()
        keys.sort()
        param_str = ''
        for k in keys:
            param_str += '%s\x00%s\x00' % (k, params[k])
        param_str += '\x00'

        param_len = len(param_str)
        if param_len > plen:
            raise Exception('parameters do not find into parameter area')

        new_t = t[:pbeg] + param_str + ('.' * (plen - param_len)) + t[pend:]
        return new_t

    def locateChild(self, ctx, segments):
        return appserver.NotFound

    def renderHTTP(self, ctx):
        # IE is a bit picky about executing EXE files downloaded from the web.
        # See:
        #   * http://technet2.microsoft.com/windowsserver/en/library/e5a730ee-a68b-4789-8419-4de4c3c7950d1033.mspx?mfr=true
        #   * http://msdn2.microsoft.com/en-us/library/ms537641.aspx
        #   * http://support.microsoft.com/kb/323308
        #   * http://support.microsoft.com/kb/815313/
        #
        # We're doing these things here to make IE execute the file:
        #   * Use the 'application/x-msdos-program' content-type (this is used by
        #     putty download page; sometimes 'application/octet-stream' is used,
        #     don't know which one is better).
        #   * Add a 'Content-disposition=attachment' header (see the Technet
        #     articles above).
        #   * Do *not* add cache control headers (such as Cache-Control: no-cache,
        #     Pragma: no-cache or Expires header; see KB articles).  If any of them
        #     are present, the EXE download will fail with at least IE6 and most
        #     likely other IE versions too.
        #
        # It's a bit nasty that we don't prevent caching of the downloaded EXE:
        # the EXE contains sensitive information (like the pre-shared key) and
        # we'd ideally not cache it.  However, caching has no functional impact
        # otherwise in practice.  First, IE6 does not seem to cache the EXE anyway
        # (or at the very least, it will re-download it if requested again).
        # Second, even if it did, the URI contains a session key which means that
        # for every user login, a separate cached entry is created - which in turn
        # means that the user will receive a properly customized EXE anyway in
        # all but extreme corner cases.
        
        request = inevow.IRequest(ctx)
        request.setHeader('content-type', 'application/x-msdos-program')
        request.setHeader('content-disposition', 'attachment')

        # NB: It is critical *not* to prevent caching; IE + SSL + caching prevention
        # means that the EXE will not download and run correctly!
        #request.setHeader('Cache-Control', 'no-cache')
        #request.setHeader('Pragma', 'no-cache')
        #request.setHeader('Expires', '-1')

        # Set to expire in 1h to minimize caching impact
        _set_expiry_headers(ctx, 3600.0)

        if request.method == "HEAD":
            return ''

        return self.patched_data

# --------------------------------------------------------------------------

def ui_truncate(str, nchars):
    """Truncate a string to a maximum of nchars characters.

    If truncation occurs, end string with three dots.
    """

    if len(str) > nchars:
        return str[:nchars-4] + " ..."
    return str
        
def convert_datetime_to_local_datetime(dt, tzname, output_naive=False):
    """Convert a datetime to local timezone.

    If datetime is naive, it is assumed to be UTC.
    """
    import pytz

    utc = pytz.timezone('UTC')
    local = pytz.timezone(tzname)

    # if datetime is naive, assume it is actually utc
    if dt.tzname() is None:
        dt = dt.replace(tzinfo=utc)

    # get local version
    loc_dt = dt.astimezone(local)

    # convert to naive if requested
    if output_naive:
        loc_dt = loc_dt.replace(tzinfo=None)

    return loc_dt

def convert_datetime_to_utc_datetime(dt, output_naive=True):
    import pytz

    utc = pytz.timezone('UTC')

    # if datetime is naive, assume it is actually utc
    if dt.tzname() is None:
        dt = dt.replace(tzinfo=utc)

    dt = dt.astimezone(utc)

    if output_naive:
        dt = dt.replace(tzinfo=None)

    return dt
    
def interface_options():
    """Get a list of physical network interfaces for web UI dropdown."""
    if_list = []

    from codebay.l2tpserver import interfacehelper
    ifaces = interfacehelper.get_all_interfaces()

    for i in ifaces.get_interface_list():
        if not i.is_ethernet_device():
            continue

        ni = i.identify_device()
        if ni.mac is not None:
            t = ni.device_string
            if t is None:
                t = '(unknown device)'

            if ni.vmware:
                t = 'VMware (%s)' % t
            # XXX: virtual pc, virtual server
            # XXX: parallels

            devicestring = ui_truncate(t, 40)
            if_list.append((i.get_device_name(), i.get_device_name() + ': ' + devicestring))

    # sort by device name; this will sort badly for eth10 and higher, but that's a remote corner case
    def _cmp(a, b):
        a1, a2 = a
        b1, b2 = b
        return cmp(a1, b1)
    if_list.sort(cmp=_cmp)
    
    if len(if_list) == 0:
        if_list.append(('', 'No network interfaces found'))
        
    return if_list

def _transfer_rate_conversion(bytes_per_second):
    bits_per_second = bytes_per_second * 8.0

    if bits_per_second < (1000.0 * 1000.0):
        s1 = '%.1f kbps' % (bits_per_second / 1000.0)
    elif bits_per_second < (1000.0 * 1000.0 * 1000.0):
        s1 = '%.1f Mbps' % (bits_per_second / (1000.0 * 1000.0))
    else:
        s1 = '%.1f Gbps' % (bits_per_second / (1000.0 * 1000.0 * 1000.0))

    if bytes_per_second < (1024.0 * 1024.0):
        s2 = '%.1f KiB/s' % (bytes_per_second / 1024.0)
    elif bytes_per_second < (1024.0 * 1024.0 * 1024.0):
        s2 = '%.1f MiB/s' % (bytes_per_second / (1024.0 * 1024.0))
    else:
        s2 = '%.1f GiB/s' % (bytes_per_second / (1024.0 * 1024.0 * 1024.0))
        
    return s1, s2

def _transfer_amount_conversion(bytes):
    bits = bytes * 8.0

    if bits < (1000.0 * 1000.0):
        s1 = '%.1f kb' % (bits / 1000.0)
    elif bits < (1000.0 * 1000.0 * 1000.0):
        s1 = '%.1f Mb' % (bits / (1000.0 * 1000.0))
    else:
        s1 = '%.1f Gb' % (bits / (1000.0 * 1000.0 * 1000.0))

    if bytes < (1024.0 * 1024.0):
        s2 = '%.1f KiB' % (bytes / 1024.0)
    elif bytes < (1024.0 * 1024.0 * 1024.0):
        s2 = '%.1f MiB' % (bytes / (1024.0 * 1024.0))
    else:
        s2 = '%.1f GiB' % (bytes / (1024.0 * 1024.0 * 1024.0))
        
    return s1, s2

def render_transfer_rate_bits(bytes_per_second):
    s1, s2 = _transfer_rate_conversion(bytes_per_second)
    return s1

def render_transfer_rate_bytes(bytes_per_second):
    s1, s2 = _transfer_rate_conversion(bytes_per_second)
    return s2

def render_transfer_rate(bytes_per_second):
    """Render a transfer rate in a human readable format."""
    s1, s2 = _transfer_rate_conversion(bytes_per_second)
    return '%s (%s)' % (s1, s2)

def render_transfer_amount_bits(bytes):
    s1, s2 = _transfer_amount_conversion(bytes)
    return s1

def render_transfer_amount_bytes(bytes):
    s1, s2 = _transfer_amount_conversion(bytes)
    return s2

def render_transfer_amount(bytes):
    """Render a transfer rate in a human readable format."""
    s1, s2 = _transfer_amount_conversion(bytes)
    return '%s (%s)' % (s1, s2)

def render_timedelta(td):
    """Render a timedelta in a concise human readable form."""
    ZERO = datetime.timedelta(0, 0, 0)
    ONE_MINUTE = datetime.timedelta(0, 60, 0)
    ONE_HOUR = datetime.timedelta(0, 60*60, 0)
    ONE_DAY = datetime.timedelta(0, 24*60*60, 0)
    ONE_WEEK = datetime.timedelta(0, 7*24*60*60, 0)

    sign_str = ''
    if td < ZERO:
        td = -td
        sign_str = '-'
        
    full_seconds = (td.days * 24*60*60) + td.seconds

    res = ''
    if False:
        # XXX: old style
        if td < ONE_MINUTE:
            res = '%d seconds' % full_seconds
        elif td < ONE_HOUR:
            res = '%.1f minutes' % (full_seconds / 60.0)
        elif td < ONE_DAY:
            res = '%.1f hours' % (full_seconds / (60.0*60.0))
        elif td < ONE_WEEK:
            res = '%.1f days' % (full_seconds / (24.0*60.0*60.0))
        else:
            res = '%.1f weeks' % (full_seconds / (7*24.0*60.0*60.0))
    else:
        if td < ONE_HOUR:
            res = '%dmin %ds' % (full_seconds / 60, full_seconds % 60)
        elif td < ONE_DAY:
            full_minutes = full_seconds / 60
            res = '%dh %dmin' % (full_minutes / 60, full_minutes % 60)
        else:
            full_hours = full_seconds / (60*60)
            res = '%dd %dh' % (full_hours / 24, full_hours % 24)
        
    return '%s%s' % (sign_str, res)


def _write_shutdown_markers(skip_update, force_update, force_fsck):
    try:
        if skip_update:
            helpers.write_datetime_marker_file(constants.UPDATE_SKIP_MARKER_FILE)
        if force_update:
            helpers.write_datetime_marker_file(constants.UPDATE_FORCE_MARKER_FILE)
        if force_fsck:
            helpers.write_datetime_marker_file(constants.FORCE_FSCK_MARKER_FILE)
            if os.path.exists(constants.FASTBOOT_MARKER_FILE):
                os.unlink(constants.FASTBOOT_MARKER_FILE)
    except:
        _log.exception('failed to write shutdown marker files')

def _run_shutdown(msg, action, delay):
    def _do_shutdown():
        p = reactor.spawnProcess(protocol.ProcessProtocol(),
                                 executable=constants.CMD_SHUTDOWN,
                                 args=[constants.CMD_SHUTDOWN, action, 'now', msg],
                                 usePTY=1)
    reactor.callLater(delay, _do_shutdown)

def ui_shutdown(msg, skip_update=False, force_update=False, force_fsck=False, delay=0.0):
    """Action for UI-issued shutdown."""

    _write_shutdown_markers(skip_update, force_update, force_fsck)
    _run_shutdown(msg, '-h', delay)

def ui_reboot(msg, skip_update=False, force_update=False, force_fsck=False, delay=0.0):
    """Action for UI-issued reboot (watchdog, admin clicks button)."""

    _write_shutdown_markers(skip_update, force_update, force_fsck)
    _run_shutdown(msg, '-r', delay)


# Avoids the use of an in-memory store because it is currently way too slow, see #666.
def _export_rdf_database_helper(filename=None, return_string=False, remove_status=True):
    fname1 = constants.WEBUI_TEMPORARY_SQLITE_DATABASE
    fname2 = '%s-journal' % fname1

    def _delete_files():
        for i in [ fname1, fname2 ]:
            if os.path.exists(i):
                os.unlink(i)

    try:
        _delete_files()
    except:
        _log.exception('failed to delete webui temporary sqlite database file(s)')
    
    temp_db = None
    try:
        root = helpers.get_db_root()
        model = root.model          # XXX: cleaner way?

        # First, create an in-memory string export (large, but no larger than a temp file)
        @db.transact(database=model)
        def _f1():
            return model.toString(name='rdfxml')     # rdf database as a string (may be a tad large)
        tmpstr = _f1()

        # Second, load the string, prune, and write out to exported RDFXML file (or string)
        temp_db = rdf.Database.create(fname1)
        @db.transact(database=temp_db)
        def _f2():
            temp_db.loadString(tmpstr)
    
            root = temp_db.getNodeByUri(ns.l2tpGlobalRoot, rdf.Type(ns.L2tpGlobalRoot))
            try:
                if remove_status:
                    l2tp_status = root.getS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))
                    activepppdevs = l2tp_status.setS(ns.pppDevices, rdf.Type(ns.PppDevices))
                    retiredpppdevs_compat = l2tp_status.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices)) # compatibility with 1.0
                    global_status = root.getS(ns.globalStatus, rdf.Type(ns.GlobalStatus))
                    retiredpppdevs = global_status.setS(ns.retiredPppDevices, rdf.Type(ns.RetiredPppDevices))
            except:
                _log.exception('failed when pruning ppp devices')
            temp_db.prune(root)

            if return_string:
                return temp_db.toString(name='rdfxml')
            else:
                temp_db.toFile(filename, name='rdfxml')
                return None
            # db is closed in 'finally' clause
        return _f2()
    finally:
        if temp_db is not None:
            try:
                temp_db.close()
                temp_db = None
            except:
                _log.exception('failed to close temporary database')
        try:
            _delete_files()
        except:
            _log.exception('failed to close temporary files')

def export_rdf_database_to_file(filename, remove_status=True):
    return _export_rdf_database_helper(filename=filename, return_string=False, remove_status=remove_status)

def export_rdf_database(remove_status=True):
    return _export_rdf_database_helper(filename=None, return_string=True, remove_status=remove_status)

def get_user_password_dict():
    """Specific helper for user config pages.

    Returns a mapping from username to three-element list containing
    plain password, md5 password, nthash password.  If any are missing,
    Nones are retured in their place.  In the current implementation
    we're expecting None for plain password, non-None for hashed.
    """
    res = {}
    if helpers.get_ui_config().hasS(ns_ui.users):
        for u in helpers.get_ui_config().getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User))):
            try:
                password = None
                if u.hasS(ns_ui.password):
                    password = u.getS(ns_ui.password, rdf.String)
                    
                password_md5 = None
                if u.hasS(ns_ui.passwordMd5):
                    password_md5 = u.getS(ns_ui.passwordMd5, rdf.String)
                    
                password_nt = None
                if u.hasS(ns_ui.passwordNtHash):
                    password_nt = u.getS(ns_ui.passwordNtHash, rdf.String)
                
                res[u.getS(ns_ui.username, rdf.String)] = [password, password_md5, password_nt]
            except:
                _log.exception('failed to get username/password hashes for dict, user %s, ignoring' % u)

    return res

def filter_users(filters=[]):
    res = []
    try:
        for u in helpers.get_ui_config().getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User))):
            user_ok = True
            for f in filters:
                try:
                    if not f(u):
                        user_ok = False
                except:
                    user_ok = False

            if user_ok:
                res.append(u)
    except:
        res = []

    return res

def filter_s2s_connections(filters=[]):
    res = []
    try:
        for u in helpers.get_ui_config().getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection))):
            s2s_ok = True
            for f in filters:
                try:
                    if not f(u):
                        s2s_ok = False
                except:
                    s2s_ok = False

            if s2s_ok:
                res.append(u)
    except:
        res = []

    return res

def find_user(username):
    def _checker(u):
        return u.getS(ns_ui.username, rdf.String) == username

    res = filter_users([_checker])
    if len(res) == 0:
        return None
    elif len(res) == 1:
        return res[0]
    else:
        raise Exception('multiple users of the same name')

def find_s2s_connection(username):
    def _checker(u):
        return u.getS(ns_ui.username, rdf.String) == username

    res = filter_s2s_connections([_checker])
    if len(res) == 0:
        return None
    elif len(res) == 1:
        return res[0]
    else:
        raise Exception('multiple s2s connections of the same name')

def _get_webui_password_checker(username, password):
    password_md5 = helpers.compute_password_md5(password).encode('hex').upper()
    password_nt = helpers.compute_password_nt_hash(password).encode('hex').upper()
    
    def _f(u):
        if u.getS(ns_ui.username, rdf.String) != username:
            return False
        if u.hasS(ns_ui.password) and u.getS(ns_ui.password, rdf.String) == password:
            return True
        if u.hasS(ns_ui.passwordMd5) and u.getS(ns_ui.passwordMd5, rdf.String) == password_md5:
            return True
        if u.hasS(ns_ui.passwordNtHash) and u.getS(ns_ui.passwordNtHash, rdf.String) == password_nt:
            return True
        return False

    return _f

def check_username_and_password(username, password, filters=[]):
    res = filter_users([_get_webui_password_checker(username, password)] + filters)
    if len(res) == 0:
        return False
    elif len(res) == 1:
        return True
    else:
        raise Exception('multiple matching users')

# NB: deferred because of (possible) RADIUS lookup
def check_username_and_password_local_and_radius(username, password, filters=[], radius=False, radius_require_admin=False):
    try:
        if check_username_and_password(username, password, filters):
            return defer.succeed(True)
    except:
        _log.exception('local user authentication failed, skipping')

    if not radius:
        return defer.succeed(False)

    def _rad_complete(res):
        auth_ok, admin_privs = res

        retval = False
        if auth_ok:
            if radius_require_admin and (not admin_privs):
                retval = False
            else:
                retval = True

        _log.info('web ui radius authentication for user %s -> (%s,%s) -> %s' % (username, auth_ok, admin_privs, retval))
        return retval

    d = radius_authenticate(username, password)
    d.addCallback(_rad_complete)
    return d

def change_user_password(username, new_password):
    u = find_user(username)
    if u is None:
        raise Exception('user %s cannot be found' % username)
    set_user_password_hashes(u, new_password)


def get_user_fixed_ip(username):
    try:
        user = find_user(username)
        if user.hasS(ns_ui.fixedIp):
            return user.getS(ns_ui.fixedIp, rdf.IPv4Address).toString()
        else:
            return None
    except:
        _log.exception('cannot check whether user has fixed ip')
        return None
    
def build_uri(ctx, suffix):
    """Build a new URI, relative to this realm.

    For instance, with suffix 'status/main.html' would build an URI like
    'http://.../admin/<session>/status/main.html.
    """

    # start from remember URL and build final URL
    #   - remove query parameters - including __start_session__
    #   - child('') is required to add slash after session ID; otherwise
    #     click() will replace the session ID.
    request = inevow.IRequest(ctx)
    uri = url.URL.fromString(request.getRootURL() + '/')
    uri = uri.clear().child('').click(suffix)
    return uri

def _reconfigure_and_restart_page(master, ctx, followup_uri=None, quick=False):
    # redirect
    request = inevow.IRequest(ctx)
    uri = build_uri(ctx, 'activateconfiguration.html')
    if quick:
        uri = uri.add('quick', '1')
    if followup_uri is not None:
        uri = uri.add('followupuri', followup_uri)
    _log.debug('reconfigure_and_restart_page: redirecting to %s' % uri)
    request.redirect(uri)
    request.finish()
    return ''

def reconfigure_and_restart_page(master, ctx, followup_uri=None):
    return _reconfigure_and_restart_page(master, ctx, followup_uri=followup_uri, quick=False)

def reconfigure_page(master, ctx, followup_uri=None):
    return _reconfigure_and_restart_page(master, ctx, followup_uri=followup_uri, quick=True)

def set_nocache_headers(request):
    # XXX: use this for other than static stuff as well
    # Try to prevent all caching of ajax pages
    request.setHeader('Cache-Control', 'no-cache')
    request.setHeader('Pragma', 'no-cache')
    request.setHeader('Expires', '-1')

# XXX: do we need to reinstantiate the resolved when e.g. /etc/resolv.conf changes?
_resolver = None
def _get_resolver():
    global _resolver

    if _resolver is None:
        _resolver = client.createResolver()   # XXX: parameters here, e.g. timeout?

    return _resolver
    
def reverse_dns_lookup(addr):
    global _resolver
    _get_resolver()
    
    @db.transact()
    def _success((ans, auth, add), name):
        _log.info('reverse dns lookup success for %s' % name)
        
        # XXX: this is not too intuitive, but works; read the twisted code
        answers = ans + auth + add
        for a in answers:
            if a.type == dns.PTR and a.name.name == name:
                return a.payload.name.name
        raise error.DNSLookupError(name)

    # ensure we get an IPv4Address
    if isinstance(addr, (str, unicode)):
        addr = datatypes.IPv4Address.fromString(str(addr))
        
    t = addr.toIntegerList()
    name = '%d.%d.%d.%d.in-addr.arpa' % (t[3], t[2], t[1], t[0])
    d = _resolver.lookupPointer(name).addCallback(_success, name)
    return d  # deferred

def dns_lookup(hostname):
    global _resolver
    _get_resolver()

    @db.transact()
    def _success((ans, auth, add), hostname):
        _log.info('dns lookup success for %s' % hostname)

        # XXX: this is not too intuitive, but works; read the twisted code
        answers = ans + auth + add
        _log.info('answers: %s' % answers)
        for a in answers:
            _log.info('result type: %s (dns.A=%s)' % (a.type, dns.A))
            if a.type == dns.A:
                t = a.payload.address
                ipstr = '%d.%d.%d.%d' % (ord(t[0]), ord(t[1]), ord(t[2]), ord(t[3]))
                res = datatypes.IPv4Address.fromString(ipstr)
                return res
        raise error.DNSLookupError(hostname)

    d = _resolver.lookupAddress(hostname).addCallback(_success, hostname)
    return d  # deferred
        
def compute_periodic_reboot_time():
    """Figure time after which periodic reboot is desired.

    Start from current boot time, go forwards until we hit the desired weekday and
    time on that day.  Any time after that we want to do periodic reboot if possible.
    Note that it's a bad idea to just take current time and compare day and time;
    that would be theoretically wrong in some corner cases.  Further, if we are past
    a previously computed periodic reboot time, the computation could then result in
    an additional wait of one week, etc.

    Because periodic reboot settings are relative to timezone, the function first
    computes the periodic reboot target time in (non-naive) locale datetime, and
    then converts it to a (naive) UTC datetime.
    """

    tz = get_timezone_helper()

    # Get UI config.  Note that all of these are relative to web UI timezone.
    ui_root = helpers.get_ui_config()
    reboot_day = ui_root.getS(ns_ui.periodicRebootDay, rdf.Integer)   # mon=0, sun=6  (NB: differs from ISO!)
    iso_reboot_day = reboot_day + 1                                   # mon=1, sun=7
    reboot_time = ui_root.getS(ns_ui.periodicRebootTime, rdf.Integer) # hours since midnight, 0...23

    # Sanity
    if iso_reboot_day < 0 or iso_reboot_day > 7:
        raise Exception('reboot day (%d, iso %d) is insane' % (reboot_day, iso_reboot_day))
        
    # Start from 00:00 of *next* day (local time, non-naive)
    curr_boot = helpers.read_datetime_marker_file(constants.BOOT_TIMESTAMP_FILE)
    curr_boot = tz.convert_datetime_to_local_datetime(curr_boot, output_naive=False)   # local, non-naive
    t = curr_boot.replace(curr_boot.year, curr_boot.month, curr_boot.day, 0, 0, 0, 0)  # local, non-naive
    t = t + datetime.timedelta(1, 0, 0)                                                # skip ahead one day

    # Increment days until proper (iso) weekday; a bit lazy but no special cases
    for i in xrange(30):  # sanity: never busyloop..
        _log.debug('_compute_periodic_reboot_time: checking %s (curr boot %s) [local time]' % (str(t), str(curr_boot)))
        if t < curr_boot:  # ignore periodic reboot; theoretical now because we add one day above
            continue
        if t.isoweekday() == iso_reboot_day:
            break
        t = t + datetime.timedelta(1, 0, 0)  # one day

    # Add proper time
    t = t + datetime.timedelta(0, reboot_time * 60 * 60, 0)     # local, non-naive
    _log.debug('_compute_periodic_reboot_time: final reboot time, local: %s' % str(t))

    # Convert (non-naive) local time to (naive) UTC
    t = convert_datetime_to_utc_datetime(t, output_naive=True)  # utc, naive
    _log.debug('_compute_periodic_reboot_time: final periodic reboot time, utc: %s' % str(t))

    return t

def check_periodic_reboot_time_window(dt):
    """Check whether current time of day is within periodic reboot window.

    For example, if admin configures periodic reboots for 02:00-03:00, actions
    can only be taken within this hourly period.  Note that the period is
    specified in local time.

    Note that this function does not check for the periodic reboot day;
    this function is used also in overdue periodic reboots when initial
    periodic reboot is postponed because of client connections or other
    such reasons.
    """

    tz = get_timezone_helper()

    # Get UI config.  Note that all of these are relative to web UI timezone.
    ui_root = helpers.get_ui_config()
    reboot_hour = ui_root.getS(ns_ui.periodicRebootTime, rdf.Integer) # hours since midnight, 0...23

    # Specified timestamp ("now") in local time
    dt_local = tz.convert_datetime_to_local_datetime(dt, output_naive=False)   # local, non-naive
    
    # Compare hours
    dt_hour = dt_local.hour
    _log.debug('check_periodic_reboot_time_window: dt_hour=%s, reboot_hour=%s' % (dt_hour, reboot_hour))
    if dt_hour == reboot_hour:
        return True

    return False

def collapse_setting(rdf_uri):
    try:
        ui_root = helpers.get_ui_config()
        if not ui_root.hasS(rdf_uri):
            _log.debug('no collapse setting for %s, assuming expanded' % rdf_uri)
            ui_root.setS(rdf_uri, rdf.Boolean, False)
        return ui_root.getS(rdf_uri, rdf.Boolean)
    except:
        _log.exception('cannot get collapse setting for %s, assuming expanded' % rdf_uri)
        return False

def update_collapse_setting(rdf_uri, collapsed):
    try:
        #
        #  XXX: this is not very clean; we currently use the strings '0' and '1'
        #  in form data and need to catch them here for convenience.  The other
        #  value checks are for future, if the form data is changed for better.
        #
        if isinstance(collapsed, bool):
            value = collapsed
        elif isinstance(collapsed, int):
            if collapsed == 0:
                value = False
            else:
                value = True
        elif isinstance(collapsed, str) and collapsed == '0':
            value = False
        elif isinstance(collapsed, str) and collapsed == '1':
            value = True
        else:
            raise Exception('unknown collapsed value: %s' % collapsed)
        helpers.get_ui_config().setS(rdf_uri, rdf.Boolean, value)
    except:
        _log.exception('cannot update collapse setting for %s, assuming expanded' % rdf_uri)

def check_request_local_address_against_config(request):
    ui_root = helpers.get_ui_config()

    # local address of HTTP/HTTPS connection
    host = request.getHost()
    address = host.host
    req_addr = datatypes.IPv4Address.fromString(address).toString()
    local_addr = datatypes.IPv4Address.fromString('127.0.0.1').toString()

    # check local immediately
    if req_addr == local_addr:
        _log.debug('request is from local interface, and is accepted')
        return True

    # address of our public / private interfaces - based on rdf (!)
    pub_addr, priv_addr = helpers.get_public_private_address_from_rdf()

    # which address?
    _log.debug('req_addr=%s, pub_addr=%s, priv_addr=%s, local_addr=%s' % (req_addr, pub_addr, priv_addr, local_addr))
    if req_addr == pub_addr:
        if ui_root.hasS(ns_ui.webAccessPublic) and ui_root.getS(ns_ui.webAccessPublic, rdf.Boolean):
            _log.debug('request is from public interface, and is accepted')
            return True
        else:
            _log.debug('request is from public interface, and is rejected')
            return False
    elif req_addr == priv_addr:
        if ui_root.hasS(ns_ui.webAccessPrivate) and ui_root.getS(ns_ui.webAccessPrivate, rdf.Boolean):
            _log.debug('request is from private interface, and is accepted')
            return True
        else:
            _log.debug('request is from private interface, and is rejected')
            return False
    else:
        _log.warning('unknown request (host) address %s, not allowing' % req_addr)
        return False

def check_allowed_characters(s, allowed):
    for i in xrange(len(s)):
        if not s[i] in allowed:
            return False
    return True

DYNDNS_USERNAME_RE = re.compile(r'^[\x21-\x7e]*$')  # XXX: quite wide
DYNDNS_PASSWORD_RE = re.compile(r'^[\x21-\x7e]*$')  # XXX: quite wide
DYNDNS_HOSTNAME_RE = re.compile(r'^[\x21-\x7e]*$')  # XXX: quite wide
PRESHARED_KEY_RE = re.compile(r'^[\x21-\x7e]*$')    # works now because Pluto uses hex format
    # XXX: we might still want to at least warn about special characters to avoid client-side trouble
DNS_NAME_RE = re.compile(r'^[\x21-\x7e]*$')         # XXX: quite wide

# PPP_USERNAME_RE = re.compile(r'^[\x21-\x7e]*$')     # works with ppp escaping
# PPP_PASSWORD_RE = re.compile(r'^[\x21-\x7e]*$')     # works with ppp escaping

# Small subset which works with freeradius users-file wihtout escaping
# PPP_USERNAME_RE = re.compile(r'^[a-zA-Z0-9\ \@\.\,\;\:\*\~\^\+\-\_\?\&\%\$\!]*$')
# PPP_PASSWORD_RE = re.compile(r'^[a-zA-Z0-9\ \@\.\,\;\:\*\~\^\+\-\_\?\&\%\$\!]*$')

# Tested to work with freeradius users-file when escaping is used
# Exclude backslash (\x5c) which is detected as NT domain separator in mschap module
PPP_USERNAME_RE = re.compile(r'^[\x21-\x5b\x5d-\x7e]*$') # works with freeradius escaping
PPP_PASSWORD_RE = re.compile(r'^[\x21-\x5b\x5d-\x7e]*$') # works with freeradius escaping

RADIUS_SECRET_RE = re.compile(r'^[\ a-zA-Z0-9_-]*$')
RADIUS_NAI_IDENTIFIER_RE = re.compile(r'^[\ a-zA-Z0-9_-]*$')

SNMP_COMMUNITY_RE = re.compile(r'^[\x21-\x7e]*$')  # XXX: quite wide

def check_dyndns_username_characters(s):
    return DYNDNS_USERNAME_RE.match(s) != None

def check_dyndns_password_characters(s):
    return DYNDNS_PASSWORD_RE.match(s) != None

def check_dyndns_hostname_characters(s):
    return DYNDNS_HOSTNAME_RE.match(s) != None

def check_preshared_key_characters(s):
    return PRESHARED_KEY_RE.match(s) != None

def check_dns_name_characters(s):
    return DNS_NAME_RE.match(s) != None

def check_ppp_username_characters(s):
    return PPP_USERNAME_RE.match(s) != None

def check_ppp_password_characters(s):
    return PPP_PASSWORD_RE.match(s) != None

def check_radius_secret_characters(s):
    return RADIUS_SECRET_RE.match(s) != None

def check_radius_nai_identifier_characters(s):
    return RADIUS_NAI_IDENTIFIER_RE.match(s) != None

def check_snmp_community_characters(s):
    return SNMP_COMMUNITY_RE.match(s) != None

def get_latest_product_version():
    changelog = None
    try:
        changelog = helpers.get_db_root().getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo)).getS(ns_ui.changeLog, rdf.String)
    except:
        _log.exception('cannot get changelog from rdf database, falling back to local version')
        changelog = versioninfo.get_changelog()

    res = None
    for [version, lines] in versioninfo.get_changelog_info(startversion=None, changelog=changelog):
        # take first
        res = version
        break

    return res

def get_status_and_substatus():
    """Get status and substatus fields for web UI.

    This has been refactored here because SNMP also needs the same health status
    information as web UI.  Hence this is also called from crontab.  This is not
    very clean; it would be better if some sort of status helper object provided
    the same information in various formats to multiple places in code.

    Calling this function only makes sense when runner is running, i.e. status
    tree exists.
    """

    failed = 0
    st_root = helpers.get_status()
    
    try:
        for x in st_root.getS(ns.serverStatuses, rdf.Bag(rdf.Type(ns.ServerStatus))):
            if x.hasS(ns.serverHealthCheck) and (not x.getS(ns.serverHealthCheck, rdf.Boolean)):
                failed += 1
    except:
        _log.exception('cannot determine dns/wins status, ignoring')
                    
    try:
        for x in st_root.getS(ns.routerStatuses, rdf.Bag(rdf.Type(ns.RouterStatus))):
            if x.hasS(ns.routerHealthCheck) and (not x.getS(ns.routerHealthCheck, rdf.Boolean)):
                failed += 1
    except:
        _log.exception('cannot determine router status, ignoring')

    lic_valid = True
    lic_demo, lic_demo_expiry, lic_demo_left, lic_days_left = False, None, None, None
    try:
        lm = licensemanager.LicenseMonitor()
        lic_valid = lm.check_license_validity()
        lic_demo, lic_demo_expiry, lic_demo_left = lm.check_demo_license()
        if lic_demo_left is not None:
            lic_days_left = helpers.timedelta_to_seconds(lic_demo_left) / float(24*60*60)
        else:
            lic_demo, lic_demo_expiry, lic_demo_left, lic_days_left = False, None, None, None
    except:
        _log.exception('cannot determine license validity, ignoring')

    # XXX: we might want to filter here to ensure that last health check is current enough
    # service running more than N minutes, lastPollTime is relatively recent, .. ?
                
    if (not lic_valid) and (not lic_demo):
        status_class, status_text = 'warning', 'Active with errors'
        substatus_class, substatus_text = '', 'Invalid license'
    elif (not lic_valid) and lic_demo:
        status_class, status_text = '', 'Active with errors'
        substatus_class, substatus_text = '', 'Demo license (expired)'
    elif failed > 0:
        status_class, status_text = 'warning', 'Active with errors'
        substatus_class, substatus_text = '', 'Server(s) not responding'
    elif lic_demo and (lic_demo_left is not None):
        status_class, status_text = '', 'Active'
        substatus_class, substatus_text = '', 'Demo license (%s left)' % render_timedelta(lic_demo_left)
    else:
        status_class, status_text = '', 'Active'
        substatus_class, substatus_text = '', ''

    return status_class, status_text, substatus_class, substatus_text, (status_text == 'Active')

def create_access_control_dropdown(fieldname, label, required=True):
    ac_options = [ ('both', 'Internet and private network connection'),
                   ('public', 'Internet connection only'),
                   ('private', 'Private network connection only'),
                   ('none', 'Not allowed') ]
    return formalutils.Field(fieldname,
                             formal.String(required=required),
                             formal.widgetFactory(formal.SelectChoice, options=ac_options),
                             label=label)

def set_user_password_hashes(user, password):
    password_nt = helpers.compute_password_nt_hash(password)
    password_md5 = helpers.compute_password_md5(password)
    user.setS(ns_ui.passwordMd5, rdf.String, password_md5.encode('hex').upper())
    user.setS(ns_ui.passwordNtHash, rdf.String, password_nt.encode('hex').upper())
    user.removeNodes(ns_ui.password)

def _check_network_interface_configuration():
    _log.info('_check_network_interface_configuration()')
    
    from codebay.l2tpserver import interfacehelper
    ifaces = interfacehelper.get_all_interfaces()

    rv = True

    def _check(ifname):
        for i in ifaces.get_interface_list():
            if i.get_device_name() == ifname:
                _log.info('_check_network_interface_configuration(): %s exists' % ifname)
                return True
        _log.info('_check_network_interface_configuration(): %s does not exist' % ifname)
        return False

    ui_root = helpers.get_ui_config()

    if ui_root.hasS(ns_ui.internetConnection):
        ic_root = ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
        if ic_root.hasS(ns_ui.interface):
            _log.info('_check_network_interface_configuration(): checking public')
            if not _check(ic_root.getS(ns_ui.interface, rdf.String)):
                rv = False

    if ui_root.hasS(ns_ui.privateNetworkConnection):
        pn_root = ui_root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
        if pn_root.hasS(ns_ui.interface):
            _log.info('_check_network_interface_configuration(): checking private')
            if not _check(pn_root.getS(ns_ui.interface, rdf.String)):
                rv = False

    _log.info('_check_network_interface_configuration() -> %s' % rv)
    return rv

def check_network_interface_configuration():
    """Check that network interfaces that are used in UI config are present in the system.

    Return True if everything checks out.
    """

    # XXX: unfortunately the check below is fragile with respect to signal handling.
    # If a signal arrives, it may be interrupted and fails with an exception.  This
    # is made more likely by the fact that when this check matters, we're often in
    # a runner restart loop.  The looping below is simply to attempt to solve the
    # problem.
    
    for i in xrange(10):
        try:
            rv = _check_network_interface_configuration()
            return rv
        except:
            _log.exception('check_network_interface_configuration() failed; sleeping and retrying')
            try:
                run_command([constants.CMD_SLEEP, '1'])
            except:
                _log.exception('sleep failed')
            

    _log.warning('check_network_interface_configuration() failed after many attempts')
    return True

def update_ssl_certificate_files():
    """Write SSL certificate and key to disk based on UI config.

    If no SSL files configured, write nothing.
    """

    #
    #  XXX: validation could happen here with openssl tool?
    #
    
    ui_root = helpers.get_ui_config()  # reget root
    if ui_root.hasS(ns_ui.publicSslCertificateChain) and \
           ui_root.getS(ns_ui.publicSslCertificateChain, rdf.String) != '' and \
           ui_root.hasS(ns_ui.publicSslPrivateKey) and \
           ui_root.getS(ns_ui.publicSslPrivateKey, rdf.String) != '':

        f = None
        try:
            f = open(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN, 'wb')
            # XXX: encoding doesn't matter if validation is correct
            f.write(ui_root.getS(ns_ui.publicSslCertificateChain, rdf.String).encode('UTF-8'))
        finally:
            if f is not None:
                f.close()
                f = None

        f = None
        try:
            f = open(constants.WEBUI_EXTERNAL_PRIVATE_KEY, 'wb')
            # XXX: encoding doesn't matter if validation is correct
            f.write(ui_root.getS(ns_ui.publicSslPrivateKey, rdf.String).encode('UTF-8'))
        finally:
            if f is not None:
                f.close()
                f = None
    else:
        if os.path.exists(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN):
            os.unlink(constants.WEBUI_EXTERNAL_CERTIFICATE_CHAIN)
        if os.path.exists(constants.WEBUI_EXTERNAL_PRIVATE_KEY):
            os.unlink(constants.WEBUI_EXTERNAL_PRIVATE_KEY)
