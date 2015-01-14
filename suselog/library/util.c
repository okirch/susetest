
#include <stdlib.h>
#include "util.h"


void
string_putc(string_t *s, char cc)
{
	if (s->len + 1 >= s->size) {
		s->size += 256;
		s->string = realloc(s->string, s->size);
	}
	s->string[s->len++] = cc;
	s->string[s->len] = '\0';
}

void
string_move(string_t *to, string_t *from)
{
	string_destroy(to);
	*to = *from;
	string_init(from);
}

void
string_trim_empty_lines(string_t *s)
{
	char *src, *dst;

	for (src = dst = s->string; *src; ) {
		char cc = *src++;

		*dst++ = cc;
		if (cc == '\n') {
			while (*src == '\n')
				++src;
		}
	}
}
