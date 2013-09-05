"""FreeRADIUS daemon configuration wrapper."""
__docformat__ = 'epytext en'

import re, textwrap

from codebay.common import rdf
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import helpers
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.config import daemon
from codebay.l2tpserver import db

ns = rdfconfig.ns
run_command = runcommand.run_command


class FreeradiusConfig(daemon.DaemonConfig):
    name = 'freeradius'
    command = constants.CMD_FREERADIUS
    pidfile = constants.FREERADIUS_PIDFILE
    cleanup_files = []

    def get_args(self):
        return ['-d', constants.FREERADIUS_CONFIG_DIR]

    def _create_users_file(self, cfg, resinfo, using_proxy):
        users_cfg = cfg.getS(ns.usersConfig)
        users_config = ''
        for u in users_cfg.getS(ns.users, rdf.Bag(rdf.Type(ns.User))):
            user = ''
            username = u.getS(ns.username, rdf.String)

            password = None
            if u.hasS(ns.password):
                password = u.getS(ns.password, rdf.String)

            password_md5 = None
            if u.hasS(ns.passwordMd5):
                password_nt = u.getS(ns.passwordMd5, rdf.String)

            password_nt = None
            if u.hasS(ns.passwordNtHash):
                password_nt = u.getS(ns.passwordNtHash, rdf.String)

            self._log.debug('considering user %s for ppp config' % username)

            # skip empty names and passwords
            if username == '' or password == '':
                self._log.warning('skipping empty username/password')
                continue

            # skip site-to-site clients
            if u.hasS(ns.siteToSiteUser):
                s2s = u.getS(ns.siteToSiteUser, rdf.Type(ns.SiteToSiteUser))
                role = s2s.getS(ns.role)
                if role.hasType(ns.Client):
                    self._log.debug('skipping site-to-site client %s' % username)
                    continue
                elif role.hasType(ns.Server):
                    self._log.debug('including site-to-site server %s' % username)
                else:
                    self._log.warning('invalid site-to-site role for user %s, skipping' % username)
                    continue

            def _oct_escape(s):
                r = ''
                for i in s:
                    r += '\\%03o' % ord(i)
                return r

            # XXX: only plaintext passwords possible with freeradius users -file
            # XXX: with rlm_passwd files it is the same problem
            if password is not None:
                # plaintext password - e.g. site-to-site connections
                user = '\n%s  User-Password == %s, Proxy-To-Realm := LOCAL' % (_oct_escape(username), _oct_escape(password))
            elif password_nt is not None:
                # hashed passwords
                user = '\n%s  NT-Password := 0x%s, Proxy-To-Realm := LOCAL' % (_oct_escape(username), password_nt)
            else:
                self._log.error('user does not have plain or nt password hash, skipping')
                continue
            
            if u.hasS(ns.fixedIp):
                fixip = u.getS(ns.fixedIp, rdf.IPv4Address).toString()
                user += '\n    Framed-IP-Address = %s' % fixip

            users_config += "%s\n" % user

        if using_proxy:
            users_config += textwrap.dedent("""\

            # Direct all other users to default realm for proxying
            DEFAULT Proxy-To-Realm := default.realm.invalid
            """)

        return {'file': constants.FREERADIUS_USERS, 'cont': users_config}


    def _get_radius_parameters(self, cfg):
        proxy = False
        servers = []
        nas_id = None

        rad_cfg = cfg.getS(ns.radiusConfig)

        if rad_cfg.hasS(ns.radiusNasIdentifier):
            n = rad_cfg.getS(ns.radiusNasIdentifier, rdf.String)
            if (n is not None) and (n != ''):
                nas_id = n

        if not rad_cfg.hasS(ns.radiusServers):
            return proxy, nas_id, servers

        for server in rad_cfg.getS(ns.radiusServers, rdf.Seq(rdf.Resource)):
            addr = server.getS(ns.address, rdf.String)
            port = server.getS(ns.port, rdf.Integer)
            secret = server.getS(ns.secret, rdf.String)
            if addr is not None and addr != '' and port is not None and int(port) > 0 and secret is not None and secret != '':
                servers.append([addr, int(port), secret])
                proxy = True

        return proxy, nas_id, servers


    def create_config(self, cfg, resinfo):
        """Create FreeRADIUS configuration files.

        Freeradius is always started and thus no start/nostart magic is needed.
        """

        net_cfg = cfg.getS(ns.networkConfig, rdf.Type(ns.NetworkConfig))
        ppp_cfg = cfg.getS(ns.pppConfig, rdf.Type(ns.PppConfig))
        ppp_auth = ppp_cfg.getS(ns.pppAuthentication, rdf.Type(ns.PppAuthentication))
        ppp_comp = ppp_cfg.getS(ns.pppCompression, rdf.Type(ns.PppCompression))
        l2tp_cfg = cfg.getS(ns.l2tpConfig, rdf.Type(ns.L2tpConfig))

        radius_public_ip = resinfo.public_interface.address.getAddress().toString()
        nas_ip = radius_public_ip

        radius_private_ip = None
        if resinfo.private_interface is not None:
            radius_private_ip = resinfo.private_interface.address.getAddress().toString()
            nas_ip = radius_private_ip

        # NB: this secret does no good for us and may be static
        client_config = textwrap.dedent("""\
        # autogenerated file, do not edit
        client 127.0.0.1 {
            secret      = notasecret
            shortname   = localhost
            nastype     = other
        }
        """ % {'nas_ip':nas_ip})
        
        dictionary_config = textwrap.dedent("""\
        # autogenerated file, do not edit
        $INCLUDE        /usr/share/freeradius/dictionary
        """)

        # XXX: may need changes in the future
        retry_delay = 5
        retry_count = 3
        proxy_config = textwrap.dedent("""\
        # autogenerated file, do not edit

        proxy server {
            synchronous = no
            retry_delay = %(retry_delay)d
            retry_count = %(retry_count)d
            dead_time = 120
            default_fallback = yes
            post_proxy_authorize = no
        }

        realm LOCAL {
                type    	= radius
                authhost	= LOCAL
                accthost	= LOCAL
        }        
        """ % {'retry_delay':retry_delay, 'retry_count':retry_count})

        # NB: no way to do failover with DEFAULT or NULL realms, use a
        # bogus realm instead

        using_proxy, nas_id, servers = self._get_radius_parameters(cfg)
        for addr, port, secret in servers:
            if addr is not None and port is not None and secret is not None:
                proxy_config += textwrap.dedent("""\

                realm default.realm.invalid {
                    type      = radius
        	    authhost  = %(addr)s:%(port)s
        	    secret    = "%(secret)s"
                    nostrip
                }
                """ % {'addr':str(addr), 'port':str(port), 'secret':str(secret)})


        # XXX: log_file below *does not work*, it causes a non-fatal startup error
        # can it be removed?  we're using syslog anyway
        
        # XXX: may need changing in the future
        max_reqtime = 30
        radiusd_config = textwrap.dedent("""\
        # autogenerated file, do not edit

        prefix = /usr
        exec_prefix = /usr
        sysconfdir = /etc
        localstatedir = /var
        sbindir = ${exec_prefix}/sbin
        logdir = syslog
        raddbdir = %(raddbdir)s
        radacctdir = ${logdir}/radacct

        confdir = ${raddbdir}
        run_dir = %(run_dir)s
        log_file = ${logdir}/radius.log
        libdir = /usr/lib/freeradius
        pidfile = ${run_dir}/freeradius.pid
        user = freerad
        group = freerad
        max_request_time = %(max_reqtime)d
        delete_blocked_requests = yes
        cleanup_delay = 5
        max_requests = 512
        """ % {'raddbdir':constants.FREERADIUS_CONFIG_DIR,
               'run_dir':constants.FREERADIUS_RUNPATH,
               'max_reqtime':max_reqtime})

        # NB: bind only to localhost
        radiusd_config += textwrap.dedent("""\
        listen {
            ipaddr = 127.0.0.1
            port = 1812
            type = auth
        }
        """)

        radiusd_config += textwrap.dedent("""\

        hostname_lookups = no
        allow_core_dumps = no

        regular_expressions     = yes
        extended_expressions    = yes
        
        log_stripped_names = no
        log_auth = no

        log_auth_badpass = no
        log_auth_goodpass = no
        usercollide = no
        lower_user = no
        lower_pass = no
        nospace_user = no
        nospace_pass = no

        checkrad = ${sbindir}/checkrad

        security {
            max_attributes = 200
            reject_delay = 1
            status_server = no
        }

        proxy_requests  = yes
        $INCLUDE  ${confdir}/proxy.conf

        $INCLUDE  ${confdir}/clients.conf

        thread pool {
            start_servers = 3
            max_servers = 16
            min_spare_servers = 2
            max_spare_servers = 3
            max_requests_per_server = 0
        }
        
        modules {
            pap {
                auto_header = yes
            }
        
            chap {
                authtype = CHAP
            }

            pam {
                pam_auth = radiusd
            }

            mschap {
            }

            realm suffix {
                format = suffix
                delimiter = "@"
                ignore_default = no
                ignore_null = no
            }
        
            preprocess {
                huntgroups = ${confdir}/huntgroups
                hints = ${confdir}/hints

                with_ascend_hack = no
                ascend_channels_per_line = 23
                with_ntdomain_hack = no
                with_specialix_jetstream_hack = no
                with_cisco_vsa_hack = no
            }

            files {
                usersfile = ${confdir}/users
                acctusersfile = ${confdir}/acct_users
                preproxy_usersfile = ${confdir}/preproxy_users
                compat = no
            }

            detail {
                detailfile = ${radacctdir}/%{Client-IP-Address}/detail-%Y%m%d
                detailperm = 0600        
                suppress {
                    User-Password
                }
            }

            acct_unique {
                key = "User-Name, Acct-Session-Id, NAS-IP-Address, Client-IP-Address, NAS-Port"
            }
        
            expr {
            }

            digest {
            }
        
            exec {
                wait = yes
                input_pairs = request
            }

        }

        instantiate {
            exec
            expr
        }
        
        authorize {
            preprocess        
            chap
            mschap
            suffix
            files
            pap
        }
        
        authenticate {
            Auth-Type PAP {
                pap
            }
            Auth-Type CHAP {
                chap
            }
            Auth-Type MS-CHAP {
                mschap
            }
        }
        
        session {
        }
        
        post-auth {
        }

        pre-proxy {
            files
        }
        
        post-proxy {
        }
        """)

        preproxy_config = textwrap.dedent("""\
        # autogenerated file, do not edit

        DEFAULT
            NAS-IP-Address := "%(nas_ip)s",
            NAS-Port-Type := 5""" % {'nas_ip':nas_ip})

        if nas_id is not None:
            preproxy_config += textwrap.dedent("""\
            ,
                NAS-Identifier := "%(nas_id)s"

            """ % {'nas_id':nas_id})
        else:
            preproxy_config += '\n\n'            

        self.configs = [
            {'file': constants.FREERADIUS_ACCT_USERS, 'cont': ''},               # Not used
            {'file': constants.FREERADIUS_ATTRS, 'cont': ''},                    # Not used
            {'file': constants.FREERADIUS_CLIENTS, 'cont': ''},                  # Deprecated
            {'file': constants.FREERADIUS_CLIENTS_CONF, 'cont': client_config},
            {'file': constants.FREERADIUS_DICTIONARY, 'cont': dictionary_config},
            {'file': constants.FREERADIUS_EAP_CONF, 'cont': ''},                 # Not used
            {'file': constants.FREERADIUS_EXPERIMENTAL_CONF, 'cont': ''},        # Not used
            {'file': constants.FREERADIUS_HINTS, 'cont': ''},                    # Not used
            {'file': constants.FREERADIUS_HUNTGROUPS, 'cont': ''},               # Not used
            {'file': constants.FREERADIUS_LDAP_ATTRMAP, 'cont': ''},             # Not used
            {'file': constants.FREERADIUS_MSSQL_CONF, 'cont': ''},               # Not used
            {'file': constants.FREERADIUS_NASLIST, 'cont': ''},                  # Deprecated
            {'file': constants.FREERADIUS_NASPASSWD, 'cont': ''},                # Not used
            {'file': constants.FREERADIUS_ORACLESQL_CONF, 'cont': ''},           # Not used
            {'file': constants.FREERADIUS_OTP_CONF, 'cont': ''},                 # Not used
            {'file': constants.FREERADIUS_POSTGRESQL_CONF, 'cont': ''},          # Not used
            {'file': constants.FREERADIUS_PREPROXY_USERS, 'cont': preproxy_config},
            {'file': constants.FREERADIUS_PROXY_CONF, 'cont': proxy_config},
            {'file': constants.FREERADIUS_RADIUSD_CONF, 'cont': radiusd_config},
            {'file': constants.FREERADIUS_REALMS, 'cont': ''},                   # Deprecated
            {'file': constants.FREERADIUS_SNMP_CONF, 'cont': ''},                # Not used
            {'file': constants.FREERADIUS_SQL_CONF, 'cont': ''},                 # Not used
            {'file': constants.FREERADIUS_SQLIPPOOL_CONF, 'cont': ''},           # Not used
            ]

        self.configs.append(self._create_users_file(cfg, resinfo, using_proxy))

    def write_config(self):
        # Ensure default certs dicretory is no more.
        run_command([constants.CMD_RM, '-rf', '/etc/freeradius/certs'])
        daemon.DaemonConfig.write_config(self)

    def pre_stop(self):
        run_command([constants.CMD_MKDIR, '-p', constants.FREERADIUS_RUNPATH], retval=runcommand.FAIL)
        run_command([constants.CMD_CHOWN, 'freerad:freerad', constants.FREERADIUS_RUNPATH], retval=runcommand.FAIL)
