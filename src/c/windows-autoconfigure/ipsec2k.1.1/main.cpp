#include "types.h"
#include "ipsec.h"

#include <stdio.h>
#include <conio.h>

void main()
{
  /*
   *  The following example establishes two ipsec rules:
   *
   *  (a) DES-MD5 ESP tunnel for client Web traffic from local subnet 
   *      1.x.x.x/8 to remote subnet 2.0.x.x/16 gatewayed by 
   *      4.4.4.4 host. Our own IP is assumed to be 3.3.3.3.
   *
   *      1.x.x.x nodes are assumed to be browsing HTTP servers 
   *      at 2.0.x.x subnet
   *
   *      +-----------+                                     +-------------+
   *      |           |                                     |             |
   *      | 1.x.x.x/8 +--[  us  ]-- Internet --[ gateway ]--+  2.0.x.x/16 |
   *      |           |                                     |             |
   *      +-----------+   3.3.3.3              4.4.4.4      +-------------+
   * 
   *  (b) 3DES-[no_auth] ESP in transport mode for all traffic between 
   *      localhost and 5.5.5.5 peer.
   *
   *  (c) Dynamic rule accepting 3DES/SHA1 tunnels with PSK authentication
   *
   *  The code below also configures ISAKMP (Phase 1) SA to use 3DES/SHA1 
   *  with 1024bit MODP group and a lifetime of 600 seconds
   *  
   */

  x4_ipsec_profile * ipsec = x4_ipsec_profile::instance();

  x4_ipsec_ts lts, rts;
  ipv4        lg,  rg;

  // -- configure ISAKMP SA parameters --
  ipsec->config(x4c_cipher_3des,
                x4c_hasher_sha1,
                x4c_dhgroup_med,
                600);
  // -- rule (a) --
  lts.addr[0] = 1; lts.mask[0] = 255; lg[0] = 3;
  lts.addr[1] = 0; lts.mask[1] = 0;   lg[1] = 3;
  lts.addr[2] = 0; lts.mask[2] = 0;   lg[2] = 3;
  lts.addr[3] = 0; lts.mask[3] = 0;   lg[3] = 3;
  lts.port = 0; // any

  rts.addr[0] = 2; rts.mask[0] = 255; lg[0] = 4;
  rts.addr[1] = 0; rts.mask[1] = 255; lg[1] = 4;
  rts.addr[2] = 0; rts.mask[2] = 0;   lg[2] = 4;
  rts.addr[3] = 0; rts.mask[3] = 0;   lg[3] = 4;
  rts.port = 80;

  ipsec->insert(lts, rts, 6,      // traffic selectors (6 is TCP)
                lg, rg,           // tunnel ends
                x4c_cipher_des,
                x4c_hasher_md5,
                false,            // no PFS
                "password",       // preshared secret authentication
                0);

  // -- rule (b) --
  memset(lts.addr, 0, 4); memset(lts.mask, 0xFF, 0); memset(lg, 0, 0);
  rts.addr[0] = 5;        memset(rts.mask, 0xFF, 0); memset(rg, 0, 0);
  rts.addr[1] = 5;
  rts.addr[2] = 5;
  rts.addr[3] = 5;

  ipsec->insert(lts, rts, 0,      // traffic selectors (0 is ANY)
                lg, rg,           // tunnel ends
                x4c_cipher_3des,
                x4c_hasher_none,
                true,             // enable PFS
                0,
                "L=Internet, "    // certificate authentication
                "O=\"VeriSign, Inc.\", "
                "OU=VeriSign Individual Software Publishers CA");

  // -- rule (c) --
  ipsec->insert_dynamic(x4c_cipher_3des,
                        x4c_hasher_sha1,
                        true,       // PFS
                        "123",      // preshared secret authentication
                        0);

  // -- create registry entries --
  x4_register(ipsec);

  // $note that at this point we only need ipsec->id() value and can freely
  //       dispose 'ipsec' given that its 'id' is cached somewhere

  //
  x4_activate(ipsec->id());

  // -- pause --
  _getch();

  //
  x4_deactivate(0);

  // -- clean the registry up -- 
  x4_unregister(ipsec->id());
  
  //
  delete ipsec;
}