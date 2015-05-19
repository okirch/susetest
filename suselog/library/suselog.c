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
 * Logging functions for use by test cases written in C
 */

#include <sys/time.h>
#include <time.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>
#include <assert.h>
#include <wchar.h>
#include <wctype.h>
#include <term.h>

#include "suselog_p.h"
#include "xml.h"
#include "util.h"

static void		suselog_test_vlog_extra(suselog_test_t *, suselog_severity_t, const char *, va_list);
static void		suselog_group_free(suselog_group_t *);
static void		suselog_test_free(suselog_test_t *);
static void		suselog_info_free(suselog_info_t *);
static int		__suselog_test_running(const suselog_journal_t *journal);
static void		__suselog_test_log_extra(suselog_test_t *, suselog_severity_t, const char *);
static void		__suselog_test_log_output(suselog_test_t *, suselog_severity_t, const char *, size_t len);
static const char *	__suselog_test_fullname(const suselog_journal_t *, const suselog_group_t *, const suselog_test_t *);
static void		suselog_common_init(suselog_common_t *, const char *, const char *);
static void		suselog_common_destroy(suselog_common_t *);
static void		suselog_common_update_duration(suselog_common_t *);
static void		suselog_stats_update(suselog_stats_t *, suselog_status_t);
static void		suselog_stats_aggregate(suselog_stats_t *, const suselog_stats_t *);
static const char *	__suselog_hostname(void);

static inline void
suselog_writer_begin_testsuite(const suselog_journal_t *journal)
{
	if (journal->writer && journal->writer->begin_testsuite)
		journal->writer->begin_testsuite(journal);
}

static inline void
suselog_writer_end_testsuite(const suselog_journal_t *journal)
{
	if (journal->writer && journal->writer->end_testsuite)
		journal->writer->end_testsuite(journal);
}

static inline void
suselog_writer_begin_group(const suselog_journal_t *journal, const suselog_group_t *group)
{
	if (journal->writer && journal->writer->begin_group)
		journal->writer->begin_group(group);
}

static inline void
suselog_writer_end_group(const suselog_journal_t *journal, const suselog_group_t *group)
{
	if (journal->writer && journal->writer->end_group)
		journal->writer->end_group(group);
}

static inline void
suselog_writer_begin_test(const suselog_journal_t *journal, const suselog_test_t *test)
{
	if (journal->writer && journal->writer->begin_test)
		journal->writer->begin_test(test);
}

static inline void
suselog_writer_end_test(const suselog_journal_t *journal, const suselog_test_t *test)
{
	if (journal->writer && journal->writer->end_test)
		journal->writer->end_test(test);
}

static inline void
journal_writer_message(const suselog_journal_t *journal, const suselog_test_t *test, suselog_severity_t severity, const char *message)
{
	if (journal->writer && journal->writer->message)
		journal->writer->message(test, severity, message);
}

static void
suselog_common_init(suselog_common_t *info, const char *name, const char *description)
{ 
	__set_string(&info->name, name);
	__set_string(&info->description, description);
	gettimeofday(&info->timestamp, NULL);
	info->duration = 0;
}

static void
suselog_common_destroy(suselog_common_t *info)
{
	__drop_string(&info->name);
	__drop_string(&info->description);
}

static void
suselog_common_update_duration(suselog_common_t *info)
{
	struct timeval now, delta;

	gettimeofday(&now, NULL);
	timersub(&now, &info->timestamp, &delta);
	info->duration = delta.tv_sec + 1e-6 * delta.tv_usec;
}

static void
suselog_autoname_init(suselog_autoname_t *autoname, const char *basename)
{
	__set_string(&autoname->base, basename);
}

static const char *
suselog_autoname_next(suselog_autoname_t *autoname)
{
	static char namebuf[256];

	snprintf(namebuf, sizeof(namebuf), "%s%u", autoname->base, autoname->index++);
	return namebuf;
}

static void
suselog_autoname_destroy(suselog_autoname_t *autoname)
{
	__drop_string(&autoname->base);
}

suselog_journal_t *
suselog_journal_new(const char *name, suselog_writer_t *writer)
{
	suselog_journal_t *journal;

	journal = calloc(1, sizeof(*journal));
	suselog_common_init(&journal->common, name, NULL);
	suselog_autoname_init(&journal->autoname, "group");
	__set_string(&journal->hostname, __suselog_hostname());
	journal->writer = writer;

	/* Do not allow per-test names. This is creating more confusion in jenkins than
	 * it's worth it.
	 */
	journal->max_name_level = SUSELOG_LEVEL_GROUP;

	/* On the other hand, jenkins will grok <systemout> elements as children
	 * of a <testcase> node, which is not part of the official schema. */
	journal->systemout_level = SUSELOG_LEVEL_TEST;

	LIST_INIT(&journal->groups);


	suselog_writer_begin_testsuite(journal);
	return journal;
}

void
suselog_journal_free(suselog_journal_t *journal)
{
	suselog_group_finish(journal);
	suselog_writer_end_testsuite(journal);

	__drop_string(&journal->hostname);
	__drop_string(&journal->pathname);
	suselog_autoname_destroy(&journal->autoname);
	LIST_DROP(&journal->groups, suselog_group_free);

	free(journal);
}

void
suselog_journal_set_pathname(suselog_journal_t *journal, const char *pathname)
{
	__set_string(&journal->pathname, pathname);
}

void
suselog_journal_set_hostname(suselog_journal_t *journal, const char *hostname)
{
	__set_string(&journal->hostname, hostname);
}

void
suselog_journal_set_max_name_level(suselog_journal_t *journal, suselog_level_t level)
{
	journal->max_name_level = level;
}

void
suselog_journal_set_systemout_level(suselog_journal_t *journal, suselog_level_t level)
{
	journal->systemout_level = level;
}

void
suselog_journal_set_color(suselog_journal_t *journal, int enabled)
{
	journal->use_colors = !!enabled;
}

suselog_group_t *
suselog_current_group(suselog_journal_t *journal)
{
	return journal->current.group;
}

suselog_test_t *
suselog_current_test(suselog_journal_t *journal)
{
	return journal->current.test;
}

void
suselog_finish(suselog_journal_t *journal)
{
	suselog_group_finish(journal);
	suselog_common_update_duration(&journal->common);

	/* FIXME: we should mark the journal as "closed" and prevent further updates */
}

void
__suselog_vlogmsg(suselog_journal_t *journal, suselog_severity_t severity, const char *fmt, va_list ap)
{
	suselog_test_t *test;
	char msgbuf[1024];

	vsnprintf(msgbuf, sizeof(msgbuf), fmt, ap);

	if ((test = suselog_current_test(journal)) != NULL) {
		journal_writer_message(journal, test, severity, msgbuf);
		__suselog_test_log_extra(test, severity, msgbuf);
	}
}

void
suselog_logmsg(suselog_journal_t *journal, suselog_severity_t severity, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, severity, fmt, ap);
	va_end(ap);
}

void
suselog_success(suselog_journal_t *journal)
{
	suselog_test_finish(journal, SUSELOG_STATUS_SUCCESS);
}

void
suselog_success_msg(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_INFO, fmt, ap);
	va_end(ap);

	suselog_test_finish(journal, SUSELOG_STATUS_SUCCESS);
}

void
suselog_info(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_INFO, fmt, ap);
	va_end(ap);

	/* An info message does not end the current test */
}

void
suselog_warning(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_WARNING, fmt, ap);
	va_end(ap);

	/* A warning does not end the current test */
}

void
suselog_failure(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_FAILURE, fmt, ap);
	va_end(ap);

	suselog_test_finish(journal, SUSELOG_STATUS_FAILURE);
}

void
suselog_error(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_ERROR, fmt, ap);
	va_end(ap);

	suselog_test_finish(journal, SUSELOG_STATUS_ERROR);
}

void
suselog_fatal(suselog_journal_t *journal, const char *fmt, ...)
{
	va_list ap;

	suselog_logmsg(journal, SUSELOG_MSG_ERROR, "FATAL ERROR");

	va_start(ap, fmt);
	__suselog_vlogmsg(journal, SUSELOG_MSG_ERROR, fmt, ap);
	va_end(ap);

	suselog_test_finish(journal, SUSELOG_STATUS_ERROR);

	suselog_journal_write(journal);
	exit(1);
}

void
suselog_record_stdout(suselog_journal_t *journal, const char *data, size_t len)
{
	suselog_test_t *test;

	if ((test = journal->current.test) != NULL)
		__suselog_test_log_output(test, SUSELOG_MSG_STDOUT, data, len);

	//append data to overall stdout buffer;
}

void
suselog_record_stderr(suselog_journal_t *journal, const char *data, size_t len)
{
	suselog_test_t *test;

	if ((test = journal->current.test) != NULL)
		__suselog_test_log_output(test, SUSELOG_MSG_STDERR, data, len);

	//append data to overall stderr buffer;
}

void
suselog_record_buffer(suselog_journal_t *journal, const char *data, size_t len)
{
	suselog_test_t *test;

	if ((test = journal->current.test) != NULL)
		__suselog_test_log_output(test, SUSELOG_MSG_INFO, data, len);
}

static suselog_group_t *
suselog_group_new(const char *name, const char *description)
{
	suselog_group_t *group;

	group = calloc(1, sizeof(*group));
	suselog_common_init(&group->common, name, description);
	suselog_autoname_init(&group->autoname, "test");
	__set_string(&group->hostname, __suselog_hostname());
	LIST_INIT(&group->tests);

	return group;
}

void
suselog_group_free(suselog_group_t *group)
{
	__drop_string(&group->hostname);
	suselog_common_destroy(&group->common);
	suselog_autoname_destroy(&group->autoname);
	LIST_DROP(&group->tests, suselog_test_free);

	if (group->merged)
		xml_node_free(group->merged);
}

suselog_group_t *
suselog_group_begin(suselog_journal_t *journal, const char *name, const char *description)
{
	suselog_group_t *group;
	char fullname[256];

	suselog_group_finish(journal);

	/* The name of a group should always be something like $package.$classname
	 * where $package is the name given to suselog_journal_new and
	 * $classname is used to group the entries in this group of tests.
	 */
	if (name == NULL)
		name = suselog_autoname_next(&journal->autoname);
	snprintf(fullname, sizeof(fullname), "%s.%s", journal->common.name, name);
	name = fullname;

	group = suselog_group_new(name, description);
	group->id = journal->num_groups++;
	__set_string(&group->hostname, journal->hostname);
	LIST_APPEND(&journal->groups, group);
	group->parent = journal;

	journal->current.group = group;
	journal->current.test = NULL;

	suselog_writer_begin_group(journal, group);
	return group;
}

const char *
suselog_group_name(const suselog_group_t *group)
{
	return group->common.name;
}

const char *
suselog_group_description(const suselog_group_t *group)
{
	return group->common.description;
}

const char *
suselog_group_fullname(const suselog_group_t *group)
{
	return __suselog_test_fullname(group->parent, group, NULL);
}

void
suselog_group_finish(suselog_journal_t *journal)
{
	suselog_group_t *group;

	if (__suselog_test_running(journal))
		suselog_test_finish(journal, SUSELOG_STATUS_SUCCESS);
	if ((group = journal->current.group) != NULL) {
		suselog_stats_aggregate(&journal->stats, &group->stats);
		suselog_common_update_duration(&group->common);
		suselog_writer_end_group(journal, group);
	}

	journal->current.group = NULL;
}

static suselog_test_t *
suselog_test_new(const char *name, const char *description)
{
	suselog_test_t *test;

	test = calloc(1, sizeof(*test));
	suselog_common_init(&test->common, name, description);

	LIST_INIT(&test->extra_info);
	return test;
}

void
suselog_test_free(suselog_test_t *test)
{
	suselog_common_destroy(&test->common);
	LIST_DROP(&test->extra_info, suselog_info_free);
}

suselog_test_t *
suselog_test_begin(suselog_journal_t *journal, const char *name, const char *description)
{
	suselog_group_t *group;
	suselog_test_t *test;
	char longname[256];

	if ((group = journal->current.group) == NULL)
		group = suselog_group_begin(journal, NULL, NULL);

	if ((test = journal->current.test) != NULL
	 && test->status == SUSELOG_STATUS_RUNNING)
		suselog_test_finish(journal, SUSELOG_STATUS_SUCCESS);

	/* The name defaults to the group name.
	 * This is what ends up in the "classname" attribute, which jenkins uses
	 * to group test cases together
	 */
	if (name == NULL || journal->max_name_level < SUSELOG_LEVEL_TEST) {
		name = group->common.name;
	} else {
		snprintf(longname, sizeof(longname), "%s.%s", group->common.name, name);
		name = longname;
	}

	test = suselog_test_new(name, description);
	LIST_APPEND(&group->tests, test);
	test->parent = group;

	journal->current.test = test;
	group->stats.num_tests++;

	suselog_writer_begin_test(journal, test);
	return test;
}

const char *
suselog_test_name(const suselog_test_t *test)
{
	return test->common.name;
}

const char *
suselog_test_description(const suselog_test_t *test)
{
	return test->common.description;
}

const char *
suselog_test_fullname(const suselog_test_t *test)
{
	const suselog_journal_t *journal = NULL;
	const suselog_group_t *group = NULL;

	if ((group = test->parent) != NULL)
		journal = group->parent;
	return __suselog_test_fullname(journal, group, test);
}

const char *
suselog_test_get_message(const suselog_test_t *test, suselog_severity_t severity)
{
	suselog_info_t *info;

	for (info = test->extra_info.head; info; info = info->next) {
		if (info->severity == severity)
			return info->message;
	}
	return NULL;
}

int
__suselog_test_running(const suselog_journal_t *journal)
{
	suselog_test_t *test;

	if ((test = journal->current.test) == NULL)
		return 0;

	return test->status == SUSELOG_STATUS_RUNNING;
}

static const char *
__suselog_test_fullname(const suselog_journal_t *journal, const suselog_group_t *group, const suselog_test_t *test)
{
	static char namebuf[256 + 1];
	int maxlen = sizeof(namebuf) - 1;
	int len = 0;

	if (journal) {
		strncpy(namebuf, journal->common.name? : "<nil>", maxlen - len);
		len = strlen(namebuf);
	}
	if (group) {
		if (len && len < maxlen)
			namebuf[len++] = '.';
		strncpy(namebuf + len, group->common.name? : "<nil>", maxlen - len);
		len = strlen(namebuf);
	}
	if (test) {
		if (len && len < maxlen)
			namebuf[len++] = '.';
		strncpy(namebuf + len, test->common.name? : "<nil>", maxlen - len);
		len = strlen(namebuf);
	}

	return namebuf;
}

void
suselog_test_finish(suselog_journal_t *journal, suselog_status_t status)
{
	suselog_test_t *test;

	if ((test = journal->current.test) != NULL) {
		if (test->status != SUSELOG_STATUS_RUNNING
		 && test->status != status) {
			suselog_warning(journal, "conflicting test stati - %u vs %u",
					test->status, status);
		} else {
			suselog_group_t *group = suselog_current_group(journal);

			suselog_common_update_duration(&test->common);

			if (test->status == SUSELOG_STATUS_RUNNING)
				suselog_stats_update(&group->stats, status);
			test->status = status;

			/* Write to stdout */
			suselog_writer_end_test(journal, test);
		}
	}
}

static void
suselog_stats_update(suselog_stats_t *stats, suselog_status_t status)
{
	switch (status) {
	case SUSELOG_STATUS_SUCCESS:
		stats->num_succeeded++;
		break;

	case SUSELOG_STATUS_FAILURE:
		stats->num_failed++;
		break;

	case SUSELOG_STATUS_ERROR:
		stats->num_errors++;
		break;

	default: ;
	}
}

static void
suselog_stats_aggregate(suselog_stats_t *agg, const suselog_stats_t *sub)
{
	agg->num_tests += sub->num_tests;
	agg->num_succeeded += sub->num_succeeded;
	agg->num_failed += sub->num_failed;
	agg->num_errors += sub->num_errors;
	agg->num_warnings += sub->num_warnings;
	agg->num_disabled += sub->num_disabled;
}

/*
 * Write out journal as a JUnit xml file
 * Shall we drag in a full fledged XML library just for a little bit of formatting?
 */
static xml_node_t *	__suselog_junit_journal(suselog_journal_t *);
static xml_node_t *	__suselog_junit_group(suselog_group_t *, xml_node_t *);
static xml_node_t *	__suselog_junit_test(suselog_test_t *, xml_node_t *);
static xml_node_t *	__suselog_junit_group_system_out(suselog_group_t *, xml_node_t *);
static xml_node_t *	__suselog_junit_test_system_out(suselog_test_t *, xml_node_t *);
static xml_node_t *	__suselog_junit_pre_string(xml_node_t *, const char *, const char *,
				const suselog_test_t *, suselog_severity_t);
static void		__suselog_junit_pre_string_append(FILE *, const suselog_test_t *);
static void		__suselog_junit_stats(xml_node_t *, const suselog_stats_t *);
static const char *	__suselog_junit_timestamp(const struct timeval *);

void
suselog_journal_write(suselog_journal_t *journal)
{
	const char *outfile;
	xml_document_t *doc;
	xml_node_t *root;
	int rv;

	doc = xml_document_new();
	root = __suselog_junit_journal(journal);
	xml_document_set_root(doc, root);

	if ((outfile = journal->pathname) == NULL) {
		outfile = "<stdout>";
		rv = xml_document_print(doc, stdout);
	} else {
		rv = xml_document_write(doc, outfile);
	}
	if (rv < 0)
		fprintf(stderr, "unable to write test document to %s: %m\n", outfile);
	else
		printf("Wrote test doc to %s\n", outfile);
	xml_document_free(doc);
}

int
suselog_journal_merge(suselog_journal_t *journal, const char *filename)
{
	suselog_group_t *group;
	xml_document_t *doc;
	xml_node_t *root, *collection;
	int found = 0;
	int rv = -1;

	if ((group = journal->current.group) == NULL)
		group = suselog_group_begin(journal, NULL, NULL);

	doc = xml_document_read(filename);
	if (doc == NULL)
		goto out;

	root = xml_document_root(doc);
	if (root == NULL) {
		fprintf(stderr, "%s: empty document\n", filename);
		goto out;
	}
	for (collection = root->children; collection; collection = collection->next) {
		if (collection == NULL || strcmp(collection->name, "testsuites")) {
			fprintf(stderr, "%s: expected root element <testsuites>\n", filename);
			goto out;
		}

		if (collection->children) {
			xml_node_t *node, *next;

			if (group->merged == NULL)
				group->merged = xml_node_new("testsuites", NULL);
			for (node = collection->children; node; node = next) {
				next = node->next;

				if (strcmp(node->name, "testsuite")) {
					fprintf(stderr, "%s: ignoring element <%s>\n",
							filename, node->name);
				} else {
					xml_node_reparent(group->merged, node);
				}
			}
		}
	}

	if (found)
		rv = 0;

out:
	if (doc)
		xml_document_free(doc);
	return rv;
}


static xml_node_t *
__suselog_junit_journal(suselog_journal_t *journal)
{
	xml_node_t *root;
	suselog_group_t *group;

	suselog_finish(journal);

	root = xml_node_new("testsuites", NULL);
	xml_node_add_attr(root, "name", journal->common.name);
	xml_node_add_attr_double(root, "time", journal->common.duration);
	__suselog_junit_stats(root, &journal->stats);

	for (group = journal->groups.head; group; group = group->next) {
		__suselog_junit_group(group, root);
	}

	return root;
}

static xml_node_t *
__suselog_junit_group(suselog_group_t *group, xml_node_t *parent)
{
	xml_node_t *node;
	suselog_test_t *test;

	/* If we have merged a junit file in this group, include the entire
	 * junit file but hide the contents of this group. */
	if (group->merged) {
		xml_node_t *node;

		while ((node = group->merged->children) != NULL)
			xml_node_reparent(parent, node);
		return NULL;
	}

	node = xml_node_new("testsuite", parent);

	xml_node_add_attr(node, "package", group->common.name);
	xml_node_add_attr(node, "name", group->common.description);
	xml_node_add_attr(node, "timestamp", __suselog_junit_timestamp(&group->common.timestamp));
	xml_node_add_attr(node, "hostname", group->hostname);
	xml_node_add_attr_double(node, "time", group->common.duration);
	xml_node_add_attr_uint(node, "id", group->id);
	__suselog_junit_stats(node, &group->stats);

	for (test = group->tests.head; test; test = test->next) {
		xml_node_t *child;

		child = __suselog_junit_test(test, node);
		if (group->parent->systemout_level == SUSELOG_LEVEL_TEST)
			__suselog_junit_test_system_out(test, child);
	}

	if (group->parent->systemout_level == SUSELOG_LEVEL_GROUP)
		__suselog_junit_group_system_out(group, node);

	return node;
}

static xml_node_t *
__suselog_junit_test(suselog_test_t *test, xml_node_t *parent)
{
	const char *status;
	xml_node_t *node;

	node = xml_node_new("testcase", parent);
	xml_node_add_attr(node, "classname", test->common.name);
	xml_node_add_attr(node, "name", test->common.description);
	/* xml_node_add_attr(node, "timestamp", __suselog_junit_timestamp(&test->common.timestamp)); */
	xml_node_add_attr_double(node, "time", test->common.duration);

	/* I'm not entirely sure on the status attribute. It's in jenkins' junit schema, but
	 * not in the one at https://windyroad.com.au/dl/Open%20Source/JUnit.xsd
	 */
	switch (test->status) {
	case SUSELOG_STATUS_SUCCESS:
		status = "success";
		break;
	case SUSELOG_STATUS_FAILURE:
		__suselog_junit_pre_string(node, "failure", "randomFailure", test, SUSELOG_MSG_FAILURE);
		status = "failure";
		break;
	case SUSELOG_STATUS_ERROR:
		__suselog_junit_pre_string(node, "error", "randomError", test, SUSELOG_MSG_ERROR);
		status = "error";
		break;
	default:
		status = NULL;
	}
	if (status)
		xml_node_add_attr(node, "status", status);

	return node;
}

struct suselog_msg_collector {
	FILE *		fp;
	char *		string;
	size_t		len;
};

static void
suselog_message_collector_init(struct suselog_msg_collector *c)
{
	c->fp = open_memstream(&c->string, &c->len);
}

static const char *
suselog_message_collector_get_string(struct suselog_msg_collector *c)
{
	if (c->fp) {
		fclose(c->fp);
		c->fp = NULL;
	}

	if (c->string == NULL || c->string[0] == '\0')
		return NULL;
	return c->string;
}

static void
suselog_message_collector_destroy(struct suselog_msg_collector *c)
{
	if (c->fp)
		fclose(c->fp);
	if (c->string)
		free(c->string);
	memset(c, 0, sizeof(*c));
}

static xml_node_t *
__suselog_junit_group_system_out(suselog_group_t *group, xml_node_t *node)
{
	struct suselog_msg_collector collector;
	const char *string;
	suselog_test_t *test;
	xml_node_t *out = NULL;

	suselog_message_collector_init(&collector);
	for (test = group->tests.head; test; test = test->next) {
		fprintf(collector.fp, "# %s (%s)\n", test->common.name, test->common.description);
		__suselog_junit_pre_string_append(collector.fp, test);
	}

	if ((string = suselog_message_collector_get_string(&collector)) != NULL) {
		out = xml_node_new("system-out", node);
		xml_cdata_new(out, string);
	}


	suselog_message_collector_destroy(&collector);
	return out;
}

static xml_node_t *
__suselog_junit_test_system_out(suselog_test_t *test, xml_node_t *node)
{
	struct suselog_msg_collector collector;
	const char *string;
	xml_node_t *out = NULL;

	suselog_message_collector_init(&collector);
	__suselog_junit_pre_string_append(collector.fp, test);

	if ((string = suselog_message_collector_get_string(&collector)) != NULL) {
		out = xml_node_new("system-out", node);
		xml_cdata_new(out, string);
	}

	return out;
}

static void
__suselog_junit_pre_string_append(FILE *fp, const suselog_test_t *test)
{
	suselog_info_t *info;

	for (info = test->extra_info.head; info; info = info->next) {
		int n;

		switch (info->severity) {
		case SUSELOG_MSG_FAILURE:
			fputs("FAIL: ", fp);
			break;

		case SUSELOG_MSG_ERROR:
			fputs("ERROR: ", fp);
			break;

		case SUSELOG_MSG_STDOUT:
			fputs("standard output:\n", fp);
			break;

		case SUSELOG_MSG_STDERR:
			fputs("standard output:\n", fp);
			break;

		default: ;
		}

		fputs(info->message, fp);

		n = strlen(info->message);
		if (n && info->message[n-1] != '\n')
			fputc('\n', fp);
	}
}

static xml_node_t *
__suselog_junit_pre_string(xml_node_t *parent, const char *name, const char *type,
				const suselog_test_t *test, suselog_severity_t severity)
{
	struct suselog_msg_collector collector;
	const char *string;
	xml_node_t *node = NULL;

	suselog_message_collector_init(&collector);
	__suselog_junit_pre_string_append(collector.fp, test);

	if ((string = suselog_message_collector_get_string(&collector)) != NULL) {
		const char *msg;

		node = xml_node_new(name, parent);
		xml_node_add_attr(node, "type", type);
		if ((msg = suselog_test_get_message(test, severity)) != NULL)
			xml_node_add_attr(node, "message", msg);
		xml_cdata_new(node, string);
	}
	return node;
}

static void
__suselog_junit_stats(xml_node_t *node, const suselog_stats_t *stats)
{
	xml_node_add_attr_uint(node, "tests", stats->num_tests);
	xml_node_add_attr_uint(node, "failures", stats->num_failed);
	xml_node_add_attr_uint(node, "disabled", stats->num_disabled);
	xml_node_add_attr_uint(node, "errors", stats->num_errors);
}

/*
 * Format the time stamp according to ISO8601_DATETIME_PATTERN
 */
static const char *
__suselog_junit_timestamp(const struct timeval *tv)
{
	static char timebuf[256];
	time_t seconds = tv->tv_sec;
	struct tm *tm;
	
	tm = localtime(&seconds);
	snprintf(timebuf, sizeof(timebuf),
			"%4u-%02u-%02uT%02u:%02u:%02u",
			tm->tm_year + 1900,
			tm->tm_mon,
			tm->tm_mday,
			tm->tm_hour,
			tm->tm_min,
			tm->tm_sec);
	return timebuf;
}

/*
 * Log messages as extra_info to the currently running test
 */
static suselog_info_t *
suselog_info_new(suselog_severity_t severity, const char *msg)
{
	suselog_info_t *extra;

	extra = calloc(1, sizeof(*extra));
	extra->severity = severity;
	extra->message = strdup(msg);
	return extra;
}

void
suselog_info_free(suselog_info_t *extra)
{
	__drop_string(&extra->message);
	free(extra);
}

void
__suselog_test_log_extra(suselog_test_t *test, suselog_severity_t severity, const char *msg)
{
	LIST_APPEND(&test->extra_info, suselog_info_new(severity, msg));
}

/*
 * Log raw stdout/stderr as extra info (this will be included in the <failure>
 * and <error> elements)
 */
struct stringbuf {
	char *		data;
	unsigned int	len, size, incr;
};

void
stringbuf_init(struct stringbuf *sb)
{
	memset(sb, 0, sizeof(*sb));
}

void
stringbuf_destroy(struct stringbuf *sb)
{
	if (sb->data)
		free(sb->data);
	memset(sb, 0, sizeof(*sb));
}

void
stringbuf_append(struct stringbuf *sb, const void *data, unsigned int len)
{
	unsigned int need = len + 1;

	if (sb->size - sb->len < need) {
		if (need < sb->incr) {
			sb->size += sb->incr;
			if (sb->incr < 65536)
				sb->incr *= 2;
		} else {
			sb->size += need;
		}
		sb->data = realloc(sb->data, sb->size);
		assert(sb->data != NULL);
	}
	memcpy(sb->data + sb->len, data, len);
	sb->len += len;
	sb->data[sb->len] = '\0';
}

void
stringbuf_puts(struct stringbuf *sb, const char *data)
{
	stringbuf_append(sb, data, strlen(data));
}

void
stringbuf_putc(struct stringbuf *sb, char cc)
{
	stringbuf_append(sb, &cc, 1);
}

static void
__escape_one_char(struct stringbuf *result, unsigned char cc)
{
	char buffer[6];

	if (cc == '\f') {
		stringbuf_puts(result, "\\f");
	} else if (cc == '\v') {
		stringbuf_puts(result, "\\v");
	} else if (cc == '\r') {
		stringbuf_puts(result, "\\r");
	} else if (cc == '\0') {
		stringbuf_puts(result, "\\0");
	} else {
		snprintf(buffer, sizeof(buffer), "\\%03o", cc);
		stringbuf_puts(result, buffer);
	}
}

static unsigned int
__escape_one_mb(struct stringbuf *result, const unsigned char *data, size_t len)
{
	mbstate_t mbs;
	wchar_t wc;
	int n;

	if (data[0] == '\0') {
		__escape_one_char(result, '\0');
		return 1;
	}

	memset(&mbs, 0, sizeof(mbs));
	n = mbrtowc(&wc, (const char *) data, len, &mbs);
	if (n == -2) {
		/* Incomplete multibyte sequence. Just escape what's left
		 * of this string. */
		unsigned int k;

		for (k = 0; k < len; ++k)
			__escape_one_char(result, data[k]);
		return len;
	} else if (n <= 0) {
		/* Invalid multibyte sequence, or something that decodes to
		 * the L'0' wchar.
		 * Just escape the next byte and see if we can resync */
		__escape_one_char(result, *data);
		return 1;
	}

	if (wc == '\f' || wc == '\v' || wc == '\r') {
		__escape_one_char(result, wc);
		return n;
	}

	if (iswprint(wc) || wc == '\n' || wc == '\t') {
		/* Append multibyte sequence as-is */
		stringbuf_append(result, data, n);
	} else {
		int k;

		for (k = 0; k < n; ++k)
			__escape_one_char(result, data[k]);
	}

	return n;
}

void
__suselog_test_log_output(suselog_test_t *test, suselog_severity_t severity, const char *data, size_t len)
{
	struct stringbuf result;

	stringbuf_init(&result);
	while (len) {
		unsigned int n;

		n = __escape_one_mb(&result, (unsigned char *) data, len);
		assert(n);

		data += n;
		len -= n;
	}

	__suselog_test_log_extra(test, severity, result.data);
	stringbuf_destroy(&result);
}

void
suselog_test_vlog_extra(suselog_test_t *test, suselog_severity_t severity, const char *fmt, va_list ap)
{
	char msgbuf[1024];

	vsnprintf(msgbuf, sizeof(msgbuf), fmt, ap);
	__suselog_test_log_extra(test, severity, msgbuf);
}

void
suselog_test_log_extra(suselog_test_t *test, suselog_severity_t severity, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	suselog_test_vlog_extra(test, severity, fmt, ap);
	va_end(ap);
}

/*
 * Helper functions
 */
const char *
__suselog_hostname(void)
{
	static char namebuf[256];

	gethostname(namebuf, sizeof(namebuf));
	return namebuf;
}

/*
 * Test logging to the application's standard error
 * Regular flavor
 */
static void
__suselog_writer_normal_end_testsuite(const suselog_journal_t *journal)
{
	fprintf(stderr,
		"\n\n"
		"Test suite finished\n"
		" %7u total tests run\n"
		" %7u tests succeeded\n"
		" %7u tests failed\n"
		" %7u test suite errors\n"
		, journal->stats.num_tests
		, journal->stats.num_succeeded
		, journal->stats.num_failed
		, journal->stats.num_errors
	       );
}

static void
__suselog_writer_normal_begin_group(const suselog_group_t *group)
{
	if (group->common.description) {
		fprintf(stderr, "=== %s ===\n", group->common.description);
	} else {
		fprintf(stderr, "=== %s ===\n", group->common.name);
	}
}

#define TI_BLACK	0
#define TI_RED		1
#define TI_GREEN	2
#define TI_BLUE		4

static int
__suselog_writer_putc(int c)
{
	return write(2, &c, 1);
}

static inline void
__suselog_writer_print_colored(const suselog_test_t *test, int color, const char *word)
{
	static bool need_setterm = true;
	static bool have_terminal = false;
	const char *setaf;

	if (test == NULL
	 || test->parent == NULL
	 || test->parent->parent == NULL
	 || !test->parent->parent->use_colors) {
		fprintf(stderr, "%s", word);
		return;
	}

	/* You wouldn't believe what strange ideas some people entertain.
	 * If you call setupterm without an err_ret pointer, and it runs into
	 * a problem (such as TERM not being set) it will silently exit.
	 */
	if (need_setterm) {
		int err_ret;

		need_setterm = false;
		if (setupterm(NULL, 1, &err_ret) >= 0)
			have_terminal = true;
	}

	if (!have_terminal || (setaf = tigetstr("setaf")) == (char *) -1 || setaf == NULL) {
		fprintf(stderr, "%s", word);
		return;
	}

	fflush(stderr);

	/* write(2, setaf, strlen(setaf)); */
	tputs(tparm(setaf, color), 1, __suselog_writer_putc);
	(void) write(2, word, strlen(word));
	tputs(tparm(setaf, TI_BLACK), 1, __suselog_writer_putc);
}

static void
__suselog_writer_normal_begin_test(const suselog_test_t *test)
{
	fprintf(stderr, "\n---------------------------------\n\n---------------------------------\n");

	__suselog_writer_print_colored(test, TI_BLUE, "TEST");
	if (test->common.description) {
		fprintf(stderr, ": %s\n", test->common.description);
	} else {
		fprintf(stderr, ": %s\n", suselog_test_fullname(test));
	}
}

static void
__suselog_writer_normal_end_test(const suselog_test_t *test)
{
	const char *msg = NULL;

	switch (test->status) {
	case SUSELOG_STATUS_SUCCESS:
		__suselog_writer_print_colored(test, TI_GREEN, "SUCCESS");
		break;

	case SUSELOG_STATUS_FAILURE:
		__suselog_writer_print_colored(test, TI_RED, "FAIL");
		msg = suselog_test_get_message(test, SUSELOG_MSG_FAILURE);
		break;

	case SUSELOG_STATUS_ERROR:
		__suselog_writer_print_colored(test, TI_RED, "ERROR");
		msg = suselog_test_get_message(test, SUSELOG_MSG_ERROR);
		break;

	case SUSELOG_STATUS_SKIPPED:
		fprintf(stderr, "SKIPPED");
		break;

	default:
		__suselog_writer_print_colored(test, TI_RED, "ERROR");
		fprintf(stderr, ": unexpected test status %d", test->status);
		break;
	}

	if (msg)
		fprintf(stderr, ": %s", msg);
	fprintf(stderr, "\n");
}

static void
__suselog_writer_normal_message(const suselog_test_t *test, suselog_severity_t severity, const char *message)
{
	switch (severity) {
	case SUSELOG_MSG_INFO:
		fprintf(stderr, "%s\n", message);
		break;
	case SUSELOG_MSG_WARNING:
		fprintf(stderr, "Warning: %s\n", message);
		break;
	case SUSELOG_MSG_FAILURE:
		fprintf(stderr, "Failing: %s\n", message);
		break;
	case SUSELOG_MSG_ERROR:
		fprintf(stderr, "Testsuite error: %s\n", message);
		break;

	default:
		fprintf(stderr, "Message of unknown severity(%u): %s\n", severity, message);
		break;

	}
}

const suselog_writer_t	__suselog_writer_normal = {
	.end_testsuite	= __suselog_writer_normal_end_testsuite,
	.begin_group	= __suselog_writer_normal_begin_group,
	.begin_test	= __suselog_writer_normal_begin_test,
	.end_test	= __suselog_writer_normal_end_test,
	.message	= __suselog_writer_normal_message,
};

suselog_writer_t *
suselog_writer_normal(void)
{
	return &__suselog_writer_normal;
}

#if 0
enum {
	TEST_BEGIN_GROUP, TEST_BEGIN, TEST_SUCCESS, TEST_FAILURE, TEST_WARNING,
};

static void
__log_test_begin_or_end(int type, const char *name, const char *extra_fmt, va_list extra_ap)
{
	if (opt_log_testbus) {
		switch (type) {
		case TEST_BEGIN_GROUP:
		case TEST_BEGIN:
			fprintf(stderr, "### TESTBEGIN %s", name);
			break;

		case TEST_SUCCESS:
			fprintf(stderr, "### TESTRESULT %s: SUCCESS", name);
			break;

		case TEST_FAILURE:
			fprintf(stderr, "### TESTRESULT %s: FAILED", name);
			break;

		case TEST_WARNING:
			fprintf(stderr, "### TESTRESULT %s: WARN", name);
			break;

		default:
			fprintf(stderr, "### INTERNALERROR");
			break;
		}

		if (extra_fmt) {
			fprintf(stderr, " (");
			vfprintf(stderr, extra_fmt, extra_ap);
			fprintf(stderr, ")");
		}
		fprintf(stderr, "\n");
	} else {
		switch (type) {
		case TEST_BEGIN_GROUP:
			fprintf(stderr, "=== ");
			if (extra_fmt)
				vfprintf(stderr, extra_fmt, extra_ap);
			fprintf(stderr, " === \n");
			break;

		case TEST_BEGIN:
			fprintf(stderr, "TEST: ");
			if (extra_fmt)
				vfprintf(stderr, extra_fmt, extra_ap);
			fprintf(stderr, "\n");
			break;

		case TEST_SUCCESS:
			/* Nothing */
			return;

		case TEST_FAILURE:
			fprintf(stderr, "FAIL: ");
			if (extra_fmt)
				vfprintf(stderr, extra_fmt, extra_ap);
			fprintf(stderr, "\n");
			break;

		case TEST_WARNING:
			fprintf(stderr, "WARN: ");
			if (extra_fmt)
				vfprintf(stderr, extra_fmt, extra_ap);
			fprintf(stderr, "\n");
			break;
		}

	}
}

static void
__log_test_finish(const char **namep)
{
	if (*namep != NULL) {
		__log_test_begin_or_end(TEST_SUCCESS, *namep, NULL, NULL);
		*namep = NULL;
	}
}

static const char *
log_name_combine(const char *prefix, const char *tag, char **save_p)
{
	char buffer[512];

	if (prefix == NULL)
		return tag;

	snprintf(buffer, sizeof(buffer), "%s.%s", prefix, tag);
	if (*save_p)
		free(*save_p);
	*save_p = strdup(buffer);
	return *save_p;
}

void
log_test_group(const char *groupname, const char *fmt, ...)
{
	static char *group_name_save = NULL;
	va_list ap;

	__log_test_finish(&test_case_name);
	__log_test_finish(&test_group_name);

	test_group_name = log_name_combine(test_root_name, groupname, &group_name_save);
	test_group_index = 0;

	va_start(ap, fmt);
	if (!opt_log_quiet) {
		__log_test_begin_or_end(TEST_BEGIN_GROUP, test_group_name, fmt, ap);
	} else {
		vsnprintf(test_group_msg, sizeof(test_group_msg), fmt, ap);
	}
	va_end(ap);
}

static void
__log_test_tagged(const char *tag, const char *fmt, va_list ap)
{
	static char *test_name_save = NULL;

	__log_test_finish(&test_case_name);

	test_case_name = log_name_combine(test_group_name? test_group_name : test_root_name, tag, &test_name_save);

	if (!opt_log_quiet) {
		__log_test_begin_or_end(TEST_BEGIN, test_case_name, fmt, ap);
	} else {
		vsnprintf(test_msg, sizeof(test_msg), fmt, ap);
	}

	test_group_index++;
	num_tests++;
}

void
log_test_tagged(const char *tag, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	__log_test_tagged(tag, fmt, ap);
	va_end(ap);
}

void
log_test(const char *fmt, ...)
{
	char tagname[32];
	va_list ap;

	va_start(ap, fmt);
	snprintf(tagname, sizeof(tagname), "testcase%u", test_group_index);
	__log_test_tagged(tagname, fmt, ap);
	va_end(ap);
}

void
log_finish(void)
{
	__log_test_finish(&test_case_name);
	__log_test_finish(&test_group_name);
}

static void
__log_msg_flush(void)
{
	if (test_group_msg[0]) {
		fprintf(stderr, "== %s ==\n", test_group_msg);
		test_group_msg[0] = '\0';
	}
	if (test_msg[0]) {
		fprintf(stderr, "TEST: %s\n", test_msg);
		test_msg[0] = '\0';
	}
}

void
log_warn(const char *fmt, ...)
{
	va_list ap;

	__log_msg_flush();

	va_start(ap, fmt);
	__log_test_begin_or_end(TEST_WARNING, test_case_name, fmt, ap);
	va_end(ap);

	num_warns++;
}

void
log_fail(const char *fmt, ...)
{
	va_list ap;

	__log_msg_flush();

	if (test_case_name) {
		va_start(ap, fmt);
		__log_test_begin_or_end(TEST_FAILURE, test_case_name, fmt, ap);
		va_end(ap);

		test_case_name = NULL;
	}

	num_fails++;
}

void
log_error(const char *fmt, ...)
{
	va_list ap;

	__log_msg_flush();

	va_start(ap, fmt);
	fprintf(stderr, "Error: ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, "\n");
	va_end(ap);
}

void
log_trace(const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	fprintf(stderr, "::: ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, "\n");
	va_end(ap);
}

void
log_fatal(const char *fmt, ...)
{
	va_list ap;

	__log_msg_flush();

	va_start(ap, fmt);
	fprintf(stderr, "FATAL ERROR: *** ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, " ***\n");
	va_end(ap);

	exit(1);
}
#endif
