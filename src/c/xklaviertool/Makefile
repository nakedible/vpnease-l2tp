#  Requires:
#    * libglib1.2
#    * libglib1.2-dev
#    * xlibs-dev
#    * libx11-dev
#    * libxklavier10 libxklavier-dev
#    * libxt-dev

xklaviertool:
	gcc -o xklaviertool `glib-config --cflags` xklaviertool.c -lxklavier

clean:
	rm -f xklaviertool
