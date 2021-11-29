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
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 *
 * Logging functions; internal use only
 */

#ifndef SUSELOG_H
#define SUSELOG_H

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
	SUSELOG_STATUS_RUNNING,
	SUSELOG_STATUS_SUCCESS,
	SUSELOG_STATUS_FAILURE,
	SUSELOG_STATUS_ERROR,
	SUSELOG_STATUS_SKIPPED,

	__SUSELOG_STATUS_MAX
} suselog_status_t;

typedef enum {
	SUSELOG_MSG_INFO,
	SUSELOG_MSG_WARNING,
	SUSELOG_MSG_FAILURE,
	SUSELOG_MSG_ERROR,

	SUSELOG_MSG_STDOUT,
	SUSELOG_MSG_STDERR,
} suselog_severity_t;

typedef struct suselog_test suselog_test_t;
typedef struct suselog_info suselog_info_t;
typedef struct suselog_common suselog_common_t;
typedef struct suselog_autoname	suselog_autoname_t;
typedef struct suselog_group suselog_group_t;
typedef struct suselog_journal suselog_journal_t;
typedef const struct suselog_writer suselog_writer_t;

typedef enum {
	SUSELOG_LEVEL_GROUP,
	SUSELOG_LEVEL_TEST,
} suselog_level_t;

typedef struct suselog_stats	suselog_stats_t;
struct suselog_stats {
	unsigned int		num_tests;
	unsigned int		num_succeeded;
	unsigned int		num_failed;
	unsigned int		num_errors;
	unsigned int		num_warnings;
	unsigned int		num_disabled;
	unsigned int		num_skipped;
};

extern suselog_group_t *suselog_current_group(suselog_journal_t *);
extern suselog_test_t *	suselog_current_test(suselog_journal_t *);
extern suselog_journal_t *suselog_journal_new(const char *, suselog_writer_t *);
extern void		suselog_journal_set_auto_group_name(suselog_journal_t *, const char *name);
extern void		suselog_journal_set_hostname(suselog_journal_t *, const char *name);
extern void		suselog_journal_set_pathname(suselog_journal_t *, const char *name);
extern void		suselog_journal_set_max_name_level(suselog_journal_t *, suselog_level_t);
extern void		suselog_journal_set_systemout_level(suselog_journal_t *, suselog_level_t);
extern void		suselog_journal_set_color(suselog_journal_t *, int);
extern const suselog_stats_t *suselog_journal_get_stats(const suselog_journal_t *);
extern void		suselog_journal_write(suselog_journal_t *);
extern int		suselog_journal_merge(suselog_journal_t *, const char *);
extern void		suselog_journal_free(suselog_journal_t *);
extern suselog_group_t *suselog_group_begin(suselog_journal_t *, const char *name, const char *description);
extern const char *	suselog_group_name(const suselog_group_t *);
extern const char *	suselog_group_description(const suselog_group_t *);
extern const char *	suselog_group_fullname(const suselog_group_t *);
extern void		suselog_group_finish(suselog_journal_t *);
extern suselog_test_t *	suselog_test_begin(suselog_journal_t *, const char *name, const char *description);
extern const char *	suselog_test_name(const suselog_test_t *);
extern const char *	suselog_test_description(const suselog_test_t *);
extern const char *	suselog_test_fullname(const suselog_test_t *);
extern const char *	suselog_test_get_message(const suselog_test_t *, suselog_severity_t);
extern suselog_status_t	suselog_test_get_status(const suselog_test_t *);
extern void		suselog_test_finish(suselog_journal_t *, suselog_status_t);

extern void		suselog_success(suselog_journal_t *);
extern void		suselog_success_msg(suselog_journal_t *, const char *fmt, ...);
extern void		suselog_skipped(suselog_journal_t *);
extern void		suselog_warning(suselog_journal_t *, const char *fmt, ...);
extern void		suselog_failure(suselog_journal_t *, const char *, ...);
extern void		suselog_fatal(suselog_journal_t *, const char *, ...);
extern void		suselog_error(suselog_journal_t *, const char *, ...);
extern void		suselog_info(suselog_journal_t *, const char *, ...);
extern void		suselog_record_stdout(suselog_journal_t *journal, const char *data, size_t len);
extern void		suselog_record_stderr(suselog_journal_t *journal, const char *data, size_t len);
extern void		suselog_record_buffer(suselog_journal_t *journal, const char *data, size_t len);

extern suselog_writer_t *suselog_writer_normal(void);

extern void		suselog_test_log_extra(suselog_test_t *, suselog_severity_t, const char *, ...);

#ifdef __cplusplus
}
#endif

#endif /* SUSELOG_H */
