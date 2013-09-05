"""
Configuration activation page - Ajax page for better activation use case.
"""
__docformat__ = 'epytext en'

import time, datetime, textwrap

from twisted.internet import reactor
from nevow import inevow, loaders, rend, guard, url, stan, tags as T

from codebay.common import datatypes
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import uihelpers
from codebay.l2tpserver.webui import uidatahelpers

class ActivateConfigurationPage(commonpage.AdminPage):
    template = 'admin/activateconfiguration.xhtml'
    pagetitle = 'Activating Configuration'
    nav_disabled = True
    
    def render_followup_uri(self, ctx, data):
        request = inevow.IRequest(ctx)
        if request.args.has_key('followupuri'):
            followup = '"%s"' % request.args['followupuri'][0]
        else:
            followup = 'null'
        if request.args.has_key('quick'):
            quick = '1'
        else:
            quick = '0'

        tmp = 'activation_followup_uri = %s;\n' % followup
        tmp += 'activation_is_quick = %s;\n' % quick

        str = textwrap.dedent("""
        // <![CDATA[
        %s
        // ]]>
        """) % tmp
        
        # raw string required for JS CDATA hack
        ctx.tag[T.raw(str)]
        return ctx.tag

    def render_start_activation(self, ctx, data):
        request = inevow.IRequest(ctx) 
        if request.args.has_key('quick'):
            quick = True
        else:
            quick = False
           
        if quick:
            # just a no-op
            return ''
        else:
            # start reactivation process, ignore result; contains built-in delay to avoid rendering problems

            # NB: no problem with synchronization here with new exclusive locking
            d = uidatahelpers.reconfigure_and_restart_runner(self.master)
            return ''
    
class AjaxActivateConfiguration(commonpage.AjaxPage):
    def handle_request(self, ctx):
        [activity, finished, success, active] = self.master.get_activate_configuration_state()

        status = ''
        if finished:
            if success:
                status = 'success'
            else:
                status = 'failure'

        return '%s\n%s' % (activity, status)
