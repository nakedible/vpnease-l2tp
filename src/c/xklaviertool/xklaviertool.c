/*
 *  Trivial tool for enumerating XKB keyboard layouts and variants
 *  using libxklavier.
 *
 *  (c) 2006-2007 Codebay Oy.  All Rights Reserved.
 */

#include <stdio.h>
#include <stdlib.h>

#include <X11/Xlib.h>
#include <X11/Intrinsic.h>
#include <X11/Xutil.h>

#include <glib.h>
#include <libxklavier/xklavier.h>
#include <libxklavier/xklavier_config.h>

void _variant_processor(const XklConfigItemPtr configItem, void *userData) {
	const XklConfigItemPtr layout = (XklConfigItemPtr) userData;
	printf("VARIANT^%s^%s^%s\n",
	       configItem->name,
	       configItem->shortDescription,
	       configItem->description);
}

void _layout_processor(const XklConfigItemPtr configItem, void *userData) {
	printf("LAYOUT^%s^%s^%s\n",
	       configItem->name,
	       configItem->shortDescription,
	       configItem->description);
	XklConfigEnumLayoutVariants(configItem->name, _variant_processor, (void *) configItem);
}

int main(int argc, char *argv[]) {
	Display *dpy = NULL;
	int rc = -1;
	int xkl_inited = 0;

	dpy = XOpenDisplay (NULL);
	if(dpy == NULL) {
		fprintf(stderr, "Cannot open display\n");
		rc = 1;
		goto cleanup;
	}
	fprintf(stderr, "Display: %p\n", dpy);

	if(XklInit(dpy) != 0) {
		fprintf(stderr, "XklInit failed\n");
		rc = 2;
		goto cleanup;
	}
	xkl_inited = 1;

	XklConfigInit();

	if(!XklConfigLoadRegistry()) {
		fprintf(stderr, "XklConfigLoadRegistry() failed\n");
		rc = 3;
		goto cleanup;
	}

	XklConfigEnumLayouts(_layout_processor, NULL);

	rc = 0;
	/* fall through */

 cleanup:
	if(xkl_inited) {
		XklTerm();
	}
	if(dpy) {
		XCloseDisplay(dpy);
	}

	return rc;
}

