Versions

  1.1, Feb 4, 2004    
	- added support for Dynamic policy
	- fixed NFA object serialization

  1.0.1, Mar 18, 2003 
	- initial public release

Introduction

  This package contain home-brewed API for configuring native Windows
  IPsec Policy Agent.
  
Legal

  Copyright (c) 2003-2004, Cipherica Labs. All rights reserved.
  See enclosed license.txt for redistribution information.

  ipsec2k is distributed under one of the OSI-approved Open Source
  licenses. The license effectively boils down to the unrestricted
  use under condition of open-sourced redistributions. For other
  redistribution schemes alternate licensing must be negotiated
  with Cipherica Labs.  

Overview
  
  Both Windows 2000 and XP are IPsec-capable, but no offical API was
  ever released. MS did publish a console application [1] capable of 
  manipulating IPsec policies, and some people [2] wrote wrappers for
  it.

  Both Microsoft Management Console and IPsecPol tool are operating
  with a number of cross-referenced registry entries. Creating a
  filter, an action or the policy results in the registry being 
  populated with respective keys and values. Assigning (or activating) 
  the policy is done via setting certain value in the registry and then
  signaling IPsec service via CONTROL interface.

  The library defines clear and simple interface for manipulating IPsec 
  policies and replicates MMC and ipsecpol behaviour behind the scenes.

Interface

  Single IPsec policy includes settings for a single ISAKMP SA (Phase 1
  SA), arbitrary number of traffic filters and associated ESP SA (Phase 2
  SA). Eventhough Windows can handle AH (Auth Header) SA, they are not 
  supported by the library due to being useless in the real world.

  The library uses term 'ipsec profile' in place of 'ipsec policy' due
  to certain ambiguity associated with latter.

Creating the policy

  The profile is instantiated with call to x4_ipsec_profile::instance(),
  which creates internal to the library object; no registry operations
  are carried out at this point.

  The profile comes preconfigured with DES/SHA1/1024 ISAKMP SA and an
  empty list of traffic selectors. ISAKMP SA can be re-configured using
  x4_ipsec_profile::config() method.

  The x4_ipsec_profile::insert() method creates IPsec traffic selector 
  and associates SA parameters with it. 

  The traffic selector is formed from two x4_ipsec_ts structures, one (l)
  defining local filter and another (r) - remote. Filtering can be done 
  by IP subnet, IP protocol and/or by ports if it's a TCP/UDP filter.
  Have a look at the examples in main.cpp - it's all pretty simple.
  
  Both tunnel and transport modes are supported. For the tunnel mode the
  caller must specify tunnel gateways' addresses (gl and gr); for the 
  transport mode these must be 0.0.0.0.

  IPsec SA encryption and hashing algorithms are specified by 'cipher'
  and 'hasher' paremeters, and 'pfs' defines is PFS must be enabled for
  Phase 2 negotiation of this SA.

  And the last but not least - authentication mode. Exactly one of 'psk'
  and 'CA' parameters must be non-zero and meaningful. 'Psk' is a pre-
  shared key authentication and must point at standard ANSI C plain-text
  secret string (oh, btw, it's stored in plain-text in the registry too).
  'CA' is a pointer at literal string as well, which must be in a form of
  
   L=Internet, O="VeriSign, Inc.", OU=VeriSign Software Publishers CA

  or something similar. 
  
  ##
  ## Please note that certificate auth mode has NOT been tested and
  ## thus most likely will not work and will require some tweaking.
  ##

  As of version 1.1 ipsec2k also allows creating so-called 'dynamic' IPsec 
  policy (see mmc manual for details). It is handled by insert_dynamic()
  method, which performs similar to insert(), except it does not setup
  any traffic selectors (see code for details).

Registering the policy

  Once the profile is ready, it must be submitted to x4_register(), which
  will go through its registry mangling magic and will (hopefully) create
  cross-referenced set of entries readable by MMC and IPsec service.

  At this point MMC can be used to verify that the freshly created policy
  is in fact what it's meant to be. The names of the filters, actions and
  other policy elements are far from being user friendly, so it might be
  something that will need an improvement later on.

  Also note that 'ipsec_profile' instance may be discarded at this point
  as the only thing that is required for profile activation and/or removal
  is profile's ID. The ID is a random GUID, which can be retrieved with a
  call to x4_ipsec_profile::id().

Assigning the policy

  The policy can be assigned (or made active) by calling x4_activate().
  The code will modify 'active policy' registry key and signal IPsec 
  service to pick the change up. If the service is not running, it will
  be started.

Cleanup

  x4_activate() and x4_register() have twin methods, which reverse their
  actions. x4_deactivate() assigns empty current policy ('allow all'),
  and x4_unregister() accepts profile ID and purges all associated entries
  from the registry.

Conclusion

  That's about it. Not exactly a field theory, so just poke around the
  main.cpp example and the library code if there are any questions. 
  
  For bugs, fixes (cert-based authentication in particular) and for all
  other stuff the email is ap-at-cipherica.com


References, links

  (1) Windows 2000 ipsecpol.exe Tool Version 1.22
      http://agent.microsoft.com/windows2000/techinfo/reskit/tools/existing/ipsecpol-o.asp
  
  (2) Windows 2000 VPN Tool
      http://vpn.ebootis.de/