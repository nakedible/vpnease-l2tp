/*****************************************************************************
 * Copyright (C) 2004,2005,2006 Katalix Systems Ltd
 * 
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA 
 *
 *****************************************************************************/

/*
 * Plugin support
 */

#include <stdlib.h>
#include <syslog.h>
#include <string.h>
#include <pwd.h>
#include <dlfcn.h>

#include "usl.h"
#include "l2tp_private.h"


int l2tp_plugin_load(char *name)
{
	void *handle;
	const char *err;
	void (*init)(void);
	char *path = name;
	const char *vers;

	if (strchr(name, '/') == 0) {
		const char *base = L2TP_PLUGIN_DIR;
		int len = strlen(base) + strlen(name) + 2;
		path = malloc(len);
		if (path == 0) {
			l2tp_log(LOG_ERR, "OOM: plugin file path");
			return -ENOMEM;
		}

		strncpy(path, base, len);
		strncat(path, "/", len);
		strncat(path, name, len);
	}
	handle = dlopen(path, RTLD_GLOBAL | RTLD_NOW);
	if (handle == 0) {
		err = dlerror();
		if (err != 0)
			l2tp_log(LOG_ERR, "%s", err);
		l2tp_log(LOG_ERR, "Couldn't load plugin %s", name);
		goto err;
	}
	init = (void (*)(void))dlsym(handle, "l2tp_plugin_init");
	if (init == 0) {
		l2tp_log(LOG_ERR, "%s has no initialization entry point", name);
		goto errclose;
	}
	vers = (const char *) dlsym(handle, "l2tp_plugin_version");
	if (vers == NULL) {
		l2tp_log(LOG_ERR, "%s has no version information", name);
		goto errclose;
	}

	l2tp_log(LOG_INFO, "Loading plugin %s, version %s", name, vers);
	(*init)();
	return 0;

errclose:
	dlclose(handle);
err:
	if (path != name)
		free(path);
	return -EINVAL;
}
