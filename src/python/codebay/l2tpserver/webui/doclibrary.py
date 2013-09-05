"""
Document loader library.
"""
__docformat__ = 'epytext en'

from zope.interface import implements
from nevow import inevow, loaders, stan

_no_default = object()

class patternLoader(loaders.xmlfile):
    """Wrap a document loader, for picking patterns.

    Instantiated with a document loader and a pattern and optionally a
    default clause. When being loaded by Nevow machinery, loads the
    document as normal, but only returns the selected pattern from the
    loaded document. If a default value is provided and the pattern is
    not found in the document, the default value is returned as is.
    """

    implements(inevow.IDocFactory)

    def __init__(self, original, pattern, default=_no_default):
        self.original = original
        self.pattern = pattern
        self.default = default

    def load(self, *args, **kw):
        doc = self.original.load(*args, **kw)
        if self.default is _no_default:
            return inevow.IQ(doc).onePattern(self.pattern)
        else:
            try:
                return inevow.IQ(doc).onePattern(self.pattern)
            except stan.NodeNotFound:
                return self.default

class DocLibrary:
    """Provide facities for loading templates."""

    def __init__(self, base_dir):
        self.base_dir = base_dir

    def getDocument(self, document):
        factory = loaders.xmlfile(document, templateDir=self.base_dir)
        return factory
