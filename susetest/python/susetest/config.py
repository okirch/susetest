##################################################################
#
# Config file handling for susetest.
# This is way more complex than it needs to be.
#
# Copyright (C) 2014-2021 SUSE Linux GmbH
#
##################################################################

import suselog
import twopence
import time
import re
import sys
import os
import functools

class ConfigWrapper():
	def __init__(self, name, data):
		self.name = name
		self.data = data

		# Set the workspace
		self.workspace = self.data.workspace()
		if not self.workspace:
			print("Oops, no workspace defined. Using current directory")
			self.workspace = "."

		# Set the journal
		reportPath = self.data.report()
		if not reportPath:
			reportPath = self.workspace + "/junit-results.xml"
		self.journal = suselog.Journal(self.name, path = reportPath);


	def target(self, nodename):
		return Target(nodename, self)

	def target_spec(self, nodename):
		return self.data.node_target(nodename)

	def ipv4_address(self, nodename):
		return self.data.node_internal_ip(nodename)

	def ipv4_ext(self, nodename):
		return self.data.node_external_ip(nodename)

	def ipv6_address(self, nodename):
		try:
			return self.data.node_ip6(nodename)
		except:
			pass

		return None

def Config(name, **kwargs):
	filename = kwargs.get('filename')
	if not filename:
		# This does not really belong here...
		filename = os.getenv("TWOPENCE_CONFIG_PATH")
		if not filename:
			filename = "twopence.conf";

	try:
		import curly

		return ConfigWrapper(name, curly.Config(filename));
	except Exception as e:
		print(e)
		pass

	try:
		import testenv

		return ConfigWrapper(name, testenv.Testenv(**kwargs))
	except:
		pass

	raise RuntimeError("unable to create a valid config object")
	return None

class NodesFile:
	class Node:
		def __init__(self, name):
			self.name = name
			self.role = name
			self.repository = None
			self.installPackages = set()

	def __init__(self, path):
		self.nodes = []

		self.currentFile = path
		self.currentLine = 0
		self.currentNode = None
		with open(path, "r") as f:
			for l in f.readlines():
				self.currentLine += 1
				self.parseLine(l)

	def addNode(self, name):
		n = self.Node(name)
		self.nodes.append(n)
		return n

	def parseError(self, msg):
		return ValueError("%s:%d: parse error: %s" % (self.currentFile, self.currentLine, msg))

	def parseLine(self, l):
		i = l.find('#')
		if i >= 0:
			l = l[:i]

		l = l.strip()
		if not l:
			return

		words = l.split(maxsplit = 1)
		if len(words) != 2:
			raise self.parseError("expected \"key value\" statement")

		key = words[0]
		value = words[1].strip()

		if key == 'node':
			self.currentNode = self.addNode(value)
		elif self.currentNode is None:
			raise self.parseError("%s statement before first node" % key)
		elif key == 'repository':
			self.currentNode.repository = value
		elif key == 'role':
			self.currentNode.role = value
		elif key == 'install':
			self.currentNode.installPackages.add(value)
		else:
			raise self.parseError("unknown statement %s" % key)

