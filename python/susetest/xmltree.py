##################################################################
#
# Helper classes for writing XML documents that are somewhat
# more readable for the human user than what ElementTree normally
# produces.
#
# Copyright (C) 2015-2020 Olaf Kirch <okir@suse.com>
#
##################################################################

import xml.etree.ElementTree as ET
import xml.etree.ElementInclude as ElementInclude

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
	def __init__(self, name, childClass, attr_name = None):
		self.name = name
		self.attr_name = attr_name or name.replace('-', '_')
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

	def save(self, filename):
		import os

		tree = ET.ElementTree(self.node)

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

##################################################################
# Obsolete stuff, will go away
##################################################################
class XMLNode:
	def __init__(self, realnode, depth = 0):
		self.realnode = realnode
		self.depth = depth

	def tag(self):
		return self.realnode.tag

	def createChild(self, name):
		depth = self.depth + 1

		parent = self.realnode
		indentWS = "\n" + depth * " "
		if len(parent) == 0:
			parent.text = indentWS
		else:
			parent[-1].tail = indentWS

		child = ET.SubElement(parent, name)
		child.tail = "\n" + self.depth * " "

		return XMLNode(child, depth)

	def setAttributes(self, **kwargs):
		for name, value in kwargs.items():
			if value is None:
				continue
			self.realnode.set(name, str(value))

	def setText(self, value):
		self.realnode.text = value

class XMLTree:
	def __init__(self, name):
		self.root = XMLNode(ET.Element(name))

	def write(self, filename):
		import os

		tree = ET.ElementTree(self.root.realnode)
		tree.write(filename + ".new", "UTF-8")
		os.rename(filename + ".new", filename)
