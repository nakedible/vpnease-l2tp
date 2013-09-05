#!/usr/bin/env python2.4

from distutils import core

core.setup(name='formal',
           version='0.9.3',
           description='HTML forms framework for Nevow',
           long_description='''HTML forms framework for Nevow''',
           author='Matt Goodall',
           author_email='matt@pollenation.net',
           packages=['formal', 'formal/examples', 'formal/test', 'formal/widgets'],
           data_files=[('', ['formal/formal.css',
                             'formal/examples/examples.css',
                             'formal/js/formal.js',
                             'formal/html/SelectOtherChoice.html'])]
           )

