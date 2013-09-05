"""ZIP file handling helpers for product specific zipfile format (see architecture docs).

Typical usage to create a zipfile:

    from codebay.l2tpserver import zipfiles

    z = zipfiles.ProductZipfile(rdfconfig.ns_zipfiles.myZipType)
    z.add_file('mydata.xml', xml_contents)
    z.add_file('bindata.bin', binary_contents)
    z.write_zipfile('/tmp/myfile.zip')

Typical usage to read a zipfile:

    from codebay.l2tpserver import zipfiles

    z = zipfiles.ProductZipfile.read_zipfile('/tmp/myfile.zip', filetype=rdfconfig.ns_zipfiles.myZipType)
    xml_contents = z.get_file('mydata.xml')
    # and so on

"""
__docformat__ = 'epytext en'

import zipfile

from codebay.common import tinyrdf
from codebay.common import logger
from codebay.l2tpserver import helpers
from codebay.l2tpserver import constants

_log = logger.get('l2tpserver.zipfiles')

# ----------------------------------------------------------------------------

class Error(Exception):
    pass

# ----------------------------------------------------------------------------

def _stringify_filetype(filetype):
    if isinstance(filetype, str):
        return filetype
    elif isinstance(filetype, unicode):
        return str(filetype)
    elif isinstance(filetype, tinyrdf.Uri):
        return str(filetype.uri)
    else:
        raise Exception('Unknown filetype: %s' % filetype)
    
class ProductZipfile:
    def __init__(self, filetype=None):
        self.magic = str(constants.PRODUCT_ZIPFILE_MAGIC)
        self.version = str(constants.PRODUCT_ZIPFILE_VERSION)
        self.filetype = _stringify_filetype(filetype)
        self.product = helpers.get_product_identifier_string()
        self.files = []

    def read_zipfile(klass, infile, filetype=None):
        # XXX: initialization of instance variables is not very clean here; we
        # first fill in dummy values which are then cleared.
        t = klass("dummy")

        filetype = _stringify_filetype(filetype)

        t.magic = None
        t.version = None
        t.filetype = None
        t.product = None
        t.files = []

        zf = None
        try:
            try:
                zf = zipfile.ZipFile(infile, mode='r')

                for f in zf.namelist():
                    if f == 'magic':
                        t.magic = zf.read('magic').strip()
                    elif f == 'version':
                        t.version = zf.read('version').strip()
                    elif f == 'type':
                        t.filetype = _stringify_filetype(zf.read('type').strip())
                    elif f == 'product':
                        t.product = zf.read('product').strip()
                    else:
                        t.files.append([f, zf.read(f)])
            
                if t.magic != constants.PRODUCT_ZIPFILE_MAGIC:
                    raise Exception('unknown magic')
                if filetype is not None:
                    if t.filetype != str(filetype):
                        raise Exception('unexpected file type (expected %s, got %s)' % (filetype, t.filetype))
            except:
                _log.exception('reading zipfile failed')
                raise
        finally:
            if zf is not None:
                zf.close()
                zf = None
            
        return t
    read_zipfile = classmethod(read_zipfile)
    
    def add_file(self, name, contents):
        self.files.append([name, contents])

    def get_file(self, name):
        for fname, fcontents in self.files:
            if fname == name:
                return fcontents
            
    def write_zipfile(self, outfile):
        zf = None
        try:
            try:
                zf = zipfile.ZipFile(outfile, mode='w')

                zf.writestr('magic', '%s\n' % self.magic)
                zf.writestr('version', '%s\n' % self.version)
                zf.writestr('type', '%s\n' % self.filetype)
                zf.writestr('product', '%s\n' % self.product)

                for name, contents in self.files:
                    zf.writestr(name, contents)
            except:
                _log.exception('creating zipfile failed')
                raise
        finally:
            if zf is not None:
                zf.close()
                zf = None
