#ifndef __SHORTCUT_H
#define __SHORTCUT_H 1

#include <objbase.h>
#include <stdio.h>
#include <windows.h>
#include <shlobj.h>

int create_shell_link_to_network_connection(int nFolder, char *link_name, char *connection_name);

#endif /* __SHORTCUT_H */

