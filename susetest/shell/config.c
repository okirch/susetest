/*
 * susetest config command
 *
 * Copyright (C) 2015 SUSE
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
 *
 *
 * If you want to create a susetest config file from the shell, do
 * something like this:
 *
 * export TWOPENCE_CONFIG_PATH=mytest.conf
 * susetest config create user=root timeout=60
 * susetest config add-node client target=ssh:192.168.5.1 ipaddr=192.168.5.1
 * susetest config add-node server target=ssh:192.168.5.8 ipaddr=192.168.5.8
 *
 * and you're done. More subcommands are available for setting attributes
 * on a global or per-node basis independently, and for querying them.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <unistd.h>
#include <errno.h>
#include <getopt.h>
#include <ctype.h>

#include "susetest.h"

char *short_options = "f:F:g:h";
struct option long_options[] = {
  { "filename",		required_argument,	NULL, 'f' },
  { "group",		required_argument,	NULL, 'g' },
  { "use-defaults",	no_argument,		NULL, 'd' },
  { "help",		no_argument,		NULL, 'h' },
  { NULL }
};

enum {
	RESOLVE_GROUP_CREATE = 0x0001,
	RESOLVE_GROUP_IGNORE_MISSING = 0x0002,
};

/* Default the output format to curly for now */
#define SUSETEST_DEFAULT_FMT	SUSETEST_CONFIG_FMT_CURLY

static bool			arg_get_type_and_name(const char *cmd, int argc, char **argv, const char **type_ret, const char **name_ret);
static bool			arg_get_attr_name(const char *cmd, int argc, char **argv, const char **name_ret);
static bool			arg_get_type(const char *cmd, int argc, char **argv, const char **type_ret);
static void			apply_defaults(susetest_config_t *group, const susetest_config_t *cfg, const char *type);
static bool			resolve_group(const char *cmd, char *groupname, int flags, susetest_config_t **cfg_p);
static int			split_key_value(char *nameattr, char **namep, char **valuep);

static void
show_usage(void)
{
	fprintf(stderr,
		"susetest config <subcommand> [--filename <path>] args ...\n"
		"\n"
		"Subcommands:\n"
		"  create name1=value name2=\"quoted-value\" ...\n"
		"     Create a new config file, optionally setting global attributes\n"
		"  add-group [--group <group-path>] type=name [attr=value] ...\n"
		"     Create a named group (a node, a network), optionally setting node attributes\n"
		"  clear-attr [--group <group-path>] name\n"
		"     Delete an attributes\n"
		"  set-attr [--group <group-path>] name1=value name2=\"quoted-value\" ...\n"
		"     Explicitly set attributes\n"
		"  get-attr [--group <group-path>] name\n"
		"     Query an attribute. If the attribute is a list attribute,\n"
		"     only the first item will be printed\n"
		"  set-attr-list [--group <group-path>] name value1 value2 value3 ...\n"
		"     Explicitly set a list attribute, overwriting any previous values\n"
		"  append-attr-list [--group <group-path>] name value1 value2 value3 ...\n"
		"     Append values to a list attribute\n"
		"  get-attr-list [--group <group-path>] name\n"
		"     Query a list attribute. Each item is printed on a separate line.\n"
		"  get-children [--group <group-path>] type\n"
		"     Print the name of all child groups of type \"type\"\n"
		"  delete\n"
		"     Delete the config file\n"
		"  help\n"
		"     Display this help message\n"
		"\n"
		"The config file can be specified the the --filename option, or through the\n"
		"TWOPENCE_CONFIG_PATH environment variable. If neither is given, it will default\n"
		"to susetest.conf in the current working directory\n"
		"\n"
		"Typical global attributes might be the default user to run commands as,\n"
		"or a timeout value. Typical node attributes may be the node's hostname\n"
		"or its IP address.\n"
	       );
}

int
do_config(int argc, char **argv)
{
	susetest_config_t *cfg = NULL, *cfg_root = NULL;
	char *opt_pathname = NULL;
	char *opt_groupname = NULL;
	bool opt_apply_defaults = false;
	char *cmd;
	int c;

	argv++, argc--;
	if (argc <= 0) {
		show_usage();
		return 0;
	}

	cmd = argv[0];
	if (!strcmp(cmd, "help")) {
		show_usage();
		return 0;
	}

	while ((c = getopt_long(argc, argv, short_options, long_options, NULL)) != -1) {
		switch (c) {
		case 'h':
			/* show usage */
			return 0;

		case 'd':
			opt_apply_defaults = true;
			break;

		case 'f':
			opt_pathname = optarg;
			break;

		case 'g':
			opt_groupname = optarg;
			break;

		default:
			fprintf(stderr, "Unsupported option\n");
			/* show usage */
			return 1;
		}
	}

	if (opt_pathname == NULL) {
		opt_pathname = getenv("TWOPENCE_CONFIG_PATH");
		if (opt_pathname == NULL)
			opt_pathname = "susetest.conf";
	}

	if (!strcmp(cmd, "create")) {
		const char *testname = "unknown";
		int i;

		for (i = optind; i < argc; ++i) {
			if (!strncmp(argv[i], "name=", 5)) {
				testname = argv[i] + 5;
				break;
			}
		}

		cfg_root = susetest_config_new();
		cfg = susetest_config_add_child(cfg_root, "testenv", testname);

		/* config create [attr="value"] ... */
		while (optind < argc) {
			char *name, *value;

			if (!split_key_value(argv[optind++], &name, &value))
				return 1;
			if (strcmp(name, "name")) {
				susetest_config_set_attr(cfg, name, value);
			}
		}
	} else
	if (!strcmp(cmd, "delete")) {
		if (unlink(opt_pathname) < 0 && errno != ENOENT) {
			fprintf(stderr, "susetest: unable to delete config file \"%s\": %m\n", opt_pathname);
			return 1;
		}
		opt_pathname = NULL; /* don't re-write it */
	} else {
		cfg_root = susetest_config_read(opt_pathname);

		if (cfg_root == NULL) {
			fprintf(stderr, "susetest: unable to read config file \"%s\"\n", opt_pathname);
			return 1;
		}

		cfg = susetest_config_get_child(cfg_root, "testenv", NULL);
		if (cfg == NULL)
			cfg = cfg_root;

		if (!strcmp(cmd, "add-group")) {
			susetest_config_t *group = cfg, *child;
			const char *type, *name;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_CREATE, &group))
				return 1;

			/* Parse type=name */
			if (!arg_get_type_and_name(cmd, argc, argv, &type, &name))
				return 1;

			child = susetest_config_get_child(group, type, name);
			if (child == NULL)
				child = susetest_config_add_child(group, type, name);
			if (child == NULL) {
				fprintf(stderr, "susetest config: unable to add %s \"%s\"\n", type, name);
				return 1;
			}

			if (opt_apply_defaults)
				apply_defaults(child, cfg, type);

			while (optind < argc) {
				char *name, *value;

				if (!split_key_value(argv[optind++], &name, &value))
					return 1;
				susetest_config_set_attr(child, name, value);
			}
		} else
		if (!strcmp(cmd, "set-attr")) {
			susetest_config_t *group = cfg;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_CREATE, &group))
				return 1;

			while (optind < argc) {
				char *name, *value;

				if (!split_key_value(argv[optind++], &name, &value))
					return 1;
				susetest_config_set_attr(group, name, value);
			}
		} else
		if (!strcmp(cmd, "clear-attr")) {
			susetest_config_t *group = cfg;
			const char *name;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_IGNORE_MISSING, &group))
				return 0;

			if (!arg_get_attr_name(cmd, argc, argv, &name))
				return 1;

			susetest_config_set_attr(group, name, NULL);
		} else
		if (!strcmp(cmd, "set-attr-list")) {
			susetest_config_t *group = cfg;
			const char *name;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_CREATE, &group)
			 || !arg_get_attr_name(cmd, argc, argv, &name))
				return 1;

			susetest_config_set_attr_list(group, name, (const char * const *) argv + optind);
		} else
		if (!strcmp(cmd, "append-attr-list")) {
			susetest_config_t *group = cfg;
			const char *name;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_CREATE, &group)
			 || !arg_get_attr_name(cmd, argc, argv, &name))
				return 1;

			while (optind < argc) {
				susetest_config_add_attr_list(group, name, argv[optind++]);
			}
		} else
		if (!strcmp(cmd, "get-attr")) {
			susetest_config_t *group = cfg;
			const char *name, *value;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_IGNORE_MISSING, &group))
				return 0;

			if (!arg_get_attr_name(cmd, argc, argv, &name))
				return 1;

			value = susetest_config_get_attr(group, name);
			if (value)
				printf("%s\n", value);
			opt_pathname = NULL; /* No need to rewrite config file */
		} else
		if (!strcmp(cmd, "get-attr-list")) {
			susetest_config_t *group = cfg;
			const char * const *values;
			const char *name;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_IGNORE_MISSING, &group))
				return 0;
			if (!arg_get_attr_name(cmd, argc, argv, &name))
				return 1;

			values = susetest_config_get_attr_list(group, name);
			while (values && *values)
				printf("%s\n", *values++);
			opt_pathname = NULL; /* No need to rewrite config file */
		} else
		if (!strcmp(cmd, "get-children")) {
			susetest_config_t *group = cfg;
			const char *type;
			const char **names;
			int n;

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_IGNORE_MISSING, &group))
				return 0;
			if (!arg_get_type(cmd, argc, argv, &type))
				return 1;

			names = susetest_config_get_children(group, type);
			for (n = 0; names[n]; ++n)
				printf("%s\n", names[n]);
			free(names);
		} else
		if (!strcmp(cmd, "copy-group")) {
			susetest_config_t *group = cfg;
			susetest_config_t *src_group;
			char *src_file = NULL, *src_group_name;

			if (opt_groupname == NULL) {
				fprintf(stderr, "susetest config copy-group: timidly refusing to replace entire config file\n");
				fprintf(stderr, "Please use --group option to specify which node to overwrite\n");
				return 1;
			}

			if (optind < argc)
				src_file = argv[optind++];
			if (optind < argc) {
				src_group_name = argv[optind++];
			} else {
				src_group_name = strdup(opt_groupname);
			}

			if (src_file == NULL || optind != argc) {
				fprintf(stderr, "susetest config copy-group: bad number of arguments\n");
				return 1;
			}

			if (!resolve_group(cmd, opt_groupname, RESOLVE_GROUP_CREATE, &group))
				return 1;

			src_group = susetest_config_read(src_file);
			if (src_group == NULL) {
				fprintf(stderr, "susetest config %s: unable to read config file \"%s\"\n", cmd, src_file);
				return 1;
			}
			if (!resolve_group(cmd, src_group_name, RESOLVE_GROUP_IGNORE_MISSING, &src_group))
				return 0;

			susetest_config_copy(group, src_group);
		} else {
			fprintf(stderr, "susetest config: unsupported subcommand \"%s\"\n", cmd);
			return 1;
		}
	}

	if (opt_pathname && susetest_config_write(cfg_root, opt_pathname) < 0) {
		fprintf(stderr, "susetest config %s: unable to rewrite config file\n", cmd);
		return 1;
	}

	return 0;
}

static bool
arg_get_type_and_name(const char *cmd, int argc, char **argv, const char **type_ret, const char **name_ret)
{
	if (optind >= argc) {
		fprintf(stderr, "susetest config %s: missing type=name argument\n", cmd);
		show_usage();
		return false;
	}

	if (!split_key_value(argv[optind++], (char **) type_ret, (char **) name_ret)) {
		fprintf(stderr, "susetest config %s: bad argument, should be type=name\n", cmd);
		return false;
	}
	return true;
}

static bool
arg_get_attr_name(const char *cmd, int argc, char **argv, const char **name_ret)
{
	if (optind >= argc) {
		fprintf(stderr, "susetest config %s: missing attribute name\n", cmd);
		show_usage();
		*name_ret = NULL;
		return false;
	}
	*name_ret = argv[optind++];
	return true;
}

static bool
arg_get_type(const char *cmd, int argc, char **argv, const char **type_ret)
{
	if (optind >= argc) {
		fprintf(stderr, "susetest config %s: missing type argument\n", cmd);
		show_usage();
		return false;
	}
	*type_ret = argv[optind++];
	return true;
}

/*
 * When creating a new group (eg a network or a node), apply
 * default settings from the corresponding "defaults" entry:
 *  defaults "network" {
 *	dhcp "yes";
 *  }
 */
static void
apply_defaults(susetest_config_t *group, const susetest_config_t *cfg, const char *type)
{
	susetest_config_t *defaults;
	const char **attr_names;

	defaults = susetest_config_get_child(cfg, "defaults", type);
	if (defaults == NULL)
		return;

	attr_names = susetest_config_get_attr_names(defaults);
	if (attr_names) {
		unsigned int i;

		for (i = 0; attr_names[i]; ++i) {
			const char *name = attr_names[i];
			const char * const *values;

			values = susetest_config_get_attr_list(defaults, name);
			if (!values)
				continue;

			susetest_config_set_attr_list(group, name, values);
		}
		free(attr_names);
	}
}

/*
 * Resolve a group path, such as
 *  /node=client/interface=eth0
 */
static bool
resolve_group(const char *cmd, char *groupname, int flags, susetest_config_t **cfg_p)
{
	char *next = NULL;

	if (groupname == NULL)
		return true;

	for (; groupname != NULL; groupname = next) {
		susetest_config_t *child;
		char *type, *name;

		while (*groupname == '/')
			++groupname;

		if ((next = strchr(groupname, '/')) != NULL)
			*next++ = '\0';
		if (*groupname == '\0')
			break;

		if (!split_key_value(groupname, &type, &name)) {
			fprintf(stderr, "susetest config %s --group: bad argument, should be type=name\n", cmd);
			return false;
		}
		child = susetest_config_get_child(*cfg_p, type, name);
		if (child == NULL) {
			if (flags & RESOLVE_GROUP_CREATE) {
				child = susetest_config_add_child(*cfg_p, type, name);
			} else {
				if (!(flags & RESOLVE_GROUP_IGNORE_MISSING))
					fprintf(stderr, "susetest config %s: unable to look up subgroup %s=\"%s\"\n", cmd, type, name);
				return false;
			}
		}
		*cfg_p = child;
	}

	return true;
}

static int
__split_attr(char *s, char **namep, char **valuep)
{
	*namep = s;

	if (!isalpha(*s))
		return 0;
	while (isalnum(*s) || *s == '_' || *s == '-')
		++s;
	if (*s != '=')
		return 0;
	*s++ = '\0';
	if (*s == '"') {
		int len;

		len = strlen(s);
		if (len < 2 || s[len-1] != '"')
			return 0;
		s[len-1] = '"';
		*valuep = s + 1;
	} else {
		*valuep = s;
	}
	return 1;
}

int
split_key_value(char *nameattr, char **namep, char **valuep)
{
	char *s = strdup(nameattr);

	if (!__split_attr(nameattr, namep, valuep)) {
		fprintf(stderr, "Cannot parse attribute assignment %s\n", s);
		free(s);
		return 0;
	}

	if (**valuep == '\0')
		*valuep = NULL;
	free(s);
	return 1;
}
