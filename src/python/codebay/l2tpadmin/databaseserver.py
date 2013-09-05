"""Database server utils."""
__docformat__ = 'epytext en'

import os, sys, time

from codebay.l2tpadmin import dbaccess
from codebay.l2tpadmin import runcommand
from codebay.l2tpadmin.constants import *
run_command = runcommand.run_command

#
#  FIXME: this is torso code after some reorganization
#

def create(args):
    dh = dbaccess.DatabaseHelpers()
    dh.create_database()

def delete(args):
    dh = dbaccess.DatabaseHelpers()
    dh.delete_database()

def list_licensekeys(args):
    da = dbaccess.DatabaseAccessor()
    for l in da.get_license_keys():
        print l.to_string()
    
def list_licenses(args):
    da = dbaccess.DatabaseAccessor()
    for l in da.get_licenses():
        print l.to_string()

def test_import_legacy_licenses(args):
    dh = dbaccess.DatabaseHelpers()
    dh.populate_licenses_from_legacy_info()

def test_license_fetch_loop(args):
    da = dbaccess.DatabaseAccessor()
    while True:
        try:
            res = da.get_licenses()
            print 'license fetch OK'
        except:
            print 'license fetch failed'

        time.sleep(5.0)
        
