#ifndef __PARAMETERS_H
#define __PARAMETERS_H 1

int set_parameter(char *key, char *value);
char *get_parameter(char *requested_key);
void get_parameter_by_index(int index, char **key_out, char **value_out);

#endif  /* __PARAMETERS_H */
