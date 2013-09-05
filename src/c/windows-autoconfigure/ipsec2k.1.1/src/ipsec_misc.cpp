#include <assert.h>
#include "misc.h"
#include "ipsec_misc.h"


//
// helpers
//
template <class T>
void serialize(buffer & b, const vector<T> & v);

void serialize_head(buffer & b, const guid & class_id);
void serialize_tail(buffer & b);

void serialize(buffer & b, const x4_ipsec_filter & v);
void serialize(buffer & b, const x4_ipsec_sa & v);
void serialize(buffer & b, const x4_ipsec_auth & v);
void serialize(buffer & b, const x4_isakmp_sa & v);

//
//
//
void serialize(buffer & b, const x4_ipsec_filters & v)
{
  serialize_head(b, v.class_id);
  serialize(b, v.entries);
  serialize_tail(b);
}

void serialize(buffer & b, const x4_ipsec_policy & v)
{
  serialize_head(b, v.class_id);
  serialize(b, v.sas);
  serialize_tail(b);
}

void serialize(buffer & b, const x4_ipsec_nfa & v)
{
  serialize_head(b, v.class_id);

  serialize(b, v.authenticators);

  b << (uint32)v.conn_type
    << v.unknown1
    << v.tunnel_endpoint
    << v.static_rule 
    << v.tunnel_enabled
    << v.unknown2;
  
  serialize(b, v.unknown3, sizeof(v.unknown3));
  serialize_tail(b);
}

void serialize(buffer & b, const x4_isakmp_policy & v)
{
  serialize_head(b, v.class_id);
  serialize(b, v.unknown1, sizeof(v.unknown1));
  b << v.pfs_enabled;
  serialize(b, v.unknown2, sizeof(v.unknown2));
  serialize(b, v.methods);
  serialize_tail(b);
}

void serialize(buffer & b, const x4_ipsec_bundle & v)
{
  serialize_head(b, v.class_id);
  b << v.refresh_interval;
  serialize_tail(b);
}


//
// Helpers
//
template <class T>
void serialize(buffer & b, const vector<T> & v)
{
  uint32 i, n=v.size();

  b << n;
  for (i=0; i<n; i++)
    serialize(b, v[i]);
}

void serialize_head(buffer & b, const guid & class_id)
{
  b.clear();
  b << class_id << (uint32)0;
}

void serialize_tail(buffer & b)
{
  assert(b.size() > 16+4); // guid + size

  *(uint32*)(b.data()+16) = b.size() - 16 - 4;
  b << (uint8)0;
}

void serialize(buffer & b, const x4_ipsec_filter & v)
{
  b << v.src_name << v.dst_name << v.description
    << v.id 
    << v.mirrored
    << v.src_ip << v.src_mask << v.dst_ip << v.dst_mask
    << v.unknown1
    << v.protocol
    << v.src_port << v.dst_port
    << v.unknown2;
}

buffer & operator << (buffer & b, const x4_ipsec_transform & v)
{
  return b << (uint32)v.alg1 << (uint32)v.alg2 << (uint32)v.type;
}

void serialize(buffer & b, const x4_ipsec_sa & v)
{
  b << v.lifetime_secs
    << v.lifetime_bytes
    << v.unknown1
    << v.pfs
    << v.transform_count
    << v.transforms[0] << v.transforms[1] << v.transforms[2];
}

void serialize(buffer & b, const x4_ipsec_auth & v)
{
  b << (uint32)v.type << v.data;
}

void serialize(buffer & b, const x4_isakmp_sa & v)
{
  b << v.unknown1
    << (uint32)v.cipher;

  serialize(b, v.unknown2, sizeof(v.unknown2));

  b << (uint32)v.hash;

  serialize(b, v.unknown3, sizeof(v.unknown3));

  b << (uint32)v.dhgroup
    << v.max_sa_count
    << v.unknown4
    << v.rekey_interval
    << v.unknown5;
}