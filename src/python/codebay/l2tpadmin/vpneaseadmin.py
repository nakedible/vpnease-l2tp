"""Swiss army knife VPNease administration helper.

Contains functionality required by all server-side elements: product web
server, database server, management server, DNS server, and monitoring
server.  The intention is to collect "script crud" here, and use it by
invoking the tool from crontab, init-scripts, etc.
"""

import os, sys, textwrap


def usage():
    print textwrap.dedent("""
    Usage:

       vpneaseadmin <category> <command> <parameters>

    Commands:

       [product web]
       vpneaseadmin pw start
       vpneaseadmin pw stop

       [database]
       vpneaseadmin db start
       vpneaseadmin db stop
       vpneaseadmin db create
       vpneaseadmin db delete
       vpneaseadmin db backup
       vpneaseadmin db restore
       vpneaseadmin db list-licenses
       vpneaseadmin db list-licensekeys
       vpneaseadmin db test-import-legacy-licenses
       vpneaseadmin db test-license-fetch-loop

       [management server]
       vpneaseadmin ms start
       vpneaseadmin ms stop
       vpneaseadmin ms demoinfo
       vpneaseadmin ms stats
       vpneaseadmin ms backup

       [dns server]
       vpneaseadmin dns start
       vpneaseadmin dns stop
       vpneaseadmin dns update

       [monitoring server]
       vpneaseadmin mon check

       [misc]
       vpneaseadmin misc create-management-server-keypair
       vpneaseadmin misc create-random-license-key
       """)

def main():
    try:
        print >> sys.stderr, 'vpnease-admin...'

        cat = sys.argv[1]
        cmd = sys.argv[2]
        args = sys.argv[3:]

        print >> sys.stderr, 'cat: %s, cmd: %s, args: %s' % (cat, cmd, args)
        
        if cat == 'pw':
            from codebay.l2tpadmin import productwebserver as pw

            if cmd == 'start':
                pw.start(args)
            elif cmd == 'stop':
                pw.stop(args)
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        elif cat == 'db':
            from codebay.l2tpadmin import databaseserver as db

            if cmd == 'start':
                db.start(args)
            elif cmd == 'stop':
                db.stop(args)
            elif cmd == 'create':
                db.create(args)
            elif cmd == 'delete':
                db.delete(args)
            elif cmd == 'backup':
                db.backup(args)
            elif cmd == 'restore':
                db.restore(args)
            elif cmd == 'list-licenses':
                db.list_licenses(args)
            elif cmd == 'list-licensekeys':
                db.list_licensekeys(args)
            elif cmd == 'test-import-legacy-licenses':
                db.test_import_legacy_licenses(args)
            elif cmd == 'test-license-fetch-loop':
                db.test_license_fetch_loop(args)
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        elif cat == 'ms':
            from codebay.l2tpadmin import managementserver as ms

            if cmd == 'start':
                ms.start(args)
            elif cmd == 'stop':
                ms.stop(args)
            elif cmd == 'demoinfo':
                print ms.get_demo_license_info()
            elif cmd == 'backup':
                backup_file = ms.write_backup_file()
                print 'Backup file written to: %s' % backup_file
            elif cmd == 'stats':
                stats = ms.get_stats()
                print stats
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        elif cat == 'dns':
            from codebay.l2tpadmin import dnsserver as dns

            if cmd == 'start':
                dns.start(args)
            elif cmd == 'stop':
                dns.stop(args)
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        elif cat == 'mon':
            from codebay.l2tpadmin import monitoringserver as mon
            if cmd == 'check':
                mon.MonitoringServer().check(args)
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        elif cat == 'misc':
            if cmd == 'create-management-server-keypair':
                import os
                from codebay.l2tpserver import helpers

                if not os.path.exists('vpnease-ca-private-aes256.pem'):
                    raise Exception('Must be in the directory with VPNease CA files')

                out_privkey = 'management-server-private.pem'
                out_cert = 'management-server-certificate.pem'

                print 'Creating management server keypair to files: %s, %s' % (out_privkey, out_cert)

                helpers.generate_ca_signed_certificate('vpnease-ca-private-aes256.pem',
                                                       'vpnease-ca-certificate.pem',
                                                       'vpnease-ca-serialfile.txt',
                                                       out_privkey,
                                                       out_cert,
                                                       nbits=1024, common_name='VPNease Management Server',
                                                       organization='VPNease')
            elif cmd == 'create-random-license-key':
                from codebay.common import licensekey

                print licensekey.create_random_license()
            else:
                raise Exception('unknown command %s for category %s' % (cmd, cat))
        else:
            raise Exception('unknown category %s' % cat)

    except:
        usage()
        raise

if __name__ == '__main__':
    main()
