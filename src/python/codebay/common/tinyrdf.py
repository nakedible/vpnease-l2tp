"""
Tiny RDF library.
"""
__docformat__ = 'epytext en'

import atexit, StringIO, re, cPickle, datetime

import sqlalchemy as sqla
import apsw

import codebay.common.randutil
from codebay.common import logger

_log = logger.get('common.tinyrdf')

RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'

### Misc utils
#from random import getrandbits
#
#def genuuid():
#    """Generate a random UUID."""
#    v = getrandbits(128)
#    v &= 0xffffffffffff0fff3fffffffffffffffL;
#    v |= 0x00000000000040008000000000000000L;
#    h = u'%032x' % v
#    return u'%s-%s-%s-%s-%s' % (h[:8], h[8:12], h[12:16], h[16:20], h[20:])

def genuuid():
    return unicode(codebay.common.randutil.random_uuid())

_autoclose = set()

def add_autoclose(obj):
    global _autoclose
    _autoclose.add(obj)

def remove_autoclose(obj):
    global _autoclose
    _autoclose.discard(obj)

def _autocloser():
    global _autoclose
    while len(_autoclose):
        c = _autoclose.pop()
        try:
            c.close(atexit=True)
        except:
            pass

# Autoclose stores in an atexit handler.  Note that this handler is only called on a
# clean Python exit.  For instance, if a SIGTERM is given, and our caller does not
# handle the signal, these handlers will not be called.  This means that the behavior
# of tinyrdf depends on the caller's signal handler setup.
#
# From http://docs.python.org/lib/module-atexit.html:
#
#    Note: the functions registered via this module are not called
#    when the program is killed by a signal, when a Python fatal
#    internal error is detected, or when os._exit() is called.

atexit.register(_autocloser)

### Errors
class TinyrdfError(Exception):
    pass

class ParseError(Exception):
    pass

### Nodes
class Node(object):
    __slots__ = ()

class Uri(Node):
    __slots__ = ('__uri')

    def __init__(self, value=u''):
        if value is None:
            raise TinyrdfError('URI is None')
        elif '\t' in value:
            raise TinyrdfError('URI contains a tab character')
        self.__uri = unicode(value)

    def __getstate__(self):
        return self.__uri,

    def __setstate__(self, state):
        self.__uri, = state

    def __cmp__(self, other):
        return (cmp(self.__class__, other.__class__) or
                cmp(self.__uri, other.__uri))

    def __hash__(self):
        return hash((self.__class__, self.__uri,))

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__uri)

    def __str__(self):
        # XXX: URI encoding, read RDF Primer
        return unicode(self).encode('ASCII','replace')

    def __unicode__(self):
        return u'<%s>' % self.__uri

    uri = property(lambda self: self.__uri)

class Blank(Node):
    __slots__ = ('__identifier')

    def __init__(self, value=None):
        if value is None:
            self.__identifier = genuuid()
        else:
            self.__identifier = unicode(value)

    def __getstate__(self):
        return self.__identifier,

    def __setstate__(self, state):
        self.__identifier, = state

    def __cmp__(self, other):
        return (cmp(self.__class__, other.__class__) or
                cmp(self.__identifier, other.__identifier))

    def __hash__(self):
        return hash((self.__class__, self.__identifier,))

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__identifier)

    def __str__(self):
        return unicode(self).encode('ASCII','replace')

    def __unicode__(self):
        return u'_:%s' % self.__identifier

    identifier = property(lambda self: self.__identifier)

class Literal(Node):
    __slots__ = ('__value', '__language', '__datatype')

    def __init__(self, value=u'', language=None, datatype=None):
        self.__value = unicode(value)
        if datatype is not None:
            if language is not None:
                raise ValueError('Only language or datatype is allowed to be set.')
            if '\t' in datatype:
                raise TinyrdfError('Datatype contains a tab character')
            self.__datatype = datatype
        else:
            self.__datatype = None
        if language is not None:
            if '\t' in language:
                raise TinyrdfError('Language contains a tab character')
            self.__language = language
        else:
            self.__language = None

    def __getstate__(self):
        return self.__value, self.__language, self.__datatype

    def __setstate__(self, state):
        self.__value, self.__language, self.__datatype = state

    def __cmp__(self, other):
        return (cmp(self.__class__, other.__class__) or
                cmp(self.__value, other.__value) or
                cmp(self.__language, other.__language) or
                cmp(self.__datatype, other.__datatype))

    def __hash__(self):
        return hash((self.__class__, self.__value, self.__language, self.__datatype))

    def __repr__(self):
        if self.__language is not None:
            return '%s(%r, language=%r)' % (self.__class__.__name__, self.__value, self.__language)
        elif self.__datatype is not None:
            return '%s(%r, datatype=%r)' % (self.__class__.__name__, self.__value, self.__datatype)
        else:
            return '%s(%r)' % (self.__class__.__name__, self.__value)

    def __str__(self):
        return unicode(self).encode('ASCII','replace')

    def __unicode__(self):
        if self.__language is not None:
            return u'%r@%s' % (self.__value, self.__language)
        elif self.__datatype is not None:
            return u'%r^^<%s>' % (self.__value, self.__datatype)
        else:
            return u'%r' % self.__value

    value = property(lambda self: self.__value)
    language = property(lambda self: self.__language)
    datatype = property(lambda self: self.__datatype)

class Statement(object):
    __slots__ = ('__subject', '__predicate', '__object')

    def __init__(self, subject, predicate, object):
        self.__subject = subject
        self.__predicate = predicate
        self.__object = object

    def __getstate__(self):
        return self.__subject, self.__predicate, self.__object

    def __setstate__(self, state):
        self.__subject, self.__predicate, self.__object = state

    def __cmp__(self, other):
        return (cmp(self.__class__, other.__class__) or
                cmp(self.__subject, other.__subject) or
                cmp(self.__predicate, other.__predicate) or
                cmp(self.__object, other.__object))

    def __hash__(self):
        return hash((self.__class__, self.__subject, self.__predicate, self.__object))

    def __repr__(self):
        return '%s(%r, %r, %r)' % (self.__class__.__name__, self.__subject, self.__predicate, self.__object)

    def __str__(self):
        return unicode(self).encode('ASCII','replace')

    def __unicode__(self):
        return '(%s %s %s)' % (self.subject, self.predicate, self.object)

    def matches(self, statement):
        return ((self.subject is None or statement.subject is None or self.subject == statement.subject) and
                (self.predicate is None or statement.predicate is None or self.predicate == statement.predicate) and
                (self.object is None or statement.object is None or self.object == statement.object))

    def concrete(self):
        return (self.subject is not None and
                self.predicate is not None and
                self.object is not None)

    def with(self, subject=None, predicate=None, object=None):
        if ((subject is not None and subject != self.subject) or
            (predicate is not None and predicate != self.predicate) or
            (object is not None and object != self.object)):
            return self.__class__(subject or self.subject,
                                  predicate or self.predicate,
                                  object or self.object)
        else:
            return self

    subject = property(lambda self: self.__subject)
    predicate = property(lambda self: self.__predicate)
    object = property(lambda self: self.__object)

class NS(object):
    def __init__(self, base=u'', **kw):
        if isinstance(base, Uri):
            self.__base = base.uri
        else:
            self.__base = unicode(base)
        for key, val in kw.iteritems():
            if val is None:
                setattr(self, key, self[key])
            else:
                setattr(self, key, self[val])

    def __getitem__(self, val):
        return Uri(u'%s%s' % (self.__base, val))

    def __repr__(self):
        return '%s(%r)' % (self.__class__.__name__, self.__base__)

class UuidURIGenerator(object):
    def next(self):
        return Uri(u'urn:uuid:%s' % genuuid())

uuid = UuidURIGenerator()

### Parsers
class Parser(object):
    def parse(self, fileobj):
        raise NotImplemented()

    def parseString(self, string):
        s = StringIO.StringIO(string)
        try:
            for st in self.parse(s):
                yield st
        except:
            s.close()
            raise
        else:
            s.close()

    def parseFile(self, filename):
        f = file(filename, 'r')
        try:
            for st in self.parse(f):
                yield st
        except:
            f.close()
            raise
        else:
            f.close()

class NtriplesParser(Parser):
    COMMENT_RE = re.compile(r'^\s*(#|$)')
    STATEMENT_RE = re.compile(r'''^\s*
                                  (?: <([^>\s]*)> | _:([A-Za-z][A-Za-z0-9]*) ) \s+
                                  <([^>\s]*)> \s+
                                  (?: <([^>\s]*)> |_: ([A-Za-z][A-Za-z0-9]*) |
                                      "((?:[^"\\]|\\.)*)"
                                      (?: | @([a-z]+(?:-[a-z0-9]+)*) | \^\^<([^>\s]*)> ) ) \s*
                                  \.\s*$''', re.VERBOSE)

    def _unescape(self, s):
        return s.decode('unicode_escape')

    def parse(self, fileobj):
        for line in fileobj:
            if self.COMMENT_RE.match(line):
                continue
            m = self.STATEMENT_RE.match(line)
            if m:
                if m.group(1) is not None:
                    sub = Uri(self._unescape(m.group(1)))
                elif m.group(2) is not None:
                    sub = Blank(self.unicode(m.group(2)))
                pre = Uri(m.group(3))
                if m.group(4) is not None:
                    obj = Uri(self._unescape(m.group(4)))
                elif m.group(5) is not None:
                    obj = Blank(self.unicode(m.group(5)))
                elif m.group(6) is not None:
                    lit = self._unescape(m.group(6))
                    if m.group(7) is not None:
                        obj = Literal(lit, language=unicode(m.group(7)))
                    elif m.group(8) is not None:
                        obj = Literal(lit, datatype=self._unescape(m.group(8)))
                    else:
                        obj = Literal(lit)
                yield Statement(sub, pre, obj)
            else:
                # XXX: Add more information in exception.
                raise ParseError('Parsing n-triples failed: %s' % line)

class RdfxmlSubsetParser(Parser):
    def parse(self, fileobj):
        from xml import sax
        from xml.sax import handler

        statements = []
        
        class _SaxContentHandler(handler.ContentHandler):
            def __init__(self):
                self._got_rdf = False
                self._subject = None
                self._predicate = None
                self._object_uri = None
                self._object_literal = None
                self._language = None
                self._datatype = None
                
            def startElementNS(self, name, qname, attrs):
                # top-level element check
                if not self._got_rdf:
                    if name[0] + name[1] != RDF_NS + 'RDF':
                        raise Exception('Expecting rdf:RDF, got %s' % qname)
                    self._got_rdf = True
                    return

                if self._subject is not None:
                    # rdf:RDF -> rdf:Description -> predicate
                    self._predicate = name[0] + name[1]
                    res = None
                    try:
                        qname = attrs.getQNameByName((RDF_NS, 'resource'))
                        res = attrs.getValueByQName(qname)
                    except KeyError:
                        pass
                    if res is not None:
                        # object is Uri
                        self._object_uri = res
                        self._object_literal = None
                        self._language = None
                        self._datatype = None
                    else:
                        # object is literal
                        self._object_uri = None
                        self._object_literal = None
                        try:
                            self._language = attrs.getValueByQName('xml:lang')
                        except KeyError:
                            self._language = None
                        try:
                            qname = attrs.getQNameByName((RDF_NS, 'datatype'))
                            self._datatype = attrs.getValueByQName(qname)
                        except KeyError:
                            self._datatype = None
                else:
                    # rdf:RDF -> new node (should be rdf:Description)
                    if name[0] == RDF_NS and name[1] == 'Description':
                        self._subject = None
                        try:
                            qname = attrs.getQNameByName((RDF_NS, 'about'))
                            self._subject = attrs.getValueByQName(qname)
                        except KeyError:
                            pass
                        if self._subject is None:
                            raise Exception('No rdf:about for rdf:Description')
                    else:
                        raise Exception('Expecting rdf:Description, got %s' % qname)
                    
            def endElementNS(self, name, qname):
                if self._predicate is not None:
                    # rdf:RDF -> rdf:Description -> predicate
                    if name[0] + name[1] != self._predicate:
                        raise Exception('Expecting end tag for %s, got %s' % (self._predicate, qname))

                    if self._object_uri is not None:
                        if self._object_literal is not None and self._object_literal != '':
                            raise Exception('Found both literal and URI reference')

                        statements.append(Statement(Uri(self._subject), Uri(self._predicate), Uri(self._object_uri)))
                    else:
                        if self._object_literal is None:
                            literal = ''
                        else:
                            literal = self._object_literal
                        if self._language is not None and self._datatype is not None:
                            raise Exception('Both language and datatype found for literal')
                        statements.append(Statement(Uri(self._subject), Uri(self._predicate), Literal(literal, self._language, self._datatype)))

                    self._predicate = None
                    self._object_uri = None
                    self._object_literal = None
                    self._datatype = None
                    self._language = None
                elif self._subject is not None:
                    # rdf:RDF -> rdf:Description
                    if name[0] + name[1] != RDF_NS + 'Description':
                        raise Exception('Expected end tag for rdf:Description, got %s' % (qname))
                    self._subject = None
                else:
                    # don't care about the rest
                    pass

            def characters(self, content):
                # Accumulate characters for literal
                if self._subject is not None and self._predicate is not None:
                    if self._object_literal is None:
                        self._object_literal = ''
                    self._object_literal += content
                else:
                    pass

        _parser = sax.make_parser()
        _parser.setFeature(handler.feature_namespaces, True)
        _parser.setContentHandler(_SaxContentHandler())
        _parser.parse(fileobj)

        # need to gather statements internally during parse; yielding doesn't work from within SAX
        for st in statements:
            yield st
    
class PickleParser(Parser):
    def parse(self, fileobj):
        try:
            while True:
                obj = cPickle.load(fileobj)
                if not isinstance(obj, Statement):
                    raise ParseError('Parsing pickles failed.')
                yield obj
        except EOFError:
            pass

### Serializers
class Serializer(object):
    def serialize(self, statements, fileobj):
        raise NotImplemented()

    def serializeString(self, statements):
        s = StringIO.StringIO()
        try:
            self.serialize(statements, s)
            return s.getvalue()
        finally:
            s.close()

    def serializeFile(self, statements, filename):
        f = file(filename, 'w')
        try:
            self.serialize(statements, f)
        finally:
            f.close()

class NtriplesSerializer(Serializer):
    ESCAPE_RE = re.compile(r'\\(x([a-fA-F0-9]{2})|u([a-fA-F0-9]{4})|")')

    def _escape_sub(self, m):
        c = m.group(1)
        if c[0] == 'x':
            return '\\u00%s' % c[1:].upper()
        elif c[0] == 'u':
            return '\\u%s' % c[1:].upper()
        elif c == '"':
            return '\\"'
        else:
            raise Exception('Internal error in serializer.')

    def _escape(self, s):
        return self.ESCAPE_RE.sub(self._escape_sub, s.encode('unicode_escape'))

    def _n3_node(self, n):
        if isinstance(n, Uri):
            return '<%s>' % n.uri
        elif isinstance(n, Blank):
            return '_:%s' % n.identifier
        elif isinstance(n, Literal):
            if n.language is not None:
                return '"%s"@%s' % (self._escape(n.value), n.language)
            elif n.datatype is not None:
                return '"%s"^^<%s>' % (self._escape(n.value), n.datatype)
            else:
                return '"%s"' % self._escape(n.value)
        else:
            raise Exception('Internal error in serializer.')

    def _n3_statement(self, st):
        return '%s %s %s .\n' % (self._n3_node(st.subject), self._n3_node(st.predicate), self._n3_node(st.object))

    def serialize(self, statements, fileobj):
        for st in statements:
            fileobj.write(self._n3_statement(st))

class RdfxmlSubsetSerializer(Serializer):
    """Serializes to RDF/XML subset; does not support blank nodes."""

    # Split URI into a namespace and local part; this is a subset of QName production
    PRED_EXTRACT_RE = re.compile(r'^(.*?)([a-zA-Z_]([a-zA-Z0-9.\-_]+))$')

    def _encode_predicate(self, pred):
        # Not all predicates can be expressed in RDF/XML.  Here we make some effort
        # but because this is a subset, we don't support all theoretically supportable
        # forms.

        m = self.PRED_EXTRACT_RE.match(pred.uri)
        if m is None:
            raise Exception('Cannot encode predicate %s as a QName' % pred.uri)
        ns, localpart = m.group(1), m.group(2)
        if ns == RDF_NS:
            return 'rdf', None, localpart
        else:
            return 'ns', ns, localpart
        
    def serialize(self, statements, fileobj):
        from xml.sax.saxutils import escape, quoteattr

        def _esc(x):
            return escape(x).encode('ascii', 'xmlcharrefreplace')
        def _attr(x):
            return quoteattr(x).encode('ascii', 'xmlcharrefreplace')

        fileobj.write('<?xml version="1.0"?>\n')
        fileobj.write('<rdf:RDF xmlns:rdf=%s>\n' % _attr(RDF_NS))

        for st in statements:
            if not st.concrete():
                raise Exception('Statement (%s) not concrete' % st)
            if isinstance(st.subject, Blank):
                raise Exception('Subject (%s) is Blank, unsupported' % st.subject)
            if not isinstance(st.subject, Uri):
                raise Exception('Subject (%s) is not Uri' % st.subject)
            if isinstance(st.predicate, Blank):
                raise Exception('Predicate (%s) is Blank, unsupported' % st.predicate)
            if not isinstance(st.predicate, Uri):
                raise Exception('Predicate (%s) is not Uri' % st.predicate)
            if isinstance(st.object, Blank):
                raise Exception('Object (%s) is Blank, unsupported' % st.object)
            if not isinstance(st.object, Uri) and not isinstance(st.object, Literal):
                raise Exception('Object (%s) is not an Uri or a Literal' % st.object)
            
            fileobj.write('    <rdf:Description rdf:about=%s>\n' % _attr(st.subject.uri))

            pred_prefix, pred_ns, pred_local = self._encode_predicate(st.predicate)
            xmlns_decl = ''
            if pred_ns is not None:
                xmlns_decl = ' xmlns:%s=%s' % (pred_prefix, _attr(pred_ns))

            if isinstance(st.object, Uri):
                fileobj.write('        <%s:%s%s rdf:resource=%s />\n' % \
                              (pred_prefix, pred_local, xmlns_decl, _attr(st.object.uri)))
            elif isinstance(st.object, Literal):
                rdf_datatype = ''
                if st.object.datatype is not None:
                    rdf_datatype = ' rdf:datatype=%s' % _attr(st.object.datatype)
                rdf_language = ''
                if st.object.language is not None and st.object.datatype is None:
                    rdf_language = ' xml:lang=%s' % _attr(st.object.language)
                fileobj.write('        <%s:%s%s%s%s>%s</%s:%s>\n' % \
                              (pred_prefix, pred_local, xmlns_decl, rdf_datatype, rdf_language, _esc(st.object.value), pred_prefix, pred_local))
            else:
                raise Exception('Internal error')

            fileobj.write('    </rdf:Description>\n')

        fileobj.write('</rdf:RDF>\n')

class PickleSerializer(Serializer):
    def serialize(self, statements, fileobj):
        for st in statements:
            cPickle.dump(st, fileobj, protocol=2)

### Stores
class Transaction(object):
    def __init__(self, store):
        self.store = store
        self.active = True
        self.was_store_active = store.is_transaction_active()
        if not self.was_store_active:
            self.store._do_begin_transaction()

    def commit(self):
        assert self.active, 'Transaction is not active'
        self.active = False
        if not self.was_store_active:
            self.store._do_commit_transaction()

    # XXX: how much time we've been actually locked; this is SqlalchemyStore specific
    # and a bit unclean but will do for now.  Call this before commit().
    def get_locked_time(self):
        assert self.active, 'Transaction is not active'
        if not self.was_store_active:
            if isinstance(self.store, SqlalchemyStore):
                if self.store.sqla_txn_begin_time is not None:
                    return datetime.datetime.utcnow() - self.store.sqla_txn_begin_time
                else:
                    return None
            else:
                return None
        else:
            return None

    def rollback(self): # XXX
        assert self.active, 'Transaction is not active'
        self.active = False
        if not self.was_store_active:
            self.store._do_rollback_transaction()

    def is_active(self):
        return self.active

class Untransaction(object):
    def __init__(self, store):
        self.store = store
        self.active = True
        self.was_store_active = store.is_transaction_active()
        self.txn_locked_time = None            
        if self.was_store_active:
            begin = None
            if isinstance(self.store, SqlalchemyStore):
                if self.store.sqla_txn_begin_time is not None:
                    begin = self.store.sqla_txn_begin_time
            self.store._do_commit_transaction()
            if isinstance(self.store, SqlalchemyStore):
                if begin is not None:
                    self.txn_locked_time = datetime.datetime.utcnow() - begin

    def commit(self):
        assert self.active, 'Untransaction is not active'
        self.active = False
        if self.was_store_active:
            self.store._do_begin_transaction()

    def get_locked_time(self):
        return None

    def get_txn_locked_time(self):
        return self.txn_locked_time

    def rollback(self): # XXX
        assert self.active, 'Untransaction is not active'
        self.active = False
        if self.was_store_active:
            self.store._do_begin_transaction()

class Store(object):
    def __init__(self):
        add_autoclose(self)
        self.txn_active = False

    def open(cls):
        raise NotImplemented()
    open = classmethod(open)

    def create(cls):
        raise NotImplemented()
    create = classmethod(create)

    def delete(cls):
        raise NotImplemented()
    delete = classmethod(delete)

    def add_statement(self, statement):
        raise NotImplemented()

    def add_statements(self, statements):
        for statement in statements:
            self.add_statement(statement)

    def contains_statement(self, statement):
        raise NotImplemented()

    def remove_statement(self, statement):
        raise NotImplemented()

    def remove_statements(self, template):
        raise NotImplemented()

    def count_statements(self, template):
        raise NotImplemented()

    def find_statements(self, template):
        raise NotImplemented()

    def all_statements(self):
        return self.find_statements(Statement(None, None, None))

    def sync(self):
        pass

    def begin_transaction(self):
        return Transaction(self)

    def begin_untransaction(self):
        return Untransaction(self)

    def close(self, atexit=False):
        # XXX: debug, because this is common
        _log.debug('autoclosing Store (%s) in atexit' % self)
        remove_autoclose(self)

    def is_transaction_active(self):
        return self.txn_active

    def _do_begin_transaction(self):
        assert not self.txn_active, 'Begin transaction called when transaction was already active'
        self.txn_active = True

    def _do_commit_transaction(self):
        assert self.txn_active, 'Commit transaction called when transaction was not active'
        self.txn_active = False

    def _do_rollback_transaction(self):
        assert self.txn_active, 'Rollback transaction called when transaction was not active'
        self.txn_active = False

class MemoryStore(Store):
    data = None

    def create(cls):
        return cls(data=set())
    create = classmethod(create)

    def __init__(self, data):
        super(MemoryStore, self).__init__()
        self.data = data

    def add_statement(self, statement):
        assert self.data is not None, 'Store is not open'
        assert isinstance(statement, Statement), 'Parameter must be a statement'
        assert statement.concrete(), 'Statement must be concrete'
        self.data.add(statement)

    def contains_statement(self, statement):
        assert self.data is not None, 'Store is not open'
        assert isinstance(statement, Statement), 'Parameter must be a statement'
        assert statement.concrete(), 'Statement must be concrete'
        return statement in self.data

    def remove_statement(self, statement):
        assert self.data is not None, 'Store is not open'
        assert isinstance(statement, Statement), 'Parameter must be a statement'
        assert statement.concrete(), 'Statement must be concrete'
        return self.data.discard(statement)

    def remove_statements(self, template):
        assert self.data is not None, 'Store is not open'
        assert isinstance(template, Statement), 'Parameter must be a statement'
        to_be_deleted = set()
        for statement in self.data:
            if template.matches(statement):
                to_be_deleted.add(statement)
        for statement in to_be_deleted:
            self.data.discard(statement)

    def count_statements(self, template):
        assert self.data is not None, 'Store is not open'
        assert isinstance(template, Statement), 'Parameter must be a statement'
        count = 0
        for statement in self.data:
            if template.matches(statement):
                count += 1
        return count

    def find_statements(self, template):
        assert self.data is not None, 'Store is not open'
        assert isinstance(template, Statement), 'Parameter must be a statement'
        for statement in self.data:
            if template.matches(statement):
                yield statement

    def close(self):
        assert self.data is not None, 'Store is not open'
        del self.data
        super(MemoryStore, self).close()

# XXX: Sqlite memory databases (sqlite:///) are currently broken with our rdf.py
# transaction wrapping model, they result in OperationalErrors.  Thus, rdf.py uses
# our trivial MemoryModel (above) instead of Sqlite memory models.
class SqlalchemyStore(Store):
    # XXX: this seems to break with newer SQLalchemy
    #metadata = sqla.MetaData(name='tinyrdf')
    metadata = sqla.MetaData()

    # Note: it is critical that indexing is adequate for common use (select with
    # subject and predicate is very critical for rdf.py performance).
    statements_table = sqla.Table('statements', metadata,
                                  sqla.Column('sub', sqla.Unicode, nullable=False),
                                  sqla.Column('pre', sqla.Unicode, nullable=False),
                                  sqla.Column('obj', sqla.Unicode, nullable=False),
                                  sqla.UniqueConstraint('sub', 'pre', 'obj'))
    statements_select = statements_table.select()
    statements_insert = statements_table.insert()
    statements_delete = statements_table.delete(sqla.and_(statements_table.c.sub == sqla.bindparam('sub'),
                                                          statements_table.c.pre == sqla.bindparam('pre'),
                                                          statements_table.c.obj == sqla.bindparam('obj')))
    accessed_table = sqla.Table('accessed', metadata,
                                sqla.Column('timestamp', sqla.DateTime, nullable=False))
    accessed_insert = accessed_table.insert()
    accessed_update = accessed_table.update()
    accessed_delete = accessed_table.delete()
    deferred_txn = object()
    active_txn = object()
    
    def open(cls, dburi, *args, **kw):
        e = sqla.create_engine(dburi, *args, **kw)
        #e.echo = True
        c = e.connect()
        return cls(c)
    open = classmethod(open)

    def create(cls, dburi, *args, **kw):
        e = sqla.create_engine(dburi, *args, **kw)
        #e.echo = True
        c = e.connect()
        cls.metadata.create_all(c)
        return cls(c, create=True)
    create = classmethod(create)

    def delete(cls, dburi):
        raise NotImplemented()
    delete = classmethod(delete)

    def __init__(self, engine, create=False):
        super(SqlalchemyStore, self).__init__()
        self.connection = engine.connect()
        self.sqla_txn = None
        self.sqla_txn_begin_time = None
        self.sqla_txn_wait_time = None
        if create:
            # XXX: transaction?
            e = self.connection.execute(self.accessed_delete)
            e.close()
            e = self.connection.execute(self.accessed_insert, timestamp=datetime.datetime.utcnow())
            e.close()
        if False:
            # See: http://www.sqlite.org/pragma.html
            e = self.connection.execute('PRAGMA synchronous = 0;')
            e.close()
            
    def add_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        try:
            e = self.connection.execute(self.statements_insert,
                                        sub=self._node_to_str(statement.subject),
                                        pre=self._node_to_str(statement.predicate),
                                        obj=self._node_to_str(statement.object))
            e.close()
        except sqla.exceptions.SQLError, e:
            # XXX: this error check is a bit ugly; is there a proper way of
            # doing this?  Perhaps use sqlite specific 'insert or ignore'?
            if 'unique' in str(e).lower():
                pass
            else:
                raise

    def contains_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        e = self.connection.execute(self.statements_select,
                                    sub=self._node_to_str(statement.subject),
                                    pre=self._node_to_str(statement.predicate),
                                    obj=self._node_to_str(statement.object))
        v = e.fetchone()
        e.close()
        if v is not None:
            return True
        else:
            return False

    def remove_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        e = self.connection.execute(self.statements_delete,
                                    sub=self._node_to_str(statement.subject),
                                    pre=self._node_to_str(statement.predicate),
                                    obj=self._node_to_str(statement.object)) 
        e.close()

    def remove_statements(self, template):
        self._maybe_begin_transaction()
        e = self.connection.execute(self._build_delete_statement(template))
        e.close()

    def count_statements(self, template):
        self._maybe_begin_transaction()
        count = 0
        e = self.connection.execute(self.statements_select,
                                    **self._build_match(template))
        for v in e:
            count += 1
        e.close()
        return count

    def find_statements(self, template):
        self._maybe_begin_transaction()
        l = []
        e = self.connection.execute(self.statements_select,
                                    **self._build_match(template))
        for v in e:
            l.append(Statement(self._str_to_node(v.sub),
                               self._str_to_node(v.pre),
                               self._str_to_node(v.obj)))
        e.close()
        return l

    def close(self, atexit=False):
        # XXX: debug, because this is common
        _log.debug('autoclosing Store (%s) in atexit' % self)
        if self.sqla_txn is self.active_txn:
            self._do_commit_transaction() # XXX: no rollbacks
        self.connection.close()
        super(SqlalchemyStore, self).close()

    def sync(self):
        pass

    def _do_begin_transaction(self):
        super(SqlalchemyStore, self)._do_begin_transaction()
        assert self.sqla_txn is None, 'sqla_txn must be None in _do_begin_transaction, transaction nesting error?'
        self.sqla_txn = self.deferred_txn # Note: transaction start is deferred and actually called on first operation

    # NB: the correct (= working) way to do transactions was not easy to arrive at.
    # Be careful if you change these; BEGIN EXCLUSIVE seems to work well for now,
    # mere BEGIN does not.
    #
    # See: http://www.sqlite.org/lang_transaction.html
    def _do_begin_transaction_harder(self):
        assert self.sqla_txn is self.deferred_txn, 'sqla_txn must be deferred_txn in _do_begin_transaction_harder'
        self.sqla_txn_wait_time = datetime.datetime.utcnow()
        self.sqla_txn = self.active_txn
        _log.debug('beginning sqlite transaction (store %s)' % self)
        e = self.connection.execute('BEGIN EXCLUSIVE;')
        e.close()
        #self._do_dummy_write()
        self.sqla_txn_begin_time = datetime.datetime.utcnow()

    def _do_commit_transaction(self):
        super(SqlalchemyStore, self)._do_commit_transaction()
        assert self.sqla_txn is self.active_txn or self.sqla_txn is self.deferred_txn, 'Commit transaction called when no transaction active'
        if self.sqla_txn is self.active_txn:
            try:
                _log.debug('committing sqlite transaction (store %s)' % self)
                e = self.connection.execute('COMMIT;')
                e.close()
            except:
                pass
        self.sqla_txn = None
        self.sqla_txn_begin_time = None
        self.sqla_txn_wait_time = None

    def _do_rollback_transaction(self):
        super(SqlalchemyStore, self)._do_rollback_transaction()
        assert self.sqla_txn is self.active_txn or self.sqla_txn is self.deferred_txn, 'Rollback transaction called when no transaction active'
        if self.sqla_txn is self.active_txn:
            try:
                _log.debug('rolling back sqlite transaction (store %s)' % self)
                e = self.connection.execute('ROLLBACK;')
                e.close()
            except:
                pass
        self.sqla_txn = None

    def _build_match(self, template):
        kw = {}
        for k, n in (('sub', template.subject),
                     ('pre', template.predicate),
                     ('obj', template.object)):
            if n is not None:
                kw[k] = self._node_to_str(n)
            else:
                pass
        return kw

    def _build_delete_statement(self, template):
        l = []
        for k, n in ((self.statements_table.c.sub, template.subject),
                     (self.statements_table.c.pre, template.predicate),
                     (self.statements_table.c.obj, template.object)):
            if n is not None:
                l.append(k == self._node_to_str(n))
            else:
                pass
        if len(l):
            return self.statements_table.delete(sqla.and_(*l))
        else:
            return self.statements_table.delete()

    def _node_to_str(self, node):
        if isinstance(node, Uri):
            return u'U%s' % node.uri
        elif isinstance(node, Blank):
            return u'B%s' % node.identifier
        elif isinstance(node, Literal):
            if node.language is not None:
                return u'L%s\t%s' % (node.language, node.value)
            elif node.datatype is not None:
                return u'D%s\t%s' % (node.datatype, node.value)
            else:
                return u'P%s' % node.value
        else:
            raise ValueError('Internal error in sqlalchemy store.')

    def _str_to_node(self, s):
        if s[0] == u'U':
            return Uri(s[1:])
        elif s[0] == u'B':
            return Blank(s[1:])
        elif s[0] == u'L':
            l, v = s.split('\t', 1)
            return Literal(value=v, language=l[1:])
        elif s[0] == u'D':
            d, v = s.split('\t', 1)
            return Literal(value=v, datatype=d[1:])
        elif s[0] == u'P':
            return Literal(value=s[1:])
        else:
            raise ValueError('Internal error in sqlalchemy store.')

    def _maybe_begin_transaction(self):
        if self.sqla_txn is self.deferred_txn:
            self._do_begin_transaction_harder()

    def _do_dummy_write(self):
        e = self.connection.execute(self.accessed_update,
                                    timestamp = datetime.datetime.utcnow())
        e.close()

class ApswStore(Store):
    deferred_txn = object()
    active_txn = object()

    def open(cls, filename):
        c = apsw.Connection(filename)
        return cls(c)
    open = classmethod(open)

    def create(cls, filename):
        c = apsw.Connection(filename)
        curs = c.cursor()
        curs.execute("""CREATE TABLE statements (
                          sub TEXT NOT NULL, 
                          pre TEXT NOT NULL, 
                          obj TEXT NOT NULL, 
	                  UNIQUE (sub, pre, obj)
                        );""")
        curs = None
        return cls(c)

    create = classmethod(create)

    def delete(cls, filename):
        raise NotImplemented()
    delete = classmethod(delete)

    def __init__(self, c):
        super(ApswStore, self).__init__()
        self.connection = c
        self.connection.setbusytimeout(300000) # 300 seconds
        self.cursor = self.connection.cursor()
        self.txn = None
        self.txn_begin_time = None
        self.txn_wait_time = None
        ## Enable the lines below to allow tracing of actual SQL executed
        #def mytrace(statement, bindings):
        #    "Called just before executing each statement"
        #    print "SQL:",statement
        #    if bindings:
        #        print "Bindings:",bindings
        #    return True  # if you return False then execution is aborted
        #self.cursor.setexectrace(mytrace)

    def add_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        self.cursor.execute('INSERT OR IGNORE INTO statements (sub, pre, obj) VALUES (?, ?, ?);', (self._node_to_str(statement.subject),
                                                                                                   self._node_to_str(statement.predicate),
                                                                                                   self._node_to_str(statement.object)))

    def contains_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        found = False
        for v in self.cursor.execute('SELECT sub, pre, obj FROM statements WHERE sub = ? AND pre = ? AND obj = ?', (self._node_to_str(statement.subject),
                                                                                                                    self._node_to_str(statement.predicate),
                                                                                                                    self._node_to_str(statement.object))):
            found = True
        return found

    def remove_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()
        self.cursor.execute('DELETE FROM statements WHERE sub = ? AND pre = ? AND obj = ?', (self._node_to_str(statement.subject),
                                                                                             self._node_to_str(statement.predicate),
                                                                                             self._node_to_str(statement.object)))

    def remove_statements(self, template):
        self._maybe_begin_transaction()
        where, args = self._build_match(template)
        self.cursor.execute('DELETE FROM statements%s' % where, args)

    def count_statements(self, template):
        self._maybe_begin_transaction()
        where, args = self._build_match(template)
        for v, in self.cursor.execute('SELECT count(*) FROM statements%s' % where, args):
            return v
        raise ValueError('Internal error in apsw store.')

    def find_statements(self, template):
        self._maybe_begin_transaction()
        where, args = self._build_match(template)
        l = []
        for sub, pre, obj in self.cursor.execute('SELECT sub, pre, obj FROM statements%s' % where, args):
            l.append(Statement(self._str_to_node(sub),
                               self._str_to_node(pre),
                               self._str_to_node(obj)))
        return l

    def _do_begin_transaction(self):
        super(ApswStore, self)._do_begin_transaction()
        assert self.txn is None, 'txn must be None in _do_begin_transaction, transaction nesting error?'
        self.txn = self.deferred_txn # Note: transaction start is deferred and actually called on first operation

    # NB: the correct (= working) way to do transactions was not easy to arrive at.
    # Be careful if you change these; BEGIN EXCLUSIVE seems to work well for now,
    # mere BEGIN does not.
    #
    # See: http://www.sqlite.org/lang_transaction.html
    def _do_begin_transaction_harder(self):
        assert self.txn is self.deferred_txn, 'txn must be deferred_txn in _do_begin_transaction_harder'
        self.txn_wait_time = datetime.datetime.utcnow()
        self.txn = self.active_txn
        _log.debug('beginning sqlite transaction (store %s)' % self)

        # XXX: for debugging
        #import traceback
        #_log.info('TRACEBACK: _do_begin_transaction_harder: starting transaction, stacktrace\n%s' % ''.join(traceback.format_stack()))

        self.cursor.execute('BEGIN EXCLUSIVE;')
        self.txn_begin_time = datetime.datetime.utcnow()

    def _do_commit_transaction(self):
        super(ApswStore, self)._do_commit_transaction()
        assert self.txn is self.active_txn or self.txn is self.deferred_txn, 'Commit transaction called when no transaction active'
        if self.txn is self.active_txn:
            try:
                _log.debug('committing sqlite transaction (store %s)' % self)
                self.cursor.execute('COMMIT;')
            except:
                pass
        self.txn = None
        self.txn_begin_time = None
        self.txn_wait_time = None

    def _do_rollback_transaction(self):
        super(ApswStore, self)._do_rollback_transaction()
        assert self.txn is self.active_txn or self.txn is self.deferred_txn, 'Rollback transaction called when no transaction active'
        if self.txn is self.active_txn:
            try:
                _log.debug('rolling back sqlite transaction (store %s)' % self)
                self.cursor.execute('ROLLBACK;')
            except:
                pass
        self.txn = None

    def close(self, atexit=False):
        # XXX: debug, because this is common
        _log.debug('autoclosing Store (%s) in atexit' % self)
        if self.txn is self.active_txn:
            self._do_commit_transaction() # XXX: no rollbacks
        self.cursor = None
        self.connection = None
        super(ApswStore, self).close()

    def _node_to_str(self, node):
        if isinstance(node, Uri):
            return u'U%s' % node.uri
        elif isinstance(node, Blank):
            return u'B%s' % node.identifier
        elif isinstance(node, Literal):
            if node.language is not None:
                return u'L%s\t%s' % (node.language, node.value)
            elif node.datatype is not None:
                return u'D%s\t%s' % (node.datatype, node.value)
            else:
                return u'P%s' % node.value
        else:
            raise ValueError('Internal error in apsw store.')

    def _str_to_node(self, s):
        if s[0] == u'U':
            return Uri(s[1:])
        elif s[0] == u'B':
            return Blank(s[1:])
        elif s[0] == u'L':
            l, v = s.split('\t', 1)
            return Literal(value=v, language=l[1:])
        elif s[0] == u'D':
            d, v = s.split('\t', 1)
            return Literal(value=v, datatype=d[1:])
        elif s[0] == u'P':
            return Literal(value=s[1:])
        else:
            raise ValueError('Internal error in apsw store.')

    def _maybe_begin_transaction(self):
        if self.txn is self.deferred_txn:
            self._do_begin_transaction_harder()

    def _build_match(self, template):
        if template.subject is None:
            if template.predicate is None:
                if template.object is None:
                    stmt = ';'
                    args = ()
                else:
                    stmt = ' WHERE obj = ?;'
                    args = (self._node_to_str(template.object),)
            else:
                if template.object is None:
                    stmt = ' WHERE pre = ?;'
                    args = (self._node_to_str(template.predicate),)
                else:
                    stmt = ' WHERE pre = ? AND obj = ?;'
                    args = (self._node_to_str(template.predicate), self._node_to_str(template.object))
        else:
            if template.predicate is None:
                if template.object is None:
                    stmt = ' WHERE sub = ?;'
                    args = (self._node_to_str(template.subject),)
                else:
                    stmt = ' WHERE sub = ? AND obj = ?;'
                    args = (self._node_to_str(template.subject), self._node_to_str(template.object))
            else:
                if template.object is None:
                    stmt = ' WHERE sub = ? AND pre = ?;'
                    args = (self._node_to_str(template.subject), self._node_to_str(template.predicate))
                else:
                    stmt = ' WHERE sub = ? AND pre = ? AND obj = ?;'
                    args = (self._node_to_str(template.subject), self._node_to_str(template.predicate), self._node_to_str(template.object))
        return (stmt, args)

#
#  XXX: EXPERIMENTAL
#
class SqlalchemySubjectCachedStore(SqlalchemyStore):
    """Caching Sqlalchemy store.

    Maintains a cache of known subjects inside a single transaction.
    For a cached subject, all statements in the database involving
    that subject (in the subject role) are cached in a local cache.
    Any statement queries or database modifications involving that
    subject will be caught and the cached value updated or used if
    the subject matches.

    The data structure is simple: self.subjectcache is a dictionary
    mapping maps _node_to_str processed subject strings to dictionaries.
    Each such dictionary contains _node_to_str processed predicate
    strings, each mapping to a list.  Each such list contains _node_to_str
    processed object strings.

    Note that the correctness of this cache model depends on a few
    basic observations.  First, if a subject is cached, all statements
    related to the subject must be fully maintained (over any remove
    or add operations) or not maintained at all.  Otherwise cached
    responses based on the subject cache may give incorrect results.
    Second, write operations must maintain both subject cache and write
    through to the database (we don't do "write caching" because we
    can't optimize the write anyway).  Third, if in doubt, the subject
    cache can be thrown away without loss of consistency.
    """

    subjectcache = None

    # debug helper
    def _dump_subjectcache(self, ctx=''):
        print 'Subject cache (%s):' % ctx
        if self.subjectcache is None:
            print '    None'
        else:
            for sub_str in self.subjectcache.keys():
                sub = self.subjectcache[sub_str]
                print '    %s' % sub_str
                for pre_str in sub.keys():
                    pre = sub[pre_str]
                    print '        %s' % pre_str
                    for obj_str in pre:
                        print '            %s' % obj_str
                    
    def _process_template(self, template, callback):
        """Work horse for template matching against subject cache."""
        def _process_predicate(sub_str, sub_dict, pre_str):
            t = sub_dict[pre_str]
            if template.object is None:
                tmp = list(t)  # XXX: clone so that caller may modify
                for i in tmp:
                    callback(sub_str, sub_dict, pre_str, t, i)
            else:
                obj_str = self._node_to_str(template.object)
                if obj_str in t:
                    callback(sub_str, sub_dict, pre_str, t, obj_str)
            
        def _process_subject(sub_str):
            t = self.subjectcache[sub_str]
            if template.predicate is None:
                for i in t.keys():
                    _process_predicate(sub_str, t, i)
            else:
                pre_str = self._node_to_str(template.predicate)
                if t.has_key(pre_str):
                    _process_predicate(sub_str, t, pre_str)
                
        if template.subject is None:
            for i in self.subjectcache.keys():
                _process_subject(i)
        else:
            sub_str = self._node_to_str(template.subject)
            if self.subjectcache.has_key(sub_str):
                _process_subject(sub_str)

    def _do_begin_transaction_harder(self):
        super(SqlalchemySubjectCachedStore, self)._do_begin_transaction_harder()
        self.subjectcache = {}  # ensure clean slate

    def _do_commit_transaction(self):
        self.subjectcache = {}  # get rid of the cache asap, to free memory
        super(SqlalchemySubjectCachedStore, self)._do_commit_transaction()

    def _do_rollback_transaction(self):
        self.subjectcache = {}  # get rid of the cache asap, to free memory
        super(SqlalchemySubjectCachedStore, self)._do_rollback_transaction()

    def add_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()

        sub_str = self._node_to_str(statement.subject)
        if self.subjectcache.has_key(sub_str):
            pre_str = self._node_to_str(statement.predicate)
            obj_str = self._node_to_str(statement.object)
            t = self.subjectcache[sub_str]
            if not t.has_key(pre_str):
                t[pre_str] = [obj_str]
            elif obj_str not in t[pre_str]:
                t[pre_str].append(obj_str)
            else:
                pass  # already present, no dups

        # XXX: dup call to maybe_begin_transaction
        return super(SqlalchemySubjectCachedStore, self).add_statement(statement)

    def contains_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()

        sub_str = self._node_to_str(statement.subject)
        if self.subjectcache.has_key(sub_str):
            pre_str = self._node_to_str(statement.predicate)
            t = self.subjectcache[sub_str]
            if not t.has_key(pre_str):
                return False
            if self._node_to_str(statement.object) in t[pre_str]:
                return True
            return False

        # XXX: dup call to maybe_begin_transaction
        return super(SqlalchemySubjectCachedStore, self).contains_statement(statement)

    def remove_statement(self, statement):
        assert statement.concrete(), 'Statement must be concrete'
        self._maybe_begin_transaction()

        sub_str = self._node_to_str(statement.subject)
        if self.subjectcache.has_key(sub_str):
            pre_str = self._node_to_str(statement.predicate)
            t = self.subjectcache[sub_str]
            if t.has_key(pre_str):
                t[pre_str].remove(self._node_to_str(statement.object))

        # XXX: dup call to maybe_begin_transaction
        return super(SqlalchemySubjectCachedStore, self).remove_statement(statement)

    def remove_statements(self, template):
        self._maybe_begin_transaction()

        # update subject cache
        def _callback(sub_str, sub_dict, pre_str, pre_list, obj_str):
            pre_list.remove(obj_str)
        self._process_template(template, _callback)
        
        # XXX: dup call to maybe_begin_transaction
        return super(SqlalchemySubjectCachedStore, self).remove_statements(template)

    def count_statements(self, template):
        # XXX: currently does not use or change subject cache; this is OK,
        # just lack of optimization
        return super(SqlalchemySubjectCachedStore, self).count_statements(template)
    
    def find_statements(self, template):
        self._maybe_begin_transaction()

        # optimize the find_statements() call only if subject is set
        if template.subject is None:
            # XXX: dup call to maybe_begin_transaction
            return super(SqlalchemySubjectCachedStore, self).find_statements(template)

        # check subject cache first
        sub_str = self._node_to_str(template.subject)
        if self.subjectcache.has_key(sub_str):
            res = []
            def _callback(sub_str, sub_dict, pre_str, pre_list, obj_str):
                res.append(Statement(self._str_to_node(sub_str),
                                     self._str_to_node(pre_str),
                                     self._str_to_node(obj_str)))
            self._process_template(template, _callback)
            return res

        # modify query to query all data for the subject in question;
        # then populate initial subject cache entry, and figure out
        # actual result to the find_statements() call

        mod_template = Statement(template.subject, None, None)
        res = super(SqlalchemySubjectCachedStore, self).find_statements(mod_template)
        pre_dict = {}
        self.subjectcache[sub_str] = pre_dict
        for stmt in res:
            pre_str = self._node_to_str(stmt.predicate)
            if pre_dict.has_key(pre_str):
                pre_dict[pre_str].append(self._node_to_str(stmt.object))
            else:
                pre_dict[pre_str] = [self._node_to_str(stmt.object)]

        # respond from subject cache
        res = []
        def _callback(sub_str, sub_dict, pre_str, pre_list, obj_str):
            res.append(Statement(self._str_to_node(sub_str),
                                 self._str_to_node(pre_str),
                                 self._str_to_node(obj_str)))
        self._process_template(template, _callback)
        return res
