//////////////////////////////////////////////////////////////////
//
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
//////////////////////////////////////////////////////////////////

#include <QtCore/QDateTime>
#include <QtXml/QDomDocument>

class Decomposition;

class ToJunit
{
  private:
    QDomDocument output;
    QDomElement root, testsuite, testcase;
    char *line;
    enum
      { none = 0, test_suite, test_case } state;
    int suites, tests, failures, errors;
    QString suiteText, caseText;
    struct timeval suiteTime, caseTime;

    void recordLine(const char *line);
    void openTestsuite(const Decomposition *d);
    void openTestcase(const Decomposition *d);
    void closeTestsuite(const Decomposition *d);
    void closeTestcase(const Decomposition *d);
    void createFailure(const Decomposition *d);
    void createError(const Decomposition *d);
    void directive(const char *line);

    QString getTimeAttrString(const Decomposition *d);
    struct timeval getTimeAttr(const Decomposition *d);

  public:
    ToJunit();
    ~ToJunit();
    void parse(FILE *fp);
    void print(FILE *fp) const;
};
