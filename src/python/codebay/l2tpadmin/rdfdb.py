"""RDF database for product web.

This file provides definitions and accessor functions for the initial
product web database, which uses the same sqlite-backed RDF database as
the product itself.  This is simply to save time in creating a reliable
database with proper transactions etc quickly.

RDF database objects
====================

Basic web-related objects are:

  * Account provides company and contact information (c.f. registration
    form).  It also provides username and password for login, i.e.,
    acts also as a user account.  In the future we might want to have a
    separate company account and 1-N user accounts for the company.

  * License tracks individual license keys which have been purchased by
    someone.  A license is related to at most one account.

These two objects are basically only tracking what the user sees and
what license information is delivered to the management server.  They
also track the minimal information required for billing: PayPal
recurring payment profile ID and confirmed sum.
"""
__docformat__ = 'epytext en'

import os
import datetime
import sha

from codebay.common import rdf
from codebay.common import rdftransact
from codebay.l2tpadmin import constants
from codebay.l2tpadmin.rdfdefs import ns_l2tp_product_web as ns

transact = rdftransact.transact
untransact = rdftransact.untransact
sqlite_file = constants.SQLITE_DATABASE_FILE

_product_db = None

def get_db():
    """Get file-backed model from disk, (re)opening if necessary."""

    global _product_db
    
    if _product_db is not None:
        return _product_db

    if not os.path.exists(sqlite_file):
        raise Exception('database file %s does not exist' % sqlite_file)

    _product_db = rdf.Database.open(sqlite_file)
    if _product_db is None:
        raise Exception('database file %s opened, result None' % sqlite_file)

    return _product_db

def close_db():
    """Close database file if open."""

    global _product_db
    
    if _product_db is None:
        return

    _product_db.close()
    _product_db = None

def get_root(db):
    return db.getNodeByUri(ns.l2tpProductWebGlobalRoot, rdf.Type(ns.L2tpProductWebGlobalRoot))

def create_initial_database():
    """Nuke and re-create the initial database.

    This is naturally a dangerous operation which should always be executed
    with great care.
    """

    if os.path.exists(sqlite_file):
        os.unlink(sqlite_file)

    db = rdf.Database.create(sqlite_file)
    db.close()
    db = None

    try:
        now = datetime.datetime.utcnow()
        
        db = get_db()
        root = rdf.Node.make(db, rdf.Type(ns.L2tpProductWebGlobalRoot), ns.l2tpProductWebGlobalRoot)
        root.setS(ns.creationTime, rdf.Datetime, now)

        accounts_root = root.setS(ns.accounts, rdf.Type(ns.Accounts))
        licenses_root = root.setS(ns.licenses, rdf.Type(ns.Licenses))

    finally:
        close_db()

def new_account(db):
    node = rdf.Node.make(db, rdf.Resource)  # random UUID
    node.addType(ns.Account)
    return node

def new_license(db):
    node = rdf.Node.make(db, rdf.Resource)  # random UUID
    node.addType(ns.License)
    return node

def compute_password_hash(salt, password):
    t = salt.encode('utf-8') + ':' + password.encode('utf-8')
    return sha.sha(t).digest().encode('hex')

def get_accounts_sorted(db):
    """Get accounts in an order sorted by username."""
    root = get_root(db)
    t = {}
    for i in root.getS(ns.accounts, rdf.Type(ns.Accounts)).getSet(ns.account, rdf.Type(ns.Account)):
        t[i.getS(ns.username, rdf.String)] = i
    k = t.keys()
    k.sort()

    res = []
    for key in k:
        res.append(t[key])
    return res
    
def get_account(db, username):
    t = get_accounts_sorted(db)
    for i in t:
        if i.getS(ns.username, rdf.String) == username:
            return i
    return None

def get_licenses_sorted(db, account):
    """Get licenses sorted by license key for a specific account."""
    if account is None:
        raise Exception('account is None')
    
    root = get_root(db)
    t = {}

    acct_uri = account.getUri()  # string
    for i in root.getS(ns.licenses, rdf.Type(ns.Licenses)).getSet(ns.license, rdf.Type(ns.License)):
        # XXX: not the best comparison
        if i.getS(ns.account).getUri() == acct_uri:
            t[i.getS(ns.licenseKey, rdf.String)] = i
    k = t.keys()
    k.sort()

    res = []
    for key in k:
        res.append(t[key])
    return res

def add_test_data():
    """Add dummy test data to the database.

    This is just to speed up testing.  Should never be used in the production
    system.
    """
    
    try:
        now = datetime.datetime.utcnow()
        
        db = get_db()
        root = get_root(db)
        accounts = root.getS(ns.accounts, rdf.Type(ns.Accounts))
        acct_set = accounts.getSet(ns.account, rdf.Type(ns.Account))
        licenses = root.getS(ns.licenses, rdf.Type(ns.Licenses))
        lic_set = licenses.getSet(ns.license, rdf.Type(ns.License))
    
        acct1 = new_account(db)
        acct1.setS(ns.username, rdf.String, 'test1')
        acct1.setS(ns.passwordSalt, rdf.String, 'salty')
        acct1.setS(ns.passwordSha1, rdf.String, compute_password_hash('salty', 'test'))
        acct_set.add(acct1)

        acct2 = new_account(db)
        acct2.setS(ns.username, rdf.String, 'test2')
        acct2.setS(ns.passwordSalt, rdf.String, 'saltz')
        acct2.setS(ns.passwordSha1, rdf.String, compute_password_hash('saltz', 'test'))
        acct_set.add(acct2)

        lic1 = new_license(db)
        lic1.setS(ns.licenseKey, rdf.String, 'RRHEX-RRHEX-RRHEX-RRHEX-RRHEX')
        lic1.setS(ns.licenseString, rdf.String, u'J\u00e4nk\u00e4-Jooses')
        lic1.setS(ns.licenseUserCount, rdf.Integer, 500)
        lic1.setS(ns.licenseSiteToSiteCount, rdf.Integer, 8)
        lic1.setS(ns.licenseEnabled, rdf.Boolean, True)
        lic1.setS(ns.account, rdf.Type(ns.Account), acct1)
        lic_set.add(lic1)

        lic2 = new_license(db)
        lic2.setS(ns.licenseKey, rdf.String, 'RRHEX-RRHEX-RRHEX-RRHEX-RRHEZ')
        lic2.setS(ns.licenseString, rdf.String, u'J\u00e4nk\u00e4-Jooses')
        lic2.setS(ns.licenseUserCount, rdf.Integer, 16)
        lic2.setS(ns.licenseSiteToSiteCount, rdf.Integer, 2)
        lic2.setS(ns.licenseEnabled, rdf.Boolean, False)
        lic2.setS(ns.account, rdf.Type(ns.Account), acct1)
        lic_set.add(lic2)
        
        lic3 = new_license(db)
        lic3.setS(ns.licenseKey, rdf.String, 'RRHEX-RRHEX-RRHEX-RRHEX-RRHEZ')
        lic3.setS(ns.licenseString, rdf.String, u'J\u00e4nk\u00e4-Jooses')
        lic3.setS(ns.licenseUserCount, rdf.Integer, 200)
        lic3.setS(ns.licenseSiteToSiteCount, rdf.Integer, 8)
        lic3.setS(ns.account, rdf.Type(ns.Account), acct2)
        lic_set.add(lic3)
        
    finally:
        close_db()
        
def dump_to_rdfxml():
    db = get_db()
    return db.toString()
