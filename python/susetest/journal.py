##################################################################
#
# New journaling code
# These classes completely replace the old suselog code.
#
# Copyright (C) 2022 Olaf Kirch <okir@suse.com>
#
##################################################################

import xml.etree.ElementTree as ET
import time

__all__ = ['load', 'create']

##################################################################
# Values represented by attributes to an XML node
##################################################################
class AttributeSchema:
	typeconv = None

	def __init__(self, name):
		self.name = name
		self.attr_name = name.replace('-', '_')

	def _getter(self, object):
		value = object.node.attrib.get(self.name)
		if value is not None:
			if self.typeconv:
				value = self.typeconv(value)
		return value

	def _setter(self, object, value):
		if value is not None:
			object.node.attrib[self.name] = str(value)
		else:
			try: del object.node.attrib[self.name]
			except: pass

class IntAttributeSchema(AttributeSchema):
	typeconv = int

class FloatAttributeSchema(AttributeSchema):
	typeconv = float

##################################################################
class NodeSchema:
	def __init__(self, name, childClass):
		self.name = name
		self.attr_name = name.replace('-', '_')
		self.childClass = childClass

	def _initer(self, object):
		setattr(object, self.attr_name, None)

	def _adder(self, object, childObject):
		setattr(object, self.attr_name, childObject)

	def _factory(self, object):
		childObject = getattr(object, self.attr_name, None)
		if childObject is None:
			childObject = self.childClass(ET.SubElement(object.node, self.name))
			setattr(object, self.attr_name, childObject)
		return childObject

class ListNodeSchema(NodeSchema):
	def _initer(self, object):
		setattr(object, self.attr_name, [])
	
	def _adder(self, object, childObject):
		current = getattr(object, self.attr_name)
		current.append(childObject)

	def _factory(self, object):
		childObject = self.childClass(ET.SubElement(object.node, self.name))
		# self._adder(object, childObject)
		object.addChild(self, childObject)
		return childObject

##################################################################
# Wrapper classes for XML nodes
##################################################################
class XMLBackedNode:
	attributes = []
	children = []

	def __init__(self, node):
		self._init_schema()

		self.node = node

		for type in self._children.values():
			type._initer(self)

		for child in node:
			type = self._children.get(child.tag)
			if type is None:
				raise KeyError(f"Unsupported XML element <{child.tag}> in <{node.tag}>")

			self.addChild(type, type.childClass(child))

	@classmethod
	def _init_schema(klass):
		if getattr(klass, '_initialized', False):
			return

		klass._attributes = {}
		for type in klass.attributes:
			prop = property(type._getter, type._setter)
			setattr(klass, type.attr_name, prop)
			klass._attributes[type.name] = type

		klass._children = {}
		for type in klass.children:
			klass._children[type.name] = type

		klass._initialized = True

	def __str__(self):
		info = []
		for type in self.attributes:
			value = type._getter(self)
			if value is not None:
				info.append(f"{type.name} = {value}")
		info = ", ".join(info)
		return f"{self.__class__.__name__}({info})"

	def addChild(self, type, childObject):
		type._adder(self, childObject)

	def createChild(self, _childName, **kwargs):
		type = self._children.get(_childName)
		if type is None:
			raise KeyError(f"Invalid name {_childName}: no type information for this child of {self}")

		childObject = type._factory(self)
		childObject.construct(**kwargs)
		return childObject

	def construct(self, **kwargs):
		if kwargs:
			for name, value in kwargs.items():
				type = self._attributes.get(name)
				if type is None:
					type = self._attributes.get(name.replace('_', '-'))
				if type is None:
					raise KeyError(f"Invalid attribute {name}: no information for this attribute of {self}")
				type._setter(self, value)

class TimedNode(XMLBackedNode):
	def __init__(self, node):
		super().__init__(node)
		self.startTime = None

	def startClock(self):
		pass

	def stopClock(self):
		pass

class JournalEvent(XMLBackedNode):
	attributes = [
		FloatAttributeSchema("timestamp"),
	]

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.timestamp = time.time()

	@property
	def eventType(self):
		return self.node.tag

class JournalMessages(JournalEvent):
	attributes = [
		AttributeSchema("type"),
		AttributeSchema("message"),
	] + JournalEvent.attributes

	_escape_table = None

	def __init__(self, node):
		super().__init__(node)
		self._messages = []
		self.writer = None

		self._init_escape_table()

	@classmethod
	def _init_escape_table(klass):
		if klass._escape_table:
			return

		d = {i: ("Ctrl-" + chr(i + 0x40)) for i in range(32)}
		del d[ord('\n')]
		del d[ord('\t')]
		d[ord('\b')] = '\\b'
		d[ord('\r')] = '\\r'
		d[ord('\v')] = '\\v'
		d[7] = '<BEL>'

		klass._escape_table = str.maketrans(d)

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.writer = writer

	@property
	def text(self):
		if not self.node.text:
			return ""
		return self.node.text.strip()

	def write(self, msg, prefix = None, nodeName = None):
		# can be None, empty string, empty bytearray...
		if not msg:
			return

		if type(msg) in (bytearray, bytes):
			try:
				msg = msg.decode('utf-8')
			except: pass
		if type(msg) != str:
			msg = str(msg)

		self._messages.append(msg)
		text = "\n".join(self._messages)
		text = text.translate(self._escape_table)
		# text = f"<![CDATA[{text}]]>"
		self.node.text = text

		if self.writer:
			self.writer.logMessage(msg)

class JournalCommandStatus(XMLBackedNode):
	attributes = [
		IntAttributeSchema("exit-code"),
		IntAttributeSchema("exit-signal"),
		AttributeSchema("timeout"),
		AttributeSchema("message"),

		# other exit info should go here, such as the SELinux
		# process domain
	]

##################################################################
# This is a single step in a chat command
##################################################################
class SimpleString(XMLBackedNode):
	attributes = [
		AttributeSchema("string"),
	]

class JournalChit(JournalEvent):
	children = [
		ListNodeSchema("expect", SimpleString),
		NodeSchema("sent", JournalMessages),
		NodeSchema("received", JournalMessages),
		NodeSchema("error", JournalMessages),
	]

	def setExpect(self, values):
		for s in values:
			childObject = self.createChild("expect")
			childObject.string = s

	def setError(self, type, message):
		if not self.error:
			self.createChild("error")
		self.error.type = type
		self.error.message = message

##################################################################
# Commands that are we wait for should be logged as one element:
#
#  <command cmdline="blah" user="root" ...>
#   <status exit-code="1"/>
#   <system-out>bla bla blah</system-out>
#  </command>
#
# Backgrounded commands should log their progress in time-based
# order, ie their progress should appear in the log in the order
# in which it happened:
#
#  <command cmdline="blah" user="root" ... id="123" />
#  <info>Some unrelated message</info>
#  .. other activity
#  <command id="123">
#   <status exit-code="1"/>
#   <system-out>bla bla blah</system-out>
#  </command>
#
# When rendering a log, the renderer can use the id to correlate
# these bits and pieces.
##################################################################
class JournalCommand(JournalEvent):
	_cmdId = 1

	attributes = [
		AttributeSchema("host"),
		AttributeSchema("cmdline"),
		AttributeSchema("user"),
		AttributeSchema("timeout"),
		AttributeSchema("background"),
		AttributeSchema("tty"),

		# Should be used for backgrounded commands
		AttributeSchema("id"),
	] + JournalEvent.attributes
	children = [
		NodeSchema("status", JournalCommandStatus),
		NodeSchema("stdout", JournalMessages),
		NodeSchema("stderr", JournalMessages),

		NodeSchema("chat", JournalChit),
	]

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.writer = writer

	def generateId(self):
		if self.id is None:
			self.id = self.__class__._cmdId
			self.__class__._cmdId += 1

	def setExitCode(self, code):
		self.createChild("status", exit_code = code)

	def recordStatus(self, **kwargs):
		if self.writer:
			self.writer.logCommandStatus(cmdline = self.cmdline, **kwargs)

		self.createChild("status", **kwargs)

	def recordStdout(self, msg):
		if msg:
			if not self.stdout:
				self.stdout = self.createChild("stdout")
			self.stdout.write(msg)

	def recordStderr(self, msg):
		if msg:
			if not self.stderr:
				self.stderr = self.createChild("stderr")
			self.stderr.write(msg)

	def recordChatExpectation(self, values):
		if not self.chat:
			self.chat = self.createChild("chat")
		self.chat.setExpect(values)

	def recordChatReceived(self, found, stdout):
		if not self.chat:
			self.chat = self.createChild("chat")
		if found is not None:
			self.chat.createChild("received").write(found)
		self.recordStdout(stdout)

	def recordChatSent(self, msg):
		if not self.chat:
			self.chat = self.createChild("chat")
		self.chat.createChild("sent").write(msg)

	def recordChatTimeout(self, stdout):
		if not self.chat:
			self.chat = self.createChild("chat")
		self.chat.setError("timeout", "chat command timed out")
		self.recordChatReceived(None, stdout)

##################################################################
# This represents a file transfer
##################################################################
class JournalFileTransfer(JournalEvent):
	attributes = [
		AttributeSchema("host"),
		AttributeSchema("path"),
		AttributeSchema("user"),
		AttributeSchema("permissions"),
		AttributeSchema("timeout"),
	] + JournalEvent.attributes
	children = [
		NodeSchema("data", JournalMessages),
		NodeSchema("error", JournalMessages),
	]

	def __init__(self, node):
		super().__init__(node)
		self.hideData = False

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)
		self.writer = writer

	def recordError(self, error, message):
		child = self.createChild("error")
		child.type = error
		child.message = message

	def recordData(self, data):
		if self.hideData or len(data) > 2048:
			data = f"[suppressed {len(data)} bytes of data]"
		elif self.writer:
			# self.writer.logBuffer("Data", data)
			pass

		self.createChild("data").write(data)

class JournalLog(XMLBackedNode):
	# This is a bit special. The reimplementation of addChild() below
	# makes sure that all children of this node are kept in a single
	# list (self.events) rather than putting them into one separate list
	# per child type.
	children = [
		ListNodeSchema("info", JournalMessages),
		ListNodeSchema("failure", JournalMessages),
		ListNodeSchema("error", JournalMessages),
		ListNodeSchema("command", JournalCommand),
		ListNodeSchema("upload", JournalFileTransfer),
		ListNodeSchema("download", JournalFileTransfer),
	]

	def __init__(self, node):
		self.events = []
		self.writer = None

		super().__init__(node)

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.writer = writer

	def addChild(self, type, childObject):
		if isinstance(childObject, JournalEvent):
			self.events.append(childObject)
		else:
			type._adder(self, childObject)

	def createMessage(self, severity):
		return self.createChild(severity, writer = self.writer)

	def createCommand(self, host, cmdline, **kwargs):
		return self.createChild("command", host = host, cmdline = cmdline, writer = self.writer, **kwargs)

	def createCommandContinuation(self, id):
		return self.createChild("command", id = id, writer = self.writer)

	def createUpload(self, host, path, hideData = False, **kwargs):
		if self.writer:
			self.writer.logMessage(f"{host}: uploading data to {path}")
		xfer = self.createChild("upload", host = host, path = path, writer = self.writer, **kwargs)
		xfer.hideData = hideData
		return xfer

	def createDownload(self, host, path, hideData = False, **kwargs):
		if self.writer:
			self.writer.logMessage(f"{host}: downloading {path}")
		xfer = self.createChild("download", host = host, path = path, writer = self.writer, **kwargs)
		xfer.hideData = hideData
		return xfer

class JournalTest(TimedNode):
	attributes = [
		AttributeSchema("name"),
		AttributeSchema("type"),
		AttributeSchema("test-id"),
		AttributeSchema("status"),
		FloatAttributeSchema("time"),
	] + TimedNode.attributes
	children = [
		NodeSchema("system-out", JournalMessages),
		NodeSchema("failure", JournalMessages),
		NodeSchema("error", JournalMessages),
		NodeSchema("log", JournalLog),
	]

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.startTime = time.time()

		if writer:
			writer.beginTestHeading(id = self.test_id, description = self.name)
		self.writer = writer

		self.createChild("log", writer = self.writer)

	def setStatus(self, status):
		assert(status in ('success', 'failure', 'error', 'skipped', 'disabled'))

		current = self.status
		if current is None:
			pass
		elif status == 'error':
			# test suite errors always win
			pass
		elif status == 'success':
			# someone hasn't been paying attention
			return
		elif status != current:
			# now it's an error
			self.logMessage(f"invalid test status changes from {current} to {status}", severity = 'error')
			status = 'error'

		self.time = time.time() - self.startTime
		self.status = status

	def logMessage(self, msg, severity = "info", **kwargs):
		if not msg:
			return

		m = self.log.createMessage(severity)
		m.write(msg, **kwargs)

	def logInfo(self, msg):
		self.logMessage(msg, severity = 'info')

	def logSuccess(self, msg = None):
		self.logMessage(msg, severity = 'info')
		self.setStatus('success')

	def logFailure(self, msg):
		self.logMessage(f"Failing: {msg}", severity = 'failure')

		if self.failure is None:
			child = self.createChild("failure")
			child.type = "randomFailure"
			child.message = msg
		self.setStatus('failure')

	def logError(self, msg):
		self.logMessage(f"Error: {msg}", severity = 'error')

		if self.error is None:
			child = self.createChild("error")
			child.type = "randomError"
			child.message = msg
		self.setStatus('error')

	def logSkipped(self, msg = None):
		if msg:
			self.logMessage(f"Skipping: {msg}", severity = 'info')
		self.setStatus('skipped')

	def logDisabled(self, msg = None):
		self.logMessage(msg, severity = 'info')
		self.setStatus('disabled')

	def logCommand(self, host, cmdline, **kwargs):
		cmd = self.log.createCommand(host, cmdline, **kwargs)

		if self.writer:
			info = []
			if cmd.user:
				info.append("user=%s" % cmd.user)
			if cmd.timeout:
				info.append("timeout=%s" % cmd.timeout)
			if cmd.background:
				info.append("background")

			# notyet
			if False:
				env = cmd.environ
				if env:
					info += [("%s=\"%s\"" % kv) for kv in env]

			if info:
				info = "; " + ", ".join(info)
			else:
				info = ""

			self.writer.logMessage(f"{host}: {cmdline}{info}")
			if cmd.background:
				self.writer.logMessage("Command was backgrounded")

		return cmd

	def logCommandContinuation(self, id):
		return self.log.createCommandContinuation(id)

	def logChatExpect(self, id, values, timeout = None):
		if type(values) not in (list, tuple):
			values = [values]

		cmd = self.log.createCommandContinuation(id)
		cmd.recordChatExpectation(values)
		if timeout is not None:
			cmd.timeout = timeout

	def logChatReceived(self, id, found, stdout = None):
		cmd = self.log.createCommandContinuation(id)
		cmd.recordChatReceived(found, stdout)

		if stdout:
			cmd.recordStdout(stdout)

	def logChatSent(self, id, msg):
		cmd = self.log.createCommandContinuation(id)
		cmd.recordChatSent(msg)

	def logUpload(self, host, path, data, **kwargs):
		xfer = self.log.createUpload(host, path, **kwargs)
		if data:
			xfer.recordData(data)
		return xfer

	def logDownload(self, host, path, data = None, **kwargs):
		xfer = self.log.createDownload(host, path, **kwargs)
		if data:
			xfer.recordData(data)
		return xfer

	def complete(self):
		assert(self.status)

		if self.writer:
			if self.status == 'failure':
				msg = self.failure.message
			elif self.status == 'error':
				msg = self.error.message
			else:
				msg = None
			self.writer.logTestResult(self.test_id, self.status, msg)

class NodeWithStats(TimedNode):
	attributes = TimedNode.attributes + [
		IntAttributeSchema("tests"),
		IntAttributeSchema("failures"),
		IntAttributeSchema("disabled"),
		IntAttributeSchema("skipped"),
		IntAttributeSchema("errors"),
	]

	def clearStats(self):
		# in a Group, self.tests already reflects the number of tests we began
		if self.tests is None:
			self.tests = 0
		self.failures = 0
		self.errors = 0
		self.skipped = 0
		self.disabled = 0

	def account(self, status):
		if status == 'success':
			pass
		elif status == 'failure':
			self.failures += 1
		elif status == 'error':
			self.errors += 1
		elif status == 'skipped':
			self.skipped += 1
		elif status == 'disabled':
			self.disabled += 1
		else:
			raise ValueError(f"Unexpected test status {status}")

	def accumulate(self, other):
		self.tests += other.tests
		self.failures += other.failures
		self.disabled += other.disabled
		self.skipped += other.skipped
		self.errors += other.errors

class JournalProperty(XMLBackedNode):
	attributes = [
		AttributeSchema("key"),
		AttributeSchema("value"),
	]

class JournalProperties(XMLBackedNode):
	children = [
		ListNodeSchema("property", JournalProperty),
	]

	def asDict(self):
		result = {}
		for p in self.property:
			result[p.key] = p.value
		return result

	def add(self, key, value):
		child = self.createChild("property")
		child.key = key
		child.value = value

class JournalGroup(NodeWithStats):
	attributes = [
		AttributeSchema("package"),
		AttributeSchema("timestamp"),
		AttributeSchema("hostname"),
	] + NodeWithStats.attributes
	children = [
		NodeSchema("properties", JournalProperties),
		ListNodeSchema("testcase", JournalTest),
	]

	def __init__(self, node):
		super().__init__(node)
		self.writer = None

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.tests = 0

		if writer:
			writer.beginGroupHeading(self.package)
		self.writer = writer

	def beginTest(self, name, description):
		self.tests += 1

		id = f"{self.package}.{name}"
		return self.createChild("testcase", writer = self.writer, test_id = id, name = description)

	def finish(self):
		self.clearStats()
		for test in self.testcase:
			if test.status is None:
				test.logError("BUG: test has no result")
			self.account(test.status)

class JournalRootNode(NodeWithStats):
	attributes = NodeWithStats.attributes + [
		AttributeSchema("name"),
	] + NodeWithStats.attributes
	children = [
		ListNodeSchema("testsuite", JournalGroup),
		NodeSchema("properties", JournalProperties),
	]

	def __init__(self, node, name = None, writer = None):
		super().__init__(node)

		if name is not None:
			self.name = name
		self.writer = writer

	def __str__(self):
		return f"{self.__class__.__name__}(name = {self.name})"

	def addProperty(self, key, value):
		if not self.properties:
			self.createChild("properties")
		self.properties.add(key, value)

	def beginGroup(self, name):
		id = f"{self.name}.{name}"
		return self.createChild("testsuite", writer = self.writer, package = id)

	def finish(self):
		self.clearStats()
		for suite in self.testsuite:
			suite.finish()
			self.accumulate(suite)

		if self.writer:
			self.writer.logStats(StatsWrapper(self),
					self.listFailedTests())

	def listFailedTests(self):
		result = []
		for suite in self.testsuite:
			for test in suite.testcase:
				if test.status in ('failure', 'error'):
					result.append(test.test_id)
		return result

class Journal:
	def __init__(self, node = None, name = None):
		if node:
			self.root = JournalRootNode(node)
			self.writer = None
		else:
			writer = StdoutWriter()

			if not name:
				name = "report"
			node = ET.Element("twopence-report")
			self.root = JournalRootNode(node, name, writer)

	def save(self, filename):
		import os
		
		tree = ET.ElementTree(self.root.node)

		# ElementTree.indent was added in 3.9
		if getattr(ET, 'indent', None):
			ET.indent(tree)
		else:
			def diy_indent(node, space = "  "):
				indent = "\n" + space
				space += "  "

				# Setting our own tail indents our right hand sibling, or,
				# if we're the last element, the closing element of our parent
				# node.
				# The default is to set .tail to indent our sibling. If we
				# are the last child, the caller will take care to adjust our .tail
				node.tail = indent[:-2]

				children = list(iter(node))
				if not children:
					# No children, no whitespace
					return

				# Indent the first child node by setting our .text
				if node.text is None:
					node.text = indent

				for child in children:
					diy_indent(child, space)

				lastChild = children[-1]
				lastChild.tail = indent[:-2]

			diy_indent(tree.getroot())

		tree.write(filename + ".new", "UTF-8", xml_declaration = True)
		os.rename(filename + ".new", filename)

		if False:
			print(f"--- {filename} ---")
			ET.dump(tree.getroot())
			print("---")

	def addProperty(self, key, value):
		self.root.addProperty(key, value)

	def beginGroup(self, *args, **kwargs):
		'''Begin a test group'''
		return self.root.beginGroup(*args, **kwargs)

	def finish(self):
		self.root.finish()

class StdoutWriter:
	def hrule(self):
		print("------------------------------------------------------------------")

	def header(self, msg):
		self.hrule()
		print()
		print(msg)
		print()
		self.hrule()

	def beginGroupHeading(self, name):
		self.header(f"GROUP: {name}")

	def beginTestHeading(self, id, description):
		self.header(f"TEST: {description or id}")

	def logMessage(self, msg):
		if msg:
			print(msg)

	def logTestResult(self, id, status, msg = None):
		if status == 'success':
			result = "SUCCESS"
		elif status == 'failure':
			result = f"FAILED"
		elif status == 'error':
			result = f"ERROR"
		elif status == 'skipped':
			result = f"SKIPPED"
		elif status == 'disabled':
			result = f"DISABLED"
		else:
			result = f"UNKNOWN STATUS {status}"

		if msg:
			print(f"RESULT: {result} ({msg})")
		else:
			print(f"RESULT: {result}")

	def logCommandStatus(self, cmdline, exit_code, exit_signal = None, message = None):
		if not exit_code and not exit_signal:
			pass
		elif message:
			self.logMessage(f"command {cmdline} failed: {message}")
		else:
			self.logMessage(f"command {cmdline} failed: exit-code={exit_code} exit-signal={exit_signal}")

	def logStats(self, stats, failedTests):
		self.hrule()
		print()
		print(f"  Test run stats:")
		print(f"    Test cases:   {stats.tests}")
		print(f"    Failed:       {stats.failures}")
		print(f"    Errors:       {stats.errors}")
		print(f"    Skipped:      {stats.skipped}")
		print(f"    Disabled:     {stats.disabled}")

		if failedTests:
			print()
			print(f"  The following tests failed:")
			for id in failedTests:
				print(f"    {id}")

		print()
		self.hrule()

##################################################################
# These wrapper classes provide access to a junit xml report
# while hiding the details of how stuff is organized.
##################################################################
class WrappedNode:
	def __init__(self, node, klass):
		for type in klass.attributes:
			value = getattr(node, type.attr_name, None)
			setattr(self, type.attr_name, value)

class StatsWrapper(WrappedNode):
	def __init__(self, nodeWithStats):
		super().__init__(nodeWithStats, NodeWithStats)

class MessagesWrapper(WrappedNode):
	def __init__(self, node):
		super().__init__(node, JournalMessages)
		self.text = node.text

	def __str__(self):
		return self.text

class TestcaseWrapper:
	def __init__(self, test):
		self.test = test
		self.status = test.status
		self.time = test.time
		self.id = test.test_id
		self.description = test.name
		self.log = test.log

		def wrapMessages(msgNode):
			if msgNode is not None:
				return MessagesWrapper(msgNode)

		self.systemOut = wrapMessages(test.system_out)
		self.failure = wrapMessages(test.failure)
		self.error = wrapMessages(test.error)

class TestsuiteWrapper:
	def __init__(self, suite):
		self.suite = suite
		self.stats = StatsWrapper(suite)
		self.id = suite.package

		if suite.properties:
			self.properties = suite.properties.asDict()
		else:
			self.properties = {}

		self.hostname = suite.hostname
		self.timestamp = suite.timestamp

	@property
	def tests(self):
		for test in self.suite.testcase:
			yield TestcaseWrapper(test)

class JournalWrapper:
	def __init__(self, journal):
		self.journal = journal
		self.name = journal.root.name
		self.stats = StatsWrapper(journal.root)
		self.properties = journal.root.properties

	@property
	def groups(self):
		for suite in self.journal.root.testsuite:
			yield TestsuiteWrapper(suite)

##################################################################
# Load a test report from XML file
##################################################################
def load(path):
	try:
		tree = ET.parse(path)
	except Exception as e:
		error(f"Unable to parse test report {path}: {e}")
		return False

	root = tree.getroot()
	if root.tag == 'testsuites' or root.tag == 'twopence-report':
		return JournalWrapper(Journal(root))
	
	raise ValueError(f"{path} does not look like a test report we can handle.")

def create(name):
	return Journal(name = name)

def dump(journal):
	print(journal.root)

	for suite in journal.root.testsuite:
		print(f"  {suite}")
		if suite.properties:
			print(f"    Properties:")
			for p in suite.properties.property:
				print(f"      {p}")

		for test in suite.testcase:
			print(f"    {test}")
			if test.system_out:
				print("      %u bytes of system-out" % len(test.system_out.text))
				for line in test.system_out.text.split("\n"):
					print(f"        {line}")
			if test.failure:
				print("      %u bytes of failures" % len(test.failure.text))
			if test.error:
				print("      %u bytes of errors" % len(test.error.text))

if __name__ == '__main__':
	# journal = load("/home/okir/susetest/logs/demo-matrix-selinux-all/selinux/guest/nginx/junit-results.xml")
	# dump(journal)

	journal = create(name = "newlog")

	group = journal.beginGroup(name = "generic")

	test = group.beginTest(name = "test1", description = "Random test")
	test.logDownload("client", "/etc/hosts", '''
# This is the hosts file
127.0.0.1	localhost
''')
	test.logSuccess("done")

	test = group.beginTest(name = "test2", description = "Another test")
	test.logInfo("This is an info message. With \7s and whistles.")
	test.logFailure("Oopsie, something went wrong")

	test = group.beginTest(name = "test3", description = "A third test")

	cmd = test.logCommand("client", "id -Z root", user = "root")
	cmd.setExitCode(1)

	cmd = test.logCommand("client", "/usr/bin/beckett", background = True, user = "okir")
	id = cmd.id

	test.logInfo("This is an unrelated message.")

	cmd = test.logCommandContinuation(id)
	cmd.setExitCode(1)
	cmd.recordStdout("Busily waiting for Godot to come around.")
	cmd.recordStderr("Godot did not come. The audience want their money back!")
	test.logSuccess("done")

	test = group.beginTest(name = "test4", description = "A third test")
	cmd = test.logCommand("client", "passwd", background = True)
	id = cmd.id

	test.logChatExpect(id, "assword:", timeout = 10)
	test.logChatReceived(id, "assword:", stdout = "Please enter password:")
	test.logChatSent(id, "sup3r$3kr3t\n")

	cmd = test.logCommandContinuation(id)
	cmd.recordStderr("You are a cheater".encode('utf-8'))
	cmd.setExitCode(1)

	test.logSuccess("done")

	test = group.beginTest(name = "test5", description = "A third test")

	journal.finish()

	dump(journal)
	journal.save("/tmp/journal.xml")
