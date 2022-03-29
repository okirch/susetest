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
from .application import Application

# Having to import twopence just in order to create a command
# is not so nice. So as a convenience, we import it here and
# make it available this way.
from twopence import Command

from twopence import Exception as TwopenceException

def say(msg):
	print(msg)
	sys.stdout.flush()

class CriticalResourceMissingError(TwopenceException):
	pass

# FIXME: deprecate this in favor of the new prediction support
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

def group_resource(f):
	@functools.wraps(f)
	def wrapper(*args, **kwds):
		print('Setting up group resource %s' % f)
		return f(*args, **kwds)

	print("Attaching group resource %s" % f)
	return wrapper

def requireResource(resourceName, resourceType = None, nodeName = None, **kwargs):
	TestDefinition.requireResource(resourceType, resourceName, nodeName, **kwargs)

def requireExecutable(resourceName, nodeName = None, **kwargs):
	TestDefinition.requireResource('executable', resourceName, nodeName, **kwargs)

def optionalResource(resourceName, resourceType = None, nodeName = None, **kwargs):
	TestDefinition.optionalResource(resourceType, resourceName, nodeName, **kwargs)

# You can use the following to annotate individual test cases. If the specified resource
# not available, the test is skipped automatically.
#
# @susetest.test
# @susetest.optionalTestResource('executable', 'fancycommand')
# def test_fancycommand(driver):
#	...
#
# The order of decorators is not significant; you should also be able to swap the
# two decorators in the above example.
def optionalTestResource(resourceType, resourceName, nodeName = None):
	def wrapper(f):
		TestDefinition.optionalTestResource(f, resourceType, resourceName, nodeName)
		return f

	return wrapper

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
			driver.skipTest()
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
	elif name == 'verify-file':
		return templateVerifyFile(*args, **kwargs)
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
	tc.addOptionalResource(resourceType, resourceName, nodeName)
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
	tc.addOptionalResource('executable', resourceName, nodeName)

	TestDefinition.optionalResource("executable", resourceName, nodeName = nodeName)

	return tc

def templateVerifyFile(resourceName, nodeName = None, **kwargs):
	def verify_file(driver):
		node = getTargetForTemplate(driver, nodeName)
		if node is None:
			driver.testError(f"Cannot verify file {resourceName} - don't know which SUT to pick")
			return

		user = driver.client.requireUser("test-user")
		if not user.uid:
			node.logError("user %s does not seem to exist" % user.login)
			return

		file = node.requireFile(resourceName)
		print(f"resource {file} DAC user={file.dac_user} group={file.dac_group} permissions={file.dac_permissions}")

		if not file.dac_user and \
		   not file.dac_group and \
		   not file.dac_permissions:
			node.logInfo(f"resource {file} does not define any DAC information")
			driver.skipTest()
			return

		info = file.stat()
		if info is None:
			node.logFailure(f"Unable to obtain user/group info for resource {resourceName} (path={file.path})")
			return

		okay = True
		if file.dac_user and file.dac_user != info.user:
			node.logFailure(f"Bad owner for {file.path}: expected {file.dac_user} but found {info.user}")
			okay = False
		if file.dac_group and file.dac_group != info.group:
			node.logFailure(f"Bad group for {file.path}: expected {file.dac_group} but found {info.group}")
			okay = False
		if file.dac_permissions and file.dac_permissions != info.permissions:
			node.logFailure(f"Bad permissions for {file.path}: expected {file.dac_permissions} but found {info.permissions}")
			okay = False

		if not okay:
			return

		node.logInfo(f"OK, {file.path} has expected protection")

	testid = resourceName.replace("-", "_")

	f = verify_file
	f.__doc__ = f"general.{testid}: verify DAC permissions for file resource {resourceName}"

	tc = TestDefinition.defineTestcase(f)
	tc.addOptionalResource('file', resourceName, nodeName)

	TestDefinition.optionalResource("file", resourceName, nodeName = nodeName)

	return tc

# Called by the user at the top of a test script when they wish to
# use libraries provided eg by farthings
#
#	susetest.enable_libdir()
#	from farthings.openssl_pki import PKI
#
def enable_libdir():
	import twopence.paths
	import sys

	sys.path.append(twopence.paths.test_lib_dir)

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
