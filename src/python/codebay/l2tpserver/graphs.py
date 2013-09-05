"""Graph data collection and manipulation.

Rrdtool is used to collect data and matplotlib to draw graphs.

All functionality here assumes that system time is UTC (GMT).  This means that
all date and time operations can be trusted to work correctly without too much
thought.  Also RRD data is always in UTC (GMT).  The only place where local
timezone may matter is graph drawing: labels in the graph should use local time
for Web UI use.

Note in particular that the code below is does *not* work correctly if system
timezone is not UTC (GMT)!

Using matplotlib in a non-GUI environment is not terribly well documented.
Basically you need to use a suitable backend (output) and to use savefig().
Suitable backends include "Agg" and "Cairo".  Also, you cannot import pylab;
it requires DISPLAY and fails without it.  Import matplotlib instead, with
some loss of API usability.

See:
  * http://matplotlib.sourceforge.net/backends.html

Other resources:
  * http://matplotlib.sourceforge.net/
  * http://www.scipy.org/Cookbook/Matplotlib/Using_MatPlotLib_in_a_CGI_script
  * http://www.scipy.org/Cookbook/Matplotlib/AdjustingImageSize
"""
__docformat__ = 'epytext en'

import os, time, datetime, re, tempfile

from codebay.common import logger
from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver import helpers
from codebay.l2tpserver import db
from codebay.l2tpserver.rdfconfig import ns, ns_ui

run_command = runcommand.run_command
_log = logger.get('l2tpserver.graphs')

_re_df_header = re.compile(r'^.*?Filesystem.*?$')
_re_df_line = re.compile(r'^\s*(.*?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)%\s+(.*?)\s*$')

_re_vmstat_hdr1 = re.compile(r'^procs.*$')
_re_vmstat_hdr2 = re.compile(r'^\s*r\s+b\s+swpd.*$')
_re_vmstat_line = re.compile(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$')

_re_cpuinfo_cpu = re.compile(r'^processor\s*:.*$')

_re_meminfo_memtotal = re.compile(r'^MemTotal:\s*(\d+)\s+kB.*?$')
_re_meminfo_memfree = re.compile(r'^MemFree:\s*(\d+)\s+kB.*?$')
_re_meminfo_buffers = re.compile(r'^Buffers:\s*(\d+)\s+kB.*?$')
_re_meminfo_cached = re.compile(r'^Cached:\s*(\d+)\s+kB.*?$')
_re_meminfo_swaptotal = re.compile(r'^SwapTotal:\s*(\d+)\s+kB.*?$')
_re_meminfo_swapfree = re.compile(r'^SwapFree:\s*(\d+)\s+kB.*?$')

class DataSource:
    def __init__(self, dsname, dstype='GAUGE', heartbeat='300', dsmin='0', dsmax='U'):
        self.dsname = dsname
        self.heartbeat = heartbeat
        self.dsmin = dsmin
        self.dsmax = dsmax
        self.dstype = dstype
        
    def dsStatement(self):
        return 'DS:%s:%s:%s:%s:%s' % (self.dsname, self.dstype, self.heartbeat, self.dsmin, self.dsmax)

class DataPoint:
    def __init__(self):
        pass
        
class Graphs:
    def __init__(self):
        self.filename = constants.L2TPSERVER_RRDFILE

        self.rrd_sources = [ DataSource('cpuload'),       # float
                             DataSource('cpuusage'),      # 0..100 %, float
                             DataSource('cpucount'),      # int
                             DataSource('disktotal'),     # fake megs
                             DataSource('diskavail'),     # fake megs
                             DataSource('memtotal'),      # kbytes
                             DataSource('memused'),       # kbytes
                             DataSource('swaptotal'),     # kbytes
                             DataSource('swapused'),      # kbytes
                             DataSource('netpubrx'),      # bytes/second
                             DataSource('netpubtx'),
                             DataSource('netprivrx'),
                             DataSource('netprivtx'),
                             DataSource('nusrcount'),     # int
                             DataSource('nusrrxtotal'),   # bytes/second
                             DataSource('nusrtxtotal'),
                             DataSource('nusrrxavg'),
                             DataSource('nusrtxavg'),
                             DataSource('nusrrxmax'),
                             DataSource('nusrtxmax'),
                             DataSource('susrcount'),     # int
                             DataSource('susrrxtotal'),   # bytes/second
                             DataSource('susrtxtotal'),
                             DataSource('susrrxavg'),
                             DataSource('susrtxavg'),
                             DataSource('susrrxmax'),
                             DataSource('susrtxmax') ]
        
    def create_rrd_files(self):
        step = 60

        # start of this 24h day (no tz known yet, in utc)
        start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - datetime.timedelta(1, 0, 0)
        start_epoch = int(time.mktime(start.timetuple()))

        rra1_steps, rra1_rows = 1, 24*60                       # 1 days, 1 minute resolution
        rra2_steps, rra2_rows = 5, (30*24*60)/5                # 30 days, 5 minute resolution
        rra3_steps, rra3_rows = 60, (365*24*60)/60             # 365 days, 1 hour resolution
        rra4_steps, rra4_rows = 24*60, (20*365*24*60)/(24*60)  # 20 years, 1 day resolution
        
        run_command([ constants.CMD_RRDTOOL,
                      'create', self.filename,
                      '--start', str(start_epoch),
                      '--step', str(step) ] +
                    map(lambda x: x.dsStatement(), self.rrd_sources) +
                    [ 'RRA:AVERAGE:0.5:%s:%s' % (rra1_steps, rra1_rows),
                      'RRA:AVERAGE:0.5:%s:%s' % (rra2_steps, rra2_rows),
                      'RRA:AVERAGE:0.5:%s:%s' % (rra3_steps, rra3_rows),
                      'RRA:AVERAGE:0.5:%s:%s' % (rra4_steps, rra4_rows) ] +
                    [ 'RRA:MAX:0.5:%s:%s' % (rra1_steps, rra1_rows),
                      'RRA:MAX:0.5:%s:%s' % (rra2_steps, rra2_rows),
                      'RRA:MAX:0.5:%s:%s' % (rra3_steps, rra3_rows),
                      'RRA:MAX:0.5:%s:%s' % (rra4_steps, rra4_rows) ],
                    retval=runcommand.FAIL)

    def fetch_rrd_data(self, start=None, end=None, resolution=5*60, cf='MAX'):
        """Fetch rrd data using rrdtool fetch for selected period.

        The result is a list of DataPoint objects, which contain all the data sources
        we have; data source values are floats or None (if nan).  The DataPoint object
        has all data sources directly accessible, as well as the special property
        'time', which is a datetime.datetime for the DataPoint measurement time.  You
        can thus access values as follows:

            d = ... # DataPoint
            print d.time
            print d.nusrcount

        Used by matplotlib drawing code to get graph input.
        """

        #
        #  XXX: resolution is useless unless start and end are rounded to its multiple.
        #  See man rrdfetch for discussion and examples.  Currently we just ignore
        #  resolution and get the finest detail available, wasting a bit of memory in
        #  the process.
        #

        if start is None:
            raise Exception('start is None')
        if end is None:
            raise Exception('end is None')
        start_str = str(int(time.mktime(start.timetuple())))  # must be int, not float
        end_str = str(int(time.mktime(end.timetuple())))      # must be int, not float
            
        [rv, stdout, stderr] = run_command([
            constants.CMD_RRDTOOL,
            'fetch', self.filename, cf,
            '--end', end_str,
            '--start', start_str
            ], retval=runcommand.FAIL)

        res = []
        for line in stdout.split('\n'):
            try:
                [timestamp, rest] = line.split(':')
                timestamp = timestamp.strip()
                rest = rest.strip()
                vals = rest.split(' ')
            except:
                # ignore; probably empty line
                continue
            
            d = DataPoint()
            try:
                setattr(d, 'time', datetime.datetime.fromtimestamp(float(timestamp)))
            except:
                setattr(d, 'time', None)

            for i, ds in enumerate(self.rrd_sources):
                val = None
                if vals[i] == 'nan':
                    val = None
                else:
                    try:
                        val = float(vals[i])
                    except ValueError, e:
                        _log.exception('failed to parse data source value: ds=%s, val=%s' % (ds.dsname, vals[i]))
                        val = None
                        
                setattr(d, ds.dsname, val)
            res.append(d)

        return res
    
    # --------------------------------------------------------------------------

    @db.transact()
    def measure_and_update(self, update_rrd=True, update_rdf=True, quick=False):
        """Update all measurements.

        To minimize rrd load on the system, it is preferable to update all measurements
        in one go.  Further, if asynchronous updating is desired, separate rrd files
        need to be used anyway.

        We also update some statistics to a RDF status branch for statistics that are not
        protocol related (e.g. CPU usage).  This is so that the web UI can get access to
        this sort of information even when the runner is not active.  Admittedly this is
        not a very clean thing to do.
        """
    
        # It is important to run time-consuming system checks inside @untransact to
        # minimize the time RDF database access is locked.
        
        timestamp = datetime.datetime.utcnow()
        timeval = int(time.mktime(timestamp.timetuple()))  # XXX: round?

        # these values can be extracted regardless of l2tp-runner state
        cpu_load = self.measure_cpuload()
        if quick:
            # quick is used in boot to minimize postinit time
            cpu_usage = 0
        else:
            cpu_usage = self.measure_vmstat()
        cpu_count = self.measure_cpuinfo()
        disk_total, disk_avail = self.measure_diskstats()
        mem_total, mem_free, swap_total, swap_free = self.measure_meminfo()
        mem_used = mem_total - mem_free
        swap_used = swap_total - swap_free
        net_pubrx, net_pubtx, net_privrx, net_privtx = self.measure_network()

        def _nusr_filter(dev):
            if dev.hasS(ns.restrictedConnection) and dev.getS(ns.restrictedConnection, rdf.Boolean):
                return False
            # XXX: We'd like to ignore inactive devices, but this wasn't reliable enough
            #if dev.hasS(ns.deviceActive) and not dev.getS(ns.deviceActive, rdf.Boolean):
            #    return False
            if dev.hasS(ns.connectionType):
                if dev.getS(ns.connectionType).hasType(ns.NormalUser):
                    return True
            return False

        def _susr_filter(dev):
            if dev.hasS(ns.restrictedConnection) and dev.getS(ns.restrictedConnection, rdf.Boolean):
                return False
            # XXX: We'd like to ignore inactive devices, but this wasn't reliable enough
            #if dev.hasS(ns.deviceActive) and not dev.getS(ns.deviceActive, rdf.Boolean):
            #    return False
            if dev.hasS(ns.connectionType):
                conntype = dev.getS(ns.connectionType)
                if conntype.hasType(ns.SiteToSiteClient) or conntype.hasType(ns.SiteToSiteServer):
                    return True
            return False

        # user related data is only reliable if l2tp-runner is in state "running"
        try:
            st = helpers.get_status().getS(ns.state)
            if not st.hasType(ns.StateRunning):
                raise Exception('State not running')

            nusr_count, \
                        nusr_rxtotal, nusr_txtotal, \
                        nusr_rxavg, nusr_txavg, \
                        nusr_rxmax, nusr_txmax = self.measure_ppp_devs(_nusr_filter)

            susr_count, \
                        susr_rxtotal, susr_txtotal, \
                        susr_rxavg, susr_txavg, \
                        susr_rxmax, susr_txmax = self.measure_ppp_devs(_susr_filter)
        except:
            nusr_count, \
                        nusr_rxtotal, nusr_txtotal, \
                        nusr_rxavg, nusr_txavg, \
                        nusr_rxmax, nusr_txmax = ['U']*7
            
            susr_count, \
                        susr_rxtotal, susr_txtotal, \
                        susr_rxavg, susr_txavg, \
                        susr_rxmax, susr_txmax = ['U']*7

        vals = [ timeval,
                 cpu_load,
                 cpu_usage,
                 cpu_count,
                 disk_total,
                 disk_avail,
                 mem_total,
                 mem_used,
                 swap_total,
                 swap_used,
                 net_pubrx,
                 net_pubtx,
                 net_privrx,
                 net_privtx,
                 nusr_count,
                 nusr_rxtotal,
                 nusr_txtotal,
                 nusr_rxavg,
                 nusr_txavg,
                 nusr_rxmax,
                 nusr_txmax,
                 susr_count,
                 susr_rxtotal,
                 susr_txtotal,
                 susr_rxavg,
                 susr_txavg,
                 susr_rxmax,
                 susr_txmax ]
                 
        valstr = map(lambda x: str(x), vals)

        @db.untransact()
        def _run_rrd():
            # update rrd
            run_command([
                constants.CMD_RRDTOOL,
                'update', self.filename,
                ':'.join(valstr)
                ], retval=runcommand.FAIL)

        if update_rrd:
            _run_rrd()

        if update_rdf:
            st = helpers.get_global_status()
            st.setS(ns.cpuUsage, rdf.Float, float(cpu_usage))  # percents
            st.setS(ns.cpuCount, rdf.Integer, int(cpu_count))  # count
            st.setS(ns.diskUsage, rdf.Float, (float(disk_total) - float(disk_avail)) / float(disk_total) * 100.0)  # percents
            st.setS(ns.diskTotal, rdf.Float, float(disk_total))  # fake megs
            st.setS(ns.memoryUsage, rdf.Float, float(mem_used) / float(mem_total) * 100.0)  # percents
            st.setS(ns.memoryTotal, rdf.Integer, int(mem_total))  # kilobytes
            if swap_total > 0:
                st.setS(ns.swapUsage, rdf.Float, float(swap_used) / float(swap_total) * 100.0)  # percents
            else:
                st.setS(ns.swapUsage, rdf.Float, 0.0)
            st.setS(ns.swapTotal, rdf.Integer, int(swap_total))  # kilobytes
            
    @db.untransact()
    def measure_cpuload(self):
        f = open('/proc/loadavg')
        _log.debug('measure_cpuload: fd=%s' % f.fileno())
        d = f.read()
        f.close()
        return float(d.split(' ')[0])

    @db.untransact()
    def measure_diskstats(self):
        [rv, stdout, stderr] = run_command([constants.CMD_DF, '/'], retval=runcommand.FAIL)

        # Example output:
        #   Filesystem           1K-blocks      Used Available Use% Mounted on
        #   /dev/hda1            151873632  82896292  61262528  58% /

        total_fake_megabytes = None
        available_fake_megabytes = None
        
        for l in stdout.split('\n'):
            m = _re_df_header.match(l)
            if m is not None:
                continue

            m = _re_df_line.match(l)
            if m is not None:
                dev, blocks_1k, used, available, use_percent, mounted_on = m.groups()
                if mounted_on != '/':
                    continue

                total_fake_megabytes = float(blocks_1k) * 1024.0 / (1000.0 * 1000.0)
                available_fake_megabytes = float(available) * 1024.0 / (1000.0 * 1000.0)
                
        return total_fake_megabytes, available_fake_megabytes
    
    @db.untransact()
    def measure_vmstat(self):
        """Run vmstat, extracting system measurement information from its output.

        NOTE: To get 'snapshot' readings from vmstat one needs to wait for a few
        seconds to let vmstat gather useful data.  Thus, this call will block for
        a while, several seconds to get it.  Caller beware.
        """
        
        # Example output from: vmstat 3 2
        #
        # procs -----------memory---------- ---swap-- -----io---- -system-- ----cpu----
        #  r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa
        #  1  0 171028   5792  11784 371280    0    0     3     7    4    2  1  0 98  1
        #  0  0 171028   5792  11792 371272    0    0     0    92  124  100  0  0 99  1
        #
        # NB: First line is average since boot.  Second is from a 3-second measurement
        # interval.
        #
        # NB: vmstat also considers multiple processors.  For instance, with a ~100%
        # usage on a single CPU, idle will be reported at about ~50% on a dual CPU system.

        delay = 10   # reasonable averaging interval, cron interval is 60 seconds
        count = 2    # outputs one "average since boot" line and one measured over "delay"

        [rv, stdout, stderr] = run_command([constants.CMD_VMSTAT, str(delay), str(count)], retval=runcommand.FAIL)

        cpu_usage = None

        for l in stdout.split('\n'):
            m = _re_vmstat_hdr1.match(l)
            if m is not None:
                continue

            m = _re_vmstat_hdr2.match(l)
            if m is not None:
                continue
        
            # This will match multiple times; the last match is what we want
            m = _re_vmstat_line.match(l)
            if m is not None:
                t_r, t_b, t_swpd, t_free, t_buff, t_cache, t_si, t_so, t_bi, t_bo, t_in, t_cs, t_us, t_sy, t_id, t_wa = m.groups()

                cpu_usage = 100 - int(t_id)  # XXX: count 'io-wait' as idle? (currently this is good as is)

        # XXX: relevant memory statistics ??

        return cpu_usage
    
    @db.untransact()
    def measure_cpuinfo(self):
        # $ cat /proc/cpuinfo
        # processor       : 0
        # ...
        # processor       : 1
        # ...

        f = open('/proc/cpuinfo')
        _log.debug('measure_cpuinfo: fd=%s' % f.fileno())
        d = f.read()
        f.close()

        cpu_count = 0
        for l in d.split('\n'):
            m = _re_cpuinfo_cpu.match(l)
            if m is not None:
                cpu_count += 1

        return cpu_count

    @db.untransact()
    def measure_meminfo(self):
        # $ cat /proc/meminfo
        # MemTotal:       786576 kB
        # MemFree:          4984 kB
        # Buffers:        193512 kB
        # Cached:         127104 kB
        # SwapCached:     127232 kB
        # Active:         282852 kB
        # Inactive:       216496 kB
        # HighTotal:           0 kB
        # HighFree:            0 kB
        # LowTotal:       786576 kB
        # LowFree:          4984 kB
        # SwapTotal:     1992052 kB
        # SwapFree:      1732676 kB
        # Dirty:              48 kB
        # Writeback:           0 kB
        # Mapped:         200360 kB
        # Slab:           259900 kB
        # CommitLimit:   2385340 kB
        # Committed_AS:   498756 kB
        # PageTables:       2016 kB
        # VmallocTotal:   434168 kB
        # VmallocUsed:      4284 kB
        # VmallocChunk:   429656 kB
        #
        # memfree (for us) = MemFree + Buffers + Cached
        # swapfree (for us) = SwapFree
        #
        # SwapCached: http://kerneltrap.org/node/4097
        
        f = open('/proc/meminfo')
        _log.debug('measure_meminfo: fd=%s' % f.fileno())
        d = f.read()
        f.close()

        memtotal, memfree, buffers, cached, swaptotal, swapfree = None, None, None, None, None, None

        for l in d.split('\n'):
            m = _re_meminfo_memtotal.match(l)
            if m is not None:
                memtotal = long(m.group(1))
                continue
            
            m = _re_meminfo_memfree.match(l)
            if m is not None:
                memfree = long(m.group(1))
                continue

            m = _re_meminfo_buffers.match(l)
            if m is not None:
                buffers = long(m.group(1))
                continue

            m = _re_meminfo_cached.match(l)
            if m is not None:
                cached = long(m.group(1))
                continue

            m = _re_meminfo_swaptotal.match(l)
            if m is not None:
                swaptotal = long(m.group(1))
                continue

            m = _re_meminfo_swapfree.match(l)
            if m is not None:
                swapfree = long(m.group(1))
                continue

        return memtotal, memfree + buffers + cached, swaptotal, swapfree

    @db.transact()
    def measure_ppp_devs(self, filterfunc):
        devs = helpers.get_ppp_devices()

        fdevs = []
        for dev in devs:
            if filterfunc(dev):
                fdevs.append(dev)

        count = len(fdevs)
        rxtotal, txtotal = 0.0, 0.0
        rxmax, txmax = 0.0, 0.0
        for d in fdevs:
            rxrate = d.getS(ns.rxRateCurrent, rdf.Float)
            txrate = d.getS(ns.txRateCurrent, rdf.Float)
            rxtotal += rxrate
            txtotal += txrate
            if rxrate > rxmax:
                rxmax = rxrate
            if txrate > txmax:
                txmax = txrate
        
        if count > 0:
            return count, rxtotal, txtotal, rxtotal / count, txtotal / count, rxmax, txmax
        return count, rxtotal, txtotal, 'U', 'U', rxmax, txmax

    @db.transact()
    def measure_network(self):
        st = helpers.get_status()
        
        if st.hasS(ns.publicInterface):
            pub_if_st = st.getS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
            net_pubrx = pub_if_st.getS(ns.rxRateCurrent, rdf.Float)
            net_pubtx = pub_if_st.getS(ns.txRateCurrent, rdf.Float)
        else:
            net_pubrx, net_pubtx = 'U', 'U'

        if st.hasS(ns.privateInterface):
            priv_if_st = st.getS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
            net_privrx = priv_if_st.getS(ns.rxRateCurrent, rdf.Float)
            net_privtx = priv_if_st.getS(ns.txRateCurrent, rdf.Float)
        else:
            net_privrx, net_privtx = 'U', 'U'

        return net_pubrx, net_pubtx, net_privrx, net_privtx

    # --------------------------------------------------------------------------

    def draw_user_graph(self):
        """Draw Web UI user summary graph."""
        current = None

        @db.transact()
        def _func():
            try:
                from codebay.l2tpserver import licensemanager
                lm = licensemanager.LicenseMonitor()
                count, limit, limit_leeway = lm.count_normal_users()
                return float(count)
            except:
                _log.info('draw_user_graph(): cannot count normal users, probably caused by missing status tree in rdf')
                #_log.exception('cannot count normal users')
        current = _func()
            
        width = constants.USER_GRAPH_WIDTH
        height = constants.USER_GRAPH_HEIGHT

        return self._draw_weekly_graph_matplotlib(constants.RRDGRAPH_USER_COUNT, 'nusrcount', ns_ui.maxNormalConnections, current, width, height)

    def draw_sitetosite_graph(self):
        """Draw Web UI site-to-site summary graph."""
        current = None

        @db.transact()
        def _func():
            try:
                from codebay.l2tpserver import licensemanager
                lm = licensemanager.LicenseMonitor()
                count, limit, limit_leeway = lm.count_site_to_site_users()
                return float(count)
            except:
                _log.info('draw_sitetosite_graph(): cannot count site-to-site users, probably caused by missing status tree in rdf')
                #_log.exception('cannot count site-to-site users')
        current = _func()

        width = constants.SITETOSITE_GRAPH_WIDTH
        height = constants.SITETOSITE_GRAPH_HEIGHT

        return self._draw_weekly_graph_matplotlib(constants.RRDGRAPH_SITETOSITE_COUNT, 'susrcount', ns_ui.maxSiteToSiteConnections, current, width, height)

    # --------------------------------------------------------------------------

    # XXX: obsolete versions of user and s2s graphs

    def _draw_user_graph_rrdgraph(self):
        outname = constants.RRDGRAPH_USER_COUNT
        limit, limit_round = self._webui_get_round_limit(ns_ui.maxNormalConnections)
        r = DataSource('nusrcount')

        # CDEF RPN expressions cannot be e.g. 'mylimit=8' or 'mylimit=8,0,+', they *MUST*
        # contain a variable.  Hence we multiply a dummy variable by zero and add a constant.
        # We want to have mylimit as a CDEF, if it is later changed to be time-dependent.
        [rv, stdout, stderr ] = run_command([
            constants.CMD_RRDTOOL,
            'graph',
            outname,
            '--end', 'now',
            '--start', 'end-%ss' % (7*24*60*60),
            '--title', '%s' % 'Users',
            '--width', str(450),
            '--height', str(60),
            '--lower-limit', str(0),
            '--upper-limit', str(limit_round),
            'DEF:%s=%s:%s:MAX' % (r.dsname, self.filename, r.dsname),
            'CDEF:mylimit=%s,0,*,%d,+' % (r.dsname, limit),  # See above
            'LINE1:%s#888888' % r.dsname,
            'LINE1:%s#ff0000' % 'mylimit'
            ], retval=runcommand.FAIL)

    def _draw_sitetosite_graph_rrdgraph(self):
        outname = constants.RRDGRAPH_SITETOSITE_COUNT
        limit, limit_round = self._webui_get_round_limit(ns_ui.maxSiteToSiteConnections)
        r = DataSource('susrcount')

        # XXX: server connections? 'susrcount' datasource counts *BOTH* connections...

        [rv, stdout, stderr ] = run_command([
            constants.CMD_RRDTOOL,
            'graph',
            outname,
            '--end', 'now',
            '--start', 'end-%ss' % (7*24*60*60),
            '--title', '%s' % 'Site-to-Site Connections',
            '--width', str(450),
            '--height', str(60),
            '--lower-limit', str(0),
            '--upper-limit', str(limit_round),
            'DEF:%s=%s:%s:MAX' % (r.dsname, self.filename, r.dsname),
            'CDEF:mylimit=%s,0,*,%d,+' % (r.dsname, limit),  # See above
            'LINE1:%s#888888' % r.dsname,
            'LINE1:%s#ff0000' % 'mylimit'
            ], retval=runcommand.FAIL)

    # --------------------------------------------------------------------------

    # Debug graphs
    def draw_debug_graphs(self):
        """Draw debug graphs of all measures."""

        for ds in self.rrd_sources:
            for [period, period_name] in [ [60*60, 'hour'],
                                           [24*60*60, 'day'],
                                           [7*24*60*60, 'week'],
                                           [30*24*60*60, 'month'],
                                           [365*24*60*60, 'year'] ]:
                for [width, height, resolution_name] in [ [800, 400, 'low'],
                                                          [1600, 800, 'high'] ]:
                
                    outname = '/tmp/debug-graph-%s-%s-%s.png' % (ds.dsname, period_name, resolution_name)
                
                    [rv, stdout, stderr ] = run_command([
                        constants.CMD_RRDTOOL,
                        'graph',
                        outname,
                        '--end', 'now',
                        '--start', 'end-%ss' % period,
                        '--title', '%s' % outname,
                        '--width', str(width),
                        '--height', str(height),
                        '--lower-limit', str(0),
                        ##'--upper-limit', ...,
                        'DEF:%s=%s:%s:MAX' % (ds.dsname, self.filename, ds.dsname),
                        'LINE1:%s#000000' % ds.dsname
                        ])

    # --------------------------------------------------------------------------

    @db.transact()
    def _webui_get_round_limit(self, nsname):
        try:
            limit = helpers.get_license_info().getS(nsname, rdf.Integer)
        except:
            _log.exception('cannot get limit')
            limit = 0

        limit_round = (limit + 4) / 5 * 5  # round up to nearest 5
        if limit_round < 5:
            limit_round = 5

        return limit, limit_round
    
    def _convert_timestamps_to_local(self, timestamps):
        from codebay.l2tpserver.webui import uihelpers

        tmp = []
        for t in timestamps:
            if t is None:
                tmp.append(None)
            else:
                # make datetime naive again, works better with matplotlib.. don't ask
                loc = uihelpers.convert_datetime_to_local_datetime(t, os.environ['TZ'], output_naive=True)
                tmp.append(loc)
        return tmp

    def _round_values(self, data):
        tmp = []
        for i in data:
            if i is None:
                tmp.append(None)
            else:
                tmp.append(round(i))
        return tmp
    
    def _draw_weekly_graph_matplotlib(self, filename, dsname, rdfnode, current_count, width, height):
        from matplotlib.dates import date2num

        # fetch rrd data before setting TZ
        now = datetime.datetime.utcnow()
        rrd_data = self.fetch_rrd_data(start=now-datetime.timedelta(7, 0, 0), end=now)

        def _draw(fig):
            data = rrd_data
            
            # raw data
            xdata = [i.time for i in data]
            ydata = [getattr(i, dsname) for i in data]

            # fix zero length issue
            if len(ydata) == 0:
                xdata.append(datetime.datetime.utcnow())
                ydata.append(0.0)

            # convert user counts to even integers
            ydata = self._round_values(ydata)
            ydata_min = min(ydata)
            ydata_max = max(ydata)
            
            # convert UTC timestamps to admin's time (TZ is set at this point)
            xdata = self._convert_timestamps_to_local(xdata)
            xdata_min = min(xdata)
            xdata_max = max(xdata)
            
            # get x and y limits
            yax_min = 0
            lic_limit, yax_max = self._webui_get_round_limit(rdfnode)
            xax_min = date2num(xdata_min)
            xax_max = date2num(xdata_max)

            # generate staircase
            staircases = self._matplotlib_generate_staircases(xdata, ydata)
    
            # setup subplot
            ax = fig.add_subplot(111)

            # draw actual data using a set of filled staircases
            for [x, y] in staircases:
                p = ax.fill(date2num(x), y, "#ccddff", antialiased=True, linewidth=0.4)

            # draw current value as a dot if it exists ('cursor')
            # we use the actual rdf count instead of rrd, because rrd imposes some extra delay
            if current_count is not None and xdata[-1] is not None:
                # XXX: this line was disabled before initial release
                #_xdata = date2num([xdata[-1], xdata[-1] - datetime.timedelta(0, 5*3600, 0)])
                #_ydata = [float(current_count), float(current_count)]
                #ax.plot(_xdata, _ydata, '-', color='#440000', linewidth=3.0, antialiased=True)

                _xdata = date2num([xdata[-1]])
                _ydata = [float(current_count)]
                ax.plot(_xdata, _ydata, 'o', markerfacecolor='#ff0000', markeredgecolor='#000000', markeredgewidth=1.0, markersize=8.0, antialiased=True, alpha=0.5)

            # draw license limit using two data points
            ax.plot([xax_min, xax_max], [lic_limit, lic_limit], 'r-', antialiased=True, linewidth=0.5)

            # finalize by setting axes
            self._matplotlib_week_axis_setup(ax, xax_min, xax_max, yax_min, yax_max)

        self._matplotlib_wrapper(_draw, width=width, height=height, dpi=70, filename=filename)

    def _draw_sitetosite_graph_matplotlib(self):
        pass

    def _matplotlib_figure_setup(self, width, height, dpi):
        from matplotlib import figure
        
        # figure size calculation, goes through inches and DPI
        dpi = float(dpi)
        width_pix = float(width)
        height_pix = float(height)
        width_inch = width_pix / dpi
        height_inch = height_pix / dpi

        # create and configure figure
        fig = figure.Figure(figsize=(width_inch, height_inch))
        return fig

    def _matplotlib_week_axis_setup(self, ax, xmin, xmax, ymin, ymax):
        from matplotlib.dates import DayLocator, DateFormatter
        from matplotlib.artist import setp

        # X axis
        ax.set_xlim((xmin, xmax))
        ax.xaxis.set_major_locator(DayLocator())
        ax.xaxis.set_major_formatter(DateFormatter("%a"))
        ax.xaxis.grid(True, "major")  # XXX - linestyle...

        labels = ax.get_xticklabels()
        setp(labels, rotation=0, fontsize=9)
        for i in labels:
            i.set_horizontalalignment('left')

        # Y axis
        ax.set_ylim((ymin, ymax))
        yrange = range(ymin, ymax + 1)
        yticks = []
        ylabels = []

        # Y tick and label generation is a bit fussy - the intent here is to generate
        # a reasonable set of ticks and labels for various ymax values.  The logic
        # below works reasonably well for graph height ~100 pixels and ymax from 0 to
        # several thousand.

        tickstep = 5            # for large values, steps of 5 are odd (e.g. 35, 70, 105)
        if ymax > 50:
            tickstep = 10
        if ymax > 500:
            tickstep = 100
            
        tickinterval = (ymax + 9) / 10                              # roughly most 10 ticks per small image
        if tickinterval > 1:                                        # if step > 1, round up to nearest tickstep
            tickinterval = (tickinterval + tickstep - 1) / tickstep * tickstep
        if tickinterval <= 1:
            tickinterval = 1                                        # otherwise use step 1 (also handles zero div)

        labelinterval = (ymax + 2) / 3                                                    # roughly 3 labels per small image
        labelinterval = (labelinterval + tickstep - 1) / tickstep * tickstep              # round up to nearest tickstep
        labelinterval = (labelinterval + tickinterval - 1) / tickinterval * tickinterval  # must be a multiple of tick interval!
        if labelinterval <= 0:
            labelinterval = tickinterval                            # sanity
        if labelinterval <= 1:
            labelinterval = 1
            
        ymax_rounded = (ymax + labelinterval - 1) / labelinterval * labelinterval + tickinterval

        # compute actual tick positions and labels
        for i in range(ymin, ymax_rounded + 1, tickinterval):
            yticks.append(i)
            if (int(i) % labelinterval) == 0:
                ylabels.append(str(int(i)))
            else:
                ylabels.append('')
                
        ax.yaxis.set_ticks(yticks)
        ax.yaxis.set_ticklabels(ylabels)
        labels = ax.get_yticklabels()
        setp(labels, rotation=0, fontsize=9)

    def _matplotlib_generate_staircases(self, orig_xdata, orig_ydata):
        """Scan data for solid runs on non-None data, generating staircase data for each run.

        Returns a list of runs, with each run described by [x, y]; x is a list of x coords
        and y is a list of y coords.
        """

        # First, scan consecutive runs of non-None values (y)
        runs = []
        curr = None
        for i in xrange(len(orig_ydata)):
            if orig_ydata[i] is not None:
                if curr is None:
                    curr = []
                curr.append([orig_xdata[i], orig_ydata[i]])
            else:
                if curr is not None:
                    runs.append(curr)
                    curr = None
        if curr is not None:
            runs.append(curr)
            curr = None

        # Then, generate staircase list
        sclist = []
        for r in runs:   # r = [ [x1,y1], [x2,y2], ..., [xN,yN] ]
            x, y = [], []
            x.append(r[0][0])
            y.append(0)  # for filling
            otx, oty = None, None
            for [tx, ty] in r:
                if oty is not None:
                    x.append(tx)
                    y.append(oty)
                x.append(tx)
                y.append(ty)
                otx, oty = tx, ty
            x.append(r[-1][0])
            y.append(0)  # for filling
            sclist.append([x, y])

        return sclist

    def _matplotlib_wrapper(self, func, width=None, height=None, dpi=None, filename=None):
        old_environ = dict(os.environ)

        try:
            # matplotlib needs a writable home
            # XXX: should use /var/run/l2tpgw directory, but it may not be available yet.
            os.environ['HOME'] = '/tmp/'
            os.environ['LANG'] = 'POSIX'

            # try to setup timezone
            @db.transact()
            def _f():
                try:
                    return helpers.get_ui_config().getS(ns_ui.timezone, rdf.String)
                except:
                    _log.exception('cannot figure out timezone, using %s' % constants.DEFAULT_TIMEZONE)
                    return constants.DEFAULT_TIMEZONE
            tzname = _f()
            os.environ['TZ'] = tzname
            time.tzset()   # see import time; help(time.tzset)
            
            # Matplotlib initialization is very tricky; if you do this wrong, matplotlib
            # will try to import GTK stuff, which fails unless DISPLAY is set.  Trick is
            # to first say matplotlib.use() and then import the backend.  This prevents
            # the backend from importing crud; see __init__.py of matplotlib.backends.
            #
            # It is actually possible to use pylab functions; however, one must say
            # matplotlib.use('Agg') or other non-GUI backend before importing pylab.
            
            import matplotlib
            matplotlib.use("Agg")

            fig = self._matplotlib_figure_setup(width, height, dpi)
            from matplotlib.backends import backend_agg
            canvas = backend_agg.FigureCanvasAgg(fig)

            func(fig)

            # save to a temporary filename first to avoid "glitches"
            t = tempfile.mktemp(suffix='-graph.png')  # NB: file extension is critical to matplotlib
            fig.savefig(t, dpi=dpi)
            [rv, stdout, stderr] = run_command([constants.CMD_MV, t, filename], retval=runcommand.FAIL)

        except Exception, e:
            _log.exception('_matplotlib_wrapper: function call failed')

        os.environ = old_environ

