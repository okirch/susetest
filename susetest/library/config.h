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

#ifndef SUSETEST_CONFIG_H
#define SUSETEST_CONFIG_H

#include "susetest.h"

typedef struct susetest_config_attr susetest_config_attr_t;

#define SUSETEST_CONFIG_SHORTLIST_MAX	2
struct susetest_config_attr {
	susetest_config_attr_t *	next;
	char *				name;

	unsigned int			nvalues;
	char **				values;
	char *				short_list[SUSETEST_CONFIG_SHORTLIST_MAX+1];
};

struct susetest_config {
	susetest_config_t *		next;

	/* The group's type (eg "node") and name (eg "client", "server") */
	char *				type;
	char *				name;

	/* Attributes */
	susetest_config_attr_t *	attrs;

	susetest_config_t *		children;
};

extern int			susetest_config_write_curly(susetest_config_t *cfg, const char *path);
extern int			susetest_config_write_xml(susetest_config_t *cfg, const char *path);
extern susetest_config_t *	susetest_config_read_curly(const char *path);
extern susetest_config_t *	susetest_config_read_xml(const char *path);

#endif /* SUSETEST_CONFIG_H */
