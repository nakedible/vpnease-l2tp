"""License control functionality.

This is a collection of functions relevant for monitoring and
controlling licensing, and for "reconciling" system state with
"license-approved" state.

The basic license control model consists of two basic functions:

   (1) Computing the "authoritative" number of "concurrent connections"
       at any given time

   (2) Limiting access to concurrent connections beyond the license
       allowed maximum

License control (i.e., (2)) only occurs during connection setup in
the current implementation (in pppscripts.py).  If a connection forms
correctly, it will not be "revoked" even if it was incorrectly formed
because of inaccurate counting of concurrent connections.

Computing concurrent connections
--------------------------------

The most reliable way to compute the number of concurrent connections
is the number of PPP devices up at any certain time.  This number is
slightly inaccurate because PPP connections may hang if a connection
dies in an awkward manner (because of a failure in IPsec, L2TP, or
PPP layer).

PPP LCP echo timeouts eventually cause removal of hanging PPP devices,
assuming that PPP LCP echos have been configured and the total timeout
is reasonable (e.g. 5x1 minute), and that pppd itself has not hanged
too badly.  If this happens, only a reboot or killing the pppd in
question will remove the device.

The approach to compute the number of concurrent connections is
three-fold:

First, the RDF status of PPP devices is kept as up-to-date as
possible through PPP ip-{preup,up,down} scripts.  In principle,
if nothing fails, the status of all PPP devices is known.  License
decisions are done based on the RDF status information available
at the time of connection establishment.

Second, to guard against inconsistencies between system state and
RDF state, the difference between the two is reconciled periodically.
Devices without corresponding RDF status are eliminated, and RDF
status without corresponding system state is also eliminated.

Third, to guard against the off-chance that some connection
becomes stuck but seems to be alive (e.g. pppd and device are
both up), we detect fully inactive connections based on device
rx/tx counters.  If there hasn't been any traffic in *both* directions
in the device in the last LICENSE_PPP_IGNORE_IDLE_INTERVAL seconds,
the device is not considered to be alive.  It is then flagged as
'inactive', and ignored in license enforcement.  This check is
done periodically.  Periodic reboots ultimately remove hanging
devices and daemons.

Final notes:

  - A leeway of LICENSE_CONNECTION_LEEWAY percents (0.05 = 5%, round
    up) on top of the limit specified by the current license is
    allowed for connections before they are considered to violate the
    license.

  - Connection counts are computed separately for two categories
    of traffic:
     
       1. Normal remote access users
       3. Site-to-site connections

    Each category has its own computation and own leeway, so they
    don't intefere.

Limiting access for connections beyond license maximum
------------------------------------------------------

Because we don't want to make the l2tp daemon or pppd enforce license
limits, we have little control over connection setup before PPP scripts
(/etc/ppp/ip-{pre-up, up, down}) are executed.  At that time, the
user has already been authenticated and the client software is almost
finished.  We cannot abort the connection at this stage without a
bad use case: connections just mysteriously fail to form.  Instead,
we'd ideally let the user know that a license violation has occurred.

This use case is currently achieved by allowing a PPP connection to
form regardless of license violations.  Instead, if the current number
of concurrent connections exceeds license limits, we setup all new
connections in "restricted" state.

Restricted connections are not allowed to route traffic beyond the
L2TP gateway (this is achieved using ppp-device-specific firewall
rules).  HTTP connection attempts are automatically redirected to a
web page which informs the client of a license limit violation, and
any other relevant information.  DNS and WINS resolutions are allowed
to ensure user can fetch the web page.  Other connections are REJECTed.

See pppscripts.py for more information on how restrictions are
actually implemented.
"""
__docformat__ = 'epytext en'

import datetime, math

from codebay.common import logger
from codebay.common import rdf
from codebay.l2tpserver import constants
from codebay.l2tpserver import runcommand
from codebay.l2tpserver.rdfconfig import ns, ns_ui
from codebay.l2tpserver import helpers
from codebay.l2tpserver import interfacehelper
from codebay.l2tpserver import db

run_command = runcommand.run_command
_log = logger.get('l2tpserver.licensemanager')

SYSNUKE_FAILURE_LIMIT = 3
RDFNUKE_FAILURE_LIMIT = 3

# ----------------------------------------------------------------------------

def _wrap_check(old_value, new_value):
    """Handle 32-bit counter wrap in a heuristic manner.

    Old value is 'wrap corrected' big integer, while new value is assumed to be
    a (modulo calculated) 32-bit integer.
    """
    WRAP_MAGIC_LIMIT = 2*1024*1024*1024

    if new_value > 2**32L:
        # should not happen
        _log.warning('new value is not 32-bit, ignoring')
        return new_value

    new_32bit = (new_value) % (2**32L)
    old_32bit = (old_value) % (2**32L)

    diff = new_32bit - old_32bit
    if diff >= 0:
        # accept diff as is
        pass
    else:
        # if diff is sufficiently negative, consider this a wrap
        # (why not accept small negative diffs as wrapping?)
        if (-diff) >= WRAP_MAGIC_LIMIT:
            diff += 2**32L
        else:
            # accept diff as is
            pass                

    return old_value + diff

class LicenseMonitor:
    """License monitoring functionality.

    LicenseMonitor provides functionality for making license decisions and
    providing license-related measurement data (such as authoritative number
    of active concurrenct connections).  License decisions are done primarily
    based on data available from current RDF status tree.

    LicenseMonitor also reconciles the differences between system and RDF
    state.  It also tracks the 'liveness' of devices, updating this information
    to PPP device state (in RDF status tree).

    A device is considered to have been last alive at min(rxtime, txtime),
    i.e., only one counter has changed since.   (This means that if packets
    are only received and never sent, or vice versa, the device will
    eventually go stale.)
    """

    def __init__(self):
        """Constructor."""
        self._sysnuke_failures = {}   # devname -> failure count
        self._rdfnuke_failures = {}   # device rdf node -> failure count
    
    def _nuke_system_device(self, devname):
        # NOTE: Taking the device down does not cause PPP or L2TP termination
        # in any reasonable time.  However: (1) user traffic is stopped by this,
        # and (2) this device doesn't count toward licenses anyway.  If the user
        # disconnects the connection, the device will go away normally.
        #
        # We could attempt to kill the pppd by looking at ps axwuf|grep pppd;
        # the device name is on the command line, yielding the pid.  This
        # seems too unreliable, though.  We could also attempt to kill the
        # openl2tp session by looking at the device name, and deducing the
        # tunnel and session IDs; openl2tp tunnels and sessions can then be
        # identified using these.
        #
        # This may not be robust with respect to pppox and pppol2tp kernel
        # modules.

        from codebay.l2tpserver import pppscripts
        pppscripts.nuke_ppp_device(devname)

    def _nuke_rdf_device(self, devnode):
        from codebay.l2tpserver import pppscripts
        devname = devnode.getS(ns.deviceName, rdf.String)
        pppscripts.nuke_ppp_device(devname)

    def _is_dev_alive(self, dev, now):
        """Determine whether a particular device (e.g. 'ppp0') is 'alive'.

        Liveness here means that traffic has passed both ways through the device
        within a certain period of time.  This concept of liveness is artificial
        and related to the license model (see module description).  The intent
        is to account for dead devices in some way.
        """

        # Estimate device age.  Note that 'delta' (= age) is always less than
        # the true device age because there is some time between measurements.
        # This error is on the side of caution: the device's age is *at least*
        # delta, but may be more (up to the sampling interval).

        rxtime = dev.getS(ns.rxLastChange, rdf.Datetime)
        rxbytes = dev.getS(ns.rxBytesCounter, rdf.Integer)
        rxpackets = dev.getS(ns.rxPacketsCounter, rdf.Integer)
        txtime = dev.getS(ns.txLastChange, rdf.Datetime)
        txbytes = dev.getS(ns.txBytesCounter, rdf.Integer)
        txpackets = dev.getS(ns.txPacketsCounter, rdf.Integer)

        devbothchanged = min(rxtime, txtime)
        delta = now - devbothchanged

        _log.debug('device %s delta is %s' % (dev.getS(ns.deviceName, rdf.String), delta))

        if delta > datetime.timedelta(seconds=constants.LICENSE_PPP_IGNORE_IDLE_INTERVAL):
            return False

        return True

    def _count_devices(self, filterfunc):
        """Count devices from RDF state matching a certain filter."""

        res = 0
        for d in helpers.get_ppp_devices():
            try:
                if filterfunc(d):
                    res += 1
            except:
                _log.exception('_count_devices: filterfunc failed')

        return res

    def _add_leeway(self, count):
        tmp = float(count)
        tmp = tmp * (1.0 + constants.LICENSE_CONNECTION_LEEWAY)   # XXX: shared across conn types
        return int(math.ceil(tmp))

    def _build_rdf_devmap(self, rdfdevs):
        rdfdevmap = {}
        for d in rdfdevs:
            try:
                devname = d.getS(ns.deviceName, rdf.String)
                rdfdevmap[devname] = d
            except:
                _log.exception('failed in constructing devmap for %s' % d)
        _log.debug('rdf devmap: %s' % rdfdevmap)
        return rdfdevmap

    def _reconcile_system_vs_rdf(self, rdfdevmap, ifaces, pub_if_name, priv_if_name):
        sysdevs = {}
        sysnuke = {}
        pub_di, priv_di = None, None
        for d in ifaces.get_interface_list():
            # snatch pub and priv devices first
            if d.devname == pub_if_name:
                pub_di = d
                continue
            if d.devname == priv_if_name:
                priv_di = d
                continue

            # filter out non-ppp devices at this point
            if not d.is_l2tp_ppp_device():
                continue

            # reconcile
            if not rdfdevmap.has_key(d.devname):
                _log.warning('reconcile: device %s exists in system but not in rdf, adding to nuke list' % d.devname)
                sysnuke[d.devname] = 1
                # XXX: shouldn't we skip adding this to sysdevs after we nuke it?

            sysdevs[d.devname] = d

        _log.debug('sysdevs: %s' % sysdevs)

        # update failure counts for system devices (increase for failed ones,
        # clear for non-failed ones)
        _log.debug('sysnuke: %s' % sysnuke)
        _log.debug('_sysnuke_failures (before): %s' % self._sysnuke_failures)
        for k in sysnuke.keys():
            if self._sysnuke_failures.has_key(k):
                sysnuke[k] += self._sysnuke_failures[k]
            else:
                pass
        for k in self._sysnuke_failures.keys():
            if not sysnuke.has_key(k):
                _log.info('device %s had a failure count (%d) but was cleared from sysnuke list' % (k, self._sysnuke_failures[k]))
        self._sysnuke_failures = sysnuke
        _log.debug('_sysnuke_failures (after): %s' % self._sysnuke_failures)
        
        # debugging
        for k in self._sysnuke_failures.keys():
            _log.info('sysnuke failures for device %s: %d' % (k, self._sysnuke_failures[k]))

        return sysdevs, pub_di, priv_di

    def _reconcile_rdf_vs_system(self, rdfdevs, sysdevs):
        rdfnuke = {}
        for d in rdfdevs:
            devname = d.getS(ns.deviceName, rdf.String)

            if not sysdevs.has_key(devname):
                _log.warning('reconcile: rdf device %s (%s) exists in rdf, but not in system, adding to nuke list' % (d, devname))
                rdfnuke[d] = 1

        # update failure counts for rdf devices (increase for failed ones,
        # clear for non-failed ones)
        _log.debug('rdfnuke: %s' % rdfnuke)
        _log.debug('_rdfnuke_failures (before): %s' % self._rdfnuke_failures)
        for k in rdfnuke.keys():
            if self._rdfnuke_failures.has_key(k):
                rdfnuke[k] += self._rdfnuke_failures[k]
            else:
                pass
        for k in self._rdfnuke_failures.keys():
            if not rdfnuke.has_key(k):
                _log.info('rdf device %s had a failure count (%d) but was cleared from rdfnuke list' % (k, self._rdfnuke_failures[k]))
        self._rdfnuke_failures = rdfnuke
        _log.debug('_rdfnuke_failures (after): %s' % self._rdfnuke_failures)

        # debugging
        for k in self._rdfnuke_failures.keys():
            try:
                devname = k.getS(ns.deviceName, rdf.String)
            except:
                devname = None
            _log.info('rdfnuke failures for device %s (%s): %d' % (k, devname, self._rdfnuke_failures[k]))

    def _update_rxtx_etc(self, now, rdfdevs, sysdevs):
        for dev in rdfdevs:
            try:
                devname = dev.getS(ns.deviceName, rdf.String)
                orxtime = dev.getS(ns.rxLastChange, rdf.Datetime)
                orxbytes = dev.getS(ns.rxBytesCounter, rdf.Integer)
                orxpackets = dev.getS(ns.rxPacketsCounter, rdf.Integer)
                otxtime = dev.getS(ns.txLastChange, rdf.Datetime)
                otxbytes = dev.getS(ns.txBytesCounter, rdf.Integer)
                otxpackets = dev.getS(ns.txPacketsCounter, rdf.Integer)

                # Here we assume that packet counters and byte counters always
                # change at the same time, which is a pretty safe assumption

                if not sysdevs.has_key(devname):
                    # If reconcile detected discrepancies but hasn't fixed them yet
                    # (nuke counter not high enough), this may happen; just ignore
                    _log.debug('device %s not in sysdevs, ignoring' % devname)
                    continue
                
                d = sysdevs[devname]  # old dict
                if orxbytes == d.rxbytes:   # no change, do not update timestamp
                    nrxtime, nrxbytes, nrxpackets = orxtime, d.rxbytes, d.rxpackets
                else:
                    nrxtime, nrxbytes, nrxpackets = now, d.rxbytes, d.rxpackets

                if otxbytes == d.txbytes:   # no change, do not update timestamp
                    ntxtime, ntxbytes, ntxpackets = otxtime, d.txbytes, d.txpackets
                else:
                    ntxtime, ntxbytes, ntxpackets = now, d.txbytes, d.txpackets

                # handle 4GiB wrapping in counters
                nrxbytes = _wrap_check(orxbytes, nrxbytes)
                nrxpackets = _wrap_check(orxpackets, nrxpackets)
                ntxbytes = _wrap_check(otxbytes, ntxbytes)
                ntxpackets = _wrap_check(otxpackets, ntxpackets)
                
                dev.setS(ns.rxLastChange, rdf.Datetime, nrxtime)
                dev.setS(ns.rxBytesCounter, rdf.Integer, nrxbytes)
                dev.setS(ns.rxPacketsCounter, rdf.Integer, nrxpackets)
                dev.setS(ns.txLastChange, rdf.Datetime, ntxtime)
                dev.setS(ns.txBytesCounter, rdf.Integer, ntxbytes)
                dev.setS(ns.txPacketsCounter, rdf.Integer, ntxpackets)

                rx_time = nrxtime - orxtime
                rx_secs = float(rx_time.seconds) + float(rx_time.microseconds / 1000000.0)
                if rx_secs > 0.0:
                    rx_rate = float(nrxbytes - orxbytes) / rx_secs
                else:
                    rx_rate = 0.0
                if rx_rate > dev.getS(ns.rxRateMaximum, rdf.Float):
                    dev.setS(ns.rxRateMaximum, rdf.Float, rx_rate)
                dev.setS(ns.rxRateCurrent, rdf.Float, rx_rate)
                         
                tx_time = ntxtime - otxtime
                tx_secs = float(tx_time.seconds) + float(tx_time.microseconds / 1000000.0)
                if tx_secs > 0.0:
                    tx_rate = float(ntxbytes - otxbytes) / tx_secs
                else:
                    tx_rate = 0.0
                if tx_rate > dev.getS(ns.txRateMaximum, rdf.Float):
                    dev.setS(ns.txRateMaximum, rdf.Float, tx_rate)
                dev.setS(ns.txRateCurrent, rdf.Float, tx_rate)

                if d.mtu is not None:
                    dev.setS(ns.mtu, rdf.Integer, d.mtu)

            except:
                _log.exception('failed up to update device rx/tx')

    def _update_liveness_status(self, now, rdfdevs):
        for d in rdfdevs:
            devname = d.getS(ns.deviceName, rdf.String)
            old_live = d.getS(ns.deviceActive, rdf.Boolean)
            new_live = self._is_dev_alive(d, now)
            d.setS(ns.deviceActive, rdf.Boolean, new_live)

            if old_live != new_live:
                if new_live:
                    _log.info('device %s became active' % devname)
                else:
                    _log.info('device %s became inactive' % devname)

    def _update_public_private_ifaces(self, now, ifaces, pub_di, priv_di, first_time):
        def _update_iface(di, st):
            orxtime = st.getS(ns.rxLastChange, rdf.Datetime)
            nrxtime = now
            st.setS(ns.rxLastChange, rdf.Datetime, nrxtime)

            otxtime = st.getS(ns.txLastChange, rdf.Datetime)
            ntxtime = now
            st.setS(ns.txLastChange, rdf.Datetime, ntxtime)

            orxbytes = st.getS(ns.rxBytesCounter, rdf.Integer)
            nrxbytes = di.rxbytes
            nrxbytes = _wrap_check(orxbytes, nrxbytes)  # handle 4GiB wrap
            st.setS(ns.rxBytesCounter, rdf.Integer, nrxbytes)

            otxbytes = st.getS(ns.txBytesCounter, rdf.Integer)
            ntxbytes = di.txbytes
            ntxbytes = _wrap_check(otxbytes, ntxbytes)  # handle 4GiB wrap
            st.setS(ns.txBytesCounter, rdf.Integer, ntxbytes)

            orxpackets = st.getS(ns.rxPacketsCounter, rdf.Integer)
            nrxpackets = di.rxpackets
            st.setS(ns.rxPacketsCounter, rdf.Integer, nrxpackets)

            otxpackets = st.getS(ns.txPacketsCounter, rdf.Integer)
            ntxpackets = di.txpackets
            st.setS(ns.txPacketsCounter, rdf.Integer, ntxpackets)

            if first_time:
                st.setS(ns.rxRateCurrent, rdf.Float, 0.0)
                st.setS(ns.rxRateMaximum, rdf.Float, 0.0)
                st.setS(ns.txRateCurrent, rdf.Float, 0.0)
                st.setS(ns.txRateMaximum, rdf.Float, 0.0)
            else:
                rx_time = nrxtime - orxtime
                rx_secs = float(rx_time.seconds) + float(rx_time.microseconds / 1000000.0)
                if rx_secs > 0.0:
                    rx_rate = float(nrxbytes - orxbytes) / rx_secs
                else:
                    rx_rate = 0.0
                if rx_rate > st.getS(ns.rxRateMaximum, rdf.Float):
                    st.setS(ns.rxRateMaximum, rdf.Float, rx_rate)
                st.setS(ns.rxRateCurrent, rdf.Float, rx_rate)

                tx_time = ntxtime - otxtime
                tx_secs = float(tx_time.seconds) + float(tx_time.microseconds / 1000000.0)
                if tx_secs > 0.0:
                    tx_rate = float(ntxbytes - otxbytes) / tx_secs
                else:
                    tx_rate = 0.0
                if tx_rate > st.getS(ns.txRateMaximum, rdf.Float):
                    st.setS(ns.txRateMaximum, rdf.Float, tx_rate)
                st.setS(ns.txRateCurrent, rdf.Float, tx_rate)

            # NB: link and IP info are updated on every round; this benefits
            # very little but also costs very little...

            # update link info
            st.setS(ns.mtu, rdf.Integer, di.mtu)
            st.setS(ns.macAddress, rdf.String, di.mac)
            
            # update ip level info
            iface = ifaces.get_interface_by_name(di.devname)
            addrsub = iface.get_current_ipv4_address_info()
            if addrsub is None:
                _log.info('could not get address of interface %s, ignoring' % di.devname)
            else:
                st.setS(ns.ipAddress, rdf.IPv4AddressSubnet, addrsub)

        if pub_di is not None:
            pub_if_st = helpers.get_status().getS(ns.publicInterface, rdf.Type(ns.NetworkInterface))
            _update_iface(pub_di, pub_if_st)

        if priv_di is not None:
            priv_if_st = helpers.get_status().getS(ns.privateInterface, rdf.Type(ns.NetworkInterface))
            _update_iface(priv_di, priv_if_st)

    @db.transact()
    def reconcile_system_and_rdf_state(self, first_time=False):
        """Reconcile system and RDF states.

        Checks system device list and compares it against RDF device information.
        Extra PPP devices without RDF book-keeping information are terminated.
        Devices present in RDF but not in the system are also removed from RDF.
        After calling this function, the system and RDF should be reasonably
        synchronized.

        This function also detects and updates the 'liveness' of each PPP device.
        Devices which are not live are not taken into account in license computations,
        thus making their detection important.

        The function also updates global public/private interface rx/tx counters,
        rates, etc.

        This function should be periodically, with an interval of 1-10 minutes or so.
        """

        #
        #  XXX: If status is incomplete for some reason, this will now
        #  spout exceptions.  The code should check whether checking and
        #  updating e.g. public interface status is useful at this point.
        #
        
        (pub_if, pub_if_name), (priv_if, priv_if_name) = helpers.get_ifaces(helpers.get_config())

        # start timestamp
        now = datetime.datetime.utcnow()
        
        # get device info from system (ip command)
        _log.debug('reconcile: getting system info')
        ifaces = interfacehelper.get_interfaces()

        # build devname->node dict
        _log.debug('reconcile: build devname->rdf dev dict')
        rdfdevs = helpers.get_ppp_devices()
        rdfdevmap = self._build_rdf_devmap(rdfdevs)
        
        # reconcile devices, pass 1: system vs rdf  [collect sysdevs dict at the same time]
        _log.debug('reconcile: pass 1, system vs rdf')
        sysdevs, pub_di, priv_di = self._reconcile_system_vs_rdf(rdfdevmap, ifaces, pub_if_name, priv_if_name)

        # do sysnukes for devices exceeding threshold
        for k in self._sysnuke_failures.keys():
            if self._sysnuke_failures[k] >= SYSNUKE_FAILURE_LIMIT:
                try:
                    _log.warning('sysnuke failure count for device %s too high, nuking' % k)
                    self._nuke_system_device(k)
                    del self._sysnuke_failures[k]
                except:
                    _log.exception('sysnuke failed')
                
        # reconcile devices, pass 2: rdf vs system
        _log.debug('reconcile: pass 2, rdf vs system')
        self._reconcile_rdf_vs_system(rdfdevs, sysdevs)

        # do rdfnukes for devices exceeding threshold
        for k in self._rdfnuke_failures.keys():  # key = rdf node of type PppDevice
            if self._rdfnuke_failures[k] >= RDFNUKE_FAILURE_LIMIT:
                try:
                    if k.hasS(ns.deviceName):
                        devname = k.getS(ns.deviceName, rdf.String)
                    else:
                        devname = '<unknown devname>'
                    _log.warning('rdfnuke failure count for device %s (%s) too high, nuking' % (k, devname))
                    self._nuke_rdf_device(k)
                    del self._rdfnuke_failures[k]
                except:
                    _log.exception('failed during reconcile, skipping device')
            # NB: device will be left in _rdfnuke_failures, and be removed next time

        # update rx/tx counters, transfer rates, etc
        # (reget devs because we may have nuked something)
        _log.debug('reconcile: updating rx/tx counters')
        rdfdevs = helpers.get_ppp_devices()
        self._update_rxtx_etc(now, rdfdevs, sysdevs)

        # update device liveness status
        _log.debug('reconcile: updating liveness status')
        rdfdevs = helpers.get_ppp_devices()
        self._update_liveness_status(now, rdfdevs)

        # update public/private interface status
        _log.debug('reconcile: updating public and/or private interface status')
        self._update_public_private_ifaces(now, ifaces, pub_di, priv_di, first_time)
            
    def check_license_validity(self):
        """Check that license is valid at this time.
        
        License validity is only checked when the connection is being formed.
        If the license expires after that, connections are not severed.
        Note that validity here is a limited period, even for continuous
        subscriptions.  The server is expected to reidentify periodically to
        extend the license validity time.
        """

        try:
            licinfo = helpers.get_license_info()
            val_start = licinfo.getS(ns_ui.validityStart, rdf.Datetime)
            val_end = licinfo.getS(ns_ui.validityEnd, rdf.Datetime)
            now = datetime.datetime.utcnow()

            if (now >= val_start) and (now <= val_end):
                return True

            _log.warning('license is not valid: validity_start=%s, validity_end=%s, now=%s' % (val_start, val_end, now))
            return False
        except:
            _log.exception('cannot check license validity, assuming invalid')
            return False

        return False  # just in case
    
    def check_demo_license(self):
        """Check whether license is a demo license and return demo parameters if so."""

        try:
            licinfo = helpers.get_license_info()

            is_demo = licinfo.getS(ns_ui.isDemoLicense, rdf.Boolean)
            if not is_demo:
                return False, None, None
            else:
                demo_expiry = licinfo.getS(ns_ui.demoValidityEnd, rdf.Datetime)
                demo_left = demo_expiry - datetime.datetime.utcnow()
                if demo_left < datetime.timedelta(0, 0, 0):
                    demo_left = datetime.timedelta(0, 0, 0)
                return True, demo_expiry, demo_left
        except:
            _log.exception('cannot check demo license')

        return False, None, None
    
    def count_both_users(self):
        """Count both normal and site-to-site users at the same time.

        This is useful for e.g. Ajax code to minimize RDF impact.
        """

        licinfo = helpers.get_license_info()
        limit = licinfo.getS(ns_ui.maxNormalConnections, rdf.Integer)
        limit_leeway = self._add_leeway(limit)
        s2s_limit = licinfo.getS(ns_ui.maxSiteToSiteConnections, rdf.Integer)
        s2s_limit_leeway = self._add_leeway(s2s_limit)

        count, s2s_count = 0, 0
        for dev in helpers.get_ppp_devices():
            try:
                # XXX: we'd ideally want to ignore inactive devices, but that did not
                # seem reliable enough

                if dev.getS(ns.connectionType).hasType(ns.NormalUser):
                    if not dev.getS(ns.restrictedConnection, rdf.Boolean):
                        count += 1
                else:
                    # XXX: assume it is site-to-site, minimize rdf impact
                    if not dev.getS(ns.restrictedConnection, rdf.Boolean):
                        s2s_count += 1
            except:
                _log.exception('count_both_users: failed')

        return count, limit, limit_leeway, s2s_count, s2s_limit, s2s_limit_leeway
        
    def count_normal_users(self):
        """Count normal users.

        Return a triple of count, limit, limit-with-leeway.
        """

        count, limit, limit_leeway, s2s_count, s2s_limit, s2s_limit_leeway = self.count_both_users()
        return count, limit, limit_leeway

    def check_normal_user_access(self):
        """Check whether a new normal user connection is allowed at this time."""

        count, limit, limit_leeway = self.count_normal_users()
        res = count < limit_leeway
        _log.debug('check_normal_user_access (count=%s, limit_leeway=%s) -> %s' % (count, limit_leeway, res))
        return res

    def count_site_to_site_users(self):
        """Count site-to-site users.

        Return a triple of count, limit, limit-with-leeway.
        """

        count, limit, limit_leeway, s2s_count, s2s_limit, s2s_limit_leeway = self.count_both_users()
        return s2s_count, s2s_limit, s2s_limit_leeway

    def check_site_to_site_access(self):
        """Check whether a new site-to-site connection is allowed at this time.

        Note that for Q2/2008 release leeway was removed from this check.  This is
        now possible because of stricted pppd killing in ppp scripts.
        """

        count, limit, limit_leeway = self.count_site_to_site_users()
        res = count < limit   # NB: no leeway
        _log.debug('check_site_to_site_access (count=%s, limit=%s) -> %s' % (count, limit, res))
        return res

        
if __name__ == '__main__':
    lm = LicenseMonitor()
    lm.reconcile_system_and_rdf_state()
