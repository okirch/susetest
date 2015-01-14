//////////////////////////////////////////////////////////////////
// Test logging facilities for SUSE test automation
//
// Copyright (C) 2015 SUSE Linux products
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
// Take a test log file with ###junit lines and decompose
//
//////////////////////////////////////////////////////////////////

#include <QtCore/QString>

#include <ctype.h>
#include <string.h>

#include "decomposition.h"

// Constructor
Decomposition::Decomposition()
{
}

// Parse directive like
//   ###junit testcase time="..." id="..." text="..."
// We try to accept " inside the "..."
void Decomposition::parseDirective(const char *line)
{
  enum { before_keyword, keyword,
         before_name, name,
         before_equal, equal,
         quote, value, endquote,
         unknown } parser;

  keyBegin = keyEnd = "";
  pairs = 0;

  // Parse input
  for (parser = before_keyword;
       *line && pairs < 10;
       line++) switch (parser)
  {
    case before_keyword: // ###junit^
      if (!isspace(*line))       { keyBegin = line;            parser = keyword; }
      break;
    case keyword:        // ###junit t^
      if (isspace(*line))        { keyEnd = line;              parser = before_name; }
      break;
    case before_name:    // ###junit testcase ^
      if (pairs && *line == '"') { valueEnd[pairs - 1] = line; parser = endquote; }
      else if (!isspace(*line))  { nameBegin[pairs] = line;    parser = name; }
      break;
    case name:           // ###junit testcase i^
      if (pairs && *line == '"') { valueEnd[pairs - 1] = line; parser = endquote; }
      else if (isspace(*line))   { nameEnd[pairs] = line;      parser = before_equal; }
      else if (*line == '=')     { nameEnd[pairs] = line;      parser = equal; }
      break;
    case before_equal:   // ###junit testcase id ^
      if (pairs && *line == '"') { valueEnd[pairs - 1] = line; parser = endquote; }
      else if (*line == '=')     {                             parser = equal; }
      else if (!isspace(*line))  {                             parser = unknown; }
      break;
    case equal:          // ###junit testcase id =^
      if (*line == '"')          {                             parser = quote; }
      else if (!isspace(*line))  {                             parser = unknown; }
      break;
    case quote:          // ###junit testcase id = "^
      valueBegin[pairs] = line;
      if (*line == '"')          { valueEnd[pairs++] = line;   parser = endquote; }
      else                       {                             parser = value; }
      break;
    case value:          // ###junit testcase id = "f^
      if (*line == '"')          { valueEnd[pairs++] = line;   parser = endquote; }
      break;
    case endquote:       // ###junit testcase id = "foo"^
      if (pairs && *line == '"') { valueEnd[pairs - 1] = line; parser = endquote; }
      else if (isspace(*line))   {                             parser = before_name; }
      else                       {                             parser = unknown; }
      break;
    case unknown:        // ###junit testcase id = "foo" bar b^
      if (pairs && *line == '"') { valueEnd[pairs - 1] = line; parser = endquote; }
      break;
  }
}

// Test keyword match
bool Decomposition::keyword(const char *value) const
{
  return strncmp(keyBegin, value, keyEnd - keyBegin) == 0;
}

// Search value matching given name
#include <stdio.h>
QString Decomposition::getValue(const char *name, const char *defaultValue) const
{
  int i;

  for (i = 0; i < pairs; i++)
  {
    if (!strncmp(nameBegin[i], name, nameEnd[i] - nameBegin[i]))
      return QString::fromLatin1(valueBegin[i], valueEnd[i] - valueBegin[i]);
  }
  return QString(defaultValue);
}

