/*
 *  Support code used by rashelper to set up a shortcut.  Isolated to a separate
 *  file because setting up shortcuts is a pretty complicate undertaking.
 */

#include <objbase.h>
#include <stdio.h>
#include <windows.h>
#include <shlobj.h>
/*#include <afxwin.h>      CString, but this include is not available in VS express edition */
#include <comdef.h>
#include <comdefsp.h>
#include <shlwapi.h>     /* http://msdn2.microsoft.com/en-us/library/bb773426(VS.85).aspx */

/*
 *  Set up dialup shortcut when given an IShellLink and the name
 *  of the network connection.
 */
static int set_dialup_shortcut(IShellLink *psl, char *name) {
        int retval = -1;

        /* Bind to network connections folder */
        ITEMIDLIST *pidl1 = NULL;  
        IShellFolderPtr desktop, ncfolder;  
        SHGetFolderLocation(NULL, CSIDL_CONNECTIONS, NULL, 0, &pidl1);  
        SHGetDesktopFolder(&desktop);  
        desktop->BindToObject(pidl1, NULL, IID_IShellFolder, (void**)&ncfolder);  
  
        /* Enumerate subitems in the folder */
        IEnumIDListPtr items; 
        ncfolder->EnumObjects(NULL, SHCONTF_NONFOLDERS, &items);  
        ITEMIDLIST *pidl2 = NULL;  
  
        while (items->Next(1, &pidl2, NULL) == S_OK) {  
                STRRET sr = {STRRET_WSTR};  
  
                ncfolder->GetDisplayNameOf(pidl2, SHGDN_NORMAL, &sr);  
                char buf[MAX_PATH] = "";
                StrRetToBuf(&sr, pidl2, buf, MAX_PATH);  

                /* Compare network connections by name */
                if (strcmp(buf, name) == 0) {  
                        ITEMIDLIST* pidl3 = ILCombine(pidl1, pidl2);  

                        /* Found, create link: http://msdn2.microsoft.com/en-us/library/bb774950(VS.85).aspx */
                        psl->SetIDList(pidl3);  
                        ILFree(pidl3);  
                        pidl3 = NULL;
                        ILFree(pidl2);  
                        pidl2 = NULL;

                        retval = 0;
                        break;  
                }  
  
                ILFree(pidl2);  
                pidl2 = NULL;  
  
        }  
  
        ILFree(pidl1);  
        pidl1 = NULL;

        return retval;
}

/*
 *  Create a shell link (LNK, shortcut) to a network connection.
 *
 *  nFolder determines where the link will be placed:
 *
 *     CSIDL_STARTMENU
 *     CSIDL_PROGRAMS
 *     CSIDL_DESKTOP
 *
 *  link_name is the plain file name of the link (e.g. "My Connection.LNK").
 *
 *  connection_name is the name of the network connection.
 *
 *  Will overwrite an existing link silently, if one exists.
 *
 *  Return:
 *     0   success
 *  != 0   failure
 */
static int _create_shell_link_to_network_connection(int nFolder, char *link_name, char *connection_name) {
        int retval = -1;
        HRESULT hr = 0;
        LPMALLOC pMalloc = NULL;
        LPITEMIDLIST pidl = NULL;
        IPersistFile *ppf = NULL;
        IShellLink *psl = NULL;

        /* http://msdn2.microsoft.com/en-us/library/ms678543(VS.85).aspx */
        CoInitialize(NULL);

        /* IMalloc interface */
        hr = SHGetMalloc(&pMalloc);
        if (!SUCCEEDED(hr)) {
                goto cleanup;
        }

        /* Get a pointer to an item ID list that represents the path of a special folder */
        /* http://msdn2.microsoft.com/en-us/library/bb762203(VS.85).aspx */
        hr = SHGetSpecialFolderLocation(NULL, nFolder, &pidl);
        if (!SUCCEEDED(hr)) {
                goto cleanup;
        }

        /* Convert to a file system path */
        /* http://msdn2.microsoft.com/en-us/library/bb762194(VS.85).aspx */
        char szPath[_MAX_PATH];
        BOOL f = SHGetPathFromIDList(pidl, szPath);
        if (!f) {
                goto cleanup;
        }

        /* Determine final link filename (absolute path) */
        char *szLinkName = link_name;
        char *m_szCurrentDirectory = szPath;
        char szBuffer[1024];
        sprintf(szBuffer, "%s\\%s", m_szCurrentDirectory, szLinkName);

        /* Get a pointer to a IShellLink interface */
        hr = CoCreateInstance(CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, IID_IShellLink, (void **) (&psl));
        if (SUCCEEDED(hr)) {
                int rc;

                /* "Connect" shortcut to network connection */
                rc = set_dialup_shortcut(psl, connection_name);
                if (rc != 0) {
                        goto cleanup;
                }

                /* Query IShellLink for the IPersistFile interface for saving the shortcut */
                hr = psl->QueryInterface(IID_IPersistFile, (void **) (&ppf));

                /* Save the shortcut */
                if (SUCCEEDED(hr)) {
                        WCHAR wsz[MAX_PATH];
                        MultiByteToWideChar(CP_ACP, 0, szBuffer, -1, wsz, MAX_PATH);
                        hr = ppf->Save(wsz, TRUE);
                        if (SUCCEEDED(hr)) {
                                ;
                        } else {
                                goto cleanup;
                        }
                } else {
                        goto cleanup;
                }
        } else {
                goto cleanup;
        }

        retval = 0;
        /* fall through */

 cleanup:
        if (ppf) {
                ppf->Release();
                ppf = NULL;
        }
        if (psl) {
                psl->Release();
                psl = NULL;
        }
        if (pidl) {
                pMalloc->Free(pidl);
                pidl = NULL;
        }
        if (pMalloc) {
                /* Free our task allocator */
                pMalloc->Release();
                pMalloc = NULL;
        }
        return retval;
}

int create_shell_link_to_network_connection(int nFolder, char *link_name, char *connection_name) {
        return _create_shell_link_to_network_connection(nFolder, link_name, connection_name);
}

