"""
Update system time.

Write timestamp when this update was done.
"""

import datetime

try:
    from codebay.common import logger
    _log = logger.get('l2tpserver.timesync')
except:
    _log = None

def _write_update_timestamps():
    try:
        from codebay.common import datatypes
        from codebay.l2tpserver import helpers
        from codebay.l2tpserver import constants

        helpers.write_file(constants.TIMESYNC_TIMESTAMP_FILE, datatypes.encode_datetime_to_iso8601_subset(datetime.datetime.utcnow()))
        helpers.write_file(constants.TIMESYNC_PERSISTENT_TIMESTAMP_FILE, datatypes.encode_datetime_to_iso8601_subset(datetime.datetime.utcnow()))
    except:
        if _log is not None:
            _log.exception('writing system time update timestamp failed.')
 
def update_system_time(utc_dt, cap_backwards=None, cap_forwards=None):
    """Update system time to specified UTC timestamp.

    The system time 'jump' is capped by optional parameters.  The function returns True
    if system time has been updated without capping (and without any other errors), and
    False if time jump is capped or an error occurs.  Timesync timestamp files are written
    if no capping or other errors occur.
    """
    if _log is not None:
        _log.debug('update_system_time(): %s' % utc_dt)
    
    capped = False
    try:
        from codebay.l2tpserver import constants
        from codebay.l2tpserver import runcommand
        run_command = runcommand.run_command

        now = datetime.datetime.utcnow()
        time_diff = utc_dt - now
        zero_diff = datetime.timedelta(0, 0, 0)
        
        if time_diff >= zero_diff:
            if cap_forwards is not None:
                if time_diff > cap_forwards:
                    _log.info('update_system_time: time jump forwards exceeds cap (%s > %s), limiting to cap' % (time_diff, cap_forwards))
                    time_diff = cap_forwards
                    capped = True
        else:
            if cap_backwards is not None:
                if (-time_diff) > cap_backwards:
                    _log.info('update_system_time: time jump backwards exceeds cap (%s > %s), limiting to cap' % (-time_diff, cap_backwards))
                    time_diff = -cap_backwards
                    capped = True

        target_time = now + time_diff
        
        date_str = str(target_time)
        run_command([constants.CMD_DATE, '-u', '--set=%s' % date_str], retval=runcommand.FAIL)
        run_command([constants.CMD_HWCLOCK, '--utc', '--systohc'], retval=runcommand.FAIL)
    except:
        if _log is not None:
            _log.exception('updating system time failed')
        return False

    if capped:
        return False
    else:
        _write_update_timestamps()
        return True
