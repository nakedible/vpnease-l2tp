#ifndef _CPHL_MISC_H_
#define _CPHL_MISC_H_

#include "types.h"
#include "buffer"

//
// Misc methods
//
guid & generate(guid & );
string to_string(const guid & );
string to_string(const ipv4 & );

//
// Customizable buffer expander
//
buffer & grow(buffer &, uint32 delta);


//
// General purpose binary serializer
//
inline buffer & serialize(buffer & b, const void * p, uint n)
{
  return grow(b,n).append((byte*)p,n);
}

//
// Simple types serializers
//
#define IMPLEMENT(T)                                  \
inline buffer & operator << (buffer & b, const T & v) \
{ return serialize(b, &v, sizeof(v)); }

IMPLEMENT(char);
IMPLEMENT(wchar_t);
IMPLEMENT(uint8);
IMPLEMENT(uint16);
IMPLEMENT(uint32);
IMPLEMENT(bool32);

#undef IMPLEMENT

//
// basic_string serializer (covers string, wstring and buffer)
//
template <class E, class T, class A>
buffer & operator << (buffer & b, const std::basic_string<E,T,A> & v)
{
  static const E tail = 0;
  uint32 size = ( v.size() + 1 ) * sizeof(E) ; // trail with 00 00

  return serialize(b << ((uint32) size), v.data(), size-sizeof(E)) << tail;
}

//
// Other serializers 
//
inline buffer & operator << (buffer & b, const ipv4 & v)
{ return serialize(b, v, 4); }

inline buffer & operator << (buffer & b, const guid & v)
{ 
  b << v.Data1 << v.Data2 << v.Data3; 
  return serialize(b, v.Data4, 8); 
}


#endif
