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

from twopence import Exception as TwopenceException

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

class CriticalResourceMissingError(TwopenceException):
	pass

class ExpectedCommandResult:
	def __init__(self, cmdname):
		self.cmdname = cmdname

class ExpectedCommandSuccess(ExpectedCommandResult):
	def verify(self, st):
		node = st.target

		if not st:
			node.logFailure(f"{self.cmdname} command failed: {st.message}")
			return False

		return True

class ExpectedCommandFailure(ExpectedCommandResult):
	def verify(self, st):
		node = st.target

		if st:
			node.logFailure(f"{self.cmdname} command succeeded (expected error)")
			return False

		node.logInfo(f"{self.cmdname} command failed as expected: {st.message}")
		return True

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
		return templateSelinuxVerifyResource("executable", *args, **kwargs)
	elif name == 'selinux-verify-file':
		return templateSelinuxVerifyResource("file", *args, **kwargs)
	elif name == 'selinux-verify-package':
		return templateSelinuxVerifyResource("package", *args, **kwargs)
	elif name == 'selinux-verify-subsystem':
		return templateSelinuxVerifyResource("subsystem", *args, **kwargs)
	elif name == 'verify-executable-no-args':
		args = list(args)
		resourceName = args.pop(0)
		return templateVerifyExecutable(resourceName, [], *args, **kwargs)
	elif name == 'verify-executable':
		return templateVerifyExecutable(*args, **kwargs)
	else:
		raise ValueError("unknown template %s" % name)

def getTargetForTemplate(driver, nodeName):
	if nodeName is None:
		nodes = list(driver.targets)
		if len(nodes) == 1:
			return nodes[0]
	else:
		return getattr(driver, nodeName, None)

	return None


def templateSelinuxVerifyResource(resourceType, resourceName, nodeName = None):
	def verify_exec_selinux(driver):
		node = getTargetForTemplate(driver, nodeName)
		if node is None:
			driver.testError("SELinux: cannot verify %s policy - don't know which SUT to pick" % resourceName)
			return

		selinux = driver.getFeature('selinux')
		if not selinux:
			driver.testError("SELinux: cannot get handle for feature 'selinux'")
			say(driver._features)
			return

		selinux.resourceVerifyPolicy(node, resourceType, resourceName)

	f = verify_exec_selinux
	f.__doc__ = f"selinux.{resourceName}: verify that selinux policy is applied to {resourceName}"

	tc = TestDefinition.defineTestcase(f)
	tc.addOptionalResource(resourceName)
	tc.addRequires('selinux')

	TestDefinition.optionalResource(resourceType, resourceName, nodeName = nodeName)

	return tc

def templateVerifyExecutable(resourceName, arguments, nodeName = None, **kwargs):
	def verify_executable(driver):
		node = getTargetForTemplate(driver, nodeName)
		if node is None:
			driver.testError(f"Cannot verify executable {resourceName} - don't know which SUT to pick")
			return

		user = driver.client.requireUser("test-user")
		if not user.uid:
			node.logError("user %s does not seem to exist" % user.login)
			return

		executable = node.requireExecutable(resourceName)
		command = executable.path
		if arguments:
			command += " " + arguments
		st = node.run(command, user = user.login, **kwargs)
		if not st:
			node.logFailure(f"{command} failed: {st.message}")
			return

		node.logInfo(f"OK, {command} works")

	arguments = " ".join(arguments)

	command = f"{resourceName} {arguments}"
	testid = command.replace(" ", "").replace("-", "_").replace("/", "_")

	f = verify_executable
	f.__doc__ = f"general.{testid}: verify that test user can invoke executable {command}"

	tc = TestDefinition.defineTestcase(f)
	tc.addOptionalResource(resourceName)

	TestDefinition.optionalResource("executable", resourceName, nodeName = nodeName)

	return tc


# Called by the user at the end of a test script, like this
#
#  if __name__ == '__main__':
#	susetest.perform()
#
# For this to work, the user needs to define one or more functions
# as test cases, and decorate these using @susetest.test
#
def perform():
	TestDefinition.perform()
