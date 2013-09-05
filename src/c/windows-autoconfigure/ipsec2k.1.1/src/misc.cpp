#include "misc.h"

#include <assert.h>
#include <stdio.h>

//
// guid ops
//
guid & generate(guid & v)
{
  HRESULT r;
  r = CoCreateGuid(&v);
  assert(r == S_OK);
  return v;
}

string to_string(const guid & v)
{
  // {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}
  char temp[38];

  sprintf(temp,
          "{%08x-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x}",
          v.Data1,
          v.Data2,
          v.Data3,
          v.Data4[0], v.Data4[1], v.Data4[2], v.Data4[3],
          v.Data4[4], v.Data4[5], v.Data4[6], v.Data4[7]);

  return temp;
}

string to_string(const ipv4 & v)
{
  char temp[3+1+3+1+3+1+3];

  sprintf(temp,
          "%u.%u.%u.%u",
          0xff & (uint)v[0],
          0xff & (uint)v[1],
          0xff & (uint)v[2],
          0xff & (uint)v[3]);

  return temp;
}

//
// caching buffer expander
//
buffer & grow(buffer & b, uint32 delta)
{
  uint32 capacity = b.capacity();
  uint32 size     = b.size();
  uint32 wanted   = size + delta;

  if (capacity < wanted)
  {
    // wanted = 4*size/3 + 2*delta; .. or something
    b.reserve(wanted);
  }
  return b;
}
