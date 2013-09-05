
import os, time, string, textwrap

from twisted.internet import reactor

from xml.dom import minidom
from codebay.common import logger
from codebay.common import runcommand
from codebay.l2tpdnsserver import monitor

_log = logger.get('l2tpddnsserver.monitor')

# safeguard
def _check_marker():
    return os.path.exists('/etc/vpnease-dns-server')

class _DnsDomain:
    def __init__(self, topname, subname, servers):
        self.topname = topname
        self.subname = subname
        self.servers = servers

class _DnsConfig:
    def __init__(self, top_level_domain, ns1, ns2, mail, domains, status_dict):
        self.named_conf = self._create_named_conf(top_level_domain)
        self.zonefile = self._create_zonefile(top_level_domain, ns1, ns2, mail, domains, status_dict)

    def _create_named_conf(self, top_level_domain):
        return textwrap.dedent("""\
        # automatically generated, do not edit!
        options {
                directory "/var/cache/bind";
                auth-nxdomain no;    # conform to RFC1035
                listen-on-v6 { any; };
        };

        # FIXME: need this? need localhost etc?
        zone "." {
                type hint;
                file "/etc/bind/db.root";
        };

        zone "%(topleveldomain)s" {
                type master;
                file "/etc/bind/db.topleveldomain";
        };
        """ % {'topleveldomain':top_level_domain})

    def _create_zonefile(self, top_level_domain, ns1, ns2, mail, domains, status_dict):
        # NB: Serial is not part of the file at this point, because we don't
        # want it to affect the results of comparison.  It is filled when
        # writing to disk.
        #
        # We use 'seconds since Epoch' instead of RFC-suggested 'YYYYMMDDNN'
        # format because we don't want to store any state files (like current
        # counter for this day, etc).

        # FIXME: this is probably quite buggy now...
        tmp = textwrap.dedent("""\
        ; automatically generated, do not edit!

        $TTL    60
        $ORIGIN %(topleveldomain)s.
        @       IN      SOA     ns1.%(topleveldomain)s. root.%(topleveldomain)s. (
                            ##SERIAL##         ; Serial (seconds since Epoch)
                            60                 ; Refresh
                            60                 ; Retry
                            60                 ; Expire
                            60 )               ; Negative Cache TTL
        ;
        @               IN      NS      ns1
        @               IN      NS      ns2
        @               IN      MX      10 mail
        ns1             IN      A       %(ns1)s
        ns2             IN      A       %(ns2)s
        mail            IN      A       %(mail)s
        """ % {'topleveldomain':top_level_domain, 'ns1':ns1, 'ns2':ns2, 'mail':mail})

        for i in domains:
            dname = i.subname
            if dname == '':
                dname = '@'
            tmp += textwrap.dedent("""\

            ; ------------------------------------------------------------------------
            ; subdomain: '%(subname)s'
            """ % {'subname': i.subname})

            # cluster records
            for s in i.servers:
                if status_dict[s]:
                    tmp += textwrap.dedent("""\
                    %(dname)s IN A %(addr)s
                    """ % {'dname':dname, 'addr':s})
                else:
                    tmp += textwrap.dedent("""\
                    ; %(dname)s  (%(addr)s not responding)
                    """ % {'dname':dname, 'addr':s})

            # records for individual servers
            for idx, s in enumerate(i.servers):
                srv_idx = idx + 1
                if i.subname == '':
                    sname = 'server%d' % srv_idx
                else:
                    sname = 'server%d.%s' % (srv_idx, i.subname)
                if status_dict[s]:
                    tmp += textwrap.dedent("""\
                    %(sname)s IN A %(addr)s
                    """ % {'sname':sname, 'addr':s})
                else:
                    tmp += textwrap.dedent("""\
                    ; %(sname)s  (%(addr)s not responding)
                    """ % {'sname':sname, 'addr':s})

        return tmp
    
    # FIXME: this is currently dependent on some existing configuration files
    # in /etc/bind (db.root).  Remove dependency or generate / check for deps.
    def write_configs(self, serial):
        named_conf = self.named_conf
        zonefile = string.replace(self.zonefile, '##SERIAL##', str(serial))

        if not _check_marker():
            _log.warning('dns server marker missing, not writing config files')
            return

        f = None
        try:
            f = open('/etc/bind/named.conf', 'wb')
            f.write(named_conf)
        finally:
            if f is not None:
                f.close()
                f = None
    
        f = None
        try:
            f = open('/etc/bind/db.topleveldomain', 'wb')
            f.write(zonefile)
        finally:
            if f is not None:
                f.close()
                f = None
    
    def __eq__(self, other):
        if isinstance(other, _DnsConfig):
            return (self.named_conf == other.named_conf) and (self.zonefile == other.zonefile)
        else:
            return False
    
class DnsMaster:
    def __init__(self, cfg_file):
        self.cfg_file = cfg_file
        self.top_level_domain = None
        self.ns1 = None
        self.ns2 = None
        self.mail = None
        self.domains = None
        self.server_addresses = None
        self.server_monitors = None
        self.current_dns_config = None
        self.bind_health_timer = None
        self.bind_health_interval = 60.0
        self._read_config()
        
    def _read_config(self):
        dom = minidom.parse(self.cfg_file)
        top = dom.documentElement

        # string helper
        def _get_string(n):
            t = ''
            for c in n.childNodes:
                if c.nodeType == c.TEXT_NODE:
                    t += c.data
            return str(t.strip())

        # parse top level info
        if top.tagName != 'config':
            raise Exception('Invalid configuration file')
        tld = top.getElementsByTagName('delegated-domain')[0]
        top_level_domain = _get_string(tld.getElementsByTagName('name')[0])
        ns1 = _get_string(tld.getElementsByTagName('ns1')[0])
        ns2 = _get_string(tld.getElementsByTagName('ns2')[0])
        mail = _get_string(tld.getElementsByTagName('mail')[0])

        # parse domains
        domlist = []        
        for i in top.getElementsByTagName('subdomain'):
            name = _get_string(i.getElementsByTagName('name')[0])
            srv = []
            for j in i.getElementsByTagName('server'):
                addr = _get_string(j)
                srv.append(addr)
            domlist.append(_DnsDomain(top_level_domain, name, srv))

        # config seems ok, store to self
        self.top_level_domain = top_level_domain
        self.ns1 = ns1
        self.ns2 = ns2
        self.mail = mail
        self.domains = domlist
        
        # process config into more useful self variables
        srvlist = []
        for d in self.domains:
            for s in d.servers:
                if s not in srvlist:
                    srvlist.append(s)
        self.server_addresses = srvlist
                
    def _status_changed(self, monitor):
        # XXX: timezone?
        now = time.time()

        st = []
        for i in self.server_monitors:
            st.append('%s -> %s' % (i.get_address(), i.get_status()))
        _log.info('server status changed for server %s, statuses now: [%s]' % (monitor.get_address(), ', '.join(st)))

        # generate new configuration object (ignoring DNS serial)
        old_cfg = self.current_dns_config
        new_cfg = self._generate_dns_config()
        if old_cfg == new_cfg:
            _log.debug('bind configuration did not change')
        else:
            # configuration changed, restart bind
            _log.info('bind configuration needs to be changed, reconfiguring and restarting bind')
            self._stop_bind()
            self._write_dns_config(new_cfg, now)
            self._start_bind()
            self.current_dns_config = new_cfg
            
    def _generate_dns_config(self):
        t = {}
        for i in self.server_monitors:
            # ip address (as string) -> True, False (whether server OK)
            t[i.get_address()] = (i.get_status() == i.STATUS_OK)

        return _DnsConfig(self.top_level_domain, self.ns1, self.ns2, self.mail, self.domains, t)
    
    def _write_dns_config(self, cfg, now):
        cfg.write_configs(str(int(now)))
    
    def _start_bind(self):
        if not _check_marker():
            _log.warning('no marker, not starting bind')
            return
        
        # XXX: error handling
        runcommand.run(['/etc/init.d/bind9', 'start'])
    
    def _stop_bind(self):
        if not _check_marker():
            _log.warning('no marker, not stopping bind')
            return

        # XXX: error handling
        runcommand.run(['/etc/init.d/bind9', 'stop'])
        runcommand.run(['/usr/bin/killall', '-9', 'named'])

    def _bind_health_callback(self):
        self.bind_health_timer = None

        bind_health = True

        try:
            rv, stdout, stderr = runcommand.run(['/usr/bin/killall', '-0', 'named'])
            if rv != 0:
                bind_health = False

            # XXX: could do better here, e.g. resolve all subdomains and see that
            # the results make some sense
        except:
            _log.exception('bind health check failed')

        if not bind_health:
            _log.warning('bind health check failed, restarting bind')
            try:
                self._stop_bind()
            except:
                _log.exception('bind stop failed')
            try:
                self._start_bind()
            except:
                _log.exception('bind start failed')
        else:
            _log.debug('bind health ok')
            
        self.bind_health_timer = reactor.callLater(self.bind_health_interval, self._bind_health_callback)

    def start(self):
        self.server_monitors = []
        for i in self.server_addresses:
            self.server_monitors.append(monitor.Monitor(server_address=i, callback=self._status_changed, interval=30.0))

        for i in self.server_monitors:
            i.start(now=True)

        self.bind_health_timer = reactor.callLater(self.bind_health_interval, self._bind_health_callback)
        
    def stop(self):
        for i in self.server_monitors:
            i.stop()

        if self.bind_health_timer is not None:
            self.bind_health_timer.cancel()
            self.bind_health_timer = None
            
