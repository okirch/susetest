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
#include <unistd.h>
#include <errno.h>
#include <getopt.h>
#include <ctype.h>

#include "susetest.h"

char *short_options = "f:h";
struct option long_options[] = {
  { "filename",	required_argument, NULL, 'f' },
  { "help",	no_argument, NULL, 'h' },
  { NULL }
};

static const char *		arg_get_nodename(const char *cmd, int argc, char **argv);
static susetest_node_config_t *	arg_get_node(susetest_config_t *, const char *cmd, int argc, char **argv);
static int			set_node_attrs(susetest_node_config_t *node, int argc, char **argv);
static void			get_node_attrs(susetest_node_config_t *node, int argc, char **argv);
static int			split_attr(char *nameattr, char **namep, char **valuep);

static void
show_usage(void)
{
	fprintf(stderr,
		"susetest config <subcommand> [--filename <path>] args ...\n"
		"\n"
		"Subcommands:\n"
		"  create name1=value name2=\"quoted-value\" ...\n"
		"     Create a new config file, optionally setting global attributes\n"
		"  set-attr name1=value name2=\"quoted-value\" ...\n"
		"     Explicitly set global attributes\n"
		"  get-attr name\n"
		"     Query a global attribute\n"
		"  add-node name [attr=value] ...\n"
		"     Add a named node, optionally setting node attributes\n"
		"  node-set-attr node-name name1=value name2=\"quoted-value\" ...\n"
		"     Explicitly set one ore more node attributes\n"
		"  node-get-attr node-name name\n"
		"     Query a node attribute\n"
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
	susetest_config_t *cfg = NULL;
	char *opt_pathname = NULL;
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

		case 'f':
			opt_pathname = optarg;
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
		/* config create [attr="value"] ... */
		cfg = susetest_config_new();

		while (optind < argc) {
			char *name, *value;

			if (!split_attr(argv[optind++], &name, &value))
				return 1;
			susetest_config_set_attr(cfg, name, value);
		}
	} else
	if (!strcmp(cmd, "delete")) {
		if (unlink(opt_pathname) < 0 && errno != ENOENT) {
			fprintf(stderr, "susetest: unable to delete config file \"%s\": %m\n", opt_pathname);
			return 1;
		}
		opt_pathname = NULL; /* don't re-write it */
	} else {
		cfg = susetest_config_read(opt_pathname);
		if (cfg == NULL) {
			fprintf(stderr, "susetest: unable to read config file \"%s\"\n", opt_pathname);
			return 1;
		}

		if (!strcmp(cmd, "add-node")) {
			susetest_node_config_t *node;
			const char *name;

			if (!(name = arg_get_nodename(cmd, argc, argv)))
				return 1;

			node = susetest_config_add_node(cfg, name, NULL);
			if (node == NULL) {
				fprintf(stderr, "susetest config: unable to add node \"%s\"\n", name);
				return 1;
			}

			if (!set_node_attrs(node, argc, argv))
				return 1;
		} else
		if (!strcmp(cmd, "set-attr")) {
			while (optind < argc) {
				char *name, *value;

				if (!split_attr(argv[optind++], &name, &value))
					return 1;
				susetest_config_set_attr(cfg, name, value);
			}
		} else
		if (!strcmp(cmd, "get-attr")) {
			const char *value;

			if (optind + 1 != argc) {
				fprintf(stderr, "susetest config get-attr: bad number of arguments\n");
				return 1;
			}

			value = susetest_config_get_attr(cfg, argv[optind]);
			if (value)
				printf("%s\n", value);
			opt_pathname = NULL; /* No need to rewrite config file */
		} else
		if (!strcmp(cmd, "node-set-attr")) {
			susetest_node_config_t *node;

			if (!(node = arg_get_node(cfg, cmd, argc, argv)))
				return 1;

			if (!set_node_attrs(node, argc, argv))
				return 1;
		} else
		if (!strcmp(cmd, "node-get-attr")) {
			susetest_node_config_t *node;

			if (!(node = arg_get_node(cfg, cmd, argc, argv)))
				return 1;

			if (optind + 1 != argc) {
				fprintf(stderr, "susetest config %s: bad number of arguments\n", cmd);
				return 1;
			}
			get_node_attrs(node, argc, argv);

			/* No need to rewrite config file */
			opt_pathname = NULL;
		} else
		if (!strcmp(cmd, "node-names")) {
			const char **names;
			unsigned int n;

			if (optind != argc) {
				fprintf(stderr, "susetest config %s: bad number of arguments\n", cmd);
				return 1;
			}

			names = susetest_config_get_nodes(cfg);
			if (names == NULL) {
				fprintf(stderr, "susetest config %s: cannot get node names\n", cmd);
				return 1;
			}

			for (n = 0; names[n]; ++n)
				printf("%s\n", names[n]);
			free(names);

			/* No need to rewrite config file */
			opt_pathname = NULL;
		} else {
			fprintf(stderr, "susetest config: unsupported subcommand \"%s\"\n", cmd);
			return 1;
		}
	}

	if (opt_pathname && susetest_config_write(cfg, opt_pathname) < 0) {
		fprintf(stderr, "susetest config %s: unable to rewrite config file\n", cmd);
		return 1;
	}

	return 0;
}

static const char *
arg_get_nodename(const char *cmd, int argc, char **argv)
{
	if (optind >= argc) {
		fprintf(stderr, "susetest config %s: missing node name\n", cmd);
		show_usage();
		return NULL;
	}

	return argv[optind++];
}

static susetest_node_config_t *
arg_get_node(susetest_config_t *cfg, const char *cmd, int argc, char **argv)
{
	susetest_node_config_t *node;
	const char *nodename;

	if (!(nodename = arg_get_nodename(cmd, argc, argv)))
		return NULL;

	node = susetest_config_get_node(cfg, nodename);
	if (node == NULL) {
		fprintf(stderr, "susetest config %s: no node named \"%s\"\n", cmd, nodename);
		return NULL;
	}

	return node;
}

static int
set_node_attrs(susetest_node_config_t *node, int argc, char **argv)
{
	while (optind < argc) {
		char *name, *value;

		if (!split_attr(argv[optind++], &name, &value))
			return 0;
		if (!strcmp(name, "target"))
			susetest_node_config_set_target(node, value);
		else
			susetest_node_config_set_attr(node, name, value);
	}
	return 1;
}

static void
get_node_attrs(susetest_node_config_t *node, int argc, char **argv)
{
	const char *value;

	while (optind < argc) {
		const char *attrname = argv[optind++];

		if (!strcmp(attrname, "target"))
			value = susetest_node_config_get_target(node);
		else
			value = susetest_node_config_get_attr(node, attrname);
		if (value)
			printf("%s\n", value);
	}
}

static int
__split_attr(char *s, char **namep, char **valuep)
{
	*namep = s;

	if (!isalpha(*s))
		return 0;
	while (isalnum(*s) || *s == '_')
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
split_attr(char *nameattr, char **namep, char **valuep)
{
	char *s = strdup(nameattr);

	if (!__split_attr(nameattr, namep, valuep)) {
		fprintf(stderr, "Cannot parse attribute assignment %s\n", s);
		free(s);
		return 0;
	}

	free(s);
	return 1;
}
