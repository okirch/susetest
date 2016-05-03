
Generic instructions on how to run tests based on twopence + susetest
=====================================================================

Twopence provides a generic layer for test scripts for communication with
nodes (SUT aka System Under Test). It is important to understand that in the
twopence model of operation, there is always an idependent control node that
orchestrates the test between the SUTs.

Where that control node resides, and what exactly it looks like, depends
on the environment you test in. If you test locally using KVM, then the
SUTs would be KVM guests and the control script would run on the host side.
If you run your tests under jenkins, then the SUTs might be VMs running in an
OpenStack clould while the control script runs on the jenkins host itself. In
an OpenQA environment, the control node might actually be in a separate VM.

The basic operations that twopence can provide are execution of commands,
as well as upload and download of files. So, a bit like what ssh will do for
you, except it's a bit more convenient to use and actually supports several
different modes of transport.  Twopence also provides shell commands as well
as a python and a ruby binding.

But, in a nutshell, twopence is the communication layer.

susetest sits on top of twopence and provides a convenience layer for test
scripts written in python.  Apart from offering a (small, so far) library of
helper functions, susetest provides logging facilities, and a simple interface
for constructing python objects for talking to the SUTs needed by your test.

Installing the required pieces
==============================

All packages that you need for this should be available from Devel:SLEnkins
in IBS. The test suites that make the most out of twopence and susetest are:
* twopence-{rpc,nfs,nis,... etc},  all suites from Olaf Kirch
* tests-salt, tests-tomcat, all suites from Dario Maiocchi.

In order to use them, install the
respective control package on your control node:

```
  rpm -ivh twopence-rpc-control
```
This should install the python script as well as the integration files for
jenkins - you want to install them even if you're not running under jenkins.

If you want to run the test suite on physical hardware (setting things up
manually), you don't need anything else. However, if you want to run the
suite under KVM, you need the slenkins-run package in addition.


Getting started
===============

Let's start with the simplest case of running a test on physical hardware.
Assume you have two physical machines, with IP addresses 192.168.10.1 and
192.168.10.2, which you want to use as client and server. Let's also assume
you have installed the target distribution you want to test, as well as all
the needed packages and SSH keys.

In order to run a susetest based script, you need two ingredients: a workspace,
and a runtime configuration file telling it how to talk to your test machines.

The workspace can be used by the script to create temporary files in, if
needed.  It will also store the test report in this directory when it's done.

In our example, the runtime configuration would look something like this:
```
  workspace "/tmp/twopence-rpc";
  node "server" {
      target       "ssh:192.168.10.1";
      ipv4_addr       "192.168.10.1";
  }
  node "client" {
      target       "ssh:192.168.10.2";
      ipv4_addr        "192.168.10.2";
  }
```
As you can see, this is a fairly trivial file format that uses key value
pairs and groups values into subsections using curly braces. For each of the
two SUT nodes, it defines two values, the target and the ipaddr. The target
is a string that is fed into twopence, and tells it how to connect to the
SUT. The ipaddr value informs the control script which address to use when
making the two SUTs talk to each other. Depending on where you run the test,
this address is not necessarily the same as the one used to reach it via SSH,
hence the need to two separate items.

If you store this file as ```/tmp/twopence-rpc/run.conf```, you need to point your
script to its location:
```
  export TWOPENCE_CONFIG_PATH="/tmp/twopence-rpc/run.conf"
```
With that, you're ready to execute the script:
```
  /usr/lib/twopence/rpc/run
```

General outline of the script
=============================

So, how does the script make use of the runtime configuration? And how
do you actually *do* anything within the script?

Let's look at the following snippet:
```
  import susetest

  config = susetest.Config("mytest")
  client = config.target("client")
  server = config.target("server")

  client.run("rpcinfo -p %s" % server.ipv4_addr)
```
This will read the runtime configuration file (it locates the file by checking
the TWOPENCE_CONFIG_PATH environment variable), and create python objects
for the two SUTs. Finally, it runs the rpcinfo command on the client two
show the RPC services registered on the server.

The name "mytest" provided to the Config() constructor doesn't carry a lot
of meaning right now. It is only used in the junit test report as the name
of the top level element.

Of course, this example misses a lot of things - it doesn't do sanity checks
on the targets obtained from the config object, it doesn't verify any results,
and it doesn't log any results. But that's something for later, for now it
should be enough to illustrate how runtime configuration and the execution
of commands are linked together.

Caveat: SSH Keys
================

If you configure twopence to use SSH to talk to the SUTs, you need
to ensure that you have the proper SSH keys. On the control node, you
can run the test script as any user you like - it doesn't need special
privilege. However, it needs access to an SSH private key that allows it
to log into the SUTs. On the back end, twopence uses libssh to talk to the
SUT's ssh daemon, which is a little bit limited in that it does not parse
.ssh/config to learn additional key files. Hence, the key needs to be in
one of the "standard" places understood by libssh, which is id_rsa, id_dsa,
id_ecdh or identity. Since few people use .ssh/identity any longer these days,
I found it most convenient to stick my ssh testing key into this file.

By default, you probably want to execute most commands on the SUT as root,
so the public part of your key needs to go into root's authorized_keys file.

However, if your test needs to execute unprivileged commands as well,
the suggested convention is to use the "testuser" account. Of course, this
means you also need to add the public portion of your SSH key to testuser's
authorized_keys file as well.


Running a susetest script on KVM or on slenkins
===============================================

The mechanics of this are still undergoing constant change.

For the time being, the best way to run susetest scripts under KVM and in
jenkins is probably using slenkins-run, but this is an interim solution only.

For more information, please refer to the slenkins-run package from
Devel:SLEnkins.


Putting susetest scripts into test automation
=============================================

In the description above, there were a lot of preratory steps we needed to
perform manually: provisioning the SUTs, installing packages, creating the
runtime configuration file, etc.

In a test automation framework, all of these steps need to be automated,
otherwise it's not test automation :-)

The actual provisioning of SUTs is out of scope for this document - this is
something that each automation framework will handle differently, but in a
uniform way for all test suites it executes.

However, for each test suite, there are steps that are specific to each suite:
how many hosts to deploy, which additional packages to install or update, etc.

This information is currently provided by the nodes file. The format and
semantics of this file are still a bit in flux, so don't be surprised if
things change a bit in the future.

Here's the nodes file from the twopence-rpc test suite:
```
	node      client
	install   tunctl
	install   twopence-rpc-client

	node      server
	install   rpcbind
	install   twopence-rpc-client
```
As you can see, this defines two nodes, named client and server, respectively.
For each of them, it lists a couple of packages than need to be installed.
This file needs to be installed below /var/lib/jenkins/testsuites for now,
because this is where the slenkins scripts will look for them. However,
this is subject to change. If the test suite is called twopence-rpc, then
the nodes file needs to go here:
```
  /var/lib/jenkins/testsuites/twopence-rpc/nodes
```
In addition, there needs to be a script inside this directory that is used
to run your python script, but we'll not go into this here - normally,
a symlink pointing back ```/usr/lib/twopence/rpc/run``` would be all it takes.

Currently, the nodes file is used only by jenkins and the scripts around it,
but I would expect a future OpenQA integration to use the same conventions.
we should then consider to move the nodes file out of /var/lib/jenkins and
into a more generic location.


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

