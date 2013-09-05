
# old
# all: radauthuser

all: radauthuserng

radauthuser: radauthuser.c Makefile
	gcc -o radauthuser -lradiusclient radauthuser.c

radauthuserng: radauthuserng.c Makefile
	gcc -o radauthuserng -lradiusclient-ng radauthuserng.c

clean:
	-rm radauthuser radauthuserng

