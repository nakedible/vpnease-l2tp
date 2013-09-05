#include "ipsec.h"
#include "ipsec_misc.h"

#include "misc.h"
#include "registry.h"
#include "service.h"

#include <time.h>

//
// Internal HPOLICY object
//
struct x4_the_ipsec_profile : x4_ipsec_profile
{
  x4_the_ipsec_profile();

  //
  // -- x4_ipsec_profile --
  //
  const guid & id() const;

  void config(x4e_cipher  cipher,
              x4e_hasher  hasher, 
              x4e_dhgroup dhgroup,
              uint        lifetime);

  void insert(const x4_ipsec_ts & l,
              const x4_ipsec_ts & r,
              uint8 proto,
              const ipv4 & gl,
              const ipv4 & gr,
              x4e_cipher  cipher,
              x4e_hasher  hasher,
              bool pfs,
              const char * psk,
              const char * CA);

  void insert_dynamic(x4e_cipher  cipher,
                      x4e_hasher  hasher,
                      bool pfs,
                      const char * psk,
                      const char * CA);

  //
  // -- misc --
  //
  void init();

public:

  guid                     the_id;
  x4_ipsec_bundle          head;
  x4_isakmp_policy         isakmp;
  vector<x4_ipsec_policy>  ipsec;
  vector<x4_ipsec_nfa>     nfas;
  vector<x4_ipsec_filters> filters;
  bool                     have_dynamic;
};

//
// -- local methods --
//
void initialize_base(x4_ipsec_base & b, const char * class_name, const guid * id = 0);
void cross_reference(x4_ipsec_base & child, x4_ipsec_base & parent, string & parent_ref);
void cross_reference(x4_ipsec_base & child, x4_ipsec_base & parent, strings & parent_ref);

bool policy_register_base(const x4_ipsec_base &, const char * class_id, 
                          const buffer & ipsec_data, x4_reg_key &);
bool policy_register(const x4_ipsec_filters &);
bool policy_register(const x4_ipsec_policy &);
bool policy_register(const x4_ipsec_nfa &);
bool policy_register(const x4_isakmp_policy &);
bool policy_register(const x4_ipsec_bundle &);

//
#define is_zero_ipv4(ip) (0 == *(uint32*)(ip))

//
// 
//
x4_the_ipsec_profile::x4_the_ipsec_profile()
{
  memset(&the_id, 0, sizeof(the_id));
  have_dynamic = false;
}

//
void x4_the_ipsec_profile::init()
{
  // reset 'unknowns'
  *this = x4_the_ipsec_profile();

  // generate ID
  generate(the_id);

  // initialize head
  initialize_base(head, head.class_name, &the_id);
  head.refresh_interval = 180*60;

  // initialize isakmp
  {
    x4_isakmp_sa sa;

    initialize_base(isakmp, isakmp.class_name);

    sa.cipher         = x4c_ipsec_des;
    sa.hash           = x4c_ipsec_sha1;
    sa.dhgroup        = x4c_ipsec_dh_med;
    sa.max_sa_count   = 0;              // see the comment in ipsec_types.h
    sa.rekey_interval = 28800;

    isakmp.methods.push_back(sa);
    isakmp.pfs_enabled = true32;
  }

  // cross-reference stuff
  cross_reference(isakmp, head, head.isakmp_policy);
}

//
const guid & x4_the_ipsec_profile::id() const
{
  return the_id;
}

//
void x4_the_ipsec_profile::config(x4e_cipher  cipher,
                                  x4e_hasher  hasher, 
                                  x4e_dhgroup dhgroup,
                                  uint        lifetime)
{
  x4_isakmp_sa & sa = isakmp.methods[0];

  sa.cipher  = (x4e_ipsec_alg)cipher;
  sa.hash    = (x4e_ipsec_alg)hasher;
  sa.dhgroup = (x4e_ipsec_alg)dhgroup;
  sa.rekey_interval = lifetime;
}

//
void x4_the_ipsec_profile::insert(const x4_ipsec_ts & l,
                                  const x4_ipsec_ts & r,
                                  uint8 proto,
                                  const ipv4 & gl,
                                  const ipv4 & gr,
                                  x4e_cipher  cipher,
                                  x4e_hasher  hasher,
                                  bool pfs,
                                  const char * psk,
                                  const char * ca)
{
  x4_ipsec_filters f_out, f_in;
  x4_ipsec_policy  pol;
  // can't memset classes
  // memset(&f_out, 0, sizeof(f_out));
  // memset(&f_in, 0, sizeof(f_in));
  // memset(&pol, 0, sizeof(pol));

  assert(is_zero_ipv4(gl) == is_zero_ipv4(gr));
  assert(psk && !ca || !psk && ca);

  // prepare traffic selector(s)
  {
    x4_ipsec_filter f;
	//memset(&f, 0, sizeof(f));

    f.mirrored = false32;
    f.protocol = proto;
    if (proto == 6 || proto == 17)
    {
      f.src_port = l.port;
      f.dst_port = r.port;
    }

    //
    initialize_base(f_out, f_out.class_name);

    generate(f.id);
    memmove(f.src_ip,   l.addr, 4);
    memmove(f.src_mask, l.mask, 4);
    memmove(f.dst_ip,   r.addr, 4);
    memmove(f.dst_mask, r.mask, 4);

    f_out.ipsec_name = "out " + f_out.ipsec_name;
    f_out.entries.push_back(f);

    //
    initialize_base(f_in, f_in.class_name);
    
    generate(f.id);
    memmove(f.src_ip,   r.addr, 4);
    memmove(f.src_mask, r.mask, 4);
    memmove(f.dst_ip,   l.addr, 4);
    memmove(f.dst_mask, l.mask, 4);
    f.src_port = r.port;
    f.dst_port = l.port;

    f_in.ipsec_name = "in " + f_in.ipsec_name;
    f_in.entries.push_back(f);
  }
  
  //
  // prepare ipsec policy
  //
  {
    x4_ipsec_sa sa;
	//memset(&sa, 0, sizeof(sa));

    initialize_base(pol, pol.class_name);

    sa.lifetime_secs = 0;
    sa.lifetime_bytes = 0;
    sa.pfs = pfs ? true32 : false32;
    sa.transform_count = 1;
    sa.transforms[0].alg1 = (x4e_ipsec_alg)cipher;
    sa.transforms[0].alg2 = (x4e_ipsec_alg)hasher;
    sa.transforms[0].type = x4c_ipsec_esp;

    pol.sas.push_back(sa);
    pol.action = x4c_ipsec_policy_ipsec;
    pol.type = x4c_ipsec_policy_type_static;
  }

  //
  // prepare nfa(s)
  //
  {
    x4_ipsec_nfa  n_out, n_in;
    x4_ipsec_auth a;
	//memset(&n_out, 0, sizeof(n_out));
	//memset(&n_in, 0, sizeof(n_in));
	//memset(&a, 0, sizeof(a));

    //
    if (psk)
    {
      a.type = x4c_ipsec_auth_psk;
      a.data = to_wstring(psk);
    }
    else
    {
      assert(ca);

      a.type = x4c_ipsec_auth_cert;
      a.data = to_wstring(ca);
    }

    //
    initialize_base(n_out, n_out.class_name);

    n_out.authenticators.push_back(a);
    n_out.conn_type = x4c_ipsec_conn_all;

    if (! is_zero_ipv4(gr))
    {
      memcpy(n_out.tunnel_endpoint, gr, 4);
      n_out.tunnel_enabled = true32;
	} else {
	  n_out.tunnel_enabled = false32;
	}

    // cross-reference
    cross_reference(f_out, n_out, n_out.filters);
    cross_reference(pol,   n_out, n_out.ipsec_policy);
    cross_reference(n_out, head,  head.nfas);

    // insert into lists
    nfas.push_back(n_out);

    //
    initialize_base(n_in, n_in.class_name);

    n_in.authenticators.push_back(a);
    n_in.conn_type = x4c_ipsec_conn_all;

    if (! is_zero_ipv4(gl))
    {
      memcpy(n_in.tunnel_endpoint, gl, 4);
      n_in.tunnel_enabled = true32;
	} else {
      n_in.tunnel_enabled = false32;
	}

    // cross-reference
    cross_reference(f_in,  n_in, n_in.filters);
    cross_reference(pol,   n_in, n_in.ipsec_policy);
    cross_reference(n_in,  head, head.nfas);

    // insert into lists
    nfas.push_back(n_in);
  }

  ipsec.push_back(pol);
  filters.push_back(f_out);
  filters.push_back(f_in);
}

void x4_the_ipsec_profile::insert_dynamic(x4e_cipher  cipher,
                                          x4e_hasher  hasher,
                                          bool pfs,
                                          const char * psk,
                                          const char * ca)
{
  /*
   * copy-paste of tweaked insert() for now .. 
   * until i have time to do it properly 
   */
  x4_ipsec_policy  pol;

  //
  assert(! have_dynamic);
  assert(psk && !ca || !psk && ca);

  have_dynamic = true; // allow no more than one dynamic rule per policy

  //
  // prepare ipsec policy
  //
  {
    x4_ipsec_sa sa;
    
    initialize_base(pol, pol.class_name);

    sa.lifetime_secs = 0;
    sa.lifetime_bytes = 0;
    sa.pfs = pfs ? true32 : false32;
    sa.transform_count = 1;
    sa.transforms[0].alg1 = (x4e_ipsec_alg)cipher;
    sa.transforms[0].alg2 = (x4e_ipsec_alg)hasher;
    sa.transforms[0].type = x4c_ipsec_esp;

    pol.sas.push_back(sa);
    pol.action = x4c_ipsec_policy_ipsec;
    pol.type = x4c_ipsec_policy_type_dynamic;
  }

  //
  // prepare nfa(s)
  //
  {
    x4_ipsec_nfa  nfa;
    x4_ipsec_auth a;

    //
    if (psk)
    {
      a.type = x4c_ipsec_auth_psk;
      a.data = to_wstring(psk);
    }
    else
    {
      assert(ca);

      a.type = x4c_ipsec_auth_cert;
      a.data = to_wstring(ca);
    }

    //
    initialize_base(nfa, nfa.class_name);

    nfa.authenticators.push_back(a);
    nfa.conn_type = x4c_ipsec_conn_all;
    nfa.tunnel_enabled = true32;
    nfa.static_rule = false32;

    // cross-reference
    cross_reference(pol, nfa,  nfa.ipsec_policy);
    cross_reference(nfa, head, head.nfas);

    // insert into lists
    nfas.push_back(nfa);
  }

  ipsec.push_back(pol);
}

/*void x4_the_ipsec_profile::insert(const ipv4 & src, const ipv4 & dst, const char * pass)
{
  x4_ipsec_filters flt_in, flt_out;
  x4_ipsec_nfa     nfa_in, nfa_out;

  // prepare flt_in, flt_out
  {
    x4_ipsec_filter f;

    initialize_base(flt_out, flt_out.class_name);

    generate(f.id);
    memcpy(f.src_ip, src, 4);
    memset(f.src_mask, 0xff, 4);
    memcpy(f.dst_ip, dst, 4);
    memset(f.dst_mask, 0xff, 4);

    flt_out.ipsec_name = "esp.tunnel.out." + 
                         to_string(src) + "." +
                         to_string(dst) + "." + flt_out.ipsec_name;
    flt_out.entries.push_back(f);

    initialize_base(flt_in, flt_in.class_name);

    generate(f.id);
    memcpy(f.src_ip, dst, 4);
    memcpy(f.dst_ip, src, 4);

    flt_in.ipsec_name = "esp.tunnel.in." + 
                         to_string(dst) + "." +
                         to_string(src) + "." + flt_out.ipsec_name;
    flt_in.entries.push_back(f);
  }

  // prepare nfa_in, nfa_out
  {
    x4_ipsec_auth a;

    initialize_base(nfa_out, nfa_out.class_name);

    a.type = x4c_ipsec_auth_psk;
    a.data = to_wstring(pass);

    nfa_out.authenticators.push_back(a);
    nfa_out.conn_type = x4c_ipsec_conn_all;

    memcpy(nfa_out.tunnel_endpoint, dst, 4);
    nfa_out.tunnel_enabled = true32;

    nfa_in = nfa_out;
    initialize_base(nfa_in, nfa_in.class_name);
    memcpy(nfa_in.tunnel_endpoint, src, 4);
  }

  // cross-reference
  cross_reference(flt_out, nfa_out, nfa_out.filters);
  cross_reference(ipsec,   nfa_out, nfa_out.ipsec_policy);
  cross_reference(nfa_out, head,    head.nfas);

  cross_reference(flt_in, nfa_in, nfa_in.filters);
  cross_reference(ipsec,  nfa_in, nfa_in.ipsec_policy);
  cross_reference(nfa_in, head,   head.nfas);

  // insert into lists
  nfas.push_back(nfa_out);
  nfas.push_back(nfa_in);

  filters.push_back(flt_out);
  filters.push_back(flt_in);
}
*/
//
// instantiation
//
x4_ipsec_profile * x4_ipsec_profile::instance()
{
  x4_the_ipsec_profile * p = new x4_the_ipsec_profile;

  return p ? (p->init(), p) : 0;
}

bool x4_register(x4_ipsec_profile * _h)
{
  x4_the_ipsec_profile * h = (x4_the_ipsec_profile *)_h;
  size_t i, n;
  bool   r = true;

  assert(h);

  for (i=0, n=h->filters.size(); i<n; i++)
    r &= policy_register(h->filters[i]);

  for (i=0, n=h->nfas.size(); i<n; i++)
    r &= policy_register(h->nfas[i]);

  for (i=0, n=h->ipsec.size(); i<n; i++)
    r &= policy_register(h->ipsec[i]);

  r &= policy_register(h->isakmp);

  r &= policy_register(h->head);

  if (! r)
  {
    x4_unregister(h->id());
    return false;
  } 

  return r;

}

bool x4_unregister(const guid & id)
{
  typedef std::pair<string, string>  cross_ref; // parent - child

  x4_reg_key k, kj;

  string             head_ref;
  vector<cross_ref>  refs;

  string             v;
  vector<string>     vmi, vmj;
  uint32             i, j, ni, nj;
  
  head_ref = x4_ipsec_base::_root + (x4_ipsec_bundle::class_name + to_string(id));

  if (! k.open(HKEY_LOCAL_MACHINE, head_ref, x4c_reg_key_open))
    return false;    

  if (k.value_get("ipsecISAKMPReference", v))
    if (kj.open(HKEY_LOCAL_MACHINE, v, x4c_reg_key_open))
      refs.push_back(cross_ref(head_ref, v));            // head - isakmp

  if (k.value_get("ipsecNFAReference", vmi))
    for (i=0, ni=vmi.size(); i<ni; i++)
      if (k.open(HKEY_LOCAL_MACHINE, vmi[i], x4c_reg_key_open))
      {
        refs.push_back(cross_ref(head_ref, vmi[i]));      // head - nfa

        if (k.value_get("ipsecFilterReference", vmj))
          for (j=0, nj=vmj.size(); j<nj; j++)
            if (kj.open(HKEY_LOCAL_MACHINE, vmj[j], x4c_reg_key_open))
              refs.push_back(cross_ref(vmi[i], vmj[j]));  // nfa - filter
        
        if (k.value_get("ipsecNegotiationPolicyReference", v))
          if (kj.open(HKEY_LOCAL_MACHINE, v, x4c_reg_key_open))
            refs.push_back(cross_ref(vmi[i], v));         // nfa - ipsec
      }

  // process cross_references
  // * check that 'child' has 'parent' in its 'ipsecOwnersReference'
  // * remove 'parent' reference from 'child.ipsecOwnersReference'
  // * remove 'child' if its 'ipsecOwnersReference' became empty
  for (i=0, ni=refs.size(); i<ni; i++)
    if (k.open(HKEY_LOCAL_MACHINE, refs[i].second, x4c_reg_key_open))
      if (k.value_get("ipsecOwnersReference", vmj))
      {
        for (j=0,nj=vmj.size(); j<nj; j++)
          if (vmj[j] == refs[i].first)
            break;

        if (j == nj) 
          continue;
          
        if (nj == 1) // last reference
        {
          x4_reg_key::remove(HKEY_LOCAL_MACHINE, refs[i].second);
          continue;
        }

        vmj.erase(vmj.begin()+j);
        k.value_set("ipsecOwnersReference", vmj);
      }

  // process head - ie remove it
  x4_reg_key::remove(HKEY_LOCAL_MACHINE, head_ref);

  return false;
}

//
// activation
//
bool x4_activate(const guid & id)
{
  x4_reg_key key;
  x4_service service;
  string     data;
  uint32     state;

  //
  // start IPsec service
  //
  if (! service.open("PolicyAgent", SERVICE_START | 
                                    SERVICE_QUERY_STATUS |
                                    SERVICE_USER_DEFINED_CONTROL))
    return false;

  if (! service.get_state(state))
    return false;

  if (state == SERVICE_STOPPED)
  {
    if (! service.start())
      return false;

    for (int i=0; i<10*20; i++) // wait 10 secs for service to come up
    {
      Sleep(50);
      if (! service.get_state(state))
        break;
      else
        if (state == SERVICE_RUNNING)
          break;
    }
  }

  if (state != SERVICE_RUNNING)
    return false;

  //
  // change key
  //
  if (! key.open(HKEY_LOCAL_MACHINE, x4_ipsec_base::_root))
    return false;

  data = x4_ipsec_base::_root + (x4_ipsec_bundle::class_name + to_string(id));

  if (! key.value_set("ActivePolicy", data))
    return false;

  //
  // notify service
  //
  if (! service.control(0x81))
    return false;

  return true;
}

//
bool x4_deactivate(const guid * id)
{
  x4_reg_key key;
  x4_service service;
  uint32     state;

  //
  // remove key
  //
  if (! key.open(HKEY_LOCAL_MACHINE, x4_ipsec_base::_root))
    return false;

  if (id)
  {
    string  data, active;

    data = x4_ipsec_base::_root + (x4_ipsec_bundle::class_name + to_string(*id));

    if (! key.value_get("ActivePolicy", active))
      return false;

    if (active != data)
      return false;
  }

  if (! key.value_remove("ActivePolicy"))
    return false;

  //
  // if IPsec service is running - notify it on the change
  //
  if (service.open("PolicyAgent", SERVICE_STOP |
                                  SERVICE_QUERY_STATUS |
                                  SERVICE_USER_DEFINED_CONTROL))
    if (service.get_state(state))
      if (state == SERVICE_RUNNING)
      {
        service.control(0x81);
        Sleep(500);
      }

  return true; 
}


//
//  -- local methods --
//
void initialize_base(x4_ipsec_base & b, const char * class_name, const guid * pid)
{
  guid   id;
  string ids;

  // fetch ID
  if (pid) id = *pid;
  else     generate(id);
  
  ids = to_string(id);

  b.description;                      //  apBlahDesc
  b.ipsec_id     = ids;               //  {72385235-70fa-11d1-864c-14a300000000}
  b.ipsec_name   = "x4 " + ids;       //  Comment
  b.name         = class_name + ids;  //  ipsecFilter{72385235-70fa-11d1-864c-14a300000000}
  b.last_changed = time(0);           //  1014057662
}

void cross_reference(x4_ipsec_base & child, x4_ipsec_base & parent, string & parent_ref)
{
  child.owners.push_back(x4_ipsec_base::_root + parent.name);
  parent_ref = x4_ipsec_base::_root + child.name;
}

void cross_reference(x4_ipsec_base & child, x4_ipsec_base & parent, vector<string> & parent_ref)
{
  string temp;
  cross_reference(child, parent, temp);
  parent_ref.push_back(temp);
}

//
//
//
bool policy_register_base(const x4_ipsec_base & a, const char * class_name, 
                          const buffer & ipsec_data, x4_reg_key & k)
{
  bool  r;

  if (! k.open(HKEY_LOCAL_MACHINE, x4_ipsec_base::_root + a.name, x4c_reg_key_create))
    return false;

  r = k.value_set("ClassName", string(class_name));
  
  if (! a.description.empty())
    r&= k.value_set("description", string(a.description));

  r &= k.value_set("ipsecData", ipsec_data);
  
  r &= k.value_set("ipsecDataType", a._type);

  r &= k.value_set("ipsecID", a.ipsec_id);

  if (! a.ipsec_name.empty())
    r &= k.value_set("ipsecName", a.ipsec_name);

  r &= k.value_set("name", a.name);

  if (! a.owners.empty())
    r &= k.value_set("ipsecOwnersReference", a.owners);

  r &= k.value_set("whenChanged", (uint32)time(0));

  return r;
}

bool policy_register(const x4_ipsec_filters & a)
{
  x4_reg_key k;
  buffer          id;
  
  serialize(id, a);

  return policy_register_base(a, a.class_name, id, k);
}

bool policy_register(const x4_ipsec_policy & a)
{
  x4_reg_key k;
  buffer          id;
  bool          r;
  
  serialize(id, a);

  r  = policy_register_base(a, a.class_name, id, k);
  r &= k.value_set("ipsecNegotiationPolicyAction", to_string(a.action));
  r &= k.value_set("ipsecNegotiationPolicyType", to_string(a.type));

  return r;
}

bool policy_register(const x4_ipsec_nfa & a)
{
  x4_reg_key k;
  buffer          id;
  bool          r;
  
  serialize(id, a);

  r  = policy_register_base(a, a.class_name, id, k);
  if (! a.filters.empty())
   r &= k.value_set("ipsecFilterReference", a.filters);
  r &= k.value_set("ipsecNegotiationPolicyReference", a.ipsec_policy);

  return r;
}

bool policy_register(const x4_isakmp_policy & a)
{
  x4_reg_key k;
  buffer          id;
  
  serialize(id, a);

  return policy_register_base(a, a.class_name, id, k);
}

bool policy_register(const x4_ipsec_bundle & a)
{
  x4_reg_key k;
  buffer        id;
  bool          r;
  
  serialize(id, a);

  r  = policy_register_base(a, a.class_name, id, k);
  r &= k.value_set("ipsecISAKMPReference", a.isakmp_policy);
  r &= k.value_set("ipsecNFAReference", a.nfas);

  return r;
}


