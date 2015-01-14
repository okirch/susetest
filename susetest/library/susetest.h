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

/*
 * Handling susetest config information
 */
typedef struct susetest_config susetest_config_t;
typedef struct susetest_target_config susetest_target_config_t;

extern susetest_config_t *		susetest_config_new(void);
extern void				susetest_config_free(susetest_config_t *);
extern int				susetest_config_write(susetest_config_t *cfg, const char *path);
extern susetest_config_t *		susetest_config_read(const char *path);
extern susetest_target_config_t *	susetest_config_get_target(susetest_config_t *cfg, const char *name);
extern susetest_target_config_t *	susetest_config_add_target(susetest_config_t *cfg, const char *name, const char *spec);
extern void				susetest_config_set_attr(susetest_config_t *cfg, const char *name, const char *value);
extern const char *			susetest_config_get_attr(susetest_config_t *cfg, const char *name);
extern const char *			susetest_target_config_get_spec(susetest_target_config_t *cfg);
extern void				susetest_target_config_set_attr(susetest_target_config_t *tgt, const char *name, const char *value);
extern const char *			susetest_target_config_get_attr(susetest_target_config_t *tgt, const char *name);
extern const char **			susetest_target_config_attr_names(const susetest_target_config_t *);


#endif /* SUSETEST_H */
