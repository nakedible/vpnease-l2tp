"""Administrator configuration pages."""
__docformat__ = 'epytext en'

import os, tempfile

from nevow import inevow, rend, tags as T

import formal

from codebay.common import rdf
from codebay.common import logger
from codebay.common import licensekey
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver import helpers
from codebay.l2tpserver import gnomeconfig
from codebay.l2tpserver import constants
from codebay.l2tpserver import zipfiles
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns_ui, ns_zipfiles
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import uidatahelpers
from codebay.l2tpserver.webui.admin import uitexts

_log = logger.get('l2tpserver.webui.admin.management.management')

saferender = uihelpers.saferender

# --------------------------------------------------------------------------

def _check_update_on_next_reboot():
    try:
        ui_root = helpers.get_ui_config()
        if ui_root.hasS(ns_ui.automaticUpdates) and ui_root.getS(ns_ui.automaticUpdates, rdf.Boolean):
            # XXX: duplication
            update_info = helpers.get_db_root().getS(ns_ui.updateInfo, rdf.Type(ns_ui.UpdateInfo))
            latest = update_info.getS(ns_ui.latestKnownVersion, rdf.String)
            current = helpers.get_product_version()
            if (latest != '') and (helpers.compare_product_versions(latest, current) > 0):
                return True
            else:
                return False
        else:
            return False
    except:
        # default, assume False
        _log.exception('cannot determine whether product update happens on next reboot')
        return False

# --------------------------------------------------------------------------

class ManagementPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/management/management.xhtml'
    pagetitle = 'Configuration / License & Maintenance'

    mng_uitexts = uitexts.ManagementTexts()

    def fill_management(self, ctx, fda):
        def _get_access(pub, priv):
            if pub:
                if priv:
                    return 'both'
                else:
                    return 'public'
            else:
                if priv:
                    return 'private'
                else:
                    return 'none'


        ui_root = helpers.get_ui_config()

        tmp = fda.descend('license_group')
        tmp['license_key'] = ui_root.getS(ns_ui.licenseKey, rdf.String)

        tmp = fda.descend('locale_group')
        tmp['timezone'] = ui_root.getS(ns_ui.timezone, rdf.String)
        tmp['keymap'] = ui_root.getS(ns_ui.keymap, rdf.String)

        tmp = fda.descend('reboot_group')
        tmp['reboot_day'] = ui_root.getS(ns_ui.periodicRebootDay, rdf.Integer)
        tmp['reboot_time'] = ui_root.getS(ns_ui.periodicRebootTime, rdf.Integer)
        tmp['automatic_updates'] = ui_root.getS(ns_ui.automaticUpdates, rdf.Boolean)

        tmp = fda.descend('snmp_group')
        tmp['snmp_access'] = _get_access(ui_root.getS(ns_ui.snmpAccessPublic, rdf.Boolean), ui_root.getS(ns_ui.snmpAccessPrivate, rdf.Boolean))
        tmp['snmp_community'] = ui_root.getS(ns_ui.snmpCommunity, rdf.String)

        tmp = fda.descend('remote_group')
        tmp['www_administration'] = _get_access(ui_root.getS(ns_ui.webAccessPublic, rdf.Boolean), ui_root.getS(ns_ui.webAccessPrivate, rdf.Boolean))
        tmp['ssh_connection'] = _get_access(ui_root.getS(ns_ui.sshAccessPublic, rdf.Boolean), ui_root.getS(ns_ui.sshAccessPrivate, rdf.Boolean))

        # XXX: private cert chain / key not currently supported
        tmp = fda.descend('ssl_group')
        tmp['ssl_certificate_chain'] = ''
        tmp['ssl_private_key'] = ''
        if ui_root.hasS(ns_ui.publicSslCertificateChain):
            tmp['ssl_certificate_chain'] = ui_root.getS(ns_ui.publicSslCertificateChain, rdf.String)
        if ui_root.hasS(ns_ui.publicSslPrivateKey):
            tmp['ssl_private_key'] = ui_root.getS(ns_ui.publicSslPrivateKey, rdf.String)

        # XXX: not yet implemented
        #tmp = fda.descend('email_group')
        #tmp['smtp_server'] = ''
        #tmp['smtp_from'] = ''
        #tmp['smtp_to'] = ''
        #if ui_root.hasS(ns_ui.adminEmailSmtpServer):
        #    tmp['smtp_server'] = ui_root.getS(ns_ui.adminEmailSmtpServer, rdf.String)
        #if ui_root.hasS(ns_ui.adminEmailFromAddress):
        #    tmp['smtp_from'] = ui_root.getS(ns_ui.adminEmailFromAddress, rdf.String)
        #if ui_root.hasS(ns_ui.adminEmailToAddresses):
        #    tmp['smtp_to'] = ui_root.getS(ns_ui.adminEmailToAddresses, rdf.String)

    @db.transact()
    def form_management(self, ctx):    
        form = formal.Form()
        fda = formalutils.FormDataAccessor(form, [], ctx)
        tzhelp = uihelpers.TimezoneHelper()
        txt = self.mng_uitexts
        
        ### License

        g = formalutils.CollapsibleGroup('license_group', label=txt.license_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseLicense))
        g.add(formalutils.Field('license_key', formal.String(required=False), label=txt.license_key_label))
        form.add(g)

        ### Locale

        tzoptions = []
        for tzname in tzhelp.get_timezones():
            tzoptions.append((tzname, tzname))
        def _tz_cmp(x,y):
            x_name, x_label = x
            y_name, y_label = y
            return unicode.__cmp__(unicode(x_label), unicode(y_label))
        tzoptions.sort(cmp=_tz_cmp)

        # XXX: keymap values are truncated because they are so long
        keymapoptions = []
        for gname, gname_escaped, human in gnomeconfig.get_keymap_list():
            keymapoptions.append((gname_escaped, uihelpers.ui_truncate(human, 56)))
        def _km_cmp(x,y):
            x_name, x_label = x
            y_name, y_label = y
            return unicode.__cmp__(unicode(x_label), unicode(y_label))
        keymapoptions.sort(cmp=_km_cmp)
        
        g = formalutils.CollapsibleGroup('locale_group', label='Locale Settings')
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseLocale))
        g.add(formalutils.Field('timezone', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=tzoptions),
                                label='Timezone'))
        g.add(formalutils.Field('keymap', formal.String(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=keymapoptions),
                                label='Keyboard layout'))

        # XXX: it would be good if we could show a time example using the timezone
        # admin has selected.
        
        form.add(g)

        ### Reboots

        g = formalutils.CollapsibleGroup('reboot_group', label=txt.reboot_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseProductMaintenance))
        g.add(formalutils.Field('reboot_day', formal.Integer(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=txt.reboot_day_options),
                                label=txt.reboot_day_label))
        g.add(formalutils.Field('reboot_time', formal.Integer(required=True),
                                formal.widgetFactory(formal.SelectChoice, options=txt.reboot_time_options),
                                label=txt.reboot_time_label))
        # Information about the periodic reboot consequences (about 5 minutes downtime).
        g.add(formalutils.Field('automatic_updates', formal.Boolean(required=True), label=txt.automatic_update_label))
        form.add(g)

        ### SNMP

        g = formalutils.CollapsibleGroup('snmp_group', label='SNMP Monitoring')
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseSnmp))
        g.add(uihelpers.create_access_control_dropdown('snmp_access', 'SNMP read-only access'))
        g.add(formalutils.Field('snmp_community', formal.String(required=False),
                                formal.widgetFactory(formalutils.SemiHiddenPassword),
                                label='SNMP community string (password)'))
        form.add(g)

        ### Remote management

        g = formalutils.CollapsibleGroup('remote_group', label=txt.remote_group_caption)
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseRemoteManagement))
        g.add(uihelpers.create_access_control_dropdown('www_administration', 'Web administration'))
        g.add(uihelpers.create_access_control_dropdown('ssh_connection', 'SSH connection'))
        g.add(formalutils.Field('root_password1', formal.String(required=False),
                                formal.widgetFactory(formalutils.HiddenPassword),
                                label='Set root password'))
        g.add(formalutils.Field('root_password2', formal.String(required=False),
                                formal.widgetFactory(formalutils.HiddenPassword),
                                label='Re-enter root password'))
        form.add(g)

        ### Admin e-mails

        # XXX: not yet implemented
        #g = formalutils.CollapsibleGroup('email_group', label='Administrator E-mail')
        #g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseAdminEmail))
        #g.add(formalutils.Field('smtp_server', formal.String(required=False), label='SMTP server'))
        #g.add(formalutils.Field('smtp_from', formal.String(required=False), label='FROM address'))
        #g.add(formalutils.Field('smtp_to', formal.String(required=False), label='TO address(es) (comma separated)'))
        #form.add(g)
        
        ### SSL certificate

        g = formalutils.CollapsibleGroup('ssl_group', label='SSL Certificate')
        g.setCollapsed(uihelpers.collapse_setting(ns_ui.collapseSslCertificate))
        g.add(formalutils.Field('ssl_certificate_chain', formal.String(required=False),
                                formal.widgetFactory(formal.TextArea, cols=80, rows=10),
                                label='SSL Certificate Chain (PEM format, server certificate first)'))
        g.add(formalutils.Field('ssl_private_key', formal.String(required=False),
                                formal.widgetFactory(formal.TextArea, cols=80, rows=10),
                                label='SSL Private Key (PEM format)'))
        form.add(g)

        ### Submit buttons
        
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False)        

        ### Fill data to form
        
        try:
            self.fill_management(ctx, fda)
        except:
            # ignore failure so user has chance to edit the form
            _log.exception('fill_form_data failed, ignoring')

        return form

    def save_ui_data(self, ctx, form, data):    
        fda = formalutils.FormDataAccessor(form, [], ctx)
        ui_root = helpers.get_new_ui_config()

        # XXX: this should probably be refactored to uihelpers, in conjunction
        # with the access control element
        def _set_access(ns_pub, ns_priv, val):
            _log.debug('_set_access: %s' % val)
            if val == 'both':
                ui_root.setS(ns_pub, rdf.Boolean, True)
                ui_root.setS(ns_priv, rdf.Boolean, True)
            elif val == 'public':
                ui_root.setS(ns_pub, rdf.Boolean, True)
                ui_root.setS(ns_priv, rdf.Boolean, False)
            elif val == 'private':
                ui_root.setS(ns_pub, rdf.Boolean, False)
                ui_root.setS(ns_priv, rdf.Boolean, True)
            else:
                ui_root.setS(ns_pub, rdf.Boolean, False)
                ui_root.setS(ns_priv, rdf.Boolean, False)
        
        tmp = fda.descend('license_group')
        if tmp.has_key('license_key') and tmp['license_key'] is not None:
            lic_key = tmp['license_key'].upper()
            ui_root.setS(ns_ui.licenseKey, rdf.String, lic_key)
        else:
            # empty field (None) => clear product license
            ui_root.setS(ns_ui.licenseKey, rdf.String, '')

        tmp = fda.descend('locale_group')

        tmp = fda.descend('reboot_group')
        ui_root.setS(ns_ui.periodicRebootDay, rdf.Integer, tmp['reboot_day'])
        ui_root.setS(ns_ui.periodicRebootTime, rdf.Integer, tmp['reboot_time'])
        ui_root.setS(ns_ui.automaticUpdates, rdf.Boolean, tmp['automatic_updates'])

        tmp = fda.descend('snmp_group')
        _set_access(ns_ui.snmpAccessPublic, ns_ui.snmpAccessPrivate, tmp['snmp_access'])
        if tmp.has_key('snmp_community') and tmp['snmp_community'] is not None:
            ui_root.setS(ns_ui.snmpCommunity, rdf.String, tmp['snmp_community'])
        else:
            ui_root.setS(ns_ui.snmpCommunity, rdf.String, '')
        
        tmp = fda.descend('remote_group')
        _set_access(ns_ui.webAccessPublic, ns_ui.webAccessPrivate, tmp['www_administration'])
        _set_access(ns_ui.sshAccessPublic, ns_ui.sshAccessPrivate, tmp['ssh_connection'])

        tmp = fda.descend('ssl_group')
        if tmp.has_key('ssl_certificate_chain') and tmp['ssl_certificate_chain'] is not None:
            ui_root.setS(ns_ui.publicSslCertificateChain, rdf.String, tmp['ssl_certificate_chain'])
        else:
            ui_root.setS(ns_ui.publicSslCertificateChain, rdf.String, '')
        if tmp.has_key('ssl_private_key') and tmp['ssl_private_key'] is not None:
            ui_root.setS(ns_ui.publicSslPrivateKey, rdf.String, tmp['ssl_private_key'])
        else:
            ui_root.setS(ns_ui.publicSslPrivateKey, rdf.String, '')

        # XXX: not yet implemented
        #tmp = fda.descend('email_group')
        #if tmp.has_key('smtp_server') and tmp['smtp_server'] is not None:
        #    ui_root.setS(ns_ui.adminEmailSmtpServer, rdf.String, tmp['smtp_server'])
        #else:
        #    ui_root.setS(ns_ui.adminEmailSmtpServer, rdf.String, '')
        #if tmp.has_key('smtp_from') and tmp['smtp_from'] is not None:
        #    ui_root.setS(ns_ui.adminEmailFromAddress, rdf.String, tmp['smtp_from'])
        #else:
        #    ui_root.setS(ns_ui.adminEmailFromAddress, rdf.String, '')
        ## XXX: split here? or later? validate at least!
        #if tmp.has_key('smtp_to') and tmp['smtp_to'] is not None:
        #    ui_root.setS(ns_ui.adminEmailToAddresses, rdf.String, tmp['smtp_to'])
        #else:
        #    ui_root.setS(ns_ui.adminEmailToAddresses, rdf.String, '')

    @db.transact()
    def submitted(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)
        pd = uidatahelpers.CreateProtocolData()
        
        # Save collapsed states first, so they feed back to next round
        for [rdf_uri, key] in [ [ ns_ui.collapseLicense, 'license_group' ],
                                [ ns_ui.collapseLocale, 'locale_group' ],
                                [ ns_ui.collapseProductMaintenance, 'reboot_group' ],
                                [ ns_ui.collapseSnmp, 'snmp_group' ],
                                [ ns_ui.collapseRemoteManagement, 'remote_group' ],
                                [ ns_ui.collapseSslCertificate, 'ssl_group' ] ]:
            try:
                # XXX: passing of the hidden _collapsedstate_ parameter is not too clean
                uihelpers.update_collapse_setting(rdf_uri, fda['%s._collapsedstate_' % key])
            except:
                _log.exception('error updating collapsed state for %s' % rdf_uri)

        try:
            # global canonicalization
            tmp = fda.descend('license_group')
            if tmp.has_key('license_key') and (tmp['license_key'] is not None):
                tmp['license_key'] = tmp['license_key'].upper().strip()

            # global validation
            tmp = fda.descend('license_group')
            if tmp.has_key('license_key') and (tmp['license_key'] is not None):
                val, grps = None, None
                try:
                    val, grps = licensekey.decode_license(tmp['license_key'])
                except:
                    _log.exception('license decoding failed')
                if val is None:
                    tmp.add_error('license_key', 'Invalid license key')

            tmp = fda.descend('remote_group')
            if tmp.has_key('root_password1') and tmp.has_key('root_password2'):
                pw1, pw2 = tmp['root_password1'], tmp['root_password2']
                if pw1 is None:
                    pw1 = ''
                if pw2 is None:
                    pw2 = ''
                if pw1 != pw2:
                    tmp.add_error('root_password1', 'Passwords do not match')
                    tmp.add_error('root_password2', 'Passwords do not match')
                else:
                    if not helpers.check_unix_password_characters(pw1):  
                        tmp.add_error('root_password1', 'Invalid characters in password')
                        tmp.add_error('root_password2', 'Invalid characters in password')

            tmp = fda.descend('snmp_group')
            if tmp.has_key('snmp_community') and tmp['snmp_community'] is not None:
                if not uihelpers.check_snmp_community_characters(tmp['snmp_community']):
                    tmp.add_error('snmp_community', 'Invalid characters')

            #
            #  XXX -- How to validate SSL certificates reliably?  Currently invalid
            #  certificate / key causes VPNease to use self-signed version so it's
            #  relatively OK.
            #

            #
            #  XXX -- admin smtp setting validation & normalization
            #
            
            # Intermediate early bail out to avoid saving if there are errors
            fda.finalize_validation()

            # Deep copy UI config to 'new' UI config
            pd.clone_ui_config()

            # save data
            self.save_ui_data(ctx, form, data)

            # re-create protocol data to see if new exceptions crop up
            pd.save_protocol_data()
        except:
            _log.exception('validation failed unexpectedly, adding global error')
            fda.add_global_error('Unknown validation error')

        # finalize; raises if something wrong
        fda.finalize_validation()

        # locale settings are handled directly
        cfg_ui = helpers.get_new_ui_config()
        try:
            cfg_ui.setS(ns_ui.timezone, rdf.String, fda['locale_group.timezone'])
            cfg_ui.setS(ns_ui.keymap, rdf.String, fda['locale_group.keymap'])
            gnomeconfig.set_keymap_settings(cfg_ui.getS(ns_ui.keymap, rdf.String))
        except:
            _log.exception('activating timezone and keymap settings failed')

        # same with root password 
        try:
            tmp = fda.descend('remote_group')
            if tmp.has_key('root_password1') and tmp.has_key('root_password2'):
                pw1, pw2 = tmp['root_password1'], tmp['root_password2']
                if (pw1 == '') and (pw2 == ''):
                    pass
                elif (pw1 == None) and (pw2 == None):
                    pass
                elif pw1 == pw2:
                    # change password; we assume it converts to ascii nicely
                    helpers.change_unix_password('root', str(pw1))
                else:
                    # should not come here
                    _log.error('passwords differ after validation, ignoring')
        except:
            _log.exception('changing root password failed')

        # activate new config
        pd.activate_protocol_data()

        # update initial config saved flag
        pd.update_initial_config_saved()

        #
        #  XXX: It would be cleaner if we could first stop the runner, then change the
        #  config, and then restart it.  If we do that with a deferred, then it is possible
        #  that the user changes the config again before we have time to activate it.
        #  Putting the config into some sort of "staging area" might help.  Currently we
        #  simply assume that runner stop (and start) are robust enough.
        #

        #
        #  XXX: If timezone has changed, we should re-render graphs immediately so they
        #  will have the correct timezone when status pages are loaded.
        #

        # ssl certificate - always rewrite here
        try:
            uihelpers.update_ssl_certificate_files()

            # reread files; we don't regenerate because we never overwrite the self-signed
            # certificate here
            self.master.reread_ssl_files()
        except:
            _log.exception('ssl certificate check failed')

        # stop, configure, start
        followup = uihelpers.build_uri(ctx, 'status/main.html')
        return uihelpers.reconfigure_and_restart_page(self.master, ctx, followup_uri=followup)
    
# --------------------------------------------------------------------------
    
class _CheckForUpdateRenderers:
    @saferender()
    def render_will_not_update(self, ctx, data):
        if _check_update_on_next_reboot():
            return ''
        else:
            return ctx.tag

    @saferender()
    def render_will_update(self, ctx, data):
        if _check_update_on_next_reboot():
            return ctx.tag
        else:
            return ''
    
# --------------------------------------------------------------------------

class ConfirmRebootPage(formal.ResourceMixin, commonpage.AdminPage, _CheckForUpdateRenderers):
    template = 'admin/management/confirmreboot.xhtml'
    pagetitle = 'Management / Reboot'

    @db.transact()
    def form_buttons(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitreboot', formal.String(), label='Reboot'))
        form.add(sg)
        form.addAction(self.submitted_reboot, name='submitreboot', validate=False)
        return form

    @db.transact()
    def submitted_reboot(self, ctx, form, data):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('waitreboot.html'))
        request.finish()
        return ''

# --------------------------------------------------------------------------

class ConfirmShutdownPage(formal.ResourceMixin, commonpage.AdminPage, _CheckForUpdateRenderers):
    template = 'admin/management/confirmshutdown.xhtml'
    pagetitle = 'Management / Shutdown'

    @db.transact()
    def form_buttons(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitshutdown', formal.String(), label='Shut down'))
        form.add(sg)
        form.addAction(self.submitted_shutdown, name='submitshutdown', validate=False)
        return form

    @db.transact()
    def submitted_shutdown(self, ctx, form, data):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('waitshutdown.html'))
        request.finish()
        return ''

# --------------------------------------------------------------------------

class ConfirmUpdatePage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/management/confirmupdate.xhtml'
    pagetitle = 'Management / Product Updates'

    @db.transact()
    def form_updatebutton(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitupdate', formal.String(), label='Update product (causes reboot)'))
        form.add(sg)
        form.addAction(self.submitted_update, name='submitupdate', validate=False)
        return form

    @db.transact()
    def submitted_update(self, ctx, form, data):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().sibling('waitupdate.html'))
        request.finish()
        return ''

# --------------------------------------------------------------------------

class WaitRebootPage(commonpage.AdminPage):
    template = 'admin/management/waitreboot.xhtml'
    pagetitle = 'Management / Reboot'
    nav_disabled = True
    
    def render_doreboot(self, ctx, data):
        helpers.db_flush()
        uihelpers.ui_reboot(constants.WEBUI_PRODUCT_REBOOT_MESSAGE, skip_update=False, force_update=False, force_fsck=False, delay=5.0)
        return ''
    
# --------------------------------------------------------------------------

class WaitShutdownPage(commonpage.AdminPage):
    template = 'admin/management/waitshutdown.xhtml'
    pagetitle = 'Management / Shutdown'
    nav_disabled = True

    def render_doshutdown(self, ctx, data):
        helpers.db_flush()
        uihelpers.ui_shutdown(constants.WEBUI_PRODUCT_SHUTDOWN_MESSAGE, skip_update=False, force_update=False, force_fsck=False, delay=5.0)
        return ''

# --------------------------------------------------------------------------

class WaitUpdatePage(commonpage.AdminPage):
    template = 'admin/management/waitupdate.xhtml'
    pagetitle = 'Management / Product Updates'
    nav_disabled = True

    def render_doupdate(self, ctx, data):
        helpers.db_flush()
        uihelpers.ui_reboot(constants.WEBUI_PRODUCT_UPDATE_MESSAGE, skip_update=False, force_update=True, force_fsck=False, delay=5.0)
        return ''

# --------------------------------------------------------------------------

class WaitConfigImportPage(commonpage.AdminPage):
    template = 'admin/management/waitconfigimport.xhtml'
    pagetitle = 'Management / Import Configuration'
    nav_disabled = True

    def render_doconfigimport(self, ctx, data):
        helpers.db_flush()
        uihelpers.ui_reboot(constants.WEBUI_PRODUCT_IMPORT_REBOOT_MESSAGE, skip_update=True, force_update=False, force_fsck=False, delay=5.0)
        return ''

# --------------------------------------------------------------------------

class ConfigExportPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/management/configexport.xhtml'
    pagetitle = 'Management / Export Configuration'

    def locateChild(self, ctx, segments):
        if len(segments) == 1:
            t = segments[0]
            _log.debug('child segment: %s' % t)

            if t[-len(constants.PRODUCT_ZIPFILE_NAME_CONFIG_EXPORT)-4:-4] == constants.PRODUCT_ZIPFILE_NAME_CONFIG_EXPORT:
                return self._create_configuration_export(), []
            else:
                return rend.notFound
            
    def _create_configuration_export(self):
        zf = zipfiles.ProductZipfile(ns_zipfiles.configurationExport)
        cfg_data = uihelpers.export_rdf_database(remove_status=True)
        zf.add_file('configuration.xml', cfg_data)
        tmpfile = tempfile.mktemp(suffix='-configexport', prefix='vpnease-')
        zf.write_zipfile(tmpfile)

        f = None
        try:
            f = open(tmpfile, 'rb')
            zipdata = f.read()
        except:
            _log.exception('cannot read zipfile')
            raise
        if f is not None:
            f.close()
            
        return uihelpers.UncachedData(zipdata, 'application/zip')

    @db.transact()
    def form_buttons(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitconfigexport', formal.String(), label='Export configuration'))
        form.add(sg)
        form.addAction(self.submitted_configexport, name='submitconfigexport', validate=False)
        return form

    @db.transact()
    def submitted_configexport(self, ctx, form, data):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().child(helpers.get_standard_zipfile_name(constants.PRODUCT_ZIPFILE_NAME_CONFIG_EXPORT)))
        request.finish()
        return ''

# --------------------------------------------------------------------------

class ConfigImportPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/management/configimport.xhtml'
    pagetitle = 'Management / Import Configuration'

    def _parse_configuration_import(self, fda):
        tmpfile = None
        f = None

        try:
            if fda.has_key('importfile') and fda['importfile'] is not None:
                # read file data
                fname, f = fda['importfile']
                zip_data = f.read()
                f.close()
                f = None

                if len(zip_data) == 0:
                    return None

                # write to temp file
                tmpfile = tempfile.mktemp(suffix='-configimport', prefix='vpnease-')
                f = open(tmpfile, 'wb')
                f.write(zip_data)
                f.close()
                f = None

                # parse and check zip
                zf = zipfiles.ProductZipfile.read_zipfile(tmpfile, filetype=ns_zipfiles.configurationExport)
                cfg_data = zf.get_file('configuration.xml')

                # delete temp file
                os.unlink(tmpfile)
                tmpfile = None

                return cfg_data
            else:
                return None
        except:
            if f is not None:
                f.close()
            if (tmpfile is not None) and os.path.exists(tmpfile):
                os.unlink(tmpfile)
            raise

    @db.transact()
    def form_buttons(self, ctx):
        form = formal.Form()

        g = formalutils.CollapsibleGroup('import', label='Import Configuration')
        g.setCollapsed(False)  # makes no sense to collapse really
        g.add(formalutils.Field('importfile', formal.File(required=False), label='File to import')) 
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitconfigimport', formal.String(), label='Import configuration'))
        g.add(sg)
        form.add(g)
        form.addAction(self.submitted_configimport, name='submitconfigimport', validate=False)
        return form

    @db.transact()
    def submitted_configimport(self, ctx, form, data):
        fda = formalutils.FormDataAccessor(form, [], ctx)

        f = None

        # Here is the web UI import logic.  We basically check the ZIP file,
        # extract the RDF/XML data, and stash it to the file system.  We
        # then reboot, handling the actual import during reboot.  To make
        # the use case as good as possible, basic sanity checking of the
        # RDF/XML data is done here, too.
        try:
            fda = fda.descend('import')
            cfg_data = self._parse_configuration_import(fda)
            if cfg_data is None:
                fda.add_error('importfile', 'File missing or empty')
            else:
                _log.info('configuration import file (rdf) is %s bytes long' % len(cfg_data))

                # sanity check
                tmp_model = rdf.Model.fromString(cfg_data)
                if tmp_model is None:
                    raise Exception('cannot create model')

                @db.transact(database=tmp_model)
                def _f():
                    # XXX: more checks here, like version, etc.

                    # write to a temporary file for next reboot
                    f = None
                    try:
                        f = open(constants.CONFIGURATION_IMPORT_BOOT_FILE, 'wb')
                        f.write(tmp_model.toString(name='rdfxml'))
                    finally:
                        if f is not None:
                            f.close()
                            f = None
                _f()
                
                # reboot host, skip update on next boot
                request = inevow.IRequest(ctx)
                request.redirect(request.URLPath().sibling('waitconfigimport.html'))
                request.finish()
                return ''
        except:
            fda.add_error('importfile', 'Cannot parse file')
            _log.exception('import file check failed')

        if f is not None:
            f.close()
            
        fda.finalize_validation()

# --------------------------------------------------------------------------

class DiagnosticsExportPage(formal.ResourceMixin, commonpage.AdminPage):
    template = 'admin/management/diagnosticsexport.xhtml'
    pagetitle = 'Management / Export Diagnostics'

    def locateChild(self, ctx, segments):
        if len(segments) == 1:
            t = segments[0]
            _log.debug('child segment: %s' % t)

            if t[-len(constants.PRODUCT_ZIPFILE_NAME_DIAGNOSTICS_EXPORT)-4:-4] == constants.PRODUCT_ZIPFILE_NAME_DIAGNOSTICS_EXPORT:
                return self._create_diagnostics_export(), []
            else:
                return rend.notFound
            
    def _read_file(self, fname):
        f = None
        try:
            f = open(fname, 'rb')
            return f.read()
        finally:
            if f is not None:
                f.close()
                f = None
        raise Exception('cannot read %s' % fname)
    
    def _create_diagnostics_export(self):
        zf = zipfiles.ProductZipfile(ns_zipfiles.diagnosticsExport)
        zf.add_file(os.path.basename(constants.SYSLOG_LOGFILE), self._read_file(constants.SYSLOG_LOGFILE))
        zf.add_file(os.path.basename(constants.DMESG_LOGFILE),  self._read_file(constants.DMESG_LOGFILE))
        tmpfile = tempfile.mktemp(suffix='-diagexport', prefix='vpnease-')
        zf.write_zipfile(tmpfile)

        f = None
        try:
            f = open(tmpfile, 'rb')
            zipdata = f.read()
        except:
            _log.exception('cannot read zipfile')
            raise
        if f is not None:
            f.close()
            
        return uihelpers.UncachedData(zipdata, 'application/zip')

    @db.transact()
    def form_buttons(self, ctx):
        form = formal.Form()

        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submitdiagexport', formal.String(), label='Export diagnostics'))
        form.add(sg)
        form.addAction(self.submitted_diagexport, name='submitdiagexport', validate=False)
        return form

    @db.transact()
    def submitted_diagexport(self, ctx, form, data):
        request = inevow.IRequest(ctx)
        request.redirect(request.URLPath().child(helpers.get_standard_zipfile_name(constants.PRODUCT_ZIPFILE_NAME_DIAGNOSTICS_EXPORT)))
        request.finish()
        return ''

