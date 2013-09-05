import os

from codebay.common import logger

_log = logger.get('common.helpers')

def write_file(dest, contents, append=False, perms=0755):
    """Write contents (a string) into a destination file, optionally appending and settings permissions.

    By default permissions will be set to 0755.  To skip setting permissions altogether
    (e.g. for /proc files), set perms=None.
    """

    try:
        perms_str = 'none'
        if perms is not None:
            perms_str = '%o' % int(perms)
        _log.debug('write_file(dest=%s, perms=%s, append=%s), contents:\n--------\n%s--------\n' % (dest, perms_str, append, contents))

        mode = 'w'
        if append:
            mode = 'a'

        f = file(dest, mode)
        f.write(contents)
        f.close()

        if perms is not None:
            os.chmod(dest, perms)
    except:
        _log.exception('write_file failed')
        raise

# XXX: is this used anymore?
def filter_file_lines(srcname, dstname, cb):
    """Read lines from source file, processing each line through the callback, and write lines to destination file.

    Suitable only for small files.
    """
    
    fi = open(srcname, 'rb')
    fo = open(dstname, 'wb')

    res = []
    for l in fi.read().split('\n'):
        res.append(cb(l))

    fo.write('\n'.join(res))

    fi.close()
    fo.close()
