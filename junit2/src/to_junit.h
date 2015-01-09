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
