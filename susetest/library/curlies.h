
#ifndef SUSETEST_CURLY_H
#define SUSETEST_CURLY_H

#include "config.h"

extern susetest_config_t *	curly_parse(const char *filename);
extern void			curly_write(const susetest_config_t *cfg, const char *filename);
extern void			curly_print(const susetest_config_t *cfg, FILE *fp);

#endif /* SUSETEST_CURLY_H */
