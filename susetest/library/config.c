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

struct susetest_config_group {
	susetest_config_group_t *	next;

	/* The group's type (eg "node") and name (eg "client", "server") */
	char *				type;
	char *				name;

	/* Attributes */
	susetest_config_attr_t *	attrs;

	susetest_config_group_t *	children;
};

static void		__susetest_node_config_free(susetest_node_config_t *);
static void		__susetest_config_attrs_free(susetest_config_attr_t **);
static void		__susetest_config_set_attr(susetest_config_attr_t **, const char *, const char *);
static const char *	__susetest_config_get_attr(susetest_config_attr_t **, const char *);
static void		__susetest_config_attrs_write(FILE *fp, const susetest_config_attr_t *list);
static const char **	__susetest_config_attr_names(susetest_config_attr_t * const*);

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
	if (cfg->children) {
		susetest_node_config_t *node;

		while ((node = cfg->children) != NULL) {
			cfg->children = node->next;
			__susetest_node_config_free(node);
		}
	}

	__susetest_config_attrs_free(&cfg->attrs);
	free(cfg);
}

susetest_node_config_t *
susetest_config_get_node(susetest_config_t *cfg, const char *name)
{
	susetest_node_config_t *node;

	for (node = cfg->children; node; node = node->next) {
		if (!strcmp(node->name, name))
			return node;
	}
	return NULL;
}

susetest_node_config_t *
susetest_config_add_node(susetest_config_t *cfg, const char *name, const char *target)
{
	susetest_node_config_t *node;

	if (susetest_config_get_node(cfg, name) != NULL) {
		fprintf(stderr, "duplicate node name \"%s\"\n", name);
		return NULL;
	}

	node = (susetest_node_config_t *) calloc(1, sizeof(*node));
	node->type = strdup("node");
	node->name = strdup(name);
	susetest_node_config_set_target(node, target);

	node->next = cfg->children;
	cfg->children = node;

	return node;
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

const char **
susetest_config_get_nodes(const susetest_config_t *cfg)
{
	const susetest_node_config_t *node;
	unsigned int n, count;
	const char **result;

	for (count = 0, node = cfg->children; node; node = node->next, ++count)
		;

	result = calloc(count + 1, sizeof(result[0]));
	for (n = 0, node = cfg->children; node; node = node->next)
		result[n++] = node->name;
	result[n++] = NULL;

	return result;
}

void
susetest_node_config_set_target(susetest_node_config_t *cfg, const char *target)
{
	susetest_node_config_set_attr(cfg, "target", target);
}

const char *
susetest_node_config_get_target(susetest_node_config_t *cfg)
{
	return susetest_node_config_get_attr(cfg, "target");
}

void
susetest_node_config_set_attr(susetest_node_config_t *node, const char *name, const char *value)
{
	__susetest_config_set_attr(&node->attrs, name, value);
}

const char *
susetest_node_config_get_attr(susetest_node_config_t *node, const char *name)
{
	return __susetest_config_get_attr(&node->attrs, name);
}

const char **
susetest_node_config_attr_names(const susetest_node_config_t *node)
{
	return __susetest_config_attr_names(&node->attrs);
}

void
__susetest_node_config_free(susetest_node_config_t *node)
{
	__susetest_config_attrs_free(&node->attrs);
	susetest_node_config_set_target(node, NULL);
	free(node->name);
	free(node);
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
	susetest_node_config_t *node;
	FILE *fp;

	if ((fp = fopen(path, "w")) == NULL) {
		fprintf(stderr, "Unable to open %s: %m\n", path);
		return -1;
	}

	__susetest_config_attrs_write(fp, cfg->attrs);

	for (node = cfg->children; node; node = node->next) {
		fprintf(fp, "node %s\n", node->name);
		__susetest_config_attrs_write(fp, node->attrs);
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
	susetest_node_config_t *node = NULL;
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
		if (!strcmp(kwd, "node")) {
			char *name, *target;

			if ((name = __get_token(&pos)) == NULL) {
				fprintf(stderr, "Missing token after \"%s\" keyword\n", kwd);
				goto failed;
			}

			/* The target does not have to be set yet. */
			target = __get_token(&pos);

			node = susetest_config_add_node(cfg, name, target);
			if (node == NULL) {
				fprintf(stderr, "Duplicate node name \"%s\" in config file\n", name);
				goto failed;
			}

			attr_list = &node->attrs;
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
