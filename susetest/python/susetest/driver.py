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

from .resource import Resource, ResourceGroup, ResourceAssertion
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
	_RESOURCE_TYPES = None

	def __init__(self, name = None, config_path = None):
		self.name = name
		self.config_path = config_path

		self._config = None
		self._caller_frame = inspect.stack()[-1]

		self._global_resources = ResourceGroup()
		self._resource_assertions = []
		self._resource_cleanups = []

		self._current_group = None
		self._setup_complete = False

		self._targets = None
		self.workspace = None
		self.journal_path = None
		self.journal = None

		self._in_test_case = False
		self._hooks_end_test = []

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
		if self._RESOURCE_TYPES is None:
			self._RESOURCE_TYPES = {}
			self._define_resources(susetest.resource.__dict__)
			self._define_resources(self._context, verbose = True)

	def __del__(self):
		self._close_journal()

	def say(self, msg):
		print(msg)
		sys.stdout.flush()

	def _define_resources(self, ctx, verbose = False):
		for klass in self._find_classes(ctx, Resource, "name"):
			if verbose:
				susetest.say("Define resource %s = %s" % (klass.name, klass.__name__))
			self._RESOURCE_TYPES[klass.name] = klass

	@classmethod
	def _find_classes(selfKlass, ctx, baseKlass, required_attr = None):
		class_type = type(Driver)

		result = []
		for thing in ctx.values():
			if type(thing) is not class_type or not issubclass(thing, baseKlass):
				continue

			if required_attr and not hasattr(thing, required_attr):
				continue

			result.append(thing)
		return result

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
	#  type_name is the name of the resource class (eg ipv4-address)
	#  node_name identifies the node on which to resource resides.
	#	If not specified, the resource is created for all nodes
	#  temporary (bool): if set to true, the resource is released
	#	when the test group completes
	def requireResource(self, type_name, node_name = None, **kwargs):
		return self._requireResource(type_name, node_name, mandatory = True, **kwargs)

	def optionalResource(self, type_name, node_name = None, **kwargs):
		return self._requireResource(type_name, node_name, mandatory = False, **kwargs)

	def _requireResource(self, type_name, node_name = None,
				state = Resource.STATE_ACTIVE,
				**kwargs):
		node_list = []
		if node_name is None:
			# require this for all nodes
			node_list = self.targets
		else:
			node = self._targets.get(node_name)
			if node is None:
				raise KeyError("Unknown node \"%s\"" % node_name)
			node_list = [node]

		res_list = self._requireResourceForNodes(type_name, node_list, state, **kwargs)

		# If we're outside a test group, do not evaluate the assertion right away
		# but defer it until we do the beginGroup().
		# Else evaluate them right away.
		if self._current_group:
			self._perform_deferred_resource_assertions()

		if node_name:
			return res_list[0]

		return res_list

	def _requireResourceForNodes(self, type_name, node_list, state = Resource.STATE_ACTIVE,
				mandatory = False, temporary = False):
		resourceKlass = self._RESOURCE_TYPES.get(type_name)
		if resourceKlass is None:
			raise KeyError("Unknown resource type \"%s\"" % type_name)

		result = []
		for node in node_list:
			res = self._global_resources.get(node, type_name)
			if res is None:
				res = resourceKlass(node)
				self._global_resources.add(res)
				susetest.say("%s: created a %s resource" % (node.name, type_name))

				node.addResource(res)

			ares = ResourceAssertion(res, state, mandatory)
			self._resource_assertions.append(ares)

			result.append(res)

		# Return the list of resources
		return result

	def _perform_deferred_resource_assertions(self):
		deferred = self._resource_assertions
		self._resource_assertions = []

		cool = True
		for assertion in deferred:
			if not self._perform_resource_assertion(assertion):
				cool = False

		return cool

	def _perform_resource_cleanups(self):
		cleanups = self._resource_cleanups
		self._resource_cleanups = []

		for assertion in cleanups:
			# self._perform_resource_assertion(assertion)
			susetest.say("Ignoring cleanup of %s" % assertion)

	def enableFeature(self, node, feature):
		# ignore duplicates
		if node.testFeature(feature):
			return

		if feature == 'selinux':
			import susetest.selinux

			susetest.selinux.enableFeature(self, node)

			if self._current_group:
				self._perform_deferred_resource_assertions()
		else:
			susetest.say("WARNING: test run requests unsupported feature %s" % feature)
			return

		node.logInfo("enabled feature %s" % feature)
		node.enabledFeature(feature)

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
		self._resource_cleanups = []

		self.info("Setup complete")
		self.endGroup()

		self._setup_complete = True

	def beginGroup(self, name):
		if not self._beginGroup(name):
			if self._resource_cleanups:
				susetest.say("resource setup failed; cleaning up")
				self._perform_resource_cleanups()

			susetest.say("Skipping group %s" % name)
			return False

		return True

	def _beginGroup(self, name):
		if self._current_group is not None:
			self.endGroup()

		self._current_group = Group(name, self.journal)
		self._current_group.begin()

		if self._resource_assertions:
			self.journal.beginTest("setup-resources")
			if not self._perform_deferred_resource_assertions():
				return False

		return True

	def endGroup(self):
		self.endTest()

		if self._current_group is not None:
			if not self._setup_complete:
				# We're done executing the setup stage
				self._resource_cleanups = []
				self._setup_complete = True

			self._perform_resource_cleanups()

			self._current_group.end()
			self._current_group = None

			self._resource_assertions = []

	def beginTest(self, *args, **kwargs):
		self.endTest()

		self.journal.beginTest(*args, **kwargs)
		self._in_test_case = True

	def endTest(self):
		if self._in_test_case:
			self.runPostTestHooks()
			# If the test failed or errored, the following call to success() will
			# not do anything.
			self.journal.success()
			self._in_test_case = False

	def _perform_resource_assertion(self, assertion):
		res = assertion.resource
		node = res.target

		if not res.is_present:
			if assertion.mandatory:
				self.testFailure("%s: mandatory resource %s not present" % (node.name, res.name))
				return False

			self.info("%s: optional resource %s not present" % (node.name, res.name))
			return True

		if res.state == assertion.state:
			return True

		if assertion.temporary:
			self._resource_cleanups.append(ResourceAssertion(res, res.state, mandatory = False))

		if assertion.state == Resource.STATE_ACTIVE:
			verb = "activate"
			ok = res.acquire(self)
		elif assertion.state == Resource.STATE_INACTIVE:
			verb = "deactivate"
			ok = res.release(self)
		else:
			raise ValueError("%s: unexpected state %d in assertion for resource %s" % (node.name,
					assertion.state, res.name))

		if ok:
			res.state = assertion.state
		else:
			self.testFailure("%s: unable to %s resource %s" % (node.name, verb, res.name))
		return ok

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
		self._set_journal()
		self._set_targets()

	def _set_targets(self):
		self._targets = {}

		tree = self._config.tree()
		for name in tree.get_children("node"):
			if getattr(self, name, None) is not None:
				raise ValueError("Bad target node name \"%s\" - reserved name" % (name))

		for name in tree.get_children("node"):
			target_config = tree.get_child("node", name)
			target = susetest.Target(name, target_config, self.journal)
			self._targets[name] = target
			setattr(self, name, target)

		# Require test-user resource for all nodes
		self.requireResource("test-user")

	# Set the workspace
	def _set_workspace(self):
		if self.workspace is None:
			self.workspace = self._config.workspace()
			if not self.workspace:
				susetest.say("Oops, no workspace defined. Using default.")
				self.workspace = "."

		susetest.say("Using workspace %s" % self.workspace)

	# Set the journal
	def _set_journal(self):
		if self.journal_path is None:
			self.journal_path = self._config.report()

		if not self.journal_path:
			self.journal_path = os.path.join(self.workspace, "junit-results.xml")

		susetest.say("Writing journal to %s" % self.journal_path)
		self.journal = suselog.Journal(self.name, path = self.journal_path);

	def _close_journal(self):
		if self.journal:
			self.journal.writeReport()
			self.journal = None

	def addPostTestHook(self, fn):
		self._hooks_end_test.append(fn)

	def runPostTestHooks(self):
		for fn in self._hooks_end_test:
			fn()

