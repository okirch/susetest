##################################################################
#
# Test driver classes for susetest
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################
import suselog
import inspect
import os
import curly
import sys
import re
import time

from .resources import Resource, ResourceManager
from .feature import Feature
import susetest

class Group:
	def __init__(self, name, journal, global_resources = None):
		self.name = name
		self.journal = journal
		self.global_resources = global_resources

		self._active = False

	def __del__(self):
		self.end()

	def begin(self):
		if not self._active:
			self.journal.beginGroup(self.name)
			self._active = True

	def end(self):
		if self._active:
			self.journal.finishGroup()
			self._active = False

class Driver:
	def __init__(self, name = None, config_path = None):
		self.name = name
		self.config_path = config_path

		self._config = None
		self._caller_frame = inspect.stack()[-1]

		self._current_group = None
		self._setup_complete = False

		self._features = {}
		self._targets = None
		self.workspace = None
		self.journal_path = None
		self.journal = None
		self._parameters = {}

		self._in_test_case = False
		self._hooks_end_test = []

		self.resourceManager = ResourceManager(self)

		if self.name is None:
			path = self._caller_frame.filename

			# If we've been invoked as /usr/blah/NAME/run,
			# extract NAME and use that.
			if os.path.basename(path) == "run":
				orig_dir = os.path.dirname(path)
				self.name = os.path.basename(orig_dir)

		if self.name is None:
			raise ValueError("Unable to determine name of test run")

		susetest.say("=== Created TestDriver(%s) ===" % self.name)

		self._context = self._caller_frame.frame.f_globals

	def __del__(self):
		self._close_journal()

	def say(self, msg):
		print(msg)
		sys.stdout.flush()

	@property
	def config(self):
		if self._config is None:
			self.load_config()
		return self._config

	@property
	def targets(self):
		return self._targets.values()

	def fatal(self, msg):
		susetest.say("FATAL " + msg)
		self.journal.fatal(msg)

	def info(self, msg):
		self.journal.info(msg)

	def logInfo(self, msg):
		self.journal.info(msg)

	def testFailure(self, msg):
		self.journal.failure(msg)

	def testError(self, msg):
		self.journal.error(msg)

	# requireResource, optionalResource:
	#  resourceType is the name of the resource class (eg executable)
	#  resourceName is the name of the resource class (eg ipv4-address)
	#  nodeName identifies the node on which to resource resides.
	#	If not specified, the resource is acquired for all nodes
	#  temporary (bool): if set to true, the resource is released
	#	when the test group completes
	#  defer (bool): do not make the requested resource change
	#	right away, even if we're in the middle of executing a
	#	test. Instead, defer the change until the user calls
	#	performDeferredResourceChanges()
	def requireUser(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("user", resourceName, nodeName, **stateArgs)

	def requireExecutable(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("executable", resourceName, nodeName, **stateArgs)

	def requireService(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("service", resourceName, nodeName, **stateArgs)

	def acquireResource(self, resourceType, resourceName, nodeName, **stateArgs):
		stateArgs['mandatory'] = True
		if nodeName is None:
			result = []
			for node in self.targets:
				res = node.acquireResourceTypeAndName(resourceType, resourceName, **stateArgs)
				result.append(res)
			return result
		else:
			node = self._targets.get(nodeName)
			if node is None:
				raise KeyError("Unknown node \"%s\"" % nodeName)
			result = node.acquireResourceTypeAndName(resourceType, resourceName, **stateArgs)

		return result



	def _requireResource(self, res_name, node_name = None, **stateArgs):
		if node_name is None:
			result = []
			for node in self.targets:
				res = node._requestResource(res_name, **stateArgs)
				result.append(res)
			return result
		else:
			node = self._targets.get(node_name)
			if node is None:
				raise KeyError("Unknown node \"%s\"" % node_name)
			result = node._requestResource(res_name, **stateArgs)

		return result

	def performDeferredResourceChanges(self):
		return self.resourceManager.performDeferredChanges()

	def getFeature(self, name):
		return self._features.get(name)

	def createFeature(self, name):
		feature = self._features.get(name)
		if feature is None:
			feature = Feature.createFeature(name)
			self._features[name] = feature
		return feature

	def enableFeature(self, node, featureName):
		feature = self.createFeature(featureName)

		# ignore duplicates
		if not node.testFeature(feature):
			feature.enableFeature(self, node)
			susetest.say("%s: enabled feature %s" % (node.name, featureName))
		node.enabledFeature(feature)

	def getParameter(self, name):
		return self._parameters.get(name)

	@property
	def setupComplete(self):
		return self._setup_complete

	def setup(self):
		if self._setup_complete:
			raise Exception("Duplicate call to setup()")

		# as part of the beginGroup call, we acquire all the resources
		# that have been requested so far.
		if not self._beginGroup("setup"):
			self.fatal("Failures during test suite setup, giving up")

		for node in self.targets:
			for feature in node.features:
				self.enableFeature(node, feature)

		# Any resources that were brought up at this stage
		# shall not be cleaned up automatically when done with this
		# group (which is the default otherwise)
		self.resourceManager.zapCleanups()

		self.info("Setup complete")
		self.info("")

		self.endGroup()

		self._setup_complete = True

	def beginGroup(self, name):
		if not self._beginGroup(name):
			if self.resourceManager.pendingCleanups:
				susetest.say("resource setup failed; cleaning up")
				self.resourceManager.cleanup()

			susetest.say("Skipping group %s" % name)
			return False

		return True

	def _beginGroup(self, name):
		if self._current_group is not None:
			self.endGroup()

		self._current_group = Group(name, self.journal)
		self._current_group.begin()

		# If we have pending resource activations, start
		# a test cases for these specifically. Without an
		# active test case, most of the logging would otherwise
		# go to the bit bucket.
		if self.resourceManager.pending:
			self.journal.beginTest("setup-resources")

		# Perform any postponed resource changes,
		# allow future resource changes to be executed right away
		self.resourceManager.unplug()

		return True

	def endGroup(self):
		self.endTest()

		if self._current_group is not None:
			if not self._setup_complete:
				# We're done executing the setup stage
				self.resourceManager.zapCleanups()
				self._setup_complete = True

			self.resourceManager.cleanup()

			self._current_group.end()
			self._current_group = None

			self.resourceManager.plug()
			# self.resourceManager.zapPending()

	def beginTest(self, *args, **kwargs):
		self.endTest()

		self.journal.beginTest(*args, **kwargs)
		self._in_test_case = True


	def skipTest(self, *args, **kwargs):
		if not self._in_test_case:
			self.beginTest(*args, **kwargs)

		# mark the test as being skipped
		self.journal.skipped()

		self._in_test_case = False

	def endTest(self):
		if self._in_test_case:
			self.runPostTestHooks()

			# If the test failed or errored, the following call to success() will
			# not do anything.
			if self.journal.status == "running":
				self.journal.success()
			self._in_test_case = False

	# Support for parameterized tests
	# Parameters are referenced using @node:variable syntax
	def expandArguments(self, args):
		result = []
		for s in args:
			orig_s = s
			expanded = ""
			while True:
				m = re.match("(.*)@([a-z0-9_]+):([a-z0-9_]+)(.*)", s)
				if not m:
					expanded += s
					break

				expanded += m.group(1)
				nodeName = m.group(2)
				varName = m.group(3)
				s = m.group(4)

				node = self._targets.get(nodeName)
				if node is None:
					raise ValueError("Cannot expand %s: no target named \"%s\"" % (orig_s, nodeName))

				value = node.expandStringResource(varName)
				if value is None:
					self.logInfo("parameter \"%s\" not set" % varName)
					return None

				expanded += value

			result.append(expanded)

		# susetest.say("expandArguments(%s) -> %s" % (args, result))
		return result

	def load_config(self):
		if self._config is not None:
			return

		if not self.config_path:
			config_path = os.path.join("/run/twopence", self.name, "status.conf")
			susetest.say("Trying config path %s" % config_path)
			if os.path.isfile(config_path):
				self.config_path = config_path

		if not self.config_path:
			susetest.say("Trying environment variable TWOPENCE_CONFIG_PATH")
			self.config_path = os.getenv("TWOPENCE_CONFIG_PATH")

		if not self.config_path:
			raise ValueError("Unable to determine path of config file")

		self._config = curly.Config(self.config_path)

		self._set_workspace()
		self._set_parameters()
		self._set_journal()
		self._set_targets()
		self._set_os_resources()

	def _set_targets(self):
		self._targets = {}

		tree = self._config.tree()
		for name in tree.get_children("node"):
			if getattr(self, name, None) is not None:
				raise ValueError("Bad target node name \"%s\" - reserved name" % (name))

		for name in tree.get_children("node"):
			target_config = tree.get_child("node", name)
			target = susetest.Target(name, target_config,
						journal = self.journal,
						resource_manager = self.resourceManager)
			self._targets[name] = target
			setattr(self, name, target)

			target.defineStringResource("ipv4_loopback", "127.0.0.1")
			target.defineStringResource("ipv6_loopback", "::1")

		# Require test-user resource for all nodes
		self.requireUser("test-user")

	# Set any paramaters passed to us
	def _set_parameters(self):
		self._parameters = {}

		tree = self._config.tree()
		child = tree.get_child("parameters")
		if child:
			printed = False
			for name in child.get_attributes():
				if not printed:
					print("Detected test suite parameter(s):")
					printed = True

				value = child.get_value(name)

				print("  %s = %s" % (name, value))
				self._parameters[name] = value

	# Set the workspace
	def _set_workspace(self):
		if self.workspace is None:
			logspace = self._config.tree().get_value("logspace")
			if not logspace:
				susetest.say("Oops, no workspace defined. Using default.")
				logspace = "."

			self.workspace = os.path.join(logspace, self.name, time.strftime("%Y%M%dT%H%M%S"))

		if not os.path.isdir(self.workspace):
			os.makedirs(self.workspace)

		susetest.say("Using workspace %s" % self.workspace)

	# Set the journal
	def _set_journal(self):
		if self.journal_path is None:
			self.journal_path = self._config.report()

		if not self.journal_path:
			self.journal_path = os.path.join(self.workspace, "junit-results.xml")

		susetest.say("Writing journal to %s" % self.journal_path)
		self.journal = suselog.Journal(self.name, path = self.journal_path);

		# Record all parameters that were set at global level
		for key, value in self._parameters.items():
			self.journal.addProperty(key, value)

	def _set_os_resources(self):
		for node in self.targets:
			vendor = node.os_vendor
			release = node.os_release
			if not vendor or not release:
				continue

			self.resourceManager.loadOSResources(node, vendor, "linux", release)

	def _close_journal(self):
		if self.journal:
			self.journal.writeReport()
			self.journal = None

	def addPostTestHook(self, fn):
		self._hooks_end_test.append(fn)

	def runPostTestHooks(self):
		for fn in self._hooks_end_test:
			fn()

