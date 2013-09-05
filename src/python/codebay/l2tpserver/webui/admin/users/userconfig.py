"""Administrator configuration pages."""
__docformat__ = 'epytext en'

import formal

from codebay.common import rdf
from codebay.common import datatypes
from codebay.common import logger

from codebay.nevow.formalutils import formdatatypes as dt
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver import constants
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import uidatahelpers
from codebay.l2tpserver.webui import commonpage

_log = logger.get('l2tpserver.webui.admin.users.userconfig')
        
class UsersPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/users/userconfig.xhtml'
    pagetitle = 'Configuration / User Accounts'
    
    def create_radius_group(self, ctx, form):
        g = formalutils.CollapsibleGroup('radius', label='RADIUS Servers')
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseRadius))
        g.add(formalutils.Field('server1', formal.String(required=False), label='Primary RADIUS server address'))
        g.add(formalutils.Field('serverport1',
                                formal.Integer(required=False, validators=[formal.RangeValidator(min=1, max=65535)]),
                                label='Primary RADIUS server port'))
        g.add(formalutils.Field('secret1', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='Primary RADIUS shared secret'))
        g.add(formalutils.Field('server2', formal.String(required=False), label='Secondary RADIUS server address'))
        g.add(formalutils.Field('serverport2',
                                formal.Integer(required=False, validators=[formal.RangeValidator(min=1, max=65535)]),
                                label='Secondary RADIUS server port'))
        g.add(formalutils.Field('secret2', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='Secondary RADIUS shared secret'))
        g.add(formalutils.Field('nasidentifier', formal.String(required=False),
                                label='NAS Identifier'))
        return g

    def _create_user_list_entry(self, index):
        g = formalutils.CollapsibleGroup(str(index), label='')
        g.setCollapsed(False)
        g.add(formalutils.Field('username', formal.String(required=True), label='Username'))
        g.add(formalutils.Field('password', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='Set password'))
        g.add(formalutils.Field('fixed_ip', dt.FormIPv4Address(required=False), label='Fixed IP address'))
        g.add(formalutils.Field('admin_rights', formal.Boolean(required=True), label='Allow VPNease administration'))
        g.add(formalutils.Field('vpn_rights', formal.Boolean(required=True), label='Allow VPN access'))
        return g
        
    def create_users_group(self, ctx, form):
        # XXX: _group is unnecessary in name
        g = formalutils.DynamicList('userlist_group', label='Users', childCreationCallback=self._create_user_list_entry)
        g.setCollapsible(True)
        g.setCollapsed(False)
        
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.users):
            for idx, user in enumerate(ui_root.getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User)))):
                g.add(self._create_user_list_entry(idx))

        return g

    def fill_radius_group(self, ctx, form, g):
        fda = formalutils.FormDataAccessor(form, ['radius'], ctx)
        ui_root = helpers.get_ui_config()

        fda['server1'] = ui_root.getS(ns_ui.radiusPrimaryServer, rdf.String)
        fda['serverport1'] = ui_root.getS(ns_ui.radiusPrimaryServerPort, rdf.Integer)
        fda['secret1'] = ui_root.getS(ns_ui.radiusPrimarySecret, rdf.String)
        fda['server2'] = ui_root.getS(ns_ui.radiusSecondaryServer, rdf.String)
        fda['serverport2'] = ui_root.getS(ns_ui.radiusSecondaryServerPort, rdf.Integer)
        fda['secret2'] = ui_root.getS(ns_ui.radiusSecondarySecret, rdf.String)
        fda['nasidentifier'] = ui_root.getS(ns_ui.radiusNasIdentifier, rdf.String)
        
    def fill_users_group(self, ctx, form, g):
        fda = formalutils.FormDataAccessor(form, ['userlist_group'], ctx)

        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.users):
            for idx, user in enumerate(ui_root.getS(ns_ui.users, rdf.Seq(rdf.Type(ns_ui.User)))):
                try:
                    g = self._create_user_list_entry(idx)

                    fda_user = fda.descend(str(idx))
                    fda_user['username'] = user.getS(ns_ui.username, rdf.String)
                    #fda_user['password'] = user.getS(ns_ui.password, rdf.String)
                    fda_user['password'] = ''
                    if user.hasS(ns_ui.fixedIp):
                        fda_user['fixed_ip'] = user.getS(ns_ui.fixedIp, rdf.IPv4Address)
                    else:
                        fda_user['fixed_ip'] = None
                    fda_user['admin_rights'] = user.getS(ns_ui.adminRights, rdf.Boolean)
                    fda_user['vpn_rights'] = user.getS(ns_ui.vpnRights, rdf.Boolean)
                except:
                    _log.exception('cannot fill data for a user, skipping')

    @db.transact()
    def form_config(self, ctx):
        form = formal.Form()

        g = self.create_radius_group(ctx, form)
        form.add(g)
        try:
            self.fill_radius_group(ctx, form, g)
        except:
            _log.exception('failed to fill radius group, skipping')
        
        g = self.create_users_group(ctx, form)
        form.add(g)
        try:
            self.fill_users_group(ctx, form, g)
        except:
            _log.exception('failed to fill users group, skipping')

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False) 
        return form
   
    def save_radius(self, ctx, form, data):
        ui_root = helpers.get_new_ui_config()
        fda = formalutils.FormDataAccessor(form, ['radius'], ctx)

        val = ''
        if fda.has_key('server1') and fda['server1'] is not None:
            val = fda['server1']
        ui_root.setS(ns_ui.radiusPrimaryServer, rdf.String, val)

        val = 1812
        if fda.has_key('serverport1') and fda['serverport1'] is not None:
            val = fda['serverport1']
        ui_root.setS(ns_ui.radiusPrimaryServerPort, rdf.Integer, val)

        val = ''
        if fda.has_key('secret1') and fda['secret1'] is not None:
            val = fda['secret1']
        ui_root.setS(ns_ui.radiusPrimarySecret, rdf.String, val)
        
        val = ''
        if fda.has_key('server2') and fda['server2'] is not None:
            val = fda['server2']
        ui_root.setS(ns_ui.radiusSecondaryServer, rdf.String, val)
        
        val = 1812
        if fda.has_key('serverport2') and fda['serverport2'] is not None:
            val = fda['serverport2']
        ui_root.setS(ns_ui.radiusSecondaryServerPort, rdf.Integer, val)
        
        val = ''
        if fda.has_key('secret2') and fda['secret2'] is not None:
            val = fda['secret2']
        ui_root.setS(ns_ui.radiusSecondarySecret, rdf.String, val)

        val = ''
        if fda.has_key('nasidentifier') and fda['nasidentifier'] is not None:
            val = fda['nasidentifier']
        ui_root.setS(ns_ui.radiusNasIdentifier, rdf.String, val)

    def save_user_list(self, ctx, form, data, userpw_dict):
        def _save_user_to_rdf(user, fda):
            username = fda['username']
            user.setS(ns_ui.username, rdf.String, username)

            # Password is tricky; we look up the previous config, and if a user
            # of this name existed and it had a password, use that password unless
            # a new one is specified.  This is not perfect, but at least it works
            # correctly w.r.t. changed username.  Note however that we do not track
            # user identity as such across a name change: if admin removes user XYZ
            # and adds a new user with name XYZ (with empty password field), that
            # user will simply inherit the older user XYZ password.
            
            if fda.has_key('password') and (fda['password'] is not None) and (fda['password'] != ''):
                # set hashed password entries
                uihelpers.set_user_password_hashes(user, fda['password'])
            else:
                if userpw_dict.has_key(username):
                    password_plain, password_md5, password_nt = userpw_dict[username]
                    user.setS(ns_ui.passwordMd5, rdf.String, password_md5)
                    user.setS(ns_ui.passwordNtHash, rdf.String, password_nt)
                    user.removeNodes(ns_ui.password)
                else:
                    # this should not happen; log but don't fail badly
                    _log.error('no password in form or userpw dict, should not happen')
                    user.setS(ns_ui.password, rdf.String, '')
                    
            uidatahelpers.save_optional_field_to_rdf(user, ns_ui.fixedIp, rdf.IPv4Address, fda, 'fixed_ip')
            user.setS(ns_ui.adminRights, rdf.Boolean, fda['admin_rights']) 
            user.setS(ns_ui.vpnRights, rdf.Boolean, fda['vpn_rights'])
        
        ui_root = helpers.get_new_ui_config()
        fda = formalutils.FormDataAccessor(form, ['userlist_group'], ctx)
        uidatahelpers.save_dynamic_list_to_rdf(ui_root,
                                               ns_ui.users,
                                               ns_ui.User,
                                               fda,
                                               _save_user_to_rdf)

    def _validate_radius(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, ['radius'], ctx)
        ui_root = helpers.get_ui_config()

        # Basic RADIUS validation - currently limit server addresses to IP addresses
        # because of FreeRADIUS DNS lookup issues (lookup happens during startup and
        # failed lookup makes daemon exit)
        server_ip_addrs = []
        for srv, prt, sec in [ ('server1', 'serverport1', 'secret1'),
                               ('server2', 'serverport2', 'secret2') ]:
            has_ip = False
            if fda.has_key(srv) and fda[srv] is not None and fda[srv] != '':
                # must be IP if nonempty
                has_ip = True
                ip_ok = False
                try:
                    tmp = datatypes.IPv4Address.fromString(fda[srv])
                    server_ip_addrs.append(tmp)
                    ip_ok = True
                except:
                    _log.exception('cannot parse IP address from user input: %s' % fda[srv])
                if not ip_ok:
                    fda.add_error(srv, 'Invalid IP address')
                
            if fda.has_key(prt) and fda[prt] is not None:
                pass # already integer and range validated
            else:
                if has_ip:
                    fda.add_error(prt, 'Required when server defined (suggested value: 1812)')

            if fda.has_key(sec) and fda[sec] is not None:
                if not uihelpers.check_radius_secret_characters(fda[sec]):
                    fda.add_error(sec, 'Invalid characters')
            else:
                if has_ip:
                    fda.add_error(sec, 'Required when server defined')

        # If two servers, don't allow same IP for both
        if len(server_ip_addrs) == 2:
            if server_ip_addrs[0] == server_ip_addrs[1]:
                fda.add_error('server2', 'Secondary server address cannot be the same as primary server address')
                
        # Nas-Identifier validation
        if fda.has_key('nasidentifier') and fda['nasidentifier'] is not None:
            if not uihelpers.check_radius_nai_identifier_characters(fda['nasidentifier']):
                fda.add_error('nasidentifier', 'Invalid characters')
                
    def _validate_users(self, ctx, form, data, userpw_dict):
        fda = formalutils.FormDataAccessor(form, ['userlist_group'], ctx)
        ui_root = helpers.get_ui_config()

        # user list validation
        idx = 0
        users = []
        while True:
            fda_user = fda.descend(str(idx))
            if len(fda_user.keys()) == 0:
                break
            users.append(fda_user)
            idx += 1

        s2s_server_usernames = []
        if ui_root.hasS(ns_ui.siteToSiteConnections):
            for s2s_conn in ui_root.getS(ns_ui.siteToSiteConnections, rdf.Seq(rdf.Type(ns_ui.SiteToSiteConnection))):
                if s2s_conn.hasS(ns_ui.mode) and s2s_conn.getS(ns_ui.mode, rdf.String) == 'server' and s2s_conn.hasS(ns_ui.username):
                    s2s_server_usernames.append(s2s_conn.getS(ns_ui.username, rdf.String))
            
        usernames_found = []
        fixed_ips_found = []
        for fda_user_index, fda_user in enumerate(users):
            # username checks
            if fda_user.has_key('username'):
                if not uihelpers.check_ppp_username_characters(fda_user['username']):
                    fda_user.add_error('username', 'Invalid characters')
                else:
                    username = fda_user['username']
                    if username in usernames_found:
                        fda_user.add_error('username', 'Duplicate username')
                    elif username in s2s_server_usernames:
                        fda_user.add_error('username', 'Duplicate username (already a site-to-site server-mode connection of that name)')
                    elif len(username) > constants.MAX_USERNAME_LENGTH:
                        fda_user.add_error('username', 'Username too long')
                    else:
                        usernames_found.append(username)

            # password chars
            if fda_user.has_key('password') and (fda_user['password'] is not None):
                if not uihelpers.check_ppp_password_characters(fda_user['password']):
                    fda_user.add_error('password', 'Invalid characters')
                elif len(fda_user['password']) > constants.MAX_PASSWORD_LENGTH:
                    fda_user.add_error('password', 'Password too long')

            # Password is a bit tricky; admin may have changed a username and we don't have
            # any permanent user identifiers that allow us to identify this as the same user
            # and keep its password despite the name change.  So, we require either that the
            # password is set, or that a user previously existed with this username (changed
            # or not !) and use the old password.

            if fda_user.has_key('username') and (fda_user['username'] is not None) and \
                   (not fda_user.has_key('password') or fda_user['password'] is None or fda_user['password'] == ''):
                username = fda_user['username']
                if userpw_dict.has_key(username):
                    # all ok
                    pass
                else:
                    fda_user.add_error('password', 'Required for new users')

            # fixed ip checks

            # XXX: we could also check that the fixed IP is from the
            # PPP subnet to try to prevent admin configuration errors,
            # but this would be too restrictive and is currently not
            # done: a warning would help here.

            if fda_user.has_key('fixed_ip') and (fda_user['fixed_ip'] is not None) and (fda_user['fixed_ip'] != ''):
                fixed_ip_errors = False
                fixed_ip = fda_user['fixed_ip']

                iprange = ui_root.getS(ns_ui.clientAddressRange, rdf.IPv4AddressRange)
                pppsubnet = ui_root.getS(ns_ui.clientSubnet, rdf.IPv4Subnet)

                # The fixed IP may not overlap with other users fixed IP addresses
                if fixed_ip.toString() in fixed_ips_found:
                    fda_user.add_error('fixed_ip', 'Duplicate fixed IP address')
                    fixed_ip_errors = True

                # Check restricted addresses inside PPP subnet
                if pppsubnet.inSubnet(fixed_ip):
                    # The fixed IP must not be from the PPP address range (dynamic allocation pool)
                    if iprange.inRange(fixed_ip):
                        fda_user.add_error('fixed_ip', 'Overlaps with client address range')
                        fixed_ip_errors = True

                    if fixed_ip < pppsubnet.getFirstUsableAddress():
                        fda_user.add_error('fixed_ip', 'First address of the client subnet prohibited')
                        fixed_ip_errors = True
                    elif fixed_ip == pppsubnet.getLastUsableAddress():
                        fda_user.add_error('fixed_ip', 'Last usable address of the client subnet prohibited')
                        fixed_ip_errors = True
                    elif fixed_ip > pppsubnet.getLastUsableAddress():
                        fda_user.add_error('fixed_ip', 'Last address of the client subnet prohibited')
                        fixed_ip_errors = True

                if not fixed_ip_errors:
                    fixed_ips_found.append(fixed_ip.toString())

    def _get_radius_info(self, new_ui_config=False):
        """Return RADIUS information in an array that we can compare later.

        Information included in the array is precisely the fields that, if
        changed, require a full runner restart (instead of just FreeRADIUS
        restart).  Currently it is just the RADIUS server addresses, because
        the are required for ICMP monitoring; note that ports are *not* needed
        here.
        """

        if new_ui_config:
            ui_root = helpers.get_new_ui_config()
        else:
            ui_root = helpers.get_ui_config()
        res = []

        try:
            res.append(ui_root.getS(ns_ui.radiusPrimaryServer, rdf.String))
        except:
            _log.exception('cannot get radius info')
            res.append(None)
            
        try:
            res.append(ui_root.getS(ns_ui.radiusSecondaryServer, rdf.String))
        except:
            _log.exception('cannot get radius info')
            res.append(None)

        return res

    @db.transact()
    def submitted(self, ctx, form, data):    
        fda = formalutils.FormDataAccessor(form, [], ctx)
        pd = uidatahelpers.CreateProtocolData()

        # Save collapsed states first, so they feed back to next round
        for [rdf_uri, key] in [ [ ns_ui.collapseRadius, 'radius' ] ]:
            try:
                # XXX: passing of the hidden _collapsedstate_ parameter is not too clean
                uihelpers.update_collapse_setting(rdf_uri, fda['%s._collapsedstate_' % key])
            except:
                _log.exception('error updating collapsed state for %s' % rdf_uri)

        old_radius_info = None
        new_radius_info = None
        try:
            # Pre-step: collect usernames and passwords in previous config; we'll need
            # them to deal with password changing correctly.
            userpw_dict = uihelpers.get_user_password_dict()
        
            # Basic validation
            fda = formalutils.FormDataAccessor(form, ['userlist_group'], ctx)
            self._validate_users(ctx, form, data, userpw_dict)
            self._validate_radius(ctx, form, data)

            # Intermediate early bail out to avoid saving if there are errors
            fda.finalize_validation()

            # Get old runner-critical RADIUS info for comparison
            old_radius_info = self._get_radius_info(new_ui_config=False)

            # Deep copy UI config to 'new' UI config
            pd.clone_ui_config()

            # Save form data to rdf database
            self.save_radius(ctx, form, data)
            self.save_user_list(ctx, form, data, userpw_dict)

            # Get new runner-critical RADIUS info for comparison
            new_radius_info = self._get_radius_info(new_ui_config=True)
 
            # Save protocol data and finalize validation
            pd.save_protocol_data()
        except:
            _log.exception('validation failed unexpectedly, adding global error')
            fda.add_global_error('Unknown validation error')

        fda.finalize_validation()

        # Check whether a full restart is required or not; although we can edit user
        # information without a full restart (in which case FreeRADIUS is reconfigured
        # and restarted), we can't add, remote, or edit RADIUS server addresses because
        # runner would not get the new server information to its monitoring list.
        
        _log.debug('old radius info: %s, new radius info: %s' % (old_radius_info, new_radius_info))
        
        full_restart_required = (old_radius_info != new_radius_info)

        if full_restart_required:
            _log.info('radius servers changed, full restart required')

            # Activate new config
            pd.activate_protocol_data()

            # Update initial config saved flag
            pd.update_initial_config_saved()

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
        else:
            _log.info('radius servers not changed, only freeradius restart')

            # Nuke unwanted PPP connections first time here, so their corresponding
            # protocol config is intact, leading to a clean teardown.
            try:
                pd.recheck_and_drop_ppp_connections()
            except:
                _log.exception('ppp device recheck failed')
                
            # Activate new config
            # XXX - just change user data here?
            pd.activate_protocol_data()
                    
            # Update initial config saved flag
            pd.update_initial_config_saved()

            try:
                pd.restart_freeradius()  # needs protocol config in place
            except:
                _log.exception('freeradius restart failed')

            # Check again for unwanted PPP devices; teardowns here will currently be ugly
            try:
                pd.recheck_and_drop_ppp_connections()
            except:
                _log.exception('ppp device recheck failed')
                
            # just a fake activation page
            followup = uihelpers.build_uri(ctx, 'status/main.html')
            return uihelpers.reconfigure_page(self.master, ctx, followup_uri=followup)
