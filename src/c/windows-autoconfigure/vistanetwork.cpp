#include <stdio.h>
#include <netlistmgr.h>

#include "rashelper.h"

/*
 *  Working with BSTRs is a PITA.  Google for lots of examples.
 *
 *  This is a poor man's BSTR -> ASCII converter (our profile
 *  names are never non-ASCII currently, so this is OK).
 */

static int _BSTR_to_ascii(BSTR bstring, char **output) {
        int nameLen = SysStringLen(bstring);
        char *tempString = (char *) malloc(nameLen + 1);
        if (!tempString) {
                return -1;
        }
        memset(tempString, 0x00, nameLen + 1);
        for (int i = 0; i < nameLen; i++) {
                int ch = bstring[i];
                if (ch > 0x7f) {
                        tempString[i] = '?';
                } else {
                        tempString[i] = (char) ch;
                }
        }
        *output = tempString;
        return 0;
}


/*
 *  Vista normally opens an annoying popup asking for a "network type".
 *  This can be prevented, see:
 *
 *    * http://windowshelp.microsoft.com/Windows/en-US/Help/6ddfa83c-01c8-441e-b041-1fd912c3fe601033.mspx
 *    * http://www.microsoft.com/communities/newsgroups/list/en-us/default.aspx?dg=microsoft.public.windowsnt.protocol.ras&tid=5fc01392-8d76-4000-af45-c4c1216e3486&p=1
 *    * http://www.vistax64.com/vista-networking-sharing/39847-set-network-location.html
 *    * http://msdn2.microsoft.com/en-us/library/aa370790(VS.85).aspx
 *
 *  Solutions include: system-wide disabling, user-wide disabling, and use of the
 *  INetwork::SetCategory COM function (Network List Manager) to change the
 *  category for one specific interface.
 */

int set_vista_network_type(char *profile_name) {
        INetworkListManager *pNetworkListManager = NULL; 
        IEnumNetworks *pEnumNetworks = NULL;
        INetwork *pNetwork = NULL;
        IEnumNetworkConnections *pEnumNetworkConnections = NULL;
        INetworkConnection *pNetworkConnection = NULL;
        BSTR networkName = NULL;
        BSTR networkDescription = NULL;
        char *tempString = NULL;

        winversion_t osVersion = (winversion_t) 0;
        int osServicePack = 0;
        int rc;
        int retval = -1;

        /*
         *  OS check
         */
        rc = rashelper_detect_os(&osVersion, &osServicePack);

        printf("set_vista_network_type(): os=%d, sp=%d\n", osVersion, osServicePack);
        if (!((osVersion == WV_VISTA_x64) ||
              (osVersion == WV_VISTA) ||
              (osVersion == WV_LONGHORN))) {
                printf("set_vista_network_type(): not vista\n");
                retval = 0;
                goto cleanup;
        }

        /*
         *  Network List Manager init
         */
        printf("set_vista_network_type(): attempting to CoCreateInstance()\n");

        /* http://msdn2.microsoft.com/en-us/library/ms686615(VS.85).aspx */
        rc = CoCreateInstance(CLSID_NetworkListManager, NULL,
                              CLSCTX_ALL, IID_INetworkListManager,
                              (LPVOID *)&pNetworkListManager);
        
        printf("set_vista_network_type(): --> %d\n", rc);

        if (!SUCCEEDED(rc)) {
                goto cleanup;
        }

        /*
         *  Enumerate networks
         */

        printf("set_vista_network_type(): attempting to GetNetworks()\n");

        /* http://msdn2.microsoft.com/en-us/library/aa370776(VS.85).aspx */
        rc = pNetworkListManager->GetNetworks(NLM_ENUM_NETWORK_ALL, &pEnumNetworks);

        printf("set_vista_network_type(): --> %d\n", rc);
        
        if (!SUCCEEDED(rc)) {
                goto cleanup;
        }

        /* http://msdn2.microsoft.com/en-us/library/aa370715(VS.85).aspx */
        while (pEnumNetworks->Next(1, &pNetwork, NULL) == S_OK) {
                printf("set_vista_network_type(): enumerated one network\n");
                
                rc = pNetwork->GetNetworkConnections(&pEnumNetworkConnections);
                if (!SUCCEEDED(rc)) {
                        goto cleanup;
                }
        
                while (pEnumNetworkConnections->Next(1, &pNetworkConnection, NULL) == S_OK) {
                        GUID adapterId;
                        pNetworkConnection->GetAdapterId(&adapterId);

                        printf("set_vista_network_type(): enumerated one network connection, guid %08lx-%04lx-%04lx-%02x%02x%02x%02x%02x%02x%02x%02x\n",
                                (unsigned long) adapterId.Data1,
                                (unsigned long) adapterId.Data2,
                                (unsigned long) adapterId.Data3,
                                (int) adapterId.Data4[0],
                                (int) adapterId.Data4[1],
                                (int) adapterId.Data4[2],
                                (int) adapterId.Data4[3],
                                (int) adapterId.Data4[4],
                                (int) adapterId.Data4[5],
                                (int) adapterId.Data4[6],
                                (int) adapterId.Data4[7]);

                        pNetworkConnection->Release();
                        pNetworkConnection = NULL;
                }

                /* GetName() is not meaningful, in that the result does not match
                 * the profile name user sees.
                 */
                rc = pNetwork->GetName(&networkName);
                if (!SUCCEEDED(rc)) {
                        goto cleanup;
                }
                rc = _BSTR_to_ascii(networkName, &tempString);
                if (rc != 0) {
                        goto cleanup;
                }
                printf ("set_vista_network_type(): netname='%s'\n", tempString);
                free(tempString);
                tempString = NULL;
                SysFreeString(networkName);
                networkName = NULL;

                /*
                 *  GetDescription() matches what user sees, so this is out point of comparison.
                 *
                 *  Unfortunately there can be multiple matches (even deleted profiles turn up
                 *  with the same description).  Here we set the category if the profile does
                 *  not have a current category.
                 *
                 *  XXX: how to detect this accurately?
                 */
                rc = pNetwork->GetDescription(&networkName);
                if (!SUCCEEDED(rc)) {
                        goto cleanup;
                }
                rc = _BSTR_to_ascii(networkName, &tempString);
                if (rc != 0) {
                        goto cleanup;
                }
                printf ("set_vista_network_type(): description='%s'\n", tempString);

                if (strcmp(tempString, profile_name) == 0) {
                        printf("set_vista_network_type(): matching profile found!\n");

                        NLM_NETWORK_CATEGORY netCategory = (NLM_NETWORK_CATEGORY) 0;
                        rc = pNetwork->GetCategory(&netCategory);
                        printf("set_vista_network_type(): current category: %d\n", netCategory);

                        if (netCategory == 0) {
                                /* networks apparently start with 0 (public), so assume user hasn't touched */
                                rc = pNetwork->SetCategory(NLM_NETWORK_CATEGORY_PRIVATE);  // trusted network
                                if (!SUCCEEDED(rc)) {
                                        goto cleanup;
                                }
                                printf("set_vista_network_type(): network type set to private successfully\n");
                        } else {
                                printf("set_vista_network_type(): category is not 'public', not touching\n");
                        }
                }

                free(tempString);
                tempString = NULL;
                SysFreeString(networkName);
                networkName = NULL;

                pNetwork->Release();
                pNetwork = NULL;
        }

        retval = 0;
        /* fall through */

 cleanup:
        if (tempString) {
                free(tempString);
                tempString = NULL;
        }
        if (networkDescription) {
                SysFreeString(networkDescription);
                networkDescription = NULL;
        }
        if (networkName) {
                SysFreeString(networkName);
                networkName = NULL;
        }
        if (pNetworkConnection) {
                pNetworkConnection->Release();
                pNetworkConnection = NULL;
        }
        if (pEnumNetworkConnections) {
                pEnumNetworkConnections->Release();
                pEnumNetworkConnections = NULL;
        }
        if (pNetwork) {
                pNetwork->Release();
                pNetwork = NULL;
        }
        if (pEnumNetworks) {
                pEnumNetworks->Release();
                pEnumNetworks = NULL;
        }
        if (pNetworkListManager) {
                pNetworkListManager->Release();
                pNetworkListManager = NULL;
        }
        return retval;
}
