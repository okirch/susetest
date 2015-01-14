/*
 * Handling for twopence config files.
 * 
 * Copyright (C) 2014-2015 SUSE
 * 
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, version 2.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU General Public License for more details.
 * 
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <ctype.h>

#include "susetest.h"

typedef struct susetest_config_attr susetest_config_attr_t;

struct susetest_config_attr {
	susetest_config_attr_t *	next;
	char *				name;
	char *				value;
};

struct susetest_target_config {
	susetest_target_config_t *	next;

	/* A shorthand name, like "client" or "server" */
	char *				name;

	/* The target spec, eg "ssh:somehost" */
	char *				spec;

	/* Attributes */
	susetest_config_attr_t *	attrs;
};

struct susetest_config {
	susetest_target_config_t *	targets;
	susetest_config_attr_t *	attrs;
};

static void	__susetest_target_config_free(susetest_target_config_t *);
static void	__susetest_config_attrs_free(susetest_config_attr_t **);
static void	__susetest_config_set_attr(susetest_config_attr_t **, const char *, const char *);
static const char *__susetest_config_get_attr(susetest_config_attr_t **, const char *);
static void	__susetest_config_attrs_write(FILE *fp, const susetest_config_attr_t *list);
static const char **__susetest_config_attr_names(susetest_config_attr_t * const*);

susetest_config_t *
susetest_config_new(void)
{
	susetest_config_t *cfg;

	cfg = (susetest_config_t *) calloc(1, sizeof(*cfg));
	return cfg;
}

void
susetest_config_free(susetest_config_t *cfg)
{
	if (cfg->targets) {
		susetest_target_config_t *tgt;

		while ((tgt = cfg->targets) != NULL) {
			cfg->targets = tgt->next;
			__susetest_target_config_free(tgt);
		}
	}

	__susetest_config_attrs_free(&cfg->attrs);
	free(cfg);
}

susetest_target_config_t *
susetest_config_get_target(susetest_config_t *cfg, const char *name)
{
	susetest_target_config_t *tgt;

	for (tgt = cfg->targets; tgt; tgt = tgt->next) {
		if (!strcmp(tgt->name, name))
			return tgt;
	}
	return NULL;
}

susetest_target_config_t *
susetest_config_add_target(susetest_config_t *cfg, const char *name, const char *spec)
{
	susetest_target_config_t *tgt;

	if (susetest_config_get_target(cfg, name) != NULL) {
		fprintf(stderr, "duplicate target name \"%s\"\n", name);
		return NULL;
	}

	tgt = (susetest_target_config_t *) calloc(1, sizeof(*tgt));
	tgt->name = strdup(name);
	tgt->spec = strdup(spec);

	tgt->next = cfg->targets;
	cfg->targets = tgt;

	return tgt;
}

void
susetest_config_set_attr(susetest_config_t *cfg, const char *name, const char *value)
{
	__susetest_config_set_attr(&cfg->attrs, name, value);
}

const char *
susetest_config_get_attr(susetest_config_t *cfg, const char *name)
{
	return __susetest_config_get_attr(&cfg->attrs, name);
}

const char *
susetest_target_config_get_spec(susetest_target_config_t *cfg)
{
	return cfg->spec;
}

void
susetest_target_config_set_attr(susetest_target_config_t *tgt, const char *name, const char *value)
{
	__susetest_config_set_attr(&tgt->attrs, name, value);
}

const char *
susetest_target_config_get_attr(susetest_target_config_t *tgt, const char *name)
{
	return __susetest_config_get_attr(&tgt->attrs, name);
}

const char **
susetest_target_config_attr_names(const susetest_target_config_t *tgt)
{
	return __susetest_config_attr_names(&tgt->attrs);
}

void
__susetest_target_config_free(susetest_target_config_t *tgt)
{
	__susetest_config_attrs_free(&tgt->attrs);
	free(tgt->name);
	free(tgt->spec);
	free(tgt);
}

static susetest_config_attr_t *
__susetest_config_find_attr(susetest_config_attr_t **list, const char *name, int create)
{
	susetest_config_attr_t **pos, *attr;

	for (pos = list; (attr = *pos) != NULL; pos = &attr->next) {
		if (!strcmp(attr->name, name))
			return attr;
	}

	if (create) {
		attr = calloc(1, sizeof(*attr));
		attr->name = strdup(name);
		*pos = attr;
		return attr;
	}

	return NULL;
}

void
__susetest_config_set_attr(susetest_config_attr_t **list, const char *name, const char *value)
{
	susetest_config_attr_t *attr;
	char *s;

	attr = __susetest_config_find_attr(list, name, 1);
	if (attr->value)
		free(attr->value);
	attr->value = value? strdup(value) : NULL;

	/* Replace newlines with a blank */
	while ((s = strchr(attr->value, '\n')) != NULL)
		*s = ' ';
}

const char *
__susetest_config_get_attr(susetest_config_attr_t **list, const char *name)
{
	susetest_config_attr_t *attr;

	attr = __susetest_config_find_attr(list, name, 0);
	if (attr)
		return attr->value;
	return NULL;
}

const char **
__susetest_config_attr_names(susetest_config_attr_t * const*list)
{
	susetest_config_attr_t *attr;
	unsigned int n, count = 0;
	const char **result;

	for (attr = *list, count = 0; attr; attr = attr->next, ++count)
		;

	result = calloc(count + 1, sizeof(*result));
	for (attr = *list, n = 0; attr; attr = attr->next) {
		/* assert(n < count); */
		result[n++] = attr->name;
	}
	result[n] = NULL;

	return result;
}

void
__susetest_config_attrs_free(susetest_config_attr_t **list)
{
	susetest_config_attr_t *attr;

	while ((attr = *list) != NULL) {
		*list = attr->next;

		free(attr->name);
		if (attr->value)
			free(attr->value);
		free(attr);
	}
}

/*
 * I/O routines
 */
int
susetest_config_write(susetest_config_t *cfg, const char *path)
{
	susetest_target_config_t *tgt;
	FILE *fp;

	if ((fp = fopen(path, "w")) == NULL) {
		fprintf(stderr, "Unable to open %s: %m\n", path);
		return -1;
	}

	__susetest_config_attrs_write(fp, cfg->attrs);

	for (tgt = cfg->targets; tgt; tgt = tgt->next) {
		fprintf(fp, "target %s %s\n", tgt->name, tgt->spec);
		__susetest_config_attrs_write(fp, tgt->attrs);
	}

	fclose(fp);
	return 0;
}

void
__susetest_config_attrs_write(FILE *fp, const susetest_config_attr_t *attr)
{
	for (; attr; attr = attr->next)
		fprintf(fp, "attr %s %s\n", attr->name, attr->value);
}

char *
__get_token(char **pos)
{
	char *s, *retval = NULL;

	if ((s = *pos) == NULL)
		return NULL;

	while (isspace(*s))
		++s;

	if (*s == '#')
		*s = '\0';

	if (*s == '\0') {
		*pos = NULL;
		return NULL;
	}

	retval = s;

	while (*s && !isspace(*s))
		++s;
	if (*s)
		*s++ = '\0';
	*pos = s;

	return retval;
}

susetest_config_t *
susetest_config_read(const char *path)
{
	susetest_config_t *cfg;
	susetest_target_config_t *tgt = NULL;
	susetest_config_attr_t **attr_list;
	char buffer[1024];
	FILE *fp;

	if ((fp = fopen(path, "r")) == NULL) {
		fprintf(stderr, "Unable to open %s: %m\n", path);
		return NULL;
	}

	cfg = susetest_config_new();
	attr_list = &cfg->attrs;

	while (fgets(buffer, sizeof(buffer), fp) != NULL) {
		char *kwd, *pos;

		buffer[strcspn(buffer, "\r\n")] = '\0';

		pos = buffer;
		if ((kwd = __get_token(&pos)) == NULL)
			continue;

		if (!strcmp(kwd, "attr")) {
			char *name, *value;

			if ((name = __get_token(&pos)) == NULL
			 || (value = __get_token(&pos)) == NULL) {
				fprintf(stderr, "Missing token after \"%s\" keyword\n", kwd);
				goto failed;
			}

			__susetest_config_set_attr(attr_list, name, value);
		} else
		if (!strcmp(kwd, "target")) {
			char *name, *spec;

			if ((name = __get_token(&pos)) == NULL
			 || (spec = __get_token(&pos)) == NULL) {
				fprintf(stderr, "Missing token after \"%s\" keyword\n", kwd);
				goto failed;
			}

			tgt = susetest_config_add_target(cfg, name, spec);
			if (tgt == NULL) {
				fprintf(stderr, "Duplicate target name \"%s\" in config file\n", name);
				goto failed;
			}

			attr_list = &tgt->attrs;
		} else {
			fprintf(stderr, "Unexpected keyword \"%s\"\n", kwd);
			goto failed;
		}
	}

	fclose(fp);
	return cfg;

failed:
	fclose(fp);
	susetest_config_free(cfg);
	return NULL;
}
