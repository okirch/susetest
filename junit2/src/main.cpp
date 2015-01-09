//////////////////////////////////////////////////////////////////
// Test logging facilities for SUSE test automation
//
// Copyright (C) 2015 Eric Bischoff <ebischoff@suse.de>
//
// This program is free software; you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 2 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
//
//
// main routine for conversion of "###junit" log files to xml
//
//////////////////////////////////////////////////////////////////

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>

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
