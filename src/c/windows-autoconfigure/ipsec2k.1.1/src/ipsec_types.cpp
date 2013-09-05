#include "ipsec_types.h"

#define ZEROg(g)   memset(&g, 0, sizeof(g));
#define ZEROa(arr) memset(&arr[0], 0, sizeof(arr))

//
//  -- static/const members --
//
const uint32 x4_ipsec_base::_type = 0x00000100;
const char * x4_ipsec_base::_root = 
  "SOFTWARE\\Policies\\Microsoft\\Windows\\IPSec\\Policy\\Local\\";

const guid   x4_ipsec_filters::class_id = { 0x80dc20b5, 0x2ec8, 0x11d1, { 0xa8, 0x9e, 0x00, 0xa0, 0x24, 0x8d, 0x30, 0x21 } };
const char * x4_ipsec_filters::class_name = "ipsecFilter";

const guid   x4_ipsec_policy::class_id = { 0x80dc20b9, 0x2ec8, 0x11d1, { 0xa8, 0x9e, 0x00, 0xa0, 0x24, 0x8d, 0x30, 0x21 } };
const char * x4_ipsec_policy::class_name = "ipsecNegotiationPolicy";

const guid   x4_ipsec_nfa::class_id = { 0x11bbac00, 0x498d, 0x11d1, { 0x86, 0x39, 0x00, 0xa0, 0x24, 0x8d, 0x30, 0x21 } };
const char * x4_ipsec_nfa::class_name = "ipsecNFA";

const guid   x4_isakmp_policy::class_id = { 0x80dc20b8, 0x2ec8, 0x11d1, { 0xa8, 0x9e, 0x00, 0xa0, 0x24, 0x8d, 0x30, 0x21 } };
const char * x4_isakmp_policy::class_name = "ipsecISAKMPPolicy";

const guid   x4_ipsec_bundle::class_id = { 0x22202163, 0x4f4c, 0x11d1, { 0x86, 0x3b, 0x00, 0xa0, 0x24, 0x8d, 0x30, 0x21 } };
const char * x4_ipsec_bundle::class_name = "ipsecPolicy";

//
//  -- constructors --
//
x4_ipsec_base::x4_ipsec_base()
{
  last_changed = 0;
}

//
x4_ipsec_filter::x4_ipsec_filter()
{
  ZEROg(id);
  mirrored = false32;
  ZEROa(src_ip);
  ZEROa(src_mask);
  ZEROa(dst_ip);
  ZEROa(dst_mask);
  unknown1 = 0;
  protocol = 0;
  src_port = 0;
  dst_port = 0;
  unknown2 = 0;
}

//
x4_ipsec_transform::x4_ipsec_transform()
{
  alg1 = x4c_ipsec_alg_none;
  alg2 = x4c_ipsec_alg_none;
  type = x4c_ipsec_proto_none;
}

//
x4_ipsec_sa::x4_ipsec_sa()
{
  lifetime_secs = 0;
  lifetime_bytes = 0;
  unknown1 = 0;
  pfs = false32;
  transform_count = 0;
}

//
x4_ipsec_policy::x4_ipsec_policy()
{
  action = x4c_ipsec_policy_action_none;
  type   = x4c_ipsec_policy_type_none;
}

//
x4_ipsec_auth::x4_ipsec_auth()
{
  type = x4c_ipsec_auth_none;
}

//
x4_ipsec_nfa::x4_ipsec_nfa()
{
  conn_type = x4c_ipsec_conn_none;
  ZEROa(tunnel_endpoint);
  static_rule = true32;
  tunnel_enabled = false32;
  unknown3[0] = 0x01010101; // hz what this is
  unknown3[1] = 0x01010101;
  unknown3[2] = 0x01010101;
  unknown3[3] = 0x01010101;
  unknown3[4] = 0x00000001;
  unknown3[5] = 0x00000005;
  unknown3[6] = 0x00000000;
}

//
x4_isakmp_sa::x4_isakmp_sa()
{
  unknown1 = 0;
  cipher = x4c_ipsec_alg_none;
  ZEROa(unknown2);
  hash = x4c_ipsec_alg_none;
  ZEROa(unknown3);
  dhgroup = x4c_ipsec_alg_none,
  max_sa_count = 0;     // 1
  unknown4 = 0;
  rekey_interval = 0;
  unknown5 = 0;
}

//
x4_isakmp_policy::x4_isakmp_policy()
{
  ZEROa(unknown1);
  pfs_enabled = false32;
  ZEROa(unknown2);
}

//
x4_ipsec_bundle::x4_ipsec_bundle()
{
  refresh_interval = 0;
}

//
//  -- some conversion methods --
//
string to_string(x4e_ipsec_policy_action v)
{
  static const char * label[] = 
  { 
    "{00000000-0000-0000-0000-000000000000}",
    "{3f91a819-7647-11d1-864d-d46a00000000}",
    "{8a171dd2-77e3-11d1-8659-a04f00000000}",
    "{8a171dd3-77e3-11d1-8659-a04f00000000}",
    "{3f91a81a-7647-11d1-864d-d46a00000000}" 
  };

  assert (x4c_ipsec_policy_block <= v &&
          v <= x4c_ipsec_policy_weak);

  return label[v];
}

string to_string(x4e_ipsec_policy_type v)
{
  static const char * label[] = 
  { 
    "{00000000-0000-0000-0000-000000000000}",
    "{62f49e10-6c37-11d1-864c-14a300000000}",
    "{62f49e13-6c37-11d1-864c-14a300000000}"
  };

  assert (v < x4c_ipsec_policy_type_max);

  return label[v];
}

