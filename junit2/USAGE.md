# Producing JUnit output from your tests #


## Presentation ##

Jenkins can provide summaries of your test results, taking
[JUnit XML result files](http://llg.cubic.org/docs/junit/) as input.

To make things easier, we have introduced a plain text format
that your tests can produce. This format will get converted
automatically to JUnit XML result format without any need for
you to deal with XML tags.

This format can be intermingled with the normal output of your
tests. Only the lines starting with `###junit` will be processed,
all other lines will be stored "as is" in the JUnit XML results.

To make things even easier, assuming that your test script is
written in bash, we also provide a script named `jlogger.sh` that
can help you generate more easily these log entries.
test cases can be written in any programming language, and the
use of this script is optional.

In Jenkins, the text output by your script will be converted
into JUnit XML result by a program named `to_junit`, then
exported on the Jenkins web site.


## The helper script ##

The helper script `jlogger.sh` produces the desired log entries
from a shell command line.

It has normally be installed on the ISO image that you will
use to create the system under tests, so it should be available
with no further installation.

### Example ###

	jlogger.sh testsuite -t "Testing the calculator functions"

	jlogger.sh testcase -t "verify addition"
	jlogger.sh success

	jlogger.sh testcase -t "verify division"
	jlogger.sh failure -T "Segmentation failure"

	jlogger.sh endsuite

These calls can be mixed with normal output, that will simply
be stored unchanged when converted to real JUnit XML result
syntax

### Basic syntax ###

	jlogger.sh testsuite [-i <identifier>] [-t <text>] [-h <hostname>]
	  start test suite

	jlogger.sh endsuite
	  end test suite

	jlogger.sh testcase [-i <identifier>] [-t <text>]
	  start test case

	jlogger.sh success
	  end succesful test case

	jlogger.sh failure [-T <type>] [-t <text>]
	  end failed test case

	jlogger.sh error [-T <type>] [-t <text>]
	  end test case aborted due to internal error

### testsuite keyword ###

	jlogger.sh testsuite [-i <identifier>] [-t <text>] [-h <hostname>]

Start the test suite.

`-i` introduces an arbitrary identifier for the test suite.
It is ignored by Jenkins, so there is not much point in using it.

`-t` introduces a text describing the test suite.

`-h` introduces the name of the host the test suite is run on.

### endsuite keyword ###

	jlogger.sh endsuite

End the test suite.

### testcase keyword ###

	jlogger.sh testcase [-i <identifier>] [-t <text>]

Start a test case.

`-i` introduces an arbitrary identifier for the test case. Jenkins
works best with dotted syntax. In Java world, that would be something
of the form `package.class.method`.

`-t` introduces a text describing the test suite.

### success keyword ###

	jlogger.sh success

Marks the successful end of a test case.

### failure keyword ###

	jlogger.sh failure [-T <type>] [-t <text>]

Marks the end of a test case that did not provide the
expected results.

`-T` introduces an error type. It could be the name of an
exception.

`-t` introduces an error message.

### error keyword ###

	jlogger.sh error [-T <type>] [-t <text>]

Marks the end of a test case that could not be run because
of an internal error in the test suite.

`-T` introduces an error type. It could be the name of an
exception.

`-t` introduces an error message.


## The text output ##

You don't necessarily use= `jlogger.sh` to produce the
needed text output. Any programming language that
can output text will do. Below is what your test script
should produce.

### Basic output syntax ###

The basic syntax of the text produced by your script
is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
     <th>Text</th>
     <th>Meaning</th>
     <th>JUnit mapping</th>
  </tr>
  <tr>
     <td>`###junit testsuite`</td>
     <td>Start a new series of tests</td>
     <td>`<testsuite>`</td>
  </tr>
  <tr>
     <td>`###junit endsuite`</td>
     <td>End up current series of tests</td>
  </tr>
  <tr>
     <td>`###junit testcase`</td>
     <td>Start new test case</td>
     <td>`<testcase>`</td>
  </tr>
  <tr>
     <td>`###junit success`</td>
     <td>End up current test case as successful</td>
  </tr>
  <tr>
     <td>`###junit failure`</td>
     <td>End up current test case as failed</td>
     <td>`<failure>`</td>
  </tr>
  <tr>
     <td>`###junit error`</td>
     <td>End up current test case as aborted because of an internal error</td>
     <td>`<error>`</td>
  </tr>
</table>

### Example ###

Here is how the output of your test program could look like:

	Calculator test suite
	Written by Hans Mustermann, <hmustermann@suse.com>
	Version 0.11, last modified 2015-01-05
	
	###junit testsuite time="2015-01-16T17:30:37.655" text="Testing the calculator functions"
	
	###junit testcase time="2015-01-16T17:30:37.655" text="verify addition"
	Additions. Let's try 5 + 3...
	Works! Got 8.
	###junit success time="2015-01-16T17:30:37.655"
	
	###junit testcase time="2015-01-16T17:30:37.655" text="verify division"
	Array operations. Let's try A[-1] = 5...
	Ouch! Got Segmentation failure, expected Out of bounds.
	###junit failure time="2015-01-16T17:30:37.656" type="Segmentation failure"
	
	###junit endsuite time="2015-01-16T17:30:37.656"
	
	Goodbye!

### Conformance ###

Since JUnit normally refers to Java testing, the semantics of a few fields
is abused. For example, `text=""` text, which we use for an arbitrary description,
maps to JUnit `name=""` attribute, which normally refers to a Java class name.

Still, the result is guaranteed to validate against `JUnit.xsd` schema.


## Syntax details ##

Below are detailed the already supported options, all with syntax
`name="value"`.

Note that embedded quotes are legal. For example,

	###junit testsuite text="Tests for "Calculator" program"

with embedded quotes around `"Calculator"` is legal.
It is not needed (nor possible) to escape the embedded quotes.

To accomodate for future extensions, unrecognized text is simply ignored.

### testsuite ###

Your test program should output `###junit testsuite` text first,
to introduce a new series of test cases.
Use it as many times as you have different test suites.

The text following `###junit testsuite` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of beginning of test suite run</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
    <td>`timestamp=""`</td>
  </tr>
  <tr>
    <td>`id=""`</td>
    <td>identifier for the test suite</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`package=""`</td>
  </tr>
  <tr>
    <td>`text=""`</td>
    <td>any text describing the test suite</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`name=""`</td>
  </tr>
  <tr>
    <td>`host=""`</td>
    <td>name of host where the suite is run</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`localhost`</td>
    <td>`hostname=""`</td>
  </tr>
</table>

`id=""` is ignored by Jenkins.

### endsuite ###

After a series of related test cases,
your test program should output `###junit endsuite`.

The text following `###junit endsuite` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of end of test suite run</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
    <td>`time=""` (test suite duration in seconds)</td>
  </tr>
</table>

The following JUnit XML attributes and tags are generated automatically:
<br><br />
<table border="1" cellpadding="4">
  <tr>
    <th>JUnit XML</th>
    <th>Meaning</th>
  </tr>
  <tr>
    <td>`id=""`</td>
    <td>Serial number of this test suite, starting at `0`</td>
  </tr>
  <tr>
    <td>`tests=""`</td>
    <td>Number of test cases in the suite</td>
  </tr>
  <tr>
    <td>`failures=""`</td>
    <td>Number of failed test cases in the suite</td>
  </tr>
  <tr>
    <td>`errors=""`</td>
    <td>Number of test cases in the suite that have aborted due to internal errors</td>
  </tr>
  <tr>
    <td>`<system-err>`</td>
    <td>Dump of stderr output</td>
  </tr>
</table>

### testcase ###

When it starts a new test case as part of a test suite,
your test program should output `###junit testcase`.

The text following `###junit testcase` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of beginning of test case</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
  </tr>
  <tr>
    <td>`id=""`</td>
    <td>identifier for the test case</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`classname=""`</td>
  </tr>
  <tr>
    <td>`text=""`</td>
    <td>any text describing the test suite</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`name=""`</td>
  </tr>
</table>

Jenkins works best with an identifier in dotted syntax.
In Java world, that would be something of the form `package.class.method`.

### success ###

When the current test case succeeds (that is, the tested software behaved
as expected), your test program should output `###junit success`.

The text following `###junit success` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of end of test case run</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
    <td>`time=""` (test case duration in seconds)</td>
  </tr>
</table>

### failure ###

When the current test case failed (that is, the tested software did not behave
as expected), your test program should output `###junit failure` and provide
some diagnostic.

The text following `###junit failure` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of end of test case run</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
    <td>`time=""` (test case duration in seconds)</td>
  </tr>
  <tr>
    <td>`type=""`</td>
    <td>type of failure</td>
    <td>[xs:string](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`randomError`</td>
    <td>`type=""`</td>
  </tr>
  <tr>
    <td>`text=""`</td>
    <td>failure message</td>
    <td>[xs:string](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`message=""`</td>
  </tr>
</table>

The `<failure>` tag in the output also contains a dump of stderr.

### error ###

When the test case itself was not able to complete, because of an
internal error, your test program should output `###junit error` and provide
some diagnostic.

The text following `###junit error` on the same line is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
    <th>Text</th>
    <th>Meaning</th>
    <th>Syntax</th>
    <th>Default</th>
    <th>JUnit mapping</th>
  </tr>
  <tr>
    <td>`time=""`</td>
    <td>date and time of end of test case run</td>
    <td>[ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) with milliseconds</td>
    <td>`1970-01-01T00:00:00.000`</td>
    <td>`time=""` (test case duration in seconds)</td>
  </tr>
  <tr>
    <td>`type=""`</td>
    <td>type of error</td>
    <td>[xs:string](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`randomError`</td>
    <td>`type=""`</td>
  </tr>
  <tr>
    <td>`text=""`</td>
    <td>error message</td>
    <td>[xs:string](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`(unknown)`</td>
    <td>`message=""`</td>
  </tr>
</table>

The `<error>` tag in the output also contains a dump of stderr.

<!-- vim: ts=4 syntax=markdown
-->
