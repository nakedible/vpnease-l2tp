#  Requires:
#    * libglib1.2
#    * libglib1.2-dev
#    * xlibs-dev
#    * libx11-dev
#    * libxt-dev
#    * libnotify1-dev

notifytool:
	gcc -o notifytool -I/usr/include/glib-2.0 -I/usr/lib/glib-2.0/include -I/usr/include/gtk-2.0 -I/usr/lib/gtk-2.0/include -I/usr/include/cairo -I/usr/include/pango-1.0 -I/usr/include/atk-1.0 notifytool.c -lnotify


clean:
	rm -f notifytool
