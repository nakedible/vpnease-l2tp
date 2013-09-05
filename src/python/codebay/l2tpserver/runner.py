#!/usr/bin/python

import sys, textwrap, tempfile, optparse

from codebay.common import logger
from codebay.common import rdf
from codebay.l2tpserver import startstop
from codebay.l2tpserver import constants
from codebay.l2tpserver import rdfconfig
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import helpers
from codebay.l2tpserver import rdfdumper
from codebay.l2tpserver import db

ns = rdfconfig.ns

run_command = runcommand.run_command

_log = logger.get('l2tpserver.runner')

class Runner:
    def __init__(self):
        pass
    
    def usage_and_exit(self):
        """Print usage and exit."""
	
        print textwrap.dedent("""\
        Commands: run, resetstate, dumpall, dumpstatus, dumpconfig, status, start, public-interface-test, private-interface-test, route-test, stop.
        """)
        sys.exit(1)

    def runner(self):
        try:
            return self._do_runner()
        finally:
            import os

            file1 = constants.RUNNER_TEMPORARY_SQLITE_DATABASE
            file2 = '%s-journal' % file1

            for i in [file1, file2]:
                if os.path.exists(i):
                    os.unlink(i)
       
    def _do_runner(self):
        """Handle runner command line commands."""

        if len(sys.argv) == 1:
            self.usage_and_exit()
        cmd = sys.argv[1]

        opt = optparse.OptionParser(usage='%prog', version='%prog')
        opt.add_option('-r', '--rdf-file', help='RDF file instead of default database',
                       action='store', dest='rdf_file', type='string', metavar='<file>')
        opt.add_option('-m', '--mode', help='Mode for start',
                       action='store', dest='mode', type='string', metavar='<string>')
        opt.add_option('-i', '--import-path', dest='importpath')
        opt.add_option('-n', '--no-distro-restart', help='Prevent distro networking restart on runner stop',
                       action='store_true', dest='no_distro_restart', default=False)

        opt.set_defaults(rdf_file=None,
                         mode=None,
                         importpath='system')

        (opts, args) = opt.parse_args(sys.argv[2:])
        
        print 'Command = %s, Options: %s' % (cmd, str(opts))

        if opts.rdf_file is not None:
            print 'runner using database file: %s' % opts.rdf_file
            db.replace_database_with_file(opts.rdf_file, constants.RUNNER_TEMPORARY_SQLITE_DATABASE)

        if opts.mode is not None:
            mode = opts.mode
        else:
            mode = 'FULL'
            print 'no mode given, using %s' % mode

        importpath = 'system'
        if opts.importpath is not None:
            importpath = opts.importpath

        nodistrorestart = False
        if opts.no_distro_restart is not None and opts.no_distro_restart:
            nodistrorestart = True

        # XXX: these need rethinking, currently ripped from startstop.py.
        
        # XXX: this should probably be some command name => lambda system, to make command help etc easier

        # XXX: also need transactions here to make things reasonably fast (e.g. for rdf dumps)
        try:
            if mode == 'FULL':
                runner_mode = startstop._mode_full
            elif mode == 'NETWORK-ONLY':
                runner_mode = startstop._mode_network_only
            else:
                raise Exception('unknown mode: %s' % mode)

            _log.debug('starting runner in mode: %s' % runner_mode)
            r = startstop.L2tpRunner(mode=runner_mode, nodistrorestart=nodistrorestart, importpath=importpath)

            if cmd == 'run':
                r.create_pidfile()
                r.run()

            elif cmd == 'resetstate':
                # Set to a fresh node - this orphans all previous state
                return db.get_db().getRoot().setS(ns.l2tpDeviceStatus, rdf.Type(ns.L2tpDeviceStatus))

            elif cmd == 'dumpall':
                rd = rdfdumper.RdfDumper()
                print rd.dump_resource(db.get_db().getRoot(), escaped=True)
            
            elif cmd == 'dumpstatus':
                rd = rdfdumper.RdfDumper()
                print rd.dump_resource(db.get_db().getRoot().getS(ns.l2tpDeviceStatus), escaped=True)

            elif cmd == 'dumpconfig':
                rd = rdfdumper.RdfDumper()
                print rd.dump_resource(db.get_db().getRoot().getS(ns.l2tpDeviceConfig), escaped=True)
            
            elif cmd == 'status':
                st_root = helpers.get_status()

                st_last_str = 'unknown'
                if st_root.hasS(ns.lastStateUpdate):
                    st_last_str = st_root.getS(ns.lastStateUpdate, rdf.Datetime).isoformat()
                
                st_start_str = 'unknown'
                if st_root.hasS(ns.startTime):
                    st_start_str = st_root.getS(ns.startTime, rdf.Datetime).isoformat()

                st_stop_str = 'unknown'
                if st_root.hasS(ns.stopTime):
                    st_stop_str = st_root.getS(ns.stopTime, rdf.Datetime).isoformat()

                st_str = 'unknown'
                st = st_root.getS(ns.state)
                if st.hasType(ns.StateStarting):
                    st_str = 'starting'
                    subst = st.getS(ns.subState)
                    if subst.hasType(ns.StateStartingPreparing):
                        st_str += ' - preparing'
                    if subst.hasType(ns.StateStartingWaitingForDhcp):
                        st_str += ' - waiting for dhcp'
                    if subst.hasType(ns.StateStartingNetwork):
                        st_str += ' - starting network'
                    if subst.hasType(ns.StateStartingDaemons):
                        st_str += ' - starting daemons'
                elif st.hasType(ns.StateRunning):
                    st_str = 'running'
                elif st.hasType(ns.StateStopping):
                    st_str = 'stopping'
                elif st.hasType(ns.StateStopped):
                    st_str = 'stopped'

                st_ppp = 'unknown'
                if st_root.hasS(ns.pppDevices):
                    st_ppp = '%s' % len(helpers.get_ppp_devices())
            
                print 'STATUS: start=%s, stop=%s, last_update=%s, devs=%s, state: %s' % (st_start_str, st_stop_str, st_last_str, st_ppp, st_str)

            elif cmd == 'start':
                r.start()

            elif cmd == 'public-interface-test':
                # XXX
                pass

            elif cmd == 'private-interface-test':
                # XXX
                pass

            elif cmd == 'route-test':
                # XXX
                pass

            elif cmd == 'stop':
                r.stop()

            else:
                raise Exception('unknown command: %s' % cmd)

        except:
            _log.exception('l2tpgw-runner command "%s" failed.' % cmd)
            raise
        
if __name__ == "__main__":
    r = Runner()
    r.runner()

