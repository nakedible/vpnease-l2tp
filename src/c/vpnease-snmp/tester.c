/*
 *  Trivial tester for key-value reading and parsing, run with valgrind
 *  to check for leaks etc.
 */
#include <stdio.h>
#include <stdlib.h>

#include <sys/time.h>
#include <sys/stat.h>

void main(void) {
  int i;
  printf("tester starts\n");

  for (i = 0; i < 100; i++) {
    system("sleep 1");
    printf("test-string: %s\n", data_file_get_string("test-string", "defvalue"));
  }

  data_file_free_keyvalue_list();

  printf("tester ends\n");
}
