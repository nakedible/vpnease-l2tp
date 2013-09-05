"""
Page fragments.
"""
__docformat__ = 'epytext en'

from nevow import inevow, loaders, rend, guard, url, stan, tags as T
from nevow.context import WovenContext

from codebay.l2tpserver.webui.commonpage import doclib

from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers

class CommonFragment(rend.Fragment):
    docFactory = None
    loaded = False

    def patternContext(self, ctx, name):
        context = WovenContext(parent=ctx)
        self.rememberStuff(context)
        # XXX: preprocessors?
        doc = self.docFactory.load(context)
        context.tag = inevow.IQ(doc).onePattern(name)
        return context

    def generic(self, ctx, name, *args):
        # XXX
        context = self.patternContext(ctx, name)

        # XXX: if self contains a "filler" and we have args.. process somehow here?
        if (args is not None and len(args) != 0): raise Exception('Internal error')
        
        return context

    # XXX: these could be factored into a "mixin"

    def macro_productname(self, ctx):
        return constants.PRODUCT_NAME

    def macro_productversion(self, ctx):
        # XXX: cache this also, see master.py
        return helpers.get_product_version()
