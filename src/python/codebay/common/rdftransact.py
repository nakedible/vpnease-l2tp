"""Transaction decorators for RDF API.

This functionality has been lifted from the VPNease decorator
(codebay.l2tpserver.db) implementation and very slightly cleaned
up.  Hopefully we can generalize this later and make VPNease use
a general version too.
"""

import datetime
import traceback
from twisted.python.util import mergeFunctionMetadata
from codebay.common import logger

_log = logger.get('codebay.rdftransact')

# XXX: globals now
TRANSACT_LOCK_TIME_WARNING_LIMIT = datetime.timedelta(seconds=2)
UNTRANSACT_LOCK_TIME_WARNING_LIMIT = datetime.timedelta(seconds=15*60)  # XXX: irrelevant

# XXX: better would be to know the transaction decorator which
# eventually caused the lock to be taken.
toplevel_transaction = None

def _get_func_info(f):
    # NB: Function attributes are not always available, so check for each one separately.
    # In particular, when a decorator gets an (at least an inner) function, it does not
    # have __file__ and __line__.

    fname = '<unknown>'
    ffile = '<unknown>'
    fline = '<unknown>'
    if f is None:
        fname, ffile, fline
    
    if hasattr(f, '__name__'):
        fname = f.__name__
    elif hasattr(f, 'func_name'):
        fname = f.func_name

    if hasattr(f, '__file__'):
        ffile = f.__file__
    elif hasattr(f, 'func_code') and hasattr(f.func_code, 'co_filename'):
        ffile = f.func_code.co_filename

    if hasattr(f, '__line__'):
        fline = str(f.__line__)
    elif hasattr(f, 'func_code') and hasattr(f.func_code, 'co_firstlineno'):
        fline = str(f.func_code.co_firstlineno)

    return fname, ffile, fline

def _transact_begin_log_helper(deco_name, f, dbase):
    try:
        fname, ffile, fline = _get_func_info(f)

        if dbase is None:
            active = 'n/a'
            deco_name = deco_name + ' (*no database*)'
        elif hasattr(dbase, 'store') and (dbase.store is not None) and dbase.is_transaction_active():
            # hasattr + store check is to fix #621, this is also an API issue with rdf.py
            active = 'yes'
        else:
            active = 'no'
        
        _log.debug('%s begin (%s, %s:%s), active before: %s' % (deco_name, fname, ffile, fline, active))
    except:
        _log.exception('_transact_begin_log_helper: failed to log')
        
def _transact_end_log_helper(deco_name, f, dbase, success, starttime, endtime, locked_time, lock_time_limit, untransact_point=None):
    try:
        fname, ffile, fline = _get_func_info(f)

        if dbase is None:
            active = 'n/a'
            deco_name = deco_name + ' (*no database*)'
        elif hasattr(dbase, 'store') and (dbase.store is not None) and dbase.is_transaction_active():
            # hasattr + store check is to fix #621, this is also an API issue with rdf.py
            active = 'yes'
        else:
            active = 'no'

        untransact_log = ''
        if untransact_point is not None:
            untransact_log = ', untransact at (%s, %s:%s)' % _get_func_info(untransact_point)
        
        # Here we show a warning if the actual locked time exceeds a set limit.

        totaltime = endtime - starttime
        if (locked_time is not None and locked_time > lock_time_limit):
            if success:
                _log.warning('%s ended with success but took long (decorator time %s, locked time %s) (%s, %s:%s), active after: %s%s\n%s' % (deco_name, totaltime, locked_time, fname, ffile, fline, active, untransact_log, ''.join(traceback.format_stack())))
            else:
                _log.warning('%s ended with failure and took long (decorator time %s, locked time %s) (%s, %s:%s), active after: %s%s\n%s' % (deco_name, totaltime, locked_time, fname, ffile, fline, active, untransact_log, ''.join(traceback.format_stack())))
        else:
            # XXX: stack tracebacks are formatted even when debug log is not ultimately logged
            if success:
                _log.debug('%s ended with success (decorator time %s, locked time %s) (%s, %s:%s), active after: %s%s' % (deco_name, totaltime, locked_time, fname, ffile, fline, active, untransact_log))
            else:
                _log.debug('%s ended with failure (decorator time %s, locked time %s) (%s, %s:%s), active after: %s%s\n%s' % (deco_name, totaltime, locked_time, fname, ffile, fline, active, untransact_log, ''.join(traceback.format_stack())))
    except:
        _log.exception('_transact_end_log_helper: failed to log')
        
def transact(database=None):
    """Transaction decorator for functions."""
    def _f(f):
        def g(*args, **kw):
            starttime = datetime.datetime.utcnow()

            dbase = database
            if dbase is None:
                raise Exception('dbase is None')
            
            _transact_begin_log_helper('@transact', f, dbase)
            if (dbase is not None) and hasattr(dbase, 'store') and (dbase.store is not None):
                # hasattr + store check is to fix #621, this is also an API issue with rdf.py
                t = dbase.begin_transaction()
            else:
                t = None

            global toplevel_transaction

            if toplevel_transaction is None:
                toplevel_transaction = f

            try:
                ret = f(*args, **kw)
            except:
                if toplevel_transaction == f:
                    toplevel_transaction = None

                t_locked_time = None
                if t is not None:
                    t_locked_time = t.get_locked_time()
                    t.commit()
                endtime = datetime.datetime.utcnow()
                _transact_end_log_helper('@transact', f, dbase, False, starttime, endtime, t_locked_time, TRANSACT_LOCK_TIME_WARNING_LIMIT)
                raise

            if toplevel_transaction == f:
                toplevel_transaction = None

            t_locked_time = None
            if t is not None:
                t_locked_time = t.get_locked_time()
                t.commit()
            endtime = datetime.datetime.utcnow()
            _transact_end_log_helper('@transact', f, dbase, True, starttime, endtime, t_locked_time, TRANSACT_LOCK_TIME_WARNING_LIMIT)
                
            return ret
        
        mergeFunctionMetadata(f, g)
        return g
    return _f

def untransact(database=None):
    """Un-transaction decorator for functions.

    Commits current transaction and executes the body of the function without
    a transaction.  This is useful for functions executed inside a @transact
    decorator, which block for too long to keep the exclusive @transact lock.
    Once the function is complete, the transaction is started again and execution
    continues normally.
    """

    def _f(f):
        def g(*args, **kw):
            starttime = datetime.datetime.utcnow()

            dbase = database
            if dbase is None:
                raise Exception('dbase is None')
                
            _transact_begin_log_helper('@untransact', f, dbase)
            if (dbase is not None) and hasattr(dbase, 'store') and (dbase.store is not None):
                # hasattr + store check is to fix #621, this is also an API issue with rdf.py
                t = dbase.begin_untransaction()
            else:
                t = None

            global toplevel_transaction

            # Log transact locktime here if active
            if t is not None:
                # XXX: There is no sensible date value to show here,
                # because we are not actually logging anything for
                # current untransaction: we log the locktime of the
                # toplevel transaction which is committed here. Using
                # current time as both timestamps for now.
                _transact_end_log_helper('@transact (in untransact)', toplevel_transaction, dbase, True, datetime.datetime.utcnow(), datetime.datetime.utcnow(), t.get_txn_locked_time(), TRANSACT_LOCK_TIME_WARNING_LIMIT, untransact_point=f)

            try:
                ret = f(*args, **kw)
            except:
                t_locked_time = None
                if t is not None:
                    t_locked_time = t.get_locked_time()
                    t.commit()
                endtime = datetime.datetime.utcnow()
                _transact_end_log_helper('@untransact', f, dbase, False, starttime, endtime, t_locked_time, UNTRANSACT_LOCK_TIME_WARNING_LIMIT)
                raise

            t_locked_time = None
            if t is not None:
                t_locked_time = t.get_locked_time()
                t.commit()
            endtime = datetime.datetime.utcnow()
            _transact_end_log_helper('@untransact', f, dbase, True, starttime, endtime, t_locked_time, UNTRANSACT_LOCK_TIME_WARNING_LIMIT)
                
            return ret

        mergeFunctionMetadata(f, g)
        return g
    return _f

