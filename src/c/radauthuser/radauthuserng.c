/*
 *  Minimal command line RADIUS authentication for VPNease.  Uses
 *  Radisuclient configuration to authenticate a user for e.g. web UI.
 *
 *  Performs RADIUS authentication (with service type 'auth only'.
 *  If authentication is successful, prints 'OK' and exits with code 0.
 *  If authentication failed, prints 'FAIL' and exits code 1.
 *  In case a response message is received (with or without error),
 *  attributes from the message are printed which allow us to determine
 *  e.g. user permissions (for instance, is user allowed web UI admin
 *  access).  Higher exit codes are internal errors.
 *
 *  Based on radiusclient's radexample.c.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <radiusclient-ng.h>

#define RC_CONFIG_FILE "/var/run/l2tpgw/radiusclient-ng/radiusclient-ng.conf"
#define MAX_USERNAME_LENGTH 128
#define MAX_PASSWORD_LENGTH 128

void _hexencode(char *buf, int buflen, void *data, int datalen) {
	int i;
	int i_max = (buflen - 1) / 2;
	int dlen = datalen;
	unsigned char *p = (unsigned char *) data;

	for(i = 0; i < i_max; i++) {
		unsigned char t;

		if (dlen <= 0) {
			break;
		}
		dlen--;

		t = p[i];
		sprintf(&buf[i*2], "%02x", (int) t);
	}

	buf[i*2] = 0x00;
}

void _print_respinfo(VALUE_PAIR *av) {
	char buf1[4096];
	char buf2[4096];
	char buf3[4096];
	char buf4[4096];
	char buf5[4096];

	if (!av) {
		printf("No A-V pairs\n");
		return;
	}

	/*
	 *  Rather crude output, but sufficient for Python parsing
	 */
	while(av) {
		int tmp;

		memset(buf1, (int) 0x00, sizeof(buf1));
		if (av->name != NULL) {
		        _hexencode(buf1, sizeof(buf1), av->name, strlen(av->name));
		}
		buf1[sizeof(buf1)-1] = 0x00;

		memset(buf2, (int) 0x00, sizeof(buf2));
		tmp = htonl(av->attribute);
		_hexencode(buf2, sizeof(buf2), &tmp, sizeof(tmp));
		buf2[sizeof(buf2)-1] = 0x00;

		memset(buf3, (int) 0x00, sizeof(buf3));
		tmp = htonl(av->type);
		_hexencode(buf3, sizeof(buf3), &tmp, sizeof(tmp));
		buf3[sizeof(buf3)-1] = 0x00;

		memset(buf4, (int) 0x00, sizeof(buf4));
		tmp = htonl(av->lvalue);
		_hexencode(buf4, sizeof(buf4), &tmp, sizeof(tmp));
		buf4[sizeof(buf4)-1] = 0x00;

		memset(buf5, (int) 0x00, sizeof(buf5));
		if (av->strvalue != NULL) {
		        _hexencode(buf5, sizeof(buf5), av->strvalue, strlen(av->strvalue));
		}
		buf5[sizeof(buf5)-1] = 0x00;

		printf("AVP: %s:%s:%s:%s:%s\n", buf1, buf2, buf3, buf4, buf5);
		av = av->next;
	}
}

int main (int argc, char **argv) {
	char            *username = NULL;
	char            *password = NULL;
	int             result;
        VALUE_PAIR      *send = NULL;
	VALUE_PAIR      *received = NULL;
        UINT4           service;
        char            msg[4096], username_realm[256];
        char            *default_realm = NULL;
	int             exit_code = -1;
	rc_handle	*rh;

	/*
	 *  Command line
	 */

	if (argc != 3) {
		printf("Usage: radauthuser <username> <password>\n");
		exit(10);
	}

	username = argv[1];
	if (strlen(username) > MAX_USERNAME_LENGTH) {
		printf("Username too long\n");
		exit(11);
	}

	password = argv[2];
	if (strlen(password) > MAX_PASSWORD_LENGTH) {
		printf("Password too long\n");
		exit(12);
	}

	/*
	 *  RADIUS init
	 */

	rh = rc_read_config(RC_CONFIG_FILE);
	if (rh == NULL) {
                return(13);
	}

        if (rc_read_dictionary(rh, rc_conf_str(rh, "dictionary")) != 0) {
                return(14);
	}

	default_realm = rc_conf_str(rh, "default_realm");

	/*
	 *  Figure out complete username, adding default realm if needed
	 */

        strncpy(username_realm, username, sizeof(username_realm));
	username_realm[sizeof(username_realm) - 1] = 0x00;

        if ((strchr(username_realm, '@') == NULL) && default_realm && (*default_realm != '\0')) {
                strncat(username_realm, "@", sizeof(username_realm));
		username_realm[sizeof(username_realm) - 1] = 0x00;
                strncat(username_realm, default_realm, sizeof(username_realm));
		username_realm[sizeof(username_realm) - 1] = 0x00;
        }

	/*
	 *  Build RADIUS message
	 */
        if (rc_avpair_add(rh, &send, PW_USER_NAME, username_realm, -1, 0) == NULL) {
                return(15);
	}
        if (rc_avpair_add(rh, &send, PW_USER_PASSWORD, password, -1, 0) == NULL) {
                return(16);
	}
        service = PW_AUTHENTICATE_ONLY;
        if (rc_avpair_add(rh, &send, PW_SERVICE_TYPE, &service, -1, 0) == NULL) {
                return(17);
	}

	/*
	 *  Send, wait for response, and process result
	 */
        result = rc_auth(rh, 0, send, &received, msg);

	switch (result) {
	case BADRESP_RC:
		printf("BADRESP\n");
		exit_code = 1;
		break;
	case ERROR_RC:
		printf("ERROR\n");
		exit_code = 1;
		break;
	case OK_RC:
		printf("OK\n");
		_print_respinfo(received);
		exit_code = 0;
		break;
	case TIMEOUT_RC:
		printf("TIMEOUT\n");
		exit_code = 1;
		break;
	default:
		printf("UNKNOWN\n");
		exit_code = 1;
		break;
	}

	exit (exit_code);

	/* should not be here */
	return -1;
}
