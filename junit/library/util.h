

#ifndef UTIL_H
#define UTIL_H

#include <string.h>
#include <stdbool.h>

static inline void
__set_string(char **str_p, const char *s)
{
	if (*str_p != s) {
		if (*str_p)
			free(*str_p);
		*str_p = s? strdup(s) : NULL;
	}
}

static inline void
__drop_string(char **str_p)
{
	__set_string(str_p, NULL);
}

static inline bool
__string_equal(const char *s1, const char *s2)
{
	if (!s1 || !s2)
		return s1 == s2;
	return !strcmp(s1, s2);
}

typedef struct {
	unsigned int		len, size;
	char *			string;
} string_t;

static inline void
string_init(string_t *p)
{
	p->len = p->size = 0;
	p->string = NULL;
}

static inline void
string_destroy(string_t *p)
{
	if (p->string) {
		free(p->string);
		string_init(p);
	}
}

static inline bool
string_is_empty(const string_t *p)
{
	return p->string == NULL || p->string[0] == '\0';
}

extern void		string_putc(string_t *, char);
extern void		string_move(string_t *to, string_t *from);
extern void		string_trim_empty_lines(string_t *);

#endif /* UTIL_H */
