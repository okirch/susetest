# Producing JUnit output from your tests #

## Presentation ##

Jenkins can provide summaries of your test results, taking
[JUnit XML result files](http://llg.cubic.org/docs/junit/) as input.

To make things easier, we have introduced a plain text format
that your tests can produce. This format will get converted
automatically to JUnit XML result format without any need for
you to deal with XML tags.

### Basic syntax ###

This format can be intermingled with the normal output of your
tests. Only the lines starting with `####junit` will be processed,
all other lines will be ignored.

The basic syntax is as follows:
<br></br>
<table border="1" cellpadding="4">
  <tr>
     <th>Text</th>
     <th>Meaning</th>
     <th>Junit mapping</th>
  </tr>
  <tr>
     <td>`####junit testsuite`</td>
     <td>Start a new series of tests</td>
     <td>`<testsuite>`</td>
  </tr>
  <tr>
     <td>`####junit endsuite`</td>
     <td>End up current series of tests</td>
  </tr>
  <tr>
     <td>`####junit testcase`</td>
     <td>Start new test case</td>
     <td>`<testcase>`</td>
  </tr>
  <tr>
     <td>`####junit success`</td>
     <td>End up current test case as successful</td>
  </tr>
  <tr>
     <td>`####junit failure`</td>
     <td>End up current test case as failed</td>
     <td>`<failure>`</td>
  </tr>
  <tr>
     <td>`####junit error`</td>
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

### Conformance ####

Since JUnit normally refers to Java testing, the semantics of a few fields
is abused. For example, `text=""` text, which we use for an arbitrary description,
maps to JUnit `name=""` attribute, which normally refers to a Java class name.

Still, the result is guaranteed to validate against `JUnit.xsd` schema.


## Syntax details ##

Below are detailed the already supported options, all with syntax
`name="value"`.

Note that embedded quotes are legal. For example,

	####junit testsuite text="Tests for "Calculator" program"

with embedded quotes around `"Calculator"` is legal.
It is not needed (nor possible) to escape the embedded quotes.

To accomodate for future extensions, unrecognized text is simply ignored.

### testsuite ###

Your test program should output `####junit testsuite` text first,
to introduce a new series of test cases.
Use it as many times as you have different test suites.

The text following `####junit testsuite` on the same line is as follows:
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
    <td>any text describing the test suite</td>
    <td>[xs:token](http://www.w3schools.com/schema/schema_dtypes_string.asp)</td>
    <td>`localhost`</td>
    <td>`hostname=""`</td>
  </tr>
</table>

### endsuite ###

After a series of related test cases,
your test program should output `####junit endsuite`.

The text following `####junit endsuite` on the same line is as follows:
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
your test program should output `####junit testcase`.

The text following `####junit testcase` on the same line is as follows:
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

### success ###

When the current test case succeeds (that is, the tested software behaved
as expected), your test program should output `####junit success`.

The text following `####junit success` on the same line is as follows:
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
as expected), your test program should output `####junit failure` and provide
some diagnostic.

The text following `####junit failure` on the same line is as follows:
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
internal error, your test program should output `####junit error` and provide
some diagnostic.

The text following `####junit error` on the same line is as follows:
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
