##################################################################
#
# Test driver classes for susetest
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################
import inspect
import os
import curly
import sys
import re
import time

from .resources import Resource, ResourceManager
from .feature import Feature
from .logger import Logger
from .containermgr import ContainerManager
import susetest
import twopence.provision

class Driver:
	def __init__(self, name = None, config_path = None):
		self.name = name
		self.config_path = config_path

		self._topologyStatus = None
		self._caller_frame = inspect.stack()[-1]

		self._setup_complete = False

		self._features = {}
		self._targets = None
		self.workspace = None
		self.journal_path = None
		self._parameters = {}
		self._logger = None

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

	def __del__(self):
		self.close()

	def say(self, msg):
		print(msg)
		sys.stdout.flush()

	@property
	def topologyStatus(self):
		if self._topologyStatus is None:
			self.loadTopologyStatus()
		return self._topologyStatus

	@property
	def targets(self):
		return self._targets.values()

	def getTarget(self, name):
		return self._targets[name]

	def fatal(self, msg):
		self._logger.logFatal(msg)

	def info(self, msg):
		self._logger.logInfo(msg)

	def logInfo(self, msg):
		self._logger.logInfo(msg)

	def testFailure(self, msg):
		self._logger.logFailure(msg)

	def testError(self, msg):
		self._logger.logError(msg)

	def close(self):
		if self._logger:
			self._logger.close()
			self._logger = None

	# requireResource, optionalResource:
	#  resourceType is the name of the resource class (eg executable)
	#  resourceName is the name of the resource class (eg ipv4-address)
	#  nodeName identifies the node on which to resource resides.
	#	If not specified, the resource is acquired for all nodes
	#  temporary (bool): if set to true, the resource is released
	#	when the test group completes
	#  defer (bool): create the resource, but do not acquire it right away.
	#	Instead, it's the caller's responsibility to call
	#	node.acquireResource(res, ...) later.
	def requireUser(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("user", resourceName, nodeName, **stateArgs)

	def requireExecutable(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("executable", resourceName, nodeName, **stateArgs)

	def requireService(self, resourceName, nodeName = None, **stateArgs):
		return self.acquireResource("service", resourceName, nodeName, **stateArgs)

	def acquireResource(self, resourceType, resourceName, nodeName, **stateArgs):
		if 'mandatory' not in stateArgs:
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

	def getFeature(self, name):
		return self._features.get(name)

	def createFeature(self, name):
		feature = self._features.get(name)
		if feature is None:
			feature = Feature.createFeature(name)
			self._features[name] = feature
		return feature

	def activateFeature(self, node, group, featureName):
		feature = self.createFeature(featureName)

		# ignore duplicates
		if not node.testFeature(feature) and feature.requiresActivation:
			group.beginTest(name = f"{node.name}-enable-{featureName}", description = f"enable {featureName} on node {node.name}")
			feature.activate(self, node)
			susetest.say(f"{node.name}: enabled feature {featureName}")
			group.endTest()

		node.enabledFeature(feature)

	def getParameter(self, name):
		return self._parameters.get(name)

	def setParameter(self, name, value):
		self._parameters[name] = value

	def setup(self):
		if self._setup_complete:
			raise Exception("Duplicate call to setup()")

		group = self.beginGroup("setup")

		for node in self.targets:
			for feature in node.features:
				self.activateFeature(node, group, feature)

		self._update_hosts_files()

		for target in self.targets:
			target.configureApplications(self)

		self.info("Setup complete")
		self.info("")

		self.endGroup()

		self._setup_complete = True

	@property
	def currentGroupLogger(self):
		return self._logger.currentGroup

	@property
	def currentTestLogger(self):
		return self._logger.currentTest

	def beginGroup(self, name):
		# Okay, resoure manager is now willing to talk business
		self.resourceManager.unplug()

		return self._logger.beginGroup(name)

	def endGroup(self):
		self.resourceManager.plug()

		group = self.currentGroupLogger
		if group:
			group.end()

	def beginTest(self, *args, **kwargs):
		group = self.currentGroupLogger
		if not group:
			raise ValueError("beginTest called outside of a test group")

		return group.beginTest(*args, **kwargs)

	def skipTest(self, msg = None):
		test = self.currentTestLogger
		if not test:
			raise ValueError("skipTest called outside of a test")

		test.skip(msg)

	def predictTestResult(self, resource, **variables):
		test = self.currentTestLogger
		if not test:
			raise ValueError("predictTestResult called outside of a test case")

		prediction = resource.predictOutcome(self, variables)
		if prediction is None:
			return

		test.setPredictedOutcome(prediction.status, prediction.reason)

	def endTest(self):
		if self.currentGroupLogger:
			self.currentGroupLogger.endTest()

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

	def loadTopologyStatus(self):
		if self._topologyStatus is not None:
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

		self._topologyStatus = twopence.provision.loadPersistent(self.config_path)

		self._set_workspace()
		self._set_parameters()
		self._set_journal()
		self._set_targets()
		self._set_os_resources()

		self._publish_properties()

	def _set_targets(self):
		self._targets = {}

		for nodeStatus in self._topologyStatus.nodes:
			name = nodeStatus.name
			if getattr(self, name, None) is not None:
				raise ValueError(f"Bad target node name \"{name}\" - reserved name")

			target = susetest.Target(name, nodeStatus,
						logger = self._logger,
						resource_manager = self.resourceManager)
			self._targets[name] = target
			setattr(self, name, target)

			containerInfo = nodeStatus.container
			if containerInfo and containerInfo.backend:
				mgr = ContainerManager.create(nodeStatus.container)
				target.setContainerManager(mgr)

			target.defineStringResource("ipv4_loopback", "127.0.0.1")
			target.defineStringResource("ipv6_loopback", "::1")

			# we should probably have a Hostname resource that we can
			# get and set
			if False:
				res = target.requireSystemResource("hostname")
				res.update(f"{target.name}.twopence")

		# Do not require test-user resource for all nodes
		# self.requireUser("test-user")

	# Set any paramaters passed to us
	def _set_parameters(self):
		self._parameters = {}

		printed = False

		for key, value in self._topologyStatus.parameters:
			if not printed:
				susetest.say("Detected test suite parameter(s):")
				printed = True

			susetest.say(f"  {key} = {value}")
			self._parameters[key] = value

	# Set the workspace
	def _set_workspace(self):
		if self.workspace is None:
			logspace = self._topologyStatus.logspace
			if logspace is None:
				logspace = "./" + self.name
				susetest.say(f"Oops, no workspace defined. Using default \"{logspace}\"")

			self.workspace = logspace

		if not os.path.isdir(self.workspace):
			os.makedirs(self.workspace)

		susetest.say(f"Using workspace {self.workspace}")

	# Set the journal
	def _set_journal(self):
		if not self.journal_path:
			self.journal_path = os.path.join(self.workspace, "junit-results.xml")

		self._logger = Logger(self.name, self.journal_path)

	def _set_os_resources(self):
		for node in self.targets:
			self.resourceManager.loadPlatformResources(node, node.resource_files)
			node.configureApplicationResources()

	def _update_hosts_files(self):
		entries = []
		for node in self.targets:
			fqdn = node.fqdn
			aliases = [node.name]
			if node.ipv4_address:
				d = {'name': fqdn, 'addr': node.ipv4_address, 'aliases': aliases}
				entries.append(d)
			if node.ipv6_address:
				d = {'name': fqdn, 'addr': node.ipv6_address, 'aliases': aliases}
				entries.append(d)

		if not entries:
			self.logInfo("None of the nodes has a network address assigned; not updating hosts files")
			return

		self.beginTest(name = "update-hosts", description = "update hosts file on all nodes with all known addresses")
		self.logInfo("Trying to update hosts file on all nodes with all known addresses")
		for node in self.targets:
			hosts = node.requireFile("system-hosts")
			node.logInfo(f"Updating hosts file {hosts.path}")
			editor = hosts.createEditor()

			for d in entries:
				editor.addOrReplaceEntry(**d)

			# Sometimes, the build process will leave behind a stale hosts entry for "build"
			editor.removeEntry(name = "build")
			editor.commit()

	def _publish_properties(self):
		# Record all parameters that were set at global level
		for key, value in self._parameters.items():
			self._logger.addProperty(f"parameter:{key}", value)

		# Record per-node information
		for node in self.targets:
			for attr_name in ('ipv4_address', 'ipv6_address', 'os_release'):
				value = getattr(node, attr_name, None)
				if value is not None:
					key = f"{node.name}:{attr_name}".replace('_', '-')
					self._logger.addProperty(key, value)

	def addPostTestHook(self, fn):
		self._logger.addPostTestHook(fn)

