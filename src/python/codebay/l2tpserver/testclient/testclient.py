"""L2TP/IPsec Linux test client for system testing.

The class structure is as follows:

  * TestConnection encapsulates one L2TP/IPsec connection: starting, stopping,
    and running various tests.

  * TestRunner provides a framework for starting and stopping a test, reporting
    results and so on.  It is subclassed to implement particular tests.

  * TestClient provides the command line interface and related functionality.

The protocols and daemons are arranged for testing as follows:

  * The client host has one IP per test connection, configured as aliases of
    a selected interface (e.g. eth0:0, eth0:1, etc).  This allows IPsec policies
    to be bound properly to one source address, and minimizes IPsec stack
    dependencies.

  * One pluto instance is used to manage all tunnels - we whack the instance
    to add and remove tunnels.  Pluto manages kernel policies and SAs.

  * One openl2tp instance is used to manage all L2TP tunnels.  The openl2tp
    instance is dynamically (de)configured accordingly.  Openl2tp spawns a
    PPP client when ready.

  * Determining the PPP IP address of a newly formed connection, *and* linking
    that IP address to a TestConnection instance is very important to allow
    proper testing.  We also need to get the PPP peer IP address for testing.
    The approach for doing this is:

    * We decide openl2tp tunnel and session IDs on our own, and can thus
      'compute' the eventual device name (l2tpTUN-SES).
      
    * When pluto and openl2tp have been initiated, we poll waiting for
      the device to appear; if it doesn't appear in a reasonable time,
      we assume something is wrong and terminate the TestConnection.

    * Once the device appear, we get the IP address information etc. using
      regexps.

Other notes:
  * There are global (interprocess) locks for pluto and openl2tp control
    connections.  These locks prevent parallel "whacking" of both daemons,
    as such behavior would probably aggravate bugs.

  * Openl2tp and Pluto connections are not persistent - we prefer to bail
    out and start a fresh TestConnection, as exited TestConnections provide
    useful statistics.
"""
__docformat__ = 'epytext en'

import os, sys, time, thread, optparse

from codebay.common import logger
from codebay.common import datatypes
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import daemonstart
from codebay.l2tpserver.testclient import globals
from codebay.l2tpserver.testclient import locks
from codebay.l2tpserver.testclient import systempoller  # FIXME
from codebay.l2tpserver.testclient import testconnection

import codebay.l2tpserver.testclient.constants as testclientconst # unfortunate naming clash

_log = logger.get('l2tpserver.testclient.testclient')
run_command = runcommand.run_command

TESTCLIENT_VERSION = '1.0'

# --------------------------------------------------------------------------


class TestRunner:
    def _pluto_write_psk(self, psk):
        """Create Pluto pre-shared key file."""
        f = open(testclientconst.PLUTO_PSK, 'wb')
        f.write(': PSK "%s"\n' % psk)
        f.close()

    def _pluto_start(self):
        """Start pluto."""

        # cleanup has already been called when we come here, so extra PID files
        # etc have been nuked already

        try:
            d = daemonstart.DaemonStart(_log)
            d.start_daemon(command=constants.CMD_PLUTO,
                           pidfile=constants.PLUTO_PIDFILE,
                           args=['--secretsfile',
                                 testclientconst.PLUTO_PSK,
                                 '--nat_traversal',
                                 '--nhelpers', '0',
                                 '--debug-none'])
        except:
            _log.exception('_pluto_start failed.')
            raise

        locks.whack_lock_acquire()

        try:
            [rv, ig1, err] = run_command([constants.CMD_IPSEC, 'whack', '--listen'])
            _log.debug('whack --listen return value: %d, stderr: %s' % (rv, err))
        except:
            _log.exception('_pluto_start failed')
            locks.whack_lock_release()
            raise

        locks.whack_lock_release()

    def _pluto_stop(self):
        """Stop pluto."""

        try:
            d = daemonstart.DaemonStart(_log)
            d.stop_daemon(command=constants.CMD_PLUTO, pidfile=constants.PLUTO_PIDFILE)
            d.hard_stop_daemon(command=constants.CMD_PLUTO, pidfile=constants.PLUTO_PIDFILE)
            d.cleanup_daemon(pidfile=constants.PLUTO_PIDFILE, cleanup_files=[constants.PLUTO_CTLFILE])

            run_command([constants.CMD_SETKEY, '-FP'], retval=runcommand.FAIL)
            run_command([constants.CMD_SETKEY, '-F'], retval=runcommand.FAIL)
        except:
            _log.exception('_pluto_stop_failed')
            raise

    def _openl2tp_start(self):
        """Start Openl2tp."""

        # cleanup has already been called when we come here, so extra PID files
        # etc have been nuked already

        locks.l2tpconfig_lock_acquire()

        try:
            run_command([constants.CMD_MODPROBE, 'pppol2tp'])
            d = daemonstart.DaemonStart(_log)

            d.start_daemon(command=constants.CMD_OPENL2TP, pidfile=constants.OPENL2TP_PIDFILE)

            # FIXME: add local IP option if using this.
            # d.start_daemon(command=constants.CMD_OPENL2TP, args=['-a', '172.20.100.202'], pidfile=constants.OPENL2TP_PIDFILE)
        except:
            _log.exception('_openl2tp_start failed')
            locks.l2tpconfig_lock_release()
            raise

        locks.l2tpconfig_lock_release()

    def _openl2tp_stop(self):
        """Stop Openl2tp."""

        try:
            d = daemonstart.DaemonStart(_log)
            d.stop_daemon(command=constants.CMD_OPENL2TP, pidfile=constants.OPENL2TP_PIDFILE)
            d.stop_daemon(command=constants.CMD_PPPD, pidfile=None)
            d.cleanup_daemon(pidfile=constants.OPENL2TP_PIDFILE)
        except:
            _log.exception('_openl2tp_stop failed')

        time.sleep(2)

        try:
            d.hard_stop_daemon(command=constants.CMD_OPENL2TP, pidfile=constants.OPENL2TP_PIDFILE)
            d.hard_stop_daemon(command=constants.CMD_PPPD, pidfile=None)
            d.cleanup_daemon(pidfile=constants.OPENL2TP_PIDFILE)
        except:
            _log.exception('_openl2tp_stop failed (hard)')
            raise

    def _configure_interfaces(self, interface, first_ip, netmask, num_ips):
        """Configure network devices for IPsec use."""

        ip_start = datatypes.IPv4Address.fromString(first_ip)
        for i in xrange(num_ips):
            ip = datatypes.IPv4Address.fromLong(ip_start.toLong() + long(i))
            device = '%s:%d' % (interface, i)

            run_command([constants.CMD_IFCONFIG, device, 'down'])
            run_command([constants.CMD_IFCONFIG, device, ip.toString(), 'netmask', netmask])
            run_command([constants.CMD_IFCONFIG, device, 'up'])
        
    def _deconfigure_interfaces(self, interface, num_ips):
        """Deconfigure network devices."""

        # FIXME: deconfigure more than what was configured?  0...255 ?

        for i in xrange(num_ips):
            device = '%s:%d' % (interface, i)
            run_command([constants.CMD_IFCONFIG, device, 'down'])

    def _cleanup(self, opts):
        """Stop daemons, cleanup interfaces and other state.."""

        try:
            self._pluto_stop()
        except:
            _log.exception('_pluto_stop failed')
        try:
            self._openl2tp_stop()
        except:
            _log.exception('_openl2tp_stop failed')
        try:
            self._deconfigure_interfaces(opts.interface, opts.num_clients * testclientconst.POOL_SIZE)
        except:
            _log.exception('_deconfigure_interfaces failed')

    def test_main(self, opts):
        """Run actual tests.

        When this function is entered, the testing environment is ready (daemons
        are running and ready, interfaces are configured, etc).  The function only
        needs to run actual tests by running TestConnections, and create useful
        results.  The wrapper will catch Exceptions and handle cleanup.
        """

        raise Exception('unimplemented')

    def run_test(self, opts):
        """Wrapper for starting up, calling internal test function, and cleaning up.

        Note that 'opts' is passed directly from OptionParser; rather ugly, but
        works for now.
        """
        
        try:
            _log.info('cleaning up before configuration')
            self._cleanup(opts)

            _log.info('configuring interface aliases (takes a while)')
            self._configure_interfaces(opts.interface, opts.source, opts.netmask, opts.num_clients * 10)

            _log.info('starting daemons (takes a while)')
            self._pluto_write_psk(opts.psk)
            self._pluto_start()
            self._openl2tp_start()

            # this allows us to 'bg' and replace openl2tpd with a manually started one
            test_wait=3
            _log.info('starting tests in %d seconds' % test_wait)
            time.sleep(test_wait)

            # actual test (in a subclass)
            self.test_main(opts)
        except SystemExit:
            _log.info('caught SystemExit, passing on')
            raise
        except:
            _log.exception('run_test failed')

        _log.info('cleaning up before exiting')
        self._cleanup(opts)

class BasicConnectionSetupTestRunner(TestRunner):
    def test_main(self, opts):
        """Basic connection setup test runner.

        Spawn num_clients TestConnections in a staggered fashion and sleep
        forever.  This is useful in testing basic connection setup and such,
        but is not useful as a system test.

        This test never reconnects clients, so it is possible to track how
        many connections survive rekeying over time.
        """

        _log.info('start BasicConnectionSetupTestRunner')

        if opts.num_clients * testclientconst.POOL_SIZE > 290:
            raise Exception('cannot use over 290 addresses (%d (num of clients) * %d (pool size)), please use smaller pool or decrease number of clients' % (opts.num_clients, testclientconst.POOL_SIZE))

        for i in xrange(opts.num_clients):
            ip_start = datatypes.IPv4Address.fromString(opts.source)
            ip_mine = datatypes.IPv4Address.fromLong(ip_start.toLong() + long(i*testclientconst.POOL_SIZE))
            
            _log.info('forking a child (%d/%d) for address %s' % (i + 1, opts.num_clients, ip_mine.toString()))

            ret = os.fork()
            if ret == 0:  # child
                try:
                    # FIXME: default src and dst ip in client? or provide better interface?
                    if opts.ping_destination != None:
                        dest = opts.ping_destination
                    else:
                        dest = tc.ppp_remote_address

                    tc = testconnection.TestConnection(debug=opts.debug,
                                                       index=i,
                                                       srcip=ip_mine.toString(),
                                                       dstip=opts.destination,
                                                       router=opts.router,
                                                       psk=opts.psk,
                                                       username=opts.username,
                                                       password=opts.password,
                                                       device='%s:%d' % (opts.interface, i),
                                                       min_connect_time=opts.min_connect_time,
                                                       max_connect_time=opts.max_connect_time,
                                                       ping_dest=dest,
                                                       ping_batch=opts.ping_batch,
                                                       ping_size=opts.ping_size,
                                                       ping_interval=opts.ping_interval)

                    _log.info('starting connection (ip=%s)' % ip_mine.toString())

                    if opts.random_reconnect:
                        tc.run_random_connection_test()
                    elif opts.single_reconnect:

                        def _daemon_restart():
                            _log.info('restarting daemons')
                            try:
                                self._pluto_stop()
                            except:
                                _log.exception('_pluto_stop failed')
                            try:
                                self._openl2tp_stop()
                            except:
                                _log.exception('_openl2tp_stop failed')
                            self._pluto_start()
                            self._openl2tp_start()

                        tc.run_single_reconnect_test(daemon_restart=_daemon_restart)
                    else:
                        tc.start_connection()
                        tc.run_ping_test()

                    _log.info('finished connection (ip=%s), subprocess exiting' % ip_mine.toString())
                    sys.exit(0)
                except:
                    # FIXME: add restart option here
                    _log.exception('test connection failed')
                    sys.exit(1)

            spawn_sleep = opts.spawn_interval
            _log.info('sleeping to next spawn (%s seconds)' % spawn_sleep)
            time.sleep(spawn_sleep)  # staggering
            
        _log.info('done spawning clients, sleep forever...')
        while True:
            time.sleep(60)
            
        _log.info('stop BasicConnectionSetupTestRunner')

# --------------------------------------------------------------------------

class TestClient:
    """Command line parsing and other interfacing functionality.

    Actual test running is done by TestRunner.
    """
    
    def __init__(self):
        pass
    
    def _start_syspoller(self):
        """Start systempoller in a background thread.

        FIXME: currently unused.
        """
        
        def _sp_start():
            # globals.get_syspoller().start()
            pass
        sp_thread = thread.start_new_thread(_sp_start, ())
        # FIXME: how to kill sp_thread?
        
    def main(self):
        """Command line parsing and test launching."""
        
        opt = optparse.OptionParser(usage='%prog', version='%prog ' + TESTCLIENT_VERSION)
        opt.add_option('-n', '--num-clients', help='Number of simultaneous test client connections',
                       action='store', dest='num_clients', type='int', metavar='<int>')
        opt.add_option('-d', '--destination', help='L2TP/IPsec gateway address',
                       action='store', dest='destination', type='string', metavar='<ipv4 address>')
        opt.add_option('-s', '--source', help='First local address used by test client',
                       action='store', dest='source', type='string', metavar='<ipv4 address>')
        opt.add_option('--ping-destination', help='IP to testping through tunnel',
                       action='store', dest='ping_destination', type='string', metavar='<ipv4 address>')
        opt.add_option('-m', '--netmask', help='Netmask for local interfaces (aliases)',
                       action='store', dest='netmask', type='string', metavar='<ipv4 mask>')
        opt.add_option('-r', '--router', help='Default router (required by pluto)',
                       action='store', dest='router', type='string', metavar='<ipv4 address>')
        opt.add_option('-i', '--interface', help='Interface to be used for aliases (eth0 => eth0:0, ...)',
                       action='store', dest='interface', type='string', metavar='<interface>')
        opt.add_option('--psk', help='IPsec pre-shared key',
                       action='store', dest='psk', type='string', metavar='<string>')
        opt.add_option('-u', '--username', help='PPP authentication username',
                       action='store', dest='username', type='string', metavar='<string>')
        opt.add_option('-p', '--password', help='PPP authentication password',
                       action='store', dest='password', type='string', metavar='<string>')
        opt.add_option('--spawn-interval', help='Client spawn interval',
                       action='store', dest='spawn_interval', type='float', metavar='<float>')
        opt.add_option('--ping-interval', help='Interval between pings, can be e.g. 0.1',
                       action='store', dest='ping_interval', type='float', metavar='<float>')
        opt.add_option('--ping-size', help='Ping packet size',
                       action='store', dest='ping_size', type='int', metavar='<int>')
        opt.add_option('--ping-batch', help='Ping batch size (how many pings between device checks)',
                       action='store', dest='ping_batch', type='int', metavar='<int>')
        opt.add_option('--random-reconnect', dest='random_reconnect', action='store_true')
        opt.add_option('--single-reconnect', dest='single_reconnect', action='store_true')
        opt.add_option('--max-connect-time', help='Maximum connect time for clients in random mode',
                       action='store', dest='max_connect_time', type='int', metavar='<int>')
        opt.add_option('--min-connect-time', help='Minimum connect time for clients in random mode',
                       action='store', dest='min_connect_time', type='int', metavar='<int>')
        opt.add_option('--debug', help='Enable debug logging etc',
                       action='store_true', dest='debug')

        opt.set_defaults(num_clients=10,
                         source='172.20.100.1',
                         ping_destination=None,
                         netmask='255.255.0.0',
                         router='172.20.255.254',
                         interface='eth0',
                         psk='psk',
                         username='test',
                         password='test',
                         spawn_interval=20.0,
                         ping_interval=3.0,
                         ping_size=1024,
                         ping_batch=20,
                         debug=False,
                         random_reconnect=False,
                         single_reconnect=False,
                         max_connect_time=30*60,
                         min_connect_time=1*60)

        (opts, args) = opt.parse_args(sys.argv[1:])

        print 'Options: ' + str(opts)
        if opts.num_clients is None: raise Exception('missing num_clients')
        if opts.destination is None: raise Exception('missing destination')
        if opts.source is None: raise Exception('missing source')
        if opts.netmask is None: raise Exception('missing netmask')
        if opts.router is None: raise Exception('missing router')
        if opts.interface is None: raise Exception('missing interface')
        if opts.psk is None: raise Exception('missing psk')
        if opts.username is None: raise Exception('missing username')
        if opts.password is None: raise Exception('missing password')
        if opts.spawn_interval is None: raise Exception('missing spawn_interval')
        if opts.ping_interval is None: raise Exception('missing ping_interval')
        if opts.ping_size is None: raise Exception('missing ping_size')
        if opts.ping_batch is None: raise Exception('missing ping_batch')
        if opts.random_reconnect is None: raise Exception('missing random_reconnect')
        if opts.max_connect_time is None: raise Exception('missing max_connect_time')
        if opts.min_connect_time is None: raise Exception('missing min_connect_time')
        if opts.debug is None: raise Exception('missing debug')

        # FIXME: syspoller is now unnecessary, but could be added back
#       self._start_syspoller()

        # Cleanup locks
        locks.cleanup()

        # Run the actual test run.  Currently this doesn't do much interesting stuff,
        # but eventually it will start clients and report on statistics.  We need
        # some way later to generalize this, so that actual testing logic (such as
        # parametrization of clients) can be separated from the mechanics of the
        # testing.

        tr = BasicConnectionSetupTestRunner()
        tr.run_test(opts)
        
        sys.exit(0)

if __name__ == '__main__':
    tc = TestClient()
    tc.main()
