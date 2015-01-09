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
// output decomposed data to junit xml
//
//////////////////////////////////////////////////////////////////

#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>

#include "to_junit.h"
#include "decomposition.h"


static QString	printTimeISO(time_t);
static float	elapsedMS(const struct timeval *now, const struct timeval *since);

// Constructor
ToJunit::ToJunit()
  : output(), root(), testsuite(), testcase(),
    line(NULL), state(none),
    suites(0), tests(0), failures(0), errors(0),
    suiteText(""), caseText("")
{
}

// Destructor
ToJunit::~ToJunit()
{
  if (line)
    free(line);
}

// Record arbitrary input lines
void ToJunit::recordLine(const char *line)
{
  switch (state)
  {
    case test_case:
      caseText += line;
    case test_suite:
      suiteText += line;
    case none:
      ;
  }
}

// Open a testsuite
void ToJunit::openTestsuite(const Decomposition *d)
{
  QString time;
  QDomElement properties;

  suiteTime = getTimeAttr(d);

  testsuite = output.createElement("testsuite");
  root.appendChild(testsuite);

  testsuite.setAttribute("package", d->getValue("id", "(unknown)"));
  testsuite.setAttribute("name", d->getValue("text", "(unknown)"));
  testsuite.setAttribute("timestamp", printTimeISO(suiteTime.tv_sec));
  testsuite.setAttribute("hostname", d->getValue("host", "localhost"));

  properties = output.createElement
    ("properties");                    // this information is not available
  testsuite.appendChild(properties);
}

// Open a testcase
void ToJunit::openTestcase(const Decomposition *d)
{
  QString time;

  caseTime = getTimeAttr(d);

  testcase = output.createElement("testcase");
  testsuite.appendChild(testcase);

  testcase.setAttribute("classname", d->getValue("id", "(unknown)"));
  testcase.setAttribute("name", d->getValue("text", "(unknown)"));
}

// Close a testsuite
void ToJunit::closeTestsuite(const Decomposition *d)
{
  struct timeval endTime;
  QDomElement systemOut, systemErr;
  QDomText errText;
  QString timeAttr;

  endTime = getTimeAttr(d);

  timeAttr.setNum(elapsedMS(&endTime, &suiteTime), 'f');

  testsuite.setAttribute("id", suites);
  testsuite.setAttribute("tests", tests);
  testsuite.setAttribute("failures", failures);
  testsuite.setAttribute("errors", errors);
  testsuite.setAttribute("time", timeAttr);

// TBD: we currently arbitrarily assume that all output was sent to stderr
//      this could be determined from some setting
  systemOut = output.createElement("system-out");
  testsuite.appendChild(systemOut);

  systemErr = output.createElement("system-err");
  testsuite.appendChild(systemErr);
  errText = output.createTextNode(suiteText);
  systemErr.appendChild(errText);
}

// Close a testcase
void ToJunit::closeTestcase(const Decomposition *d)
{
  struct timeval endTime = getTimeAttr(d);
  QString timeAttr;

  timeAttr.setNum(elapsedMS(&endTime, &caseTime), 'f');
  testcase.setAttribute("time", timeAttr);
}

// Create a failure
void ToJunit::createFailure(const Decomposition *d)
{
  QDomElement failure;
  QDomText errText;

  failure = output.createElement("failure");
  testcase.appendChild(failure);

  failure.setAttribute("type", d->getValue("type", "randomError"));
  failure.setAttribute("message", d->getValue("text", "(unknown)"));
  errText = output.createTextNode(caseText);
  failure.appendChild(errText);
}

// Create an error
void ToJunit::createError(const Decomposition *d)
{
  QDomElement error;
  QDomText errText;

  error = output.createElement("error");
  testcase.appendChild(error);

  error.setAttribute("type", d->getValue("type", "randomError"));
  error.setAttribute("message", d->getValue("text", "(unknown)"));
  errText = output.createTextNode(caseText);
  error.appendChild(errText);
}

// Process one directive
void ToJunit::directive(const char *line)
{
  Decomposition d;

  // Do the parsing
  d.parseDirective(line);

  // Act based upon current state
  switch (state)
  {
    case none:
      if (d.keyword("testsuite"))
      {
        openTestsuite(&d);
        tests = 0;
        failures = 0;
        state = test_suite;
      }
      break;
    case test_suite:
      if (d.keyword("testcase"))
      {
        openTestcase(&d);
        state = test_case;
      }
      else if (d.keyword("endsuite"))
      {
        closeTestsuite(&d);
        suites++;
        suiteText = "";
        state = none;
      }
      break;
    case test_case:
      if (d.keyword("success") || d.keyword("failure") || d.keyword("error"))
      {
        tests++;
        if (d.keyword("failure"))
        {
          failures++;
          createFailure(&d);
        }
        else if (d.keyword("error"))
        {
          errors++;
          createError(&d);
        }
        closeTestcase(&d);
        caseText = "";
        state = test_suite;
      }
      break;
  }
}

// Parse input file
void ToJunit::parse(FILE *fp)
{
  size_t size = 0;

  root = output.createElement("testsuites");
  output.appendChild(root);

  while (getline(&line, &size, fp) != -1)
  {
    recordLine(line);

    if (!strncmp(line, "###junit ", 9))
      directive(line + 9);
  }
}

// Print result
void ToJunit::print(FILE *fp) const
{
  fputs(output.toString(2).toLatin1(), fp);
}

// Helper functions
QString ToJunit::getTimeAttrString(const Decomposition *d)
{
  return d->getValue("time", "1970-01-01T00:00:00.000");
}

struct timeval ToJunit::getTimeAttr(const Decomposition *d)
{
  struct timeval result = { 0, 0 };
  QString timeString;
  struct tm tm;
  const char *s;
  time_t seconds;

  timeString = getTimeAttrString(d);
  if (timeString.isEmpty())
    return result;

  QByteArray ba(timeString.toUtf8());
  s = ba.constData();
  if (s == 0)
    return result;

  memset(&tm, 0, sizeof(tm));

  s = strptime(s, "%Y-%m-%dT%H:%M:%S", &tm);
  if (s == NULL)
    return result;

  if (*s == '.') {
    // Consume the .<millisecs> portion
    result.tv_usec = strtoul(s + 1, (char **) &s, 10);
  }

  if (*s != '\0')
    return result;

  seconds = mktime(&tm);
  if (seconds == (time_t) -1)
    return result;

  result.tv_sec = seconds;
  return result;
}

static QString	printTimeISO(time_t time)
{
  char buffer[128];
  struct tm *tm;

  tm = localtime(&time);
  if (tm == NULL)
    return QString::null;

  strftime(buffer, sizeof(buffer), "%FT%T", tm);
  return QString(buffer);
}

static float
elapsedMS(const struct timeval *now, const struct timeval *since)
{
  struct timeval diff;

  timersub(now, since, &diff);
  return diff.tv_sec + 1e-6 * diff.tv_usec;
}

