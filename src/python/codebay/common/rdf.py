"""
Codebay RDF utils.

The Codebay RDF utils define a set of classes to be used for
manipulating RDF graphs.

Example Usage
=============

This is a complete example of using these classes to create and parse
a simple RDF configuration file.

First we need to define the namespace that we are using.

>>> ns_terms = NS('http://www.example.com/ns/1.0/l2tp-config/1.0/terms/',
...               globalConfigRoot = 'globalConfigRoot',
...               GlobalConfigRoot = 'GlobalConfigRoot',
...               L2tpConfig = 'L2tpConfig',
...               l2tpConfig = 'l2tpConfig',
...               preSharedKey = 'preSharedKey',
...               idleTimeout = 'idleTimeout',
...               proxyArp = 'proxyArp',
...               publicInterface = 'publicInterface',
...               privateInterface = 'privateInterface',
...               users = 'users',
...               Interface = 'Interface',
...               ipAddress = 'ipAddress',
...               netmask = 'netmask',
...               gateway = 'gateway',
...               User = 'User',
...               username = 'username',
...               password = 'password',
...               Hacks = 'Hacks',
...               mysteryBackoff = 'mysteryBackoff',
...               dnsServers = 'dnsServers')

We start by making an empty in-memory model.

>>> model = Model.make()

Then we make our global root node. It is the only node which has a
well defined URI. We also specify the type for the node which means
that an rdf:type is automatically added for the node.

>>> globalroot = Node.make(model, Type(ns_terms.GlobalConfigRoot), ns_terms.globalConfigRoot)

Then our actual configuration root as a child of the global root
node. This is a new blank node.

>>> l2tp_conf = globalroot.setS(ns_terms.l2tpConfig, Type(ns_terms.L2tpConfig))

Now we are ready to start adding values to our root. Note that we are
assigning the result to _ here just for convenience as we don't care
about the return type. The return value of setS is the set value
parsed back from the node.

>>> _ = l2tp_conf.setS(ns_terms.preSharedKey, String, 'abcdefgh')
>>> _ = l2tp_conf.setS(ns_terms.idleTimeout, Integer, 5)
>>> _ = l2tp_conf.setS(ns_terms.proxyArp, Boolean, True)

The config is structured with some new blank nodes for the different
interfaces. Note that we wish to give a common type for all our
interfaces.

>>> pubif = l2tp_conf.setS(ns_terms.publicInterface, Type(ns_terms.Interface))
>>> _ = pubif.setS(ns_terms.ipAddress, IPv4Address, '1.2.3.4')
>>> _ = pubif.setS(ns_terms.netmask, IPv4Address, '255.255.255.0')
>>> _ = pubif.setS(ns_terms.gateway, IPv4Address, '1.2.3.254')

>>> privif = l2tp_conf.setS(ns_terms.privateInterface, Type(ns_terms.Interface))
>>> _ = privif.setS(ns_terms.ipAddress, IPv4Address, '192.168.0.0')
>>> _ = privif.setS(ns_terms.netmask, IPv4Address, '255.255.0.0')
>>> _ = privif.setS(ns_terms.gateway, IPv4Address, '192.168.255.254')

Users are added as an RDF Bag container.

>>> users = l2tp_conf.setS(ns_terms.users, Bag(Type(ns_terms.User)))
>>> user1 = users.new()
>>> _ = user1.setS(ns_terms.username, String, 'naked')
>>> _ = user1.setS(ns_terms.password, Binary, 'hellurei')
>>> user2 = users.new()
>>> _ = user2.setS(ns_terms.username, String, 'sva')
>>> _ = user2.setS(ns_terms.password, Binary, 'hullupuuro')

Just as a test, we add an ad-hoc property, 'loop', pointing at our
configuration root to show that parts of the configuration can
reference other parts of the configuration directly. This is not a
tree, it's a graph.

>>> loop = user2.setS(ns_terms['loop'], Resource, l2tp_conf) # Just to show it doesn't croak

Some other uses of sequences.

>>> backoff = l2tp_conf.setS(ns_terms.mysteryBackoff, Seq(Integer), [1,1,2,3,5])

>>> dnss = l2tp_conf.setS(ns_terms.dnsServers, Seq(IPv4Address))
>>> dnss.append('4.2.2.1')
>>> dnss.append('1.2.3.4')

The configuration is now complete. We want to prune the config from
any additional nodes by only taking statements starting from the
global config root. And in this case, we write the configuration to a
string, instead of a file.

>>> pruned = model.makePruned(globalroot)
>>> s = pruned.toString()

Next up is parsing the entire configuration starting from the string
we just created. In this example, all the new variable names are
suffixed with an underscore to differentiate them from the ones we
used before. First we create a model by parsing the string.

>>> model_ = Model.fromString(s)

Just to be safe, in this example we check that we got as many
statements back as we wrote out. This isn't normally done.

>>> len(pruned) == len(model_)
True

Root node is found by finding the config starting from the global
config root.

>>> globalroot_ = model.getNodeByUri(ns_terms.globalConfigRoot, Type(ns_terms.GlobalConfigRoot))
>>> l2tp_conf_ = globalroot.getS(ns_terms.l2tpConfig, Type(ns_terms.L2tpConfig))

Now we read back the values we wrote earlier.

>>> l2tp_conf_.getS(ns_terms.preSharedKey, String)
u'abcdefgh'
>>> l2tp_conf_.getS(ns_terms.idleTimeout, Integer)
5
>>> l2tp_conf_.getS(ns_terms.proxyArp, Boolean)
True

When accessing the structure, we make sure to check the type of the
structured nodes.

>>> pubif_ = l2tp_conf_.getS(ns_terms.publicInterface, Type(ns_terms.Interface))
>>> pubif_.getS(ns_terms.ipAddress, IPv4Address).toString()
'1.2.3.4'
>>> pubif_.getS(ns_terms.netmask, IPv4Address).toString()
'255.255.255.0'
>>> pubif_.getS(ns_terms.gateway, IPv4Address).toString()
'1.2.3.254'

>>> privif_ = l2tp_conf_.getS(ns_terms.privateInterface, Type(ns_terms.Interface))
>>> privif_.getS(ns_terms.ipAddress, IPv4Address).toString()
'192.168.0.0'
>>> privif_.getS(ns_terms.netmask, IPv4Address).toString()
'255.255.0.0'
>>> privif_.getS(ns_terms.gateway, IPv4Address).toString()
'192.168.255.254'

Users are accessed as Bag.

>>> users_ = l2tp_conf_.getS(ns_terms.users, Bag(Type(ns_terms.User)))
>>> len(users_)
2
>>> for curuser in users_:
...   print curuser.getS(ns_terms.username, String)
...   print curuser.getS(ns_terms.password, Binary)
naked
hellurei
sva
hullupuuro

Just checking if the loop element is still there.

>>> loop = users[1].getS(ns_terms['loop'])

And the other sequences that were set.

>>> l2tp_conf_.getS(ns_terms.mysteryBackoff, Seq(Integer))
[1, 1, 2, 3, 5]

>>> [x.toString() for x in l2tp_conf_.getS(ns_terms.dnsServers, Seq(IPv4Address))]
['4.2.2.1', '1.2.3.4']

@group Namespaces: RDF_NS, RDF_NUM_NS, XSD_NS, TYPES_NS
@var RDF_NS:
  The core RDF namespace.
@var RDF_NUM_NS:
  The core RDF number namespace.
@var XSD_NS:
  The XSD namespace.
@var TYPES_NS:
  The Codebay types namespace.
@group Lookup directions: toSubject, toObject
@var toSubject:
  Specifies that lookup should be done from object to subject via
  predicate. Given as an argument to several functions in L{Node}.
@var toObject:
  Specifies that lookup should be done from subject to object via
  predicate. Given as an argument to several functions in L{Node}.
"""
__docformat__ = 'epytext en'

import os, datetime, re, traceback
from sets import Set as set
from twisted.python.util import mergeFunctionMetadata

from codebay.common import logger, datatypes, randutil, tinyrdf
_log = logger.get('common.rdf')

Uri = tinyrdf.Uri

# for API markers
_invalid = object()

def makeUuidUri():
    return tinyrdf.uuid.next()

NS = tinyrdf.NS

RDF_NS = NS('http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            type = None,
            Bag = None,
            Alt = None,
            Seq = None,
            value = None)

RDF_NUM_NS = NS('http://www.w3.org/1999/02/22-rdf-syntax-ns#_')

XSD_NS = NS('http://www.w3.org/2001/XMLSchema#',
            string = None,
            integer = None,
            double = None,
            boolean = None,
            base64Binary = None,
            dateTime = None,
            dayTimeDuration = None)

TYPES_NS = NS('http://purl.org/NET/codebay/1.0/types/1.0/',
              ipv4Address = None,
              ipv4Subnet = None,
              ipv4AddressSubnet = None,
              ipv4AddressRange = None,
              port = None,
              portRange = None)

toSubject = 0
toObject = 1

def _get_func_info(f):
    # NB: Function attributes are not always available, so check for each one separately.
    # In particular, when a decorator gets an (at least an inner) function, it does not
    # have __file__ and __line__.
    
    if hasattr(f, '__name__'):
        fname = f.__name__
    elif hasattr(f, 'func_name'):
        fname = f.func_name
    else:
        fname = '<unknown>'

    if hasattr(f, '__file__'):
        ffile = f.__file__
    elif hasattr(f, 'func_code') and hasattr(f.func_code, 'co_filename'):
        ffile = f.func_code.co_filename
    else:
        ffile = '<unknown>'

    if hasattr(f, '__line__'):
        fline = str(f.__line__)
    elif hasattr(f, 'func_code') and hasattr(f.func_code, 'co_firstlineno'):
        fline = str(f.func_code.co_firstlineno)
    else:
        fline = '<unknown>'

    return fname, ffile, fline

def _get_formatted_func_info(f):
    fname, ffile, fline = _get_func_info(f)
    return '%s in %s:%s' % (fname, ffile, fline)

def _transact_begin(f, model, logname, silent):
    t = None
    if not model.is_transaction_active():
        if not silent:
            _log.warning('%s: starting an autotransaction: %s\n%s' % (logname, _get_formatted_func_info(f), ''.join(traceback.format_stack())))
        t = model.begin_transaction()
    return t

def _transact_end(f, t, logname, silent):
    if t is not None:
        if not silent:
            _log.warning('%s: committing an autotransaction: %s\n%s' % (logname, _get_formatted_func_info(f), ''.join(traceback.format_stack())))
        t.commit()

def modeltransact(model, silent=False):
    def _f(f):
        def g(*args, **kw):
            t = _transact_begin(f, model, 'modeltransact', silent)
            try:
                return f(*args, **kw)
            finally:
                _transact_end(f, t, 'modeltransact', silent)
        mergeFunctionMetadata(f, g)
        return g
    return _f
    
def selftransact(silent=False):
    def _f(f):
        def g(self, *args, **kw):
            t = _transact_begin(f, self, 'selftransact', silent)
            try:
                return f(self, *args, **kw)
            finally:
                _transact_end(f, t, 'selftransact', silent)
        mergeFunctionMetadata(f, g)
        return g
    return _f

def selfmodeltransact(silent=False):
    def _f(f):
        def g(self, *args, **kw):
            t = _transact_begin(f, self.model, 'selfmodeltransact', silent)
            try:
                return f(self, *args, **kw)
            finally:
                _transact_end(f, t, 'selfmodeltransact', silent)
        mergeFunctionMetadata(f, g)
        return g
    return _f

def selfnodemodeltransact(silent=False):
    def _f(f):
        def g(self, *args, **kw):
            t = _transact_begin(f, self.node.model, 'selfnodemodeltransact', silent)
            try:
                return f(self, *args, **kw)
            finally:
                _transact_end(f, t, 'selfnodemodeltransact', silent)
        mergeFunctionMetadata(f, g)
        return g
    return _f

class RdfException(Exception):
    """RDF Exception"""

#
#  XXX: handling of self.store in the functions below is a bit bad API design.
#  First of all, the functions will fail with an exception if the database is
#  closed which is more or less OK.  The exceptions just could be of a better
#  sort ('DatabaseClosedError' instead of some random exception because self.store
#  is None or non-existent).  Second, the caller has no reasonable way of checking
#  whether the API functions can be called (i.e. whether the database has been
#  closed or not), so it's not even possible to avoid bogus calls properly without
#  checking for the 'store' attribute directly (a violation of several principles).
#  Finally, even checking for 'store' is difficult because it is *deleted*, not
#  set to None, when closing.  So caller has to use something like:
#
#      if hasattr(foo, 'store') and (foo.store is not None):
#          ... foo.is_transaction_active() ...
#
#  Not very pretty.  Currently this mostly interacts with autoclosing and the
#  codebay.l2tpserver.db transaction helpers, which have a fix for this now.
#

class BaseModel:
    """Base model Class."""
    store = None

    def _get_parser(self, name):
        if name == 'rdfxml':
            return tinyrdf.RdfxmlSubsetParser()      # XXX: subset of RDF/XML only
        elif name == 'ntriples':
            return tinyrdf.NtriplesParser()
        elif name == 'pickle':
            return tinyrdf.PickleParser()
        else:
            raise RdfException('Unknown parser name "%s".' % name)

    def _get_serializer(self, name):  
        if name == 'rdfxml':
            return tinyrdf.RdfxmlSubsetSerializer()  # XXX: subset of RDF/XML only
        elif name == 'ntriples':
            return tinyrdf.NtriplesSerializer()
        elif name == 'pickle':
            return tinyrdf.PickleSerializer()
        else:
            raise RdfException('Unknown serializer name "%s".' % name)

    @selftransact()
    def loadFile(self, filename, name = 'rdfxml'):
        p = self._get_parser(name)
        self.store.add_statements(p.parseFile(filename))

    @selftransact()
    def loadString(self, value, name = 'rdfxml'):
        p = self._get_parser(name)
        self.store.add_statements(p.parseString(value))

    @selftransact()
    def toFile(self, filename, name = 'rdfxml', namespaces = {}):
        serializer = self._get_serializer(name)
        serializer.serializeFile(self.store.all_statements(), filename)

    @selftransact()
    def toString(self, name = 'rdfxml', namespaces = {}):
        serializer = self._get_serializer(name)
        return serializer.serializeString(self.store.all_statements())

    @selftransact()
    def prune(self, root):
        """Prunes an RDF model in place.

        Traverses statements from each subject to object starting from
        the given root and listing seen objects as it goes. Then
        iterates through all statements and removes them if their
        subjects are not on the list.
        """
        handled = set()
        queue = [root.node]
        handled.add(root.node)
        while len(queue):
            curnode = queue.pop(0)
            template = tinyrdf.Statement(curnode, None, None)
            for stmt in self.store.find_statements(template):
                if stmt.object not in handled:
                    handled.add(stmt.object)
                    queue.append(stmt.object)
        todelete = []
        for stmt in self.store.all_statements():
            if stmt.subject not in handled:
                todelete.append(stmt)
        for stmt in todelete:
            self.store.remove_statement(stmt)

    @selftransact()
    def pruneTo(self, root, newmodel):
        """Prune starting from a root node into a new model."""

        # XXX: duplication with prune

        @modeltransact(newmodel)
        def _f():
            handled = set()
            queue = [root.node]
            handled.add(root.node)
            while len(queue):
                curnode = queue.pop(0)
                template = tinyrdf.Statement(curnode, None, None)
                for stmt in self.store.find_statements(template):
                    if stmt.object not in handled:
                        handled.add(stmt.object)
                        queue.append(stmt.object)
                    newmodel.store.add_statement(stmt)
        _f()
        return newmodel

    @selftransact()
    def makePruned(self, root):
        """Returns a new RDF memory model, pruned by starting from root.

        Creates a new empty RDF model, then starts copying statements
        from this model by traversing from each subject to object
        starting from the given root and returning the new model.
        """
        newmodel = Model.make()

        # This is a silent autotransact because caller cannot do this
        @modeltransact(newmodel, silent=True)
        def _f():
            self.pruneTo(root, newmodel)
        _f()

        return newmodel

    @selftransact()
    def getPruneStatistics(self, root):
        """Execute a pseudo-prune and produce useful RDF database statistics."""
        
        # XXX: duplication with prune and pruneTo
        handled = set()
        queue = [root.node]
        handled.add(root.node)
        while len(queue):
            curnode = queue.pop(0)
            template = tinyrdf.Statement(curnode, None, None)
            for stmt in self.store.find_statements(template):
                if stmt.object not in handled:
                    handled.add(stmt.object)
                    queue.append(stmt.object)

        count, reachable = 0, 0
        for stmt in self.store.all_statements():
            count += 1
            if stmt.subject in handled:
                reachable += 1

        return count, reachable

    @selftransact()
    def getNodeByUri(self, uri, dataclass = None):
        """Gets a Node instance by giving an uri and optional dataclass.

        >>> ns = NS('http://www.example.com/#')
        >>> model = Model.make()
        >>> model.getNodeByUri(ns['example'], Type(ns['Example']))
        Traceback (most recent call last):
          ...
        RdfException: Expecting <http://www.example.com/#Example> in properties <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> for <http://www.example.com/#example>, but did not find.
        >>> _ = Node.make(model, Type(ns['Example']), ns['example'])
        >>> n = model.getNodeByUri(ns['example'], Type(ns['Example']))
        >>> str(n.getUri())
        'http://www.example.com/#example'
        """
        return Node.make(self, UriType, uri).getSelf(dataclass)

    def _findNodes(self, val1, val2, direction = None):
        res = []
        if direction is None or direction is toObject:
            template = tinyrdf.Statement(val1, val2, None)
            for stmt in self.store.find_statements(template):
                res.append(stmt.object)
        elif direction is toSubject:
            template = tinyrdf.Statement(None, val2, val1)
            for stmt in self.store.find_statements(template):
                res.append(stmt.subject)
        else:
            raise RdfException('Unknown find type %s.' % repr(direction))
        return res

    def _findNodePairs(self, node):
        res = []
        stm_temp = tinyrdf.Statement(node, None, None)
        for s in self.store.find_statements(stm_temp):
            res.append([s.predicate, s.object])
        return res

    def begin_transaction(self):
        return self.store.begin_transaction()

    def begin_untransaction(self):
        return self.store.begin_untransaction()

    def is_transaction_active(self):
        return self.store.is_transaction_active()

    def __len__(self):
        return self.store.count_statements(tinyrdf.Statement(None, None, None))

    def close(self):
        self.store.close()
        del self.store

class Model(BaseModel):
    """Memory model."""

    def make(klass):
        m = klass()

        # XXX: When using SqlAlchemy/Sqlite memory stores, the following
        # fails completely (with errors about recursive transactions):
        #
        #  from codebay.common import rdf
        #  from codebay.l2tpserver import db
        #
        #  def _test1():
        #    m1 = rdf.Model.make()
        #    # t1 = m1.begin_transaction()   # fails with or without
        #    n1 = rdf.Node.make(m1, rdf.Resource, rdf.Uri('urn:1'))
        #    n1.setS(rdf.Uri('urn:arc1'), rdf.String, 'val1')
        #    #print m1.toString()
        #    # t1.commit()
        #  _test1()
        #
        # So, here we use the tinyrdf.MemoryStore which is simple but
        # works for our purposes.
        
        #m.store = tinyrdf.SqlalchemyStore.create('sqlite:///')
        m.store = tinyrdf.MemoryStore.create()
        
        return m
    make = classmethod(make)

    def fromFile(klass, filename, name = 'rdfxml'):
        m = klass.make()

        # This is silent because caller cannot use a transact decorator on the
        # model - we're creating the instance here.
        @modeltransact(m, silent=True)
        def _f():
            m.loadFile(filename, name)
        _f()
        
        return m
    fromFile = classmethod(fromFile)

    def fromString(klass, value, name = 'rdfxml'):
        m = klass.make()

        # This is silent because caller cannot use a transact decorator on the
        # model - we're creating the instance here.
        @modeltransact(m, silent=True)
        def _f():
            m.loadString(value, name)
        _f()
        
        return m
    fromString = classmethod(fromString)

class Database(BaseModel):
    """Database model."""

    # XXX: This API call does not protect against race conditions; e.g. two callers
    # may both first delete the database and then try to create it.  Further, there
    # is no protection against someone using open() at the same time as create().
    def create(klass, filename):
        """Create a new database.

        This means overwriting any already existing database.
        """
        klass.delete(filename)
        m = klass()
        # NB: this parameterization is crucial for correctly working transactions, beware
        #m.store = tinyrdf.SqlalchemyStore.create('sqlite:///%s' % filename, connect_args={'timeout': 300.0, 'isolation_level': None})
        m.store = tinyrdf.ApswStore.create(filename)
###     m.store = tinyrdf.SqlalchemySubjectCachedStore.create('sqlite:///%s' % filename, connect_args={'timeout': 300.0, 'isolation_level': None})
        return m
    create = classmethod(create)

    def open(klass, filename):
        """Open an already existing database.

        Note that this function call returning an opened database does
        not mean that the database is valid, or even if it is valid
        that writing to it would succeed.
        """
        m = klass()
        # NB: this parameterization is crucial for correctly working transactions, beware
        #m.store = tinyrdf.SqlalchemyStore.open('sqlite:///%s' % filename, connect_args={'timeout': 300.0, 'isolation_level': None})
        m.store = tinyrdf.ApswStore.open(filename)
###     m.store = tinyrdf.SqlalchemySubjectCachedStore.open('sqlite:///%s' % filename, connect_args={'timeout': 300.0, 'isolation_level': None})
        return m
    open = classmethod(open)

    def delete(klass, filename):
        """Delete a database if it exists."""
        try:
            os.unlink(filename)
        except OSError:
            pass
        try:
            os.unlink('%s.journal' % filename)
        except OSError:
            pass
    delete = classmethod(delete)

class Node:
    """Node Class

    >>> model = Model.make()
    >>> node = Node.make(model)
    """

    def __init__(self, model, node):
        self.model = model
        self.node = node

    # Factory methods

    def make(klass, model, dataclass = None, value = None):
        if dataclass is None:
            dataclass = Resource
        node = dataclass.build(model, value)
        return klass(model, node)
    make = classmethod(make)

    def isResource(self):
        return isinstance(self.node, tinyrdf.Uri)

    def isBlank(self):
        return isinstance(self.node, tinyrdf.Blank)

    def isLiteral(self):
        return isinstance(self.node, tinyrdf.Literal)
    
    def getUri(self):
        # NB! Returns a string, not a Uri
        return self.node.uri

    def getBlankIdentifier(self):
        return self.node.identifier

    def getLiteral(self):
        return self.node.value

    def getDatatype(self):
        return self.node.datatype

    def getLanguage(self):
        return self.node.language

    @selfmodeltransact()
    def getSelf(self, dataclass = None):
        if dataclass is None:
            dataclass = Resource
        return dataclass.parse(self.model, self.node)

    # Python internals

    def __str__(self):
        return str(self.node)

    def __unicode__(self):
        return unicode(self.node)

    def __cmp__(self, other):
        return (cmp(self.__class__, other.__class__) or
                cmp(self.node, other.node))

    def __hash__(self):
        return hash((self.__class__, self.node))

    # Accessors

    @selfmodeltransact()
    def countNodes(self, predicate, direction = None):
        i = 0
        for _ in self.model._findNodes(self.node, predicate, direction):
            i += 1
        return i

    @selfmodeltransact()
    def iterNodes(self, predicate, dataclass = None, direction = None):
        """Use getNodes unless you know what you are doing."""
        if dataclass is None:
            dataclass = Resource
        for node in self.model._findNodes(self.node, predicate, direction):
            yield dataclass.parse(self.model, node)

    @selfmodeltransact()
    def getNodes(self, predicate, dataclass = None, direction = None):
        return list(self.iterNodes(predicate, dataclass, direction))

    @selfmodeltransact()
    def getNodePairs(self):
        t = []
        for [p,o] in self.model._findNodePairs(self.node):
            t.append([Node(self.model, p), Node(self.model, o)])
        return t
    
    @selfmodeltransact()
    def getS(self, predicate, dataclass = None, direction = None, default = _invalid):
        nodes = self.getNodes(predicate, dataclass, direction)
        if len(nodes) == 0:
            if default == _invalid:
                raise RdfException('Expecting singleton property <%s> for %s, but got none.' % (predicate, self))
            else:
                return default
        elif len(nodes) > 1:
            raise RdfException('Expecting singleton property <%s> for %s, but got several.' % (predicate, self))
        return nodes[0]

    @selfmodeltransact()
    def hasS(self, predicate, direction = None):
        # Note: this does not take a type
        c = self.countNodes(predicate, direction)
        if c == 0:
            return False
        elif c == 1:
            return True
        else:
            raise RdfException('Expecting singleton property <%s> for %s, but got several.' % (predicate, self))

    def getSet(self, predicate, dataclass = None):
        return NodeSet(self, predicate, dataclass)

    @selfmodeltransact()
    def removeAll(self):
        template = tinyrdf.Statement(self.node, None, None)
        self.model.store.remove_statements(template)

    @selfmodeltransact()
    def removeNodes(self, predicate):
        template = tinyrdf.Statement(self.node, predicate, None)
        self.model.store.remove_statements(template)

    @selfmodeltransact()
    def removeNode(self, predicate, dataclass = None, value = None):
        if dataclass is None:
            dataclass = Resource
        stmt = tinyrdf.Statement(self.node, predicate, dataclass.build(self.model, value))
        self.model.store.remove_statement(stmt)

    @selfmodeltransact()
    def addNode(self, predicate, dataclass = None, value = None):
        if dataclass is None:
            dataclass = Resource
        stmt = tinyrdf.Statement(self.node, predicate, dataclass.build(self.model, value))
        self.model.store.add_statement(stmt)
        return dataclass.parse(self.model, stmt.object)

    @selfmodeltransact()
    def setS(self, predicate, dataclass = None, value = None):
        self.removeNodes(predicate)
        return self.addNode(predicate, dataclass, value)

    # Convenience helpers for rdf:types

    @selfmodeltransact()
    def hasType(self, uri):
        return uri in self.getSet(RDF_NS.type, UriType)

    @selfmodeltransact()
    def addType(self, uri):
        self.getSet(RDF_NS.type, UriType).add(uri)

# Container classes

class NodeSet:
    """Node Set Class

    Implements a set of Nodes as a set.
    """
    
    def __init__(self, node, predicate, dataclass = None):
        self.node = node
        self.predicate = predicate
        if dataclass is None:
            self.dataclass = Resource
        else:
            self.dataclass = dataclass

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self.node == other.node and self.predicate == other.predicate

    def __ne__(self, other):
        return not (self == other)

    @selfnodemodeltransact()
    def __len__(self):
        return self.node.countNodes(self.predicate)

    @selfnodemodeltransact()
    def __iter__(self):
        # This first builds the list and then returns an iterator to
        # it to prevent possibly removing statements while iterating.
        return iter(self.node.getNodes(self.predicate, self.dataclass))

    @selfnodemodeltransact()
    def add(self, value):
        self.node.addNode(self.predicate, self.dataclass, value)

    @selfnodemodeltransact()
    def remove(self, value):
        if value in self:
            self.discard(value)
        else:
            raise KeyError(value)

    @selfnodemodeltransact()
    def discard(self, value):
        self.node.removeNode(self.predicate, self.dataclass, value)

    @selfnodemodeltransact()
    def pop(self, value):
        for v in self:
            self.discard(v)
            return v
        raise KeyError(value)

    @selfnodemodeltransact()
    def clear(self):
        self.node.removeNodes(self.predicate)

    @selfnodemodeltransact()
    def new(self, value = None):
        return self.node.addNode(self.predicate, self.dataclass, value)

class NodeContainer(list):
    """Node Container Class

    Implements an RDF Container interface as a list.
    """

    def __init__(self, node, ctype, dataclass = None):
        self.node = node
        self.ctype = ctype
        if dataclass is None:
            self.dataclass = Resource
        else:
            self.dataclass = dataclass

    @selfnodemodeltransact()
    def _read(self):
        self[:] = []
        i = 0
        if self.node.getS(RDF_NS.type, UriType) != self.ctype:
            raise RdfException('Expecting <%s> as property <%s> for %s, but got %s' % (self.ctype, RDF_NS.type, self.node,
                                                                                       self.node.getS(RDF_NS.type)))
        while self.node.hasS(RDF_NUM_NS[i+1]):
            self.append(self.node.getS(RDF_NUM_NS[i+1], self.dataclass))
            i += 1

    @selfnodemodeltransact()
    def _write(self, iterable):
        self.node.removeAll()
        self.node.setS(RDF_NS.type, UriType, self.ctype)
        self[:] = []
        i = 0
        for v in iterable:
            self.append(self.node.setS(RDF_NUM_NS[i+1], self.dataclass, v))
            i += 1

    @selfnodemodeltransact()
    def _wrap(self, op, *args, **kw):
        prev = self[:]
        prevlen = len(prev)
        ret = op(self, *args, **kw)
        for i in range(len(self)):
            if i >= prevlen or prev[i] != self[i]:
                self[i] = self.node.setS(RDF_NUM_NS[i+1], self.dataclass, self[i])
        for j in range(len(self), len(prev)):
            self.node.removeNodes(RDF_NUM_NS[j+1])
        return ret

    def __delitem__(self, *args, **kw):
        return self._wrap(list.__delitem__, *args, **kw)
    def __delslice__(self, *args, **kw):
        return self._wrap(list.__delslice__, *args, **kw)
    def __iadd__(self, *args, **kw):
        return self._wrap(list.__iadd__, *args, **kw)
    def __imul__(self, *args, **kw):
        return self._wrap(list.__imul__, *args, **kw)
    def __setitem__(self, *args, **kw):
        return self._wrap(list.__setitem__, *args, **kw)
    def __setslice__(self, *args, **kw):
        return self._wrap(list.__setslice__, *args, **kw)
    def append(self, *args, **kw):
        return self._wrap(list.append, *args, **kw)
    def extend(self, *args, **kw):
        return self._wrap(list.extend, *args, **kw)
    def insert(self, *args, **kw):
        return self._wrap(list.insert, *args, **kw)
    def pop(self, *args, **kw):
        return self._wrap(list.pop, *args, **kw)
    def remove(self, *args, **kw):
        return self._wrap(list.remove, *args, **kw)
    def reverse(self, *args, **kw):
        return self._wrap(list.reverse, *args, **kw)
    def sort(self, *args, **kw):
        return self._wrap(list.sort, *args, **kw)        

    def new(self, value = None):
        self.append(value)
        return self[-1]

# XXX: too difficult to implement and useless for us
# class NodeCollection(list):
#    pass

# Datatype classes

class Accessor:
    """Datatype Accessor Base Class

    This is the base class for all datatype accessors. All datatype
    accessors should inherit from this and override the parse and
    build methods.
    """

    def parse(klass, model, node):
        """Given a model and an RDF node, return a value parsed from the node."""
        raise NotImplemented
    parse = classmethod(parse)

    def build(klass, model, value):
        """Given a model and a value, return and RDF node built from the value."""
        raise NotImplemented
    build = classmethod(build)

class Resource(Accessor):
    """Resource Datatype Class

    This is the most generic datatype accessor. When setting values it
    acts based on the type of the argument. If the argument is None,
    the value set will be a newly generated UUID URI. If the argument
    is a string or an URI the value set will be a node with that
    URI. If the argument is another Node instance, the value set will
    be set to the same value is the given argument. When getting
    values, it will always return Node instances.

    >>> model = Model.make()
    >>> blank = Node.make(model, Resource, None)
    >>> uri = Node.make(model, Resource, 'http://example.com/')
    >>> uri = Node.make(model, Resource, Uri('http://example.com/'))
    >>> node = Node.make(model, Resource, Node.make(model))
    >>> n = node.getSelf(Resource)
    >>> isinstance(n, Node)
    True
    """
    
    def parse(klass, model, node):
        return Node(model, node)
    parse = classmethod(parse)

    def build(klass, model, value):
        if value is None:
            return makeUuidUri()
        elif isinstance(value, Node):
            return value.node
        elif isinstance(value, tinyrdf.Uri):
            return value
        elif isinstance(value, str):
            return tinyrdf.Uri(value)
        else:
            raise RdfException('Cannot set resource from %s.' % repr(value))
    build = classmethod(build)

class NodeType(Accessor):
    """Node Datatype Class

    The NodeType datatype accessor is used when the arguments are
    decidedly other Node instances. When setting values, the argument
    should be another Node instance. When getting values, the returned
    value will always be Node instances.

    >>> model = Model.make()
    >>> node = Node.make(model, NodeType, Node.make(model))
    >>> n = node.getSelf(NodeType)
    >>> isinstance(n, Node)
    True
    """
    
    def parse(klass, model, node):
        return Node(model, node)
    parse = classmethod(parse)

    def build(klass, model, value):
        if isinstance(value, Node):
            return value.node
            raise RdfException('Cannot set node from %s.' % repr(value))
    build = classmethod(build)

class UriType(Accessor):
    """Uri Datatype Class

    The UriType datatype accessor is used when the arguments are
    decidedly URIs. When setting values, strings and URIs are
    converted to nodes with that URI. When getting values, the
    returned value will always be an URI.

    >>> model = Model.make()
    >>> node = Node.make(model, UriType, 'http://example.com/')
    >>> node = Node.make(model, UriType, Uri('http://example.com/'))
    >>> uri = node.getSelf(UriType)
    >>> str(uri)
    '<http://example.com/>'
    """
    
    def parse(klass, model, node):
        if not isinstance(node, tinyrdf.Uri):
            raise RdfException('Node %s is not a resource.' % Node(model, node))
        return node
    parse = classmethod(parse)

    def build(klass, model, value):
        if isinstance(value, tinyrdf.Uri):
            return value
        elif isinstance(value, str):
            return tinyrdf.Uri(value)
        else:
            raise RdfException('Cannot set uri from %s.' % repr(value))
    build = classmethod(build)

class Blank(Accessor):
    """Blank Node Datatype Class

    The Blank node datatype accessor is rarely used as Resource can be
    used to generate new blank nodes. This is used when it is
    necessary to directly access the blank node identifier of a
    node. When setting values, None is converted to a new blank node
    and a string is converted to a blank node with that
    identifier. When getting values, the blank node identifier of the
    node is returned as a string.

    >>> model = Model.make()
    >>> blank = Node.make(model, Blank, None)
    >>> blank = Node.make(model, Blank, 'foobar')
    >>> blank.getSelf(Blank)
    u'foobar'
    """
    
    def parse(klass, model, node):
        if not isinstance(node, tinyrdf.Blank):
            raise RdfException('Node %s is not a blank node.' % Node(model, node))
        return node.identifier
    parse = classmethod(parse)

    def build(klass, model, value):
        if value is None:
            return tinyrdf.Blank()
        elif isinstance(value, str):
            return tinyrdf.Blank(value)
        else:
            raise RdfException('Cannot set blank from %s.' % repr(value))
    build = classmethod(build)

class Uuid(Accessor):
    """UUID Datatype Class

    The UUID datatype accessor is to automatically generate random
    UUID URI Nodes. When setting values, only None is accepted as a
    value and a new random UUID has been generated. When getting
    values, the returned value will always be an URI.

    >>> model = Model.make()
    >>> node = Node.make(model, Uuid, None)
    >>> uuid = node.getSelf(Uuid)
    >>> str(uuid)[:9]
    'urn:uuid:'
    """

    def parse(klass, model, node):
        if not isinstance(node, tinyrdf.Uri):
            raise RdfException('Node %s is not a resource.' % Node(model, node))
        return node.uri
    parse = classmethod(parse)

    def build(klass, model, value):
        if value is None:
            return makeUuidUri()
        else:
            raise RdfException('Cannot set uuid from %s.' % repr(value))
    build = classmethod(build)

class Literal(Accessor):
    """Literal Datatype Class

    The Literal datatype accessor is used to access untyped
    literals. When setting values, strings and unicode strings are
    converted to literal nodes with that value. When getting values,
    the literal value of the node is returned as an unicode string.

    >>> model = Model.make()
    >>> literal = Node.make(model, Literal, u'foobar')
    >>> literal.getSelf(Literal)
    u'foobar'
    """
    
    def parse(klass, model, node):
        if not isinstance(node, tinyrdf.Literal):
            raise RdfException('Node %s is not a literal.' % Node(model, node))
        if node.datatype is not None:
            raise RdfException('Expecting literal with no datatype but got %s.' % Node(model, node))
        return node.value
    parse = classmethod(parse)

    def build(klass, model, value):
        if isinstance(value, str):
            return tinyrdf.Literal(unicode(value))
        elif isinstance(value, unicode):
            return tinyrdf.Literal(value)
        else:
            raise RdfException('Cannot set literal from %s.' % repr(value))
    build = classmethod(build)

class TypedLiteral(Accessor):
    """Typed Literal Datatype Class

    The TypedLiteral datatype accessor is a base class for all typed
    literal datatype accessors and should not be used directly. It has
    a datatype member which should be set to the URI of the datatype
    and parse_value and build_value methods should be overriden to
    provide conversions for the actual value.

    >>> class MyLiteral(TypedLiteral):
    ...   datatype = Uri('http://example.com/')
    >>> model = Model.make()
    >>> myliteral = Node.make(model, MyLiteral, u'foobar')
    >>> myliteral.getSelf(MyLiteral)
    u'foobar'
    """

    datatype = None
    
    def parse(klass, model, node):
        if not isinstance(node, tinyrdf.Literal):
            raise RdfException('Node %s is not a literal.' % Node(model, node))
        if not tinyrdf.Uri(node.datatype) == klass.datatype:
            raise RdfException('Expecting literal with datatype <%s> but got %s.' % (klass.datatype,
                                                                                     Node(model, node)))
        return klass.parse_value(node.value)
    parse = classmethod(parse)

    def parse_value(klass, value):
        """Parse the given unicode string to the return value."""
        return value
    parse_value = classmethod(parse_value)

    def build(klass, model, value):
        return tinyrdf.Literal(klass.build_value(value), datatype = klass.datatype.uri, language = None)
    build = classmethod(build)

    def build_value(klass, value):
        """Encode the given value into an unicode string."""
        return value
    build_value = classmethod(build_value)

class String(TypedLiteral):
    """String Literal Datatype Class

    The String datatype accessor handles xsd:string values. The
    arguments are unicode strings made directly into RDF
    literals. Special characters may not be encoded correctly in this
    format so don't use this for arbitrary data.

    >>> model = Model.make()
    >>> string = Node.make(model, String, u'foobar')
    >>> string.getSelf(String)
    u'foobar'
    """
    
    datatype = XSD_NS.string
    
    def parse_value(klass, value):
        return value
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, unicode):
            return value
        elif isinstance(value, str):
            return unicode(value)
        else:
            raise RdfException('Cannot set string from %s.' % repr(value))
    build_value = classmethod(build_value)

class Integer(TypedLiteral):
    """Integer Literal Datatype Class

    The Integer datatype accessor handles xsd:integer values. The
    arguments are Python integer or long values. Arbitrary length
    integers are supported.

    >>> model = Model.make()
    >>> string = Node.make(model, Integer, 5)
    >>> string.getSelf(Integer)
    5
    """

    datatype = XSD_NS.integer

    def parse_value(klass, value):
        return int(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, (int, long)):
            return u'%d' % value
        else:
            raise RdfException('Cannot set integer from %s.' % repr(value))
    build_value = classmethod(build_value)

class Float(TypedLiteral):
    """Float Literal Datatype Class

    The Float datatype accessor handles xsd:double values. The
    arguments are Python float values.

    NOTE: The accuracy of these values is not specified by Python, so
    they do not correspond identically to the XSD datatype.

    >>> model = Model.make()
    >>> f = Node.make(model, Float, 5.6)
    >>> f.getLiteral()
    u'5.6'
    >>> f.getSelf(Float)
    5.5999999999999996
    >>> f = Node.make(model, Float, float('nan'))
    >>> f.getLiteral()
    u'NaN'
    >>> f.getSelf(Float)
    nan
    >>> f = Node.make(model, Float, float('-inf'))
    >>> f.getLiteral()
    u'-INF'
    >>> f.getSelf(Float)
    -inf
    """
    # XXX:
    # Hadaka:#python => how to write inf, -inf and nan literals in python?
    # Yhg1s:#python => Hadaka: you can't, portably.
    # Hadaka:#python => Yhg1s: oh? what do I do then?
    # Yhg1s:#python => Hadaka: live without them, or use a package that tries
    # better to handle them portably. Or only run your code on systems where
    # 'float('nan')' works.
    # Hadaka:#python => Yhg1s: yikes! okay, thanks.

    datatype = XSD_NS.double

    def parse_value(klass, value):
        return float(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, float):
            v = str(value)
            if v == 'nan':
                return 'NaN'
            elif v == 'inf':
                return 'INF'
            elif v == '-inf':
                return '-INF'
            else:
                return v
        else:
            raise RdfException('Cannot set float from %s.' % repr(value))
    build_value = classmethod(build_value)

class Boolean(TypedLiteral):
    """Boolean Literal Datatype Class

    The Boolean datatype accessor handles xsd:boolean values. The
    arguments are Python boolean values.

    >>> model = Model.make()
    >>> string = Node.make(model, Boolean, True)
    >>> string.getSelf(Boolean)
    True
    """

    datatype = XSD_NS.boolean

    def parse_value(klass, value):
        if value in ['true', '1']:
            return True
        elif value in ['false', '0']:
            return False
        else:
            raise RdfException('Cannot get boolean from "%s"' % value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, bool):
            truth = value
        else:
            raise RdfException('Cannot set boolean from %s.' % repr(value))
        if truth:
            return u'true'
        else:
            return u'false'
    build_value = classmethod(build_value)

class Binary(TypedLiteral):
    """Binary Literal Datatype Class

    The Binary datatype accessor handles xsd:base64Binary values. The
    arguments are Python string values that are encoded to and from
    base64 representations.

    >>> model = Model.make()
    >>> binary = Node.make(model, Binary, 'foo')
    >>> binary.getSelf(Binary)
    'foo'
    """

    datatype = XSD_NS.base64Binary

    def parse_value(klass, value):
        return str(value).decode('base64')
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, str):
            return unicode(value.encode('base64'))
        else:
            raise RdfException('Cannot set binary from %s.' % repr(value))
    build_value = classmethod(build_value)

#
#  XXX: this could share code with codebay.common.datatypes
#
class Datetime(TypedLiteral):
    """Datetime Literal Datatype Class

    The Datetime datatype accessor handles xsd:dateTime values. The
    arguments are Python datetime instances.

    NOTE: This handles only a really small subset of XSD datatype.

    >>> model = Model.make()
    >>> dt = Node.make(model, Datetime, datetime.datetime(2006, 6, 7, 1, 28, 30, 1242))
    >>> dt.getLiteral()
    u'2006-06-07T01:28:30.001242Z'
    >>> dt.getSelf(Datetime)
    datetime.datetime(2006, 6, 7, 1, 28, 30, 1242)
    """

    datatype = XSD_NS.dateTime
    DATETIME_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z')

    def parse_value(klass, value):
        m = klass.DATETIME_RE.match(value)
        if not m:
            raise RdfException('Cannot get datetime from "%s".' % value)
        try:
            year = int(m.group(1))
            month = int(m.group(2))
            day = int(m.group(3))
            hour = int(m.group(4))
            minute = int(m.group(5))
            second = int(m.group(6))
            if m.group(7) is not None:
                microsecond = int((m.group(7)+'000000')[:6])
            else:
                microsecond = 0
        except ValueError:
            raise RdfException('Cannot get datetime from "%s".' % value)
        return datetime.datetime(year, month, day, hour, minute, second, microsecond)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datetime.datetime):
            if value.tzinfo is not None:
                raise RdfException('Cannot set datetime from non-naive %s.' % repr(value))
            return '%sZ' % value.isoformat()
        else:
            raise RdfException('Cannot set datetime from %s.' % repr(value))
    build_value = classmethod(build_value)

class Timedelta(TypedLiteral):
    """Timedelta Literal Datatype Class

    The Timedelta datatype accessor handles xsd:dayTimeDuration
    values. The arguments are Python timedelta instances.

    NOTE: This handles only a really small subset of XSD
    datatype. Also note that xsd:dayTimeDuration objects are always
    expressable in seconds where as xsd:duration objects vary in
    length because of the month field.

    >>> model = Model.make()
    >>> td = Node.make(model, Timedelta, datetime.timedelta(53, 13601, 2354))
    >>> td.getLiteral()
    u'P53DT13601.002354S'
    >>> td.getSelf(Timedelta)
    datetime.timedelta(53, 13601, 2354)
    >>> td = Node.make(model, Timedelta, datetime.timedelta(-1, -5, -5))
    >>> td.getLiteral()
    u'-P1DT5.000005S'
    >>> td.getSelf(Timedelta)
    datetime.timedelta(-2, 86394, 999995)
    """

    datatype = XSD_NS.dayTimeDuration
    TIMEDELTA_RE = re.compile(r'(-)?P(\d+)DT(\d+)(?:.(\d{1,6}))S')

    def parse_value(klass, value):
        m = klass.TIMEDELTA_RE.match(value)
        if not m:
            raise RdfException('Cannot get timedelta from "%s".' % value)
        try:
            if m.group(1) is None:
                sign = 1
            else:
                sign = -1
            day = int(m.group(2))*sign
            second = int(m.group(3))*sign
            if m.group(4) is not None:
                microsecond = int((m.group(4)+'000000')[:6])*sign
            else:
                microsecond = 0
        except ValueError:
            raise RdfException('Cannot get timedelta from "%s".' % value)
        return datetime.timedelta(day, second, microsecond)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datetime.timedelta):
            if value < datetime.timedelta():
                d = abs(value)
                sign = '-'
            else:
                d = value
                sign = ''
            return '%sP%dDT%d.%6.6dS' % (sign, d.days, d.seconds, d.microseconds)
        else:
            raise RdfException('Cannot set timedelta from %s.' % repr(value))
    build_value = classmethod(build_value)

class IPv4Address(TypedLiteral):
    """IPv4 Address Literal Datatype Class

    The IPv4Address datatype accessor handles Codebay
    types:ipv4Address values. The arguments are IPv4Address class
    instances, but as a convenience string arguments are automatically
    converted to IPv4Addresses.

    >>> model = Model.make()
    >>> ipv4addr = Node.make(model, IPv4Address, datatypes.IPv4Address.fromString('1.2.3.4'))
    >>> ipv4addr.getSelf(IPv4Address).toString()
    '1.2.3.4'
    >>> ipv4addr = Node.make(model, IPv4Address, '1.2.3.4')
    >>> ipv4addr.getSelf(IPv4Address).toString()
    '1.2.3.4'
    """

    datatype = TYPES_NS.ipv4Address

    def parse_value(klass, value):
        return datatypes.IPv4Address.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.IPv4Address):
            return value.toString()
        elif isinstance(value, (str, unicode)):
            return datatypes.IPv4Address.fromString(value).toString()
        else:
            raise RdfException('Cannot set IPv4Address from %s.' % repr(value))
    build_value = classmethod(build_value)

class IPv4Subnet(TypedLiteral):
    """IPv4 Subnet Literal Datatype Class
    
    The IPv4Subnet datatype accessor handles Codebay types:ipv4Subnet
    values. The arguments are IPv4Subnet class instances, but as a
    convenience string arguments are automatically converted to
    IPv4Subnets.

    >>> model = Model.make()
    >>> ipv4subnet = Node.make(model, IPv4Subnet, datatypes.IPv4Subnet.fromString('10.0.0.0/8'))
    >>> ipv4subnet.getSelf(IPv4Subnet).toString()
    '10.0.0.0/8'
    >>> ipv4subnet = Node.make(model, IPv4Subnet, '20.20.20.0/31')
    >>> ipv4subnet.getSelf(IPv4Subnet).toString()
    '20.20.20.0/31'
    """

    datatype = TYPES_NS.ipv4Subnet

    def parse_value(klass, value):
        return datatypes.IPv4Subnet.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.IPv4Subnet):
            return value.toString()
        elif isinstance(value, (str, unicode)):
            return datatypes.IPv4Subnet.fromString(value).toString()
        else:
            raise RdfException('Cannot set IPv4Subnet from %s.' % repr(value))
    build_value = classmethod(build_value)

class IPv4AddressSubnet(TypedLiteral):
    """IPv4 Address Subnet Literal Datatype Class
    
    The IPv4AddressSubnet datatype accessor handles Codebay
    types:ipv4AddressSubnet values. The arguments are
    IPv4AddressSubnet class instances, but as a convenience string
    arguments are automatically converted to IPv4AddresseSubnets.

    >>> model = Model.make()
    >>> ipv4addrsubnet = Node.make(model, IPv4AddressSubnet, datatypes.IPv4AddressSubnet.fromString('1.2.3.4/32'))
    >>> ipv4addrsubnet.getSelf(IPv4AddressSubnet).toString()
    '1.2.3.4/32'
    >>> ipv4addrsubnet = Node.make(model, IPv4AddressSubnet, '1.2.3.4/24')
    >>> ipv4addrsubnet.getSelf(IPv4AddressSubnet).toString()
    '1.2.3.4/24'
    """

    datatype = TYPES_NS.ipv4AddressSubnet

    def parse_value(klass, value):
        return datatypes.IPv4AddressSubnet.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.IPv4AddressSubnet):
            return value.toString()
        elif isinstance(value, (str, unicode)):
            return datatypes.IPv4AddressSubnet.fromString(value).toString()
        else:
            raise RdfException('Cannot set IPv4AddressSubnet from %s.' % repr(value))
    build_value = classmethod(build_value)

class IPv4AddressRange(TypedLiteral):
    """IPv4 Address Range Literal Datatype Class

    The IPv4AddressRange datatype accessor handles Codebay
    types:ipv4AddressRange values. The arguments are IPv4AddressRange
    class instances, but as a convenience string arguments are
    automatically converted to IPv4AddresseRanges.

    >>> model = Model.make()
    >>> ipv4addrrange = Node.make(model, IPv4AddressRange, datatypes.IPv4AddressRange.fromString('1.2.3.4-1.2.3.5'))
    >>> ipv4addrrange.getSelf(IPv4AddressRange).toString()
    '1.2.3.4-1.2.3.5'
    >>> ipv4addrrange = Node.make(model, IPv4AddressRange, '1.2.3.4-1.2.3.5')
    >>> ipv4addrrange.getSelf(IPv4AddressRange).toString()
    '1.2.3.4-1.2.3.5'
    """

    datatype = TYPES_NS.ipv4AddressRange

    def parse_value(klass, value):
        return datatypes.IPv4AddressRange.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.IPv4AddressRange):
            return value.toString()
        elif isinstance(value, (str, unicode)):
            return datatypes.IPv4AddressRange.fromString(value).toString()
        else:
            raise RdfException('Cannot set IPv4AddressRange from %s.' % repr(value))
    build_value = classmethod(build_value)

class Port(TypedLiteral):
    """Port Literal Datatype Class
    
    The Port datatype accessor handles Codebay types:port values. The
    arguments are Port class instances, but as a convenience string
    and integer arguments are automatically converted to
    Ports.

    >>> model = Model.make()
    >>> port = Node.make(model, Port, datatypes.Port.fromString('65365'))
    >>> port.getSelf(Port).toString()
    '65365'
    >>> port = Node.make(model, Port, '0')
    >>> port.getSelf(Port).toString()
    '0'
    >>> port = Node.make(model, Port, 0)
    >>> port.getSelf(Port).toString()
    '0'
    """

    datatype = TYPES_NS.port

    def parse_value(klass, value):
        return datatypes.Port.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.Port):
            return value.toString()
        elif isinstance(value, (str, unicode)):
            return datatypes.Port.fromString(value).toString()
        elif isinstance(value, (int, long)):
            return datatypes.Port.fromLong(value).toString()
        else:
            raise RdfException('Cannot set Port from %s.' % repr(value))
    build_value = classmethod(build_value)

class PortRange(TypedLiteral):
    """Port Range Literal Datatype Class
    
    The PortRange datatype accessor handles Codebay types:portRange
    values. The arguments are PortRange class instances, but as a
    convenience string arguments are automatically converted to
    PortRanges.

    >>> model = Model.make()
    >>> ipv4addr = Node.make(model, PortRange, datatypes.PortRange.fromString('10-12'))
    >>> ipv4addr.getSelf(PortRange).toString()
    '10-12'
    >>> ipv4addr = Node.make(model, PortRange, u'100-200')
    >>> ipv4addr.getSelf(PortRange).toString()
    '100-200'
    """

    datatype = TYPES_NS.portRange

    def parse_value(klass, value):
        return datatypes.PortRange.fromString(value)
    parse_value = classmethod(parse_value)

    def build_value(klass, value):
        if isinstance(value, datatypes.PortRange):
            return value.toString()
        if isinstance(value, (str, unicode)):
            return datatypes.PortRange.fromString(value).toString()
        else:
            raise RdfException('Cannot set PortRange from %s.' % repr(value))
    build_value = classmethod(build_value)

class Container(Accessor):
    """Container Datatype Class

    The Container datatype accessor is a base class for all RDF
    container accessors. It has a ctype member which should be set to
    the URI of container type.

    >>> class MyContainer:
    ...   ctype = Uri('http://example.com')
    """

    ctype = None

    def __init__(self, dataclass):
        if dataclass is None:
            self.dataclass = Resource
        else:
            self.dataclass = dataclass

    def parse(self, model, node):
        newnode = Node(model, node)
        container = NodeContainer(newnode, self.ctype, self.dataclass)
        container._read()
        return container

    def build(self, model, value):
        newnode = Node.make(model)
        container = NodeContainer(newnode, self.ctype, self.dataclass)
        if value is None:
            container._write([])
        else:
            container._write(value)
        return newnode.node

class Bag(Container):
    """Bag Container Datatype Class

    The Bag container datatype accessor is used to access rdf:Bag type
    containers. It should be instanced with the datatype accessor for
    the invidual values as the argument. When setting values, a None
    argument is converted to an empty list and any other values are
    interpreted as an iterable to set values from. When getting values
    a NodeContainer instance is returned, which behaves like a Python
    list.

    >>> model = Model.make()
    >>> bag = Node.make(model, Bag(Integer), [1, 2, 3])
    >>> bag.getSelf(Bag(Integer))
    [1, 2, 3]
    """

    ctype = RDF_NS.Bag

class Seq(Container):
    """Seq Container Datatype Class

    The Seq container datatype accessor is used to access rdf:Seq type
    containers. It should be instanced with the datatype accessor for
    the invidual values as the argument. When setting values, a None
    argument is converted to an empty list and any other values are
    interpreted as an iterable to set values from. When getting values
    a NodeContainer instance is returned, which behaves like a Python
    list.

    >>> model = Model.make()
    >>> seq = Node.make(model, Seq(Integer), [1, 2, 3])
    >>> seq.getSelf(Seq(Integer))
    [1, 2, 3]
    """

    ctype = RDF_NS.Seq

class Alt(Container):
    """Alt Container Datatype Class

    The Alt container datatype accessor is used to access rdf:Alt type
    containers. It should be instanced with the datatype accessor for
    the invidual values as the argument. When setting values, a None
    argument is converted to an empty list and any other values are
    interpreted as an iterable to set values from. When getting values
    a NodeContainer instance is returned, which behaves like a Python
    list.

    >>> model = Model.make()
    >>> alt = Node.make(model, Alt(Integer), [1, 2, 3])
    >>> alt.getSelf(Alt(Integer))
    [1, 2, 3]
    """

    ctype = RDF_NS.Alt

class Type(Accessor):
    """Typed Node Datatype Class

    The Type accessor is used to access resource with a certain
    rdf:type. It should be instanced with the desired rdf:type
    URI. When setting values, it will behave identically to the
    Resource accessor, but it will add the given rdf:type to for the
    node. When getting values, it will behave identically to the
    Resource accessor, but it will verify that the returned Node has
    the given rdf:type.

    >>> model = Model.make()
    >>> node = Node.make(model, Type(Uri('http://example.com')), None)
    >>> n = node.getSelf(Type(Uri('http://example.com')))
    >>> isinstance(n, Node)
    True
    """

    def __init__(self, rdftype):
        self.rdftype = rdftype

    def parse(self, model, node):
        n = Resource.parse(model, node)

        # XXX: this gave trouble with 'iterable argument required', hence wrapping
        nodetypes = None
        try:
            nodetypes = n.getSet(RDF_NS.type, UriType)
            if self.rdftype not in nodetypes:
                raise RdfException('Expecting %s in properties %s for %s, but did not find.' % (self.rdftype, RDF_NS.type, n))
        except TypeError:
            _log.exception('parse failed unexpectedly, self: %s, self.rdftype: %s, node: %s, nodetypes: %s' % (self, self.rdftype, n, nodetypes))
        return n

    def build(self, model, value):
        v = Resource.build(model, value)
        n = Resource.parse(model, v)
        n.getSet(RDF_NS.type, UriType).add(self.rdftype)
        return v

def deepCopy(from_node, to_node, clone_prefixes=['urn:uuid:']):
    """Make a 'deep' copy of all arcs with from_node as source to to_node.

    The copying process handles different nodes as follows.  Literals are
    shared, as they are immutable.  Blank nodes currently cause an exception,
    although they could be copied (as separate blank nodes).  Property nodes
    are shared.

    Resources are tricky.  We basically only want to clone resources that
    have a specific URI prefix.  For instance, we don't want to clone
    a Resources indicating rdf:type as being an rdf Seq.  To overcome this
    limitation, the caller supplies a list of URI prefixes for cloning.
    If one of the URI prefixes matches the URI of the node, the node is
    cloned with a fresh UUID URI.  (This could also have been implemented
    the other way around.)

    The process detects and handles loops: a node is not cloned twice,
    but the clone is shared as in the original.
    
    The from_node and to_node parameters must be resources, not literal values.

    The caller should be in a transaction to make the copy process both atomic
    and quick.
    """

    if not (isinstance(from_node, Node) and \
            (from_node.isResource() or from_node.isBlank())):
        raise Exception('from_node is of invalid type')
    if not (isinstance(to_node, Node) and \
            (to_node.isResource() or to_node.isBlank())):
        raise Exception('to_node is of invalid type')

    cloned = {}   # old URI -> new node
    visited = {}  # visited: shared or cloned

    def _do_copy(f, t):
        if f.isBlank() or t.isBlank():
            raise Exception('blank node encountered during deep copy')

        for [p,o] in f.getNodePairs():
            if o.isLiteral():
                # XXX: Slight abuse. Using addNode() is painful because of the way
                # it mixes the layers; in particular, how to deal with untyped and
                # typed literals (and literal languages) comfortably?
                stmt = tinyrdf.Statement(t.node, p.node, o.node)
                t.model.store.add_statement(stmt)
            elif o.isBlank():
                raise Exception('blank node encountered during deep copy')
            elif o.isResource():
                o_uri = o.getUri()  # string
                clone = False
                for pfx in clone_prefixes:
                    if o_uri.startswith(pfx):
                        clone = True
                        break

                o_new = None
                created_new = False
                if clone:
                    if cloned.has_key(o_uri):
                        o_new = cloned[o_uri]
                    else:
                        created_new = True
                        o_new = Node.make(o.model)  # UUID URI node
                        cloned[o_uri] = o_new
                else:
                    o_new = o  # share

                visited[f.getUri()] = 1

                t.addNode(p.node, Resource, o_new.node)

                if created_new:
                    # only need to recurse the first time
                    _do_copy(o, o_new)
                else:
                    # no need to recurse, shared
                    pass

    _do_copy(from_node, to_node)
