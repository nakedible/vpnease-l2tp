"""Administrator configuration pages."""
__docformat__ = 'epytext en'

from nevow import inevow, loaders, rend, athena, url
import formal
from codebay.nevow.formalutils import formdatatypes as dt
from codebay.nevow.formalutils import formalutils
from codebay.l2tpserver.rdfconfig import ns_ui
from codebay.l2tpserver import db
from codebay.common import rdf
from codebay.l2tpserver.webui import uidatahelpers
from codebay.common import datatypes
from codebay.l2tpserver.webui import commonpage
from codebay.l2tpserver.webui import master
from codebay.l2tpserver.webui import l2tpmanager
from codebay.l2tpserver.webui.admin import uitexts
import sys

class DebugPage(formal.ResourceMixin, commonpage.AdminPage):
    """Debug form for internally configured options and such."""
    template = 'admin/config/debugconfig.xhtml'
    pagetitle = 'Debug Settings'
    
    def create_debug_group(self, form, ctx):
        debug_group = formalutils.CollapsibleGroup('debug_group', label='Debug')
        debug_group.setCollapsed(False)
        debug_group.add(formal.Field('debug', formal.Integer(required=True, validators=[formal.RangeValidator(min=0, max=2)]), label='Debug mode (0=normal, 1=light, 2=heavy)'))
        ui_root = db.get_db().getRoot().getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
        # Default false if no entry found from the database.
        debug_fda = formalutils.FormDataAccessor(form, ['debug_group'], ctx)
        if ui_root.hasS(ns_ui.debug):
            debug_fda['debug'] = ui_root.getS(ns_ui.debug, rdf.Integer)
        else:
            debug_fda['debug'] = 0
        return debug_group
        
    def save_debug(self, ctx, form, data):
        ui_root = db.get_db().getRoot().getS(ns_ui.uiConfig, rdf.Type(ns_ui.UiConfig))
        debug_fda = formalutils.FormDataAccessor(form, ['debug_group'], ctx)
        ui_root.setS(ns_ui.debug, rdf.Integer, debug_fda['debug'])
    
    def save_ui_data(self, ctx, form, data):    
        """ Saves form data to ui data after succeessfull submit. """
        self.save_debug(ctx, form, data)

    @db.transact()
    def form_config(self, ctx):    
        form = formal.Form()
        form.add(self.create_debug_group(form, ctx))
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit', formal.String(), label='Save changes'))
        form.add(sg)
        form.addAction(self.submitted, name='submit', validate=False) 
        return form

    @db.transact()
    def submitted(self, ctx, form, data):     
        fda = formalutils.FormDataAccessor(form, [], ctx)
        fda.finalize_validation()
        self.save_ui_data(ctx, form, data)

    @db.transact()
    def form_controls(self, ctx):
        form = formal.Form()
        g = formal.Group('debug_controls', 'Debug controls')
        sg = formalutils.SubmitFieldGroup('buttons')
        sg.add(formalutils.SubmitField('submit1', formal.String(), label='Start runner'))
        sg.add(formalutils.SubmitField('submit2', formal.String(), label='Stop runner'))
        g.add(sg)
        form.add(g)
        form.addAction(self.submitted_startrunner, name='submit1', validate=False) 
        form.addAction(self.submitted_stoprunner, name='submit2', validate=False) 
        return form

    @db.transact()
    def submitted_startrunner(self, ctx, form, data):
        try:
            m = self.get_master()
            m.start_l2tp_service()
        except:
            print 'Runner start failed with exception...'
            raise
        
    @db.transact()
    def submitted_stoprunner(self, ctx, form, data):
        try:
            m = self.get_master()
            m.stop_l2tp_service()
        except:
            print 'Runner stop failed with exception...'
            raise
