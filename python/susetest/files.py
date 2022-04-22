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
import shutil
import shlex
import twopence
import os

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
		return klass.createEditorForProxy(RemoteFileProxy(target, path), format)

	@classmethod
	def createHostEditor(klass, target, format, path):
		return klass.createEditorForProxy(LocalFileProxy(target, path), format)

	@classmethod
	def createEditorForProxy(klass, proxy, format):
		registry = klass.instance()

		format_klass = registry.lookupFormat(format)
		if format_klass is None:
			return None

		return FileEditor(proxy, format_klass())

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

class FileProxy:
	def __init__(self, target, path):
		self.target = target
		self.path = path

	def logFailure(self, msg):
		self.target.logFailure(msg)

	def logError(self, msg):
		self.target.logError(msg)

	def logInfo(self, msg):
		self.target.logInfo(msg)

	@property
	def isLocal(self):
		return isinstance(self, LocalFileProxy)

	@property
	def parentDirectory(self):
		parent = os.path.dirname(self.path)
		if self.path == parent:
			raise ValueError(f"No parent directory for \"{self.path}\"")

		return self.__class__(self.target, parent)

	def createFile(self, name):
		assert('/' not in name)

		path = os.path.join(self.path, name)
		return self.__class__(self.target, path)

class LocalFileProxy(FileProxy):
	def __init__(self, target, path):
		super().__init__(target, path)

	def __str__(self):
		return f"host-path={self.path}"

	def read(self, quiet = False):
		with open(self.path, "rb") as f:
			data = f.read()
		return data

	def write(self, data, quiet = False):
		temp = f"{self.path}.new"
		with open(temp, "wb") as f:
			f.write(data)

			self.copyDAC(temp)
			os.rename(temp, self.path)
		return True

	def copyTo(self, destPath):
		shutil.copyfile(self.path, destPath)

	def remove(self, destPath):
		if os.path.exists(destPath):
			os.remove(destPath)

	def copyToOnce(self, destPath):
		if not os.path.exists(destPath):
			self.copyTo(destPath)

	def copyDAC(self, destPath):
		if os.path.exists(self.path):
			mode = os.stat(self.path).st_mode
			os.chmod(destPath, mode)
			os.system(f"sudo chown --reference {self.path} {destPath}")
			os.system(f"type -p chcon && sudo chcon --reference {self.path} {destPath}")
		else:
			os.system(f"sudo chown root.root {destPath}")

	def displayDiff(self, origPath):
		import susetest

		with os.popen(f"diff -u {origPath} {self.path}") as f:
			output = f.read().split("\n")
			status = f.close()
			if not status:
				exit_code = 0
			elif os.WIFEXITED(status):
				exit_code = os.WEXITSTATUS(status)
			else:
				self.logFailure("diff command crashed")
				return

		if exit_code == 0:
			self.logInfo(f"File {self.path} remains unchanged")
		elif exit_code == 1:
			self.logInfo(f"Showing the difference between old and new {self.path}")
			for line in output:
				susetest.say(line)

class RemoteFileProxy(FileProxy):
	def __init__(self, target, path):
		super().__init__(target, path)

	def __str__(self):
		return f"node={self.target.name}, path={self.path}"

	def read(self, **kwargs):
		node = self.target

		data = node.recvbuffer(self.path, user = "root", **kwargs)
		if not data:
			self.logFailure(f"Failed to download {self.path}")

		return data

	def write(self, data, **kwargs):
		node = self.target
		if not node.sendbuffer(self.path, data, user = "root", **kwargs):
			node.logFailure(f"Failed to store updated file {self.path}")
			return False

		return True

	def copyTo(self, destPath):
		st = self.target.run(f"cp {self.path} {destPath}", quiet = True)
		if not st:
			self.logFailure(f"Failed to copy {self.path} to {destPath}: {st.message}")
		return bool(st)

	def remove(self, destPath):
		st = self.target.run(f"rm -f {destPath}", quiet = True)
		if not st:
			self.logFailure(f"Failed to remove {destPath}: {st.message}")
		return bool(st)

	def copyToOnce(self, destPath):
		st = self.target.run(f"test -f {destPath} || cp -p {self.path} {destPath}", quiet = True)
		if not st:
			self.logFailure(f"Failed to back up {self.path} to {destPath}: {st.message}")
		return bool(st)

	def displayDiff(self, origPath):
		import susetest

		st = self.target.run(f"diff -u {origPath} {self.path}", quiet = True)
		if st.code == 0:
			self.logInfo(f"File {self.path} remains unchanged")
		elif st.code == 1:
			self.logInfo(f"Showing the difference between old and new {self.path}")
			for line in st.stdoutString.split("\n"):
				susetest.say(line)

class FileEditor(object):
	def __init__(self, proxy, format):
		self.proxy = proxy
		self.format = format

		self.rewriter = None

	def __str__(self):
		return f"{self.__class__.__name__}({self.proxy})"

	def makeKey(self, *args, **kwargs):
		return self.format.makeKey(*args, **kwargs)

	def makeEntry(self, *args, **kwargs):
		return self.format.makeEntry(*args, **kwargs)

	def _createReader(self):
		return FileReader(self.proxy, self.format)

	def _createRewriter(self):
		return FileRewriter(self.proxy, self.format)

	def entries(self):
		reader = self._createReader()
		for e in reader.entries():
			yield e

	def lookupEntry(self, key = None, **kwargs):
		if key is None:
			key = self.makeKey(**kwargs)

		reader = self.rewriter
		if reader is None:
			reader = self._createReader()

		for e in reader.entries():
			if isinstance(e, CommentOrOtherFluff):
				continue
			if key.matchEntry(e):
				return e

	def lookupEntryNested(self, keys = []):
		if not keys:
			raise KeyError("lookupEntryNested: empty keys argument")

		reader = self.rewriter
		if reader is None:
			reader = self._createReader()

		haystack = [reader]
		for key in keys:
			found = []
			for bale in haystack:
				for e in bale.entries():
					if key.matchEntry(e):
						found.append(e)
			haystack = found

		return haystack

	def beginRewrite(self):
		if self.rewriter:
			raise ValueError(f"{self} already open for rewriting")

		self.rewriter = self._createRewriter()

	def commit(self):
		if not self.rewriter:
			raise ValueError(f"{self} not open for rewriting")

		self.rewriter.commit()
		self.rewriter = None
		return True

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
		else:
			# zap the cached representation of the entry; force
			# a rebuild
			entry.invalidate()

		# print(f"addOrReplaceEntry({entry})")
		self.rewriter.replaceEntry(entry)
		return

class FileReader(object):
	def __init__(self, proxy, format):
		self.proxy = proxy
		self.format = format
		self.data = None
		self._cache = None

	@property
	def path(self):
		return self.proxy.path

	def receive(self):
		if self.data is None:
			self.data = self.proxy.read(quiet = True)
		return self.data

	def entries(self):
		if self.format.suggest_caching:
			if self._cache is None:
				data = self.receive()
				self._cache = list(self.format.entries(data))
			it = self._cache
		else:
			data = self.receive()
			it = self.format.entries(data)

		for e in it:
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

			if removeMatchFunc(e):
				# print(f"Replacing {writeEntry} with {newEntry}")
				writeEntry = newEntry
				newEntry = None

			if writeEntry:
				self.format.output(writeEntry, outputBuffer)

		if newEntry:
			self.format.output(newEntry, outputBuffer)

		if self.data != outputBuffer:
			self.data = outputBuffer
			self.modified = True

	def commit(self):
		proxy = self.proxy

		# The file format has asked us to cache the file's content.
		# Most likely it's a block oriented format that uses the
		# find-entry-and-update protocol rather than addOrReplaceEntry()
		if self._cache:
			if any(e.modified for e in self._cache):
				self.modified = True

				# update our raw file representation
				data = bytearray()
				for e in self._cache:
					self.format.output(e, data)
				self.data = data

		if not self.modified:
			proxy.logInfo(f"Not writing back {self.path}: content remains unmodified")
			return True

		diff_orig = f"{self.path}.diff_orig"
		if self.showDiff:
			proxy.copyTo(diff_orig)

		# Always make sure we have a backup copy of the original file
		proxy.copyToOnce(f"{self.path}.orig")

		if not proxy.write(self.data, quiet = self.showDiff):
			return False

		if self.showDiff:
			proxy.displayDiff(diff_orig)
			proxy.remove(diff_orig)

		self.modified = False
		return True

class CommentOrOtherFluff:
	modified = False

class FileFormat(object):
	suggest_caching = False

	class CommentLine(CommentOrOtherFluff):
		def __init__(self, line):
			self.line = line

		def format(self):
			return self.line

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

##################################################################
# Helper class to process files line by line.
# It offers two modes of processing
#  - straightforward iteration:
#	for line in lineProcess:
#		do stuff
#  - wrapped in a lexical analyzer
#	line = lineProcess.next()
#	if line is None:
#		return EOF
#	feed line to lexer
##################################################################
class LineByLineReader:
	def __init__(self, data):
		data = data.decode('utf-8')

		# strip off trailing newline, else this will
		# make an empty line appear at the end of the file
		if data.endswith('\n'):
			data = data[:-1]
		self._lines = data.split('\n')

		self._iter = iter(self._lines)

		self._saved = None
		self._done = False

	def __bool__(self):
		if not self._done and self._saved is None:
			self._saved = self.readLine()
		return not self._done

	def __iter__(self):
		return iter(self._lines)

	def nextLine(self):
		line = self._saved
		if line:
			self._saved = None
		else:
			line = self.readLine()
		return line

	def readLine(self):
		try:
			return next(self._iter)
		except StopIteration:
			self._done = True
			return None

	def save(self, line):
		assert(self._saved is None)
		self._saved = line

class LineOrientedFileFormat(FileFormat):
	def entries(self, buffer):
		for line in LineByLineReader(buffer):
			e = self.parseLineEntry(line)
			if e is not None:
				yield e

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
			if isinstance(entry, CommentOrOtherFluff):
				return False

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

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw:
				return self.raw
			words = [self.addr, self.name] + self.aliases
			return " ".join(words)

		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

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
			twopence.error(f"could not parse |{raw_line}|")
			return

		return self.Entry(name = w[1], addr = w[0], aliases = w[2:], raw = raw_line)

class FstabFile(LineOrientedFileFormat):
	file_type = "fstab"

	class Key:
		def __init__(self, fsname = None, mountpoint = None):
			if not fsname and not mountpoint:
				raise ValueError(f"refusing to create empty key")
			self.fsname = fsname
			self.mountpoint = mountpoint

		def __str__(self):
			return f"Filesystem({self.fsname}, {self.mountpoint})"

		def matchEntry(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			if self.fsname and self.fsname != entry.fsname:
				return False
			if self.mountpoint and self.mountpoint != entry.mountpoint:
				return False
			return True

	class Entry(Key):
		def __init__(self, fsname, mountpoint, fstype, options = None, freq = "0", passno = "0", raw = None):
			super().__init__(fsname, mountpoint)
			self.fstype = fstype
			self.options = options or "defaults"
			self.freq = freq
			self.passno = passno
			self.raw = raw

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw:
				return self.raw
			return f"{self.fsname} {self.mountpoint} {self.fstype} {self.options} {self.freq} {self.passno}"

		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			if self.mountpoint == entry.mountpoint or \
			   self.fsname == entry.fsname:
				return True
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
		if len(w) != 6:
			twopence.error(f"could not parse |{raw_line}|")
			return

		return self.Entry(*w, raw = raw_line)

class LinesWithColonFileFormat(LineOrientedFileFormat):
	entry_type = None

	class EntryType:
		def __init__(self, name, key_fields, entry_fields, display_fields = None):
			self.name = name
			self.key_fields = key_fields
			self.entry_fields = entry_fields
			self.num_entry_fields = len(entry_fields)
			self.display_fields = display_fields or entry_fields

	class KeyOrEntryBase:
		def initialize(self, fields, *args, **kwargs):
			for attr_name in fields:
				setattr(self, attr_name, None)
			for attr_name, value in zip(fields, args):
				setattr(self, attr_name, value)
			for attr_name, value in kwargs.items():
				assert(attr_name in fields)
				setattr(self, attr_name, value)

		def render(self, name, fields):
			attrs = []
			for attr_name in fields:
				attrs.append("%s=%s" % (attr_name, getattr(self, attr_name)))
			return "%s(%s)" % (name, ", ".join(attrs))

		def has_nonempty_attr(self, fields):
			for attr_name in fields:
				if getattr(self, attr_name) is not None:
					return True
			return False

	class Key(KeyOrEntryBase):
		def __init__(self, type, *args, **kwargs):
			self._type = type
			if not args and not kwargs:
				raise ValueError(f"refusing to create empty key")
			self.initialize(type.key_fields, *args, **kwargs)

		def __str__(self):
			type = self._type
			return self.render(type.name, type.key_fields)

		def matchEntry(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			for attr_name in self._type.key_fields:
				key_value = getattr(self, attr_name)
				if key_value is None:
					continue

				if key_value != getattr(entry, attr_name):
					return False

			return True

	class Entry(KeyOrEntryBase):
		def __init__(self, type, *args, raw = None, **kwargs):
			self._type = type
			self.raw = raw

			self.initialize(type.entry_fields, *args, **kwargs)

		def __str__(self):
			type = self._type
			return self.render(type.name, type.display_fields)

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw:
				return self.raw

			type = self._type

			words = []
			for attr_name in type.entry_fields:
				words.append(getattr(self, attr_name) or "")

			return ":".join(words)

	def makeKey(self, *args, **kwargs):
		return self.Key(self.entryType, *args, **kwargs)

	def makeEntry(self, *args, **kwargs):
		return self.Entry(self.entryType, *args, **kwargs)

	def entryFromLine(self, raw_line):
		w = raw_line.split(":")
		if len(w) != self.entryType.num_entry_fields:
			twopence.error(f"could not parse |{raw_line}|")
			return

		return self.Entry(self.entryType, raw = raw_line, *w)

class PasswdFile(LinesWithColonFileFormat):
	file_type = "passwd"
	entryType = LinesWithColonFileFormat.EntryType("PWENT",
		key_fields = ["name", "uid"],
		entry_fields = [ "name", "passwd", "uid", "gid", "gecos", "homedir", "shell", ],
		display_fields = [ "name", "uid", "shell",])

	class Entry(LinesWithColonFileFormat.Entry):
		def get_gecos_field(self, index):
			if not self.gecos:
				return None
			fields = self.gecos.split(',')
			if index >= len(fields):
				return None
			return fields[index]

		@property
		def gecos_fullname(self):
			return self.get_gecos_field(0)

		@property
		def gecos_room(self):
			return self.get_gecos_field(1)

		@property
		def gecos_home_phone(self):
			return self.get_gecos_field(3)

		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	def parseLineEntry(self, raw_line):
		# Transparently handle NIS entries
		if raw_line.startswith("+") or raw_line.startswith("-"):
			return self.CommentLine(raw_line)

		return self.entryFromLine(raw_line)

class ShadowFile(LinesWithColonFileFormat):
	file_type = "shadow"
	entryType = LinesWithColonFileFormat.EntryType("SPWENT",
		key_fields = ["name"],
		entry_fields = [ "name", "passwd", "last_change", "min", "max", "warn", "inactive", "expire", ],
		display_fields = [ "name", "uid", ])

	class Entry(LinesWithColonFileFormat.Entry):
		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	def parseLineEntry(self, raw_line):
		# Transparently handle NIS entries
		if raw_line.startswith("+") or raw_line.startswith("-"):
			return self.CommentLine(raw_line)

		return self.entryFromLine(raw_line)

class GroupFile(LinesWithColonFileFormat):
	file_type = "group"
	entryType = LinesWithColonFileFormat.EntryType("GRP",
		key_fields = ["name", "gid"],
		entry_fields = [ "name", "passwd", "gid", "mem" ],
		display_fields = [ "name", "gid", ])

	class Entry(LinesWithColonFileFormat.Entry):
		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	def parseLineEntry(self, raw_line):
		# Transparently handle NIS entries
		if raw_line.startswith("+") or raw_line.startswith("-"):
			return self.CommentLine(raw_line)

		return self.entryFromLine(raw_line)

class LinesWithKeyValueFileFormat(LineOrientedFileFormat):
	class Key:
		def __init__(self, name = None):
			if not name:
				raise ValueError(f"refusing to create empty key")
			self.name = name

		def __str__(self):
			return f"Key({self.name})"

		def matchEntry(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	class Entry:
		def __init__(self, name = None, value = None, raw = None):
			self.name = name
			self.value = value
			self.raw = raw

		def __str__(self):
			return f"Entry({self.name}, {self.value})"

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw:
				return self.raw
			return f"{self.name} {self.value}"

		def shouldReplace(self, entry):
			if isinstance(entry, LineOrientedFileFormat.CommentLine):
				# Check if the line is a commented out entry for this keyword, as in
				#    #Foobar value yadda yadda
				line = entry.line
				if line.startswith("#"):
					words = line[1:].split()
					if words and words[0] == self.name:
						return True

			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	def parseLineEntry(self, raw_line):
		if raw_line == "" or raw_line.isspace() or raw_line.startswith("#"):
			return self.CommentLine(raw_line)

		i = raw_line.find('#')
		if i >= 0:
			line = raw_line[:i]
		else:
			line = raw_line

		w = line.split(maxsplit = 1)
		if len(w) < 2:
			twopence.error(f"could not parse |{raw_line}|")
			return

		return self.Entry(raw = raw_line, *w)

class SSHConfigFile(LinesWithKeyValueFileFormat):
	file_type = "ssh-config-file"

class ShadowLoginDefsFile(LinesWithKeyValueFileFormat):
	file_type = "shadow-login-defs"

##################################################################
# Files that contain lines with a single value on it, such as
# /etc/shells
##################################################################
class ListFileFormat(LineOrientedFileFormat):
	file_type = "list-file"

	class Key:
		def __init__(self, name = None):
			if not name:
				raise ValueError(f"refusing to create empty key")
			self.name = name

		def __str__(self):
			return f"Key({self.name})"

		def matchEntry(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	class Entry:
		def __init__(self, name = None, raw = None):
			self.name = name
			self.raw = raw

		def __str__(self):
			return f"Entry({self.name})"

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw:
				return self.raw
			return f"{self.name}"

		def shouldReplace(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			return self.name == entry.name

	def parseLineEntry(self, raw_line):
		if raw_line == "" or raw_line.isspace() or raw_line.startswith("#"):
			return self.CommentLine(raw_line)

		return self.Entry(raw = raw_line, name = raw_line)

##################################################################
# FileTokenizer class.
# Processes a file line by line, returning a mix of tokens
# and comment lines
#
# The main entry point is getToken(), which returns one of
#	None: EOF
#	str: a string token
#	CommentLine: a line containing a comment
#
# The caller is free to ignore comment lines, or use them any way
# they wish.
#
# Note: depending on the actual file, this may return comment lines
# in the middle of a file entry or block, in which case it should
# probably be ignored:
#
#	long-entry a b c
#		# we don't want to do D today
# 		# D
#		E F G;
#
##################################################################
class FileTokenizer:
	def __init__(self, lineReader):
		self.lineReader = lineReader

		self._lexer = None
		self._raw = []
		self._peek = None

	def __bool__(self):
		return bool(self.lineReader)

	def peekToken(self):
		if self._peek is None:
			self._peek = self.getToken()
		return self._peek

	def getIndent(self):
		assert(self._raw)

		current_line = self._raw[-1]
		indent = ""
		for c in current_line:
			if not c.isspace():
				break
			indent += c
		return indent

	def getRaw(self):
		raw = "\n".join(self._raw)
		self._raw = []
		return raw

	# INTERNAL.
	# The following implementation of getToken() creates a new lexical analyzer
	# for each line of file.
	def getToken(self):
		token = self._peek
		if token is not None:
			self._peek = None
			return token

		while True:
			if self._lexer is not None:
				token = self.nextToken(self._lexer)
				if token is not None:
					return token
				self._lexer = None

			raw_line = self.lineReader.nextLine()
			if raw_line is None:
				return None

			semicooked = self.stripComment(raw_line)
			if not semicooked:
				return FileFormat.CommentLine(raw_line.rstrip("\n"))

			# Create a new lexical analyzer for this line
			self._lexer = self.newLexer(semicooked)
			self._raw.append(raw_line)

##################################################################
# Files with some sort of block structure
# For the time being, this is very much geared towards nginx.conf
##################################################################
class BlockOrientedFileFormat(FileFormat):
	def parseLineEntry(self, line):
		raise NotImplementedError(f"{self}")

	def output(self, e, buffer):
		line = e.format()
		if line is not None:
			if not line.endswith("\n"):
				line += "\n"
			buffer += line.encode('utf-8')

	class Key:
		def __init__(self, words = []):
			if not words:
				raise KeyError(f"refusing to create empty key")
			if type(words) == str:
				words = [words]
			self.words = words
			self.len = len(words)

		def __str__(self):
			return f"Key({' '.join(self.words)})"

		def matchEntry(self, entry):
			if isinstance(entry, CommentOrOtherFluff):
				return False

			# If the entry's key length is known, check that we are
			# specific enough.
			# For file formats like nginx.conf, the key length is not really
			# easy to determine, so we leave it unset.
			if entry.key_length is not None and entry.key_length != self.len:
				return False

			return entry._words[:self.len] == self.words

	class Entry:
		# If a file format knows exactly what the key length of an
		# entry is, it should set entry.key_length.
		# This will be used by key.matchEntry().
		key_length = None

		# this should be set by derived classes
		entry_type = None

		def __init__(self, words, raw = None, indent = ""):
			if type(words) == str:
				words = [words]
			assert(len(words))
			self._words = words
			self.raw = raw
			self.indent = indent
			self._modified = False

		@property
		def modified(self):
			return self._modified

		@property
		def name(self):
			return self._words[0]

		@property
		def values(self):
			# Beware: callers may modify the object we return here. Whatever
			# they do with it, we do not want that to modify Entry.values()
			return self._words[1:]

		@values.setter
		def values(self, values):
			if type(values) == str:
				values = [values]
			self._words = [self.name] + values
			self._modified = True

		@property
		def value(self):
			if len(self._words) != 2:
				raise KeyError(f"Cannot return single value for multi-word entry {self}")
			return self._words[1]

		@value.setter
		def value(self, value):
			if len(self._words) != 2:
				raise KeyError(f"Cannot set single value for multi-word entry {self}")
			self._words[1] = value

		def __str__(self):
			return f"Entry({' '.join(self._words)})"

		def invalidate(self):
			self.raw = None

		def format(self):
			if self.raw and not self._modified:
				return self.raw
			return self.entry_type.formatEntry(self)

		def shouldReplace(self, entry):
			return self.entry_type.shouldReplaceEntry(self, entry)

	class Block(Entry):
		# this should be set by derived classes
		entry_type = None

		def __init__(self, *args, **kwargs):
			super().__init__(*args, **kwargs)
			self._entries = []

		def __str__(self):
			return f"Block({' '.join(self._words)})"

		@property
		def modified(self):
			return self._modified or any(e.modified for e in self._entries)

		def addEntry(self, e):
			self._entries.append(e)

		def validateKey(self, key):
			if type(key) in (str, list, tuple):
				key = self.entry_type.makeKey(key)
			return key

		def hasEntry(self, key):
			for e in self._entries:
				if key.matchEntry(e):
					return True

		def createBlock(self, key):
			block = self.entry_type.createBlock(key)
			self._entries.append(block)
			self.copyIndentFromPredecessor(block)
			return block

		def matchBlocks(self, key):
			key = self.validateKey(key)

			for e in self._entries:
				if isinstance(e, BlockOrientedFileFormat.Block) and key.matchEntry(e):
					yield e

		def getProperty(self, key):
			key = self.validateKey(key)

			found = None
			for e in self._entries:
				if isinstance(e, BlockOrientedFileFormat.Entry) and key.matchEntry(e):
					if found:
						raise KeyError(f"{self}: property {key} is not unique")
					found = e
			return found

		def setProperty(self, key, value = None):
			if type(value) == list:
				values = value
			elif value is not None:
				values = [value]
			else:
				values = [""]

			prop = self.getProperty(key)
			if prop is not None:
				prop.values = values
				return

			words = []
			if type(key) == str:
				words.append(key)
			else:
				words += key
			words += values

			prop = self.entry_type.createEntry(words)
			self._entries.append(prop)

			self.copyIndentFromPredecessor(prop)
			return prop

		# we want to iterate over block entries just the way we iterate over
		# the file:
		#	for e in reader.entries():
		#	for e in block.entries():
		def entries(self):
			return self._entries

		def format(self):
			return self.entry_type.formatBlock(self)

		def shouldReplace(self, entry):
			self.entry_type.shouldReplaceBlock()

		def replaceEntry(self, e):
			raise NotImplementedError()

		def copyIndentFromPredecessor(self, newEntry):
			# Set the indent of the new property to match the preceding
			# entry (excluding comments and such). If there are none,
			# choose an indent that is 4 spaces deeper than the current block
			indent = self.indent + "    "
			for entry in self._entries:
				if isinstance(entry, NginxConfigFileFormat.Entry):
					if newEntry is entry:
						break
					indent = entry.indent

			newEntry.indent = indent


##################################################################
# A file format that uses curly braces for blocks, and ; as
# line delimiter
##################################################################
class BlockFileFormatWithBraces(BlockOrientedFileFormat):
	OPEN_BRACE	= '{'
	CLOSE_BRACE	= '}'
	SEMICOLON	= ';'

	def parse(self, scanner):
		words = []
		while True:
			token = scanner.getToken()
			if token is None:
				return None

			# comments in the middle of a declaration are ignored.
			# If they appear by themselves, we return them as is
			if isinstance(token, CommentOrOtherFluff):
				if not words:
					return token
				continue

			# Save the indent that we encountered at the start of the line.
			# Needed for reasonable formatting.
			if not words:
				indent = scanner.getIndent()

			if token == self.OPEN_BRACE:
				# print(f"Creating block {words}")
				block = self.Block(words, raw = scanner.getRaw(), indent = indent)
				while scanner.peekToken() != self.CLOSE_BRACE:
					entry = self.parse(scanner)
					if entry is None:
						raise ValueError(f"premature end of file while parsing block {block}")
					block.addEntry(entry)

				# consume the closing brace
				scanner.getToken()
				scanner.getRaw()

				return block

			if token == self.CLOSE_BRACE:
				raise ValueError("Unexpected closing brace")

			if token == self.SEMICOLON:
				# print(f"Creating entry {words}")
				return self.Entry(words, raw = scanner.getRaw(), indent = indent)

			words.append(token)


##################################################################
# Process nginx.conf
##################################################################
class NginxConfigFileFormat(BlockFileFormatWithBraces):
	file_type = "nginx-config"
	suggest_caching = True

	class EntryFormat:
		def makeKey(self, key):
			return NginxConfigFileFormat.Key(key)

		def _formatEntryPartial(self, entry):
			words = map(shlex.quote, entry._words)
			return f"{entry.indent}{' '.join(words)}"

		def formatEntry(self, entry):
			words = map(shlex.quote, entry._words)
			return self._formatEntryPartial(entry) + NginxConfigFileFormat.SEMICOLON

		def shouldReplaceEntry(self, entry, other):
			if isinstance(other, LineOrientedFileFormat.CommentLine):
				# Check if the line is a commented out entry for this keyword, as in
				#    #Foobar value yadda yadda
				line = other.line
				if line.startswith("#"):
					words = line[1:].split()
					if words and words[0] == entry.name:
						return True

			if isinstance(other, CommentOrOtherFluff):
				return False

			return entry.name == other.name

		def formatBlock(self, block):
			result = []
			if block.raw:
				line = block.raw
			else:
				line = self._formatEntryPartial(block) + " " + NginxConfigFileFormat.OPEN_BRACE
			result.append(line)

			for e in block.entries():
				result.append(e.format())
			result.append(block.indent + NginxConfigFileFormat.CLOSE_BRACE)
			return "\n".join(result)

		def shouldReplaceBlock(self, entry, other):
			return False

		def createEntry(self, words):
			return NginxConfigFileFormat.Entry(words)

		def createBlock(self, words):
			return NginxConfigFileFormat.Block(words)

	class Entry(BlockOrientedFileFormat.Entry):
		def __init__(self, *args, **kwargs):
			if self.__class__.entry_type is None:
				self.__class__.entry_type = NginxConfigFileFormat.EntryFormat()

			super().__init__(*args, **kwargs)

	class Block(BlockOrientedFileFormat.Block):
		def __init__(self, *args, **kwargs):
			if self.__class__.entry_type is None:
				self.__class__.entry_type = NginxConfigFileFormat.EntryFormat()

			super().__init__(*args, **kwargs)

	class Tokenizer(FileTokenizer):
		def __init__(self, lines):
			super().__init__(lines)

		def nextToken(self, lexer):
			return lexer.get_token()

		def stripComment(self, raw_line):
			i = raw_line.find('#')
			if i >= 0:
				return raw_line[:i].strip()
			return raw_line.strip()

		def newLexer(self, semicooked):
			sh = shlex.shlex(semicooked, posix = True, punctuation_chars = True)
			sh.escape = ""
			sh.wordchars += "\\$?:"
			return sh

	def entries(self, buffer):
		scanner = self.Tokenizer(LineByLineReader(buffer))

		while True:
			e = self.parse(scanner)
			if e is None:
				break

			yield e
