##################################################################
#
# Python classes for susetest: test case and group definitions
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################

import twopence
import time
import re
import sys
import os
import functools

from .target import Target
from .driver import Driver
import susetest

class Name:
	_re = None

	def __init__(self, group = None, case = None):
		self.group = group
		self.case = case

	@staticmethod
	def parse(s):
		words = Name._split(s)
		if words is None:
			return None
		if len(words) == 2:
			return Name(*words)
		return Name(case = words[0])

	@staticmethod
	def parseMatch(s):
		words = Name._split(s, wildcardOkay = True)
		if words is None:
			return None
		if len(words) == 1:
			words.append('*')
		return Name(*words)

	@staticmethod
	def _split(s, wildcardOkay = False):
		if not s:
			return None

		words = s.split('.')
		if len(words) > 2:
			return None

		if not Name._re:
			Name._re = re.compile("[-a-z0-9_]+$", re.IGNORECASE)

		if wildcardOkay:
			check = lambda s: (s == "*" or Name._re.match(s))
		else:
			check = Name._re.match
		if any(not check(_) for _ in words):
			return None

		return words

	def __str__(self):
		return "Name(group = %s, case = %s)" % (self.group, self.case)

class NameMatcher:
	def __init__(self, id, context):
		self.name = Name.parseMatch(id)
		if self.name is None:
			raise ValueError("Cannot parse %s %s" % (context, id))

	def matchGroup(self, name):
		return self.name.group == "*" or self.name.group == name

	def matchTestcase(self, name):
		return self.name.case == "*" or self.name.case == name

	@property
	def matchAllTestcases(self):
		return self.name.case == '*'

	def __str__(self):
		return "Matcher(%s)" % self.name

class ResourceRequirement:
	def __init__(self, resourceType, resourceName, nodeName = None, mandatory = False):
		self.resourceType = resourceType
		self.resourceName = resourceName
		self.nodeName = nodeName
		self.mandatory = mandatory

	def request(self, driver):
		result = driver.acquireResource(self.resourceType, self.resourceName, self.nodeName, mandatory = self.mandatory)
		if type(result) == list:
			return all(res.is_active for res in result)
		return result.is_active

	def __str__(self):
		if self.mandatory:
			return f"ResourceRequirement({self.resourceType} {self.resourceName})"
		return f"ResourceRequirement(optional {self.resourceType} {self.resourceName})"

	@property
	def testID(self):
		return "resource-acquire:%s:%s:%s:%s" % (
			self.nodeName,
			self.mandatory and "mandatory" or "optional",
			self.resourceType,
			self.resourceName
			)

class TestCase:
	pass

class TestCaseDefinition(TestCase):
	def __init__(self, f):
		self.f = f
		self.name = None
		self.group = None
		self.description = "(no description)"
		self.skip = False
		self.requires = []
		self.unmetRequirements = []
		self.resources = []

		if not callable(f):
			raise ValueError("Don't know how to handle test defined by %s" % type(f))

		doc = f.__doc__
		if doc:
			m = re.match("([^:]*): *(.*)", doc)
			if m is not None:
				n = Name.parse(m.group(1))
				if n:
					# susetest.say("found name %s" % n)
					self.group = n.group
					self.name = n.case
					self.description = m.group(2)

		if not self.group:
			self.group = f.__module__

		if not self.name:
			self.name = f.__name__

		if not self.description:
			self.description = doc

	def addRequires(self, name):
		self.requires.append(name)

	def addResource(self, req):
		self.resources.append(req)

	def addOptionalResource(self, *args, **kwargs):
		self.addResource(ResourceRequirement(*args, **kwargs))

	def lackingRequirements(self, driver):
		result = set()

		for name in self.requires:
			for node in driver.targets:
				if name not in node.features:
					result.add(name)

		return result

	def verifyResources(self, driver):
		for req in self.resources:
			if not req.request(driver):
				return False
		return True

	def __str__(self):
		return "TestCase(%s.%s, \"%s\")" % (
				self.group or "default",
				self.name,
				self.description or "")

	def __call__(self, *args, **kwargs):
		return self.f(*args, **kwargs)

class TestGroupDef:
	def __init__(self, name):
		self.name = name
		self._setup = None
		self.tests = []
		self.skip = False

	@property
	def setup(self):
		return self._setup

	@setup.setter
	def setup(self, f):
		if self._setup:
			raise ValueError("Duplicate definition of susetest.setup")
		self._setup = f

	@property
	def empty(self):
		return not(self._setup) and not(self.tests)

	def add(self, tc):
		self.tests.append(tc)

	def getTest(self, name):
		for tc in self.tests:
			if tc.name == name:
				return tc
		return None

class GroupInitWrapper:
	def __init__(self, group):
		self.group = group
		self.name = "setup-resources"
		self.description = group.setup.__doc__
		self.skip = False

	def verifyResources(self, driver):
		return True

	def __call__(self, driver):
		self.group.setup(driver)

class TestsuiteInfo:
	_instance = None

	def __init__(self, name = None):
		self._groups = {}
		self.testResources = {}

		self.setup = None

		# If the caller did not specify a name, we try to guess one.
		# - if we were invoked as somepath/NAME/run, we use NAME
		if name is None:
			import inspect

			caller_frame = inspect.stack()[-1]
			script = caller_frame.filename

			(dir, file) = os.path.split(caller_frame.filename)
			(dir, parent) = os.path.split(dir)
			if file == 'run' and not parent.startswith('.'):
				name = parent

			assert(name)

		self._name = name

		# If the test comes with its own resources.conf file, load it now
		self.loadTestResources(name)

		# List of resource requirements
		# Scripts can specify these via
		#  susetest.requireResource("foo", [node = "client"])
		#  susetest.optionalResource("bar")
		self._resources = []

		# Ensure that the first group is always the one defined
		# in the calling script, even if that script imports
		# other files that define additional test cases
		self.createGroup(self._name)

		self._currentGroup = None
		self._failing = False

	@classmethod
	def instance(klass):
		if klass._instance is None:
			klass._instance = klass()
		return klass._instance

	@property
	def empty(self):
		return all(_.empty for _ in self.groups)

	@property
	def name(self):
		return self._name

	# Most test cases come with their own resource definitions
	def loadTestResources(self, name):
		if name in self.testResources:
			return

		info = twopence.TestBase().findTestCase(name)
		if info is None:
			twopence.error(f"Unable to find test case {name}")
			return

		if info.resources is None:
			if name != self._name:
				# We end up here when called via susetest.loadTestResources
				twopence.warning(f"Test case {name} does not specify any resources")
			return

		twopence.verbose(f"Using {name} test resources from {info.resources}")
		self.testResources[name] = info.resources

	@property
	def groups(self):
		return self._groups.values()

	def getGroup(self, name):
		return self._groups.get(name)

	def createGroup(self, name):
		if name == '__main__':
			name = self._name

		group = self._groups.get(name)
		if not group:
			group = TestGroupDef(name)
			self._groups[name] = group
		return group

	def requireResource(self, resourceType, resourceName, nodeName = None):
		self._resources.append(ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = True))

	def optionalResource(self, resourceType, resourceName, nodeName = None):
		self._resources.append(ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = False))

	def requireTestResource(self, test, resourceType, resourceName, nodeName = None):
		self.addTestResource(test, ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = True))

	def optionalTestResource(self, test, resourceType, resourceName, nodeName = None):
		self.addTestResource(test, ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = False))

	# This function and the next are used to handle ordering of decorators before
	# test functions. Example:
	#   @susetest.test
	#   @susetest.optionalTestResource('executable', 'verify_password')
	#   def testfunc(driver):
	#	...
	# In this case, optionalTestResource is called first, and is supposed to return
	# a wrapper function. That wrapper function is then invoked with testfunc
	# as its single argument. So at this point in time, we do not have a TestCaseDefinition
	# yet to which we could attach the resource requirement. As a stopgap measure,
	# we add a _twopence_magic_resources member to the function which is used
	# to hold the resource requirement(s). We then return testfunc to the caller.
	#
	# When susetest.test is invokved, it receives the function testfunc,
	# and does its usual stuff (ie it calls defineTestcase()). At this point
	# we check for _twopence_magic_resources, and if it exists, we transfer the
	# stashed requirements to the final TestCaseDefinition.
	def addTestResource(self, test, requirement):
		if isinstance(test, TestCaseDefinition):
			test.resources.append(requirement)
		else:
			# This is a function
			if getattr(test, '_twopence_magic_resources', None) is None:
				test._twopence_magic_resources = []
			test._twopence_magic_resources.append(requirement)

	def applyTestResources(self, f, tc):
		for requirement in getattr(f, '_twopence_magic_resources', []):
			print(f"Transfer {requirement} to {tc}")
			tc.resources.append(requirement)

	# @susetest.setup is largely useless because it is executed at
	# a point in time when the resource manager is still plugged, so
	# we cannot really do anything useful with resources there. Which
	# would be the main reason for defining a setup function :-(
	def defineSetup(self, f):
		name = f.__module__

		# So that we don't end up with module name __main__
		if name == '__main__':
			name = self._name

		self.createGroup(name).setup = f

	def defineTestcase(self, f):
		if not callable(f):
			raise ValueError("Don't know how to handle test defined by %s" % type(f))

		tc = TestCaseDefinition(f)
		self.applyTestResources(f, tc)

		# print("Defined test case %s" % tc)
		self.createGroup(tc.group).add(tc)

		return tc

	def actionSetup(self, driver, dummy = None):
		# First set up everything the drivers needs/thinks we need
		# This includes setup of features, like SELinux
		driver.beginSetup()

		# Request all resources that the user specified in the test
		# script using susetest.requireResource() and friends
		for req in self._resources:
			driver.beginTest(req.testID, f"acquire {req.resourceType} resource {req.resourceName}")
			req.request(driver)
			driver.endTest()

		# Last, run the setup function the user decorated with
		# @susetest.setup (if any).
		if self.setup:
			self.setup(driver)

		driver.setupComplete()

	def actionBeginGroup(self, driver, group):
		if self._failing:
			# Just go through the reporting motions, but don't
			# claim any resources etc.
			driver._logger.beginGroup(group.name)
		else:
			driver.beginGroup(group.name)

		self._currentGroup = group

	def actionEndGroup(self, driver, group):
		if self._currentGroup:
			self._currentGroup = None
			driver.endGroup()

	def actionSkipGroup(self, driver, group):
		susetest.say("\nSkipping group %s" % group.name)
		driver.beginGroup(group.name)
		if group.setup:
			driver.beginTest("setup-resources", group.setup.__doc__)
			driver.skipTest()
		for test in group.tests:
			driver.beginTest(test.name, test.description)
			driver.skipTest()
		driver.endGroup()

	def actionPerformTest(self, driver, test):
		driver.beginTest(test.name, test.description)
		if test.skip:
			driver.skipTest()
		else:
			if not test.verifyResources(driver):
				driver.skipTest()
			else:
				test(driver)
			driver.endTest()

	def enumerateSteps(self):
		result = []

		result.append([self.actionSetup, None])
		for group in self.groups:
			skipping = group.skip

			if group.skip:
				result.append([self.actionSkipGroup, group])
				continue

			if group.empty:
				continue

			result.append([self.actionBeginGroup, group])

			# Note: there is one significant difference in the way
			# setup works at the driver level (above) vs at the test group
			# level. At the driver level, we queue up the list of required
			# resources, and then perform the resource changes in one go.
			#
			# When calling user-defined functions, this is probably a bit
			# counter-intuitive, which is why in this case, we execute
			# these changes as they are issued by the user.
			if group.setup:
				result.append([self.actionPerformTest, GroupInitWrapper(group)])

			for test in group.tests:
				result.append([self.actionPerformTest, test])

			result.append([self.actionEndGroup, group])
		return result

	def prepare(self, driver):
		# If the test case comes with its own resource definitions,
		# we need to inform the driver so that it can load them
		driver.addTestResources(self.testResources)

		driver.loadTopologyStatus()

		# skip any tests whose requirements are not met
		self.verifyRequirements(driver)

	def perform(self, driver):
		steps = self.enumerateSteps()
		while steps:
			action, arg = steps.pop(0)
			try:
				action(driver, arg)
			except twopence.Exception as e:
				susetest.say("received fatal exception, failing all remaining test cases")
				driver.testError("test suite is failing (%s)" % e)
				self._failing = True
			except Exception as e:
				import traceback

				driver.testError("Caught python exception %s" % e)
				# print(traceback.format_exc(None))
				driver.logInfo(traceback.format_exc(None))

	class Found:
		def __init__(self, testOrGroup, parent = None):
			self.thing = testOrGroup
			self.parent = parent

	def findGroupOrTest(self, id):
		if '.' in id:
			(groupName, testName) = id.split('.', maxsplit = 1)
			group = self.getGroup(groupName)
			if not group:
				return None

			tc = group.getTest(testName)
			if tc:
				return self.Found(tc, parent = group)
			return None

		group = self.getGroup(id)
		if group:
			return self.Found(group)

		for group in self.groups:
			tc = group.getTest(id)
			if tc:
				return self.Found(tc, parent = group)

		return None

	def executeOnly(self, only):
		if only:
			for group in self.groups:
				group.skip = True
				for tc in group.tests:
					tc.skip = True

		for id in only:
			matcher = NameMatcher(id, context = "--only")

			found = False
			for group in self.groups:
				if not matcher.matchGroup(group.name):
					continue

				group.skip = False

				for test in group.tests:
					if matcher.matchTestcase(test.name):
						test.skip = False
						found = True

			if not found:
				raise ValueError("Did not find any tests matching --only \"%s\"" % id)

	def executeSkip(self, skip):
		for id in skip:
			matcher = NameMatcher(id, context = "--skip")

			found = False
			for group in self.groups:
				if not matcher.matchGroup(group.name):
					continue

				if matcher.matchAllTestcases:
					group.skip = True

				for test in group.tests:
					if matcher.matchTestcase(test.name):
						test.skip = True
						found = True

			if not found:
				raise ValueError("Did not find any tests matching --skip \"%s\"" % id)

	def verifyRequirements(self, driver):
		for group in self.groups:
			if group.skip:
				continue

			for test in group.tests:
				if test.skip:
					continue

				lacking = test.lackingRequirements(driver)
				if lacking:
					test.unmetRequirements = list(lacking)
					test.skip = True

class TestDefinition:
	@staticmethod
	def loadTestResources(*args, **kwargs):
		TestsuiteInfo.instance().loadTestResources(*args, **kwargs)

	@staticmethod
	def requireResource(*args, **kwargs):
		TestsuiteInfo.instance().requireResource(*args, **kwargs)

	@staticmethod
	def optionalResource(*args, **kwargs):
		TestsuiteInfo.instance().optionalResource(*args, **kwargs)

	@staticmethod
	def requireTestResource(*args, **kwargs):
		TestsuiteInfo.instance().requireTestResource(*args, **kwargs)

	@staticmethod
	def optionalTestResource(*args, **kwargs):
		TestsuiteInfo.instance().optionalTestResource(*args, **kwargs)

	@staticmethod
	def defineSetup(*args, **kwargs):
		TestsuiteInfo.instance().defineSetup(*args, **kwargs)

	@staticmethod
	def defineGroup(*args, **kwargs):
		return TestsuiteInfo.instance().defineGroup(*args, **kwargs)

	@staticmethod
	def defineTestcase(*args, **kwargs):
		return TestsuiteInfo.instance().defineTestcase(*args, **kwargs)

	@staticmethod
	def isValidTestcase(tc):
		return isinstance(tc, TestCase)

	@staticmethod
	def parseArgs():
		import optparse

		p = optparse.OptionParser(usage = "%prog [global options]")

		p.add_option('--quiet', action = 'store_true', default = False,
			help = "Suppress test case output")
		p.add_option('--debug', action = 'store_true', default = False,
			help = "Enable debugging at the provisioning layer")
		p.add_option('--debug-schema', action = 'store_true', default = False,
			help = "Enable debugging for config schema")
		p.add_option('--twopence-debug', action = 'store_true', default = False,
			help = "Enable debugging at the twopence layer")
		p.add_option('--config',
			help = "Path to config file")
		p.add_option('--skip', action = 'append', default = [],
			help = "Skip the named test case or group")
		p.add_option('--only', action = 'append', default = [],
			help = "Skip all but the named test case or group")

		(opts, args) = p.parse_args()

		if opts.debug:
			twopence.logger.enableLogLevel('debug')
		if opts.debug_schema:
			from twopence.schema import Schema
			Schema.debug.enabled = True

			twopence.logger.enableLogLevel('debug')

		if opts.twopence_debug:
			twopence.setDebugLevel(1)

		return opts, args


	@staticmethod
	def print_pre_run_summary(suite):
		printed = False

		print()
		print(f"=== Test definition summary for test script \"{suite.name}\" ===")
		print()

		for group in suite.groups:
			if group.empty:
				continue

			if not printed:
				print("This test script defines the following groups and test cases")
				print()
				printed = True

			print("  Group %s%s" % (group.name, group.skip and "; SKIPPED" or ""))
			for test in group.tests:
				description = [test.description]
				if test.skip:
					description.append("SKIPPED")
				if test.unmetRequirements:
					description.append("unmet requirement(s): %s" % " ".join(test.unmetRequirements))
				if test.resources:
					description.append("optional resources: %s" % " ".join(
							map(str, test.resources)))
				print("    %-20s %s" % (test.name, "; ".join(description)))

		if not printed:
			print("This test suite does not define any test cases")

		print()

	@staticmethod
	def print_schedule(suite):
		for group in suite.groups:
			if group.empty:
				continue

			print(f"GROUP:{group.name}.*:{group.skip and 'SKIP' or ''}")
			for test in group.tests:
				print(f"TEST:{group.name}.{test.name}:{test.skip and 'SKIP' or ''}:{test.description}")

	# Called by the user at the end of a test script, like this
	#
	#  if __name__ == '__main__':
	#	susetest.perform()
	#
	# For this to work, the user needs to define one or more functions
	# as test cases, and decorate these using @susetest.test
	#
	@staticmethod
	def perform():
		opts, args = TestDefinition.parseArgs()

		suite = TestsuiteInfo.instance()

		# The call to executeOnly must be first, so that
		# constructs like
		#	--only groupA --skip groupA.caseB
		# do what you'd expect
		suite.executeOnly(opts.only)
		suite.executeSkip(opts.skip)

		if args:
			for action in args:
				if action == 'info':
					TestDefinition.print_pre_run_summary(suite)
				elif action == 'schedule':
					TestDefinition.print_schedule(suite)
				else:
					raise ValueError(f"Unknown action \"{action}\" on the command line")
			exit(0)

		if not suite or suite.empty:
			raise ValueError("susetest.perform() invoked, but the script does not seem to define any test cases")

		driver = Driver(suite.name, config_path = opts.config)

		driver.verbose = not opts.quiet

		suite.prepare(driver)

		TestDefinition.print_pre_run_summary(suite)

		suite.perform(driver)

		driver.close()
