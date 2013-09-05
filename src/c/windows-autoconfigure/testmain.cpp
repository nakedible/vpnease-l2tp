#include <stdio.h>
#include "parameters.h"

int main(int argc, char **argv) {
        printf("foo=%s\n", get_parameter("foo"));
        printf("bar=%s\n", get_parameter("bar"));
        printf("quux=%s\n", get_parameter("quux"));
        printf("baz=%s\n", get_parameter("baz"));
}
