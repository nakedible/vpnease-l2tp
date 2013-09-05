#ifndef _CPHL_REGISTRY_H_
#define _CPHL_REGISTRY_H_

#include "types.h"
#include "buffer"

enum x4e_reg_key_access
{
  x4c_reg_key_open   = 0x01,
  x4c_reg_key_create = 0x02,
  x4c_reg_key_either = 0x03
};

struct x4_reg_key
{
  x4_reg_key();
  ~x4_reg_key();

  bool open(HKEY hKey, const char * subkey, uint8 how = 0x01, REGSAM samDesired = KEY_ALL_ACCESS);
  bool open(HKEY hKey, const string & subkey, uint8 how = 0x01, REGSAM samDesired = KEY_ALL_ACCESS);
  void close();

  bool subkey_open(const char * label, x4_reg_key & subkey, uint8 how = 0x01);

  //
  // get
  //
  bool value_get(const char * label, string & );          // REG_SZ
  bool value_get(const char * label, vector<string> & );  // REG_MULTI_SZ

  //
  // set
  //
  bool value_set(const char * label, const uint32 & );          // REG_DWORD
  bool value_set(const char * label, const string & );          // REG_SZ
  bool value_set(const char * label, const vector<string> & );  // REG_MULTI_SZ
  bool value_set(const char * label, const buffer & );          // REG_BINARY
//bool value_set(const char * label, const wstring & ); // REG_SZ

  //
  // remove
  //
  static bool remove(HKEY hKey, const char * subkey);
  static bool remove(HKEY hKey, const string & subkey);

  bool value_remove(const char * label);
  bool subkey_remove(const char * label);

protected:

  bool read(const char * label, buffer & data, uint32 & type);
  bool write(const char * label, const void * data, uint32 size, uint32 type);

protected:

  x4_reg_key(const x4_reg_key & );
  int operator = (const x4_reg_key & );

protected:

  HKEY   hRoot, hKey;
  string path;
  REGSAM sam;
};

#endif
