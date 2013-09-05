
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "parameters.h"
#include "rashelper.h"

/* NB: don't want to refer to drive letter */
#define WINDOWS2000_REGISTRY_TEMPFILE "\\vpnease-temp.reg"
#define WINDOWS2000_REGFILE_MAX_WAIT_MS (60 * 1000)

static int nybble_to_int(char c) {
	if (c >= '0' && c <= '9') {
		return c - '0' + 0;
	} else if (c >= 'a' && c <= 'f') {
		return c - 'a' + 0x0a;
	} else if (c >= 'A' && c <= 'F') {
		return c - 'A' + 0x0a;
	}
	return -1;
}

static void usage_and_exit(int argc, char *argv[]) {
	printf("Usage:\n");
	printf("    %s --help\n", argv[0]);
	printf("    %s [--set param=value]* --show-parameters\n", argv[0]);
	printf("    %s [--set param=value]*\n", argv[0]);
	printf("\n");
	printf("Supported parameters for 'running' (last form) are:\n");
	printf("\n");
	printf("   Configuring a profile\n");
	printf("       operation                    configure_profile\n");
	printf("       profile_name                 <string>\n");
	printf("       desktop_shortcut_name        <string>\n");
	printf("       server_address               <string>\n");
	printf("       preshared_key                <string>\n");
	printf("       username                     <string>\n");
	printf("       win2k_registry_file          <string>\n");
	printf("       ppp_compression_enabled      <0|1>\n");
	printf("       default_route_enabled        <0|1>\n");
	printf("       create_desktop_shortcut      <0|1>\n");
	printf("       open_profile_after_creation  <0|1>\n");
	printf("       server_behind_port_forward   <0|1>\n");
	exit(1);
}

static void show_params_and_exit(void) {
	int i;

	for (i = 0; ; i++) {
		char *key;
		char *value;

		get_parameter_by_index(i, &key, &value);
		if (key && value) {
			printf("Parameter %d: %s=%s\n", i, key, value);
		} else {
			break;
		}
	}
	exit(1);
}

static void parse_and_process_args(int argc, char *argv[]) {
	int i;

	for (i = 1; i < argc; ) {
		if (strcmp(argv[i], "--show-parameters") == 0) {
			show_params_and_exit();
		} else if (strcmp(argv[i], "--set") == 0) {
			char *key;
			char *value;

			i++;
			if (i >= argc) {
				goto fail;
			}

			// XXX: strtok is deprecated, strok_s is preferred.
			// http://msdn2.microsoft.com/en-us/library/2c8d19sb(VS.80).aspx
			key = strtok(argv[i], "=");
			value = strtok(NULL, "\x00");

			if (!key || !value) {
				goto fail;
			}

			if (set_parameter(key, value) != 0) {
				printf("Cannot set parameter %s to %s (maybe out of space)\n", key, value);
				goto fail;
			}
			i++;
		} else if (strcmp(argv[i], "--help") == 0) {
			goto fail;
		} else {
			printf("Invalid option: %s\n", argv[i]);
			goto fail;
		}
	}

	return;
 fail:
	usage_and_exit(argc, argv);
}

static int _do_natt_registry_change(int *reboot_required,
				    char *server_behind_port_forward) {
	int rc;
	printf("*** Registry change - NATT\n");

	rc = rashelper_change_natt_registry_value(2);   /* 2 is correct for NAT-T enable for both XP and Vista */
	if (rc == RASHELPER_FAILED) {
		printf("rashelper_change_natt_registry_value() failed: %d\n", rc);
		goto fail;
	} else if (rc == RASHELPER_NO_REBOOT) {
		printf("rashelper_change_natt_registry_value() did not request a reboot\n");
	} else if (rc == RASHELPER_REBOOT) {
		/* reboot at this stage only if server is behind port forward */
		if (atoi(server_behind_port_forward) != 0) {
#ifndef AUTOCONFIGURE_WIN2000
			/* For XP and Vista */
			printf("rashelper_change_natt_registry_value() requested a reboot, and server behind port forward => reboot\n");
			*reboot_required = 1;
#endif
		} else {
			printf("rashelper_change_natt_registry_value() requested a reboot, but server not behind port forward\n");
		}
	} else {
		printf("Unknown return value from rashelper_change_natt_registry_value(): %d\n", rc);
		goto fail;
	}

	return 0;
 fail:
	return -1;
}

static int _do_prohibitipsec_registry_change(int *reboot_required) {
	int rc;

	printf("*** Registry change - prohibitIpsec\n");

#ifdef AUTOCONFIGURE_WIN2000
	rc = rashelper_change_prohibitipsec_registry_value(1);   /* 0 = "prohibit" IPsec for RasMan */
#else
	rc = rashelper_change_prohibitipsec_registry_value(0);   /* 0 = "allow" IPsec for RasMan */
#endif
	if (rc == RASHELPER_FAILED) {
		printf("rashelper_change_prohibitipsec_registry_value() failed: %d\n", rc);
		goto fail;
	} else if (rc == RASHELPER_NO_REBOOT) {
			;
	} else if (rc == RASHELPER_REBOOT) {
		*reboot_required = 1;
	} else {
		printf("Unknown return value from rashelper_change_prohibitipsec_registry_value(): %d\n", rc);
		goto fail;
	}

	return 0;
 fail:
	return -1;
}

static int _do_critical_services_fixup(int *reboot_required) {
	int rc;

	printf("*** Enable critical services\n");

	rc = rashelper_enable_critical_services();
	if (rc == RASHELPER_FAILED) {
		printf("rashelper_enable_critical_services() failed: %d\n", rc);
		goto fail;
	} else if (rc == RASHELPER_NO_REBOOT) {
		;
	} else if (rc == RASHELPER_REBOOT) {
		*reboot_required = 1;
	} else if (rc == RASHELPER_OK) {
		;
	} else {
		printf("Unknown return value from rashelper_enable_critical_services(): %d\n", rc);
	}

	return 0;
 fail:
	return -1;
}

#ifdef AUTOCONFIGURE_WIN2000
static int _do_win2k_ipsec_registry(int *reboot_required,
				    char *win2k_registry_file) {
	FILE *f = NULL;
	char *p = NULL;
	int clen = 0;
	int failed = 0;

	/*
	 *  Sanity check and write Windows 2000 registry data to a temp file
	 *
	 *  Data is UTF16 little-end, BOM is 0xff 0xfe, hex encoded 'fffe'
	 */
	if (!win2k_registry_file) {
		goto bad_data;
	}
	if (strlen(win2k_registry_file) < 4) {
		goto bad_data;
	}
	if ((win2k_registry_file[0] != 'f') ||
	    (win2k_registry_file[1] != 'f') ||
	    (win2k_registry_file[2] != 'f') ||
	    (win2k_registry_file[3] != 'e')) {
		goto bad_data;
	}

	p = win2k_registry_file;
	clen = strlen(p) / 2;
		
	printf("win2k registry data looks ok, writing to temp file\n");
		
	f = fopen(WINDOWS2000_REGISTRY_TEMPFILE, "wb");
	if (!f) {
		goto fail;
	}

	int i;
	for (i = 0; i < clen; i++) {
		int i0 = nybble_to_int(p[i*2 + 0]);
		int i1 = nybble_to_int(p[i*2 + 1]);
		char ch;
		
		if (i0 < 0 || i1 < 0) {
				failed = 1;
				break;
		}
		ch = (char) (i0*16 + i1);
		fwrite(&ch, sizeof(ch), 1, f);
	}
	fclose(f);
	f = NULL;
		
	if (failed) {
		goto fail;
	}

	/*
	 *  Shell execute registry file to activate it (causes two user prompts)
	 */
	printf("win2k registry data write OK, shellexecuting\n");
	
	/* Need to use ShellExecuteEx() so that we can wait for completion */
	BOOL res;
	SHELLEXECUTEINFO execInfo;
			
	/* http://msdn2.microsoft.com/en-us/library/bb759784(VS.85).aspx */
	memset(&execInfo, 0, sizeof(execInfo));
	execInfo.cbSize = sizeof(execInfo);
	execInfo.fMask = SEE_MASK_NOCLOSEPROCESS;
	execInfo.hwnd = NULL;
	execInfo.lpVerb = "open";
	execInfo.lpFile = WINDOWS2000_REGISTRY_TEMPFILE;
	execInfo.lpParameters = NULL;
	execInfo.lpDirectory = NULL;
	execInfo.nShow = SW_SHOW;
	execInfo.hInstApp = 0;      /* output */
	execInfo.lpIDList = NULL;
	execInfo.lpClass = NULL;
	execInfo.hkeyClass = NULL;
	execInfo.dwHotKey = 0;
	execInfo.hMonitor = NULL;
	execInfo.hProcess = NULL;   /* output */
			
	/* http://msdn2.microsoft.com/en-us/library/bb762154(VS.85).aspx */
	res = ShellExecuteEx(&execInfo);
	if ((res == TRUE) && (((int) execInfo.hInstApp) > 32)) {
		printf("shellexecuteex() successful, wait for completion\n");
		
		if (execInfo.hProcess) {
			DWORD ret;

			printf("going to waitforsingleobject\n");

			/* http://msdn2.microsoft.com/en-us/library/ms687032(VS.85).aspx */
			ret = WaitForSingleObject(execInfo.hProcess,               /* hHandle */
						  WINDOWS2000_REGFILE_MAX_WAIT_MS  /* dwMilliseconds */
						  );
			printf("waitforsingleobject -> %d\n", ret);
			/* FIXME: check result? */
		} else {
			printf("no process handle to wait for\n");
		}
	} else {
		printf("shellexecuteex() failed, hInstApp=%d\n", (int) execInfo.hInstApp);
		/* FIXME: goto fail? */
	}
	
	/* cleanup */
	if (execInfo.hProcess) {
		CloseHandle(execInfo.hProcess);
	}
	memset(&execInfo, 0, sizeof(execInfo));

	/*
	 *  At this point we would need to "assign" the IPsec policy.  Without that,
	 *  the IPsec policy won't be active even if the registry is in good shape.
	 *  That's because the "activation" part of the IPsec policy (which transfers
	 *  data from the registry to kernel and IKE) is missing.
	 *
	 *  Current workaround: force a reboot.  This causes Windows to re-read the
	 *  IPsec policy information on the next reboot, effectively assigning the
	 *  policy.
	 *
	 *  The policy is assigned by the IPsec 2000 library by restarting the
	 *  PolicyAgent (IKE) service.  This is what we should do here.
	 */
	*reboot_required = 1;

	/* done */
	return 0;

       	/*
	 *  FIXME: delete temp file?
	 */

	/*
	 *  FIXME: policy is not assigned at this stage, so we're forcing a reboot
	 *  at the moment to have the same effect without further Windows IPsec
	 *  integration.
	 */
	       
 bad_data:
	printf("win2k registry data write failed, broken hex encoding?\n");
	return 0;

 fail:
	return -1;
}
#endif  /* #ifdef AUTOCONFIGURE_WIN2000 */


static int _do_cleanup_and_configure_profile(int *reboot_required,
					     char *profile_name,
					     char *server_address,
					     char *open_profile_after_creation,
					     char *desktop_shortcut_name,
					     char *preshared_key,
					     char *username,
					     char *ppp_compression_enabled,
					     char *default_route_enabled,
					     char *create_desktop_shortcut) {
    int rc;
    int open_profile;
	
    printf("*** Check and delete existing profiles\n");

	rc = rashelper_check_profiles(profile_name, server_address);
	if (rc > 0) {
		/* Delete existing profiles with same server address */
		printf("old profiles found, deleting\n");
		rc = rashelper_delete_profiles(profile_name, server_address);
	}
#if 0  /* unnecessary check */
	rc = rashelper_check_profiles(profile_name, server_address);
	if (rc > 0) {
		rc = rashelper_show_error_dialog("Failed to create profile",
						 "Failed to delete an existing profile with the same VPN server address");
		printf("Attempted to delete a profile with the same server address, but profile still exists after delete\n");
		goto fail;
	}
#endif

	printf("*** Creating new profile\n");
	open_profile = atoi(open_profile_after_creation);
	if (*reboot_required) {
		/* if reboot required, no use opening the profile */
		open_profile = 0;
	}
	rc = rashelper_configure_profile(profile_name,
					 desktop_shortcut_name,
					 server_address,
					 preshared_key,
					 username,
					 atoi(ppp_compression_enabled),
					 atoi(default_route_enabled),
					 atoi(create_desktop_shortcut),
					 open_profile);
	if (rc != 0) {
		printf("rashelper profile configuration failed\n");
		goto fail;
	}

	return 0;
 fail:
	return -1;
}

static int _do_mutex_workaround(int *reboot_required) {
#ifndef AUTOCONFIGURE_WIN2000
	printf("*** Named mutex workaround check\n");
	if (rashelper_need_to_block_forever()) {
		printf("rashelper indicates that we need to block forever...\n");
		
		for (;;) {
			// sleep 24h at a time
			printf("sleeping...\n");
			Sleep(24 * 60 * 60 * 1000);
		}
	}
#endif
	return 0;
}

static void run_operation(int argc, char *argv[]) {
	int rc;
	char *operation = NULL;
	char *profile_name = NULL;
	char *desktop_shortcut_name = NULL;
	char *server_address = NULL;
	char *preshared_key = NULL;
	char *username = NULL;
	char *ppp_compression_enabled = NULL;
	char *default_route_enabled = NULL;
	char *create_desktop_shortcut = NULL;
	char *open_profile_after_creation = NULL;
	char *server_behind_port_forward = NULL;
	char *win2k_registry_file = NULL;
	int reboot_required = 0;
	int open_profile = 0;

	/*
	 *  Normal case: run, checking 'operation' parameter for what to do
	 */

	operation = get_parameter("operation");
	profile_name = get_parameter("profile_name");
	desktop_shortcut_name = get_parameter("desktop_shortcut_name");
	server_address = get_parameter("server_address");
	preshared_key = get_parameter("preshared_key");
	username = get_parameter("username");
	ppp_compression_enabled = get_parameter("ppp_compression_enabled");
	default_route_enabled = get_parameter("default_route_enabled");
	create_desktop_shortcut = get_parameter("create_desktop_shortcut");
	open_profile_after_creation = get_parameter("open_profile_after_creation");
	server_behind_port_forward = get_parameter("server_behind_port_forward");
	win2k_registry_file = get_parameter("win2k_registry_file");

	if (!operation) {
		printf("No operation specified\n");
		goto fail;
	} else if (strcmp(operation, "configure_profile") == 0) {
		/*
		 *  Parameter sanity
		 */
		if (!profile_name || !desktop_shortcut_name || !server_address || !preshared_key || !username ||
		    !ppp_compression_enabled || !default_route_enabled || !create_desktop_shortcut || !open_profile_after_creation ||
		    !server_behind_port_forward) {
			printf("Missing one or more parameters for configure_profile\n");
			goto fail;
		}

		/*
		 *  Registry change - NATT
		 *
		 *  Not really needed for Windows 2000; we do it anyway but don't require
		 *  a reboot in this case.
		 */
		if (_do_natt_registry_change(&reboot_required,
					     server_behind_port_forward) < 0) {
			goto fail;
		}

		/*
		 *  Registry change - prohibitIpsec
		 *
		 *  For Windows XP and Vista, set prohibitIpsec to 0 so that Rasman can create
		 *  an IPsec policy dynamically.  For Windows 2000, set to 1 so that assigned
		 *  policy ("manually created") works.
		 */
		if (_do_prohibitipsec_registry_change(&reboot_required) < 0) {
			goto fail;
		}

		/*
		 *  L2TP/IPsec related services running and startup mode fixed
		 */
		if (_do_critical_services_fixup(&reboot_required) < 0) {
			goto fail;
		}

#ifdef AUTOCONFIGURE_WIN2000
		/*
		 *  Windows 2000 - registry changes
		 */
		if (_do_win2k_ipsec_registry(&reboot_required,
					     win2k_registry_file) < 0) {
			goto fail;
		}
#endif

		/*
		 *  FIXME: On Windows 2000 we should set the MTU of the PPP interface
		 *  manually.  How to do that?  This is a pretty straightforward
		 *  reference:
		 *
		 *  http://support.microsoft.com/kb/q120642/
		 *
		 *  but where to get the adapter ID?  Further, it seems that even if
		 *  a new VPN profile is added, no new adapter appears in the TCP/IP
		 *  registry branch.
		 */

		/*
		 *  Check and remove existing overlapping profiles; configure new profile
		 */
		if (_do_cleanup_and_configure_profile(&reboot_required,
						      profile_name,
						      server_address,
						      open_profile_after_creation,
						      desktop_shortcut_name,
						      preshared_key,
						      username,
						      ppp_compression_enabled,
						      default_route_enabled,
						      create_desktop_shortcut
						      ) < 0) {
			goto fail;
		}

		/*
		 *  Reboot if required
		 */
		printf("*** Reboot required check\n");
		if (reboot_required) {
			rc = rashelper_prompt_and_reboot("Your computer needs to be restarted before the VPN connection can be used.  "
							 "Reboot now?");
			/* XXX: ignore rc */
		} else {
			;
		}

		/*
		 *  To work around corner cases of NAT-T reboot avoidance, we use
		 *  a named mutex inside rashelper.cpp to signal that NAT-T registry
		 *  value was changed but reboot not done.
		 *
		 *  However, named mutexes disappear from the system namespace unless
		 *  at least one process is holding the mutex alive.  So, this function
		 *  in rashelper indicates whether we, at the end of the autoconfigure
		 *  process, should stick around keeping the mutex alive.  Quite ugly.
		 *
		 *  XXX: remove if persistent mechanism found.
		 */
		if (_do_mutex_workaround(&reboot_required) < 0) {
			goto fail;
		}

		/*
		 *  All done
		 */
		printf("*** All done\n");
	} else {
		printf("Invalid operation: %s\n", operation);
		goto fail;
	}

	return;
 fail:
	rc = rashelper_show_error_dialog("VPN configuration failed",
					 "VPNease failed to autoconfigure your VPN profile. "
					 "Please check that you have administrative privileges and try again.\n\n"
					 "If the problem persists, please configure the VPN profile manually.");
	/* ignore rc */

	usage_and_exit(argc, argv);
}

int __cdecl main(int argc, char *argv[]) {
	parse_and_process_args(argc, argv);
	run_operation(argc, argv);

	/*
	 *  FIXME: windows 2000 does not seem to exit properly?
	 *  See task manager process list.  Now that we reboot,
	 *  it doesn't really matter.
	 */
}

/* Wrapper for use when application type is set to WINDOWS.  We need to parse
 * command line manually because lpCmdLine is a single string containing the
 * arguments (not process name).  There is an existing function to do this in
 * Win32, but it only works for Unicode command line arguments.
 */

/* http://msdn2.microsoft.com/en-us/library/ms633559(VS.85).aspx */
#define ARGV_SIZE 256
int WINAPI WinMain(HINSTANCE hInstance,
				   HINSTANCE hPrevInstance,
				   LPSTR lpCmdLine,
				   int nShowCmd) {
	char *writableCopy;
	char argc = 0;
	char *argv[ARGV_SIZE] = { NULL };
	int retval = -1;
	int i;

	// strtok requires writable string
	writableCopy = strdup(lpCmdLine);
	if (!writableCopy) {
		goto cleanup;
	}

	argv[argc++] = "dummy";  // program name

	for(;;) {
		char *arg;
		char *tmp;
		if (argc == 1) {
			arg = strtok(lpCmdLine, "\x20\x09");
		} else {
			arg = strtok(NULL, "\x20\x09");
		}
		if (arg == NULL) {
			argv[argc] = NULL;
			break;
		}

		tmp = strdup(arg);
		if (!tmp) {
			goto cleanup;
		}

		argv[argc++] = tmp;
	}

	retval = main(argc, argv);

 cleanup:
	if (writableCopy) {
		free(writableCopy);
		writableCopy = NULL;
	}
	for (i = 0; i < ARGV_SIZE; i++) {
		if (argv[i] == NULL) {
			break;
		}
		free(argv[i]);
		argv[i] = NULL;
	}
	return retval;
}

