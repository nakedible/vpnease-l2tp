from twisted.trial import unittest

from codebay.common import tinyrdf

class _TestStore(object):
    store = None

    def createStore(self):
        raise NotImplemented()

    def clearStore(self):
        self.store.remove_statements(tinyrdf.Statement(None, None, None))
        self.failUnless(self.store.count_statements(tinyrdf.Statement(None, None, None)) == 0)

    def setUp(self):
        self.store = self.makeStore()

    def tearDown(self):
        self.store.close()
        self.store = None

    def test_basic(self):
        self.clearStore()
        subject1 = tinyrdf.Blank()
        subject2 = tinyrdf.Blank()
        st1 = tinyrdf.Statement(subject1,
                                tinyrdf.Uri('http://www.example.com/#aaa'),
                                tinyrdf.Literal('AAA'))
        st2 = tinyrdf.Statement(subject1,
                                tinyrdf.Uri('http://www.example.com/#bbb'),
                                tinyrdf.Literal('BBB'))
        st3 = tinyrdf.Statement(subject2,
                                tinyrdf.Uri('http://www.example.com/#aaa'),
                                tinyrdf.Literal('CCC'))
        self.store.add_statement(st1)
        self.failUnlessEqual(list(self.store.find_statements(tinyrdf.Statement(None, None, None))), [st1])
        self.failUnless(self.store.contains_statement(st1))
        self.store.add_statement(st2)
        self.failUnless(self.store.contains_statement(st2))
        self.store.remove_statement(st1)
        self.failUnlessEqual(list(self.store.find_statements(tinyrdf.Statement(None, None, None))), [st2])
        self.store.add_statements([st1, st3])
        self.failUnlessEqual(self.store.count_statements(tinyrdf.Statement(subject1, None, None)), 2)
        self.failUnlessEqual(self.store.count_statements(tinyrdf.Statement(None, tinyrdf.Uri('http://www.example.com/#aaa'), None)), 2)
        self.failUnlessEqual(self.store.count_statements(tinyrdf.Statement(subject1, tinyrdf.Uri('http://www.example.com/#aaa'), None)), 1)
        self.store.remove_statements(tinyrdf.Statement(subject1, None, None))
        self.failUnlessEqual(list(self.store.find_statements(tinyrdf.Statement(None, None, None))), [st3])
        self.clearStore()

    def test_errors(self):
        self.clearStore()
        subject1 = tinyrdf.Blank()
        st1 = tinyrdf.Statement(subject1,
                                tinyrdf.Uri('http://www.example.com/#aaa'),
                                tinyrdf.Literal('AAA'))
        self.store.add_statement(st1)
        self.store.add_statement(st1)
        self.failUnlessEqual(list(self.store.find_statements(tinyrdf.Statement(None, None, None))), [st1])
        self.store.remove_statement(st1)
        self.store.remove_statement(st1)
        self.failUnlessEqual(list(self.store.find_statements(tinyrdf.Statement(None, None, None))), [])
        self.clearStore()

class TestMemoryStore(_TestStore, unittest.TestCase):
    def makeStore(self):
        return tinyrdf.MemoryStore.create()

class TestSqlalchemyStore(_TestStore, unittest.TestCase):
    def makeStore(self):
        return tinyrdf.SqlalchemyStore.create('sqlite:///')

class TestApswStore(_TestStore, unittest.TestCase):
    def makeStore(self):
        return tinyrdf.ApswStore.create(':memory:')

class TestUri(unittest.TestCase):
    def test_basic(self):
        u = tinyrdf.Uri('http://www.example.com/#xxx')
        self.failUnlessEqual(u.uri, u'http://www.example.com/#xxx')
        self.failUnlessEqual(repr(u), "Uri(u'http://www.example.com/#xxx')")
        self.failUnlessEqual(unicode(u), u'<http://www.example.com/#xxx>')
        self.failUnlessEqual(u, u)
        u2 = tinyrdf.Uri('http://www.example.com/#xxx')
        self.failUnlessEqual(u, u2)
        u3 = tinyrdf.Uri('http://www.example.com/#yyy')
        self.failIfEqual(u, u3)
        
class TestBlank(unittest.TestCase):
    def test_basic(self):
        u = tinyrdf.Blank('blank1')
        self.failUnlessEqual(u.identifier, u'blank1')
        self.failUnlessEqual(repr(u), "Blank(u'blank1')")
        self.failUnlessEqual(unicode(u), u'_:blank1')
        self.failUnlessEqual(u, u)
        u2 = tinyrdf.Blank('blank1')
        self.failUnlessEqual(u, u2)
        u3 = tinyrdf.Blank('blank2')
        self.failIfEqual(u, u3)
        u4 = tinyrdf.Blank()
        u5 = tinyrdf.Blank()
        self.failIfEqual(u4, u5)
        
class TestLiteral(unittest.TestCase):
    def test_basic(self):
        u = tinyrdf.Literal('xxx')
        self.failUnlessEqual(u.value, u'xxx')
        self.failUnlessEqual(repr(u), "Literal(u'xxx')")
        self.failUnlessEqual(unicode(u), u"u'xxx'")
        self.failUnlessEqual(u, u)
        u2 = tinyrdf.Literal('xxx')
        self.failUnlessEqual(u, u2)
        u3 = tinyrdf.Literal('yyy')
        self.failIfEqual(u, u3)

    def test_language(self):
        pass

    def test_datatype(self):
        pass
        
class TestStatement(unittest.TestCase):
    def test_basic(self):
        pass

class TestNamespace(unittest.TestCase):
    def test_plain(self):
        ns = tinyrdf.NS('http://www.example.com/#')
        self.failUnless(isinstance(ns[''], tinyrdf.Uri))
        self.failUnlessEqual(ns[''].uri, 'http://www.example.com/#')
        self.failUnlessEqual(ns['a'].uri, 'http://www.example.com/#a')
        self.failUnlessEqual(ns['foo/bar'].uri, 'http://www.example.com/#foo/bar')

    def test_keywords(self):
        ns = tinyrdf.NS('http://www.example.com/#',
                    a = 'a',
                    uri = 'uri',
                    foo = 'bar')
        self.failUnlessEqual(ns.a.uri, 'http://www.example.com/#a')
        self.failUnlessEqual(ns.uri.uri, 'http://www.example.com/#uri')
        self.failUnlessEqual(ns.foo.uri, 'http://www.example.com/#bar')

