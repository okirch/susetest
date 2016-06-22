## Susetest api functions.


* logging.
* how to run commands on SUTs(system_under_test)


Some words on logging
=====================

When we looked for a reasonable file format for reporting test results, we
decided to settle for JUnit XML. It seems to be a pretty common standard,
plus jenkins is able to use it to generate reports from it.

The basic structure of a JUnit report is a collection of test groups, and each
test group containing a number of individual test cases. The basic report
has a name (such as "mytest" or "nfs"), and each group (or "testsuite" as
it's called within the junit file) has a name prefixed with that base name
(such as "nfs.init" or "nfs.regressions").

Individual test cases can have a result of "success", "failure", or "error".
The difference between "failure" and "error" is this: if the test case does
not produce the expected result, then this is a failure by default. However,
if the code executing the test case behaves erractically (for instance,
by throwing a python exception), then this would be an error.

There are other states, but we're not using these effectively right now.

Apart from the test result, it is possible to log the standard output of the
command to the test report. Built-in functions provided by susetest do this
for you already.


When using susetest, the global Config object will provide you with
a handle to use for reporting; it is called "journal":
```
  import susetest

  config = susetest.Config("mytest")
  journal = config.journal
```
The basic API provided by the Journal class is this
```
journal.beginGroup(tag, description)
journal.finishGroup()
```
  In JUnit, you can group test cases that belong together. The
  tag should be a short identifier consisting of alphanumeric
  characters plus "-" and "_", and should be unique within your
  test suite.
```
journal.beginTest(tag, description)
journal.beginTest(description)
```
  Either of these two calls indicates the beginning of a new test case. The
  tag is a unique identifier, like the tags used in beginGroup. However,
  given that it may not be practical or needed to define separate tags for
  each test case, this argument is optional. If no explicit tag is specified,
  the logging library will just make up a tag automatically.

  If you call beginTest() without having explicitly finished the previous
  test case, the logging library will assume that the test succeeded.
```
journal.info(msg)
journal.warning(msg)
```
  These functions let you print informational and warning messages.
  These messages will show up both on screen and in the test report.
```
journal.recordStdout(data)
journal.recordStderr(data)
```
  This will record the given data as standard output/error for the
  current test case. The argument can be either a string or a
  bytearray object.
```
journal.success(msg)
journal.failure(msg)
journal.error(msg)
```
  These calls finish the current test and sets its status accordingly.
  The msg argument is optional for success(), but is required for the
  other calls.

  Note to those relatively new to python: printf style formatting
  is done using the "%" operator, like this:
```
   Journal.failure("Argh, unable to contact %s at %s" % (service, ipaddr))
```

``` 
journal.writeReport()
```

```
susetest.finish(journal)
```


susetest.finish(journal) function is equivalent to 


```
journal.writeReport()
        if (journal.num_failed() + journal.num_errors()):
                        sys.exit(1)
        sys.exit(0)

```

If errors (not failures !) or failed test happens, then exit with 1.

This is usefull for integration with susetest and Jenkins automation-framework.

