#ifndef _CPHL_IPSEC_TYPES_H_
#define _CPHL_IPSEC_TYPES_H_

#include "types.h"

//
typedef vector<string>  strings;

/*
 *  There are five structures in play that has 1-to-1
 *  correspondance to the registry entries maintained by
 *  Windows IPsec service:
 *
 *    x4_ipsec_filters  - define traffic filters
 *    x4_ipsec_policy   - define IPsec SAs
 *    x4_ipsec_nfa      - defines authentication methods and 
 *                        binds one ipsec_policy to many ipsec_filter                        
 *    x4_isakmp_policy  - define ISAKMP SAs
 *    x4_ipsec_bundle   - binds one isakmp_policy to many ipsec_nfa
 *
 *  All five are inherited from the base x4_ipsec_base class,
 *  which contains fields common to registry entries of all types.
 *
 */

//
//  -- constants -- 
//
enum x4e_ipsec_alg
{
  x4c_ipsec_alg_none,

  // ciphers
  x4c_ipsec_des  = 1,
  x4c_ipsec_3des = 3,

  // hashes
  x4c_ipsec_md5  = 1,
  x4c_ipsec_sha1 = 2,

  // diffie-hellman groups
  x4c_ipsec_dh_low = 1,
  x4c_ipsec_dh_med = 2,
};

//
enum x4e_ipsec_proto
{
  x4c_ipsec_proto_none,

  x4c_ipsec_ah   = 1,
  x4c_ipsec_esp  = 2,
};

//
enum x4e_ipsec_policy_action
{
  x4c_ipsec_policy_action_none,
  
  x4c_ipsec_policy_block,      // block traffic              {3f91a819-7647-11d1-864d-d46a00000000}
  x4c_ipsec_policy_raw,        // accept raw,   reply raw    {8a171dd2-77e3-11d1-8659-a04f00000000}
  x4c_ipsec_policy_ipsec,      // accept ipsec, reply ipsec  {8a171dd3-77e3-11d1-8659-a04f00000000}
  x4c_ipsec_policy_weak,       // accept raw,   reply ipsec  {3f91a81a-7647-11d1-864d-d46a00000000}
};

//
enum x4e_ipsec_policy_type
{
  x4c_ipsec_policy_type_none,
  
  x4c_ipsec_policy_type_static,
  x4c_ipsec_policy_type_dynamic,

  x4c_ipsec_policy_type_max
};

//
enum x4e_ipsec_auth
{
  x4c_ipsec_auth_none,

  x4c_ipsec_auth_psk  = 1,  // preshared key
  x4c_ipsec_auth_cert = 3,  // certificate
  x4c_ipsec_auth_krb  = 5,  // kerberos
};

//
enum x4e_ipsec_conn
{
  x4c_ipsec_conn_none,

  x4c_ipsec_conn_all = 0xFFFFFFFD,  // all connections
  x4c_ipsec_conn_lan = 0xFFFFFFFE,  // LAN
  x4c_ipsec_conn_ra  = 0xFFFFFFFF,  // remote access
};

//
// -- structures --
//
struct x4_ipsec_base
{
  static const uint32 _type; //  0x0100
  static const char * _root; //  'HKEY_LOCAL_MACHINE\SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\'

  string   description;  //  apBlahDesc
  string   ipsec_id;     //  {72385235-70fa-11d1-864c-14a300000000}
  string   ipsec_name;   //  Comment
  strings  owners;       //  SOFTWARE\Policies\Microsoft\Windows\IPSec\Policy\Local\ipsecNFA{ce3c84c4-0c3b-4c70-aef4-cf80f0766b55}
  string   name;         //  ipsecFilter{72385235-70fa-11d1-864c-14a300000000}
  uint32   last_changed; //  1014057662

  x4_ipsec_base();
};

//
//
struct x4_ipsec_filter
{
  wstring  src_name;
  wstring  dst_name;
  wstring  description;
  guid     id;
  bool32   mirrored;
  ipv4     src_ip;
  ipv4     src_mask;
  ipv4     dst_ip;
  ipv4     dst_mask;
  uint32   unknown1;
  byte32   protocol;
  uint16   src_port;
  uint16   dst_port;
  uint32   unknown2;

  x4_ipsec_filter();
};

//
struct x4_ipsec_filters : x4_ipsec_base
{
  static const guid   class_id;
  static const char * class_name;

  vector<x4_ipsec_filter> entries;
};

//
//
struct x4_ipsec_transform
{
  x4e_ipsec_alg   alg1;
  x4e_ipsec_alg   alg2;
  x4e_ipsec_proto type;

  x4_ipsec_transform();
};

//
struct x4_ipsec_sa
{
  uint32  lifetime_secs;
  uint32  lifetime_bytes;
  uint32  unknown1;
  bool32  pfs;

  byte32  transform_count;
  x4_ipsec_transform transforms[3];

  x4_ipsec_sa();
};

//
struct x4_ipsec_policy : x4_ipsec_base
{
  static const guid   class_id;
  static const char * class_name;

  vector<x4_ipsec_sa> sas;
  
  x4e_ipsec_policy_action action; // not a part of ipsecData
  x4e_ipsec_policy_type   type;   // not a part of ipsecData

  x4_ipsec_policy();
};

//
//
struct x4_ipsec_auth
{
  x4e_ipsec_auth type;
  wstring        data;

  x4_ipsec_auth();
};

//
struct x4_ipsec_nfa : x4_ipsec_base
{
  static const guid   class_id;
  static const char * class_name;

  vector<x4_ipsec_auth>  authenticators;
  x4e_ipsec_conn         conn_type;
  wstring                unknown1;
  ipv4                   tunnel_endpoint;
  bool32                 static_rule;      // vs 'Dynamic'
  bool32                 tunnel_enabled;
  wstring                unknown2;
  uint32                 unknown3[7];

  strings filters;      // references
  string  ipsec_policy; // reference

  x4_ipsec_nfa();
};

//
//
struct x4_isakmp_sa
{
  uint32         unknown1;
  x4e_ipsec_alg  cipher;
  uint32         unknown2[2];
  x4e_ipsec_alg  hash;
  uint32         unknown3[6];
  x4e_ipsec_alg  dhgroup;
  uint32         max_sa_count;   // execute pfs rekey after negotiating 'max_rekey' SAs
  uint32         unknown4;
  uint32         rekey_interval; // in sec
  uint32         unknown5;

  x4_isakmp_sa();
};

//
struct x4_isakmp_policy : x4_ipsec_base
{
  static const guid   class_id;
  static const char * class_name;

  uint32  unknown1[5];
  bool32  pfs_enabled;
  uint32  unknown2[9];
  vector<x4_isakmp_sa>  methods;

  x4_isakmp_policy();
};

//
//
struct x4_ipsec_bundle : x4_ipsec_base
{
  static const guid   class_id;
  static const char * class_name;

  uint32   refresh_interval;
  string   isakmp_policy;  // reference
  strings  nfas;           // references

  x4_ipsec_bundle();
};

//
//
string to_string(x4e_ipsec_policy_action);
string to_string(x4e_ipsec_policy_type);


#endif
