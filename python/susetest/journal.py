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
		self._initclass()

		self.node = node

		for type in self._children.values():
			type._initer(self)

		for child in node:
			type = self._children.get(child.tag)
			if type is None:
				raise KeyError(f"Unsupported XML element <{child.tag}> in <{node.tag}>")

			type._adder(self, type.childClass(child))

	@classmethod
	def _initclass(klass):
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
		if kwargs:
			for name, value in kwargs.items():
				childObject.setAttribute(name, value)
		return childObject

	def setAttribute(self, name, value):
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

		self.classinit()
	
	@classmethod
	def classinit(klass):
		if klass._escape_table:
			return

		d = {i: ("<Ctrl-" + chr(i + 0x41) + ">") for i in range(32)}
		del d[ord('\n')]
		d[ord('\b')] = '\\b'
		d[ord('\r')] = '\\r'
		d[ord('\v')] = '\\v'
		d[7] = '<BEL>'

		klass._escape_table = str.maketrans(d)

	@property
	def text(self):
		if not self.node.text:
			return ""
		return self.node.text.strip()

	def write(self, msg, level = None, nodeName = None):
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

class ConstructedJournalTest(JournalTest):
	def __init__(self, node):
		super().__init__(node)

		self.createChild("system-out")
		# child = node.createChild("system-out")
		# self.systemOut = JournalMessages(child)

		self.startTime = time.time()

	def setStatus(self, status):
		current = self.status
		if current is None:
			self.time = time.time() - self.startTime
		elif status != current:
			raise ValueError("status changes from {current} to {status}")

		self.status = status

	def logInfo(self, msg):
		self.system_out.write(msg, level = 'info')

	def logSuccess(self, msg):
		self.system_out.write(msg, level = 'info')
		self.setStatus('success')

	def logFailure(self, msg):
		self.system_out.write(msg, level = 'failure')

		if self.failure is None:
			child = self.createChild("failure")
			child.type = "randomFailure"
			child.message = msg
		self.setStatus('failure')

	def logError(self, msg):
		self.system_out.write(msg, level = 'error')
		self.setStatus('error')

	def logSkipped(self, msg):
		self.system_out.write(msg, level = 'skipped')
		self.setStatus('skipped')

	def logDisabled(self, msg):
		self.system_out.write(msg, level = 'disabled')
		self.setStatus('disabled')

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
		ListNodeSchema("testcase", JournalTest, ConstructedJournalTest),
	]

	def finish(self):
		self.clearStats()
		for test in self.testcase:
			if test.status is None:
				test.logError("BUG: test has no result")
			self.account(test.status)

class ConstructedJournalGroup(JournalGroup):
	def __init__(self, node):
		super().__init__(node)
		self.tests = 0

	def beginTest(self, name, description):
		self.tests += 1

		id = f"{self.package}.{name}"
		return self.createChild("testcase", classname = id, name = description)

class JournalRootNode(NodeWithStats):
	attributes = NodeWithStats.attributes + [
		AttributeSchema("name"),
	] + NodeWithStats.attributes
	children = [
		ListNodeSchema("testsuite", JournalGroup, ConstructedJournalGroup),
	]

	def __str__(self):
		return f"{self.__class__.__name__}(name = {self.name})"

	def beginGroup(self, name):
		return self.createChild("testsuite", package = name)

	def finish(self):
		self.clearStats()
		for suite in self.testsuite:
			suite.finish()
			self.accumulate(suite)

class Journal:
	def __init__(self, node = None, name = None):
		if node:
			self.root = JournalRootNode(node)
		else:
			if not name:
				name = "report"
			node = ET.Element("testsuites")
			self.root = JournalRootNode(node)
			self.root.name = name

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
		journal.root.finish()

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
		# FIXME: rename to id
		self.stats.package = suite.package
		self.properties = suite.properties.asDict()
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
