"""A bunch of renderers for various purpose.

These are in need of cleanup, but since they are pretty much
orthogonal and don't cause execution overhead, it's not very
important.

XXX: many renderers in this file are wasteful, in that they
compute the same (intermediate) values over and over again
instead sharing access to common data.  This should be refactored
later to make better use of the Nevow data/render split.
"""
__docformat__ = 'epytext en'

import os, time, datetime, textwrap, re

from nevow import inevow, url, tags as T

from codebay.common import rdf
from codebay.common import logger
from codebay.common import datatypes

from codebay.l2tpserver import helpers
from codebay.l2tpserver import licensemanager
from codebay.l2tpserver import constants
from codebay.l2tpserver import versioninfo
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import db
from codebay.l2tpserver.webui import l2tpmanager
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import doclibrary

_log = logger.get('l2tpserver.webui.renderers')

saferender = uihelpers.saferender

# --------------------------------------------------------------------------

def _render_datetime(dt, show_seconds=True):
    tz = uihelpers.get_timezone_helper()
    return tz.render_datetime(dt, show_seconds=show_seconds)

def _render_datetime_delta(dt):
    now = datetime.datetime.utcnow()
    td = now - dt
    return uihelpers.render_timedelta(td)

def _render_percentage(x):
    return '%d%%' % int(x)

def _capitalize_first(s):
    if s is None or len(s) == 0:
        return s
    return s[0].capitalize() + s[1:]

# --------------------------------------------------------------------------

class StatusRenderers:
    @saferender()
    def render_service_uptime(self, ctx, data):
        return self.get_service_uptime(ajax=False)

    @saferender()
    def render_last_update_time(self, ctx, data):
        st_root = helpers.get_status()
        return _render_datetime_delta(st_root.getS(ns.lastStateUpdate, rdf.Datetime)) + ' ago'

    @saferender()
    def render_last_poll_time(self, ctx, data):
        st_root = helpers.get_status()
        return _render_datetime_delta(st_root.getS(ns.lastPollTime, rdf.Datetime)) + ' ago'

    @saferender()
    def render_last_successful_product_update_time(self, ctx, data):
        t = helpers.read_datetime_marker_file(constants.LAST_SUCCESSFUL_UPDATE_MARKER_FILE)
        if t is None:
            return ''
        return _render_datetime(t, show_seconds=False)

    @saferender()
    def render_last_automatic_reboot_time(self, ctx, data):
        t = helpers.read_datetime_marker_file(constants.LAST_AUTOMATIC_REBOOT_MARKER_FILE)
        if t is None:
            return ''
        return _render_datetime(t, show_seconds=False)

    @saferender()
    def render_next_automatic_reboot_time(self, ctx, data):
        t = uihelpers.compute_periodic_reboot_time()
        if t is None:
            return ''
        return _render_datetime(t, show_seconds=False)

    @saferender()
    def render_server_uptime(self, ctx, data):
        return self.get_server_uptime(ajax=False)
        
    @saferender()
    def render_state(self, ctx, data):
        status_class, status_text, substatus_class, substatus_text = self.get_status_overview_information()
        return status_text

    # This is only of internal use - raw RDF PPP device count
    @saferender()
    def render_ppp_device_count(self, ctx, data):
        st_root = helpers.get_status()
        return '%s' % len(st_root.get_ppp_devices())

    @saferender(default='0')
    def render_normal_user_count(self, ctx, data):
        lm = licensemanager.LicenseMonitor()
        count, limit, limit_leeway = lm.count_normal_users()
        return count

    @saferender(default='0')
    def render_site_to_site_user_count(self, ctx, data):
        lm = licensemanager.LicenseMonitor()
        count, limit, limit_leeway = lm.count_site_to_site_users()
        return count

    @saferender()
    def render_public_rxrate(self, ctx, data): 
        st_root = helpers.get_status()
        if st_root.hasS(ns.publicInterface):
            return uihelpers.render_transfer_rate_bits(st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.rxRateCurrent, rdf.Float))
        else:
            return ''
         
    @saferender()
    def render_public_txrate(self, ctx, data):
        st_root = helpers.get_status()
        if st_root.hasS(ns.publicInterface):
            return uihelpers.render_transfer_rate_bits(st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.txRateCurrent, rdf.Float))
        else:
            return ''

    @saferender()
    def render_public_rxtx_rate_summary(self, ctx, data): 
        return self.get_public_rxtx_summary(ajax=False)
    
    @saferender()
    def render_public_limit(self, ctx, data):
        ui_root = helpers.get_ui_config()
        
        if ui_root.hasS(ns_ui.internetConnection):
            pub_iface = ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
            if pub_iface.hasS(ns_ui.vpnUplink):
                return 'Traffic limit: %.1f Mbps' % pub_iface.getS(ns_ui.vpnUplink, rdf.Float)

        return 'Traffic limit not set'
        
    @saferender()
    def render_public_dyndns_line(self, ctx, data):
        return self.get_public_dyndns_line(ajax=False)
    
    @saferender()
    def get_public_dyndns_line(self, ajax=False):
        ui_root = helpers.get_ui_config()
        
        if ui_root.hasS(ns_ui.dynDnsServer):
            dyndns = ui_root.getS(ns_ui.dynDnsServer, rdf.Type(ns_ui.DynDnsServer))
            
            if dyndns.hasS(ns_ui.dynDnsProvider) and (dyndns.getS(ns_ui.dynDnsProvider, rdf.String) != '') and \
                   dyndns.hasS(ns_ui.dynDnsUsername) and (dyndns.getS(ns_ui.dynDnsUsername, rdf.String) != '') and \
                   dyndns.hasS(ns_ui.dynDnsPassword) and (dyndns.getS(ns_ui.dynDnsPassword, rdf.String) != '') and \
                   dyndns.hasS(ns_ui.dynDnsHostname) and (dyndns.getS(ns_ui.dynDnsHostname, rdf.String) != ''):
                curr = self.master.get_dyndns_current_address()
                addr = ''
                if curr == '':
                    addr = '...'
                elif curr == 'ERROR':  # XXX: special case
                    # XXX: not the cleanest possible solution - javascript "magics" this to be red
                    addr = 'Error'
                else:
                    addr = curr

                # XXX: this is currently not classed correctly before Ajax updates the SPAN element.
                # See: #844.
                res = u'%s \u2192 %s' % (dyndns.getS(ns_ui.dynDnsHostname, rdf.String), addr)
                return res

        return 'Dynamic DNS not set'

    @saferender()
    def render_private_rxrate(self, ctx, data):
        st_root = helpers.get_status()
        if st_root.hasS(ns.privateInterface):
            return uihelpers.render_transfer_rate_bits(st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.rxRateCurrent, rdf.Float))
        else:
            return ''

    @saferender()
    def render_private_txrate(self, ctx, data):
        st_root = helpers.get_status()
        if st_root.hasS(ns.privateInterface):
            return uihelpers.render_transfer_rate_bits(st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.txRateCurrent, rdf.Float))
        else:
            return ''

    @saferender()
    def render_private_rxtx_rate_summary(self, ctx, data): 
        return self.get_private_rxtx_summary(ajax=False)

    @saferender()
    def render_public_address(self, ctx, data):
        return self.get_public_address(ajax=False)

    @saferender()
    def render_public_interface_string(self, ctx, data):
        return self.get_public_interface_string(ajax=False)

    @saferender()
    def render_private_address(self, ctx, data):
        return self.get_private_address(ajax=False)
    
    @saferender()
    def render_private_interface_string(self, ctx, data):
        return self.get_private_interface_string(ajax=False)

    @saferender()
    def render_private_interface_unconfigured(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.privateNetworkConnection):
            return ''
        else:
            return 'Not configured'

    @saferender()
    def render_public_mac(self, ctx, data):
        return self.get_public_mac(ajax=False)
    
    @saferender()
    def render_private_mac(self, ctx, data):
        return self.get_private_mac(ajax=False)
    
    @saferender()
    def render_dns_wins_overview(self, ctx, data):
        return self.get_dns_wins_overview(ajax=False)

    # helper shared by dns/wins and router lists
    def _render_server_status_list(self, data, ajax, empty_string='None'):
        if ajax:
            res = []
            for [addr, text, classname] in data:
                res = res + [addr, text, classname]
            if len(res) > 0:
                return '\t'.join(res)
            else:
                # ajax will update this as a special case
                return empty_string
        else:
            s = []
            for [addr, text, classname] in data:
                t = T.span['%s (%s)' % (addr, text)]
                if classname != '':
                    t(_class=classname)
                s.append(t)

            res = T.invisible()
            if len(s) > 0:
                for i, t in enumerate(s):
                    if i > 0:
                        res[T.br()]
                    res[t]
            else:
                res[empty_string]
            return res
    
    def get_dns_wins_overview(self, ajax=False):
        st_root = helpers.get_status()
        r = []
        try:
            for x in st_root.getS(ns.serverStatuses, rdf.Bag(rdf.Type(ns.ServerStatus))):
                addr = x.getS(ns.serverAddress, rdf.IPv4Address)
                health = x.getS(ns.serverHealthCheck, rdf.Boolean)
                # server interface, not used here
                r.append((addr, health))

            def _cmp(a, b):
                a_addr, a_health = a
                b_addr, b_health = b
                return cmp(a_addr.toLong(), b_addr.toLong())
            r.sort(cmp=_cmp)
        except:
            _log.exception('error in looking up dns/wins server status list')

        data = []
        for addr, health in r:
            if health:
                data.append([addr.toString(), 'OK', ''])
            else:
                data.append([addr.toString(), 'Not responding', 'warning'])

        return self._render_server_status_list(data, ajax, empty_string='...')

    @saferender()
    def render_router_overview(self, ctx, data):
        return self.get_router_overview(ajax=False)

    def get_router_overview(self, ajax=False):
        st_root = helpers.get_status()
        try:
            r = []
            for x in st_root.getS(ns.routerStatuses, rdf.Bag(rdf.Type(ns.RouterStatus))):
                addr = x.getS(ns.routerAddress, rdf.IPv4Address)
                health = x.getS(ns.routerHealthCheck, rdf.Boolean)
                # related routes, not used here
                r.append((addr, health))

            def _cmp(a, b):
                a_addr, a_health = a
                b_addr, b_health = b
                return cmp(a_addr.toLong(), b_addr.toLong())
            r.sort(cmp=_cmp)
        except:
            _log.exception('error in looking up router status list')

        data = []
        for addr, health in r:
            if health:
                data.append([addr.toString(), 'OK', ''])
            else:
                data.append([addr.toString(), 'Not responding', 'warning'])

        return self._render_server_status_list(data, ajax, empty_string='...')

    @saferender()
    def render_site_to_site_overview(self, ctx, data):
        return self.get_site_to_site_overview(ajax=False)

    def get_site_to_site_overview(self, ajax=False):
        st_root = helpers.get_status()

        s2s_fixup_limit = datetime.timedelta(0, 5*60, 0)  # 5 mins, XXX: constants

        # empty string depends on ui config
        empty_string = 'Not configured'
        try:
            ui_root = helpers.get_ui_config()
            if len(ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection)))) > 0:
                empty_string = '...'
        except:
            _log.exception('cannot determine empty string for s2s')

        # get last poll time if possible, used below
        last_poll = None
        try:
            last_poll = st_root.getS(ns.lastPollTime, rdf.Datetime)
        except:
            _log.exception('last_poll get failed')

        # first pass, gather data from rdf, sort it
        r = []
        try:
            for x in st_root.getS(ns.siteToSiteStatuses, rdf.Bag(rdf.Type(ns.SiteToSiteStatus))):
                try:
                    health = x.getS(ns.tunnelHealthCheck, rdf.Boolean)
                    addrfailure = False
                    if x.hasS(ns.addressCheckFailure):
                        addrfailure = x.getS(ns.addressCheckFailure, rdf.Boolean)
                    licfailure = False
                    if x.hasS(ns.licenseRestrictedFailure):
                        licfailure = x.getS(ns.licenseRestrictedFailure, rdf.Boolean)
                    username = x.getS(ns.tunnelConfig, rdf.Type(ns.User)).getS(ns.username, rdf.String)
                    role = x.getS(ns.tunnelConfig, rdf.Type(ns.User)).getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser)).getS(ns.role)
                    tuntype = None
                    is_client = None
                    if role.hasType(ns.Client):
                        tuntype = 'initiate'
                        is_client = True
                    elif role.hasType(ns.Server):
                        tuntype = 'respond'
                        is_client = False
                    else:
                        raise Exception('cannot get tunnel type')

                    # Site-to-site remote address
                    #    - if has tunnelRemoteAddress, use that; it only exists for client mode
                    #      connections that we init, and exists even before the PPP device comes up
                    #    - if a PPP device exists, look for an address from there; this is the only
                    #      viable option for server mode connections
                    addr = None
                    try:
                        addr = x.getS(ns.tunnelRemoteAddress, rdf.IPv4Address)
                    except:
                        _log.debug('cannot get tunnel remote address, this is normal')

                    ppp_dev = None
                    try:
                        if is_client:
                            ppp_dev = helpers.find_ppp_device_status_sitetosite_client(username)
                        else:
                            ppp_dev = helpers.find_ppp_device_status_sitetosite_server(username)
                    except:
                        _log.exception('getting ppp_dev failed')

                    try:
                        if (addr is None) and (ppp_dev is not None):
                            addr = ppp_dev.getS(ns.outerAddress, rdf.IPv4Address)
                    except:
                        _log.exception('getting address from ppp_dev failed')

                    # The status of both client and server connections are systematically out-of-date
                    # when the connection is initiated: the PPP device status will be up much before
                    # the startstop.py health check can actually ping and verify that the connection
                    # works.  See #508.
                    #
                    # It looks pretty misleading in the web UI to show these connections as being
                    # 'down' when they have in fact just been established.  So, what we do here is
                    # pretend that the connection is up, if the last poll is older than the start
                    # time of the matching PPP device (if any).  This makes web UI state a bit more
                    # responsive and useful for the admin.
                    #
                    # This is complicated even further by the fact that not all poll rounds will
                    # actually update site-to-site state.  So there may be cases (very likely ones)
                    # where poll time is newer than device startTime but the site-to-site health
                    # status is still out of date.  This could be fixed by making the PPP script
                    # update health state; or by adding a separate timestamp to individual site-to-site
                    # connection status entries.  The workaround below is to require that the status
                    # be old enough (at least older than presumed poll interval for site-to-site
                    # connections).
                    
                    try:
                        if (not health) and (ppp_dev is not None):
                            # Also handle the corner case that last_poll is None; this happens because
                            # lastPollTime is updated *last* in the poll loop by startstop, so when the
                            # first loop is still happening and we have site-to-site status in RDF, the
                            # lastPollTime value may still be missing -- but on the first round only.

                            ppp_start = ppp_dev.getS(ns.startTime, rdf.Datetime)
                            ppp_age = datetime.datetime.utcnow() - ppp_start
                            if (last_poll is None) or (ppp_start > last_poll) or (ppp_age > datetime.timedelta(0, 0, 0) and ppp_age < s2s_fixup_limit):
                                health = True
                    except:
                        _log.exception('health fixup failed')

                    r.append((addr, health, addrfailure, licfailure, username, tuntype))
                except:
                    _log.exception('cannot get status for a site-to-site tunnel, skipping')
        
            def _cmp(a, b):
                a_addr, a_health, a_addrfail, a_licfail, a_user, a_type = a
                b_addr, b_health, b_addrfail, b_licfail, b_user, b_type = b
                return cmp(a_user, b_user)  # XXX: better sorting
            r.sort(cmp=_cmp)
        except:
            _log.exception('error in looking up site-to-site server status list')

        # second pass, distill into actual renderable data
        data = []
        for addr, health, addrfail, licfail, username, tuntype in r:
            addr_str = '?'
            if addr is not None:
                addr_str = addr.toString()
            if health:
                status_txt = 'Up'
                if tuntype == 'initiate':
                    data.append([u'%s \u2192 %s' % (username, addr_str), status_txt, ''])   # \u2192 = rarr
                else:
                    data.append([u'%s \u2190 %s' % (username, addr_str), status_txt, ''])   # \u2190 = larr
            else:
                failures = []
                if addrfail:
                    failures.append('address check failed')
                if licfail:
                    failures.append('license exceeded')
                status_txt = 'Down'
                if len(failures) > 0:
                    status_txt += ', ' + (', '.join(failures))
                if tuntype == 'initiate':
                    data.append([u'%s \u2192 %s' % (username, addr_str), status_txt, 'warning'])   # \u2192 = rarr
                else:
                    data.append([u'%s \u2190 %s' % (username, addr_str), status_txt, 'warning'])   # \u2190 = larr

        return self._render_server_status_list(data, ajax, empty_string=empty_string)

    # XXX: these are now updated once a minute, not very nice
    @saferender()
    def render_cpu_usage(self, ctx, data):
        return self.get_cpu_usage(ajax=False)

    @saferender()
    def render_disk_usage(self, ctx, data):
        return self.get_disk_usage(ajax=False)

    @saferender()
    def render_memory_usage(self, ctx, data):
        return self.get_memory_usage(ajax=False)

    @saferender()
    def render_swap_usage(self, ctx, data):
        return self.get_swap_usage(ajax=False)
    
    @saferender()
    def render_l2tpmanager_state(self, ctx, data):
        m = self.get_master().get_l2tpmanager()
        return str(m.getState())

    @saferender()
    def render_usergraph(self, ctx, data):
        uri = self.build_uri(ctx, 'graph.html')
        uri = uri.add('name', 'usercount')

        # XXX: this code could use some sharing, and be placed in static/
        jscode = textwrap.dedent("""
        <script type="text/javascript">
        // <![CDATA[
        _user_graph_root_uri = "%(rooturi)s";
        _user_graph_reload_interval = 1 * 60 * 1000;
        
        function _reload_user_graph() {
          var n = document.getElementById("user-graph");
          if (n) {
            n.src = _user_graph_root_uri + "&dummy=" + (new Date()).getTime();
          }
          setTimeout(_reload_user_graph, _user_graph_reload_interval);
        }

        addDOMLoadEvent(function() {
          setTimeout(_reload_user_graph, _user_graph_reload_interval);
        })
        // ]]>
        </script>
        """ % {'rooturi': str(uri)})

        res = T.span[T.img(src=uri, alt='Users graph', id='user-graph', width=constants.USER_GRAPH_WIDTH, height=constants.USER_GRAPH_HEIGHT)]
        #res['\n', T.raw(jscode), '\n']
        return res
    
    @saferender()
    def render_sitetositegraph(self, ctx, data):
        uri = self.build_uri(ctx, 'graph.html')
        uri = uri.add('name', 'sitetositecount')

        # XXX: this code could use some sharing, and be placed in static/
        jscode = textwrap.dedent("""
        <script type="text/javascript">
        // <![CDATA[
        _s2s_graph_root_uri = "%(rooturi)s";
        _s2s_graph_reload_interval = 1 * 60 * 1000;
        
        function _reload_s2s_graph() {
          var n = document.getElementById("s2s-graph");
          if (n) {
            n.src = _s2s_graph_root_uri + "&dummy=" + (new Date()).getTime();
          }
          setTimeout(_reload_s2s_graph, _s2s_graph_reload_interval);
        }

        addDOMLoadEvent(function() {
          setTimeout(_reload_s2s_graph, _s2s_graph_reload_interval);
        })
        // ]]>
        </script>
        """ % {'rooturi': str(uri)})

        res = T.span[T.img(src=uri, alt='Site-to-site graph', id='s2s-graph', width=constants.SITETOSITE_GRAPH_WIDTH, height=constants.SITETOSITE_GRAPH_HEIGHT)]
        #res['\n', T.raw(jscode), '\n']
        return res
    
    # XXX: the sort parameterization here is not particularly good
    @saferender()
    def render_ppp_devices_helper(self, ctx, data, include_normal_users, include_sitetosites, include_active, include_retired, sort_by_starttime, sort_by_activity):
        st_root = helpers.get_status()
        global_st_root = helpers.get_global_status()
        now = datetime.datetime.utcnow()

        username_label = 'Username'
        no_connections_label = 'No user connections'
        if include_sitetosites:
            username_label = 'Connection username'
            no_connections_label = 'No site-to-site connections'

        # filter interesting users
        users = []
        devsets = []
        
        if st_root.hasS(ns.pppDevices) and include_active:
            devsets.append(helpers.get_ppp_devices())
        if global_st_root.hasS(ns.retiredPppDevices) and include_retired:
            devsets.append(helpers.get_retired_ppp_devices())
        for devset in devsets:
            for d in devset:
                # render restricted connections too

                # XXX: we'd like to ignore inactive devices, but this wasn't reliable enough
                #if not d.getS(ns.deviceActive, rdf.Boolean):
                #    continue

                t = d.getS(ns.connectionType)
                if t.hasType(ns.NormalUser) and include_normal_users:
                    users.append(d)
                elif t.hasType(ns.SiteToSiteClient) and include_sitetosites:
                    users.append(d)
                elif t.hasType(ns.SiteToSiteServer) and include_sitetosites:
                    users.append(d)

        # sorting
        def _cmp_activity_and_time(a, b):
            # active first, sorted by start time; then closed connections, sorted by close time
            a_closed = a.hasS(ns.stopTime)
            b_closed = b.hasS(ns.stopTime)
            if a_closed:
                a_time = a.getS(ns.stopTime, rdf.Datetime)
            else:
                a_time = a.getS(ns.startTime, rdf.Datetime)
            if b_closed:
                b_time = b.getS(ns.stopTime, rdf.Datetime)
            else:
                b_time = b.getS(ns.startTime, rdf.Datetime)
            # NB: order of times so that larger times (more recent timestamps) appear first
            return cmp([a_closed, b_time],
                       [b_closed, a_time])
        def _cmp_username_starttime(a, b):
            # NB: we want highest starttime (latest connection) at the top, hence order of a&b below
            return cmp([a.getS(ns.username, rdf.String), b.getS(ns.startTime, rdf.Datetime)],
                       [b.getS(ns.username, rdf.String), a.getS(ns.startTime, rdf.Datetime)])
        def _cmp_starttime_username(a, b):
            return cmp([b.getS(ns.startTime, rdf.Datetime), a.getS(ns.username, rdf.String)],
                       [a.getS(ns.startTime, rdf.Datetime), b.getS(ns.username, rdf.String)])
        if sort_by_activity:
            users.sort(cmp=_cmp_activity_and_time)
        elif sort_by_starttime:
            users.sort(cmp=_cmp_starttime_username)
        else:
            users.sort(cmp=_cmp_username_starttime)

        # render table
        table = T.table(border="0", cellpadding="0", cellspacing="0")
        table[T.tr[T.th[username_label],
                   T.th["Connection time"],
                   T.th["Notes"],
                   T.th["Details"]]]

        # render active users
        for d in users:
            notes = []
            if d.hasS(ns.ipsecPskIndex) and (d.getS(ns.ipsecPskIndex, rdf.Integer) != 0):
                notes.append('secondary pre-shared key')
            if d.getS(ns.ipsecEncapsulationMode).hasType(ns.EspPlain):
                notes.append('no NAT-T support')
            if d.getS(ns.restrictedConnection, rdf.Boolean):
                notes.append('restricted by license')  # XXX: other reasons later too

            age_str = ''
            if d.hasS(ns.stopTime):
                stop_str = ''
                try:
                    stop_str = ' (%s)' % uihelpers.render_datetime(d.getS(ns.stopTime, rdf.Datetime), show_seconds=False, show_timezone=False)
                except:
                    _log.exception('cannot render stopTime')
                age_str = 'Closed' + stop_str
            else:
                age = now - d.getS(ns.startTime, rdf.Datetime)
                if age < datetime.timedelta(0, 0, 0):
                    # should not happen too much, but we don't want negative times
                    age = datetime.timedelta(0, 0, 0)
                age_str = uihelpers.render_timedelta(age)

            detaillink = '?deviceuuid=' + str(d.getUri())

            notes_stan = T.invisible()
            for i, n in enumerate(notes):
                if i > 0:
                    notes_stan[T.br()]
                notes_stan[_capitalize_first(n)]

            table[T.tr[T.td[d.getS(ns.username, rdf.String)],
                       T.td[age_str],
                       T.td[notes_stan],
                       T.td[T.a(href=detaillink)[u'Details\u00a0\u2192']]]]  # nbsp, rarr

        if len(users) == 0:
            table[T.tr[T.td(colspan=4)[no_connections_label]]]
            
        return table
    
    def render_userlist(self, ctx, data):
        return self.render_ppp_devices_helper(ctx, data,
                                              include_normal_users=True,
                                              include_sitetosites=False,
                                              include_active=True,
                                              include_retired=False,
                                              sort_by_starttime=False,
                                              sort_by_activity=False)

    def render_userlist_with_retired(self, ctx, data):
        return self.render_ppp_devices_helper(ctx, data,
                                              include_normal_users=True,
                                              include_sitetosites=False,
                                              include_active=True,
                                              include_retired=True,
                                              sort_by_starttime=False,
                                              sort_by_activity=True)

    def render_sitetositelist(self, ctx, data):
        return self.render_ppp_devices_helper(ctx, data,
                                              include_normal_users=False,
                                              include_sitetosites=True,
                                              include_active=True,
                                              include_retired=False,
                                              sort_by_starttime=False,
                                              sort_by_activity=False)

    def render_sitetositelist_with_retired(self, ctx, data):
        return self.render_ppp_devices_helper(ctx, data,
                                              include_normal_users=False,
                                              include_sitetosites=True,
                                              include_active=True,
                                              include_retired=True,
                                              sort_by_starttime=False,
                                              sort_by_activity=True)


    #
    #  Rendering for selected device
    #
    #  Note that all rendered are from server point of view (i.e. PPP device).
    #  However, rx/tx values are from user point of view, i.e. user receive
    #  is server (ppp device) transfer!
    #

    # XXX: @db.transact() added to all selected device render functions to avoid
    # autotransactions.  This is necessary because some renderers (namely, dns
    # reverses) return deferred values.  This means that when the whole details
    # list for the selected device is rendered, the renderers after the first dns
    # reverse (= reverse of remote address) run outside the original @db.transact.
    # Hence we need to setup a new @db.transact.  This is not very pretty, but is
    # not easy to avoid without tampering with deferreds in the decorator.
    #
    # One possibility would be to detect that a deferred was returned and wrap the
    # deferred automatically with a transaction wrapper (in @db.transact()).

    def _reverse_lookup(self, addr, error_value):
        d = uihelpers.reverse_dns_lookup(addr)
        d.addCallback(lambda x: str(x))  # XXX: conversions?
        d.addErrback(lambda x: error_value)
        return d
    
    def _get_selected_device(self, ctx):        
        try:
            request = inevow.IRequest(ctx)
            if not request.args.has_key('deviceuuid'):
                return None
            devuri = request.args['deviceuuid'][0]  # XXX: take first, should not be more

            model = db.get_db().getModel()
            dev = model.getNodeByUri(rdf.Uri(devuri), rdf.Type(ns.PppDevice))
            return dev
        except:
            _log.exception('cannot get device by deviceuuid')
            return None

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_maybe(self, ctx, data):
        if self._get_selected_device(ctx):
            return ctx.tag
        else:
            return ''
        
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_username(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return dev.getS(ns.username, rdf.String)

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_connection_start(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return _render_datetime(dev.getS(ns.startTime, rdf.Datetime), show_seconds=True)

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_connection_end(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return _render_datetime(dev.getS(ns.stopTime, rdf.Datetime), show_seconds=True)
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_connection_duration(self, ctx, data):
        dev = self._get_selected_device(ctx)
        start_time = dev.getS(ns.startTime, rdf.Datetime)
        end_time = datetime.datetime.utcnow()
        if dev.hasS(ns.stopTime):
            end_time = dev.getS(ns.stopTime, rdf.Datetime)
        duration = end_time - start_time
        return uihelpers.render_timedelta(duration)
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_remote_address(self, ctx, data):
        """Render address, reverse, and configured address (if site-to-site client).

        These are now in one function (as opposed to clean, separate renderers) to avoid
        multiple reverse lookups.
        """

        def _got_reverse(rev):
            res = T.invisible()

            dev = self._get_selected_device(ctx)

            res[dev.getS(ns.outerAddress, rdf.IPv4Address).toString()]
            res[T.br()]
            if rev is not None:
                res['%s' % rev]
            else:
                res[u'\u00a0']

            # This is only relevant for s2s client connections: show configured address if
            # it is not a dotted decimal address *and* differs from reverse DNS address
            #
            # XXX: Note that this refers to *current* configuration and is incorrect for
            # historical entries.  This is a lesser evil at this point, though.

            try:
                conn = uihelpers.find_s2s_connection(dev.getS(ns.username, rdf.String))
                if (conn is not None) and \
                       conn.hasS(ns_ui.mode) and \
                       (conn.getS(ns_ui.mode, rdf.String) == 'client') and \
                       (conn.hasS(ns_ui.serverAddress)):
                    conf = conn.getS(ns_ui.serverAddress, rdf.String)

                    is_dotted = False
                    try:
                        ign = datatypes.IPv4Address.fromString(conf)
                        is_dotted = True
                    except:
                        pass

                    if (conf != rev) and (not is_dotted):
                        res[T.br()]
                        res['(%s)' % conf]
            except:
                _log.exception('s2s client configured vs. reverse address check failed')
                
            return res

        dev = self._get_selected_device(ctx)
        d = self._reverse_lookup(dev.getS(ns.outerAddress, rdf.IPv4Address), None)
        d.addCallback(_got_reverse)
        return d
    
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_ppp_address(self, ctx, data):
        dev = self._get_selected_device(ctx)

        # Use local PPP address for site-to-site connections, remote otherwise
        addr = None
        ctype = dev.getS(ns.connectionType)
        if ctype.hasType(ns.SiteToSiteClient):
            addr = dev.getS(ns.pppLocalAddress, rdf.IPv4Address).toString()
        else:
            addr = dev.getS(ns.pppRemoteAddress, rdf.IPv4Address).toString()
        return addr

    # XXX: reversing the PPP address doesn't usually make much sense
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_ppp_address_reverse(self, ctx, data):
        dev = self._get_selected_device(ctx)

        # Use local PPP address for site-to-site connections, remote otherwise
        addr = None
        ctype = dev.getS(ns.connectionType)
        if ctype.hasType(ns.SiteToSiteClient):
            addr = dev.getS(ns.pppLocalAddress, rdf.IPv4Address).toString()
        else:
            addr = dev.getS(ns.pppRemoteAddress, rdf.IPv4Address).toString()

        return self._reverse_lookup(addr, u'\u00a0')

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_ppp_device(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return dev.getS(ns.deviceName, rdf.String)

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_ppp_mtu(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return dev.getS(ns.mtu, rdf.Integer)

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_total_rxtx_bytes(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return 'RX %s / TX %s' % (uihelpers.render_transfer_amount_bytes(dev.getS(ns.txBytesCounter, rdf.Integer)),   # rx/tx order intentional
                                  uihelpers.render_transfer_amount_bytes(dev.getS(ns.rxBytesCounter, rdf.Integer)))

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_total_rxtx_packets(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return 'RX %d / TX %d' % (dev.getS(ns.txPacketsCounter, rdf.Integer),   # rx/tx order intentional
                                  dev.getS(ns.rxPacketsCounter, rdf.Integer))
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_current_rxtx(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return 'RX %s / TX %s' % (uihelpers.render_transfer_rate_bits(dev.getS(ns.txRateCurrent, rdf.Float)),   # rx/tx order intentional
                                  uihelpers.render_transfer_rate_bits(dev.getS(ns.rxRateCurrent, rdf.Float)))
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_maximum_rxtx(self, ctx, data):
        dev = self._get_selected_device(ctx)
        return 'RX %s / TX %s' % (uihelpers.render_transfer_rate_bits(dev.getS(ns.txRateMaximum, rdf.Float)),   # rx/tx order intentional
                                  uihelpers.render_transfer_rate_bits(dev.getS(ns.rxRateMaximum, rdf.Float)))
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_psk(self, ctx, data):
        dev = self._get_selected_device(ctx)
        pskindex = dev.getS(ns.ipsecPskIndex, rdf.Integer)
        if pskindex == 0:
            return 'Primary'
        else:
            return 'Secondary'

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_natt_ok(self, ctx, data):
        dev = self._get_selected_device(ctx)
        encaps = dev.getS(ns.ipsecEncapsulationMode)
        if encaps.hasType(ns.EspOverUdp):
            return 'Yes'
        else:
            return 'No'
            
    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_connection_restricted(self, ctx, data):
        dev = self._get_selected_device(ctx)
        if dev.getS(ns.restrictedConnection, rdf.Boolean):
            return 'Yes'
        else:
            return 'No'

    @db.transact()  # XXX: see discussion above near _reverse_lookup()
    @saferender()
    def render_selected_device_connection_s2s_type(self, ctx, data):
        dev = self._get_selected_device(ctx)
        ctype = dev.getS(ns.connectionType)
        if ctype.hasType(ns.SiteToSiteClient):
            return 'Initiate connection'
        elif ctype.hasType(ns.SiteToSiteServer):
            return 'Respond to a connection'
        else:
            return ''

    @db.transact()
    @saferender()
    def render_primary_psk(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.preSharedKeys):
            for psk in ui_root.getS(ns_ui.preSharedKeys, rdf.Seq(rdf.Type(ns_ui.PreSharedKey))):
                # return first
                return psk.getS(ns_ui.preSharedKey, rdf.String)
        else:
            return ''
        
# --------------------------------------------------------------------------

# XXX: unused now
class ContextHelpRenderers:
    @saferender()
    def render_context_help(self, ctx, data):
        return doclibrary.patternLoader(self.template, 'contexthelp', default=T.invisible())

# --------------------------------------------------------------------------

class MiscRenderers:
    def render_customer_logo_customization_maybe(self, ctx, data):
        if os.path.exists(constants.CUSTOMER_LOGO):
            t = T.div(id='context-customer-logo')[u'\u00a0']  # paranoia
            return t
        else:
            # nbsp ensures proper height; this is only used for user page
            t = T.div(id='context')[u'\u00a0']
            return t

    def _config_has_public_interface(self):
        cfg_root = helpers.get_config()
        if cfg_root.hasS(ns.networkConfig) and cfg_root.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig)).hasS(ns.publicInterface):
            return True
        return False

    def _config_has_private_interface(self):
        cfg_root = helpers.get_config()
        if cfg_root.hasS(ns.networkConfig) and cfg_root.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig)).hasS(ns.privateInterface):
            return True
        return False

    @saferender()
    def render_user_agent(self, ctx, data):
        request = inevow.IRequest(ctx)
        return request.getHeader('User-Agent')
    
    @saferender()
    def render_if_local(self, ctx, data):
        mind = self.get_mind()
        if mind is not None:
            if mind.isLocal():
                return ctx.tag
            else:
                return ''
        else:
            return ''

    @saferender()
    def render_if_not_local(self, ctx, data):
        mind = self.get_mind()
        if mind is not None:
            if mind.isLocal():
                return ''
            else:
                return ctx.tag
        else:
            return ''

    @saferender()
    def render_logged_in_user(self, ctx, data):
        return self.get_logged_in_username()
    
    @saferender()
    def render_legal_notice_uri(self, ctx, data):
        return ctx.tag(href=constants.WEBUI_LEGAL_NOTICE_URI, target='_blank')

    @saferender()
    def render_datetime(self, ctx, data):
        return self.get_date_and_time()
    
    @saferender()
    def render_software_version(self, ctx, data):
        return self.get_product_version()

    @saferender()
    def render_latest_software_version(self, ctx, data):
        return self.get_latest_software_version(ajax=False)

    @saferender()
    def render_update_available(self, ctx, data):
        return self.get_update_available(ajax=False)

    @saferender()
    def get_update_available(self, ajax=False):
        update_info = helpers.get_db_root().getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))
        latest = update_info.getS(ns_ui.latestKnownVersion, rdf.String)
        current = helpers.get_product_version()
        if (latest != '') and (helpers.compare_product_versions(latest, current) > 0):
            return '(update available)'
        return ''

    @saferender()
    def render_status(self, ctx, data):
        status_class, status_text, substatus_class, substatus_text = self.get_status_overview_information()
        ctx.tag(_class=status_class)[status_text]
        return ctx.tag

    @saferender()
    def render_substatus(self, ctx, data):
        status_class, status_text, substatus_class, substatus_text = self.get_status_overview_information()
        ctx.tag(_class=substatus_class)[substatus_text]
        return ctx.tag

    @saferender()
    def render_dynamic_javascript(self, ctx, data):
        # XXX: in some cases (apparently when redirecting requests) this produces harmless
        # error logs, see #684.  The underlying culprit is that request.getRootURL() returns
        # None (apparently); ctx and request are not None.
        if ctx is None:
            _log.warning('render_dynamic_javascript: ctx is None')
        else:
            request = inevow.IRequest(ctx)
            if request is None:
                _log.warning('render_dynamic_javascript: ctx -> request is None')

        # XXX: this provides javascript a way to load and redirect sanely
        rooturi = self.build_uri(ctx, '')
        hosturi1 = url.URL.fromString('http://%s/' % rooturi.netloc)
        hosturi2 = url.URL.fromString('https://%s/' % rooturi.netloc)
        timeouturi = url.URL.fromString('http://%s' % rooturi.netloc)
        str = textwrap.dedent("""
        // <![CDATA[
        webui_root_uri = "%(rooturi)s";
        host_root_http_uri = "%(hosturi1)s";
        host_root_https_uri = "%(hosturi2)s";
        global_timeout_uri = "%(timeouturi)s";
        // ]]>
        """ % {'rooturi':rooturi, 'hosturi1':hosturi1, 'hosturi2':hosturi2, 'timeouturi':timeouturi})

        # raw string required for JS CDATA hack
        ctx.tag[T.raw(str)]
        return ctx.tag

    def get_status_overview_information(self, ajax=False):
        st_root = helpers.get_status()
        mgr = self.master.l2tpmanager

        status_class, status_text = '', ''
        substatus_class, substatus_text = '', ''
        if mgr is None:
            status_class, status_text = 'warning', 'Inactive'
            substatus_class, substatus_text = '', ''
        else:
            st = mgr.getState()
            if st == l2tpmanager.L2TPManager.STATE_RUNNING:
                status_class, status_text, substatus_class, substatus_text, status_ok = uihelpers.get_status_and_substatus()
            elif st == l2tpmanager.L2TPManager.STATE_STOPPED:
                status_class, status_text = '', 'Inactive'
                substatus_class, substatus_text = '', ''
            elif st == l2tpmanager.L2TPManager.STATE_STARTING:
                status_class, status_text = '', 'Starting'
                substatus_class, substatus_text = '', ''
            elif st == l2tpmanager.L2TPManager.STATE_STOPPING:
                status_class, status_text = '', 'Stopping'
                substatus_class, substatus_text = '', ''
            else:
                raise Exception('unexpected state: %s' % st)

        # if watchdog is on the verge of taking action, override status line
        if self.master.watchdog_action_is_pending():
            status_class, status_text = 'error', 'Internal error'
            substatus_class, substatus_text = '', 'Reboot pending...'
        elif self.master.periodic_reboot_is_pending():
            status_class, status_text = 'warning', 'Maintenance reboot'
            substatus_class, substatus_text = '', 'Reboot pending...'

        return status_class, status_text, substatus_class, substatus_text
    
    def get_status_overview_line(self, ajax=False):
        status_class, status_text, substatus_class, substatus_text = self.get_status_overview_information()

        if not ajax:
            return T.span[T.span(_class='header-text-label')['Status: '], T.span(_class=status_class, id='header-status-text')[status_text]]
        else:
            return '%s\t%s\t%s\t%s' % (status_class, status_text, substatus_class, substatus_text)

    def get_software_version_line(self, show_update=False, ajax=False):
        version_text = self.get_product_version()
        update_text = ''
        try:
            update_info = helpers.get_db_root().getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))
            latest = update_info.getS(ns_ui.latestKnownVersion, rdf.String)
            current = helpers.get_product_version()
            _log.debug('comparing versions -> latest=%s, current=%s' % (latest, current))
            if (latest != '') and (helpers.compare_product_versions(latest, current) > 0) and show_update:
                update_text = ' (update available)'
        except:
            _log.exception('cannot check whether update is available')

        if not ajax:
            return T.span[T.span(_class='header-text-label')['Software Version: '],
                          T.span(_class='header-text-normal', id='header-status-software-version')['%s' % version_text],
                          T.span[update_text]]
        else:
            return '%s%s' % (version_text, update_text)

    def get_user_connections_overview_line(self, ajax=False):
        count_text = '0'

        if self.service_active():
            try:
                lm = licensemanager.LicenseMonitor()
                count, limit, limit_leeway = lm.count_normal_users()
                count_text = '%d' % count
            except:
                _log.exception('cannot count users')

        if not ajax:
            return T.span[T.span(_class='header-text-label')['User Connections: '],
                          T.span(_class='header-text-normal', id='header-status-users-text')['%s' % count_text]]
        else:
            return count_text

    def get_s2s_connections_overview_line(self, ajax=False):
        count_text = '0'
        if self.service_active():
            try:
                lm = licensemanager.LicenseMonitor()
                count, limit, limit_leeway = lm.count_site_to_site_users()
                count_text = '%d' % count
            except:
                _log.exception('cannot count users')

        if not ajax:
            return T.span[T.span(_class='header-text-label')['Site-to-Site Connections: '],
                          T.span(_class='header-text-normal')['%s' % count_text]]
        else:
            return count_text

    def get_logged_in_user_line(self, logout_uri=None, ajax=False):
        username = self.get_logged_in_username()
            
        if logout_uri is not None:
            logout_span = T.span(_class='header-logout')['[ ', T.a(href=logout_uri)['Logout'], ' ]']
        else:
            logout_span = T.span['']

        if not ajax:
            return T.span[T.span[T.span(_class='header-text-label')['User: '],
                                 T.span(_class='header-text-normal', id='header-status-username')['%s' % username]],
                          logout_span]
        else:
            return username

    def get_date_and_time_line(self, ajax=False):
        sync = ''
        try:
            if helpers.check_marker_file(constants.TIMESYNC_PERSISTENT_TIMESTAMP_FILE):
                # synced at least once, not necessarily on this boot
                if helpers.check_marker_file(constants.TIMESYNC_TIMESTAMP_FILE):
                    # synced on this boot
                    sync = ''
                else:
                    # synced sometime in the past, not on this boot
                    sync = ''
            else:
                # never synchronized
                # XXX: show this?
                sync = ''
        except:
            pass
            
        if not ajax:
            return T.span(id='header-status-date-and-time')[self.get_date_and_time(), sync]
        else:
            return '%s%s' % (self.get_date_and_time(), sync)

    @saferender(default='')
    def get_license_key(self, ajax=False):
        return helpers.get_license_info().getS(ns_ui.licenseKey, rdf.String)

    @saferender(default='')
    def get_license_key_or_demo(self, ajax=False):
        licinfo = helpers.get_license_info()
        if licinfo.hasS(ns_ui.isDemoLicense) and licinfo.getS(ns_ui.isDemoLicense, rdf.Boolean):
            return ''
        elif licinfo.hasS(ns_ui.licenseKey) and licinfo.getS(ns_ui.licenseKey, rdf.String) != '':
            return licinfo.getS(ns_ui.licenseKey, rdf.String)
        return ''

    @saferender(default='')
    def get_license_name(self, ajax=False):
        return helpers.get_license_info().getS(ns_ui.licenseString, rdf.String)

    @saferender(default='')
    def get_license_name_or_demo(self, ajax=False):
        licinfo = helpers.get_license_info()
        if licinfo.hasS(ns_ui.isDemoLicense) and licinfo.getS(ns_ui.isDemoLicense, rdf.Boolean):
            lm = licensemanager.LicenseMonitor()
            lic_demo, lic_demo_expiry, lic_demo_left = lm.check_demo_license()
            lic_days_left = helpers.timedelta_to_seconds(lic_demo_left) / float(24*60*60)
            return 'Demo license (%s left)' % uihelpers.render_timedelta(lic_demo_left)
        elif licinfo.hasS(ns_ui.licenseString) and licinfo.getS(ns_ui.licenseString, rdf.String) != '':
            return licinfo.getS(ns_ui.licenseString, rdf.String)
        else:
            return ''

    @saferender(default='0')
    def get_license_user_limit_line(self, ajax=False):
        return str(helpers.get_license_info().getS(ns_ui.maxNormalConnections, rdf.Integer))

    @saferender(default='0')
    def get_license_site_to_site_limit_line(self, ajax=False):
        return str(helpers.get_license_info().getS(ns_ui.maxSiteToSiteConnections, rdf.Integer))

    @saferender()
    def get_cpu_usage(self, ajax=False):
        st_root = helpers.get_global_status()
        pct = _render_percentage(st_root.getS(ns.cpuUsage, rdf.Float))
        t = st_root.getS(ns.cpuCount, rdf.Integer)
        if t == 1:
            cnt = '%d CPU' % t
        else:
            cnt = '%d CPUs' % t
        return '%s of %s' % (pct, cnt)
    
    @saferender()
    def get_disk_usage(self, ajax=False):
        st_root = helpers.get_global_status()
        pct = _render_percentage(st_root.getS(ns.diskUsage, rdf.Float))
        tot = '%.1f MB' % st_root.getS(ns.diskTotal, rdf.Float)
        return '%s of %s' % (pct, tot)
    
    @saferender()
    def get_memory_usage(self, ajax=False):
        st_root = helpers.get_global_status()
        pct = _render_percentage(st_root.getS(ns.memoryUsage, rdf.Float))
        tot = '%d MiB' % int(st_root.getS(ns.memoryTotal, rdf.Integer) / 1024)
        return '%s of %s' % (pct, tot)
    
    @saferender()
    def get_swap_usage(self, ajax=False):
        st_root = helpers.get_global_status()
        pct = _render_percentage(st_root.getS(ns.swapUsage, rdf.Float))
        tot = '%d MiB' % int(st_root.getS(ns.swapTotal, rdf.Integer) / 1024)
        return '%s of %s' % (pct, tot)

    @saferender()
    def get_service_uptime(self, ajax=False):
        st_root = helpers.get_status()
        return _render_datetime_delta(st_root.getS(ns.startTime, rdf.Datetime))
    
    @saferender()
    def get_latest_software_version(self, ajax=False):
        res = uihelpers.get_latest_product_version()
        if res is None:
            res = ''
        return res

    @saferender()
    def get_public_address(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_public_interface():
            try:
                return st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).toString()
            except:
                return '...'
        return ''
    
    @saferender()
    def get_public_interface_string(self, ajax=False):
        st_root = helpers.get_status()
        return '(%s)' % st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.deviceName, rdf.String)
    
    @saferender()
    def get_public_mac(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_public_interface():
            try:
                return st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.macAddress, rdf.String)
            except:
                return '...'
        return ''
    
    @saferender()
    def get_public_rxtx_summary(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_public_interface():
            try:
                return 'RX %s / TX %s' % (uihelpers.render_transfer_rate_bits(st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.rxRateCurrent, rdf.Float)), uihelpers.render_transfer_rate_bits(st_root.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface)).getS(ns.txRateCurrent, rdf.Float)))
            except:
                return '...'
        return ''
    
    @saferender()
    def get_private_address(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_private_interface():
            try:
                return st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.ipAddress, rdf.IPv4AddressSubnet).toString()
            except:
                return '...'
        return ''

    @saferender()
    def get_private_interface_string(self, ajax=False):
        st_root = helpers.get_status()
        if st_root.hasS(ns.privateInterface):
            return '(%s)' % st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.deviceName, rdf.String)
        return ''
    
    @saferender()
    def get_private_mac(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_private_interface():
            try:
                return st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.macAddress, rdf.String)
            except:
                return '...'
        return ''

    @saferender()
    def get_private_rxtx_summary(self, ajax=False):
        st_root = helpers.get_status()

        if self._config_has_private_interface():
            try:
                return 'RX %s / TX %s' % (uihelpers.render_transfer_rate_bits(st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.rxRateCurrent, rdf.Float)), uihelpers.render_transfer_rate_bits(st_root.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface)).getS(ns.txRateCurrent, rdf.Float)))
            except:
                return '...'
        return ''
            
    @saferender()
    def get_server_uptime(self, ajax=False):
        return uihelpers.render_timedelta(datetime.timedelta(0, helpers.get_uptime(), 0))

    @saferender()
    def get_management_connection_status(self, ajax=False):
        have_connection = self.master.managementconnection.is_active()
        global_st = helpers.get_global_status()
        
        if have_connection:
            if global_st.hasS(ns.behindNat) and global_st.getS(ns.behindNat, rdf.Boolean):
                return 'Connected (NAT)'
            else:
                return 'Connected'
        else:
            return 'Not connected'

    @saferender()
    def render_management_connection_status(self, ctx, data):
        return self.get_management_connection_status(ajax=False)
    
    @saferender()
    def render_license_key(self, ctx, data):
        return self.get_license_key()

    @saferender()
    def render_license_name(self, ctx, data):
        return self.get_license_name()

    @saferender()
    def render_license_user_limit(self, ctx, data):
        return self.get_license_user_limit_line()

    @saferender()
    def render_license_site_to_site_limit(self, ctx, data):
        return self.get_license_site_to_site_limit_line()
    
    @saferender()
    def render_license_key_or_demo(self, ctx, data):
        return self.get_license_key_or_demo(ajax=False)

    @saferender()
    def render_license_name_or_demo(self, ctx, data):
        return self.get_license_name_or_demo(ajax=False)
        
    def get_ajax_status(self):
        # XXX: unicode strings are sent as UTF-8 to client-side Javascript
        # this works, but document why (page encoding is utf-8?)
        def _fix_string(x):
            if isinstance(x, str):
                return x
            if isinstance(x, unicode):
                return x.encode('utf-8')
            
        # This must be synced against admin_ajaxupdate.js
        vals = [self.get_logged_in_user_line(ajax=True),               # 0
                self.get_status_overview_line(ajax=True),              # 1
                self.get_user_connections_overview_line(ajax=True),    # 2
                self.get_s2s_connections_overview_line(ajax=True),     # 3
                self.get_software_version_line(ajax=True),             # 4
                self.get_date_and_time_line(ajax=True),                # 5
                self.get_license_key(ajax=True),                       # 6
                self.get_license_key_or_demo(ajax=True),               # 7
                self.get_license_name(ajax=True),                      # 8
                self.get_license_name_or_demo(ajax=True),              # 9
                self.get_license_user_limit_line(ajax=True),           # 10
                self.get_license_site_to_site_limit_line(ajax=True),   # 11
                self.get_cpu_usage(ajax=True),                         # 12
                self.get_disk_usage(ajax=True),                        # 13
                self.get_memory_usage(ajax=True),                      # 14
                self.get_swap_usage(ajax=True),                        # 15
                self.get_service_uptime(ajax=True),                    # 16
                self.get_latest_software_version(ajax=True),           # 17
                self.get_update_available(ajax=True),                  # 18
                self.get_public_address(ajax=True),                    # 19
                self.get_public_interface_string(ajax=True),           # 20
                self.get_public_mac(ajax=True),                        # 21
                self.get_public_rxtx_summary(ajax=True),               # 22
                self.get_private_address(ajax=True),                   # 23
                self.get_private_interface_string(ajax=True),          # 24
                self.get_private_mac(ajax=True),                       # 25
                self.get_private_rxtx_summary(ajax=True),              # 26
                self.get_server_uptime(ajax=True),                     # 27
                self.get_dns_wins_overview(ajax=True),                 # 28
                self.get_router_overview(ajax=True),                   # 29
                self.get_site_to_site_overview(ajax=True),             # 30
                self.get_management_connection_status(ajax=True),      # 31
                self.get_public_dyndns_line(ajax=True),                # 32
                ]

        vals = map(_fix_string, vals)
        # NB: no newline after last line (does not really matter)
        res = '\n'.join(vals)
        return res

    def render_changelog(self, ctx, data):
        # XXX: to versioninfo module?
        def _parse_signed_off_date(signed_off):
            _re = re.compile(r'^(.*? <.*?>)\s+(.*?)(\s+(\+.*?))?$')
            m = _re.match(signed_off)
            if m is None:
                raise Exception('cannot parse signed off: %s' % signed_off)

            datetime_str = m.group(2)
            timeoffset_str = m.group(4)  # may be None

            # try a few formats
            dt = None
            try:
                # unexpected format where timestamp is not GMT
                if (dt is None) and (timeoffset_str is not None) and (timeoffset_str != '+0000'):
                    t = '%s %s' % (datetime_str, timeoffset_str)
                    dt = datetime.datetime.utcfromtimestamp(time.mktime(time.strptime(t, '%a, %d %b %Y %H:%M:%S %z')))
            except:
                _log.exception('failed to parse datetime')
            
            try:
                # expected format
                if (dt is None):
                    t = '%s' % datetime_str
                    dt = datetime.datetime.utcfromtimestamp(time.mktime(time.strptime(t, '%a, %d %b %Y %H:%M:%S')))
            except:
                _log.exception('failed to parse datetime')
            
            if dt is None:
                raise Exception('cannot parse signed off: %s' % signed_off)
            return dt

        # NB: ctx.tag contains the form renderer - so we place ctx.tag in the
        # relevant div.
        try:
            clist = T.div(_class='changelog')
            curr_version = helpers.get_product_version()

            changelog = None
            try:
                changelog = helpers.get_db_root().getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo)).getS(ns_ui.changeLog, rdf.String)
            except:
                _log.exception('cannot get changelog from rdf database, falling back to local version')
                changelog = versioninfo.get_changelog()
                
            update_button_rendered = False
            first_entry = True
            for [version, lines] in versioninfo.get_changelog_info(startversion=None, changelog=changelog):
                rc = helpers.compare_product_versions(curr_version, version)
                if rc > 0:
                    verclass, verappend = 'old-version', ''
                elif rc == 0:
                    verclass, verappend = 'current-version', '(current version)'
                else:
                    verclass, verappend = 'new-version', '(update available)'

                # add a bogus first entry in case no updates are available
                if first_entry and (verclass != 'new-version'):
                    tmpdiv = T.div(_class='new-version')
                    tmpdiv[T.h3['No updates available']]
                    clist[tmpdiv]
                first_entry = False

                verdiv = T.div(_class=verclass)
                datediv = T.div(_class='changelog-date')
                verdiv[datediv]
                verdiv[T.h3['%s %s' % (version, verappend)]]

                try:
                    # try to render very sanely
                    [version, bullets, signed_off] = versioninfo.parse_changelog_entry(lines)

                    # attempt to present signed off date in a readable manner, otherwise fall back to the string itself
                    try:
                        # XXX: this could go to versioninfo module
                        signed_off_date = _parse_signed_off_date(signed_off)
                        datediv[uihelpers.get_timezone_helper().render_datetime(signed_off_date)]
                    except:
                        _log.exception('cannot parse signed_off, using verbatim')
                        datediv[signed_off]

                    ul = T.ul()
                    for b in bullets:
                        ul[T.li[b]]
                    verdiv[ul]
                except:
                    # fallback renderer
                    first = True
                    for l in lines.split('\n'):
                        l = l.strip()
                        if not first:
                            verdiv[T.br()]
                        first = False
                        verdiv[l]

                if verclass == 'new-version' and (not update_button_rendered):
                    # XXX: this is definitely a pretty bad interface between the update
                    # page and a 'renderer'.
                    update_button_rendered = True
                    verdiv[ctx.tag]
                    verdiv[T.div(_class='cut')[u'\u00a0']]  # XXX: see adminpage.xhtml, css dependency

                clist[verdiv]

            return clist
        except:
            _log.exception('cannot get changelog')
            return 'Changelog not available.'

class CommonRenderers(StatusRenderers, MiscRenderers, ContextHelpRenderers):
    """A hodgepodge of renderers.

    Basically contains all renderers defined in this file.
    """
