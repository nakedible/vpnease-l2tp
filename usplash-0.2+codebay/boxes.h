#ifndef _BOXES_H_
#define _BOXES_H_

#define DLG_ERROR               -1
#define DLG_OKAY                0
#define DLG_CANCEL              10

#define DLG_YES			-1
#define DLG_NO			0

int setFont(const char *, const char *);

void boxResume(void);
void boxSuspend(void);
void boxPopWindow(void);
void boxFinished(void);
void boxInit(void);

void setMono(void);
int pleaseWaitBox(const char *text);
int vaproblemBox(const char *title, const char *fmt, ...);
int problemBox(const char *text, const char *title);
int problemBoxEn (const char *, const char *);
int wideMessageBox(const char *text, const char *title);
int perrorBox(const char *text);
int twoButtonBox(const char *text, const char *title, const char *button1, const char* button2);
int yesNoBox(const char *text, const char *title);
char *inputBox(const char *text, const char *title, const char *proto);

int enterDirBox (const char *, const char *, const char *, const char *, char *, size_t);

void pushHelpLine (const char *, int);
void popHelpLine (void);

/*
 * Internal representation of the list
 */
struct list
{
  int nelem;
  char** data;
};

/*
 * Option Constants for the lists
 */
#define OPT_F    (10000)
#define OPT_D    (10000 + OPT_F)

int tz_dialogBox(const char* text, const char* title, 
                 int height, int width,
                 struct list* dirs, struct list* files);

#define SCALE_CREATE	0
#define SCALE_REFRESH	1
#define SCALE_DELETE	2
int scaleBox(const char *text, const char *title, long long length, int action);

struct d_choices
 {
   char* tag;
   char* string;
   int   state;
};

int menuBox(const char* text, const char* title,
		struct d_choices* choices, int nchoices, int cancel);
int checkBox(const char* text, const char* title, int height, int width,
             char** choices, char** values, int nchoices);

#endif
