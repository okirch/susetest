##################################################################
#
# Resource classes for susetest Driver
#
# Copyright (C) 2022 SUSE Linux GmbH
#
# The FileFormat base class defines an interface for
# file editors
#

import ipaddress

class FileFormatRegistry(object):
	_instance = None

	def __init__(self):
		self.formats = {}
		self.findFileFormats(globals())

	@classmethod
	def instance(klass):
		if klass._instance is None:
			klass._instance = klass()
		return klass._instance

	@classmethod
	def createEditor(klass, target, format, path):
		registry = klass.instance()

		format_klass = registry.lookupFormat(format)
		if format_klass is None:
			return None

		return FileEditor(target, path, format_klass())

	def lookupFormat(self, name):
		return self.formats.get(name)

	def findFileFormats(self, ctx):
		for format_klass in self._find_classes(ctx, FileFormat, "file_type"):
			self._registerFormat(format_klass)

	def _find_classes(self, ctx, baseKlass, required_attr = None):
		class_type = type(self.__class__)

		result = []
		for thing in ctx.values():
			if type(thing) is not class_type or not issubclass(thing, baseKlass):
				continue

			if required_attr and not hasattr(thing, required_attr):
				continue

			result.append(thing)
		return result

	@classmethod
	def registerFormat(klass, format_klass):
		klass.instance()._registerFormat(format_klass)

	def _registerFormat(self, format_klass):
		self.formats[format_klass.file_type] = format_klass

class FileEditor(object):
	def __init__(self, node, path, format):
		self.target = node
		self.path = path
		self.format = format

		self.rewriter = None

	def __str__(self):
		return f"{self.__class__.__name__}(node={self.target.name}, path={self.path})"

	def makeKey(self, *args, **kwargs):
		return self.format.makeKey(*args, **kwargs)

	def makeEntry(self, *args, **kwargs):
		return self.format.makeEntry(*args, **kwargs)

	def _createReader(self):
		return FileReader(self.target, self.path, self.format)

	def _createRewriter(self):
		return FileRewriter(self.target, self.path, self.format)

	def entries(self):
		reader = self._createReader()
		for e in reader.entries():
			yield e

	def lookupEntry(self, key = None, **kwargs):
		if key is None:
			key = self.makeKey(**kwargs)

		reader = self._createReader()
		for e in reader.entries():
			if isinstance(e, CommentOrOtherFluff):
				continue
			if key.matchEntry(e):
				return e

	def beginRewrite(self):
		if self.rewriter:
			raise ValueError(f"{self} already open for rewriting")

		self.rewriter = self._createRewriter()

	def commit(self):
		if not self.rewriter:
			raise ValueError(f"{self} not open for rewriting")

		self.rewriter.commit()
		self.rewriter = None

	def discard(self):
		self.rewriter = None

	def removeEntry(self, key = None, **kwargs):
		if not self.rewriter:
			raise ValueError(f"{self} not open for rewriting")

		if key is None:
			key = self.makeKey(**kwargs)

		self.rewriter.removeEntry(key)

	def addOrReplaceEntry(self, entry = None, **kwargs):
		if not self.rewriter:
			raise ValueError(f"{self} not open for rewriting")

		if entry is None:
			entry = self.makeEntry(**kwargs)

		# print(f"addOrReplaceEntry({entry})")
		self.rewriter.replaceEntry(entry)
		return

class FileReader(object):
	def __init__(self, target, path, format):
		self.target = target
		self.path = path
		self.format = format
		self.data = None

	def receive(self):
		if self.data is None:
			self.data = self.download()
		return self.data

	def download(self):
		node = self.target

		data = node.recvbuffer(self.path, user = "root", quiet = True)
		if not data:
			node.logError(f"unable to download {self.path}")

		return data

	def entries(self):
		data = self.receive()
		for e in self.format.entries(data):
			if not isinstance(e, CommentOrOtherFluff):
				yield e

class FileRewriter(FileReader):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.modified = False
		self.showDiff = True

	def removeEntry(self, key):
		return self.process(key.matchEntry, None)

	def replaceEntry(self, newEntry):
		return self.process(newEntry.shouldReplace, newEntry)

	def process(self, removeMatchFunc, newEntry):
		inputBuffer = self.receive()
		outputBuffer = bytearray()

		for e in self.format.entries(inputBuffer):
			writeEntry = e

			if isinstance(e, CommentOrOtherFluff):
				pass
			elif removeMatchFunc(e):
				# print(f"Replacing {writeEntry} with {newEntry}")
				writeEntry = newEntry
				newEntry = None

			if writeEntry:
				self.format.output(writeEntry, outputBuffer)

		if self.data != outputBuffer:
			self.data = outputBuffer
			self.modified = True

	def commit(self):
		import susetest

		node = self.target

		if not self.modified:
			node.logInfo(f"Not writing back {self.path}: content remains unmodified")
			return

		diff_orig = f"{self.path}.diff_orig"
		if self.showDiff:
			node.run(f"cp {self.path} {diff_orig}", quiet = True)

		# Always make sure we have a backup copy of the original file
		node.run(f"test -f {self.path}.orig || cp -p {self.path} {self.path}.orig", quiet = True)

		if not node.sendbuffer(self.path, self.data, user = "root", quiet = self.showDiff):
			node.logFailure(f"Failed store updated file {self.path}")
			return

		if self.showDiff:
			st = node.run(f"diff -u {diff_orig} {self.path}", quiet = True)
			if st.code == 0:
				node.logInfo(f"File {self.path} remains unchanged")
			elif st.code == 1:
				node.logInfo(f"Showing the difference between old and new {self.path}")
				for line in st.stdoutString.split("\n"):
					susetest.say(line)

			node.run(f"rm -f {diff_orig}", quiet = True)

		self.modified = False

class CommentOrOtherFluff:
	pass

class FileFormat(object):
	def __init__(self):
		pass

	def __str__(self):
		return "%s()" % self.__class__.__name__

	def makeKey(self, *args, **kwargs):
		return self.Key(*args, **kwargs)

	def makeEntry(self, *args, **kwargs):
		return self.Entry(*args, **kwargs)

	def entries(self, buffer):
		raise NotImplementedError()

class LineOrientedFileFormat(FileFormat):
	def receiveLines(self, data):
		if data is not None:
			data = data.decode('utf-8')

			# strip off trailing newline, else this will
			# make an empty line appear at the end of the file
			if data.endswith('\n'):
				data = data[:-1]
			for line in data.split('\n'):
				yield line

	def entries(self, buffer):
		for line in self.receiveLines(buffer):
			e = self.parseLineEntry(line)
			if e is not None:
				yield e

	class CommentLine(CommentOrOtherFluff):
		def __init__(self, line):
			self.line = line

		def format(self):
			return self.line

	def parseLineEntry(self, line):
		raise NotImplementedError(f"{self}")

	def output(self, e, buffer):
		line = e.format()
		if line is not None:
			if not line.endswith("\n"):
				line += "\n"
			buffer += line.encode('utf-8')

class HostsFile(LineOrientedFileFormat):
	file_type = "hosts"

	class Key:
		def __init__(self, name = None, addr = None):
			if not name and not addr:
				raise ValueError(f"refusing to create empty key")
			self.name = name
			self.addr = addr

			self.addr_type = None
			if addr:
				try:
					parsed_addr = ip_address.ipaddress(addr)
					self.addr_type = parsed_addr.__class__
				except:
					pass

		def __str__(self):
			return f"Host({self.addr}, {self.name})"

		def matchEntry(self, entry):
			if self.name and self.name != entry.name:
				return False
			if self.addr and self.addr != entry.addr:
				return False
			return True

	class Entry(Key):
		def __init__(self, name = None, addr = None, aliases = None, raw = None):
			super().__init__(name, addr)
			self.aliases = aliases or []
			self.raw = raw

		def __str__(self):
			return f"Host({self.addr}, {self.name}, aliases = {self.aliases})"

		def format(self):
			if self.raw:
				return self.raw
			words = [self.addr, self.name] + self.aliases
			return " ".join(words)

		def shouldReplace(self, entry):
			if self.addr == entry.addr:
				return True

			# if we're not an exact address match, at least the addr type
			# should match, so that we can have two entries for the same name,
			# one for v4 and one for v6.
			if self.addr_type != entry.addr_type:
				return False

			if self.name == entry.name:
				return True

			if self.name in entry.aliases:
				# FIXME: should we quietly remove our name from entry.aliases?
				pass

			return False

	def parseLineEntry(self, raw_line):
		if raw_line == "" or raw_line.startswith("#") or raw_line.isspace():
			return self.CommentLine(raw_line)

		i = raw_line.find('#')
		if i >= 0:
			line = raw_line[:i]
		else:
			line = raw_line

		w = line.split()
		if len(w) < 2:
			print(f"could not parse |{raw_line}|")
			return

		return self.Entry(name = w[1], addr = w[0], aliases = w[2:], raw = raw_line)
