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

#endif /* SUSETEST_CONFIG_H */
