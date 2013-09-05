#ifndef _CPHL_IPSEC_API_H_
#define _CPHL_IPSEC_API_H_

#include "types.h"

//
enum x4e_cipher
{
  x4c_cipher_invalid,

  x4c_cipher_des  = 1,  // must match x4c_ipsec_alg_xx from ipsec_types.h
  x4c_cipher_3des = 3,
};

//
enum x4e_hasher
{
  x4c_hasher_invalid,

  x4c_hasher_none = 0,  // must match x4c_ipsec_alg_xx from ipsec_types.h
  x4c_hasher_md5  = 1,
  x4c_hasher_sha1 = 2,
};

//
enum x4e_dhgroup
{
  x4c_dhgroup_invalid,

  x4c_dhgroup_none = 0, // no Phase 2 PFS 
  x4c_dhgroup_low  = 1, // must match x4c_ipsec_alg_xx from ipsec_types.h
  x4c_dhgroup_med  = 2,
};

//
struct x4_ipsec_ts      // traffic selector
{
  ipv4   addr;
  ipv4   mask;
  uint16 port;
};

/*
 *
 */
struct x4_ipsec_profile
{
  // internal unique ID
  virtual const guid & id() const = 0;

  // isakmp sa
  virtual void config(x4e_cipher  cipher,
                      x4e_hasher  hasher, 
                      x4e_dhgroup dhgroup,
                      uint        lifetime) = 0;

  // ipsec sa - esp, preshared key
  virtual void insert(const x4_ipsec_ts & l,
                      const x4_ipsec_ts & r,
                      uint8 proto,
                      const ipv4 & gl,
                      const ipv4 & gr,
                      x4e_cipher  cipher,
                      x4e_hasher  hasher,
                      bool pfs,
                      const char * psk,
                      const char * CA) = 0;

  // ipsec sa - esp, preshared key, dynamic rule (ie w/o TS)
  virtual void insert_dynamic(x4e_cipher  cipher,
                              x4e_hasher  hasher,
                              bool pfs,
                              const char * psk,
                              const char * CA) = 0;

  // dtor
  virtual ~x4_ipsec_profile() {}

  //
  // factory method (accepts ISAKMP SA parameters)
  //
  static x4_ipsec_profile * instance();
};

/*
 *  Registering x4_ipsec_profile creates supporting data 
 *  entries in Windows registry and allows profile to be
 *  activated. 
 *
 *  $Note that while multiple profiles can be registered 
 *  simulteneously, no more than one can be active at any 
 *  given moment. 
 *
 *  $Note also that mmc/ipsec application 'assigns policies'
 *  rather than 'activates profiles'.
 *
 */

bool x4_register  (x4_ipsec_profile * h);
bool x4_unregister(const guid & id);

/*
 *  'Activating' the policy force Windows IPsec service
 *  to re-initialize itself with current IPsec policy.
 */
bool x4_activate(const guid & id);
bool x4_deactivate(const guid * id);

#endif
