/*
 * Tests for the suselog library - junit xml output
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
	suselog_group_t *group;

	journal = suselog_journal_new("subtest", suselog_writer_normal());
	suselog_journal_set_pathname(journal, "other.xml");
	group = suselog_group_begin(journal, NULL, "One group");
	suselog_test_begin(journal, NULL, "one test");
	suselog_journal_write(journal);
	suselog_journal_free(journal);

	journal = suselog_journal_new("mytest", suselog_writer_normal());
	suselog_journal_set_pathname(journal, "test-report.xml");

	group = suselog_group_begin(journal, NULL, "This is a test group");
	suselog_test_begin(journal, "testfoo", "testing the foo thing");
	suselog_success(journal);

	suselog_test_begin(journal, "testbar", "testing the bar thing");
	suselog_success(journal);

	suselog_test_begin(journal, "testbaz", "testing the baz thing");
	suselog_failure(journal, "baz crapped out");

	suselog_journal_merge(journal, "other.xml");

	group = suselog_group_begin(journal, NULL, "This is another test group");
	suselog_test_begin(journal, "frobnication", "frobnication is tricky");
	suselog_error(journal, "argh!");

	suselog_journal_write(journal);
	suselog_journal_free(journal);

	/* make the compiler believe we did something with the group handle */
	(void) group;

	return 0;
}

