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

# Having to import twopence just in order to create a command
# is not so nice. So as a convenience, we import it here and
# make it available this way.
from twopence import Command

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

def requireResource(resourceName, resourceType = None, nodeName = None, **kwargs):
	TestDefinition.requireResource(resourceType, resourceName, nodeName, **kwargs)

def optionalResource(resourceName, resourceType = None, nodeName = None, **kwargs):
	TestDefinition.optionalResource(resourceType, resourceName, nodeName, **kwargs)

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
	# We need to return the test definition here so that
	#	@susetest.requires('foo')
	#	@susetest.test
	#	def bla(): ..
	# can work
	return TestDefinition.defineTestcase(f)

# susetest.requires decorator
# use this when a test case should be skipped unless a certain feature
# is present. Typical use case:
#
#  @susetest.requires('selinux')
#  def mytest(...)
def requires(name):
	def partial_req(tc):
		if not TestDefinition.isValidTestcase(tc):
			raise ValueError("@susetest.requires() only valid when preceding @susetest.test")

		tc.addRequires(name)
		return tc

	return partial_req

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

def template(name, *args, **kwargs):
	if name == 'selinux-verify-executable':
		templateSelinuxVerifyResource("executable", *args, **kwargs)
	else:
		raise ValueError("unknown template %s" % name)


def templateSelinuxVerifyResource(resourceType, resourceName, nodeName = None):
	def verify_exec_selinux(driver):
		node = None

		if nodeName is None:
			nodes = list(driver.targets)
			if len(nodes) == 1:
				node = nodes[0]
		else:
			node = getattr(driver, nodeName, None)

		if node is None:
			driver.testError("SELinux: cannot verify %s policy - don't know which SUT to pick" % resourceName)
			return

		selinux = driver.getFeature('selinux')
		selinux.resourceVerifyPolicy(node, resourceType, resourceName)

	f = verify_exec_selinux
	f.__doc__ = f"selinux.{resourceName}: verify that selinux policy is applied to {resourceName}"

	tc = TestDefinition.defineTestcase(f)
	tc.addOptionalResource(resourceName)
	tc.addRequires('selinux')

	TestDefinition.optionalResource(resourceType, resourceName, nodeName = nodeName)

	return tc

def verifySELinuxPolicy(node, resourceType, resourceName):
	executor = SELinux()
	executor.resourceVerifyPolicy(node, resourceType, resourceName)

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
