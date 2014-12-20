/*
 *	VERY limited XML read/write implementation
 *	This basically parses tags, attributes and CDATA, and that's
 *	just about it.
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
#include <string.h>
#include <stdarg.h>
#include "xml.h"
#include "util.h"

typedef struct xml_writer {
	FILE *		file;
	unsigned int	noclose : 1;
} xml_writer_t;

static int		xml_writer_open(xml_writer_t *, const char *);
static int		xml_writer_init_file(xml_writer_t *, FILE *);
static int		xml_writer_close(xml_writer_t *);
static int		xml_writer_destroy(xml_writer_t *);
static void		xml_writer_printf(xml_writer_t *, const char *, ...);

static void		xml_document_output(const xml_document_t *, xml_writer_t *);
static void		xml_node_output(const xml_node_t *node, xml_writer_t *, unsigned int indent);
static const char *	xml_escape_quote(const char *);
static const char *	xml_escape_entities(const char *, char **);

int
xml_document_write(const xml_document_t *doc, const char *filename)
{
	xml_writer_t writer;

	if (xml_writer_open(&writer, filename) < 0)
		return -1;

	xml_document_output(doc, &writer);
	return xml_writer_destroy(&writer);
}

int
xml_document_print(const xml_document_t *doc, FILE *fp)
{
	xml_writer_t writer;

	if (xml_writer_init_file(&writer, fp? fp : stdout) < 0)
		return -1;

	xml_document_output(doc, &writer);
	return xml_writer_destroy(&writer);
}

char *
xml_document_sprint(const xml_document_t *doc)
{
	char *string = NULL;
	size_t size = 0;
	FILE *fp;
	int rv;

	if ((fp = open_memstream(&string, &size)) == NULL) {
		fprintf(stderr, "%s: unable to open memstream", __func__);
		return NULL;
	}

	rv = xml_document_print(doc, fp);
	fclose(fp);

	if (rv < 0) {
		free(string);
		return NULL;
	}

	return string;
}

void
xml_document_output(const xml_document_t *doc, xml_writer_t *writer)
{
	xml_writer_printf(writer, "<?xml version=\"1.0\" encoding=\"utf8\"?>\n");
	xml_node_output(doc->root, writer, 0);
}

int
xml_node_print(const xml_node_t *node, FILE *fp)
{
	xml_writer_t writer;
	int rv = 0;

	if (xml_writer_init_file(&writer, fp? fp : stdout) >= 0) {
		xml_node_output(node, &writer, 0);
		rv = xml_writer_destroy(&writer);
	}

	return rv;
}

char *
xml_node_sprint(const xml_node_t *node)
{
	char *string = NULL;
	size_t size = 0;
	FILE *fp;
	int rv;

	if ((fp = open_memstream(&string, &size)) == NULL) {
		fprintf(stderr, "%s: unable to open memstream", __func__);
		return NULL;
	}

	rv = xml_node_print(node, fp);
	fclose(fp);

	if (rv < 0) {
		free(string);
		return NULL;
	}

	return string;
}

int
xml_node_print_fn(const xml_node_t *node, void (*writefn)(const char *, void *), void *user_data)
{
	char *membuf = NULL;
	size_t memsz = 0;
	FILE *memf;
	int rv;

	memf = open_memstream(&membuf, &memsz);
	rv = xml_node_print(node, memf);
	fclose(memf);

	if (rv >= 0) {
		char *s, *t;

		for (s = membuf; s; s = t) {
			if ((t = strchr(s, '\n')) != NULL)
				*t++ = '\0';
			writefn(s, user_data);
		}
	}

	free(membuf);
	return rv;
}

void
xml_node_output(const xml_node_t *node, xml_writer_t *writer, unsigned int indent)
{
	unsigned int child_indent = indent;
	int newline = 0;

	if (__string_equal(node->name, "![CDATA[")) {
		xml_writer_printf(writer, "%*.*s<%s", indent, indent, "", node->name);
		xml_writer_printf(writer, "%s", node->cdata);
		xml_writer_printf(writer, "]]>\n");
		return;
	} else
	if (node->name != NULL) {
		xml_attr_t *attr;
		unsigned int i;

		xml_writer_printf(writer, "%*.*s<%s", indent, indent, "", node->name);
		for (i = 0, attr = node->attrs.data; i < node->attrs.count; ++i, ++attr) {
			if (attr->value)
				xml_writer_printf(writer, " %s=\"%s\"",
						attr->name, xml_escape_quote(attr->value));
			else
				xml_writer_printf(writer, " %s", attr->name);
		}

		if (node->cdata == NULL && node->children == NULL) {
			xml_writer_printf(writer, "/>\n");
			return;
		}
		xml_writer_printf(writer, ">");
		child_indent += 2;
	} else {
		newline = 1;
	}

	if (node->cdata) {
		unsigned int len;
		char *temp = NULL;

		if (strchr(node->cdata, '\n')) {
			xml_writer_printf(writer, "\n");
			newline = 1;
		}
		xml_writer_printf(writer, "%s", xml_escape_entities(node->cdata, &temp));
		__drop_string(&temp);

		if (newline) {
			len = strlen(node->cdata);
			if (len && node->cdata[len-1] != '\n')
				xml_writer_printf(writer, "\n");
		}
	}
	if (node->children) {
		xml_node_t *child;

		if (!newline)
			xml_writer_printf(writer, "\n");
		for (child = node->children; child; child = child->next)
			xml_node_output(child, writer, child_indent);
		newline = 1;
	}

	if (node->name != NULL) {
		if (newline)
			xml_writer_printf(writer, "%*.*s", indent, indent, "");
		xml_writer_printf(writer, "</%s>\n", node->name);
	}
}

const char *
xml_escape_entities(const char *cdata, char **temp)
{
	static const char *escmap[256] = {
		['<'] = "&lt;",
		['>'] = "&gt;",
		['&'] = "&amp;",
	};
	const unsigned char *pos;
	unsigned int expand = 0, idx;
	char *copy = NULL;

	if (!cdata)
		return NULL;

	for (pos = (const unsigned char *)cdata; *pos; ++pos) {
		const char *replace;

		idx = *pos;
		if ((replace = escmap[idx]) != NULL)
			expand += strlen(replace);
	}

	if (expand == 0)
		return cdata;

	copy = *temp = malloc(expand + strlen(cdata) + 1);
	for (pos = (const unsigned char *)cdata; *pos; ++pos) {
		const char *replace;

		idx = *pos;
		if ((replace = escmap[idx]) != NULL) {
			strcpy(copy, replace);
			copy += strlen(copy);
		} else {
			*copy++ = *pos;
		}
	}
	*copy = '\0';

	return *temp;
}

const char *
xml_escape_quote(const char *string)
{
	return string;
}

/*
 * xml_writer object
 */
int
xml_writer_open(xml_writer_t *writer, const char *filename)
{
	memset(writer, 0, sizeof(*writer));
	writer->file = fopen(filename, "w");
	if (!writer->file) {
		fprintf(stderr, "xml_writer: cannot open %s for writing: %m", filename);
		return -1;
	}

	return 0;
}

int
xml_writer_init_file(xml_writer_t *writer, FILE *file)
{
	memset(writer, 0, sizeof(*writer));
	writer->file = file;
	writer->noclose = 1;
	return 0;
}

int
xml_writer_close(xml_writer_t *writer)
{
	int rv = 0;

	if (writer->file && ferror(writer->file))
		rv = -1;
	if (writer->file && !writer->noclose) {
		fclose(writer->file);
		writer->file = NULL;
	}
	return rv;
}

int
xml_writer_destroy(xml_writer_t *writer)
{
	return xml_writer_close(writer);
}

void
xml_writer_printf(xml_writer_t *writer, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	vfprintf(writer->file, fmt, ap);
	va_end(ap);
}
