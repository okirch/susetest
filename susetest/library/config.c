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
#include "curlies.h"

static void		__susetest_config_attrs_free(susetest_config_attr_t **);
static void		__susetest_config_set_attr(susetest_config_attr_t **, const char *, const char *);
static void		__susetest_config_add_attr_list(susetest_config_attr_t **, const char *, const char *);
static void		__susetest_config_set_attr_list(susetest_config_attr_t **, const char *, const char * const *);
static const char *	__susetest_config_get_attr(susetest_config_attr_t **, const char *);
static void		__susetest_config_drop_attr(susetest_config_attr_t **, const char *);
static const char * const *__susetest_config_get_attr_list(susetest_config_attr_t **, const char *);
static const char **	__susetest_config_attr_names(susetest_config_attr_t * const*);
static void		__susetest_config_attr_free(susetest_config_attr_t *attr);
static void		__susetest_config_attr_clear(susetest_config_attr_t *attr);

static inline int
xstrcmp(const char *a, const char *b)
{
	if (a == NULL || b == NULL)
		return a == b;
	return strcmp(a, b);
}

susetest_config_group_t *
susetest_config_group_new(const char *type, const char *name)
{
	susetest_config_group_t *cfg;

	cfg = (susetest_config_group_t *) calloc(1, sizeof(*cfg));
	cfg->type = type? strdup(type) : NULL;
	cfg->name = name? strdup(name) : NULL;
	return cfg;
}

void
susetest_config_group_free(susetest_config_group_t *cfg)
{
	if (cfg->children) {
		susetest_config_group_t *child;

		while ((child = cfg->children) != NULL) {
			cfg->children = child->next;
			susetest_config_group_free(child);
		}
	}

	if (cfg->type)
		free(cfg->type);
	cfg->type = NULL;

	if (cfg->name)
		free(cfg->name);
	cfg->name = NULL;

	__susetest_config_attrs_free(&cfg->attrs);
	free(cfg);
}

susetest_config_group_t *
susetest_config_group_get_child(const susetest_config_group_t *cfg, const char *type, const char *name)
{
	susetest_config_group_t *child;

	for (child = cfg->children; child; child = child->next) {
		if (type && xstrcmp(child->type, type))
			continue;
		if (name && xstrcmp(child->name, name))
			continue;
		return child;
	}
	return NULL;
}

susetest_config_group_t *
susetest_config_group_add_child(susetest_config_t *cfg, const char *type, const char *name, bool unique)
{
	susetest_config_group_t *child, **pos;

	if (unique && susetest_config_group_get_child(cfg, type, name) != NULL) {
		fprintf(stderr, "duplicate %s group named \"%s\"\n", type, name);
		return NULL;
	}

	/* Find the tail of the list */
	for (pos = &cfg->children; (child = *pos) != NULL; pos = &child->next)
		;

	*pos = child = susetest_config_group_new(type, name);
	return child;
}

const char **
susetest_config_group_get_children(const susetest_config_t *cfg, const char *type)
{
	const susetest_node_config_t *node;
	unsigned int n, count;
	const char **result;

	for (count = 0, node = cfg->children; node; node = node->next, ++count)
		;

	result = calloc(count + 1, sizeof(result[0]));
	for (n = 0, node = cfg->children; node; node = node->next) {
		if (type == NULL || !xstrcmp(node->type, type))
			result[n++] = node->name;
	}
	result[n++] = NULL;

	return result;
}

const char **
susetest_config_group_get_attr_names(const susetest_config_group_t *cfg)
{
	return __susetest_config_attr_names(&cfg->attrs);
}

/*
 * Accessor functions for susetest_config_t
 */
susetest_config_t *
susetest_config_new(void)
{
	return susetest_config_group_new("root", NULL);
}

void
susetest_config_free(susetest_config_t *cfg)
{
	susetest_config_group_free(cfg);
}

susetest_config_t *
susetest_config_get_child(const susetest_config_t *cfg, const char *type, const char *name)
{
	return susetest_config_group_get_child(cfg, type, name);
}

susetest_config_t *
susetest_config_add_child(susetest_config_t *cfg, const char *type, const char *name)
{
	return susetest_config_group_add_child(cfg, type, name, true);
}

const char **
susetest_config_get_children(const susetest_config_t *cfg, const char *type)
{
	return susetest_config_group_get_children(cfg, type);
}

const char **
susetest_config_get_attr_names(const susetest_config_t *cfg)
{
	return susetest_config_group_get_attr_names(cfg);
}

/*
 * Backward compatibility
 */
susetest_node_config_t *
susetest_config_get_node(susetest_config_t *cfg, const char *name)
{
	return susetest_config_group_get_child(cfg, "node", name);
}

susetest_node_config_t *
susetest_config_add_node(susetest_config_t *cfg, const char *name, const char *target)
{
	susetest_config_group_t *node;

	if (!(node = susetest_config_group_add_child(cfg, "node", name, true)))
		return NULL;

	if (target)
		susetest_node_config_set_target(node, target);
	return node;
}

void
susetest_config_set_attr(susetest_config_t *cfg, const char *name, const char *value)
{
	__susetest_config_set_attr(&cfg->attrs, name, value);
}

void
susetest_config_set_attr_list(susetest_config_t *cfg, const char *name, const char * const *values)
{
	__susetest_config_set_attr_list(&cfg->attrs, name, values);
}

void
susetest_config_add_attr_list(susetest_config_t *cfg, const char *name, const char *value)
{
	__susetest_config_add_attr_list(&cfg->attrs, name, value);
}

const char *
susetest_config_get_attr(susetest_config_t *cfg, const char *name)
{
	return __susetest_config_get_attr(&cfg->attrs, name);
}

const char * const *
susetest_config_get_attr_list(susetest_config_t *cfg, const char *name)
{
	return __susetest_config_get_attr_list(&cfg->attrs, name);
}

const char **
susetest_config_get_nodes(const susetest_config_t *cfg)
{
	return susetest_config_group_get_children(cfg, "node");
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
		attr->values = attr->short_list;
		*pos = attr;
		return attr;
	}

	return NULL;
}

static void
__susetest_config_drop_attr(susetest_config_attr_t **list, const char *name)
{
	susetest_config_attr_t **pos, *attr;

	for (pos = list; (attr = *pos) != NULL; pos = &attr->next) {
		if (!strcmp(attr->name, name)) {
			*pos = attr->next;
			__susetest_config_attr_free(attr);
			return;
		}
	}
}

static void
__susetest_config_attr_append(susetest_config_attr_t *attr, const char *value)
{
	char *s;

	if (attr->nvalues >= SUSETEST_CONFIG_SHORTLIST_MAX) {
		unsigned int new_size;

		new_size = (attr->nvalues + 2) * sizeof(char *);
		if (attr->values == attr->short_list) {
			attr->values = malloc(new_size);
			memcpy(attr->values, attr->short_list, sizeof(attr->short_list));
		} else {
			attr->values = realloc(attr->values, new_size);
		}
	}

	attr->values[attr->nvalues++] = s = strdup(value);
	attr->values[attr->nvalues] = NULL;

	/* Replace newlines with a blank */
	while ((s = strchr(s, '\n')) != NULL)
		*s = ' ';
}

void
__susetest_config_set_attr(susetest_config_attr_t **list, const char *name, const char *value)
{
	susetest_config_attr_t *attr;

	if (value == NULL || *value == '\0') {
		__susetest_config_drop_attr(list, name);
	} else {
		attr = __susetest_config_find_attr(list, name, 1);
		__susetest_config_attr_clear(attr);
		__susetest_config_attr_append(attr, value);
	}
}

void
__susetest_config_set_attr_list(susetest_config_attr_t **attr_list, const char *name, const char * const *values)
{
	susetest_config_attr_t *attr;

	if (values == NULL || *values == NULL) {
		__susetest_config_drop_attr(attr_list, name);
	} else {
		attr = __susetest_config_find_attr(attr_list, name, 1);
		__susetest_config_attr_clear(attr);

		while (values && *values)
			__susetest_config_attr_append(attr, *values++);
	}
}

void
__susetest_config_add_attr_list(susetest_config_attr_t **attr_list, const char *name, const char *value)
{
	susetest_config_attr_t *attr;

	attr = __susetest_config_find_attr(attr_list, name, 1);
	if (value == NULL)
		return;

	__susetest_config_attr_append(attr, value);
}

const char *
__susetest_config_get_attr(susetest_config_attr_t **list, const char *name)
{
	susetest_config_attr_t *attr;

	attr = __susetest_config_find_attr(list, name, 0);
	if (attr && attr->nvalues)
		return attr->values[0];
	return NULL;
}

const char * const *
__susetest_config_get_attr_list(susetest_config_attr_t **attr_list, const char *name)
{
	susetest_config_attr_t *attr;

	attr = __susetest_config_find_attr(attr_list, name, 0);
	if (attr && attr->nvalues)
		return (const char * const *) attr->values;
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

static void
__susetest_config_attr_clear(susetest_config_attr_t *attr)
{
	unsigned int n;

	for (n = 0; n < attr->nvalues; ++n)
		free(attr->values[n]);
	if (attr->values != attr->short_list)
		free(attr->values);
	attr->values = attr->short_list;
	attr->nvalues = 0;
}

static void
__susetest_config_attr_free(susetest_config_attr_t *attr)
{
	free(attr->name);
	__susetest_config_attr_clear(attr);
	free(attr);
}

void
__susetest_config_attrs_free(susetest_config_attr_t **list)
{
	susetest_config_attr_t *attr;

	while ((attr = *list) != NULL) {
		*list = attr->next;

		__susetest_config_attr_free(attr);
	}
}

/*
 * I/O routines
 */
int
susetest_config_write(susetest_config_t *cfg, const char *path)
{
	FILE *fp;

	if ((fp = fopen(path, "w")) == NULL) {
		fprintf(stderr, "Unable to open %s: %m\n", path);
		return -1;
	}

	curly_print(cfg, fp);
	fclose(fp);
	return 0;
}

susetest_config_t *
susetest_config_read(const char *path)
{
	return curly_parse(path);
}
