"""
System logger daemon.
"""

import os, sys, stat, re, socket, select, syslog, datetime, traceback

from codebay.l2tpserver import constants

socket_path = constants.SYSLOG_DEVICE_FILE
logfile_path = constants.SYSLOG_LOGFILE
backup_path = constants.SYSLOG_LOGFILE_BACKUP
max_file_size = constants.SYSLOG_LOGFILE_MAX_SIZE
max_msg_size = constants.SYSLOG_MSG_MAX_SIZE
poll_timeout = constants.SYSLOG_POLL_TIMEOUT
max_flush_timeout = constants.SYSLOG_FLUSH_TIMEOUT

prefix_re = re.compile('<(\d+)>(.*)')

class LoggerError(Exception):
    """System logger exited with error."""

class Logger:
    def __init__(self):
        self.logfile = None
        self.socket = None

    def _rotate_logfile(self):
        if os.path.exists(logfile_path) and os.stat(logfile_path)[stat.ST_SIZE] > max_file_size:
            try:
                if os.path.exists(backup_path):
                    os.unlink(backup_path)
                os.rename(logfile_path, backup_path)
            except:
                raise LoggerError('Logrotate failed')

    def _flush_logfile(self):
        if self.logfile != None:
            self.logfile.flush()

    def _close_logfile(self):
        if self.logfile != None:
            self._flush_logfile()
            try:
                self.logfile.close()
            except:
                pass
            self.logfile = None

    def _open_logfile(self):
        self.logfile = open(logfile_path, 'a')
        if self.logfile is None:
            raise LoggerError('Cannot open logfile')

    def _sanitize_line(self, line):
        line = line.strip()
        if len(line) > 0 and line[-1] == '\x00':
            line = line[:-1]
        t = ''
        # XXX: perfmonster
        for i in xrange(len(line)):
            ch = ord(line[i])
            if (ch < 0x20) or (ch > 0x7e):
                t = t + '<%x%x>' % (ch / 16, ch % 16)
            else:
                t = t + line[i]
        return t

    def _write_logfile(self, line):
        if self.logfile != None:
            line = self._sanitize_line(line)
            try:
                self.logfile.write(line + '\n')
            except:
                # Try again one time..
                self._close_logfile()
                self._rotate_logfile()
                self._open_logfile()
                self.logfile.write(line + '\n')

    def _close_socket(self):
        if self.socket != None:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

        if os.path.exists(socket_path):
            os.unlink(socket_path)

    def _open_socket(self):
        if os.path.exists(socket_path):
            os.unlink(socket_path)

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM, 0)
        if self.socket is None:
            raise LoggerError('Failed to get socket')

        self.socket.bind(socket_path)
        os.chmod(socket_path, 0666)

    def flush(self):
        self._flush_logfile()

    def cleanup(self):
        self._close_logfile()
        self._close_socket()

    def start(self, errormsg=None):
        self.cleanup()

        self._rotate_logfile()
        self._open_logfile()

        self._open_socket()

        p = select.poll()
        p.register(self.socket, select.POLLIN)

        d = datetime.datetime.utcnow()
        d = d.replace(microsecond=0, tzinfo=None)
        self._write_logfile('%s : *** syslog starting ***' % str(d))

        if errormsg is not None:
            self._write_logfile('%s : *** delayed syslog error follows ***' % str(d))
            self._write_logfile('%s : *** %s ***' % (str(d), errormsg))

        rotate_count = 0
        flush_timestamp = datetime.datetime.utcnow()
        while True:
            time_now = datetime.datetime.utcnow()
            if time_now - flush_timestamp > max_flush_timeout:
                flush_timestamp = time_now
                self._flush_logfile()

            ret = p.poll(poll_timeout)
            if len(ret) == 0:
                continue

            msg = self.socket.recv(max_msg_size)
            m = prefix_re.match(msg)
            if m is None:
                continue
            try:
                prefix = int(m.groups()[0])
                line = str(m.groups()[1])
            except:
                continue

            facility = 8 * (prefix / 8) # syslog.LOG_* (facility)
            level = prefix % 8          # syslog.LOG_* (priority)

            if rotate_count > 100:
                rotate_count = 0
                self._close_logfile() # This also flushes the file
                self._rotate_logfile()
                self._open_logfile()
                flush_timestamp = datetime.datetime.utcnow()
            else:
                rotate_count += 1

            self._write_logfile(line)

            # Flush on serious messages always
            if level <= syslog.LOG_WARNING:
                self._flush_logfile()
                flush_timestamp = datetime.datetime.utcnow()
