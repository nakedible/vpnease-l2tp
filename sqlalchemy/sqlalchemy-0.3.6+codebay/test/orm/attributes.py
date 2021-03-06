from testbase import PersistTest
import sqlalchemy.util as util
import sqlalchemy.orm.attributes as attributes
import unittest, sys, os
import pickle


class MyTest(object):pass
class MyTest2(object):pass
    
class AttributesTest(PersistTest):
    """tests for the attributes.py module, which deals with tracking attribute changes on an object."""
    def testbasic(self):
        class User(object):pass
        manager = attributes.AttributeManager()
        manager.register_attribute(User, 'user_id', uselist = False)
        manager.register_attribute(User, 'user_name', uselist = False)
        manager.register_attribute(User, 'email_address', uselist = False)
        
        u = User()
        print repr(u.__dict__)
        
        u.user_id = 7
        u.user_name = 'john'
        u.email_address = 'lala@123.com'
        
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.email_address == 'lala@123.com')
        manager.commit(u)
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.email_address == 'lala@123.com')

        u.user_name = 'heythere'
        u.email_address = 'foo@bar.com'
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'heythere' and u.email_address == 'foo@bar.com')
        
        manager.rollback(u)
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.email_address == 'lala@123.com')

    def testpickleness(self):
        manager = attributes.AttributeManager()
        manager.register_attribute(MyTest, 'user_id', uselist = False)
        manager.register_attribute(MyTest, 'user_name', uselist = False)
        manager.register_attribute(MyTest, 'email_address', uselist = False)
        manager.register_attribute(MyTest2, 'a', uselist = False)
        manager.register_attribute(MyTest2, 'b', uselist = False)
        # shouldnt be pickling callables at the class level
        def somecallable(*args):
            return None
        manager.register_attribute(MyTest, 'mt2', uselist = True, trackparent=True, callable_=somecallable)
        x = MyTest()
        x.mt2.append(MyTest2())
        
        x.user_id=7
        s = pickle.dumps(x)
        x2 = pickle.loads(s)
        assert s == pickle.dumps(x2)

    def testlist(self):
        class User(object):pass
        class Address(object):pass
        manager = attributes.AttributeManager()
        manager.register_attribute(User, 'user_id', uselist = False)
        manager.register_attribute(User, 'user_name', uselist = False)
        manager.register_attribute(User, 'addresses', uselist = True)
        manager.register_attribute(Address, 'address_id', uselist = False)
        manager.register_attribute(Address, 'email_address', uselist = False)
        
        u = User()
        print repr(u.__dict__)

        u.user_id = 7
        u.user_name = 'john'
        u.addresses = []
        a = Address()
        a.address_id = 10
        a.email_address = 'lala@123.com'
        u.addresses.append(a)

        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.addresses[0].email_address == 'lala@123.com')
        manager.commit(u, a)
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.addresses[0].email_address == 'lala@123.com')

        u.user_name = 'heythere'
        a = Address()
        a.address_id = 11
        a.email_address = 'foo@bar.com'
        u.addresses.append(a)
        print repr(u.__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'heythere' and u.addresses[0].email_address == 'lala@123.com' and u.addresses[1].email_address == 'foo@bar.com')

        manager.rollback(u, a)
        print repr(u.__dict__)
        print repr(u.addresses[0].__dict__)
        self.assert_(u.user_id == 7 and u.user_name == 'john' and u.addresses[0].email_address == 'lala@123.com')
        self.assert_(len(manager.get_history(u, 'addresses').unchanged_items()) == 1)

    def testbackref(self):
        class Student(object):pass
        class Course(object):pass
        manager = attributes.AttributeManager()
        manager.register_attribute(Student, 'courses', uselist=True, extension=attributes.GenericBackrefExtension('students'))
        manager.register_attribute(Course, 'students', uselist=True, extension=attributes.GenericBackrefExtension('courses'))
        
        s = Student()
        c = Course()
        s.courses.append(c)
        print c.students
        print [s]
        self.assert_(c.students == [s])
        s.courses.remove(c)
        self.assert_(c.students == [])
        
        (s1, s2, s3) = (Student(), Student(), Student())
        c.students = [s1, s2, s3]
        self.assert_(s2.courses == [c])
        self.assert_(s1.courses == [c])
        print "--------------------------------"
        print s1
        print s1.courses
        print c
        print c.students
        s1.courses.remove(c)
        self.assert_(c.students == [s2,s3])
        
        
        class Post(object):pass
        class Blog(object):pass
        
        manager.register_attribute(Post, 'blog', uselist=False, extension=attributes.GenericBackrefExtension('posts'), trackparent=True)
        manager.register_attribute(Blog, 'posts', uselist=True, extension=attributes.GenericBackrefExtension('blog'), trackparent=True)
        b = Blog()
        (p1, p2, p3) = (Post(), Post(), Post())
        b.posts.append(p1)
        b.posts.append(p2)
        b.posts.append(p3)
        self.assert_(b.posts == [p1, p2, p3])
        self.assert_(p2.blog is b)
        
        p3.blog = None
        self.assert_(b.posts == [p1, p2])
        p4 = Post()
        p4.blog = b
        self.assert_(b.posts == [p1, p2, p4])
        
        p4.blog = b
        p4.blog = b
        self.assert_(b.posts == [p1, p2, p4])


        class Port(object):pass
        class Jack(object):pass
        manager.register_attribute(Port, 'jack', uselist=False, extension=attributes.GenericBackrefExtension('port'))
        manager.register_attribute(Jack, 'port', uselist=False, extension=attributes.GenericBackrefExtension('jack'))
        p = Port()
        j = Jack()
        p.jack = j
        self.assert_(j.port is p)
        self.assert_(p.jack is not None)
        
        j.port = None
        self.assert_(p.jack is None)

    def testlazytrackparent(self):
        """test that the "hasparent" flag works properly when lazy loaders and backrefs are used"""
        manager = attributes.AttributeManager()

        class Post(object):pass
        class Blog(object):pass

        # set up instrumented attributes with backrefs    
        manager.register_attribute(Post, 'blog', uselist=False, extension=attributes.GenericBackrefExtension('posts'), trackparent=True)
        manager.register_attribute(Blog, 'posts', uselist=True, extension=attributes.GenericBackrefExtension('blog'), trackparent=True)

        # create objects as if they'd been freshly loaded from the database (without history)
        b = Blog()
        p1 = Post()
        Blog.posts.set_callable(b, lambda:[p1])
        Post.blog.set_callable(p1, lambda:b)
        manager.commit(p1, b)

        # no orphans (called before the lazy loaders fire off)
        assert getattr(Blog, 'posts').hasparent(p1, optimistic=True)
        assert getattr(Post, 'blog').hasparent(b, optimistic=True)

        # assert connections
        assert p1.blog is b
        assert p1 in b.posts
        
        # manual connections
        b2 = Blog()
        p2 = Post()
        b2.posts.append(p2)
        assert getattr(Blog, 'posts').hasparent(p2)
        assert getattr(Post, 'blog').hasparent(b2)
        
    def testinheritance(self):
        """tests that attributes are polymorphic"""
        class Foo(object):pass
        class Bar(Foo):pass
        
        manager = attributes.AttributeManager()
        
        def func1():
            print "func1"
            return "this is the foo attr"
        def func2():
            print "func2"
            return "this is the bar attr"
        def func3():
            print "func3"
            return "this is the shared attr"
        manager.register_attribute(Foo, 'element', uselist=False, callable_=lambda o:func1)
        manager.register_attribute(Foo, 'element2', uselist=False, callable_=lambda o:func3)
        manager.register_attribute(Bar, 'element', uselist=False, callable_=lambda o:func2)
        
        x = Foo()
        y = Bar()
        assert x.element == 'this is the foo attr'
        assert y.element == 'this is the bar attr'
        assert x.element2 == 'this is the shared attr'
        assert y.element2 == 'this is the shared attr'

    def testinheritance2(self):
        """test that the attribute manager can properly traverse the managed attributes of an object,
        if the object is of a descendant class with managed attributes in the parent class"""
        class Foo(object):pass
        class Bar(Foo):pass
        manager = attributes.AttributeManager()
        manager.register_attribute(Foo, 'element', uselist=False)
        x = Bar()
        x.element = 'this is the element'
        hist = manager.get_history(x, 'element')
        assert hist.added_items() == ['this is the element']
        manager.commit(x)
        hist = manager.get_history(x, 'element')
        assert hist.added_items() == []
        assert hist.unchanged_items() == ['this is the element']

    def testlazyhistory(self):
        """tests that history functions work with lazy-loading attributes"""
        class Foo(object):pass
        class Bar(object):
            def __init__(self, id):
                self.id = id
            def __repr__(self):
                return "Bar: id %d" % self.id
                
        manager = attributes.AttributeManager()

        def func1():
            return "this is func 1"
        def func2():
            return [Bar(1), Bar(2), Bar(3)]

        manager.register_attribute(Foo, 'col1', uselist=False, callable_=lambda o:func1)
        manager.register_attribute(Foo, 'col2', uselist=True, callable_=lambda o:func2)
        manager.register_attribute(Bar, 'id', uselist=False)

        x = Foo()
        manager.commit(x)
        x.col2.append(Bar(4))
        h = manager.get_history(x, 'col2')
        print h.added_items()
        print h.unchanged_items()

        
    def testparenttrack(self):    
        class Foo(object):pass
        class Bar(object):pass
        
        manager = attributes.AttributeManager()
        
        manager.register_attribute(Foo, 'element', uselist=False, trackparent=True)
        manager.register_attribute(Bar, 'element', uselist=False, trackparent=True)
        
        f1 = Foo()
        f2 = Foo()
        b1 = Bar()
        b2 = Bar()
        
        f1.element = b1
        b2.element = f2
        
        assert manager.get_history(f1, 'element').hasparent(b1)
        assert not manager.get_history(f1, 'element').hasparent(b2)
        assert not manager.get_history(f1, 'element').hasparent(f2)
        assert manager.get_history(b2, 'element').hasparent(f2)
        
        b2.element = None
        assert not manager.get_history(b2, 'element').hasparent(f2)

    def testmutablescalars(self):
        """test detection of changes on mutable scalar items"""
        class Foo(object):pass
        manager = attributes.AttributeManager()
        manager.register_attribute(Foo, 'element', uselist=False, copy_function=lambda x:[y for y in x], mutable_scalars=True)
        x = Foo()
        x.element = ['one', 'two', 'three']    
        manager.commit(x)
        x.element[1] = 'five'
        assert manager.is_modified(x)
        
        manager.reset_class_managed(Foo)
        manager = attributes.AttributeManager()
        manager.register_attribute(Foo, 'element', uselist=False)
        x = Foo()
        x.element = ['one', 'two', 'three']    
        manager.commit(x)
        x.element[1] = 'five'
        assert not manager.is_modified(x)
        
    def testdescriptorattributes(self):
        """changeset: 1633 broke ability to use ORM to map classes with unusual
        descriptor attributes (for example, classes that inherit from ones
        implementing zope.interface.Interface).
        This is a simple regression test to prevent that defect.
        """
        class des(object):
            def __get__(self, instance, owner): raise AttributeError('fake attribute')

        class Foo(object):
            A = des()

        manager = attributes.AttributeManager()
        manager.reset_class_managed(Foo)
        
if __name__ == "__main__":
    unittest.main()
