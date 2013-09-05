#include <stdio.h>
#include <stdlib.h>
#include <sys/types.h>
#include <string.h>
#include <locale.h>
#include <limits.h>

#include <wchar.h>

#define BITS_NO     (65536l / 32)

u_int32_t used[BITS_NO];

void
usage (void)
{
    printf ("usage: reduce-font <font> < text\n");
}

inline size_t
bits (u_int32_t x)
{
    size_t r;

    for (r = 0 ; x != 0 ; r++)
        x = x & (x - 1);

    return r;
}

void
test (u_int32_t x)
{
    int i;
    size_t l = bits (x);

    printf ("%08x: ", x);

    for (i = 0 ; i < 32 ; x <<= 1, ++i)
        putchar (x & 0x80000000 ? '1' : '0');

    printf (": %d\n", l);
}

int
main (int argc, char **argv)
{
    FILE *font;
    char *buffer = NULL;
    char *locale = setlocale (LC_CTYPE, "");
    int error = 0;

    if (locale == NULL) {
      fprintf (stderr, "Unable to set locale\n");
      return 1;
    }
    
    fprintf (stderr, "setlocale: %s\n", locale);
#if 1
    fprintf (stderr, "FYI: MB_CUR_MAX/MB_LEN_MAX: %d/%d\n", MB_CUR_MAX, MB_LEN_MAX);
#endif
    if (argc != 2)
        usage ();
    else if ((buffer = (char *)malloc (MB_LEN_MAX)) == NULL)
        perror ("buffer allocation");
    else if ((font = fopen (argv[1], "r")) == NULL)
        perror (argv[1]);
    else
    {
        size_t got, avail, chars, pos;
        int i;
        wchar_t wc;
        mbstate_t wstate = { 0 };

        /* Initialize the array */

        /* Make sure ASCII is included! */
        for (i = 0 ; i < (128 / 32) ; ++i)
            used[i] = UINT_MAX;

        /* Other stuff will only be included iff it's there... :) */
        for (; i < BITS_NO ; ++i)
            used[i] = 0;

        mbrtowc (NULL, NULL, 0, &wstate);   /* Init the engine */

        for (pos = avail = 0 ; (got = fread (buffer + avail, 1, MB_LEN_MAX - avail, stdin)) >= 0 && (avail += got) > 0 ;)
        {
            switch (got = mbrtowc (&wc, buffer, avail, &wstate))
            {
                case -1:    /* An error occured */
                    fprintf (stderr, "error -1 at position %ld (bytes: %d %*.*s)\n", pos, avail, avail, avail, buffer);
		    error = 1;
                    break;

                case -2:
                    fprintf (stderr, "-2: bytes: %d %*.*s\n", avail, avail, avail, buffer);
                    continue;

                case 0:     /* Nothing's read so far */
                    fprintf (stderr, "0: bytes: %d %*.*s\n", avail, avail, avail, buffer);
                    continue;

                default:    /* Seems to read something reasonable */
#if 0
                    fprintf (stdout, "got: %ld\n", wc);
#endif
                    pos += got;

                    used[wc / 32] |= (1 << (wc % 32));
                    if (got == avail)   /* I just do not know how memcpy behaves in case of length equal to 0 :) */
                        avail = 0;
                    else
                    {
                        memcpy (buffer, buffer + got, avail - got);
                        avail -= got;
                    }
                    continue;
            }

            break;
        }

        /* Process stdin here */
        /* mbrtowc */
#if 0
        usage ();

        test (0x12345678);
#endif
        for (chars = 0, i = 0 ; i < BITS_NO ; ++i)
            chars += bits (used[i]);

        fprintf (stderr, "Used chars: %d (%d processed)\n", chars, pos);
#if 1
        {
            char *buf = (char *)malloc (1024);
            int header, docopy;

            for (header = 1, docopy = 0 ; fgets (buf, 1024, font) != NULL ;)
            {
                if (header)
                {
                    if (strncmp (buf, "CHARS ", 6) == 0)
                        printf ("CHARS %d\n", chars);
                    else if (strncmp (buf, "STARTCHAR ", 10) == 0)
                        header = 0;
                    else
                        fprintf (stdout, buf);
                }
                
                if (!header)
                {
                    if (strncmp (buf, "STARTCHAR ", 10) == 0)
                    {
                        wc = strtol (buf + 12, NULL, 16);

                        docopy = used[wc / 32] & (1 << (wc % 32));
                    }

                    if (docopy)
                        fprintf (stdout, buf);
                }
            }

            if (!header)
                fputs ("ENDFONT\n", stdout);

            free (buf);
        }
#endif
        fclose (font);
    }

    if (buffer != NULL)
        free (buffer);

    return error;
}
