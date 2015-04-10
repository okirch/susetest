/*
 * Test logging facilities for SUSE test automation
 *
 * Copyright (C) 2011-2014, Olaf Kirch <okir@suse.de>
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
 *
 * Internal declarations
 */

#ifndef SUSELOG_P_H
#define SUSELOG_P_H

#include <stdbool.h>
#include "suselog.h"

#define LIST_HEAD(type) \
	struct { type *head; type **tail; }
#define LIST_ITEM(type) \
	struct { type *next; }

#define LIST_INIT(__list__) \
	(__list__)->tail = &(__list__)->head
#define LIST_APPEND(__list__, item) \
	do { \
		typeof((__list__)->head) __item__ = item; \
		*((__list__)->tail) = __item__; (__list__)->tail = &__item__->next; \
	} while (0)
#define LIST_DROP(__list__, __dtor__) \
	do { \
		typeof((__list__)->head) __item__; \
		while ((__item__ = (__list__)->head) != NULL) { \
			if (__item__ == NULL) \
				break; \
			(__list__)->head = __item__->next; \
			__dtor__(__item__); \
		} \
		(__list__)->tail = &(__list__)->head; \
	} while (0)



struct suselog_info {
	suselog_info_t *	next;
	suselog_severity_t	severity;
	char *			message;
};

struct suselog_common {
	char *			name;
	char *			description;
	struct timeval		timestamp;
	double			duration;
};

/*
 * If a caller passes a group name name of NULL to suselog_group_begin(),
 * or a test name of NULL to suselog_test_begin(), we generate a unique
 * name consisting of autoname.base followed by a autoname.index++
 */
struct suselog_autoname {
	char *			base;
	unsigned int		index;
};

typedef struct suselog_stats	suselog_stats_t;
struct suselog_stats {
	unsigned int		num_tests;
	unsigned int		num_succeeded;
	unsigned int		num_failed;
	unsigned int		num_errors;
	unsigned int		num_warnings;
	unsigned int		num_disabled;
};

struct suselog_test {
	suselog_test_t *	next;
	suselog_group_t *	parent;

	suselog_common_t	common;
	suselog_status_t	status;

	LIST_HEAD(suselog_info_t) extra_info;
};

struct suselog_group {
	suselog_group_t *	next;
	suselog_journal_t *	parent;

	suselog_common_t	common;
	suselog_autoname_t	autoname;
	suselog_stats_t		stats;
	char *			hostname;
	unsigned int		id;

	LIST_HEAD(suselog_test_t) tests;
};

struct suselog_journal  {
	suselog_common_t	common;
	suselog_autoname_t	autoname;
	suselog_stats_t		stats;
	char *			pathname;
	char *			hostname;
	suselog_writer_t *	writer;

	suselog_level_t		max_name_level;
	suselog_level_t		systemout_level;
	bool			use_colors;

	struct {
	  suselog_group_t *	group;
	  suselog_test_t *	test;
	} current;

	unsigned int		num_groups;
	LIST_HEAD(suselog_group_t) groups;
};

struct suselog_writer {
	const char *		name;

	void			(*begin_testsuite)(const suselog_journal_t *);
	void			(*end_testsuite)(const suselog_journal_t *);

	void			(*begin_group)(const suselog_group_t *);
	void			(*end_group)(const suselog_group_t *);

	void			(*begin_test)(const suselog_test_t *);
	void			(*end_test)(const suselog_test_t *);

	void			(*message)(const suselog_test_t *, suselog_severity_t, const char *);
};


#endif /* SUSELOG_P_H */
