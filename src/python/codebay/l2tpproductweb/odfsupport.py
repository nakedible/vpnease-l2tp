"""Brute force Open Document Format support.

Allows unzipping ODF files, making modifications, and rezipping.
"""

import os
import tempfile
# http://docs.python.org/lib/module-xml.dom.html
from xml.dom import minidom
from codebay.common import runcommand

run_command = runcommand.run

class OdfEditor:
    """Opens an ODF file into memory for editing and allows writing back to a different file.

    Does not modify the source file."""

    def __init__(self, filename):
        self.loadOdfFile(filename)

    def loadOdfFile(self, filename):
        self.tempdir = tempfile.mkdtemp(suffix='-odf')
        run_command(['unzip', filename], cwd=self.tempdir, retval=runcommand.FAIL)

    def saveOdfFile(self, filename):
        run_command(['zip', '-r', filename, '.'], cwd=self.tempdir, retval=runcommand.FAIL)

    def getContentDom(self):
        return minidom.parse(os.path.join(self.tempdir, 'content.xml'))

    def saveContentDom(self, doc):
        f = None
        f = open(os.path.join(self.tempdir, 'content.xml'), 'wb')
        try:
            f.write(doc.toxml(encoding='utf-8'))
        finally:
            if f is not None:
                f.close()
                f = None
