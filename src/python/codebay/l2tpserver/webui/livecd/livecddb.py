
from codebay.common import rdf
from codebay.l2tpserver.rdfconfig import ns_ui

_livecd_model = None

def reset_livecd_database():
    global _livecd_model
    _livecd_model = None

def get_livecd_database_root():
    global _livecd_model

    if _livecd_model is None:
        model = rdf.Model.make()
        root = rdf.Node.make(model, rdf.Type(ns_ui.LiveCdGlobalRoot), ns_ui.liveCdGlobalRoot)
        _livecd_model = model
        
    return _livecd_model.getNodeByUri(ns_ui.liveCdGlobalRoot, rdf.Type(ns_ui.LiveCdGlobalRoot))

def dump_livecd_database():
    from codebay.l2tpserver import rdfdumper
    rd = rdfdumper.RdfDumper()
    return rd.dump_resource(get_livecd_database_root())
