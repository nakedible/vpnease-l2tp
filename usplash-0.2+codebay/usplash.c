/* USplash - a trivial framebuffer splashscreen application */
/* Copyright Matthew Garrett, 2005. Released under the terms of the GNU
   General Public License version 2.1 or later */

#include <string.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <sys/select.h>
#include <errno.h>
#include <linux/vt.h>
#include <sys/ioctl.h>
#include <dlfcn.h>

#include "bogl.h"
#include "usplash.h"

#ifdef DEBUG
FILE* logfile;
#endif

int left_edge, top_edge;

#define BACKGROUND_COLOUR 0
#define PROGRESSBAR_COLOUR 1
#define PROGRESSBAR_BACKGROUND 4
#define TEXT_BACKGROUND 0
#define TEXT_FOREGROUND 2
#define TEXT_NORMAL 8
#define RED 13

#define TEXT_X1 (left_edge + 136)
#define TEXT_X2 (left_edge + 514)
#define TEXT_Y1 (top_edge + 235)
#define TEXT_Y2 (top_edge + 385)
#define LINE_HEIGHT 15

#define PROGRESS_BAR (top_edge + 210)

#define TEXT_WIDTH TEXT_X2-TEXT_X1
#define TEXT_HEIGHT TEXT_Y2-TEXT_Y1

int pipe_fd;
char command[4096];

extern struct bogl_font font_helvB10;
struct bogl_pixmap* pixmap_usplash_artwork;

void draw_progress(int percentage);
void draw_text(char *string, int length);
void draw_image(struct bogl_pixmap *pixmap);
void event_loop();
void text_clear();
void switch_console(int screen);
void init_progressbar();

int saved_vt=0;
int new_vt=0;
int timeout=15;

void cleanup() {

	if (saved_vt!=0) {
                struct vt_stat state;
                int fd;

                fd = open("/dev/console", O_RDWR);
                ioctl(fd,VT_GETSTATE,&state);
                close(fd);

                if (state.v_active == new_vt) {
                        // We're still on the console to which we switched,
                        // so switch back
                        switch_console(saved_vt);
                }
	}
}

int main (int argc, char** argv) {
	int err;
	void *handle;

#ifdef DEBUG
	logfile = fopen ("/dev/.initramfs/usplash_log","w+");
#endif

	if (argc>1) {
		if (strcmp(argv[1],"-c")==0) 
			switch_console(8);
	}

	chdir("/dev/.initramfs");

	if (mkfifo(USPLASH_FIFO, S_IRUSR | S_IWUSR | S_IRGRP | S_IWGRP))
	{
		if (errno!=EEXIST) {
			perror("mkfifo");
			cleanup();
			exit(1);
		}
	}

	pipe_fd = open(USPLASH_FIFO,O_RDONLY|O_NONBLOCK);

	if (pipe_fd==-1) {
		perror("pipe open");
		cleanup();
		exit(2);
	}

	err=bogl_init();

	if (!err) {
		fprintf(stderr,"%d",err);
		cleanup();
		exit (2);
	}

	handle = dlopen("/usr/lib/usplash/usplash-artwork.so", RTLD_LAZY);
	if (!handle) {
		exit(1);
	}
	pixmap_usplash_artwork = (struct bogl_pixmap *)dlsym(handle, "pixmap_usplash_artwork");
	
	bogl_set_palette (0, 16, pixmap_usplash_artwork->palette);

	left_edge = (bogl_xres - 640) / 2;
	top_edge  = (bogl_yres - 400) / 2;

	draw_image(pixmap_usplash_artwork);

	init_progressbar();

	text_clear();

	event_loop();

	bogl_done();

	cleanup();

	return 0;
}

void switch_console(int screen) {
	char vtname[10];
	int fd;
	struct vt_stat state;

	fd = open("/dev/console", O_RDWR);
	ioctl(fd,VT_GETSTATE,&state);
	saved_vt = state.v_active;
	close(fd);

	sprintf(vtname, "/dev/tty%d",screen);
	fd = open(vtname, O_RDWR);
	ioctl(fd,VT_ACTIVATE,screen);
        new_vt = screen;
	ioctl(fd,VT_WAITACTIVE,screen);
	close(fd);

	return;
}

void text_clear() {
	bogl_clear(TEXT_X1, TEXT_Y1, TEXT_X2, TEXT_Y2, TEXT_BACKGROUND);
}

void init_progressbar() {
	bogl_clear(left_edge+220,PROGRESS_BAR,left_edge+420,PROGRESS_BAR+10,PROGRESSBAR_BACKGROUND);
}

void draw_progress(int percentage) {
	int fore = PROGRESSBAR_COLOUR, back = PROGRESSBAR_BACKGROUND;

	if (percentage < -100 || percentage > 100)
		return;

	// Paint bar in reverse-video if percentage passed is negative.
	if (percentage < 0) {
		fore = PROGRESSBAR_BACKGROUND;
		back = PROGRESSBAR_COLOUR;
		percentage = -percentage;
	}
	// Overwrite the whole area to blank out any previous contents
	bogl_clear(left_edge+220,PROGRESS_BAR,left_edge+420,PROGRESS_BAR+10, back);
	bogl_clear(left_edge+220,PROGRESS_BAR,(left_edge+220+2*percentage),PROGRESS_BAR+10, fore);
	return;
}	

void draw_status(char *string, int colour) {
	bogl_clear (TEXT_X2-30, TEXT_Y2-LINE_HEIGHT, 
		    TEXT_X2, TEXT_Y2, TEXT_BACKGROUND);
	bogl_text (TEXT_X2-30, TEXT_Y2-LINE_HEIGHT, string, strlen(string), 
		   colour, TEXT_BACKGROUND, 0, &font_helvB10);
	return;
}

void draw_text(char *string, int length) {		
	/* Move the existing text up */
	bogl_move(TEXT_X1, TEXT_Y1+LINE_HEIGHT, TEXT_X1, TEXT_Y1, TEXT_X2-TEXT_X1,
		  TEXT_HEIGHT-LINE_HEIGHT);
	/* Blank out the previous bottom contents */
	bogl_clear(TEXT_X1, TEXT_Y2-LINE_HEIGHT, TEXT_X2, TEXT_Y2, 
		   TEXT_BACKGROUND);
	bogl_text (TEXT_X1, TEXT_Y2-LINE_HEIGHT, string, length,
		   TEXT_NORMAL, TEXT_BACKGROUND, 0, &font_helvB10);
	return;
}

void draw_image(struct bogl_pixmap *pixmap) {
	int colour_map[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
	bogl_clear(0, 0, bogl_xres, bogl_yres, BACKGROUND_COLOUR);	
	bogl_put (left_edge, top_edge, pixmap, colour_map);
}
	
int parse_command(char *string, int length) {
	char *command;
	char *origstring = string;
	int parsed=0;

#ifdef DEBUG
	fprintf (logfile, "%s\n", string);
	fflush (logfile);
#endif

	parsed = strlen(string)+1;
	
	if (strcmp(string,"QUIT")==0) {
		return 1;
	}	

	command = strtok(string," ");

	if (strcmp(command,"TEXT")==0) {
		char *line = strtok(NULL,"\0");
		int length = strlen(line);		
		while (length>50) {
			draw_text(line,50);
			line+=50;
			length-=50;
		}
		draw_text(line,length);
	} else if (strcmp(command,"STATUS")==0) {
		draw_status(strtok(NULL,"\0"),0);
	} else if (strcmp(command,"SUCCESS")==0) {
		draw_status(strtok(NULL,"\0"),TEXT_FOREGROUND);
	} else if (strcmp(command,"FAILURE")==0) {
		draw_status(strtok(NULL,"\0"),RED);
	} else if (strcmp(command,"PROGRESS")==0) {
		draw_progress(atoi(strtok(NULL,"\0")));
	} else if (strcmp(command,"CLEAR")==0) {
		text_clear();
	} else if (strcmp(command,"TIMEOUT")==0) {
		timeout=(atoi(strtok(NULL,"\0")));
	} else if (strcmp(command,"QUIT")==0) {
		return 1;
	}

	return 0;
}

void event_loop() {
	int err;
	ssize_t length = 0;
	fd_set descriptors;
	struct timeval tv;
        char *end;

	tv.tv_sec = timeout;
	tv.tv_usec = 0;

	FD_ZERO(&descriptors);
	FD_SET(pipe_fd,&descriptors);

        end = command;
	while (1) {
		if (timeout != 0) {
			err = select(pipe_fd+1, &descriptors, NULL, NULL, &tv);
		} else {
			err = select(pipe_fd+1, &descriptors, NULL, NULL, NULL);
		}

		if (err == -1) {
			return;
		}
		
		if (err == 0) {
			/* Timeout */
			return;
		}
		length += read(pipe_fd, end, sizeof(command) - (end - command));
		if (length == 0) {
                        /* Reopen to see if there's anything more for us */
                        close(pipe_fd);
                        pipe_fd = open(USPLASH_FIFO,O_RDONLY|O_NONBLOCK);
			goto out;
		}

                while (memchr(command, 0, length) != NULL && 
                       (char*)memchr(command, 0, length) < command + length - 1) {
                        /* More than one command in here, do the first */
                        char *ncommand = strdup(command);
                        if (parse_command(ncommand, strlen(ncommand))) {
                                free(ncommand);
                                return;
                        }
                        free(ncommand);
                        length = length - strlen(command) - 1;
                        memmove(command, command + strlen(command) + 1, length+1);
                }
                if (command[length-1] == '\0') {
                        /* Easy, just one command*/
                        if (parse_command(command, strlen(command))) {
                                return;
                        }
                        length = 0;
                } else {
                        /* Incomplete command.  Handle this in the
                         * next round */
                }
	out:
                end = &command[length];

		tv.tv_sec = timeout;
		tv.tv_usec = 0;

		FD_ZERO(&descriptors);
		FD_SET(pipe_fd,&descriptors);
	}
	return;
}
