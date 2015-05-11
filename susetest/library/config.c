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

static susetest_config_t *__susetest_config_new(const char *type, const char *name);
static void		__susetest_config_free(susetest_config_t *cfg);
static void		__susetest_config_attrs_free(susetest_config_attr_t **);
static void		__susetest_config_set_attr(susetest_config_attr_t **, const char *, const char *);
static void		__susetest_config_add_attr_list(susetest_config_attr_t **, const char *, const char *);
static void		__susetest_config_set_attr_list(susetest_config_attr_t **, const char *, const char * const *);
static void		__susetest_config_copy_attrs(susetest_config_attr_t **dst, const susetest_config_attr_t *src);
static const char *	__susetest_config_get_attr(susetest_config_attr_t **, const char *);
static void		__susetest_config_drop_attr(susetest_config_attr_t **, const char *);
static const char * const *__susetest_config_get_attr_list(susetest_config_attr_t **, const char *);
static const char **	__susetest_config_attr_names(susetest_config_attr_t * const*);
static susetest_config_attr_t *__susetest_config_attr_new(const char *name);
static susetest_config_attr_t *__susetest_config_attr_clone(const susetest_config_attr_t *src_attr);
static void		__susetest_config_attr_free(susetest_config_attr_t *attr);
static void		__susetest_config_attr_clear(susetest_config_attr_t *attr);

static inline int
xstrcmp(const char *a, const char *b)
{
	if (a == NULL || b == NULL)
		return a == b;
	return strcmp(a, b);
}

/*
 * Constructor
 */
susetest_config_t *
susetest_config_new(void)
{
	return __susetest_config_new("root", NULL);
}

static susetest_config_t *
__susetest_config_new(const char *type, const char *name)
{
	susetest_config_t *cfg;

	cfg = (susetest_config_t *) calloc(1, sizeof(*cfg));
	cfg->type = type? strdup(type) : NULL;
	cfg->name = name? strdup(name) : NULL;
	return cfg;
}

/*
 * Destructor
 */
void
susetest_config_free(susetest_config_t *cfg)
{
	__susetest_config_free(cfg);
}

static void
__susetest_config_clear(susetest_config_t *cfg)
{
	susetest_config_t *child;

	/* This function clears out all children and attributes,
	 * but leaves the type/name information intact
	 */
	while ((child = cfg->children) != NULL) {
		cfg->children = child->next;
		susetest_config_free(child);
	}

	__susetest_config_attrs_free(&cfg->attrs);
}

static void
__susetest_config_free(susetest_config_t *cfg)
{
	__susetest_config_clear(cfg);

	if (cfg->type)
		free(cfg->type);
	cfg->type = NULL;

	if (cfg->name)
		free(cfg->name);
	cfg->name = NULL;

	free(cfg);
}

/*
 * Accessor functions for child nodes
 */
susetest_config_t *
susetest_config_get_child(const susetest_config_t *cfg, const char *type, const char *name)
{
	susetest_config_t *child;

	for (child = cfg->children; child; child = child->next) {
		if (type && xstrcmp(child->type, type))
			continue;
		if (name && xstrcmp(child->name, name))
			continue;
		return child;
	}
	return NULL;
}


susetest_config_t *
susetest_config_add_child(susetest_config_t *cfg, const char *type, const char *name)
{
	susetest_config_t *child, **pos;

	if (susetest_config_get_child(cfg, type, name) != NULL) {
		fprintf(stderr, "duplicate %s group named \"%s\"\n", type, name);
		return NULL;
	}

	/* Find the tail of the list */
	for (pos = &cfg->children; (child = *pos) != NULL; pos = &child->next)
		;

	*pos = child = __susetest_config_new(type, name);
	return child;
}


const char **
susetest_config_get_children(const susetest_config_t *cfg, const char *type)
{
	const susetest_config_t *node;
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
susetest_config_get_attr_names(const susetest_config_t *cfg)
{
	return __susetest_config_attr_names(&cfg->attrs);
}

/*
 * Copy all attributes and children from one config node to another
 */
void
susetest_config_copy(susetest_config_t *dst, const susetest_config_t *src)
{
	const susetest_config_t *src_child;
	susetest_config_t **pos;

	__susetest_config_clear(dst);
	__susetest_config_copy_attrs(&dst->attrs, src->attrs);

	pos = &dst->children;
	for (src_child = src->children; src_child; src_child = src_child->next) {
		susetest_config_t *clone;

		/* Recursively create a deep copy of the child node */
		clone = __susetest_config_new(src_child->type, src_child->name);
		susetest_config_copy(clone, src_child);

		/* Append to list */
		*pos = clone;
		pos = &clone->next;
	}
}

/*
 * Attribute accessors
 */
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

static susetest_config_attr_t *
__susetest_config_find_attr(susetest_config_attr_t **list, const char *name, int create)
{
	susetest_config_attr_t **pos, *attr;

	for (pos = list; (attr = *pos) != NULL; pos = &attr->next) {
		if (!strcmp(attr->name, name))
			return attr;
	}

	if (!create)
		return NULL;

	*pos = __susetest_config_attr_new(name);
	return *pos;
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

void
__susetest_config_copy_attrs(susetest_config_attr_t **dst, const susetest_config_attr_t *src_attr)
{
	__susetest_config_attrs_free(dst);

	while (src_attr != NULL) {
		*dst = __susetest_config_attr_clone(src_attr);
		src_attr = src_attr->next;
		dst = &(*dst)->next;
	}
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

static susetest_config_attr_t *
__susetest_config_attr_new(const char *name)
{
	susetest_config_attr_t *attr;

	attr = calloc(1, sizeof(*attr));
	attr->name = strdup(name);
	attr->values = attr->short_list;
	return attr;
}

static susetest_config_attr_t *
__susetest_config_attr_clone(const susetest_config_attr_t *src_attr)
{
	susetest_config_attr_t *attr;
	char **values;

	attr = __susetest_config_attr_new(src_attr->name);

	values = src_attr->values;
	while (values && *values)
		__susetest_config_attr_append(attr, *values++);
	return attr;
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
static int
susetest_config_guess_format(const char *path)
{
	int result = SUSETEST_CONFIG_FMT_DEFAULT;
	char buffer[256];
	FILE *fp;

	if ((fp = fopen(path, "r")) == NULL)
		return SUSETEST_CONFIG_FMT_DEFAULT;

	while (fgets(buffer, sizeof(buffer), fp) != NULL) {
		char *s = buffer;

		while (isspace(*s))
			++s;

		switch (*s) {
		case '\0':
			/* Empty line, keep looping */
			break;

		case '<':
			result = SUSETEST_CONFIG_FMT_XML;
			goto out;

		default:
			result = SUSETEST_CONFIG_FMT_CURLY;
			goto out;
		}
	}
out:
	fclose(fp);
	return result;
}

int
susetest_config_format_from_string(const char *s)
{
	if (s == NULL || !strcasecmp(s, "default"))
		return SUSETEST_CONFIG_FMT_DEFAULT;
	if (!strcasecmp(s, "xml"))
		return SUSETEST_CONFIG_FMT_XML;
	if (!strcasecmp(s, "curly"))
		return SUSETEST_CONFIG_FMT_CURLY;

	return SUSETEST_CONFIG_FMT_INVALID;
}

const char *
susetest_config_format_to_string(int fmt)
{
	switch (fmt) {
	case SUSETEST_CONFIG_FMT_DEFAULT:
		return "default";
	case SUSETEST_CONFIG_FMT_INVALID:
		return "invalid";
	case SUSETEST_CONFIG_FMT_XML:
		return "xml";
	case SUSETEST_CONFIG_FMT_CURLY:
		return "curly";
	}

	return "unknown";
}

int
susetest_config_write(susetest_config_t *cfg, const char *path, int fmt)
{
	if (fmt == SUSETEST_CONFIG_FMT_DEFAULT)
		fmt = susetest_config_guess_format(path);

	if (fmt == SUSETEST_CONFIG_FMT_CURLY)
		susetest_config_write_curly(cfg, path);
	else
		susetest_config_write_xml(cfg, path);
	return 0;
}

int
susetest_config_write_curly(susetest_config_t *cfg, const char *path)
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
susetest_config_read(const char *path, int *format_p)
{
	susetest_config_t *cfg;
	int fmt;

	fmt = susetest_config_guess_format(path);
	if (format_p)
		*format_p = fmt;

	if (fmt == SUSETEST_CONFIG_FMT_CURLY)
		cfg = susetest_config_read_curly(path);
	else
		cfg = susetest_config_read_xml(path);
	/* fprintf(stderr, "%s: root node type=%s name=%s\n", __func__, cfg->type, cfg->name); */
	return cfg;
}

susetest_config_t *
susetest_config_read_curly(const char *path)
{
	susetest_config_t *cfg;

	cfg = curly_parse(path);
	return cfg;
}

/*
 * XML I/O routines for config
 *
 * For now, very straightforward
 */
#include "xml.h"

static void
susetest_config_to_xml(const susetest_config_t *cfg, xml_node_t *parent)
{
	const susetest_config_attr_t *attr;
	const susetest_config_t *child;
	xml_node_t *node;

	node = xml_node_new(cfg->type, parent);
	if (cfg->name)
		xml_node_add_attr(node, "name", cfg->name);

	for (attr = cfg->attrs; attr; attr = attr->next) {
		if (attr->nvalues != 1)
			continue;
		xml_node_add_attr(node, attr->name, attr->values[0]);
	}

	for (child = cfg->children; child; child = child->next) {
		susetest_config_to_xml(child, node);
	}
}

static susetest_config_t *
susetest_config_from_xml(const xml_node_t *node)
{
	susetest_config_t *result, **tail;
	xml_node_t *child;
	const char *name;
	unsigned int i;

	name = xml_node_get_attr(node, "name");

	result = __susetest_config_new(node->name, name);
	for (i = 0; i < node->attrs.count; ++i) {
		xml_attr_t *ap = &node->attrs.data[i];

		if (strcmp(ap->name, "name") && ap->value != NULL)
			susetest_config_set_attr(result, ap->name, ap->value);
	}

	tail = &result->children;
	for (child = node->children; child; child = child->next) {
		*tail = susetest_config_from_xml(child);
		tail = &(*tail)->next;
	}

	return result;
}

int
susetest_config_write_xml(susetest_config_t *cfg, const char *path)
{
	susetest_config_t testenv_cfg;
	xml_document_t *doc;

	/* If this was read from a curly file, the top node will be
	 * named "root".
	 * Fake a testenv node if needed
	 */
	if (cfg->type && !strcmp(cfg->type, "root") && cfg->name == NULL) {
		susetest_config_t *child = cfg->children;

		if (child->type && !strcmp(child->type, "testenv") && child->next == NULL) {
			/* We just continue with this */
			cfg = child;
		} else {
			testenv_cfg = *cfg;
			testenv_cfg.type = "testenv";
			testenv_cfg.name = "unknown";
			cfg = &testenv_cfg;

		}
	}

	doc = xml_document_new();
	susetest_config_to_xml(cfg, doc->root);

	xml_document_write(doc, path);
	xml_document_free(doc);
	return 0;
}

susetest_config_t *
susetest_config_read_xml(const char *path)
{
	susetest_config_t *cfg;
	xml_document_t *doc;

	doc = xml_document_read(path);
	if (doc == NULL)
		return NULL;

	cfg = susetest_config_from_xml(doc->root);
	xml_document_free(doc);

	if (cfg->type == NULL)
		cfg->type = strdup("root");
	return cfg;
}
