
from codebay.l2tpserver.webui import uihelpers

class SharedTexts:
    primary_dns_label = 'Primary DNS server IP address'
    secondary_dns_label = 'Secondary DNS server IP address'
    tcp_udp_select_options = [
        ('tcp', 'TCP'),
        ('udp', 'UDP')
        ]
    firewall_protocol_select_options = [
        ('any', 'Any'),
        ('tcp', 'TCP'),
        ('udp', 'UDP'),
        ('icmp', 'ICMP')
        ]
    firewall_protocol_action_options = [
        ('allow', 'Allow'),
        ('deny', 'Deny')
        ]


class NetworkConfigTexts:
    shared = SharedTexts()

    # Group caption
    network_group_caption = 'Network'
    
    # Interface count texts
    ifcount_label = 'Network setup'
    ifcount_options = [
        ('oneif', 'One network interface'),
        ('twoif', 'Two network interfaces')
        ]
    #ifcount_options_help = ''
    
    # Texts for both network connections
    ip_selection_label = 'IP address selection'
    ip_selection_options = [
        ('dhcp', 'Automatic (DHCP)'),
        ('static', 'Set IP address')
        ]
    ip_selection_options_help = ''
    if_label = 'Network interface'
    if_help = ''
    ip_label = 'Static IP address'
    ip_help = ''
    subnet_label = 'Subnet mask'
    subnet_help = ''
    default_gw_label = 'Default gateway IP address'
    default_gw_help = ''
    client_traffic_label = 'Client traffic handling' 
    client_traffic_options = [
        ('nat', 'Use NAT'),
        ('proxyarp', 'Use Proxy ARP'),
        ('none', 'Don\'t use NAT or Proxy ARP')
        ]

    # Internet connection texts
    ic_group_caption = 'Internet Connection'
    mtu_label = 'MTU'
    mtu_help = ''
    uplink_label = 'Uplink speed (Mbps)'
    uplink_help = ''
    
    # Private network connection texts
    pn_group_caption = 'Private Network Connection'
    
    
    # DNS servers texts
    dns_group_caption = 'DNS Servers'
    dns_select_label = 'DNS server information'
    dns_select_options = [
        ('use_dhcp_ic', 'Internet connection DHCP'),
        ('use_dhcp_pn', 'Private network connection DHCP'),
        ('set_manually', 'Set DNS servers')
        ]
#    dns_select_options_help = ''
    primary_dns_label = shared.primary_dns_label
    primary_dns_help = ''
    secondary_dns_label = shared.secondary_dns_label
    secondary_dns_help = ''

    # Email server group texts
    smtp_group_caption = 'Email Server'
    smtp_server_label = 'SMTP server address'
    smtp_server_help = ''

    # Dynamic dns texts
    ddns_group_caption = 'Dynamic DNS'
    ddns_providers_label = 'Provider'
    ddns_providers = [
        ('none', 'Dynamic DNS not in use'),
        ('dyndns', 'DynDNS dynamic (dyndns.com)'),
        ('dhs', 'DHS International (dhs.org)'),
        ('ods', 'Open Domain Server (ods.org)'),
        ('dyns', 'DyNS (dyns.cx)'),
        ]
    ddns_providers_help = ''
    ddns_username_label = 'Username'
    ddns_username_help = ''
    ddns_password_label = 'Password'
    ddns_password_help = ''
    ddns_hostname_label = 'Full hostname'
    ddns_hostname_help = ''
    ddns_address_label = 'Force address'
    ddns_address_help = ''
    
class RoutesTexts:
    shared = SharedTexts()
    routing_group_caption = 'Routes'
    
    # Routing shared texts
    routing_subnet = 'Subnet'
    routing_nw_label = 'Destination network'
    routing_nw_options = [
        ('internet', 'Internet connection'),
        ('private', 'Private network connection')
        ]
    routing_gw_select_options = [
        ('nw_default_gw', 'Use network connection default gateway'),
        ('manual_gw', 'Set gateway')
        ]
    routing_gw_select_label = 'Gateway selection'
    routing_gw_label = 'Gateway IP address'
    
    # Default route
    default_route_caption = 'Default Route'

    # Additional routes
    additional_routes_caption = 'Additional Routes'
    new_route_caption = 'Add Route'
    
    # Source routing (forced routing)
    source_routing_caption = 'Forced Routing'
    source_routing_select_label = 'Forced routing'
    source_routing_select_options = [
        ('on', 'On'),
        ('off', 'Off')
        ]
    # Prohibited services
    prohibited_caption = 'Prohibited Services'

    fw_protocol_select_options = shared.firewall_protocol_select_options
    fw_protocol_action_options = shared.firewall_protocol_action_options
    new_proh_protocol_select_label = 'Protocol'
    new_proh_port_label = 'Port'
    
class FirewallTexts:
    shared = SharedTexts()
    
    firewall_group_caption = 'Firewall'
    enable_routing_label = 'Enable simple firewall (routing through)'
    # New port forward
    port_forwards_group_caption = 'Port Forwarding'
    new_fw_protocol_options = shared.tcp_udp_select_options
    new_fw_protocol_label = 'Protocol'
    new_fw_port_in_label = 'Incoming port'
    new_fw_ip_out_label = 'Destination IP address'
    new_fw_port_out_label = 'Destination port'      
        
class ClientConnectionTexts: 
    shared = SharedTexts()
    
    cc_group_caption = 'VPN Connection Settings'
    client_dns_options_label = 'VPN client DNS servers'
    client_dns_options = [
        ('use_ic_dns', 'Use network connection DNS servers'),
        ('manual_dns', 'Set DNS servers')
        ]
    client_dns_options_help = ''
    server_address_label = 'VPN server domain name'
    server_address_help = ''
    psk_label = 'Pre-shared key'
    psk_help = ''
    primary_dns_label = shared.primary_dns_label
    primary_dns_help = ''
    secondary_dns_label = shared.secondary_dns_label
    secondary_dns_help = ''
    primary_wins_label = 'Primary WINS server IP address'
    primary_wins_help = ''
    secondary_wins_label = 'Secondary WINS server IP address'
    secondary_wins_help = ''
    client_subnet_label = 'VPN client subnet'
    client_subnet_help = ''
    client_address_range_label = 'VPN client address range'
    client_address_range_help = ''
   
class ManagementTexts:
    # Product maintenance group
    maintenance_group_caption = 'Maintenance'
    reboot_group_caption = 'Product Maintenance'
    reboot_day_label = 'Maintenance reboot weekday'
    reboot_day_options = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday')
        ]
    reboot_time_label = 'Maintenance reboot time'
    reboot_time_options = []
    automatic_update_label = 'Check for updates when rebooting'
    backup_group_caption = 'Email back-ups'
    # Email reports group
    email_reports_caption = 'Email reporting'
    email_internal_errors_label = 'Send email from internal errors'
    email_network_errors_label = 'Send email from network errors'
    status_group_caption = 'Gateway status reports'
    email_status_label = 'Send status email periodically'
    email_status_period_label = 'Status reports period'
    email_status_period_options = [
        ('weekly', 'One week'),
        ('monthly', 'One month')
        ]
    email_backups_label = 'Add configuration backup file to status email'
    admin_email_address_label = 'Admin email address'
    # Check service
    check_service_group_caption = 'Check service availability'
    service_address_label = 'Service address'
    service_port_label = 'Service port'
    periodic_test_group_caption = 'Monitor service availability'
    new_periodic_test_group_caption = 'Add service to monitor'
    send_periodic_fail_email_label = 'Send email if service not available'
    
    def __init__(self):
      for i in range(24):
        if i < 9:
            self.reboot_time_options.append((i, '0' + str(i)+':00 - ' + '0' + str(i+1) + ':00'))
        elif i == 9:
            self.reboot_time_options.append((i, '0' + str(i)+':00 - ' + str(i+1) + ':00'))
        else:
            self.reboot_time_options.append((i, str(i)+':00 - ' + str(i+1) + ':00'))
            
    # License page
    license_group_caption = 'Product License'
    license_key_label = 'License key'
    license_name_label = 'License name'
    license_user_count_label = 'Max user connections'
    license_sts_count_label = 'Max site-to-site connections'
    
    # Remote management
    remote_group_caption = 'Remote Management'
    root_password_label = 'Root password'
    
class ContactTexts:
    # Message type
    message_type_group_caption = 'Message type'
    message_type_options_label = 'Message type'
    message_type_options = [
        ('bug', 'Bug report'),
        ('question', 'Product question'),
        ('idea', 'Product improvement idea'),
        ('other', 'Other')
        ]
    # Email message
    email_message_group_caption = 'Email message'
    email_message_label = 'Message'
    add_attachment_caption = 'Add attachment'
    add_heavy_error_log_caption = 'Create client connection error log'
    reply_address_label = 'Reply address'
    # Form submit
    send_email_caption = 'Send message'
    download_message_caption = 'Download message'
    
class GlobalValidationTexts:
    e_public_and_private_ip_same = 'Internet and private network connection cannot have the same IP address'
    e_public_and_private_if_same = 'Internet and private network connection cannot have the same network interface'
    e_required = 'Required'
    e_ip_and_subnet_does_not_match = 'IP address and subnet mask do not match'
    e_unknown = 'Unknown error, check system logs'
    e_two_proxyarps = 'Only one interface may use proxy ARP'
    e_ic_dhcp_not_in_use = 'Internet connection DHCP is not in use'
    e_pn_dhcp_not_in_use = 'Private network connection DHCP is not in use'
    e_dns_server_not_defined = 'At least one DNS server must be defined'
    e_one_interface_and_private_route = 'Cannot use private network connection in one interface setup'
    e_network_default_gateway_not_set = 'Network default gateway has not been defined'
    
    # Warnings
    w_gw_not_in_ip_subnet = 'Gateway is not in the same subnet as IP address'
    w_uplink_small = 'Simultaneous VPN connections may be very slow with VPN uplink value smaller than 0.256 Mbps'
    w_uplink_big = 'Uplink speed limit not recommended for link speeds higher than 100 Mbps'
    
