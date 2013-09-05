#ifndef _CPHL_IPSEC_MISC_H_
#define _CPHL_IPSEC_MISC_H_

#include "ipsec_types.h"
#include "buffer"

//
// serializes 'ipsecData' portion of apXxx structures
//
void serialize(buffer & , const x4_ipsec_filters & );
void serialize(buffer & , const x4_ipsec_policy & );
void serialize(buffer & , const x4_ipsec_nfa & );
void serialize(buffer & , const x4_isakmp_policy & );
void serialize(buffer & , const x4_ipsec_bundle & );

#endif
