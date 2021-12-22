##################################################################
#
# Python classes for susetest: test case and group definitions
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################

import suselog
import twopence
import time
import re
import sys
import os
import functools

from .target import Target
from .driver import Driver
from .resources import globalResourceRegistry
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
		return driver.acquireResource(self.resourceType, self.resourceName, self.nodeName, mandatory = self.mandatory)

class TestCase:
	pass

class TestCaseDefinition(TestCase):
	def __init__(self, f):
		self.f = f
		self.name = None
		self.group = None
		self.description = None
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

	def addOptionalResource(self, name):
		self.resources.append(name)

	def lackingRequirements(self, driver):
		result = set()

		for name in self.requires:
			for node in driver.targets:
				if name not in node.features:
					result.add(name)

		return result

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

	def __call__(self, driver):
		self.group.setup(driver)

class TestsuiteInfo:
	_instance = None

	def __init__(self):
		self._groups = {}

		self.setup = None

		# List of resource requirements
		# Scripts can specify these via
		#  susetest.requireResource("foo", [node = "client"])
		#  susetest.optionalResource("bar")
		self._resources = []

		# Ensure that the first group is always the one defined
		# in the calling script, even if that script imports
		# other files that define additional test cases
		self.createGroup('__main__')

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
	def groups(self):
		return self._groups.values()

	def getGroup(self, name):
		return self._groups.get(name)

	def createGroup(self, name):
		group = self._groups.get(name)
		if not group:
			group = TestGroupDef(name)
			self._groups[name] = group
		return group

	def requireResource(self,  resourceType,resourceName, nodeName = None):
		self._resources.append(ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = True))

	def optionalResource(self, resourceType, resourceName, nodeName = None):
		self._resources.append(ResourceRequirement(resourceType, resourceName, nodeName = nodeName, mandatory = False))

	def defineSetup(self, f):
		name = f.__module__
		self.createGroup(name).setup = f

	def defineTestcase(self, f):
		if not callable(f):
			raise ValueError("Don't know how to handle test defined by %s" % type(f))

		tc = TestCaseDefinition(f)

		# print("Defined test case %s" % tc)
		self.createGroup(tc.group).add(tc)

		return tc

	def requestResources(self, driver):
		for req in self._resources:
			req.request(driver)

	def actionBeginGroup(self, driver, group):
		try:
			driver.beginGroup(group.name)
		except twopence.Exception as e:
			susetest.say("received fatal exception, failing all remaining test cases")
			driver.testError("test suite is failing")
			self._failing = True
		self._currentGroup = group

	def actionEndGroup(self, driver, group):
		if self._currentGroup:
			self._currentGroup = None
			driver.endGroup()

	def actionSkipGroup(self, driver, group):
		susetest.say("\nSkipping group %s" % group.name)
		driver.beginGroup(group.name)
		if group.setup:
			driver.skipTest("setup-resources", group.setup.__doc__)
		for test in group.tests:
			driver.skipTest(test.name, test.description)
		driver.endGroup()

	def actionPerformTest(self, driver, test):
		if test.skip:
			driver.skipTest(test.name, test.description)
		else:
			driver.beginTest(test.name, test.description)
			if not self._failing:
				try:
					test(driver)
				except twopence.Exception as e:
					susetest.say("received fatal exception, failing all remaining test cases")
					self._failing = True

			# Note, it's "if" not "elif" here for a reason
			if self._failing:
				driver.testError("test suite is failing")

			driver.endTest()

	def enumerateSteps(self):
		result = []

		for group in self.groups:
			skipping = group.skip

			if group.skip:
				result.append([self.actionSkipGroup, group])
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

	def performSteps(self, driver, steps):
		while steps:
			action, arg = steps.pop(0)
			action(driver, arg)

	def perform(self, driver):
		steps = self.enumerateSteps()
		self.performSteps(driver, steps)

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
				raise ValueError("Did not find any tests maching --only \"%s\"" % id)

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
				raise ValueError("Did not find any tests maching --only \"%s\"" % id)

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
	def defineResource(*args, **kwargs):
		registry = globalResourceRegistry()
		registry.defineResource(*args, **kwargs, verbose = True)

	@staticmethod
	def requireResource(*args, **kwargs):
		TestsuiteInfo.instance().requireResource(*args, **kwargs)

	@staticmethod
	def optionalResource(*args, **kwargs):
		TestsuiteInfo.instance().optionalResource(*args, **kwargs)

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
		p.add_option('--twopence-debug', action = 'store_true', default = False,
			help = "Enable debugging at the twopence layer")
		p.add_option('--config',
			help = "Path to config file")
		p.add_option('--skip', action = 'append', default = [],
			help = "Skip the named test case or group")
		p.add_option('--only', action = 'append', default = [],
			help = "Skip all but the named test case or group")
		p.add_option('--on-failure',
			help = "Specify reaction to a failed test case (continue, abort, shell) [default: continue]")

		(opts, args) = p.parse_args()

		if args:
			p.error("Extra arguments on command line - don't know what to do with them")

		if opts.twopence_debug:
			twopence.setDebugLevel(1)

		return opts


	@staticmethod
	def print_pre_run_summary(suite):
		printed = False

		print()
		print("=== Test definition summary ===")

		for group in suite.groups:
			if group.empty:
				continue

			if not printed:
				print("This test suite defines these groups and test cases")
				printed = True

			print("  Group %s%s" % (group.name, group.skip and "; SKIPPED" or ""))
			for test in group.tests:
				description = [test.description]
				if test.skip:
					description.append("SKIPPED")
				if test.unmetRequirements:
					description.append("unmet requirement(s): %s" % " ".join(test.unmetRequirements))
				if test.resources:
					description.append("optional resources: %s" % " ".join(test.resources))
				print("    %-20s %s" % (test.name, "; ".join(description)))

		if not printed:
			print("This test suite does not define any test cases")

	# Called by the user at the end of a test script, like this
	#
	#  if __name == '__main__':
	#	susetest.perform()
	#
	# For this to work, the user needs to define one or more functions
	# as test cases, and decorate these using @susetest.test
	#
	@staticmethod
	def perform():
		opts = TestDefinition.parseArgs()

		suite = TestsuiteInfo._instance
		if not suite or suite.empty:
			raise ValueError("susetest.perform() invoked, but the script does not seem to define any test cases")

		# The call to executeOnly must be first, so that
		# constructs like
		#	--only groupA --skip groupA.caseB
		# do what you'd expect
		suite.executeOnly(opts.only)
		suite.executeSkip(opts.skip)

		driver = Driver()

		driver.verbose = not opts.quiet
		driver.config_path = opts.config

		driver.load_config()

		# skip any tests whose requirements are not met
		suite.verifyRequirements(driver)

		TestDefinition.print_pre_run_summary(suite)

		suite.perform(driver)
