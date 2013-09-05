"""
Codebay RDF object wrapper

Note: RDF object wrapper is not currently used, so this code is here
for reference only.

>>> ns_conf = rdf.NS('http://www.example.com/ns/1.0/l2tp-config/1.0/')

>>> class User(RdfObject):
...     _type = ns_conf['User']
...     username = Singleton(ns_conf['username'], rdf.String)
...     password = Singleton(ns_conf['password'], rdf.String)

>>> class Users(RdfObject):
...     _type = ns_conf['Users']
...     user = Set(ns_conf['user'], ObjectType(User))

>>> class Interface(RdfObject):
...     _type = ns_conf['Interface']
...     ip_address = Singleton(ns_conf['ip-address'], rdf.Literal)
...     netmask = Singleton(ns_conf['netmask'], rdf.Literal)
...     gateway = Singleton(ns_conf['gateway'], rdf.Literal)

>>> class Hacks(RdfObject):
...     _type = ns_conf['Hacks']
...     backoff = Singleton(ns_conf['mystery-backoff'], rdf.Seq(rdf.Integer))
...     dnss = Singleton(ns_conf['dns-servers'], rdf.Seq(rdf.Literal))

>>> class L2tpConf(RdfObject):
...     _type = ns_conf['L2tpConf']
...     pre_shared_key = Singleton(ns_conf['pre-shared-key'], rdf.String)
...     idle_timeout = Singleton(ns_conf['idle-timeout'], rdf.Integer)
...     proxy_arp = Singleton(ns_conf['proxy-arp'], rdf.Boolean)
...     public_interface = Singleton(ns_conf['public-interface'], ObjectType(Interface))
...     private_interface = Singleton(ns_conf['private-interface'], ObjectType(Interface))
...     users = Singleton(ns_conf['users'], ObjectType(Users))
...     hacks = Singleton(ns_conf['hacks'], ObjectType(Hacks))

>>> class Root(RdfObject):
...     _type = ns_conf['Root']
...     l2tp_conf = Singleton(ns_conf['l2tp_conf'], ObjectType(L2tpConf))

>>> model = rdf.Model.make()

>>> root = rdf.Node.make(model, ObjectType(Root), ns_conf['root']).getSelf(ObjectType(Root))

>>> root.l2tp_conf = None
>>> l2tp_conf = root.l2tp_conf
>>> l2tp_conf.pre_shared_key = 'abcdefgh'
>>> l2tp_conf.idle_timeout = 5
>>> l2tp_conf.proxy_arp = True

>>> l2tp_conf.public_interface = None
>>> pubif = l2tp_conf.public_interface
>>> pubif.ip_address = '1.2.3.4'
>>> pubif.netmask = '255.255.255.0'
>>> pubif.gateway = '1.2.3.254'

>>> l2tp_conf.private_interface = None
>>> privif = l2tp_conf.private_interface
>>> privif.ip_address = '192.168.0.0'
>>> privif.netmask = '255.255.0.0'
>>> privif.gateway = '192.168.255.254'

>>> l2tp_conf.users = None
>>> users = l2tp_conf.users
>>> user1 = users.user.new()
>>> user1.username = 'naked'
>>> user1.password = 'hellurei'
>>> user2 = users.user.new()
>>> user2.username = 'sva'
>>> user2.password = 'hullupuuro'

>>> l2tp_conf.hacks = None
>>> hacks = l2tp_conf.hacks
>>> hacks.backoff = [1,1,2,3,5]
>>> hacks.dnss = []
>>> hacks.dnss.append('4.2.2.1')
>>> hacks.dnss.append('1.2.3.4')

>>> pruned = model.makePruned(root._node)
>>> s = pruned.toString()
>>> model_ = rdf.Model.fromString(s)
>>> len(pruned) == len(model_)
True

>>> root_ = Root(rdf.Node.make(model, rdf.Resource, ns_conf['root']))

>>> l2tp_conf_ = root.l2tp_conf
>>> l2tp_conf.pre_shared_key
u'abcdefgh'
>>> l2tp_conf.idle_timeout
5
>>> l2tp_conf.proxy_arp
True

>>> pubif = l2tp_conf.public_interface
>>> pubif.ip_address
u'1.2.3.4'
>>> pubif.netmask
u'255.255.255.0'
>>> pubif.gateway
u'1.2.3.254'

>>> privif = l2tp_conf.private_interface
>>> privif.ip_address
u'192.168.0.0'
>>> privif.netmask
u'255.255.0.0'
>>> privif.gateway
u'192.168.255.254'

>>> users = l2tp_conf.users
>>> userset = users.user
>>> v = []
>>> for curuser in userset:
...   v.append((curuser.username,
...             curuser.password))
>>> v.sort()
>>> v
[(u'naked', u'hellurei'), (u'sva', u'hullupuuro')]

>>> hacks = l2tp_conf.hacks
>>> hacks.backoff
[1, 1, 2, 3, 5]
>>> hacks.dnss
[u'4.2.2.1', u'1.2.3.4']

"""
import rdf

class RdfObject(object):
    _type = None

    def __init__(self, node):
        self._node = node

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        return self._node == other._node

    def __ne__(self, other):
        return not (self._node == other)

class ObjectType(rdf.Accessor):
    def __init__(self, dataclass):
        self.dataclass = dataclass

    def parse(self, model, node):
        n = rdf.Resource.parse(model, node)
        if self.dataclass._type is not None:
            if self.dataclass._type not in n.getSet(rdf.RDF_NS.type, rdf.UriType):
                raise rdf.RdfException('Expecting <%s> in properties <%s> for %s, but did not find.' % (self.dataclass._type, rdf.RDF_NS.type, n))
        return self.dataclass(n)

    def build(self, model, value):
        if isinstance(value, RdfObject):
            ret = rdf.Resource.build(model, value._node)
        else:
            ret = rdf.Resource.build(model, value)
        if self.dataclass._type is not None:
            n = rdf.Resource.parse(model, ret)
            n.getSet(rdf.RDF_NS.type, rdf.UriType).add(self.dataclass._type)
        return ret

class RdfDescriptor(object):
    pass

class Singleton(RdfDescriptor):
    def __init__(self, predicate, dataclass):
        self.predicate = predicate
        self.dataclass = dataclass

    def __get__(self, instance, owner):
        return instance._node.getS(self.predicate, self.dataclass)

    def __set__(self, instance, value):
        return instance._node.setS(self.predicate, self.dataclass, value)

    def __delete__(self, instance):
        return instance._node.removeNodes(self.predicate)

class Set(RdfDescriptor):
    def __init__(self, predicate, dataclass):
        self.predicate = predicate
        self.dataclass = dataclass

    def __get__(self, instance, owner):
        return instance._node.getSet(self.predicate, self.dataclass)

    def __set__(self, instance, value):
        s = instance._node.getSet(self.predicate, self.dataclass)
        s.clear()
        for v in value:
            s.add(v)

    def __delete__(self, instance):
        return instance._node.removeNodes(self.predicate)
