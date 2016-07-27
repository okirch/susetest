## Susetest api functions documentation.

* susetest design concept
* Helloworld test with susetest
* [the logging facility on susetest](#some-words-on-logging)
* [susetest core library](#susetest-core)
* [susetest_api](#susetest-api)
* [advanced examples](#advanced-examples)

##  Susetest design concept

As you can see [susetest design concept](susetest_design.jpg). 

Susetest can run in every automation framework and run tests for one or more target machines (virtual, docker or bare metal).

The **control-node** is an isolated environment, could be a VM, systemd-jail, or on bare metal. In SLEnkins it's a systemd-jail.

The separation between SUTs (Systems under test) and control-node is very important for testing. This gives you 100% reproducibility for testing: you don't mix up stuff between machines under tests.

## Hello World test with susetest

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

### we need this function for setup logging and SUT
def setup():
    global client, server, journal

    config = susetest.Config("workshop-helloworld")
    journal = config.journal

    client = config.target("client")
    server = config.target("server")

### Here we make one function, that can be used from server or client node
def some_test(node):
    journal.beginTest("This is some test")

    if node.run("uptime"):
        journal.success("Test on " + node.name + " has succeeded")
    else:
        journal.failure("Test on " + node.name + " has failed")

###################### MAIN-FUNCTION is here ..

setup()

try:
    some_test(client)
    some_test(server)

except:
    print "Unexpected error"
    journal.info(traceback.format_exc(None))
    raise

susetest.finish(journal)
```

#  Some words on logging

When we looked for a reasonable file format for reporting test results, we
decided to settle for JUnit XML. It seems to be a pretty common standard,
plus Jenkins is able to use it to generate reports from it.

The basic structure of a JUnit report is a collection of test groups, and each
test group containing a number of individual test cases. The basic report
has a name (such as "mytest" or "nfs"), and each group (or "testsuite" as
it's called within the junit file) has a name prefixed with that base name
(such as "nfs.init" or "nfs.regressions").

Individual test cases can have a result of *success*, *failure*, or *error*.
The difference between "failure" and "error" is this: if the test case does
not produce the expected result, then this is a failure by default. However,
if the code executing the test case behaves erractically (for instance,
by throwing a python exception), then this would be an error.

There are other states, but we're not using these effectively right now.

Apart from the test result, it is possible to log the standard output of the
command to the test report. Built-in functions provided by susetest do this
for you already.


When using susetest, the global `Config` object will provide you with
a handle to use for reporting; it is called *journal*:

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
characters plus *-* and *_*, and should be unique within your
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
journal.failure("Argh, unable to contact %s at %s" % (service, ipaddr))
journal.writeReport()
susetest.finish(journal)
```

The `susetest.finish(journal)` function is equivalent to 

```
journal.writeReport()
if (journal.num_failed() + journal.num_errors()):
    sys.exit(1)
    sys.exit(0)
```

If errors (not failures !) or failed tests happen, then exit with 1.

This is usefull for integration with susetest and the Jenkins automation-framework.

## susetest core

#### How do I run commands on my systems under test? (Run family commands)

> You don't need *os* or *subprocess* from python! Run is the answer!

* `run`, `runOrFail`, `runOrRaise`
* `runBackground`, wait commands
* the targets attributes (`ip_addr`, etc)
* how to work with files

First, we have to define the target.

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

Now we have two targets: client and server.
So after the setup, we can run some commands with `run`.

```
setup()
try:
  server.run("uptime")
  client.run("uptime")
...
```

The run method has several parameters. Here you can see which parameters you can use.

```
server.run("uptime", user="testuser", timeout=500, quiet=True)
```

* `user`, specifies as which user you want to run the command. Default: root.
* `timeout`, you can increase the timeout for the command. Default: 60 seconds.
* `quiet = True`,  will suppress the stdout of the command. Default: false.

The following will print the IP on the logging output. With `quiet=true` you suppress it.
```
server.run("ip a s", user="testuser", timeout=500)
```

#### runOrFail command

`runOrFail` is similar to run, with the excpetion that the test will be marked as failed if the command returns an error or can't be executed.

```
journal.beginTest("Verify host lookup of %s" % hostname)
  client.runOrFail("getent hosts %s" % hostname)
```

#### What is the basic workflow for one test? An example for run command

```
journal.beginGroup("apache2 tests")
 
journal.beginTest("check status apache2") 
status = server.run("systemctl status apache2)
if not status and status.code != 0:
  journal.failure("Oops: fail to get the status of apache2 service")
journal.success("apache2 is running")
        
journal.beginTest("restart apache2 service")
server.runOrFail("systemctl restart apache2")
```

#### Capture output or code of commands

* capture the output of a command

You can capture the output of a comand with the **stdout** method of the `run` object.
Remember that you have to transfom it into a string:

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

* check the retcode of a command

Similar to stdout, we can check the return code of a command:

```
journal.beginTest("Check status of stopped NFS server")
st = server.run("rcnfsserver status")
if st.code != 3:
  journal.info("rcnfsserver status returned exit code %d" % st.code)
  journal.failure("rcnfsserver should have returned 3 [unused]")
```

* the *susetest_api* has some common functions to do this basic stuff, but *susetest_core* API give you the possibility to implement your own functions

**Hint:**
Take care, that sometimes commands that you run, doesn't eliminate white spaces.
Here is an example for clean up. You can use `strip()`, or `s.rstrip()`. Refer to the python documentation for more information on this.

```
status = node.run("losetup -f")
if status and status.stdout:
  dev = str(status.stdout).strip()
```

#### The different attributes of susetest targets

When you define a target, like server, you have some attributes that can help you testing.

Here is the actual list:

```
node.ipadrr, self.ip6addr, self.ipaddr_ext,  self.family,  self.name 
```

Some example why these are cool attributes (you maybe already understood why ? :) )

**node.ipaddr**

ip_internal 192.x.x.x, != ipaddr_ext cloud_ip = 10.x.x.x

```
client1.runOrFail("/usr/sbin/showmount -e %s" % server.ipaddr)
```

**node.family**

```
# we do something if we have opensuse_leap42.2
if (server.family == 42.2):
  server.run("zypper in docker")
# sles-12-sp2
if (server.family == 12.2)    
  #something else
```

**node.name**

The name attribute gives you the node name, not the hostname.
This is useful, when you have a  generic function like this:

```
if node.name == "server":
    node.run("systemctl start apache2")
if node.name == "client"
    do other stuff for client
```

#### working with files 

*  sendfile, recvfile
*  recvbuffer, sendbuffer

*recvfile/sendfile*: These functions transfer a file from the SUT to the control node, or vice versa.
This is useful, for instance, if you need to copy a tarball to the SUT and unpack it there. 

```
node.sendfile(remotefile = "/etc/idmapd.conf", data = idmapd_conf)
```

```
localPath = server.workspaceFile("rpcunit.xml")
print "localPath is ", localPath
if not server.recvfile("/tmp/rpcunit.xml", localfile = localPath, permissions = 0644):
  journal.failure("unable to download /tmp/rpcunit.xml to " + localPath)
  return
```

*recvbuffer/sendbuffer*: These functions transfer a file from the SUT to a python bytearray object, or vice versa. This is useful if you want to process the content of a file on the SUT (eg. add an entry to `/etc/hosts`)

Here some examples. I use the function from `susetest_api.files`

```
def replace_string(node, replacements, _file, _max_replace=0):
        ''' replace given strings as dict in the file '''
        data = node.recvbuffer(_file)
        if not data:
                node.journal.fatal("something bad with getting the file {}!".format(_file))
      		return False
        data_str = str(data)
        for src, target in replacements.iteritems():
                if not _max_replace:
                        data_str = data_str.replace(str(src), str(target))
                else:
                        data_str = data_str.replace(str(src), str(target), _max_replace)
        if not node.sendbuffer(_file,  bytearray(data_str)):
                node.journal.fatal("error writing file {}".format(_file))
return False 
```

## susetest api

The main goal of this, is to improve the susetest_core api.
One important choice by creating this api, was the design. susetest_api is on top of susetest_core. 
This implies the following: susetest_api doesn't change the stable basic design of the core api: it is optional to susetest_core api.
So no regression is added, because this are two linux stand-alone tools.

In future, we can integrate some functions from susetest_api to susetest_core, if they are provide really an advantage for the nodes and are nodes methods, and we have some unit-testing automation for this functions. (see *how-to-contribute*).

The susetest_core api can be found here:
https://github.com/okirch/susetest/blob/master/susetest/python/susetest.py

The susetest_api can be found here:
https://github.com/okirch/susetest/tree/master/susetest/python/susetest_api

susetest_api is somthing like a rolling api. If you think that you have a cool generic function, you can create one. see *how-to-contribute* for this.

If you want to use the susetest_api, you need to import the specific modules, and function you want to use:

```
from susetest_api.log import systemd_check

systemd_check(sut)
```

An example with more functions:

```
from susetest_api.assertions import fail_retcode, assert_ok_equal

   fail_retcode(sut, "ls #I FAIL", 127)
   fail_retcode(sut, "ls -ERROR_COMMAND", 2)
   assert_ok_equal(sut, "whoami", "root")

```

The output will be:

```   
---------------------------------
TEST: Command must fail "ls -ERROR_COMMAND" with retcode"127" 
sut: ls -ERROR_COMMAND
ls: invalid option -- 'E'
Try 'ls --help' for more information.
sut: command "ls -ERROR_COMMAND" failed: status 2
Failing: Command error_code"2" expected retcode: "127". TEST_FAIL!!
FAIL: Command error_code"2" expected retcode: "127". TEST_FAIL!!

---------------------------------

---------------------------------
TEST: Command must fail "ls -ERROR_COMMAND" with retcode"2" 
sut: ls -ERROR_COMMAND
ls: invalid option -- 'E'
Try 'ls --help' for more information.
sut: command "ls -ERROR_COMMAND" failed: status 2
Command failed with retcode "2" as expected  "ls -ERROR_COMMAND" PASS! OK
SUCCESS

---------------------------------

---------------------------------
TEST: for successful cmd: "whoami" ASSERT_OUTPUT:  "root" 
sut: whoami
root
ASSERT_TEST_EQUAL to whoami PASS! OK
SUCCESS
```

## Advanced examples

### Machinery integration on susetest

This is needed for machinery. (Maybe in future I will see for more dynamic way)

Ensure that your control-node has the following option in: `/var/lib/slenkins/.ssh/config`

```
Host *
    StrictHostKeyChecking no
~ 
```

Now, your run.py should only contain:

```
machinery_sut = machinery(sut)
machinery_sut.inspect()
machinery_sut.show("tests-systemd") # name of your testsuite
```

At the end you will have a machinery report in the workspace directory.

For the command `show` you can choose to save the inspect file to the workspace (default) or to put the result on the console log

```
machinery_sut.show("tests-systemd", console=True) # name of your testsuite
```
