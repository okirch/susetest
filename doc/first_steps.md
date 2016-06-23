## Susetest api functions documentation.[Work in progress]


* the logging facility on susetest.
* [susetest core library](#susetest-core)
* [susetest_api](#susetest-api)
* [examples](#examples)

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

## susetest core

#### How do i run commands on my systems under test?. (Run family commands)

> you don't need os or subprocess from python! run is the answer!

* run, runOrFail, runBackground, wait commands
* wait commands
* the targets attributes (ip_addr, etc)
* how to work with files

First , we have to define the target.

```
#! /usr/bin/python

import sys
import traceback
import twopence
import susetest
import suselog


journal = None
client = None
server = None

def setup():
    global client, server, journal

    config = susetest.Config("tests-tomcat")
    journal = config.journal

    client = config.target("client")
    server = config.target("server")

```

Now we have 2 targets (in example) : client and server.

so after the setup, we can run some commands with run.

```
setup()
try:
  server.run("uptime")
  client.run("uptime")
...
```

THe run method as different parameter. here we are with the parameters that you can use.

```
server.run("uptime", user="testuser", timeout=500, quiet=True)
```
* user, let you specify with which user you want to run on the command. (by default all command are runned as root.
* timeout , you can increase the timeout for the command. by default is 60 seconds
* quiet =True  will suppress the stdout of the command. default is false 

```
server.run("ip a s", user="testuser", timeout=500)
```
will print th ip on the logging output. with true you suppress it.


#### runOrFail command

runOrFail is similar to run, but you can use for automatically make a test fails( as the name suggest) .

```
  journal.beginTest("Verify host lookup of %s" % hostname)
        client.runOrFail("getent hosts %s" % hostname)
```

#### What is the basic workflow for one test? An example for run command.

```
        journal.beginGroup("apache2 tests")
        
        journal.beginTest("check status apache2") 
        status = server.run("systemctl status apache2)
        if not status and status.code != 0
                 journal.failure("Oops: fail to get the status of apache2 service")
        journal.success("apache2 is running")
        
        journal.beginTest("restart apache2 service")
        server.runOrFail("systemctl restart apache2")
```

#### Capture output or code of commands.

* capture the output of a command

you can capture the output of comand with the **stdout** method of the run object. here an example:
Remeber that you have to transfom it into a string.
```
 status = client1.run("cat " + tf)
        if not(status):
                journal.failure("unable to read testfile on client1")
        else:
                after = str(status.stdout)
                if after == "frankzappa":
                        journal.success("Great: file contains \"frankzappa\"")
                else:
                        journal.failure("Too bad: file contains \"%s\" (expected \"frankzappa\")" % after)

```
* check the retcode of a command.

Similar to the stdout , we can check the return code of a command. 

```
  journal.beginTest("Check status of stopped NFS server")
        st = server.run("rcnfsserver status")
        if st.code != 3:
                journal.info("rcnfsserver status returned exit code %d" % st.code)
                journal.failure("rcnfsserver should have returned 3 [unused]")

```
* the susetest_api has some common function to do this basic stuff, but susetest_core api give you the possibility to implement your own functions

**Hint:**
Take care, that sometimes commands that you run, doesn't eliminate white spaces.
Here is an example for cleaning up. For this, you can use strip(), or s.rstrip(). take a look on python doc for this.
```
        status = node.run("losetup -f")
        if status and status.stdout:
                dev = str(status.stdout).strip()
```


#### The differents attributes of susetest targets.

```
server.ipadrr, self.ip6addr ,  server.family,  server.name 
```

## susetest api

## examples
