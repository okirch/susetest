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
		value = object.node.attrib.get(self.attr_name)
		if value is not None:
			if self.typeconv:
				value = self.typeconv(value)
		return value

	def _setter(self, object, value):
		if value is not None:
			value = str(value)
		object.node.attrib[self.attr_name] = value

class IntAttributeSchema(AttributeSchema):
	typeconv = int

class FloatAttributeSchema(AttributeSchema):
	typeconv = float

##################################################################
class NodeSchema:
	def __init__(self, name, childClass, constructedChildClass = None):
		self.name = name
		self.attr_name = name.replace('-', '_')
		self.childClass = childClass
		self.constructedChildClass = constructedChildClass or childClass

	def _initer(self, object):
		setattr(object, self.attr_name, None)

	def _adder(self, object, childObject):
		setattr(object, self.attr_name, childObject)

	def _factory(self, object):
		childObject = getattr(object, self.attr_name, None)
		if childObject is None:
			childObject = self.constructedChildClass(ET.SubElement(object.node, self.name))
			setattr(object, self.attr_name, childObject)
		return childObject

class ListNodeSchema(NodeSchema):
	def _initer(self, object):
		setattr(object, self.attr_name, [])
	
	def _adder(self, object, childObject):
		current = getattr(object, self.attr_name)
		current.append(childObject)

	def _factory(self, object):
		childObject = self.constructedChildClass(ET.SubElement(object.node, self.name))
		self._adder(object, childObject)
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

			type._adder(self, type.childClass(child))

	@classmethod
	def _init_schema(klass):
		if getattr(klass, '_initialized', False):
			return

		klass._attributes = {}
		for type in klass.attributes:
			prop = property(type._getter, type._setter)
			setattr(klass, type.name, prop)
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

class JournalMessages(XMLBackedNode):
	attributes = [
		AttributeSchema("type"),
		AttributeSchema("message"),
	]

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

		d = {i: ("<Ctrl-" + chr(i + 0x41) + ">") for i in range(32)}
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

	def write(self, msg, level = None, nodeName = None):
		# can be None, empty string, empty bytearray...
		if not msg:
			return

		if type(msg) in (bytearray, bytes):
			try:
				msg = msg.decode('utf-8')
			except: pass
		if type(msg) != str:
			msg = str(msg)

		if self.writer and level != 'quiet':
			self.writer.logMessage(msg)

		self._messages.append(msg)
		text = "\n".join(self._messages)
		text = text.translate(self._escape_table)
		# text = f"<![CDATA[{text}]]>"
		self.node.text = text

class JournalTest(TimedNode):
	attributes = [
		AttributeSchema("name"),
		AttributeSchema("classname"),
		AttributeSchema("status"),
		FloatAttributeSchema("time"),
	] + TimedNode.attributes
	children = [
		NodeSchema("system-out", JournalMessages),
		NodeSchema("failure", JournalMessages),
		NodeSchema("error", JournalMessages),
	]

	def construct(self, writer = None, **kwargs):
		super().construct(**kwargs)

		self.startTime = time.time()

		if writer:
			writer.beginTestHeading(id = self.classname, description = self.name)
		self.writer = writer

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
			self.log("invalid test status changes from {current} to {status}", level = 'error')
			status = 'error'

		self.time = time.time() - self.startTime
		self.status = status

	def log(self, msg, level = None):
		if not msg:
			return

		if self.system_out is None:
			self.createChild("system-out", writer = self.writer)

		self.system_out.write(msg, level)

	def recordStdout(self, msg):
		if msg:
			self.log("Standard output:", level = 'quiet')
			self.log(msg, level = 'quiet')

	def recordStderr(self, msg):
		if msg:
			self.log("Standard error:", level = 'quiet')
			self.log(msg, level = 'quiet')

	def recordBuffer(self, msg):
		if msg:
			self.log(msg, level = 'quiet')

	def logInfo(self, msg):
		self.log(msg, level = 'info')

	def logSuccess(self, msg = None):
		self.log(msg, level = 'info')
		self.setStatus('success')

	def logFailure(self, msg):
		self.log(f"Failing: {msg}", level = 'failure')

		if self.failure is None:
			child = self.createChild("failure")
			child.type = "randomFailure"
			child.message = msg
		self.setStatus('failure')

	def logError(self, msg):
		self.log(f"Error: {msg}", level = 'error')

		if self.error is None:
			child = self.createChild("error")
			child.type = "randomError"
			child.message = msg
		self.setStatus('error')

	def logSkipped(self, msg = None):
		if msg:
			self.log(f"Skipping: {msg}", level = 'info')
		self.setStatus('skipped')

	def logDisabled(self, msg = None):
		self.log(msg, level = 'info')
		self.setStatus('disabled')

	def complete(self):
		assert(self.status)

		if self.writer:
			if self.status == 'failure':
				msg = self.failure.message
			elif self.status == 'error':
				msg = self.error.message
			else:
				msg = None
			self.writer.logTestResult(self.classname, self.status, msg)

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
		return self.createChild("testcase", writer = self.writer, classname = id, name = description)

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
	]

	def __init__(self, node, name = None, writer = None):
		super().__init__(node)

		if name is not None:
			self.name = name
		self.writer = writer

	def __str__(self):
		return f"{self.__class__.__name__}(name = {self.name})"

	def beginGroup(self, name):
		id = f"{self.name}.{name}"
		group = self.createChild("testsuite", writer = self.writer, package = id)
		return group

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
					result.append(test.classname)
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
			node = ET.Element("testsuites")
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
		pass

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
		self.id = test.classname
		self.description = test.name

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

	# FIXME: check for proper root element name
	root = tree.getroot()
	if root.tag == 'testsuites':
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
	journal = load("/home/okir/susetest/logs/demo-matrix-selinux-all/selinux/guest/nginx/junit-results.xml")
	# dump(journal)

	journal = create(name = "newlog")

	group = journal.beginGroup(name = "generic")

	test = group.beginTest(name = "test1", description = "Random test")
	test.logSuccess("done")

	test = group.beginTest(name = "test2", description = "Another test")
	test.logInfo("This is an info message. With \7s and whistles.")
	test.logFailure("Oopsie, something went wrong")

	test = group.beginTest(name = "test3", description = "A third test")

	journal.finish()

	dump(journal)
	journal.save("/tmp/journal.xml")
