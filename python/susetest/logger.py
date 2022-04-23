##################################################################
#
# This wraps the journal object and test logging
#
# Copyright (C) 2014-2022 SUSE Linux GmbH
#
##################################################################

import susetest
from .xmltree import XMLTree

from .journal import load as loadJournal
from .journal import create as createJournal
from .xmltree import *

class TestLoggerHooks:
	def __init__(self):
		self._postTestHooks = []

	def addPostTestHook(self, fn):
		self._postTestHooks.append(fn)

	def runPostTestHooks(self):
		for fn in self._postTestHooks:
			fn()

class GroupLogger:
	def __init__(self, journal, hooks, name, global_resources = None):
		self._name = name
		self._journal = journal
		self._group = journal.beginGroup(name)
		self._hooks = hooks

		self._currentTest = None
		self.global_resources = global_resources

		assert(not global_resources)

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
			self.endTest()
			self._active = False

	@property
	def errors(self):
		fart

	@property
	def failures(self):
		fart

	def beginTest(self, *args, **kwargs):
		self.endTest()

		test = TestLogger(self._group, self._hooks, *args, **kwargs)
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

	def __init__(self, group, hooks, name, *args, **kwargs):
		self._hooks = hooks

		self._test = group.beginTest(name, *args, **kwargs)
		self._active = True

		self._predict = None
		self._predictionArrived = False

		self.outcomeFailure = self.Outcome("failure", self._test.logFailure)
		self.outcomeError = self.Outcome("error", self._test.logError)


	def __bool__(self):
		return self._active

	def end(self):
		if not self._active:
			return

		self._hooks.runPostTestHooks()

		if self._test.status is None:
			if self._predict and not self._predictionArrived:
				self._test.logFailure(f"*** Expected {self._predict.noun} ({self._predict.reason}) - but the test apparently succeeded")
			else:
				self._test.logSuccess()

		self._test.complete()
		self._active = False

	# mark the test as being skipped
	def skip(self, msg = None):
		self._test.logSkipped(msg)
		self.end()

	def logInfo(self, message):
		self._test.logInfo(message)

	def logOutcome(self, outcome, message):
		if self._predict is outcome:
			if not self._predictionArrived:
				self.logInfo(f"*** Encountering expected {outcome.noun} of test case")
				self._predictionArrived = True
			self.logInfo(f"Expected {outcome.noun}: {message}")
			return

		if self._predict and not self._predictionArrived:
			self.logInfo("*** Encountering unpredicted {outcome.noun} of test case (expected {self._predict.noun})")
			self._predictionArrived = True

		outcome.log(message)

	def logFailure(self, message):
		self.logOutcome(self.outcomeFailure, message)

	def logError(self, message):
		self.logOutcome(self.outcomeError, message)

	# cmd is a twopence.Command instance
	def logCommand(self, host, cmd):
		kwargs = {}
		if cmd.user:
			kwargs['user'] = cmd.user
		if cmd.timeout:
			kwargs['timeout'] = cmd.timeout
		if cmd.background:
			kwargs['background'] = cmd.background
		if cmd.tty:
			kwargs['tty'] = cmd.tty

		logHandle = self._test.logCommand(host, cmdline = cmd.commandline, **kwargs)

		# FIXME: if the caller set an environment, enter it into the log here
		if cmd.environ:
			pass

		# Backgrounded commands need a handle to track future updates
		if cmd.background:
			logHandle.generateId()

		return logHandle

	# logHandle is the handle returned by logCommand above;
	# st is a twopence.Status instance
	def logCommandStatus(self, logHandle, st):
		if not st:
			logHandle.recordStatus(exit_code = st.exitStatus, exit_signal = st.exitSignal, message = st.message)
		else:
			logHandle.recordStatus(exit_code = st.exitStatus)

		logHandle.recordStdout(st.stdout)
		if st.stderr != st.stdout:
			logHandle.recordStderr(st.stderr)

		# Status.buffer is just for file transfers
		assert(not st.buffer)

	class ProcessWithPaperTrail:
		def __init__(self, logger, test, id, process):
			self.logger = logger
			self.test = test
			self.id = id
			self.process = process

		@property
		def commandContinuation(self):
			return self.test.logCommandContinuation(self.id)

		@property
		def selinux_context(self):
			return self.process.selinux_context

		def kill(self, signal):
			# FIXME: log message. Would need a <signal> element in <command>
			self.process.kill(signal)

		def wait(self):
			st = self.process.wait()
			if st is not None:
				logHandle = self.commandContinuation
				self.logger.logCommandStatus(logHandle, st)
			return st

	def wrapProcess(self, logHandle, process):
		return self.ProcessWithPaperTrail(self, self._test, logHandle.id, process)

	class ChatWithPaperTrail(ProcessWithPaperTrail):
		@property
		def found(self):
			return self.process.found

		@property
		def consumed(self):
			return self.process.consumed

		@property
		def command(self):
			return self.process.command

		def expect(self, values, **kwargs):
			logHandle = self.commandContinuation

			if type(values) not in (list, tuple):
				values = [values]

			logHandle.recordChatExpectation(values)
			if 'timeout' in kwargs:
				logHandle.timeout = kwargs['timeout']

			found = self.process.expect(values, **kwargs)
			if found:
				logHandle.recordChatReceived(self.found, self.consumed)
			else:
				logHandle.recordChatTimeout(self.consumed)

			return found

		def send(self, msg):
			logHandle = self.commandContinuation
			logHandle.recordChatSent(msg)

			self.process.send(msg)

	def wrapChat(self, logHandle, chat):
		return self.ChatWithPaperTrail(self, self._test, logHandle.id, chat)

	def logUpload(self, host, xfer, hideData = False):
		kwargs = {}
		if xfer.user:
			kwargs['user'] = xfer.user
		if xfer.timeout:
			kwargs['timeout'] = xfer.timeout
		if xfer.data:
			kwargs['data'] = xfer.data
		kwargs['hideData'] = hideData

		return self._test.logUpload(host, xfer.remotefile, **kwargs)


	def logDownload(self, host, xfer, hideData = False):
		kwargs = {}
		if xfer.user:
			kwargs['user'] = xfer.user
		if xfer.timeout:
			kwargs['timeout'] = xfer.timeout
		kwargs['hideData'] = hideData

		return self._test.logDownload(host, xfer.remotefile, **kwargs)

	# logHandle is the handle returned by logUpload/Download above;
	# st is a twopence.Status instance
	def logTransferStatus(self, logHandle, st):
		if not st:
			logHandle.recordError(error = st.localError, message = st.message)
		elif logHandle.node.tag == 'download':
			logHandle.recordData(st.buffer)

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

	@property
	def predictedStatus(self):
		if not self._predict:
			return None
		return self._predict.noun

	def createSecurityViolation(self, *args, **kwargs):
		return self._test.createSecurityViolation(*args, **kwargs)

class Logger:
	def __init__(self, name, path):
		susetest.say(f"Writing journal to {path}")

		self._journal = createJournal(name)
		self._path = path
		self._hooks = TestLoggerHooks()

		self._currentGroup = None

	def __del__(self):
		self.close()

	def close(self):
		if self._journal:
			self._journal.finish()
			self._journal.save(self._path)
			self._journal = None

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

	def logCommand(self, host, cmd):
		return self.currentTest.logCommand(host, cmd)

	def logChatCommand(self, host, cmd):
		h = self.logCommand(host, cmd)
		h.generateId()
		return h

	def wrapProcess(self, logHandle, process):
		return self.currentTest.wrapProcess(logHandle, process)

	def wrapChat(self, logHandle, chat):
		return self.currentTest.wrapChat(logHandle, chat)

	def logCommandStatus(self, logHandle, st):
		self.currentTest.logCommandStatus(logHandle, st)

	def logDownload(self, host, xfer, hideData = False):
		return self.currentTest.logDownload(host, xfer, hideData)

	def logUpload(self, host, xfer, hideData = False):
		return self.currentTest.logUpload(host, xfer, hideData)

	def logTransferStatus(self, logHandle, st):
		self.currentTest.logTransferStatus(logHandle, st)

	def createSecurityViolation(self, subsystem, **kwargs):
		test = self.currentTest
		if test:
			return test.createSecurityViolation(subsystem, **kwargs)

		print(f"*** Calling createSecurityViolation outside of a test case - messages will be LOST")
		return self._journal.createSecurityViolation(subsystem, **kwargs)

	def addProperty(self, name, value):
		self._journal.addProperty(name, value)

def LogParser(path):
	return loadJournal(path)

class InfoInvocation(XMLBackedNode):
	def __str__(self):
		return self.node.text

	def set(self, value):
		# FIXME: escape processing
		self.node.text = value

class InfoParameter(XMLBackedNode):
	attributes = [
		AttributeSchema("name"),
		AttributeSchema("value"),
	]

class InfoParameterSet(XMLBackedNode):
	children = [
		ListNodeSchema("parameter", InfoParameter),
	]

	def asDict(self):
		result = {}
		for p in self.parameter:
			result[p.name] = p.value
		return result

	def add(self, name, value):
		child = self.createChild("parameter", name = name, value = value)

	def update(self, parameters):
		for name, value in parameters.items():
			self.add(name, value)

class TestResult(XMLBackedNode):
	attributes = [
		AttributeSchema("status"),
		AttributeSchema("id"),
		AttributeSchema("description"),
	]

class ResultsDocument(XMLBackedNode):
	attributes = [
		AttributeSchema("name"),
		AttributeSchema("type"),
	]
	children = [
		NodeSchema("invocation", InfoInvocation, attr_name = "_invocation"),
	]

	def setInvocation(self, text):
		self.createChild("invocation").set(text)

	@property
	def invocation(self):
		if self._invocation is not None:
			return str(self._invocation)

class ResultsVector(ResultsDocument):
	children = [
		ListNodeSchema("test", TestResult),
		NodeSchema("parameters", InfoParameterSet, attr_name = "_parameters"),
	] + ResultsDocument.children

	def addParameters(self, paramDict):
		if paramDict:
			self.createChild("parameters").update(paramDict)

	@property
	def parameters(self):
		if self._parameters:
			return self._parameters.asDict()
		return {}

	def addResults(self, results):
		for test in results:
			self.createChild("test",
					id = test.id,
					status = test.status,
					description = test.description)

	@property
	def results(self):
		return self.test

class ResultsMatrix(ResultsDocument):
	children = [
		ListNodeSchema("vector", ResultsVector),
	] + ResultsDocument.children

	@property
	def columns(self):
		return self.vector

	def createColumn(self, name = None):
		return self.createChild("vector", name = name)

def loadResultsDocument(path):
	try:
		tree = ET.parse(path)
	except Exception as e:
		error(f"Unable to parse results document {path}: {e}")
		return False

	root = tree.getroot()
	if root.tag == 'results' or root.attrib.get('type') == 'matrix':
		return ResultsMatrix(root)

	if root.tag == 'results' or root.attrib.get('type') == 'vector':
		return ResultsVector(root)

	raise ValueError(f"{path} does not look like a results document we can handle.")

def createResultsDocument(type):
	root = ET.Element("results")

	if type == "matrix":
		doc = ResultsMatrix(root)
	elif type == "vector":
		doc = ResultsVector(root)
	else:
		raise ValueError(f"Don't know how to create results document for type \"{type}\"")

	doc.type = type
	return doc

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
