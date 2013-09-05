#include "registry.h"
#include <assert.h>

x4_reg_key::x4_reg_key()
{
  hKey = 0;
}

x4_reg_key::~x4_reg_key()
{
  close();
}

bool x4_reg_key::open(HKEY hRootKey, const char * subkey, uint8 how, REGSAM regsam)
{
  DWORD dwHow;
  
  close();

  sam = regsam;
  path = subkey;
  hRoot = hRootKey;

  if (how & x4c_reg_key_open)
    if (ERROR_SUCCESS == RegOpenKeyEx(hRoot, path.c_str(), 0, sam, &hKey))
      return true;

  if (how & x4c_reg_key_create)
    if (ERROR_SUCCESS == RegCreateKeyEx(hRoot, path.c_str(), 0, 0, 0, sam, 0, &hKey, &dwHow))
      if ((how & x4c_reg_key_open) || (dwHow == REG_CREATED_NEW_KEY))
      {
        return true;
      }
      else
      {
        // already exists - no good, wanted it to be created
        close();
      }

  return false;
}

bool x4_reg_key::open(HKEY hKey, const string & subkey, uint8 how, REGSAM samDesired)
{
  return open(hKey, subkey.c_str(), how, samDesired);
}

void x4_reg_key::close()
{
  if (hKey)
  {
    RegCloseKey(hKey);
    hKey = 0;
  }
}

bool x4_reg_key::subkey_open(const char * label, x4_reg_key & subkey, uint8 how)
{
  if (! hKey)
    return false;

  return subkey.open(hRoot, path + '\\' + label, how, sam);
}

//
//
//
bool x4_reg_key::value_get(const char * label, string & v)
{
  buffer temp;
  uint32 type;
  uint32 size;

  if (! hKey)
    return false;

  if (! read(label, temp, type) || (type != REG_SZ))
    return false;

  // trim trailing zero
  size = temp.size();
  if (size && !temp[size-1])
    size--;

  v.assign((char*)temp.data(), size);
  return true;
}

bool x4_reg_key::value_get(const char * label, vector<string> & v)
{
  buffer temp;
  uint32 type, pos, qos;

  if (! hKey)
    return false;

  if (! read(label, temp, type) || (type != REG_MULTI_SZ) )
    return false;

  v.clear();
 
  // parse em out
  for (pos=0; pos<temp.size(); pos=qos+1)
  {
    qos = temp.find((unsigned char) char(0), pos);
    if (qos < 0)
    {
      v.clear();
      return false; // malformed item
    }
    if (qos == pos) // two zeros
    {
      break;
    }
    v.push_back(string((char*)temp.data()+pos, qos-pos));
  }

  if (pos != temp.size()-1)
  {
    v.clear();
    return false;  
  }

  return true;
}

//
//
//
bool x4_reg_key::value_set(const char * label, const uint32 & v)
{
  return write(label, &v, 4, REG_DWORD);
}

bool x4_reg_key::value_set(const char * label, const string & v)
{
  return write(label, v.data(), v.size(), REG_SZ);
}

bool x4_reg_key::value_set(const char * label, const vector<string> & v)
{
  buffer temp;
  uint32 i,n;

  for (i=0, n=v.size(); i<n; i++)
  {
    temp += (buffer&)v[i];
    temp += (uint8)0;
  }

  temp += (uint8)0;

  return write(label, temp.data(), temp.size(), REG_MULTI_SZ);
}

bool x4_reg_key::value_set(const char * label, const buffer & v)
{
  return write(label, v.data(), v.size(), REG_BINARY);
}

bool x4_reg_key::remove(HKEY hRoot, const char * subkey)
{
  // static method
  // $todo - enumerate and recursively remove all subkeys first
  return RegDeleteKey(hRoot, subkey) == ERROR_SUCCESS;
}

bool x4_reg_key::remove(HKEY hRoot, const string & subkey)
{
  return remove(hRoot, subkey.c_str());
}

bool x4_reg_key::value_remove(const char * label)
{
  return RegDeleteValue(hKey, label) == ERROR_SUCCESS;
}

bool x4_reg_key::subkey_remove(const char * label)
{
  return (hKey != 0) & remove(hKey, label);
}



//
// protected
//
bool x4_reg_key::read(const char * label, buffer & data, uint32 & type)
{
  LONG  r;
  DWORD size;

  assert(hKey);

  size = 0;
  r = RegQueryValueEx(hKey, label, 0, &type, 0, &size);
  if (r != ERROR_SUCCESS)
    return false;

  if (size > 65536)
    return false;

  data.resize(size);
  r = RegQueryValueEx(hKey, label, 0, &type, (BYTE*)data.data(), &size);
  if (r != ERROR_SUCCESS)
    return false;

  return true;
}

bool x4_reg_key::write(const char * label, const void * data, uint32 size, uint32 type)
{
  LONG r;

  assert(hKey);

  r = RegSetValueEx(hKey, label, 0, type, (BYTE*)data, size);
  return (r == ERROR_SUCCESS);
}