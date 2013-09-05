
#include <stdio.h>

int rashelper_show_error_dialog(char *error_title, char *error_text) {
        printf("RASHELPER ERROR DIALOG: %s -> %s\n", error_title, error_text);
        return 0;
}

int rashelper_configure_profile(char *profile_name,
                                char *desktop_shortcut_name,
                                char *server_address,
                                char *preshared_key,
                                char *username,
                                int ppp_compression_enabled,
                                int default_route_enabled,
                                int create_desktop_shortcut,
                                int open_profile_after_creation) {
        printf("RASHELPER CONFIGURE PROFILE: %s, %s, %s, %s, %s, %d, %d, %d, %d\n",
               profile_name, desktop_shortcut_name, server_address, preshared_key, username,
               ppp_compression_enabled, default_route_enabled, create_desktop_shortcut, open_profile_after_creation);
        return 0;
}

int rashelper_check_profiles(char *profile_name,
                             char *server_address) {
        return 0;
}

int rashelper_delete_profiles(char *profile_name,
                              char *server_address) {
        return 0;
}

