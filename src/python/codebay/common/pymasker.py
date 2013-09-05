"""Light obfuscation of a Python source file.

Replaces content of docstrings and comments with white space.  Does not
alter function or variable names.

A few limitations:

  * Unfortunately currently removes blank lines.

  * Does not work with vanilla astng, because it seems to contain bugs
    in handling of argument lists and except-clauses at least; l2tp-dev
    contains patches to fix astng for our purposes.

NOTE!!!
*** This module does not currently work because ASTNG has a number of bugs! ***
NOTE!!!

See /usr/lib/python2.4/site-packages/pylint/lint.py for nice astng examples.
"""

import os
import tempfile
import py_compile
from logilab import astng

class Obfuscator:
    """Light obfuscation of a Python source file."""

    def __init__(self):
        pass

    def obfuscate(self, infile, outfile):
        # parse to astng
        mgr = astng.ASTNGManager()
        modname = None  # XXX!
        ast = mgr.astng_from_file(infile, modname)

        # process
        self._recursive_process(ast)

        # write out
        f = open(outfile, 'wb')
        f.write(ast.as_string())
        f.close()

    def compile_pyc(self, infile, outfile):
        rc = py_compile.compile(infile, cfile=outfile, dfile=infile, doraise=True)

    def obfuscate_and_compile(self, infile, outfile):
        t = tempfile.mktemp(suffix='-obf')
        try:
            self.obfuscate(infile, t)
            self.compile_pyc(t, outfile)
        finally:
            if os.path.exists(t):
                os.unlink(t)
            
    def _obfuscate_docstring_preserve_length(self, old_doc):
        new_doc = ''
        for i in xrange(len(old_doc)):
            ch = old_doc[i]
            if ch in ['\n', ' ', '\t']:
                new_doc += ch
            else:
                new_doc += ' '
        return new_doc

    def _obfuscate_docstring(self, old_doc):
        return '.'

    def _recursive_process(self, x):
        # x may be a wide variety of things: None, int, string, astng objects, etc.

        # XXX: this is rather bruteforce checking but seems to work OK

        if hasattr(x, 'doc'):
            if hasattr(x, 'doc') and isinstance(x.doc, (str, unicode)):
                x.doc = self._obfuscate_docstring_preserve_length(x.doc)
                #x.doc = self._obfuscate_docstring(x.doc)
            
        if hasattr(x, 'getChildren'):
            for c in x.getChildren():
                self._recursive_process(c)


if __name__ == '__main__':
    import sys
    infile = sys.argv[1]
    outfile = sys.argv[2]

    obf = Obfuscator()
    obf.obfuscate(infile, outfile)
    obf.obfuscate_and_compile(infile, outfile + 'c')
