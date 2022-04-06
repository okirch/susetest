##################################################################
#
# This wraps the journal object and test logging
#
# Copyright (C) 2014-2022 SUSE Linux GmbH
#
##################################################################

import suselog
import susetest
from .xmltree import XMLTree

from .journal import load as loadJournal
from .journal import create as createJournal

def error(msg):
	print(f"Error: {msg}")

class TestLoggerHooks:
	def __init__(self):
		self._groupBeginHooks = []
		self._groupEndHooks = []
		self._postTestHooks = []

	def addGroupBeginHook(self, fn):
		self._groupBeginHooks.append(fn)

	def addGroupEndHook(self, fn):
		self._groupEndHooks.append(fn)

	def addPostTestHook(self, fn):
		self._postTestHooks.append(fn)

	def runGroupBeginHooks(self, group):
		for fn in self._groupBeginHooks:
			fn(group)

	def runGroupEndHooks(self, group):
		for fn in self._groupEndHooks:
			fn(group)

	def runPostTestHooks(self):
		for fn in self._postTestHooks:
			fn()

class GroupLogger:
	def __init__(self, journal, hooks, name, global_resources = None):
		self._name = name
		self._journal = journal
		self._hooks = hooks

		self._currentTest = None
		self.global_resources = global_resources

		assert(not global_resources)

		self._journal.beginGroup(self._name)
		self._active = True

	def __del__(self):
		self.end()

	@property
	def active(self):
		return self._active

	def __bool__(self):
		return self._active

	@property
	def currentTest(self):
		return self._currentTest

	def end(self):
		if self._active:
			self._hooks.runGroupEndHooks(self)
			self._journal.finishGroup()
			self._active = False

	@property
	def errors(self):
		fart

	@property
	def failures(self):
		fart

	def beginTest(self, *args, **kwargs):
		self.endTest()

		test = TestLogger(self._journal, self._hooks, *args, **kwargs)
		self._currentTest = test

		return test

	def endTest(self):
		test = self._currentTest
		if test:
			# Do not clear _currentTest until after we're done with test.end()
			# The reason being that this will call postTestHooks like a journal
			# or audit log monitor, which will want to log stuff via driver.log*,
			# which relies on currentTest
			test.end()

			self._currentTest = None

class TestLogger:
	class Outcome:
		def __init__(self, noun, logfn):
			self.noun = noun
			self.log = logfn

			self.reason = None

		def __str__(self):
			return self.noun

	def __init__(self, journal, hooks, name, *args, **kwargs):
		self._journal = journal
		self._hooks = hooks

		self._journal.beginTest(name, *args, **kwargs)
		self._active = True

		self._predict = None
		self._predictionArrived = False

		self.outcomeFailure = self.Outcome("failure", self._journal.failure)
		self.outcomeError = self.Outcome("error", self._journal.error)


	def __bool__(self):
		return self._active

	def end(self):
		if not self._active:
			return

		self._hooks.runPostTestHooks()

		if self._journal.status == "running":
			if self._predict and not self._predictionArrived:
				self._journal.failure(f"*** Expected {self._predict.noun} ({self._predict.reason}) - but the test apparently succeeded")
			else:
				self._journal.success()

		self._active = False

	# mark the test as being skipped
	def skip(self):
		self._journal.skipped()
		self.end()

	def logInfo(self, message):
		self._journal.info(message)

	def logOutcome(self, outcome, message):
		if self._predict is outcome:
			if not self._predictionArrived:
				self._journal.info(f"*** Encountering expected {outcome.noun} of test case")
				self._predictionArrived = True
			self._journal.info(f"Expected {outcome.noun}: {message}")
			return

		if self._predict and not self._predictionArrived:
			self._journal.info("*** Encountering unpredicted {outcome.noun} of test case (expected {self._predict.noun})")
			self._predictionArrived = True

		outcome.log(message)

	def logFailure(self, message):
		self.logOutcome(self.outcomeFailure, message)

	def logError(self, message):
		self.logOutcome(self.outcomeError, message)

	def recordStdout(self, data):
		self._journal.recordStdout(data)

	def recordStderr(self, data):
		self._journal.recordStderr(data)

	def setPredictedOutcome(self, status, reason):
		if status == 'failure':
			outcome = self.outcomeFailure
		elif status == 'error':
			outcome = self.outcomeError
		else:
			raise ValueError(f"Cannot handle unknown prediction {status}")

		if self._predict is not None and self._predict is not outcome:
			self.logError(f"Cassandra is confused: conflicting predictions {self._predict} vs {status}")
			return

		self.logInfo(f"*** Setting the predicted outcome of this test case to {status}: {reason}")
		outcome.reason = reason
		self._predict = outcome

class Logger:
	def __init__(self, name, path):
		susetest.say(f"Writing journal to {path}")

		self._journal = suselog.Journal(name, path = path);
		self._hooks = TestLoggerHooks()

		self._currentGroup = None

	def __del__(self):
		self.close()

	def close(self):
		if self._journal:
			self._journal.writeReport()
			self._journal.close()
			self._journal = None

	def addGroupBeginHook(self, fn):
		self._hooks.addGroupBeginHook(fn)

	def addGroupEndHook(self, fn):
		self._hooks.addGroupEndHook(fn)

	def addPostTestHook(self, fn):
		self._hooks.addPostTestHook(fn)

	@property
	def currentGroup(self):
		return self._currentGroup

	@property
	def currentTest(self):
		group = self._currentGroup
		if group:
			return group.currentTest
		return None

	def beginGroup(self, name):
		if self._currentGroup is not None:
			self.endGroup()

		group = GroupLogger(self._journal, self._hooks, name)
		self._currentGroup = group

		# We need to call the hooks from here, after setting
		# self._currentGroup
		self._hooks.runGroupBeginHooks(group)

		return group

	def endGroup(self):
		group = self._currentGroup
		if not group or not group.active:
			return None

		self._currentGroup = None
		group.end()

		return group

	def logFatal(self, message):
		susetest.say("FATAL " + message)
		self._journal.fatal(message)

	def logInfo(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logInfo outside of a test case - message will be LOST: {message}")
			return

		test.logInfo(message)

	def logFailure(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logFailure outside of a test case - message will be LOST: {message}")
			return

		test.logFailure(message)

	def logError(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logError outside of a test case - message will be LOST: {message}")
			return

		test.logError(message)

	def recordStdout(self, data):
		test = self.currentTest
		if not test:
			print(f"*** Calling recordStdout outside of a test case - data will be LOST: {data}")
			return

		test.recordStdout(data)

	def recordStderr(self, data):
		self._journal.recordStderr(data)
		test = self.currentTest
		if not test:
			print(f"*** Calling recordStderr outside of a test case - data will be LOST: {data}")
			return

		test.recordStderr(data)

	def addProperty(self, name, value):
		self._journal.addProperty(name, value)

def LogParser(path):
	return loadJournal(path)

class ResultsIO:
	class GenericObject:
		pass

	class NodeIO:
		def __init__(self, node):
			self._node = node

		def setName(self, name):
			self._node.setAttributes(name = name)

		@property
		def name(self):
			return self._node.attrib.get('name')

		def setInvocation(self, command):
			node = self._node.createChild("invocation")
			node.setText(command)

		@property
		def invocation(self):
			node = self._node.find("invocation")
			if node is not None:
				return node.text.strip()

		def addParameters(self, parameters):
			if not parameters:
				return

			node = self._node.createChild("parameters")
			for name, value in parameters.items():
				child = node.createChild("parameter")
				child.setAttributes(name = name, value = value)

		@property
		def parameters(self):
			d = {}

			node = self._node.find("parameters")
			if node is not None:
				for child in node.findall("parameter"):
					name = child.attrib.get("name")
					value = child.attrib.get("value")
					if name is None or value is None:
						continue
					d[name] = value

			return d

		def addResults(self, results):
			assert(self._node)
			for test in results:
				node = self._node.createChild("test")
				node.setAttributes(id = test.id,
						status = test.status,
						description = test.description)

		@property
		def results(self):
			ret = []
			for child in self._node:
				if child.tag != "test":
					continue

				res = ResultsIO.GenericObject()
				for name, value in child.attrib.items():
					setattr(res, name, value)
				ret.append(res)
			return ret

	class DocumentIO(NodeIO):
		@property
		def type(self):
			return self._node.attrib.get('type')

		def createColumn(self, name = None):
			node = self._node.createChild("vector")
			if name:
				node.setAttributes(name = name)

			return ResultsIO.NodeIO(node)

		@property
		def columns(self):
			if self._node is not None:
				for node in self._node:
					if node.tag == "vector":
						yield ResultsIO.NodeIO(node)

	class DocumentWriter(DocumentIO):
		def __init__(self, type):
			self._tree = XMLTree("results")

			super().__init__(self._tree.root)
			self._node.setAttributes(type = type)

		def save(self, path):
			self._tree.write(path)

	class DocumentReader(DocumentIO):
		def __init__(self, path):
			import xml.etree.ElementTree as ET

			try:
				self._tree = ET.parse(path)
			except Exception as e:
				raise ValueError(f"{path}: cannot parse XML document: {e}")

			super().__init__(self._tree.getroot())

			if self._node.tag != "results":
				raise ValueError(f"{path}: unexpected root node <{self._node.tag}>")

class ResultsMatrixWriter(ResultsIO.DocumentWriter):
	def __init__(self):
		super().__init__("matrix")

class ResultsVectorWriter(ResultsIO.DocumentWriter):
	def __init__(self):
		super().__init__("vector")

def ResultsParser(path):
	return ResultsIO.DocumentReader(path)
