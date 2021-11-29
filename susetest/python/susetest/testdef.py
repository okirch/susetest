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
from .config import Config
from .driver import Driver
from .resources import resourceRegistry
import susetest

class Name:
	_re = None

	def __init__(self, group = None, case = None):
		self.group = group
		self.case = case

	@staticmethod
	def parse(s):
		words = s.split('.')

		if len(words) > 2:
			return None

		if not Name._re:
			Name._re = re.compile("[-a-z0-9_]+", re.IGNORECASE)
		if any(not Name._re.match(_) for _ in words):
			return None

		if len(words) == 2:
			return Name(*words)
		return Name(case = words[0])

	def __str__(self):
		return "Name(group = %s, case = %s)" % (self.group, self.case)

class ResourceRequirement:
	def __init__(self, resourceName, nodeName = None, mandatory = False):
		self.resourceName = resourceName
		self.nodeName = nodeName
		self.mandatory = mandatory

class TestCase:
	pass

class TestCaseDefinition(TestCase):
	def __init__(self, f):
		self.f = f
		self.name = None
		self.group = None
		self.description = None
		self.skip = False

		if not callable(f):
			raise ValueError("Don't know how to handle test defined by %s" % type(f))

		doc = f.__doc__
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

	def requireResource(self, resourceName, nodeName = None):
		self.requireResource(ResourceRequirement(resourceName, nodeName = nodeName, mandatory = True))

	def optionalResource(self, resourceName, nodeName = None):
		self.requireResource(ResourceRequirement(resourceName, nodeName = nodeName, mandatory = False))

	def requireResource(self, req):
		self._resources.append(req)

	def defineSetup(self, f):
		name = f.__module__
		self.createGroup(name).setup = f

	def defineTestcase(self, f):
		if not callable(f):
			raise ValueError("Don't know how to handle test defined by %s" % type(f))

		tc = TestCaseDefinition(f)

		print("Defined test case %s" % tc)
		self.createGroup(tc.group).add(tc)

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
			found = self.findGroupOrTest(id)
			if not found:
				raise ValueError("Invalid test or group ID --only \"%s\"" % id)

			found.thing.skip = False
			if found.parent:
				found.parent.skip = False
			else:
				for test in found.thing.tests:
					test.skip = False

	def executeSkip(self, skip):
		for id in skip:
			found = self.findGroupOrTest(id)
			if not found:
				raise ValueError("Invalid test or group ID --skip \"%s\"" % id)

			found.thing.skip = True

class TestDefinition:
	@staticmethod
	def defineResource(*args, **kwargs):
		registry = resourceRegistry()
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
		TestsuiteInfo.instance().defineGroup(*args, **kwargs)

	@staticmethod
	def defineTestcase(*args, **kwargs):
		TestsuiteInfo.instance().defineTestcase(*args, **kwargs)

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

		if True:
			printed = False
			for group in suite.groups:
				if group.empty:
					continue

				if not printed:
					print("This test suite defines a set of functions")
					printed = True

				print("  Group %s%s" % (group.name, group.skip and "; SKIPPED" or ""))
				for test in group.tests:
					print("    %-20s %s%s" % (test.name, test.description, test.skip and "; SKIPPED" or ""))

			if not printed:
				print("This test suite does not define any test cases")

		driver = Driver()

		driver.verbose = not opts.quiet
		driver.config_path = opts.config

		driver.load_config()
		if suite.setup:
			suite.setup(driver)
		if not driver.setupComplete:
			driver.setup()

		for group in suite.groups:
			if group.skip:
				susetest.say("Skipping group %s" % group.name)
				continue

			driver.beginGroup(group.name)

			# Note: there is one significant difference in the way
			# setup works at the driver level (above) vs at the test group
			# level. At the driver level, we queue up the list of required
			# resources, and then perform the resource changes in one go.
			#
			# When calling user-defined functions, this is probably a bit
			# counter-intuitive, which is why in this case, we execute
			# these changes as they are issued by the user.
			if group.setup:
				driver.beginTest("setup-resources", group.setup.__doc__)
				group.setup(driver)
				driver.endTest()

				# FIXME: error out when setup fails

			for test in group.tests:
				if test.skip:
					susetest.say("Skipping test %s" % test.name)
					continue

				driver.beginTest(test.name, test.description)
				test(driver)
				driver.endTest()
			driver.endGroup()
