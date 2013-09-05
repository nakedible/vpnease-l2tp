"""Administrator configuration pages."""
__docformat__ = 'epytext en'

import formal
from codebay.nevow.formalutils import formdatatypes as dt
from codebay.nevow.formalutils import formalutils

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger

from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver import constants
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import uidatahelpers
from codebay.l2tpserver.webui import commonpage

saferender = uihelpers.saferender

_log = logger.get('l2tpserver.webui.admin.config.sitetositeconfig')

class SiteToSitePage(formal.ResourceMixin, commonpage.AdminPage):
    """Creates site to site configuration form."""
    template = 'admin/config/sitetositeconfig.xhtml'
    pagetitle = 'Configuration / Site-to-Site Connections'

    @saferender()
    def render_s2s_warning_normal(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.clientSubnet) and \
           (ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet) == datatypes.IPv4Subnet.fromString(uidatahelpers.uidefaults.CLIENT_SUBNET)):
            return ''
        else:
            return ctx.tag
    
    @saferender()
    def render_s2s_warning_heavy(self, ctx, data):
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.clientSubnet) and \
           (ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet) == datatypes.IPv4Subnet.fromString(uidatahelpers.uidefaults.CLIENT_SUBNET)):
            return ctx.tag
        else:
            return ''

    def _create_s2s_connection_list_entry(self, index):
        mode_options = [ ('server', 'Respond to a connection from a remote server'),
                         ('client', 'Initiate connection to a remote server') ]

        g = formalutils.CollapsibleGroup(str(index), label='')
        g.setCollapsed(False)
        g.add(formalutils.Field('s2s_username', formal.String(required=True), label='Username'))
        g.add(formalutils.Field('s2s_password', formal.String(required=True),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='Password'))
        g.add(formalutils.Field('s2s_subnets', dt.FormIPv4SubnetList(required=True), label='Remote subnets'))
        g.add(formalutils.Field('s2s_mode', formal.String(required=True),
                                formal.widgetFactory(formal.RadioChoice, options=mode_options),
                                label='Connection mode'))
        g.add(formalutils.Field('s2s_server', formal.String(required=False), label='Remote server address'))
        g.add(formalutils.Field('s2s_psk', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='Remote server pre-shared key'))
        return g

    def create_s2s_list(self, form, ctx):
        conn_list = formalutils.DynamicList('s2s_connections',
                                            label='Site-to-Site Connections',
                                            childCreationCallback=self._create_s2s_connection_list_entry)
        conn_list.setCollapsible(True)
        conn_list.setCollapsed(False)
        return conn_list

    def fill_s2s_list(self, form, ctx, conn_list):
        fda = formalutils.FormDataAccessor(form, ['s2s_connections'], ctx)

        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.siteToSiteConnections):
            for idx, conn in enumerate(ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection)))):
                try:
                    g = self._create_s2s_connection_list_entry(idx)

                    fda_conn = fda.descend(str(idx))
                    fda_conn['s2s_username'] = conn.getS(ns_ui.username, rdf.String)
                    fda_conn['s2s_password'] = conn.getS(ns_ui.password, rdf.String)
                    # XXX: why is this API so weird? why not give the rdf:Seq and get a string in response?
                    uidatahelpers.fill_subnet_list_to_form(conn, ns_ui.subnetList, fda_conn, 's2s_subnets')

                    mode = conn.getS(ns_ui.mode, rdf.String)
                    if mode == 'client':
                        fda_conn['s2s_mode'] = 'client'
                        fda_conn['s2s_psk'] = conn.getS(ns_ui.preSharedKey, rdf.String)
                        fda_conn['s2s_server'] = conn.getS(ns_ui.serverAddress, rdf.String)
                    elif mode == 'server':
                        fda_conn['s2s_mode'] = 'server'
                        fda_conn['s2s_psk'] = ''
                        fda_conn['s2s_server'] = ''
                    else:
                        raise 'unknown mode: %s' % mode

                    conn_list.add(g)
                except:
                    _log.exception('cannot fill data for s2s connection, skipping')

    @db.transact()
    def form_config(self, ctx):
        form = formal.Form()

        g = self.create_s2s_list(form, ctx)
        form.add(g)
        try:
            self.fill_s2s_list(form, ctx, g)
        except:
            _log.exception('cannot fill data for s2s connections, skipping')

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False)
        return form

    def save_s2s_list_data(self, ctx, form, data):
        def _save_connection(conn, fda):
            conn.setS(ns_ui.username, rdf.String, fda['s2s_username'])
            conn.setS(ns_ui.password, rdf.String, fda['s2s_password'])
            uidatahelpers.save_subnet_list_to_rdf(conn, ns_ui.subnetList, fda, 's2s_subnets')
            mode = fda['s2s_mode']
            if mode == 'client':
                conn.setS(ns_ui.mode, rdf.String, 'client')
                conn.setS(ns_ui.preSharedKey, rdf.String, fda['s2s_psk'])
                conn.setS(ns_ui.serverAddress, rdf.String, fda['s2s_server'])
            elif mode == 'server':
                conn.setS(ns_ui.mode, rdf.String, 'server')
            else:
                raise Exception('unknown mode: %s' % mode)

        ui_root = helpers.get_new_ui_config()
        fda = formalutils.FormDataAccessor(form, ['s2s_connections'], ctx)
        uidatahelpers.save_dynamic_list_to_rdf(ui_root,
                                               ns_ui.siteToSiteConnections,
                                               ns_ui.SiteToSiteConnection,
                                               fda,
                                               _save_connection)

    def _validate(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, ['s2s_connections'], ctx)

        # Get some useful stuff for validation
        ui_root = helpers.get_ui_config()
        pub_iface, pub_addr_subnet = None, None
        if ui_root.hasS(ns_ui.internetConnection):
            pub_iface = ui_root.getS(ns_ui.internetConnection, rdf.Type(ns_ui.NetworkConnection))
            pub_addr = pub_iface.getS(ns_ui.address)
            if pub_addr.hasType(ns_ui.StaticAddress):
                pub_addr_subnet = datatypes.IPv4AddressSubnet.fromStrings(pub_addr.getS(ns_ui.ipAddress, rdf.IPv4Address).toString(), pub_addr.getS(ns_ui.subnetMask, rdf.IPv4Address).toString())
        priv_iface, priv_addr_subnet = None, None
        if ui_root.hasS(ns_ui.privateNetworkConnection):
            priv_iface = ui_root.getS(ns_ui.privateNetworkConnection, rdf.Type(ns_ui.NetworkConnection))
            priv_addr = priv_iface.getS(ns_ui.address)
            if priv_addr.hasType(ns_ui.StaticAddress):
                priv_addr_subnet = datatypes.IPv4AddressSubnet.fromStrings(priv_addr.getS(ns_ui.ipAddress, rdf.IPv4Address).toString(), priv_addr.getS(ns_ui.subnetMask, rdf.IPv4Address).toString())
        ppp_subnet = None
        if ui_root.hasS(ns_ui.clientSubnet):
            ppp_subnet = ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet)
            
        # Validate individual site-to-site connections
        idx = 0
        conns = []
        while True:
            fda_conn = fda.descend(str(idx))
            if len(fda_conn.keys()) == 0:
                break
            conns.append(fda_conn)
            idx += 1

        remote_access_usernames = []
        if ui_root.hasS(ns_ui.users):
            for user in ui_root.getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User))):
                if user.hasS(ns_ui.username):
                    remote_access_usernames.append(user.getS(ns_ui.username, rdf.String))

        s2s_server_usernames_found = []
        for fda_conn_index, fda_conn in enumerate(conns):
            if fda_conn.has_key('s2s_username'):
                if not uihelpers.check_ppp_username_characters(fda_conn['s2s_username']):
                    fda_conn.add_error('s2s_username', 'Invalid characters')
                elif len(fda_conn['s2s_username']) > constants.MAX_USERNAME_LENGTH:
                    fda_conn.add_error('s2s_username', 'Username too long')

            if fda_conn.has_key('s2s_password'):
                if not uihelpers.check_ppp_password_characters(fda_conn['s2s_password']):
                    fda_conn.add_error('s2s_password', 'Invalid characters')
                elif len(fda_conn['s2s_password']) > constants.MAX_PASSWORD_LENGTH:
                    fda_conn.add_error('s2s_password', 'Password too long')

            if fda_conn.has_key('s2s_mode'):
                mode = fda_conn['s2s_mode']
                if mode == 'client':
                    # psk and server address are mandatory for client
                    if not fda_conn.has_key('s2s_psk') or fda_conn['s2s_psk'] == '' or fda_conn['s2s_psk'] is None:
                        fda_conn.add_error('s2s_psk', 'Required for initiator')
                    else:
                        if not uihelpers.check_preshared_key_characters(fda_conn['s2s_psk']):
                            fda_conn.add_error('s2s_psk', 'Invalid characters')
                    if not fda_conn.has_key('s2s_server') or fda_conn['s2s_server'] == '' or fda_conn['s2s_server'] is None:
                        fda_conn.add_error('s2s_server', 'Required for initiator')
                    else:
                        if not uihelpers.check_dns_name_characters(fda_conn['s2s_server']):
                            fda_conn.add_error('s2s_server', 'Invalid characters')
                else:  # server
                    # must not have duplicate server-mode names; client mode names may be duplicates
                    if fda_conn.has_key('s2s_username'):
                        username = fda_conn['s2s_username']
                        if username in s2s_server_usernames_found:
                            fda_conn.add_error('s2s_username', 'Duplicate username for server mode connection')
                        elif username in remote_access_usernames:
                            fda_conn.add_error('s2s_username', 'Duplicate username for server mode connection (already a user with that name)')
                        else:
                            s2s_server_usernames_found.append(fda_conn['s2s_username'])
                    
            # check subnets
            if fda_conn.has_key('s2s_subnets'):
                subnets = fda_conn['s2s_subnets']

                # check that list doesn't contain overlap inside itself
                overlap_inside_list = False
                for i in xrange(len(subnets)):
                    for j in xrange(len(subnets)):
                        if i != j:
                            if subnets[i].overlapsWithSubnet(subnets[j]):
                                overlap_inside_list = True
                if overlap_inside_list:
                    fda_conn.add_warning('s2s_subnets', 'Subnets in list overlap')
                
                # check that no element of list overlaps with any other subnet of any other site-to-site connection
                overlap_with_other = False
                for subnet in subnets:
                    for other_conn_index, other_conn in enumerate(conns):
                        if other_conn.has_key('s2s_subnets') and other_conn_index != fda_conn_index:
                            for other_subnet in other_conn['s2s_subnets']:
                                if subnet.overlapsWithSubnet(other_subnet):
                                    overlap_with_other = True
                if overlap_with_other:
                    fda_conn.add_warning('s2s_subnets', 'Remote subnet(s) overlap with other connections')

                # check overlap against public interface
                if pub_addr_subnet is not None:
                    if subnet.overlapsWithSubnet(pub_addr_subnet.getSubnet()):
                        fda_conn.add_warning('s2s_subnets', 'Remote subnet(s) overlap with Internet connection subnet')
                        
                # check overlap against private interface
                if priv_addr_subnet is not None:
                    if subnet.overlapsWithSubnet(priv_addr_subnet.getSubnet()):
                        fda_conn.add_warning('s2s_subnets', 'Remote subnet(s) overlap with private network connection subnet')

                # check overlap against ppp subnet
                if ppp_subnet is not None:
                    if subnet.overlapsWithSubnet(ppp_subnet):
                        fda_conn.add_warning('s2s_subnets', 'Remote subnet(s) overlap with client subnet')

    @db.transact()
    def submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, ['s2s_connections'], ctx)
        pd = uidatahelpers.CreateProtocolData()

        # No collapse states need to be saved for site-to-site connections

        try:
            # Check errors
            self._validate(ctx, form, data)
                
            # Intermediate early bail out to avoid saving if there are errors
            fda.finalize_validation()

            # Deep copy UI config to 'new' UI config
            pd.clone_ui_config()

            # Save form data to rdf database
            self.save_s2s_list_data(ctx, form, data)

            # Convert uidata to protocol data.
            pd.save_protocol_data()
        except:
            _log.exception('validation failed unexpectedly, adding global error')
            fda.add_global_error('Unknown validation error')

        # Finalize
        fda.finalize_validation()

        # XXX: The recheck_and_drop_ppp_connections below does not do
        # anything to site-to-site connections! This does not
        # currently matter because the runner restart follows, but if
        # the site-to-site activation is later modified so that it
        # will not require full restart, the code below must be fixed.

        # Nuke unwanted PPP connections first time here, so their corresponding
        # protocol config is intact, leading to a clean teardown.
        try:
            pd.recheck_and_drop_ppp_connections()
        except:
            _log.exception('ppp device recheck failed')

#         # XXX: this trickery is disabled for now: user config changes require
#         # freeradius restart which is not very sensible now when we restart anyways
#         try:
#             pd.restart_freeradius()  # needs protocol config in place
#         except:
#             _log.exception('freeradius restart failed')
#
#         # Check again for unwanted PPP devices; teardowns here will currently be ugly
#         try:
#             pd.recheck_and_drop_ppp_connections()
#         except:
#             _log.exception('ppp device recheck failed')

        # Activate new config
        pd.activate_protocol_data()
        
        # Update initial config saved flag
        pd.update_initial_config_saved()

        #
        #  XXX: Because we stop, reconfigure, and start here, the user trickery above
        #  is not strictly necessary though it doesn't hurt.  It was left intact because
        #  we might want to try to make site-to-site activation without full restart.
        #  Currently that's not possible because site-to-site changes cause route changes,
        #  for instance.
        #

        #
        #  XXX: It would be cleaner if we could first stop the runner, then change the
        #  config, and then restart it.  If we do that with a deferred, then it is possible
        #  that the user changes the config again before we have time to activate it.
        #  Putting the config into some sort of "staging area" might help.  Currently we
        #  simply assume that runner stop (and start) are robust enough.
        #
        
        # stop, configure, start
        followup = uihelpers.build_uri(ctx, 'status/main.html')
        return uihelpers.reconfigure_and_restart_page(self.master, ctx, followup_uri=followup)

