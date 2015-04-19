/*
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

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <getopt.h>

#include "suselog.h"
#include "xml.h"

static const char *	opt_logfile;

static void	show_usage(int rv);
extern int	do_merge(int argc, char **argv);

static struct option options[] = {
	{ "logfile",	required_argument,	NULL,	'f' },
	{ "help",	no_argument,		NULL,	'h' },
	{ NULL }
};

int
main(int argc, char *argv[])
{
	char *cmd;
	int rv = 1;
	int c;

	while ((c = getopt_long(argc, argv, "f:h", options, NULL)) != EOF) {
		switch (c) {
		case 'f':
			opt_logfile = optarg;
			break;

		case 'h':
			show_usage(0);
			break;

		default:
			show_usage(1);
		}
	}

	if (optind >= argc)
		show_usage(0);

	cmd = argv[optind];
	if (!strcmp(cmd, "help"))
		show_usage(0);

	if (!strcmp(cmd, "merge")) {
		rv = do_merge(argc - optind, argv + optind);
	} else {
		fprintf(stderr, "unsupported command \"%s\"\n", cmd);
		show_usage(1);
	}

	return rv;
}

void
show_usage(int rv)
{
	FILE *fp = rv? stderr : stdout;

	fprintf(fp,
		"Usage:\n"
		"suselog command [args]\n"
		"Currently supported commands:\n"
		"  merge     merge another log file into the specified one\n"
		"  help      show this help message\n"
	       );
	exit(rv);
}

int
do_merge(int argc, char **argv)
{
	const char *src_logfile = NULL;
	xml_document_t *dst_doc, *src_doc;
	xml_node_t *dst_root, *dst_node, *src_root, *collection;
	bool merged = false;

	if (argc != 2) {
		fprintf(stderr,
			"Usage:\n"
			"suselog merge <logfile>\n");
		return 1;
	}
	src_logfile = argv[1];

	if (opt_logfile == NULL) {
		fprintf(stderr, "No primary logfile specified\n");
		return 1;
	}
	if (src_logfile == NULL) {
		fprintf(stderr, "No secondary logfile specified\n");
		return 1;
	}

	dst_doc = xml_document_read(opt_logfile);
	if (!dst_doc || !(dst_root = dst_doc->root)) {
		fprintf(stderr, "Unable to read logfile \"%s\"\n", opt_logfile);
		return 1;
	}

	/* Find the node to insert into */
	for (dst_node = dst_root->children; dst_node; dst_node = dst_node->next) {
		if (!strcmp(dst_node->name, "testsuites"))
			break;
	}
	if (dst_node == NULL)
		xml_node_new("testsuites", dst_root);

	src_doc = xml_document_read(src_logfile);
	if (!src_doc || !(src_root = src_doc->root)) {
		fprintf(stderr, "Unable to read logfile \"%s\"\n", src_logfile);
		return 1;
	}

	printf("Merging %s into %s\n", src_logfile, opt_logfile);
	for (collection = src_root->children; collection; collection = collection->next) {
		xml_node_t *node, *next;

		if (strcmp(collection->name, "testsuites"))
			continue;

		for (node = collection->children; node; node = next) {
			next = node->next;

			xml_node_reparent(dst_node, node);
			merged = true;
		}
	}

	if (merged && xml_document_write(dst_doc, opt_logfile) < 0) {
		fprintf(stderr, "Unable to write merged document to %s\n", opt_logfile);
		return 1;
	}

	xml_document_free(src_doc);
	xml_document_free(dst_doc);

	return 0;
}
