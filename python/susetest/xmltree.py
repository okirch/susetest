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
