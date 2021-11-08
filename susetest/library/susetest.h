/*
 * Higher level functions for running tests
 *
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

#ifndef SUSETEST_H
#define SUSETEST_H

#include <stdbool.h>

/*
 * Handling susetest config information
 */
typedef struct susetest_config susetest_config_t;

extern susetest_config_t *	susetest_config_new(void);
extern void			susetest_config_free(susetest_config_t *);
extern void			susetest_config_copy(susetest_config_t *dst, const susetest_config_t *src);
extern int			susetest_config_write(susetest_config_t *cfg, const char *path);
extern susetest_config_t *	susetest_config_read(const char *path);
extern const char *		susetest_config_name(const susetest_config_t *cfg);
extern const char *		susetest_config_type(const susetest_config_t *cfg);
extern susetest_config_t *	susetest_config_get_child(const susetest_config_t *cfg, const char *type, const char *name);
extern susetest_config_t *	susetest_config_add_child(susetest_config_t *cfg, const char *type, const char *name);
extern unsigned int		susetest_config_drop_child(susetest_config_t *cfg, const susetest_config_t *child);
extern const char **		susetest_config_get_children(const susetest_config_t *, const char *type);
extern const char **		susetest_config_get_attr_names(const susetest_config_t *);
extern void			susetest_config_set_attr(susetest_config_t *cfg, const char *name, const char *value);
extern void			susetest_config_set_attr_list(susetest_config_t *cfg, const char *name, const char * const *value);
extern void			susetest_config_add_attr_list(susetest_config_t *cfg, const char *name, const char *value);
extern const char *		susetest_config_get_attr(susetest_config_t *cfg, const char *name);
extern const char * const *	susetest_config_get_attr_list(susetest_config_t *cfg, const char *name);

extern int			susetest_config_format_from_string(const char *s);
extern const char *		susetest_config_format_to_string(int fmt);

#endif /* SUSETEST_H */
