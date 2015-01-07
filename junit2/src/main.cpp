#include <stdio.h>
#include <unistd.h>

#include "to_junit.h"

// Print usage message
void usage(const char *name)
{
   fprintf(stderr, "Usage:\n");
   fprintf(stderr, "  %s                   convert stdin to stdout\n", name);
   fprintf(stderr, "  %s <input>           convert input file to stdout\n", name);
   fprintf(stderr, "  %s <input> <output>  convert input file to output file\n", name);
   fprintf(stderr, "  %s -h | --help       print this help message\n", name);
}

// Open input file, if any
void open_files(int argc, const char **argv, FILE **in, FILE **out)
{
  if (argc < 1 || argc > 3)
  {
    usage(*argv);
    exit(1);
  }

  if (argc == 2)
  {
    if (!strcmp(argv[1], "-h") ||
        !strcmp(argv[1], "--help")
       )
    {
      usage(*argv);
      exit(0);
    }
  }

  if (argc >= 2)
  {
    const char *filename;

    filename = argv[1];
    *in = fopen(filename, "r");
    if (*in == NULL)
    {
      fprintf(stderr, "Can't open %s\n", filename);
      exit(2);
    }
  }
  else *in = stdin;

  if (argc >= 3)
  {
    const char *filename;

    filename = argv[2];
    *out = fopen(filename, "w");
    if (*out == NULL)
    {
      fprintf(stderr, "Can't open %s\n", filename);
      exit(2);
    }
  }
  else *out = stdout;
}

// Main program
int main(int argc, const char **argv)
{
  FILE *in, *out;
  ToJunit converter;

  open_files(argc, argv, &in, &out);

  converter.parse(in);
  converter.print(out);

  fclose(in);
  fclose(out);
}
