/*
 *	XML objects - document and node
 *
 *	Copyright (C) 2009-2014  Olaf Kirch <okir@suse.de>
 *
 *	This program is free software; you can redistribute it and/or modify
 *	it under the terms of the GNU General Public License as published by
 *	the Free Software Foundation; either version 2 of the License, or
 *	(at your option) any later version.
 *
 *	This program is distributed in the hope that it will be useful,
 *	but WITHOUT ANY WARRANTY; without even the implied warranty of
 *	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *	GNU General Public License for more details.
 *
 *	You should have received a copy of the GNU General Public License along
 *	with this program; if not, see <http://www.gnu.org/licenses/> or write 
 *	to the Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, 
 *	Boston, MA 02110-1301 USA.
 *
 */

#include <stdlib.h>
#include <assert.h>
#include "xml.h"
#include "util.h"

#define XML_DOCUMENTARRAY_CHUNK		1
#define XML_NODEARRAY_CHUNK		8

xml_document_t *
xml_document_new()
{
	xml_document_t *doc;

	doc = calloc(1, sizeof(*doc));
	doc->root = xml_node_new(NULL, NULL);
	return doc;
}

xml_node_t *
xml_document_root(xml_document_t *doc)
{
	return doc->root;
}

const char *
xml_document_type(const xml_document_t *doc)
{
	return doc->dtd;
}

void
xml_document_set_root(xml_document_t *doc, xml_node_t *root)
{
	if (doc->root != root) {
		xml_node_free(doc->root);
		doc->root = root;
	}
}

xml_node_t *
xml_document_take_root(xml_document_t *doc)
{
	xml_node_t *root = doc->root;

	doc->root = NULL;
	return root;
}

void
xml_document_free(xml_document_t *doc)
{
	if (doc) {
		xml_node_free(doc->root);
		__drop_string(&doc->dtd);
		free(doc);
	}
}

/*
 * Helper functions for XML attribute management
 */
static xml_attr_t *
__xml_attr_array_get(const xml_attr_array_t *attrs, const char *name)
{
	xml_attr_t *attr;
	unsigned int i;

	for (i = 0, attr = attrs->data; i < attrs->count; ++i, ++attr) {
		if (__string_equal(attr->name, name))
			return attr;
	}

	return NULL;
}

static bool
__xml_attr_array_remove(xml_attr_array_t *attrs, const char *name)
{
	xml_attr_t *attr;
	unsigned int i;

	for (i = 0, attr = attrs->data; i < attrs->count; ++i, ++attr) {
		if (__string_equal(attr->name, name)) {
			__drop_string(&attr->name);
			__drop_string(&attr->value);
			memmove(attrs->data + i, attrs->data + i + 1,
					(attrs->count - i - 1) * sizeof(xml_attr_t));
			attrs->count -= 1;
			return attr;
		}
	}

	return NULL;
}

void
xml_attr_array_set(xml_attr_array_t *attrs, const char *name, const char *value)
{
	xml_attr_t *attr;

	if ((attr = __xml_attr_array_get(attrs, name)) == NULL) {
		attrs->data = realloc(attrs->data, (attrs->count + 1) * sizeof(xml_attr_t));
		attr = &attrs->data[attrs->count++];
		memset(attr, 0, sizeof(*attr));
		__set_string(&attr->name, name);
	}
	__set_string(&attr->value, value);
}

void
xml_attr_array_destroy(xml_attr_array_t *attrs)
{
	xml_attr_t *attr;
	unsigned int i;

	for (i = 0, attr = attrs->data; i < attrs->count; ++i, ++attr) {
		__drop_string(&attr->name);
		__drop_string(&attr->value);
	}
	if (attrs->data)
		free(attrs->data);
	memset(attrs, 0, sizeof(*attrs));
}

/*
 * Helper functions for xml node list management
 */
static inline void
__xml_node_list_insert(xml_node_t **pos, xml_node_t *node, xml_node_t *parent)
{
	node->parent = parent;
	node->next = *pos;
	*pos = node;
}

static inline xml_node_t *
__xml_node_list_remove(xml_node_t **pos)
{
	xml_node_t *np = *pos;

	if (np) {
		np->parent = NULL;
		*pos = np->next;
		np->next = NULL;
	}

	return np;
}

static inline void
__xml_node_list_drop(xml_node_t **pos)
{
	xml_node_t *np;

	if ((np = __xml_node_list_remove(pos)) != NULL)
		xml_node_free(np);
}

static inline xml_node_t **
__xml_node_list_tail(xml_node_t **pos)
{
	xml_node_t *np;

	while ((np = *pos) != NULL)
		pos = &np->next;
	return pos;
}

void
xml_node_add_child(xml_node_t *parent, xml_node_t *child)
{
	xml_node_t **tail;

	assert(child->parent == NULL);

	tail = __xml_node_list_tail(&parent->children);
	__xml_node_list_insert(tail, child, parent);
}

xml_node_t *
xml_node_new(const char *ident, xml_node_t *parent)
{
	xml_node_t *node;

	node = calloc(1, sizeof(xml_node_t));
	if (ident)
		__set_string(&node->name, ident);

	if (parent)
		xml_node_add_child(parent, node);
	node->refcount = 1;

	return node;
}

xml_node_t *
xml_node_new_element(const char *ident, xml_node_t *parent, const char *cdata)
{
	xml_node_t *node = xml_node_new(ident, parent);

	if (cdata)
		xml_node_set_cdata(node, cdata);
	return node;
}

xml_node_t *
xml_cdata_new(xml_node_t *parent, const char *data)
{
	return xml_node_new_element("![CDATA[", parent, data);
}

xml_node_t *
xml_node_new_element_unique(const char *ident, xml_node_t *parent, const char *cdata)
{
	xml_node_t *node;

	if (parent == NULL || (node = xml_node_get_child(parent, ident)) == NULL)
		node = xml_node_new(ident, parent);

	xml_node_set_cdata(node, cdata);
	return node;
}

xml_node_t *
xml_node_new_element_int(const char *ident, xml_node_t *parent, int value)
{
	xml_node_t *node = xml_node_new(ident, parent);

	xml_node_set_int(node, value);
	return node;
}

xml_node_t *
xml_node_new_element_uint(const char *ident, xml_node_t *parent, unsigned int value)
{
	xml_node_t *node = xml_node_new(ident, parent);

	xml_node_set_uint(node, value);
	return node;
}

/*
 * Clone an XML node and all its descendants
 */
xml_node_t *
xml_node_clone(const xml_node_t *src, xml_node_t *parent)
{
	xml_node_t *dst, *child;
	const xml_attr_t *attr;
	unsigned int i;

	dst = xml_node_new(src->name, parent);
	__set_string(&dst->cdata, src->cdata);

	for (i = 0, attr = src->attrs.data; i < src->attrs.count; ++i, ++attr)
		xml_node_add_attr(dst, attr->name, attr->value);

	for (child = src->children; child; child = child->next)
		xml_node_clone(child, dst);

	return dst;
}

/*
 * "Clone" an XML node by incrementing its refcount
 */
xml_node_t *
xml_node_clone_ref(xml_node_t *src)
{
	assert(src->refcount);
	src->refcount++;
	return src;
}

/*
 * Merge node @merge into node @base.
 */
void
xml_node_merge(xml_node_t *base, const xml_node_t *merge)
{
	const xml_node_t *mchild;

	for (mchild = merge->children; mchild; mchild = mchild->next) {
		xml_node_t **pos, *np, *clone;

		for (pos = &base->children; (np = *pos) != NULL; pos = &np->next) {
			if (__string_equal(mchild->name, np->name))
				goto dont_merge;
		}

		clone = xml_node_clone(mchild, NULL);
		__xml_node_list_insert(pos, clone, base);

dont_merge: ;
	}
}



/*
 * Free an XML node
 */
void
xml_node_free(xml_node_t *node)
{
	xml_node_t *child;

	if (!node)
		return;

	assert(node->refcount);
	if (--(node->refcount) != 0)
		return;

	while ((child = node->children) != NULL) {
		node->children = child->next;
		xml_node_free(child);
	}

	xml_attr_array_destroy(&node->attrs);
	free(node->cdata);
	free(node->name);
	free(node);
}

void
xml_node_set_cdata(xml_node_t *node, const char *cdata)
{
	__set_string(&node->cdata, cdata);
}

void
xml_node_set_int(xml_node_t *node, int value)
{
	char buffer[32];

	snprintf(buffer, sizeof(buffer), "%d", value);
	__set_string(&node->cdata, buffer);
}

void
xml_node_set_uint(xml_node_t *node, unsigned int value)
{
	char buffer[32];

	snprintf(buffer, sizeof(buffer), "%u", value);
	__set_string(&node->cdata, buffer);
}

void
xml_node_set_uint_hex(xml_node_t *node, unsigned int value)
{
	char buffer[32];

	snprintf(buffer, sizeof(buffer), "0x%x", value);
	__set_string(&node->cdata, buffer);
}

void
xml_node_add_attr(xml_node_t *node, const char *name, const char *value)
{
	xml_attr_array_set(&node->attrs, name, value);
}

void
xml_node_add_attr_uint(xml_node_t *node, const char *name, unsigned int value)
{
	char buffer[64];

	snprintf(buffer, sizeof(buffer), "%u", value);
	xml_attr_array_set(&node->attrs, name, buffer);
}

void
xml_node_add_attr_ulong(xml_node_t *node, const char *name, unsigned long value)
{
	char buffer[64];

	snprintf(buffer, sizeof(buffer), "%lu", value);
	xml_attr_array_set(&node->attrs, name, buffer);
}

void
xml_node_add_attr_double(xml_node_t *node, const char *name, double value)
{
	char buffer[64];

	snprintf(buffer, sizeof(buffer), "%f", value);
	xml_attr_array_set(&node->attrs, name, buffer);
}

const xml_attr_t *
xml_node_get_attr_var(const xml_node_t *node, const char *name)
{
	return node ? __xml_attr_array_get(&node->attrs, name) : NULL;
}

bool
xml_node_has_attr(const xml_node_t *node, const char *name)
{
	return xml_node_get_attr_var(node, name) != NULL;
}

const char *
xml_node_get_attr(const xml_node_t *node, const char *name)
{
	const xml_attr_t *attr;

	if (!(attr = xml_node_get_attr_var(node, name)))
		return NULL;
	return attr->value;
}

bool
xml_node_del_attr(xml_node_t *node, const char *name)
{
	return node ? __xml_attr_array_remove(&node->attrs, name) : false;
}

bool
xml_node_get_attr_uint(const xml_node_t *node, const char *name, unsigned int *valp)
{
	const char *value, *end;

	if (!valp || !(value = xml_node_get_attr(node, name)))
		return false;

	*valp = strtoul(value, (char **) &end, 10);
	if (*end)
		return false;

	return true;
}

bool
xml_node_get_attr_ulong(const xml_node_t *node, const char *name, unsigned long *valp)
{
	const char *value, *end;

	if (!valp || !(value = xml_node_get_attr(node, name)))
		return false;

	*valp = strtoul(value, (char **) &end, 10);
	if (*end)
		return false;

	return true;
}

bool
xml_node_get_attr_double(const xml_node_t *node, const char *name, double *valp)
{
	const char *value, *end;

	if (!valp || !(value = xml_node_get_attr(node, name)))
		return false;

	*valp = strtod(value, (char **) &end);
	if (*end)
		return false;

	return true;
}

/*
 * Find a child element given its name
 */
xml_node_t *
xml_node_get_next_child(const xml_node_t *top, const char *name, const xml_node_t *cur)
{
	xml_node_t *child;

	if (top == NULL)
		return NULL;
	for (child = cur ? cur->next : top->children; child; child = child->next) {
		if (!strcmp(child->name, name))
			return child;
	}

	return NULL;
}

inline xml_node_t *
xml_node_get_child(const xml_node_t *node, const char *name)
{
	return xml_node_get_next_child(node, name, NULL);
}

/*
 * Find a child element given its name and a list of attributes
 */
xml_node_t *
xml_node_get_child_with_attrs(const xml_node_t *node, const char *name,
		const xml_attr_array_t *attrs)
{
	xml_node_t *child;

	for (child = node->children; child; child = child->next) {
		if (!strcmp(child->name, name)
		 && xml_node_match_attrs(child, attrs))
			return child;
	}
	return NULL;
}

bool
xml_node_replace_child(xml_node_t *node, xml_node_t *newchild)
{
	xml_node_t **pos, *child;
	bool found = false;

	pos = &node->children;
	while ((child = *pos) != NULL) {
		if (!strcmp(child->name, newchild->name)) {
			__xml_node_list_drop(pos);
			found = true;
		} else {
			pos = &child->next;
		}
	}

	__xml_node_list_insert(pos, newchild, node);
	return found;
}

bool
xml_node_delete_child(xml_node_t *node, const char *name)
{
	xml_node_t **pos, *child;
	bool found = false;

	pos = &node->children;
	while ((child = *pos) != NULL) {
		if (!strcmp(child->name, name)) {
			__xml_node_list_drop(pos);
			found = true;
		} else {
			pos = &child->next;
		}
	}

	return found;
}

bool
xml_node_delete_child_node(xml_node_t *node, xml_node_t *destroy)
{
	xml_node_t **pos, *child;

	assert(destroy->parent == node);

	pos = &node->children;
	while ((child = *pos) != NULL) {
		if (child == destroy) {
			__xml_node_list_drop(pos);
			return true;
		}
		pos = &child->next;
	}

	return false;
}

void
xml_node_detach(xml_node_t *node)
{
	xml_node_t *parent, **pos, *sibling;

	if ((parent = node->parent) == NULL)
		return;

	pos = &parent->children;
	while ((sibling = *pos) != NULL) {
		if (sibling == node) {
			__xml_node_list_remove(pos);
			break;
		}
		pos = &sibling->next;
	}
}

void
xml_node_reparent(xml_node_t *parent, xml_node_t *child)
{
	if (child->parent)
		xml_node_detach(child);
	xml_node_add_child(parent, child);
}

/*
 * Get xml node path relative to some top node
 */
static const char *
__xml_node_path(const xml_node_t *node, const xml_node_t *top, char *buf, size_t size)
{
	unsigned int offset = 0;

	if (node->parent && node->parent != top) {
		__xml_node_path(node->parent, top, buf, size);
		offset = strlen(buf);
		if ((offset == 0 || buf[offset-1] != '/') && offset < size)
			buf[offset++] = '/';
	}

	if (node->name == NULL && node->parent == NULL) {
		/* this is the root node */
		strcpy(buf, "/");
	} else {
		snprintf(buf + offset, size - offset, "%s", node->name);
	}
	return buf;
}

const char *
xml_node_path(const xml_node_t *node, const xml_node_t *top)
{
	static char pathbuf[1024];

	return __xml_node_path(node, top, pathbuf, sizeof(pathbuf));
}

/*
 * Traverse an xml tree, depth first.
 */
xml_node_t *
xml_node_get_next(xml_node_t *top, xml_node_t *cur)
{
	if (cur == NULL) {
		/* Start at the top node and descend */
		cur = top;
	} else {
		/* We've already visited this node. Get the
		 * next one.
		 * By default, move right, then down. If there's
		 * no right sibling, move up and repeat.
		 */

		/* No next sibling: move up, then right */
		if (cur->next == NULL) {
			if (cur == top || cur->parent == top)
				return NULL;
			cur = cur->parent;
			assert(cur);
			return cur;
		}
		cur = cur->next;
	}

	/* depth first */
	while (cur->children)
		cur = cur->children;

	return cur;
}

xml_node_t *
xml_node_get_next_named(xml_node_t *top, const char *name, xml_node_t *cur)
{
	while ((cur = xml_node_get_next(top, cur)) != NULL) {
		if (!strcmp(cur->name, name))
			return cur;
	}

	return NULL;
}

/*
 * XML node matching functions
 */
bool
xml_node_match_attrs(const xml_node_t *node, const xml_attr_array_t *attrlist)
{
	unsigned int i;
	xml_attr_t *attr;

	for (i = 0, attr = attrlist->data; i < attrlist->count; ++i, ++attr) {
		const char *value;

		value = xml_node_get_attr(node, attr->name);
		if (attr->value == NULL || value == NULL) {
			if (attr->value != value)
				return false;
		} else if (strcmp(attr->value, value)) {
			return false;
		}
	}
	return true;
}

/*
 * XML node arrays
 */
void
xml_node_array_init(xml_node_array_t *array)
{
	memset(array, 0, sizeof(*array));
}

void
xml_node_array_destroy(xml_node_array_t *array)
{
	unsigned int i;

	for (i = 0; i < array->count; ++i)
		xml_node_free(array->data[i]);

	if (array->data)
		free(array->data);
	memset(array, 0, sizeof(*array));
}

xml_node_array_t *
xml_node_array_new(void)
{
	xml_node_array_t *array;

	array = calloc(1, sizeof(*array));
	return array;
}

void
xml_node_array_free(xml_node_array_t *array)
{
	xml_node_array_destroy(array);
	free(array);
}

static void
__xml_node_array_realloc(xml_node_array_t *array, unsigned int newsize)
{
	xml_node_t **newdata;
	unsigned int i;

	newsize = (newsize + XML_NODEARRAY_CHUNK) + 1;
	newdata = realloc(array->data, newsize * sizeof(array->data[0]));

	array->data = newdata;
	for (i = array->count; i < newsize; ++i)
		array->data[i] = NULL;
}

void
xml_node_array_append(xml_node_array_t *array, xml_node_t *node)
{
	if ((array->count % XML_NODEARRAY_CHUNK) == 0)
		__xml_node_array_realloc(array, array->count);

	array->data[array->count++] = xml_node_clone_ref(node);
}

xml_node_t *
xml_node_create(xml_node_t *parent, const char *name)
{
	xml_node_t *child;

	if ((child = xml_node_get_child(parent, name)) == NULL)
		child = xml_node_new(name, parent);
	return child;
}

void
xml_node_dict_set(xml_node_t *parent, const char *name, const char *value)
{
	xml_node_t *child;

	if (!value || !*value)
		return;

	child = xml_node_create(parent, name);
	xml_node_set_cdata(child, value);
}
