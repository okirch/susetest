#!/usr/bin/perl
#
# Perl module to generate JUnit XML
#
# This should be part of the general suse-testing tool box.
#
# Copyright (C) 2014 Olaf Kirch <okir@suse.de>
#


package JUnit;
use strict;
use XML::DOM;

our $trace = 0;

our $SUCCESS	= 'success';
our $FAILED	= 'failed';
our $ERROR	= 'error';

sub loadReport {

	my $file = shift;

	my $parser = new XML::DOM::Parser;
	my $doc = $parser->parsefile($file) or

	die "JUnit::loadReport() not implemented yet\n";
}

sub __maybeSetAttribute {

	my $node = shift;
	my $name = shift;
	my $value = shift;

	$node->setAttribute($name, $value) if ($value);
}

1;

package Report;
use strict;

sub new {
	my $class = shift;
	my $file = shift;

	my $self = {};

	$self->{'filename'} = $file;
	$self->{'package'} = undef;
	$self->{'numtests'} = 0;
	$self->{'numfailed'} = 0;
	$self->{'numerrors'} = 0;
	@{ $self->{'tests'} } = ();

	bless($self, $class);
	return $self;
}

sub filename {
	my $self = shift;
	return $self->{'filename'};
}

sub hostname {
	my $self = shift;

	$self->{'hostname'} = shift if (@_);
	return $self->{'hostname'};
}

sub timestamp {
	my $self = shift;

	$self->{'timestamp'} = shift if (@_);
	return $self->{'timestamp'};
}

sub systemout {
	my $self = shift;

	while (@_) {
		$self->{'systemout'} .= shift;
	}
	return $self->{'systemout'};
}

sub systemerr {
	my $self = shift;

	while (@_) {
		$self->{'systemerr'} .= shift;
	}
	return $self->{'systemerr'};
}

sub numtests {
	my $self = shift;
	return $self->{'numtests'};
}

sub numfailures {
	my $self = shift;
	return $self->{'numfailed'};
}

sub numerrors {
	my $self = shift;
	return $self->{'numerrors'};
}

sub package {
	my $self = shift;

	if (@_) {
		$self->{'package'} = shift;
	}
	return $self->{'package'};
}

sub addResult {
	my $self = shift;

	my $testcase = Testcase->new(@_);
	$self->appendTestcase($testcase);
	return $testcase;
}

sub appendTestcase {
	my $self = shift;

	foreach my $tc (@_) {
		$tc->package($self->package());
		if ($tc->result() eq $SUCCESS) {
			# nothing
		} elsif ($tc->result() eq $FAILED) {
			$self->{'numfailed'} += 1;
		} else {
			$self->{'numerrors'} += 1;
		}
		$self->{'numtests'} += 1;
		push (@{ $self->{'tests'} }, $tc);
	}
}

sub testcases {
	my $self = shift;

	return @{ $self->{'tests'} };
}

sub save {
	my $self = shift;

	my $doc = XML::DOM::Document->new();
	my $root = $doc->createElement('testsuite');
	$doc->appendChild($root);

	JUnit::__maybeSetAttribute($root, 'package', $self->package());
	JUnit::__maybeSetAttribute($root, 'timestamp', $self->timestamp());
	JUnit::__maybeSetAttribute($root, 'hostname', $self->hostname());
	$root->setAttribute('tests', $self->numtests());
	$root->setAttribute('errors', $self->numerrors());
	$root->setAttribute('failures', $self->numfailures());

	foreach my $tc ($self->testcases()) {
		my $node = $doc->createElement('testcase');
		my $child;

		$node->setAttribute('name', $tc->name());
		JUnit::__maybeSetAttribute($node, 'classname', $tc->classname());
		JUnit::__maybeSetAttribute($node, 'time', $tc->duration());
		$root->appendChild($node);

		if ($tc->result() eq $FAILED) {
			$child = $doc->createElement('failure');
			$child->setAttribute('type', 'randomError');
			if ($tc->message()) {
				$child->setAttribute('message', $tc->message());
			}
			if ($tc->output()) {
				$child->appendChild($doc->createCDATASection($tc->output()));
			}
			$node->appendChild($child);
		}
	}

	if ($self->systemout()) {
		my $node = $doc->createElement('system-out');
		$node->appendChild($doc->createCDATASection($self->systemout()));
		$root->appendChild($node);
	}

	$doc->printToFile($self->filename());
}

package Testcase;
use strict;

sub new {
	my $class = shift;
	my $name = shift;
	my $desc = shift;
	my $result = shift;
	my $pkg;

	my $self = {};

	# if the name is foo.bar.baz, make "foo" the package name
	if ($name =~ m:([^.]*)\.([.a-zA-Z_0-9]*):o) {
		$pkg = $1;
		$name = $2;
	}

	$self->{'name'} = $name;
	# This is a bit of an abuse - we use the @classname attribute to store
	# a short description of the test case
	$self->{'classname'} = $desc;
	$self->{'result'} = $result;
	$self->{'package'} = $pkg;
	$self->{'timestamp'} = undef;
	$self->{'duration'} = undef;

	bless($self, $class);
	return $self;
}

sub getset {

	my $name = shift;
	my $self = shift;

	if (@_) {
		$self->{$name} = shift;
	}
	return $self->{$name};
}

sub name {
	return getset('name', @_);
}

sub classname {
	return getset('classname', @_);
}

sub result {
	return getset('result', @_);
}

sub package {
	return getset('package', @_);
}

sub timestamp {
	return getset('timestamp', @_);
}

sub duration {
	return getset('duration', @_);
}

sub message {
	return getset('message', @_);
}

sub output {
	return getset('output', @_);
}
