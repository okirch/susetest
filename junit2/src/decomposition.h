class QString;

class Decomposition
{
  private:
    int pairs;
    const char *keyBegin, *keyEnd,
               *nameBegin[10], *nameEnd[10],
               *valueBegin[10], *valueEnd[10];

  public:
    Decomposition();
    void parseDirective(const char *line);
    bool keyword(const char *value) const;
    QString getValue(const char *name, const char *defaultValue) const;
};
