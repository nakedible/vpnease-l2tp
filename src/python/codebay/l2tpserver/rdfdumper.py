"""Semi-generic RDF dumper.

Can dump DAGs starting from arbitrary RDF node.  Optimized to
'pretty print' l2tpserver RDF data: shortens common RDF, XSD,
Codebay types and l2tpserver specific prefixes to more readable
form.

Usage: instantiate RdfDumper, call dump_resource() from the
instance.  Don't call dump_resource in parallel.
"""
__docformat__ = 'epytext en'

from codebay.l2tpserver import rdfconfig
from codebay.common import rdf

_nslist = []
for [ ns, pfx ] in [ [ unicode(rdfconfig.ns[''].uri), 'l2tp:' ],
                     [ unicode(rdf.RDF_NUM_NS[''].uri), '#' ],
                     [ unicode(rdf.RDF_NS[''].uri), 'rdf:' ],
                     [ unicode(rdf.XSD_NS[''].uri), 'xsd:' ],
                     [ unicode(rdf.TYPES_NS[''].uri), 'types:' ] ]:
    _nslist.append([unicode(ns), pfx])

class RdfDumper:
    indstr = '  '
    
    def dump_resource(self, node, escaped=False):
        """Recursive dump of a RDF resource.

        NOTE: Not thread safe.
        """
        self._visiting = {}
        self._visited = {}
        res = self._dump(node, 0)
        if escaped:
            res = map(lambda x: x.encode('unicode_escape'), res)
        return '\n'.join(res) + '\n'

    def _prettify_uri(self, uri):
        uri = unicode(uri)
        for [ns, pfx] in _nslist:
            nslen = len(ns)
            if uri[:nslen] == ns:
                return '%s%s' % (pfx, uri[nslen:])
        return uri
    
    # XXX: sorting Bags and Seqs would be nice
    def _dump(self, node, indent):
        ind1 = self.indstr*indent
        ind2 = self.indstr*(indent+1)
        
        # loop detection
        if self._visiting.has_key(unicode(node.getUri())):
            return [ind1 + '*** loop ***']
        already_visited = False
        if self._visited.has_key(unicode(node.getUri())):
            already_visited = True
        self._visited[unicode(node.getUri())] = 1
        self._visiting[unicode(node.getUri())] = 1

        # separate arcs into terminals and non-terminals
        rdftypes = []
        stringarcs = []
        numberedarcs = []
        resourcearcs = []
        num_prefix = unicode(rdf.RDF_NUM_NS[''])
        num_prefix_len = len(num_prefix)

        for [p,o] in node.getNodePairs():
            # first try to parse as numbered
            uristr = unicode(p.getUri())
            if uristr[:num_prefix_len] == num_prefix:
                try:
                    num = int(uristr[num_prefix_len:])
                    numberedarcs.append([num,p,o])
                    continue
                except:
                    pass

            # if fails, fall back here
            if o.isLiteral():
                stringarcs.append([p,o])                
            elif o.isResource():
                # pick up rdf types as a special case
                if unicode(p.getUri()) == unicode(rdf.RDF_NS.type.uri):
                    rdftypes.append(self._prettify_uri(o.getUri()))
                else:
                    resourcearcs.append([p,o])
            elif o.isBlank():
                resourcearcs.append([p,o])
            else:
                raise Exception('invalid object: %s' % unicode(o))

        # sort arcs to make dumps more consistent
        stringarcs.sort(cmp=lambda x,y: unicode.__cmp__(unicode(x[0].getUri()), unicode(y[0].getUri())))
        resourcearcs.sort(cmp=lambda x,y: unicode.__cmp__(unicode(x[0].getUri()), unicode(y[0].getUri())))
        numberedarcs.sort(cmp=lambda x,y: int.__cmp__(x[0], y[0]))
        
        # render node itself
        res = []
        if node.isBlank():
            t = ind1 + '<blank>'
        else:
            t = ind1 + '<%s>' % self._prettify_uri(node.getUri())
        if len(rdftypes) > 0:
            t += ' [%s]' % ', '.join(rdftypes)
        if already_visited:
            t += ' {visited}'
        res.append(t)
        
        # render string arcs
        for [p,o] in stringarcs:
            res.append(ind2 + '%s = "%s" (%s)' % (self._prettify_uri(p.getUri()), o.getLiteral(), self._prettify_uri(o.getDatatype())))

        # render rdf number _n arcs, regardless of type
        for [n,p,o] in numberedarcs:
            if o.isLiteral():
                res.append(ind2 + '%s = "%s" (%s)' % (self._prettify_uri(p.getUri()), o.getLiteral(), self._prettify_uri(o.getDatatype())))
            else:
                res.append(ind2 + self._prettify_uri(p.getUri()))
                res.extend(self._dump(o, indent+2))

        # render resource arcs (blank or otherwise)
        for [p,o] in resourcearcs:
            res.append(ind2 + self._prettify_uri(p.getUri()))
            res.extend(self._dump(o, indent+2))

        # loop detection
        del self._visiting[unicode(node.getUri())]
        return res
    
if __name__ == '__main__':
    from codebay.l2tpserver import db

    rd = RdfDumper()
    print rd.dump_resource(db.get_db().getRoot())

    
