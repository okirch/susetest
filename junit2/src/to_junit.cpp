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
// output decomposed data to junit xml
//
//////////////////////////////////////////////////////////////////
#include <QtCore/QtGlobal>

#include <stdio.h>
#include <stdlib.h>

#include "to_junit.h"
#include "decomposition.h"

#define MSECS_IN_A_DAY 86400000L // 24 x 60 x 60 x 1000

// Compute the time span in seconds between two dates
double ToJunit::timeSpan(QDateTime &date1, QDateTime &date2) const
{
  long long msecs;
#if QT_VERSION >= 0x040700
  msecs = date2.toMSecsSinceEpoch() - date1.toMSecsSinceEpoch();
#else
  msecs = date1.time().msecsTo(date2.time()) +
          MSECS_IN_A_DAY * (date1.date().daysTo(date2.date()));
#endif
  return (double) msecs / 1000.0;
}

// Constructor
ToJunit::ToJunit()
  : output(), root(), testsuite(), testcase(),
    line(NULL), state(none),
    suites(0), tests(0), failures(0), errors(0), skipps(0),
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

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  suiteTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");

  testsuite = output.createElement("testsuite");
  root.appendChild(testsuite);

  QString package = d->getValue("id", "(unknown)");
  testsuite.setAttribute("package", package);
  QString name = d->getValue("text", NULL);
  if (name.isNull()) name = package;
  testsuite.setAttribute("name", name);
  testsuite.setAttribute("timestamp", suiteTime.toString(Qt::ISODate));
  testsuite.setAttribute("hostname", d->getValue("host", "localhost"));

  properties = output.createElement
    ("properties");                    // this information is not available
  testsuite.appendChild(properties);
}

// Open a testcase
void ToJunit::openTestcase(const Decomposition *d)
{
  QString time;

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  caseTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");

  testcase = output.createElement("testcase");
  testsuite.appendChild(testcase);

  QString classname = d->getValue("id", "(unknown)");
  testcase.setAttribute("classname", classname);
  QString name = d->getValue("text", NULL);
  if (name.isNull()) name = classname;
  testcase.setAttribute("name", name);
}

// Close a testsuite
void ToJunit::closeTestsuite(const Decomposition *d)
{
  QString time;
  QDateTime endTime;
  double span;
  QDomElement systemOut, systemErr;
  QDomText errText;

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  endTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");
  span = timeSpan(suiteTime, endTime);

  testsuite.setAttribute("id", suites);
  testsuite.setAttribute("tests", tests);
  testsuite.setAttribute("failures", failures);
  testsuite.setAttribute("errors", errors);
  testsuite.setAttribute("skipped", skipps);
  testsuite.setAttribute("time", span);

// TBD: we currently arbitrarily assume that all output was sent to stderr
//      this could be determined from some setting
  systemOut = output.createElement("system-out");
  testsuite.appendChild(systemOut);

  systemErr = output.createElement("system-err");
  testsuite.appendChild(systemErr);
  errText = output.createCDATASection(suiteText);
  systemErr.appendChild(errText);
}

// Close a testcase
void ToJunit::closeTestcase(const Decomposition *d)
{
  QString time;
  QDateTime endTime;
  double span;

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  endTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");
  span = timeSpan(caseTime, endTime);

  testcase.setAttribute("time", span);
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
  errText = output.createCDATASection(caseText);
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
  errText = output.createCDATASection(caseText);
  error.appendChild(errText);
}

void ToJunit::createSkipped(const Decomposition *d)
{
	QDomElement skipp;

	skipp = output.createElement("skipped");
	testcase.appendChild(skipp);
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
      if (d.keyword("success") || d.keyword("failure") || d.keyword("error") || d.keyword("skipped"))
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
	else if (d.keyword("skipped"))
	{
	  skipps++;
	  createSkipped(&d);
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
