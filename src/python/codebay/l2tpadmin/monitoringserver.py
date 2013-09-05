"""
Monitors a set of servers using ping and predefined urls by retrieving them.
Mails results to predefined address(es).
"""

# Monitoring server constants.

SERVERNAME='VPNease monitor'
RESULT_MAIL_ADDRESSES=['devel@intra.codebay.fi'] # FIXME
FROM_ADDRESS='root@vpnease-monitor.intra.codebay.fi'
SMTP_SERVER='172.20.0.1'

DNS_TO_CHECK=[
    {'name':'ns1.vpnease.com', 'ips':['212.68.6.249']},
    {'name':'ns2.vpnease.com', 'ips':['212.68.6.250']},
    {'name':'mail.vpnease.com', 'ips':['212.68.6.227']},
    {'name':'www.vpnease.com', 'ips':['212.68.6.249', '212.68.6.250']},
    {'name':'downloads.vpnease.com', 'ips':['212.68.6.249', '212.68.6.250']},
    {'name':'bittorrent.vpnease.com', 'ips':['212.68.6.249', '212.68.6.250']},
    {'name':'packages.vpnease.com', 'ips':['212.68.6.251']},
    {'name':'management.vpnease.com', 'ips':['212.68.6.253']},
    {'name':'test.vpnease.com', 'ips':['212.68.6.248']},
    {'name':'www.codebay.fi', 'ips':['212.68.6.228', '212.68.6.229']}]


SERVERS_TO_PING=[]
for i in DNS_TO_CHECK:
    SERVERS_TO_PING.append(i['name'])

# Ping vmware hosts without DNS names
SERVERS_TO_PING+=[
    '172.20.11.2', # Wumpus
    '172.20.11.3', # Vuokaavio
    '172.21.11.1', # Server1
    '172.21.11.2'  # Server2
    ]

WEBSERVERS_TO_CHECK=[
    'www.vpnease.com', # FIXME: add url(s) when product web is online
    'test.vpnease.com', # FIXME: check login and some instruction pages?
    'www.codebay.fi/services.html',
    'www.codebay.fi/contact.html']

MANAGEMENT_SERVERS=[
    'management.vpnease.com'
    ]

MAIL_SUBJECT_SUCCESS='%s: all tests ok' % SERVERNAME
MAIL_SUBJECT_FAILURE='%s: some test(s) failed' % SERVERNAME

CMD_MAILX='/usr/bin/mailx'
CMD_PING='/bin/ping'
CMD_WGET='/usr/bin/wget'
CMD_HOST='/usr/bin/host'

import traceback, re, textwrap, os

from codebay.l2tpadmin import runcommand
run_command = runcommand.run_command

from codebay.common import logger
_log = logger.get('monitoringserver')

def _duallog(msg, logf):
    print msg
    if logf == _log.exception:
        traceback.print_exc()

    logf(msg)


class DnsMonitor:
    """Monitors DNS name resolving to address(es)."""

    def check_name(self, name, addresses):
        [rv, out, err] = run_command([CMD_HOST, '-t', 'A', name])
        if rv != 0:
            return rv, out, err

        if out is None or out == '':
            return 100, 'no output', ''

        # XXX: this works only for host -command from bind9-host package
        expr = '^%s has address (.*)$' % name

        address_re = re.compile(expr)
        found_addresses = []
        for l in out.split('\n'):
            m = address_re.match(l)
            if m is not None:
                found_addresses.append(m.groups()[0].strip())

        if len(addresses) != len(found_addresses):
            return 101, '%s: number of addresses mismatch: expected %s, but resolved %s' % (name, len(addresses), len(found_addresses)), ''

        addresses.sort()
        found_addresses.sort()

        for i in xrange(len(addresses)):
            if addresses[i] != found_addresses[i]:
                return 102, '%s: address mismatch: expected %s, but resolved %s' % (name, addresses[i], found_addresses[i]), ''

        return 0, '', ''

class PingMonitor:
    """Monitors servers by checking reply to ping."""

    def check_address(self, address):
        # FIXME: assume that return value is always set.
        [rv, out, err] = run_command([CMD_PING, '-i', '1.0', '-c', '1', '-w', '5', address])
        return rv, out, err

class WebMonitor:
    """Monitors webserver by trying to get predefined pages from server."""

    def check_url(self, url):
        # FIXME: recheck timeout sanity: this may still take long (maximum 3*30*10*10=9000 => 2.5 hours!)
        # FIXME: default timeouts are totally unacceptable: readtimeout is 900 seconds and no other timeouts are set by default.
        # FIXME: assume that wget returns non-zero for all errors (seems like this is true) and no output parsing is required.
        [rv, out, err] = run_command([CMD_WGET, '--no-check-certificate', '--dns-timeout=10', '--connect-timeout=10', '--read-timeout=30', '--tries=3', '--output-document=/dev/null', url])
        return rv, out, err

class MonitorMail:
    """Sends monitoring results via mail message."""

    def send_mail(self, fromaddr, toaddrs, subject, contents, attachments=[]):
        import smtplib
        import mimetypes

        from email import Encoders
        from email.Message import Message
        from email.MIMEBase import MIMEBase
        from email.MIMEMultipart import MIMEMultipart
        from email.MIMEText import MIMEText

        # FIXME: assume that return value is set on all errors..

        # FIXME: raise exceptions on send errors

        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = fromaddr
        msg['To'] = ', '.join(toaddrs)

        msg.preamble = contents
        msg.epilogue = ''

        att = MIMEText(contents, 'plain')
        msg.attach(att)

        for subtype, filename in attachments:
            f = open(filename, 'rb')
            att = MIMEBase('application', subtype)
            att.set_payload(f.read())
            Encoders.encode_base64(att)
            att.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filename))
            f.close()
            msg.attach(att)

        s = smtplib.SMTP(SMTP_SERVER)
        s.sendmail(fromaddr, toaddrs, msg.as_string())

class MonitoringServer:
    def __init__(self):
        self.mailer = MonitorMail()
        self.dnsmonitor = DnsMonitor()
        self.pingmonitor = PingMonitor()
        self.webmonitor = WebMonitor()

    def check(self, args):

        silent = False
        if args is not None and len(args) > 0:
            if args[0] == 'silent':
                silent = True

        results = ''
        errors = False

        _duallog('running server monitor in one-shot mode (silent: %s)' % silent, _log.info)

        try:
            results += 'Results for DNS checks\n'
            results += '----------------------\n'

            for entry in DNS_TO_CHECK:
                name, addresses = entry['name'], entry['ips']
                rv, out, err = self.dnsmonitor.check_name(name, addresses)
                results += '\nDNS check of name %s, addresses %s: ' % (name, addresses)
                if rv != 0:
                    results += 'Failed!'
                    results += '\n    rv: %s\n  out: %s\n  err: %s' % (str(rv), out, err)
                    _duallog('dnsmonitor check of name %s, addresses %s failed!\n  rv: %s\n  out: %s\n  err: %s\n' % (name, addresses, str(rv), out, err), _log.warning)
                    errors = True
                else:
                    results += 'OK'

            results += '\n\n'

            results += 'Results for ping checks\n'
            results += '-----------------------\n'

            for address in SERVERS_TO_PING:
                rv, out, err = self.pingmonitor.check_address(address)
                results += '\nPing check of address %s: ' % address
                if rv != 0:
                    results += 'Failed!'
                    results += '\n    rv: %s\n  out: %s\n  err: %s' % (str(rv), out, err)
                    _duallog('pingmonitor check to address %s failed!\n  rv: %s\n  out: %s\n  err: %s\n' % (address, str(rv), out, err), _log.warning)
                    errors = True
                else:
                    results += 'OK'

            results += '\n\n'
            results += 'Results for web-page checks\n'
            results += '---------------------------\n'

            for url in WEBSERVERS_TO_CHECK:
                rv, out, err = self.webmonitor.check_url(url)
                results += '\nWeb check of url %s: ' % url
                if rv != 0:
                    results += 'Failed!'
                    results += '\n    rv: %s\n  out: %s\n  err: %s' % (str(rv), out, err)
                    _duallog('webmonitor check to url %s failed!\n  rv: %s\n  out: %s\n  err: %s\n' % (url, str(rv), out, err), _log.warning)
                    errors = True
                else:
                    results += 'OK'

        except:
            _duallog('some monitoring check failed badly', _log.exception)
            errors = True
            results += '\n\nFailed to run rest of the monitoring checks!'

        attachments = []

        for server in MANAGEMENT_SERVERS:
            try:
                [rv, out, err] = run_command(['/usr/bin/ssh', 'root@%s' % server, '/usr/bin/vpneaseadmin', 'ms', 'stats'], retval=runcommand.FAIL)

                results += textwrap.dedent("""\


                Management server status:
                =========================
                (server IP/DNS: %s)

                %s
            
                """) % (server, out)
            except:
                errors = True
                results += '\n\nFailed to get status from management server (%s)!' % server

            try:
                backup_filename = None
                [rv, out, err] = run_command(['ssh', 'root@%s' % server, '/usr/bin/vpneaseadmin', 'ms', 'backup'], retval=runcommand.FAIL)
                backup_re = re.compile("^Backup file written to: (.+)$")
                for line in out.split('\n'):
                    m = backup_re.match(line)
                    if m is not None:
                        backup_filename = m.groups()[0].strip()
                        break

                if backup_filename is None:
                    print "out: %s" % out
                    print "err: %s" % err
                    raise Exception('no backup file')

                backup_output = os.path.join('/tmp', '%s_%s' % (server, os.path.basename(backup_filename)))
                [rv, out, err] = run_command(['scp', 'root@%s:%s' % (server, backup_filename), backup_output], retval=runcommand.FAIL)

                attachments.append(('gzip', backup_output))

                results += textwrap.dedent("""\
                Server backup in attachment: %s
                """ % os.path.basename(backup_output))
            except:
                errors = True
                results += '\n\nFailed to get backup from management server (%s)!' % server

        if errors:
            subject = MAIL_SUBJECT_FAILURE
        else:
            subject = MAIL_SUBJECT_SUCCESS

        if errors or not silent:
            # Mail results
            for mail_address in RESULT_MAIL_ADDRESSES:
                try:
                    self.mailer.send_mail(FROM_ADDRESS, [mail_address], subject, results, attachments)
                except:
                    _duallog('failed to send monitoring mail to address %s' % mail_address, _log.exception)

if __name__ == '__main__':
    m = MonitoringServer()
    m.check()
