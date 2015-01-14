
import suselog

journal = suselog.Journal("mytest");

journal.beginGroup("foobar", "This test group validates the foobar group of functions");

journal.beginTest("fooInit")
journal.success();

journal.beginTest("fooSetState")
journal.failure("unable to set foo state");

journal.finishGroup();
journal.writeReport("test-report.xml");
