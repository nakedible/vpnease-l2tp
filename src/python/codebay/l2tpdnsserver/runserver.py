
import os, sys, optparse, textwrap

from twisted.internet import reactor

from codebay.l2tpdnsserver import dnsmaster

_example_config = textwrap.dedent("""\
<?xml version="1.0"?>
<config>
    <!--
      Configuration file for VPNease monitoring DNS server

      Please see support documents at http://www.vpnease.com/ for more
      information about how to set up DNS servers for the VPNease high
      availability configuration.

      Note: this configuration file should be placed in:

          /etc/vpnease-dns-server.xml
          
      If the configuration is changed, the server must be restarted by
      running:

          $ /etc/init.d/vpnease-dns-server restart

      See www.vpnease.com for legal information.
    -->

    <!-- *************************************************************** -->

    <!--
      Information about delegated domain
    -->
    <delegated-domain>
        <name>vpn.example.com</name>    <!-- XXX -->
        <ns1>172.16.0.1</ns1>           <!-- XXX -->
        <ns2>172.16.0.2</ns2>           <!-- XXX -->
        <mail>10.0.0.1</mail>           <!-- XXX -->
    </delegated-domain>
             
    <!-- *************************************************************** -->

    <!--
      Subdomains, one subdomain for each server cluster

      Each subdomain defines a server cluster which will be addressed
      using a domain name (e.g. cluster1 -> cluster1.vpn.example.com).
      The cluster domain name will map in a round robin fashion to the
      currently active servers.  This domain name should be configured
      to VPN clients.

      Individual servers are also available in the DNS configuration
      for convenience, using domain names of the format:

          server<n>.<clustername>

      for instance, third server of 'cluster2' would be:

          server3.cluster2.vpn.example.com
    -->

    <subdomain>
        <!-- nameless subdomain controls top level name resolution, e.g. vpn.example.com -->
        <name></name>                   <!-- vpn.example.com -->
        <server>192.168.100.1</server>  <!-- available as: server1.vpn.example.com -->
        <server>192.168.100.2</server>  <!-- available as: server2.vpn.example.com -->
    </subdomain>
    
    <subdomain>
        <!-- subdomain, e.g. cluster1.vpn.example.com -->
        <name>cluster1</name>           <!-- cluster1.vpn.example.com -->
        <server>192.168.0.1</server>    <!-- available as: server1.cluster1.vpn.example.com -->
        <server>192.168.0.2</server>    <!-- available as: server2.cluster1.vpn.example.com -->
     </subdomain>

    <subdomain>
        <!-- subdomain, e.g. cluster2.vpn.example.com -->
        <name>cluster2</name>           <!-- cluster2.vpn.example.com -->
        <server>192.168.1.1</server>    <!-- available as: server1.cluster2.vpn.example.com -->
        <server>192.168.1.2</server>    <!-- available as: server2.cluster2.vpn.example.com -->
        <server>192.168.1.3</server>    <!-- available as: server3.cluster2.vpn.example.com -->
    </subdomain>
</config>
""")

def _create_example_config():
    return _example_config
    
def _run_server():
    # options
    opt = optparse.OptionParser(usage='%prog', version='%prog')
    opt.add_option('-c', '--config', action="store", type="string", dest="config")
    opts, args = opt.parse_args(sys.argv[1:])

    # spit out example config
    cfgname = '/tmp/example-config.xml'
    if not os.path.exists(cfgname):
        f = open(cfgname, 'wb')
        f.write(_create_example_config())
        f.close()

    # start dnsmaster
    cfgname = '/etc/vpnease-dns-server.xml'
    dm = dnsmaster.DnsMaster(cfgname)
    dm.start()
    
    # run reactor until it exits
    reactor.run()

if __name__ == '__main__':
    _run_server()
