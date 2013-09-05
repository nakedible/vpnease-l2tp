"""
Codebay site-wide default configuration.

The format of this file is normal Python syntax where configuration
values are directly modified in the 'conf' object.

Example:
>>> conf.conftest_test1 = 5
>>> conf.conftest_test2 = 'test'
>>> conf.conftest_test3 = True

Use the '.codebayrc.py' file in home directory to add to or override the
configuration values defined here.
"""
__docformat__ = 'epytext en'

conf.logging_config = 'default'
conf.logging_syslog = True
conf.logging_stdout = False
conf.logging_stderr = False
conf.logging_debug = False
