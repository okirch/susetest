/*
 * Tests for the suselog library.
 *
 * Copyright (C) 2014, Olaf Kirch <okir@suse.de>
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
 */
#include <stdlib.h>
#include <string.h>
#include "suselog.h"

int
main(int argc, char **argv)
{
	suselog_journal_t *journal;
	suselog_group_t *group1, *group2;
	suselog_test_t *test1, *test2;
	const char *msg;

	journal = suselog_journal_new("mytest", suselog_writer_normal());

	group1 = suselog_group_begin(journal, NULL, NULL);

	test1 = suselog_test_begin(journal, NULL, "verify test name");
	if (!strcmp(suselog_test_fullname(test1), "mytest.group0.test0"))
		suselog_success(journal);
	else
		suselog_failure(journal, "unexpected test name %s", suselog_test_fullname(test1));

	test2 = suselog_test_begin(journal, NULL, "verify test autoname uniqueness");
	if (strcmp(suselog_test_name(test1), suselog_test_name(test2)))
		suselog_success(journal);
	else
		suselog_failure(journal, "automatically assigned test names not unique (%s)", suselog_test_name(test1));

	test2 = suselog_test_begin(journal, NULL, "verify current_test()");
	if (test2 == suselog_current_test(journal))
		suselog_success(journal);
	else
		suselog_failure(journal, "mismatch in test returned by current_test()");

	test1 = suselog_test_begin(journal, "mytest", "verify test naming");
	if (!strcmp(suselog_test_name(test1), "mytest"))
		suselog_success(journal);
	else
		suselog_failure(journal, "unexpected test name %s", suselog_test_name(test1));

	test1 = suselog_test_begin(journal, NULL, "verify test description");
	if (!strcmp(suselog_test_description(test1), "verify test description"))
		suselog_success(journal);
	else
		suselog_failure(journal, "unexpected test description \"%s\"", suselog_test_description(test1));

	test1 = suselog_test_begin(journal, NULL, "verify info messages");
	suselog_info(journal, "info message %u", 42);
	msg = suselog_test_get_message(test1, SUSELOG_MSG_INFO);
	if (msg == NULL || strcmp(msg, "info message 42"))
		suselog_failure(journal, "retrieved wrong info message %s", msg);
	else
		suselog_success(journal);

	test1 = suselog_test_begin(journal, NULL, "verify warning messages");
	suselog_warning(journal, "warning message %u", 42);
	msg = suselog_test_get_message(test1, SUSELOG_MSG_WARNING);
	if (msg == NULL || strcmp(msg, "warning message 42"))
		suselog_failure(journal, "retrieved wrong warning message %s", msg);
	else
		suselog_success(journal);

	group2 = suselog_group_begin(journal, NULL, NULL);
	suselog_test_begin(journal, NULL, "verify group autoname uniqueness");
	if (strcmp(suselog_group_name(group1), suselog_group_name(group2)))
		suselog_success(journal);
	else
		suselog_failure(journal, "automatically assigned group names not unique (%s)", suselog_group_name(group1));

	group1 = suselog_group_begin(journal, "foobar", NULL);
	suselog_test_begin(journal, NULL, "verify group naming");
	if (!strcmp(suselog_group_name(group1), "foobar"))
		suselog_success(journal);
	else
		suselog_failure(journal, "unexpected group name %s", suselog_group_name(group1));

#if 0
	suselog_test_begin(journal, NULL, "verify that consecutive log calls work");
	suselog_failure(journal, "a");
	suselog_failure(journal, "b");
	/* Retrieve concatenation of all failure messages and verify it's "a\nb\n" */
#endif

	suselog_journal_free(journal);

	return 0;
}
