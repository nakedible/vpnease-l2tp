/*
 *  Parameterization interface.
 *
 *  The basic model here is that caller requests for string-valued
 *  parameters with a string key (key-value pairs, string -> string).
 *
 *  The hackery here is basically intended to allow an EXE to be
 *  binary patched after it has been built, so that parameters can
 *  be 'injected' into an EXE after build easily by VPNease web UI.
 *
 *  Future improvements:
 *    * Better code sharing between helpers
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Note: these constants MUST NOT be used in any other place than the array
 * below, otherwise the EXE patcher may misidentify the block!
 */
#define _MARKER_BEGIN           "##### BEGIN PARAMETER BLOCK #####"
#define _MARKER_END             "##### END PARAMETER BLOCK #####"
#define _MARKER_BEGIN_LENGTH    (5 + 1 + 9 + 1 + 5 + 1 + 5 + 1 + 5)
#define _MARKER_END_LENGTH      (5 + 1 + 9 + 1 + 5 + 1 + 3 + 1 + 5)

#define _ONE_KILO_DOTS \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................" \
        "................................................................"

#define _8_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS

/*
 *  Parameter space for ~60 kilobytes, format:
 *  <key>\0<value>\0<key>\0<value>\0\0
 *
 *  NB: about 20+ kilobytes is required by Windows 2000 REG file.
 *  Visual C++ does not allow character constants larger than 64KB,
 *  so that's why we have ~60KB here only.
 */
#ifdef AUTOCONFIGURE_WIN2000
static char _parameter_array[] = \
        _MARKER_BEGIN \
        "\0\0" \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _8_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _ONE_KILO_DOTS \
        _MARKER_END;
#else
static char _parameter_array[] = \
        _MARKER_BEGIN \
        "\0\0" \
        _8_KILO_DOTS \
        _MARKER_END;
#endif

int set_parameter(char *key, char *value) {
        char *p;
        char *p_max;
        int space, space_required;

        p = _parameter_array + _MARKER_BEGIN_LENGTH;
        p_max = _parameter_array + sizeof(_parameter_array) - _MARKER_END_LENGTH;

        for(;;) {
                int null_count;

                /* is this the final null term? */
                if (p >= p_max) {
                        return -1;
                }
                if (*p == '\x00') {
                        /* final null term */
                        break;
                }
                p++;

                /* no, skip a key and a value (two nulls) */
                null_count = 0;
                for (;;) {
                        if (p >= p_max) {
                                return -1;
                        }
                        if (*p == '\x00') {
                                null_count++;
                        }
                        if (null_count == 2) {
                                p++;
                                break;
                        }
                        p++;
                }
        }

        if (p >= p_max) {
                return -1;
        }

        space = p_max - p;
        space_required = strlen(key) + 1 + strlen(value) + 1 + 1;
        if (space_required > space) {
                return -1;
        }

        memcpy(p, key, strlen(key));
        p += strlen(key);
        *p++ = '\x00';
        memcpy(p, value, strlen(value));
        p += strlen(value);
        *p++ = '\x00';
        *p++ = '\x00';  /* new final null term */

        return 0;
}

void get_parameter_by_index(int index, char **key_out, char **value_out) {
        char *p;
        char *p_max;

        *key_out = NULL;
        *value_out = NULL;

        p = _parameter_array + _MARKER_BEGIN_LENGTH;
        p_max = _parameter_array + sizeof(_parameter_array) - _MARKER_END_LENGTH;

        for(;;) {
                char *key = NULL;
                char *value = NULL;

                if (*p == '\x00') {
                        return;
                }

                key = p;
                for(;;) {
                        if (p >= p_max) {
                                return;
                        }
                        if (*p == '\x00') {
                                break;
                        }
                        p++;
                }
                p++;
                if (p >= p_max) {
                        return;
                }

                value = p;
                for(;;) {
                        if (p >= p_max) {
                                return;
                        }
                        if (*p == '\x00') {
                                break;
                        }
                        p++;
                }
                p++;
                if (p >= p_max) {
                        return;
                }

                if (index == 0) {
                        *key_out = key;
                        *value_out = value;
                }
                index --;
        }
}

char *get_parameter(char *requested_key) {
        char *p;
        char *p_max;

        p = _parameter_array + _MARKER_BEGIN_LENGTH;
        p_max = _parameter_array + sizeof(_parameter_array) - _MARKER_END_LENGTH;

        for(;;) {
                char *key = NULL;
                char *value = NULL;

                if (*p == '\x00') {
                        return NULL;
                }

                key = p;
                for(;;) {
                        if (p >= p_max) {
                                return NULL;
                        }
                        if (*p == '\x00') {
                                break;
                        }
                        p++;
                }
                p++;
                if (p >= p_max) {
                        return NULL;
                }

                value = p;
                for(;;) {
                        if (p >= p_max) {
                                return NULL;
                        }
                        if (*p == '\x00') {
                                break;
                        }
                        p++;
                }
                p++;
                if (p >= p_max) {
                        return NULL;
                }

                if (strcmp(key, requested_key) == 0) {
                        return value;
                }
        }

        return NULL;
}

