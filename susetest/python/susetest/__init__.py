##################################################################
#
# Python classes for susetest
#
# Copyright (C) 2014-2021 SUSE Linux GmbH
#
##################################################################

import suselog
import time
import re
import sys
import os
import functools

from .target import Target
from .driver import Driver
from .testdef import TestDefinition

def say(msg):
	print(msg)
	sys.stdout.flush()

# This class is needed for break a whole testsuite, exit without run all tests. Wanted in some scenarios.
# Otherwise we can use susetest.finish(journal) to continue after  failed tests, 
class SlenkinsError(Exception):
	def __init__(self, code):
		self.code = code

	def __str__(self):
		return repr(self.code)

# Same for basiliqa
class BasiliqaError(Exception):
	def __init__(self, code):
		self.code = code

	def __str__(self):
		return repr(self.code)

# finish the junit report.
def finish(journal):
	journal.writeReport()
	if (journal.num_failed() + journal.num_errors()):
			sys.exit(1)
	sys.exit(0)

def group_resource(f):
	@functools.wraps(f)
	def wrapper(*args, **kwds):
		print('Setting up group resource %s' % f)
		return f(*args, **kwds)

	print("Attaching group resource %s" % f)
	return wrapper

def requireResource(*args, **kwargs):
	TestDefinition.requireResource(*args, **kwargs)

def optionalResource(*args, **kwargs):
	TestDefinition.optionalResource(*args, **kwargs)

# susetest.resource decorator
def resource(klass):
	TestDefinition.defineResource(klass)
	return klass

# susetest.setup decorator
def setup(f):
	TestDefinition.defineSetup(f)
	return f

# susetest.group decorator
def group(f):
	print("Defining group function %s (%s)" % (f, f.__doc__))
	TestDefinition.defineGroup(f)
	return f

# susetest.test decorator
def test(f):
	TestDefinition.defineTestcase(f)
	return f

def define_parameterized(testfn, *args):
	@functools.wraps(testfn)
	def wrapper(driver):
		_args = driver.expandArguments(args)
		if _args is None:
			driver.logInfo("argument list %s expanded to None" % (args,))
			driver.journal.skipped()
			return

		testfn(driver, _args)

	wrapper.__doc__ = testfn.__doc__.replace("@ARGS", " ".join(args))
	TestDefinition.defineTestcase(wrapper)

# Called by the user at the end of a test script, like this
#
#  if __name == '__main__':
#	susetest.perform()
#
# For this to work, the user needs to define one or more functions
# as test cases, and decorate these using @susetest.test
#
def perform():
	TestDefinition.perform()
