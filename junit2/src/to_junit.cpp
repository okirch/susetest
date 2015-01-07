#include <stdio.h>

#include "to_junit.h"
#include "decomposition.h"

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

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  suiteTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");

  testsuite = output.createElement("testsuite");
  root.appendChild(testsuite);

  testsuite.setAttribute("package", d->getValue("id", "(unknown)"));
  testsuite.setAttribute("name", d->getValue("text", "(unknown)"));
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

  testcase.setAttribute("classname", d->getValue("id", "(unknown)"));
  testcase.setAttribute("name", d->getValue("text", "(unknown)"));
}

// Close a testsuite
void ToJunit::closeTestsuite(const Decomposition *d)
{
  QString time;
  QDateTime endTime;
  float span;
  QDomElement systemOut, systemErr;
  QDomText errText;

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  endTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");
  span = (float) (endTime.toMSecsSinceEpoch() - suiteTime.toMSecsSinceEpoch()) / 1000.0;

  testsuite.setAttribute("id", suites);
  testsuite.setAttribute("tests", tests);
  testsuite.setAttribute("failures", failures);
  testsuite.setAttribute("errors", errors);
  testsuite.setAttribute("time", span);

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
  QString time;
  QDateTime endTime;
  float span;

  time = d->getValue("time", "1970-01-01T00:00:00.000");
  endTime = QDateTime::fromString(time, "yyyy-MM-ddThh:mm:ss.zzz");
  span = (float) (endTime.toMSecsSinceEpoch() - caseTime.toMSecsSinceEpoch()) / 1000.0;

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
