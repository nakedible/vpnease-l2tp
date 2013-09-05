#ifndef _RASHELPER_H_
#define _RASHELPER_H_

// NOTE: Code assumes that UNICODE is not defined
#if defined(UNICODE) || defined(_UNICODE)
#error UNICODE or _UNICODE defined
#endif

// Set implicitly version number to get newest structures
// for the os detection code
#ifdef _WIN32_WINNT
#undef _WIN32_WINNT
#endif
#ifdef AUTOCONFIGURE_WIN2000
#define _WIN32_WINNT 0x0500   // Windows 2000
#else
#define _WIN32_WINNT 0x0502   // Windows XP SP2
#endif

#include <stdio.h>
#include <windows.h>
#include <ras.h>        // RASENTRY, RASCREDENTIALS
#include <rasdlg.h>     // RASDIALDLG
#include <raserror.h>   // RAS error codes
#include <shlobj.h>     // CSIDL_COMMON_APPDATA, SHGFP_TYPE_CURRENT

#define RASHELPER_REBOOT        1
#define RASHELPER_NO_REBOOT     0
#define RASHELPER_OK            0
#define RASHELPER_FAILED        -1

typedef enum _winversion {
        WV_UNKNOWN,
        WV_NT,                  // "Microsoft Windows NT"
        WV_2000,                // "Microsoft Windows 2000"
        WV_XPHOME,              // "Microsoft Windows XP Home Edition"
        WV_XPPRO,               // "Microsoft Windows XP Professional"
        WV_XP_x64,              // "Microsoft Windows XP Professional x64 Edition"
        WV_VISTA,               // "Windows Vista"
        WV_VISTA_x64,           // "Windows Vista (x64)"
        WV_LONGHORN,            // "Windows Server Longhorn"
        WV_SERVER2003,          // "Microsoft Windows Server 2003"
        WV_SERVER2003R2         // "Microsoft Windows Server 2003 R2"
} winversion_t;

/* Public API */

/*
 *  Detect current OS version and service pack number
 *
 *  Parameters
 *     version                 returns OS version type
 *     servicepack             returns service pack number
 *
 *  Return value
 *     RASHELPER_OK            detection ok
 *     RASHELPER_FAILED        detection failed
 */
int rashelper_detect_os(winversion_t *version, int *servicepack);

/*
 *  Set registry NAT-T value to new_value.
 *
 *  Parameters
 *     new_value               new value for registry
 *
 *  Return value
 *     RASHELPER_NO_REBOOT     no reboot needed (value in registry was same as new_value)
 *     RASHELPER_REBOOT        reboot needed, value changed
 *     RASHELPER_FAILED        registry modification failed
 */
int rashelper_change_natt_registry_value(int new_value);

/*
 *  Set registry prohibitIpsec (RASMAN) value to new_value.
 *
 *  Parameters
 *     new_value               new value for registry
 *
 *  Return value
 *     RASHELPER_NO_REBOOT     no reboot needed (value not changed or RASMAN restart OK)
 *     RASHELPER_REBOOT        reboot needed, value changed
 *     RASHELPER_FAILED        registry modification failed
 */
int rashelper_change_prohibitipsec_registry_value(int new_value);

/*
 *  Indicate whether caller should block forever instead of exiting
 *  after configuration is complete.  This is a workaround for keeping
 *  named mutex marker alive.
 *
 *  Return value
 *     1                       stay alive blocking forever
 *     0                       OK to exit
 */
int rashelper_need_to_block_forever(void);

/*
 *  Validate RAS phonebook entry
 * 
 *  Parameters
 *     entry_name              name of the phonebook entry
 *
 *  Return value
 *     ERROR_ALREADY_EXISTS           the entry name already exists in the specified phonebook
 *     ERROR_CANNOT_FIND_PHONEBOOK    the specified phonebook doesn't exist
 *     ERROR_INVALID_NAME             name of the entry is invalid
 */
int rashelper_validate_phonebook_entry(char *entry_name);

/*
 *  Create a new profile (don't check for existing profiles)
 *
 *  Parameters
 *    profile_name                 L2TP/IPsec profile name (shown in network control panel)
 *    desktop_shortcut_name        Name for the desktop shortcut, if its creation is requested
 *    server_address               Server domain name or IP address as a string
 *    preshared_key                IPsec pre-shared key (null-terminated string like others)
 *    username                     Username to configure into profile; if NULL, don't configure
 *    ppp_compression_enabled      If nonzero, enable PPP compression, otherwise disable
 *    default_route_enabled        If nonzero, enable 'default route' checkbox for profile,
 *                                 otherwise disable
 *    create_desktop_shortcut      If nonzero, create desktop shortcut, otherwise don't
 *    open_profile_after_creation  If nonzero, open profile after it has been created
 *
 *  Return value
 *    0 if success, -1 otherwise (XXX: error codes?)
 *    Potential Windows Error codes:
 *    ERROR_ACCESS_DENIED         The user does not have the correct privileges.
 *                                Only an administrator can complete this task. 
 *    ERROR_BUFFER_INVALID        The address or buffer specified by lpRasEntry is invalid. 
 *    ERROR_CANNOT_OPEN_PHONEBOOK The phone book is corrupted or missing components. 
 *    ERROR_INVALID_PARAMETER     The RASENTRY structure pointed to by the lpRasEntry parameter
 *                                does not contain adequate information.
 */
int rashelper_configure_profile(char *profile_name,
                                char *desktop_shortcut_name,
                                char *server_address,
                                char *preshared_key,
                                char *username,
                                int ppp_compression_enabled,
                                int default_route_enabled,
                                int create_desktop_shortcut,
                                int open_profile_after_creation);

/*
 *  Check whether a profile with selected values exists, and return the
 *  number of profiles matching criteria.
 *
 *  Each profile is compared against profile_name and/or server_address.
 *  If the caller supplies a NULL as either, the corresponding value is
 *  ignored when considering a profile.  (This means that if NULLs are
 *  given for all parameters, this function returns the total number of
 *  (relevant) profiles, regardless of their parameters.)
 *
 *  Parameters
 *    profile_name                 L2TP/IPsec profile name (shown in network control panel).
 *                                 If NULL, ignore in comparison.
 *    server_address               Server domain name or IP address as a string.
 *                                 If NULL, ignore in comparison.
 *
 *  Return value
 *    Number of matching profiles, 0 means no matching profiles found
 */
int rashelper_check_profiles(char *profile_name,
                             char *server_address);

/*
 *  Delete all profiles matching selected criteria.  Return the number
 *  of profiles deleted.
 *
 *  Parameters
 *    profile_name                 L2TP/IPsec profile name (shown in network control panel).
 *                                 If NULL, ignore in comparison.
 *    server_address               Server domain name or IP address as a string.
 *                                 If NULL, ignore in comparison.
 *
 *  Return value
 *    Number of matching (deleted) profiles, 0 means no matching profiles found
 */
int rashelper_delete_profiles(char *profile_name,
                              char *server_address);

/*
 *  Ask reboot from user.
 *
 *  Return value
 *    RASHELPER_NO_REBOOT             no reboot allowed
 *    RASHELPER_REBOOT                reboot allowed and executed
 *    RASHELPER_FAILED                dialog failed
 */
int rashelper_prompt_and_reboot(char *reason);

/*
 *  Show an error dialog with an OK button and text.
 *
 *  Parameters
 *    error_title                  Title for error message
 *    error_text                   Text for error message
 *
 *  Return value
 *    0 if success, -1 otherwise (XXX: error codes?)
 */
int rashelper_show_error_dialog(char *error_title, char *error_text);

/*
 *  Return last (Windows) error code
 *
 *  Parameters
 *
 *  Return value
 *    (windows error code, defined in winerror.h)
 */
int rashelper_get_last_error(void);

/*
 *  Re-enable critical service(s) if currently disabled.
 *
 *  Parameters
 *
 *  Return value
 *
 *     RASHELPER_REBOOT          required changes, reboot required
 *     RASHELPER_NO_REBOOT       required changes, reboot not required
 *     RASHELPER_OK              no changes required
 *     RASHELPER_FAILED          failed
 */
int rashelper_enable_critical_services(void);

/* Private utils */

typedef void (WINAPI *PGNSI)(LPSYSTEM_INFO);
typedef void (*callback_t)(void *userdata);

void __iterate_phonebook_entries(callback_t *callback, void *userdata);
int __get_default_phonebook(char *path);


#endif /* _RASHELPER_H_ */
