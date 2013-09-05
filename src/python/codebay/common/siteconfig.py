"""
Site configuration module

This module both provides a class for holding configuration values and
automatically loading site and user specific customizations to them.

There is a singleton Config class instance, conf, that should imported
into other modules:

>>> from codebay.common.siteconfig import conf

Configuration values should be added with conf.add:

>>> conf.add('doctest_first', 5)
5
>>> conf.add('doctest_second', 'foo')
'foo'
>>> conf.add('doctest_third', True)
True

Configuration values are accessed as attributes of the conf instance:

>>> print conf.doctest_first
5
>>> print conf.doctest_second
foo
>>> print conf.doctest_third
True

The configuration object is automatically initialized from custom
configuration files. A site configuration file (defaults to
\"/etc/codebayrc.py\") is read first and a user configuration file
(defaults to \"~/.codebayrc.py\") next. The configuration files are
simple python source files that are executed in the namespace of this
module. They should set configuration values directly to the conf
instance:

>>> conf.doctest_userfirst = 5
>>> conf.doctest_usersecond = 'bar'

The actual configuration values can be arbitrary Python types - and
the configuration files may do other site specific set up as well.

@var conf:
    Singleton configuration object.
"""
__docformat__ = 'epytext en'

import os

class Config:
    """Configuration holder class."""

    SITECONFFILE = '/etc/codebayrc.py'
    USERCONFFILE = '.codebayrc.py'
    
    def loadConfigFile(self, filename):
        """Load a single configuration file.

        Load a file and execute it in the current namespace. If the
        file cannot be opened, ignore the error silently. If executing
        the file causes errors, they are propagated on.
        """
        try:
            f = open(filename)
        except IOError:
            pass
        else:
            f.close()
            execfile(filename)

    def loadStandardConfig(self):
        """Load site and user configurations.

        Load the site configuration file and the user configuration
        file.
        """
        self.loadConfigFile(self.SITECONFFILE)
        
        if 'HOME' in os.environ:
            home = os.environ['HOME']
        else:
            home = os.path.expanduser("~")
        userconf = os.path.join(home, self.USERCONFFILE)
        self.loadConfigFile(userconf)

    def add(self, name, default):
        """Add a configuration variable.

        Add a single configuration variable with given name and
        default value. The value is not modified if it has already
        been set. This is similar to lisp defvar.
        """
        if not hasattr(self, name):
            setattr(self, name, default)
        return getattr(self, name)

    def set(self, name, value):
        """Set a configuration variables.

        This is not normally used, instead just assign to the
        attribute in question, but it can be used for programmatical
        access to configuration variables.
        """
        setattr(self, name, value)
        return getattr(self, name)
        
    def get(self, name):
        """Get a configuration variable.

        This is not normally used, instead just read the attribute in
        question, but it can be used for programmatical access to
        configuratin variables.
        """
        return getattr(self, name)

conf = Config()
conf.loadStandardConfig()
