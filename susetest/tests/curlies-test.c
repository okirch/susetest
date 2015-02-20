
#include <stdio.h>
#include "susetest.h"
#include "curlies.h"

int
main(int argc, char **argv)
{
	const char *filename;
	susetest_config_t *cfg;

	if (argc <= 1) {
		fprintf(stderr, "Missing file name argument\n");
		return 1;
	}

	filename = argv[1];
	cfg = curly_parse(filename);
	if (cfg == NULL) {
		fprintf(stderr, "Unable to parse file \"%s\"\n", filename);
		return 1;
	}

	curly_print(cfg, stdout);

	susetest_config_free(cfg);

	return 0;
}
