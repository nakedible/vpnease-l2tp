#include <string.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <errno.h>
#include "usplash.h"

int main(int argc, char **argv) {
	int pipe_fd;

	if (argc!=2) {
		fprintf(stderr,"Wrong number of arguments\n");
		exit(1);
	}

	chdir("/dev/.initramfs");	

	pipe_fd = open(USPLASH_FIFO,O_WRONLY|O_NONBLOCK);
	
	if (pipe_fd==-1) {
		/* We can't really do anything useful here */
		exit(0);
	}
	
	write(pipe_fd,argv[1],strlen(argv[1])+1);

	return 0;
}

