#include "rashelper.h"
#include "shortcut.h"
#include "vistanetwork.h"

#define VPNEASE_NATT_MARKER_MUTEX "Global\\VpneaseNattChangeMarker"

/*
 *  Global marker which indicates whether this process has created the
 *  VPNease mutex.  If so, main.cpp must "hang around" forever to ensure
 *  that the mutex remains active for other invokations to see.  This is
 *  rather ugly, but Windows doesn't provide good mechanisms which could
 *  act as a marker without resorting to file system or registry "temp"
 *  markers.
 */
static int _created_mutex = 0;
static HANDLE _global_mutex_handle = NULL;

int rashelper_need_to_block_forever(void) {
        return _created_mutex;
}

/*
 *  Check existence of named mutex; for mutex name spaces, see:
 *     http://msdn2.microsoft.com/en-us/library/ms684295(VS.85).aspx
 *
 *  Global mutex names should be used by default.
 */
static int _check_named_mutex(char *mutex_name) {
        HANDLE h = NULL;
        int retval = 0;

        /* http://msdn2.microsoft.com/en-us/library/ms684315(VS.85).aspx */
        h = OpenMutex(SYNCHRONIZE,    /* dwDesiredAccess */
                      FALSE,          /* bInheritHandle */
                      mutex_name      /* lpName */
                      );

        if (h == NULL) {
                DWORD err = GetLastError();

                if (err == ERROR_FILE_NOT_FOUND) {
                        // expected case
                        printf("_check_named_mutex(%s): mutex does not exist\n", mutex_name);
                } else {
                        // XXX: what to do here? now we pretend mutex doesn't exist
                        printf("_check_named_mutex(%s): unexpected error: %d\n", mutex_name, (int) err);
                }

                retval = 0;
                goto cleanup;
        }

        printf("_check_named_mutex(%s): mutex exists\n", mutex_name);

        retval = 1; /* exists */
        /* fall through */

 cleanup:
        if (h) {
                CloseHandle(h);
                h = NULL;
        }
        return retval;
}

// create named mutex, ignore "already exists" error
static int _create_named_mutex(char *mutex_name) {
        HANDLE h = NULL;
        int retval = -1;

        /* http://msdn2.microsoft.com/en-us/library/ms682411(VS.85).aspx  */
        /* NB: CreateMutexEx() only available in Vista, not in XP */
        h = CreateMutex(NULL,           /* lpMutexAttributes */
                        FALSE,          /* bInitialOwner */
                        mutex_name      /* lpName */
                        );
        
        if (h == NULL) {
                DWORD err = GetLastError();
                if (err == ERROR_ALREADY_EXISTS) {
                        printf("_create_named_mutex(%s): mutex already exists, ignoring\n", mutex_name);
                        retval = 0;
                } else {
                        printf("_create_named_mutex(%s): unexpected error: %d\n", mutex_name, (int) err);
                        retval = -1;
                }
                goto cleanup;
        }

        printf("_create_named_mutex(%s): mutex created, ok\n", mutex_name);
        _created_mutex = 1;
        _global_mutex_handle = h;
        retval = 0;

        /*
         *  NOTE!  We *must not* close the handle here.  Otherwise the
         *  mutex is again "forgotten".
         */
        return retval;

 cleanup:
        if (h) {
                CloseHandle(h);
                h = NULL;
        }
        return retval;
}


// http://support.microsoft.com/kb/885407/
// XXX - leaks registry key if exits prematurely, refactor with cleanup branch
int rashelper_change_natt_registry_value(int new_value)
{
        DWORD current_value;
        DWORD size;
        DWORD type;
        LONG ret;
        HKEY key;
        winversion_t version;
        int servicepack;
        char *regpath = NULL;
        char *value_name = "AssumeUDPEncapsulationContextOnSendRule";

        if (rashelper_detect_os(&version, &servicepack) != RASHELPER_OK) {
                return RASHELPER_FAILED;
        }

        if (version == WV_XPHOME || version == WV_XPPRO || version == WV_XP_x64) {
                regpath = "SYSTEM\\CurrentControlSet\\Services\\IPsec";
        } else if (version == WV_VISTA || version == WV_VISTA_x64) {
                regpath = "SYSTEM\\CurrentControlSet\\Services\\PolicyAgent";
        } else if (version == WV_2000) {
                // same as winxp
                regpath = "SYSTEM\\CurrentControlSet\\Services\\IPsec";
        } else {
                // unsupported OS - guess anyway
                regpath = "SYSTEM\\CurrentControlSet\\Services\\IPsec";
        }

        // Needs to be administrator priviledges to open this key
        // http://msdn2.microsoft.com/en-us/library/ms724897.aspx
        ret = RegOpenKeyEx(HKEY_LOCAL_MACHINE,
                        regpath,
                        0,
                        KEY_SET_VALUE | KEY_QUERY_VALUE,
                        &key);

        if (ret != NO_ERROR)
                return RASHELPER_FAILED;

        size = sizeof(DWORD);

        ret = RegQueryValueEx(key,
                              value_name,
                              NULL,
                              &type,
                              (LPBYTE)&current_value,
                              &size);
        
        /*
         * Not found, OK, set anyway - the "not set" value is the same as
         * the value 0, i.e., requires reboot if changed (to nonzero).
         */
        if (ret == ERROR_FILE_NOT_FOUND) {
                current_value = 0;
        } else if (ret != NO_ERROR) {
                return RASHELPER_FAILED;
        } else {
                // NO_ERROR
                ;
        }

        printf("Changing NAT-T registry value: %d -> %d\n", current_value, new_value);

        ret = RegSetValueEx(key,
                            value_name,
                            0,
                            REG_DWORD,
                            (BYTE *)&new_value,
                            sizeof(new_value));

        RegCloseKey(key);

        /*
         *  Reboot handling is a bit complicated.
         *
         *  First, we now set the registry value regardless of whether the
         *  existing value is correct or not.  So, we get here on every run.
         *
         *  Second, to solve some nasty corner cases (explained below), we
         *  use a named mutex always to mark that a reboot *MAY* be required.
         *  This marker is set, and is sticky, whenever the registry value
         *  is changed, which ensures that if the value is changed on a run
         *  where reboot is not necessary (server is not behind port fwd), while
         *  the value is *not* changed on a subsequent run where reboot would
         *  be necessary (server is behind port fwd), we don't miss the reboot
         *  on the second run.
         *
         *  The corner case which must be solved:
         *
         *    1. Server is not behind port forwarding, user autoconfigures,
         *       registry value is changed, but reboot is not required.
         *
         *    2. User configures another profile using autoconfigure,
         *       registry value is not changed (already correct), but
         *       kernel IPsec is still running with wrong setting.  Here
         *       we need to reboot, even though the value was not changed
         *       on this particular run.
         *
         */
        if (current_value != new_value) {
                if (_check_named_mutex(VPNEASE_NATT_MARKER_MUTEX)) {
                        /* already exists, don't bother */
                        printf("nat-t value changed but mutex exists, not creating\n");
                } else {
                        // XXX: ignore retval
                        printf("nat-t value changed and mutex does not exist, creating\n");
                        _create_named_mutex(VPNEASE_NATT_MARKER_MUTEX);
                }
        }

        /*
         *  Reboot if mutex exists *or* value changed (paranoia).
         *
         *  Note that 'reboot' here means that caller should reboot if
         *  server is behind port forwarding, it's not an absolute
         *  judgment at this point.
         */
        if (_check_named_mutex(VPNEASE_NATT_MARKER_MUTEX)) {
                printf("named mutex exists, returning RASHELPER_REBOOT\n");
                return RASHELPER_REBOOT;
        } else if (current_value != new_value) {
                // some error dealing with mutex, signal reboot
                printf("named mutex check failed, but value changed, returning RASHELPER_REBOOT\n");
                return RASHELPER_REBOOT;
        } else {
                printf("named mutex does not exist and value not changed, returning RASHELPER_NO_REBOOT\n");
                return RASHELPER_NO_REBOOT;
        }
}

static int _restart_rasman(void)
{
        /*
         *  XXX - Restarting a service is not trivial in Windows.  Stopping a
         *  service requires handling of dependent services, polling for service
         *  state etc.  See: http://msdn2.microsoft.com/en-us/library/ms686335(VS.85).aspx.
         *
         *  Currently we just force a reboot instead.
         */

        return -1;
}

// XXX - leaks registry key if exits prematurely, refactor with cleanup branch
int rashelper_change_prohibitipsec_registry_value(int new_value)
{
        DWORD current_value;
        DWORD size;
        DWORD type;
        LONG ret;
        HKEY key;
        winversion_t version;
        int servicepack;
        char *regpath = NULL;
        char *value_name = "prohibitIpsec";

        if (rashelper_detect_os(&version, &servicepack) != RASHELPER_OK)
                return RASHELPER_FAILED;

        if (version == WV_XPHOME || version == WV_XPPRO || version == WV_XP_x64) {
                regpath = "SYSTEM\\CurrentControlSet\\Services\\RasMan\\Parameters";
        } else if (version == WV_VISTA || version == WV_VISTA_x64) {
                regpath = "SYSTEM\\CurrentControlSet\\Services\\RasMan\\Parameters";
        } else if (version == WV_2000) {
                // same as winxp
                regpath = "SYSTEM\\CurrentControlSet\\Services\\RasMan\\Parameters";
        } else {
                // unsupported OS - guess anyway
                regpath = "SYSTEM\\CurrentControlSet\\Services\\RasMan\\Parameters";
        }

        // Needs to be administrator priviledges to open this key
        // http://msdn2.microsoft.com/en-us/library/ms724897.aspx
        ret = RegOpenKeyEx(HKEY_LOCAL_MACHINE,
                           regpath,
                           0,
                           KEY_SET_VALUE | KEY_QUERY_VALUE,
                           &key);

        if (ret != NO_ERROR)
                return RASHELPER_FAILED;

        size = sizeof(DWORD);

        ret = RegQueryValueEx(key,
                              value_name,
                              NULL,
                              &type,
                              (LPBYTE)&current_value,
                              &size);

        /*
         * Not found, OK, set anyway - the "not set" value is the same as
         * the value 0.  Reboot is not required if new_value is zero.
         */
        if (ret == ERROR_FILE_NOT_FOUND) {
                current_value = 0;
        } else {
                if (ret != NO_ERROR || type != REG_DWORD) {
                        return RASHELPER_FAILED;
                }

                if (current_value == new_value) {
                        return RASHELPER_NO_REBOOT;
                }
        }

        printf("Changing prohibitIpsec registry value: %d -> %d\n", current_value, new_value);

        ret = RegSetValueEx(key,
                            value_name,
                            0,
                            REG_DWORD,
                            (BYTE *)&new_value,
                            sizeof(new_value));

        RegCloseKey(key);

        if (current_value != new_value) {
                // if value changed, attempt RASMAN restart to avoid reboot
                if (_restart_rasman() != 0) {
                        return RASHELPER_REBOOT;
                }
                return RASHELPER_NO_REBOOT;
        } else {
                // this case only occurs when prohibitIpsec did not previously exist
                // and was set to the default value (0).
                return RASHELPER_NO_REBOOT;
        }
}

int rashelper_validate_phonebook_entry(char *entry_name)
{
        DWORD nRet = 0;
                
        // NULL as a phonebook uses default user selected phonebook file, usually:
        // C:\Documents and Settings\All Users\Application Data\Microsoft\Network\Connections\Pbk\rasphone.pbk
        nRet = RasValidateEntryName(NULL, entry_name);

        return nRet;
}

/*
 *  XXX - currently fails badly (without useful error) if VPN profile already
 *  exists and is active (connected).
 */
int rashelper_configure_profile(char *profile_name,
                                char *desktop_shortcut_name,
                                char *server_address,
                                char *preshared_key,
                                char *username,
                                int ppp_compression_enabled,
                                int default_route_enabled,
                                int create_desktop_shortcut,
                                int open_profile_after_creation)
{
        RASCREDENTIALS Credentials = {0};
        RASDIALDLG RasDlg = {0};
        RASENTRY RasEntry = {0};
        RASENTRY RasEntry2 = {0};
        DWORD dwErr = NO_ERROR;
        DWORD dwSize;
        int retval = RASHELPER_FAILED;

        printf("rashelper_configure_profile: starting\n");

        // validate entry, if one exists or entry is invalid this fails
        dwErr = rashelper_validate_phonebook_entry(profile_name);
        
        if (dwErr != NO_ERROR)
                return dwErr;

        printf("rashelper_configure_profile: phonebook validation step OK\n");

        // Define RASENTRY for RAS Phonebook
        // http://msdn2.microsoft.com/en-us/library/aa377274.aspx
        RasEntry.dwSize                 = sizeof(RASENTRY);
        RasEntry.dwType                 = RASET_Vpn;
        RasEntry.dwVpnStrategy          = VS_L2tpOnly;
        RasEntry.dwEncryptionType       = ET_Require;
        RasEntry.dwfNetProtocols        = RASNP_Ip;
        // XXX: other options like RASEO_IpHeaderCompression (may be set by default), RASEO_RequireEncryptedPw (?)
        RasEntry.dwfOptions             = RASEO_RequireMsEncryptedPw | RASEO_RequireDataEncryption | RASEO_PreviewUserPw | RASEO_ShowDialingProgress | RASEO_ModemLights;
#ifndef AUTOCONFIGURE_WIN2000
	/* XP and upwards */
	RasEntry.dwfOptions2            = RASEO2_UsePreSharedKey | RASEO2_ReconnectIfDropped | RASEO2_DontNegotiateMultilink;
	RasEntry.dwRedialCount          = 50;
	RasEntry.dwRedialPause          = 10;
#endif
        RasEntry.dwSubEntries           = 0;
        RasEntry.dwDialMode             = 0;
        strcpy(RasEntry.szDeviceType, RASDT_Vpn);
        strcpy(RasEntry.szLocalPhoneNumber, server_address);

        /*
         *  XXX: This doesn't work in Windows XP.  The failure is related to the following
         *  registry key: HKEY_LOCAL_MACHINE\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters,
         *  value DontAddDefaultGatewayDefault (normally set to 0).  This value needs to be 1 for
         *  this setting to have an effect, but we'd have to modify and restore the value.
         *
         *  Because we always want default route enabled, there's no point in fixing this bug
         *  now.
         */

        if (default_route_enabled)
        {
                RasEntry.dwfOptions |= RASEO_RemoteDefaultGateway;
        }

        if (ppp_compression_enabled)
        {
                RasEntry.dwfOptions |= RASEO_SwCompression;
        }

        printf("rashelper_configure_profile: creating ras entry to phonebook\n");

        // Create RAS Entry to phonebook
        // http://msdn2.microsoft.com/en-us/library/aa377827.aspx
        dwErr = RasSetEntryProperties(NULL, profile_name, &RasEntry, sizeof(RASENTRY), NULL, 0);
        if (dwErr != NO_ERROR) {
                retval = RASHELPER_FAILED;
                goto cleanup;
        }
        printf("RasSetEntryProperties() successful\n");

        /*
         *  Read properties back, we want the actual device name
         */
        RasEntry2.dwSize = sizeof(RASENTRY);
        dwSize = sizeof(RASENTRY);
        dwErr = RasGetEntryProperties(NULL, profile_name, &RasEntry2, &dwSize, NULL, 0);
        if (dwErr != NO_ERROR) {
                retval = RASHELPER_FAILED;
                goto cleanup;
        }
        printf("deviceName: %s\n", RasEntry2.szDeviceName);
        
        // Set pre-shared key
        // http://msdn2.microsoft.com/en-us/library/aa377811.aspx
        Credentials.dwSize = sizeof(RASCREDENTIALS);
        Credentials.dwMask = RASCM_PreSharedKey;
        strcpy(Credentials.szPassword, preshared_key);  // FIXME: check copy size

        dwErr = RasSetCredentials(NULL, profile_name, &Credentials, FALSE);

        if (dwErr != NO_ERROR) {
                retval = RASHELPER_FAILED;
                goto cleanup;
        }

        if (username != NULL)
        {
                memset(&Credentials, 0, sizeof(RASCREDENTIALS));

                Credentials.dwSize = sizeof(RASCREDENTIALS);
                Credentials.dwMask = RASCM_UserName;
                strcpy(Credentials.szUserName, username);

                dwErr = RasSetCredentials(NULL, profile_name, &Credentials, FALSE);

                if (dwErr != NO_ERROR) {
                        retval = RASHELPER_FAILED;
                        goto cleanup;
                }
        }

        if (create_desktop_shortcut)
        {
                int rc;

                rc = create_shell_link_to_network_connection(CSIDL_DESKTOP,
                                                             desktop_shortcut_name, 
                                                             profile_name);
                if (rc != 0) {
                        // FIXME: ignore error, this is best effort now?
                        ;
                }
        }

        /*
         *  Vista "set network type" fix is not possible at this, commented out
         *  because this does not work.
         */
#if 0
        /* FIXME: this is too early, the Network List Manager has not "seen" the connection yet */
        if (1) {
                int rc;

                rc = set_vista_network_type(profile_name);
                printf("__set_vista_network_type() returned %d\n", rc);
        }
#endif

        if (open_profile_after_creation)
        {
            HWND wnd = NULL;

                /* http://msdn2.microsoft.com/en-us/library/aa377023(VS.85).aspx */
                /* just in case */
                memset(&RasDlg, 0x00, sizeof(RASDIALDLG));

                /*
                 *  Find foreground window in an attempt to avoid opening the RAS
                 *  dialog to "background" in Windows Vista SP0.
                 */
        
                /* http://msdn2.microsoft.com/en-us/library/ms633505(VS.85).aspx */
                wnd = GetForegroundWindow();
                if (wnd == NULL) {
                        /* OK, not really fatal */
                        printf("rashelper_configure_profile(): cannot open temporary window\n");
                        ;
                }

                /*
                 *  Call RasDialDlg().  See:
                 *
                 *    http://msdn2.microsoft.com/en-us/library/aa377020.aspx
                 *
                 *  RasDlg.hwndOwner could be NULL (no window to which the dialog
                 *  is attached), but without an underlying "on the top" window, the
                 *  dialog can go to the background.  So we try to use the foreground
                 *  window (but fail gracefully if it is not available).  This fix
                 *  seems to be only required in Windows Vista (not in Windows XP SP2).
                 */

                RasDlg.dwSize = sizeof(RASDIALDLG);
                RasDlg.hwndOwner = wnd;
                if (!RasDialDlg(NULL, profile_name, NULL, &RasDlg))
                {
                        /*
                         *  RasDlg.dwError == 0 => user cancel.  However, basically all
                         *  errors here should be ignored: we've already got the profile
                         *  configured, so an error saying "cannot configure profile"
                         *  would be incorrect.
                         */
#if 0                           
                        if (RasDlg.dwError != 0) {
                                /* Zero is apparently user cancel */
                                SetLastError(RasDlg.dwError);
                                retval = RASHELPER_FAILED;
                                goto cleanup;
                        }
#endif
                }
        }

                /*
                 *  FIXME: this is a temporary hack test.  We're racing Vista to set the
                 *  network category (after dialup connection is complete; whose success
                 *  we don't currently check for).  Ultimately we'd need to implement the
                 *  INetworkEvents API and get callbacks for new networks and run the
                 *  whole thing from there.
                 *
                 *  Most disappointing of all, even this racy version doesn't work, so
                 *  this part is disabled entirely :-(
                 */
#if 0
                for (int i = 0; i < 50; i++) {
                        Sleep(200);

                        if (1) {
                                int rc;
                                
                                rc = set_vista_network_type(profile_name);
                                printf("set_vista_network_type() returned %d\n", rc);
                        }
                }
#endif

        retval = RASHELPER_OK;
        /* fall through */

 cleanup:
        return retval;
}

/*
 *  XXX: currently only uses profile_name, not server_address
 */
#define  RAS_LOOP_COUNT  5
int rashelper_check_profiles(char *profile_name,
                             char *server_address)
{
        RASENTRYNAME *entries = NULL;
        DWORD cb = sizeof(RASENTRYNAME);
        DWORD numEntries;
        int rc;
        int retval = 0;
        int matches = 0;
        int i;

        printf("rashelper_check_profiles: first LocalAlloc\n");

        /* http://msdn2.microsoft.com/en-us/library/aa366597(VS.85).aspx */
                entries = (RASENTRYNAME *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, cb);

        if (!entries) {
                        goto cleanup;
        }
        entries->dwSize = sizeof(RASENTRYNAME);

        /* http://msdn2.microsoft.com/en-us/library/aa920280.aspx */
        if (RasEnumEntries(NULL, NULL, entries, &cb, &numEntries) == ERROR_BUFFER_TOO_SMALL) {
                /* allocate larger buffer */
                if (entries) {
                                                HeapFree(GetProcessHeap(), 0, entries);
                                                entries = NULL;
                }

                printf("rashelper_check_profiles: second LocalAlloc, size %d\n", cb);

                entries = (RASENTRYNAME *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, cb);
                if (!entries) {
                        goto cleanup;
                }
                entries->dwSize = sizeof(RASENTRYNAME);
        }

        printf("rashelper_check_profiles: second RasNumEntries\n");

        /* actual call */
        for (i = 0; i < RAS_LOOP_COUNT; i++) {
                /*
                 *  Why do we loop here?  The MSDN documentation indicates that this
                 *  might be smart.  Further, when prohibitIpsec registry value has
                 *  been changed or created, the call seems to fail at first for
                 *  some unfathomable reason, with error 632 (invalid struct size);
                 *  this seems completely incorrect from Windows, but in this loop
                 *  we don't care what fails.
                 *
                 */
                rc = RasEnumEntries(NULL, NULL, entries, &cb, &numEntries);
                if (rc == ERROR_SUCCESS) {
                        break;
                }
                printf("rashelper_check_profiles: RasEnumEntries failed with rc %d, ignoring this round (sleep & retry)\n", rc);
                Sleep(1000);
        }
        if (rc != ERROR_SUCCESS) {
                printf("rashelper_check_profiles: RasEnumEntries failed, %d\n", rc);
                goto cleanup;
        }

        printf("Found %d RAS entries\n", numEntries);

        for (i = 0; i < numEntries; i++) {
                printf("RAS entry %d: %s\n", i, entries[i].szEntryName);
                if (strcmp(entries[i].szEntryName, profile_name) == 0) {
                        matches ++;
                }
        }

        retval = matches;

        /* fall through */
 cleanup:
        if (entries) {
                HeapFree(GetProcessHeap(), 0, entries);
                entries = NULL;
        }
        return retval;
}

/*
 *  XXX: currently only uses profile_name, not server_address
 */
int rashelper_delete_profiles(char *profile_name,
                              char *server_address)
{
        int rv;

        /* http://msdn2.microsoft.com/en-us/library/aa376739(VS.85).aspx */

        rv = RasDeleteEntry(NULL, profile_name);
        if (rv == ERROR_SUCCESS) {
                return 1;
        } else {
                return 0;
        }
}

int rashelper_detect_os(winversion_t *version, int *servicepack)
{
        OSVERSIONINFOEX osvi;
        SYSTEM_INFO si;
        PGNSI pGNSI;
        BOOL bOsVersionInfoEx;

        ZeroMemory(&si, sizeof(SYSTEM_INFO));
        ZeroMemory(&osvi, sizeof(OSVERSIONINFOEX));

        *version = WV_UNKNOWN;
        *servicepack = 0;

        // Try calling GetVersionEx using the OSVERSIONINFOEX structure.
        // If that fails, try using the OSVERSIONINFO structure.

        osvi.dwOSVersionInfoSize = sizeof(OSVERSIONINFOEX);

        // http://msdn2.microsoft.com/en-us/library/ms724451.aspx
        if (!(bOsVersionInfoEx = GetVersionEx((OSVERSIONINFO *) &osvi)))
        {
                osvi.dwOSVersionInfoSize = sizeof (OSVERSIONINFO);
                if (!GetVersionEx((OSVERSIONINFO *)&osvi)) 
                        return RASHELPER_FAILED;
        }

        // Call GetNativeSystemInfo if supported or GetSystemInfo otherwise.
        // GetNativeSystemInfo gives correct info when executable running on WOW64
        // http://msdn2.microsoft.com/en-us/library/aa384249.aspx - WOW64
        // http://msdn2.microsoft.com/en-us/library/ms724340.aspx - GetNativeSystemInfo
        // http://msdn2.microsoft.com/en-us/library/ms724381.aspx - GetSystemInfo

        pGNSI = (PGNSI) GetProcAddress(GetModuleHandle(TEXT("kernel32.dll")),
                                                                   "GetNativeSystemInfo");
        if (pGNSI != NULL)
                pGNSI(&si);
        else
                GetSystemInfo(&si);

        switch (osvi.dwPlatformId)
        {
                // Test for the Windows NT product family.

        case VER_PLATFORM_WIN32_NT:

                // Test for the specific product.

                if ( osvi.dwMajorVersion == 6 && osvi.dwMinorVersion == 0 )
                {
                        if( osvi.wProductType == VER_NT_WORKSTATION )
                        {
                                if (si.wProcessorArchitecture==PROCESSOR_ARCHITECTURE_AMD64)
                                        *version = WV_VISTA_x64;
                                else
                                        *version = WV_VISTA;
                        }
                        else
                        {
                                *version = WV_LONGHORN;
                        }
                }

#ifndef AUTOCONFIGURE_WIN2000  /* Does not compile for Windows 2000, but doesn't matter */
                if ( osvi.dwMajorVersion == 5 && osvi.dwMinorVersion == 2 )
                {
                        // http://msdn2.microsoft.com/en-us/library/ms724385.aspx
                        if( GetSystemMetrics(SM_SERVERR2) )
                                *version = WV_SERVER2003R2;
                        else if( osvi.wProductType == VER_NT_WORKSTATION &&
                                     si.wProcessorArchitecture==PROCESSOR_ARCHITECTURE_AMD64)
                        {
                                *version = WV_XP_x64;
                        }
                        else
                        {
                                *version = WV_SERVER2003;
                        }
                }
#endif

                if ( osvi.dwMajorVersion == 5 && osvi.dwMinorVersion == 1 )
                {
                        if ( osvi.wSuiteMask & VER_SUITE_PERSONAL )
                                *version = WV_XPHOME;
                        else
                                *version = WV_XPPRO;
                }

                if ( osvi.dwMajorVersion == 5 && osvi.dwMinorVersion == 0 )
                        *version = WV_2000;

                if ( osvi.dwMajorVersion <= 4 )
                        *version = WV_NT;
        }

        *servicepack = osvi.wServicePackMajor;

        return RASHELPER_OK;
}

int rashelper_show_error_dialog(char *error_title, char *error_text)
{
        return MessageBox(NULL, error_text, error_title, MB_OK | MB_ICONERROR);
}

int rashelper_prompt_and_reboot(char *reason)
{
        HANDLE hToken; 
        TOKEN_PRIVILEGES tkp; 
        DWORD ret;

        ret = MessageBox(NULL, reason, "Reboot Required", MB_YESNO | MB_ICONQUESTION);

        if (ret == IDNO)
                return RASHELPER_NO_REBOOT;

        if (ret == IDYES)
        {
                // Get a token for this process. 
                if (!OpenProcessToken(GetCurrentProcess(), 
                        TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, &hToken)) 
                        return RASHELPER_FAILED; 

                // Get the LUID for the shutdown privilege. 
                LookupPrivilegeValue(NULL, SE_SHUTDOWN_NAME, 
                        &tkp.Privileges[0].Luid); 

                tkp.PrivilegeCount = 1;  // one privilege to set    
                tkp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED; 

                // Get the shutdown privilege for this process. 
                AdjustTokenPrivileges(hToken, FALSE, &tkp, 0, 
                        (PTOKEN_PRIVILEGES)NULL, 0); 

                if (GetLastError() != ERROR_SUCCESS) 
                        return RASHELPER_FAILED; 

                // Shut down the system
                //  EWX_REBOOT | EWX_FORCE, - if needed more power
                if (!ExitWindowsEx(EWX_REBOOT, 
                                SHTDN_REASON_MAJOR_SOFTWARE |
                                SHTDN_REASON_FLAG_PLANNED)) 
                        return RASHELPER_FAILED;

                return RASHELPER_REBOOT;
        }

        return RASHELPER_FAILED;
}

int rashelper_get_last_error(void)
{
        return GetLastError();
}

/*
 *  See:
 *    - http://msdn2.microsoft.com/en-us/library/ms685141(VS.85).aspx
 */
int rashelper_enable_critical_services(void)
{
        SC_HANDLE mgr = NULL;
        SC_HANDLE h = NULL;
        int i;
        int ret;
        int rv = RASHELPER_FAILED;
        int changes_made = 0;
        int reboot_required = 0;
        winversion_t version;
        int servicepack;
        char **critical_services = NULL;
        char *services_winxp[] = { "PolicyAgent",   /* IPSEC Services */
                                   "RasMan",        /* Remote Access Connection Manager */
                                   NULL };
        char *services_vista[] = { "PolicyAgent",   /* IPsec Policy Agent */
                                   "IKEEXT",        /* IKE and AuthIP IPsec Keying Modules */
                                   "RasMan",        /* Remote Access Connection Manager */
                                   NULL };

        if (rashelper_detect_os(&version, &servicepack) != RASHELPER_OK) {
                return RASHELPER_FAILED;
        }

        if (version == WV_XPHOME || version == WV_XPPRO || version == WV_XP_x64) {
                critical_services = services_winxp;
        } else if (version == WV_VISTA || version == WV_VISTA_x64) {
                critical_services = services_vista;
        } else if (version == WV_2000) {
                // same as winxp
                critical_services = services_winxp;
        } else {
                // unknown, guess winxp
                critical_services = services_winxp;
        }

        /* http://msdn2.microsoft.com/en-us/library/ms684323(VS.85).aspx */
        mgr = OpenSCManager(NULL, SERVICES_ACTIVE_DATABASE, SC_MANAGER_ALL_ACCESS);
        if (!mgr) {
                rv = RASHELPER_FAILED;
                goto fail;
        }

        /* Loop through services; enable all services required in the list */
        for (i = 0; critical_services[i] != NULL; i++) {
                char buf[8192];   /* see QueryServiceConfig API, rough solution */
                LPQUERY_SERVICE_CONFIG cfg = (LPQUERY_SERVICE_CONFIG) &buf;
                DWORD bytesNeeded;
                DWORD oldStartType;
                DWORD newStartType;

                printf("rashelper_enable_critical_services(): checking %s\n", critical_services[i]);

                /* http://msdn2.microsoft.com/en-us/library/ms684330(VS.85).aspx */
                h = OpenService(mgr, critical_services[i], SC_MANAGER_ALL_ACCESS);
                if (!h) {
                        rv = RASHELPER_FAILED;
                        goto fail;
                }

                /* http://msdn2.microsoft.com/en-us/library/ms684932(VS.85).aspx */
                ret = QueryServiceConfig(h, (LPQUERY_SERVICE_CONFIG) buf, sizeof(buf), &bytesNeeded);
                if (ret == 0) {
                        rv = RASHELPER_FAILED;
                        goto fail;
                }
                /* NB: cleaner approach in: http://msdn2.microsoft.com/en-us/library/ms684928(VS.85).aspx */

                /* http://msdn2.microsoft.com/en-us/library/ms684950(VS.85).aspx */
                oldStartType = cfg->dwStartType;
                if (oldStartType != SERVICE_AUTO_START) {
                        printf("rashelper_enable_critical_services(): service %s does not have autostart, fixing\n", critical_services[i]);

                        /* http://msdn2.microsoft.com/en-us/library/ms681987(VS.85).aspx */
                        ret = ChangeServiceConfig(h,                           /* hService */
                                                  SERVICE_NO_CHANGE,           /* dwServiceType */
                                                  SERVICE_AUTO_START,          /* dwStartType */
                                                  SERVICE_NO_CHANGE,           /* dwErrorControl */
                                                  NULL,                        /* lpBinaryPathName */
                                                  NULL,                        /* lpLoadOrderGroup */
                                                  NULL,                        /* lpdwTagId */
                                                  NULL,                        /* lpDependencies */
                                                  NULL,                        /* lpServiceStartName */
                                                  NULL,                        /* lpPassword */
                                                  NULL                         /* lpDisplayName */
                                                  );
                        if (ret == 0) {
                                rv = RASHELPER_FAILED;
                                goto fail;
                        }
                                            
                        changes_made = 1;
                }

                /* http://msdn2.microsoft.com/en-us/library/ms684932(VS.85).aspx */
                ret = QueryServiceConfig(h, (LPQUERY_SERVICE_CONFIG) buf, sizeof(buf), &bytesNeeded);
                if (ret == 0) {
                        rv = RASHELPER_FAILED;
                        goto fail;
                }
                /* NB: cleaner approach in: http://msdn2.microsoft.com/en-us/library/ms684928(VS.85).aspx */

                /* recheck startup */
                newStartType = cfg->dwStartType;
                if (newStartType != SERVICE_AUTO_START) {
                        rv = RASHELPER_FAILED;
                        goto fail;
                }

                /* http://msdn2.microsoft.com/en-us/library/ms686321(VS.85).aspx */
                ret = StartService(h, NULL, NULL);
                if (ret == 0) {
                        switch(GetLastError()) {
                        case ERROR_SERVICE_ALREADY_RUNNING:
                                /* OK, no panic */
                                printf("rashelper_enable_critical_services(): service %s already running\n", critical_services[i]);
                                break;
                        case ERROR_SERVICE_DISABLED:
                                /* OK, reboot assumedly required */
                                printf("rashelper_enable_critical_services(): service %s start failed, disabled -> reboot\n", critical_services[i]);
                                reboot_required = 1;
                                break;
                        default:
                                /* Not sure, assume reboot required? */
                                printf("rashelper_enable_critical_services(): service %s start failed (unknown error %d) -> reboot\n", critical_services[i], ret);
                                reboot_required = 1;
                                break;
                        }
                } else {
                        printf("rashelper_enable_critical_services(): service %s started successfully\n", critical_services[i]);
                }

                /* --- at this point service startup is OK, service is running OR reboot_required=1 --- */

                /* http://msdn2.microsoft.com/en-us/library/ms682028(VS.85).aspx */
                CloseServiceHandle(h);
                h = NULL;
        }

        if (reboot_required) {
                rv = RASHELPER_REBOOT;
        } else if (changes_made) {
                rv = RASHELPER_NO_REBOOT;
        } else {
                rv = RASHELPER_OK;
        }

 fail:
        if (h) {
                /* http://msdn2.microsoft.com/en-us/library/ms682028(VS.85).aspx */
                CloseServiceHandle(h);
                h = NULL;
        }
        if (mgr) {
                CloseServiceHandle(mgr);
                mgr = NULL;
        }
        return rv;
}


// Private functions

static int __get_default_phonebook(char *path)
{
        HRESULT hRes;

        hRes = SHGetFolderPath(NULL, CSIDL_COMMON_APPDATA, NULL, SHGFP_TYPE_CURRENT, path);

        return hRes;
}

//typedef void (*callback_t)(void *userdata);

static void __iterate_phonebook_entries(callback_t *callback, void *userdata)
{
}
