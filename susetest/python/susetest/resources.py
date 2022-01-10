##################################################################
#
# Resource classes for susetest Driver
#
# Copyright (C) 2021 SUSE Linux GmbH
#
# A resource type is a class, specifying a name via a class
# attribute. No manual registration is required; the test Driver
# will auto-detect all Resource classes in this module as well
# as the caller's context.
#
# Test scripts can request resources at any time using
# driver.requestResource() and driver.optionalResource().
# If the call happens outside a test group, the actual
# acquisition of the resources is postponed until the next
# test group begins.
#
# Common resources
#  ipv4-address
#  ipv6-address
#	Network address of a SUT. The value of resource can
#	be accessed via resource.value
#
#  test-user
#	Ensures that a user account for testing purposes
#	exists. The user's login name can be accessed
#	via resource.value
#
# Resource classes to derive from
#  ExecutableResource
#	When acquired, this resource will search for a
#	given executable in a predefined set of directories
#	on the SUT.
#	The name of the executable will be taken from the
#	optional class attribute executable, or, if not present,
#	from the resource class' name.
#
#	Optionally, you can specify a "package" class attribute.
#	If the executable cannot be found, the resource will
#	attempt to install the indicated package, and make another
#	attempt at locating the executable.
#
#	If found, the path of the executable is available in
#	the .path attribute
#
#	The class provides a run() method, which invokes the
#	command with the arguments provided. Any optional
#	keyword arguments will be passed to the run() method
#	of susetest.Target:
#
#	Example:
#	  class RpcinfoExecutableResource(ExecutableResource):
#		name = "rpcinfo"
#
#	rpcinfo = d.requireResource("rpcinfo", "client")
#	...
#	rpcinfo.run("-p", user = "nobody")
#
#  ServiceResource
#	When acquired, this resource will enable and start a service
#	(via systemd). In addition, it offers helper functions to
#	obtain runtime information on the server process, such as
#	its pid or uid.
#
#	Optionally, you can specify a "package" class attribute.
#	If one or more of the systemd units cannot be found, the
#	resource will install the indicated package before trying
#	to enable and start all services.
#
#	Example:
#	  class RpcbindServiceResource(ServiceResource):
#	        name = "rpcbind"
#	        daemon_path = "/sbin/rpcbind"
#	        systemd_unit = "rpcbind.service"
#	        systemd_activate = ["rpcbind.socket"]
#
#	rpcbind = d.requireResource("rpcbind", "server")
#	...
#	print("rpcbind runs as %s" % rpcbind.user)
#
#  UserResource
#	When acquired, this resource will check for the user
#	account indicated by resource.login. If it does not
#	exist, it will try to create the login (along with its
#	home directory).
#
#	If the class has an password attribute, the newly created
#	account's password will be set to this.
#
#	In addition, the resource class provides these properties:
#	 uid, gid, home
#		string value
#	 groups
#		list of strings
#	 password
#		the clear-text password (if defined by the class)
#
#	If the account does not exist, these properties return
#	None
#
#  FileResource
#	This is primarily intended to handle variation between
#	platforms. For example, one OS release may use ISC ntp,
#	which places its config and key files in one location,
#	and another OS release may use chrony, which places
#	them in some other location.
#
##################################################################

import susetest
import suselog
import inspect
import os
import curly
import sys
import re

class Resource:
	STATE_INACTIVE = 0
	STATE_ACTIVE = 1

	def __init__(self, target, mandatory = False):
		self.target = target
		self.mandatory = mandatory
		self.state = Resource.STATE_INACTIVE

	@property
	def is_active(self):
		return self.state == Resource.STATE_ACTIVE

	def __str__(self):
		return "%s on %s" % (self.describe(), self.target.name)

	def describe(self):
		return self.name

	@classmethod
	def createDefaultInstance(klass, node, resourceName):
		return None

class StringValuedResource(Resource):
	resource_type = "string"

	attributes = {
		'value'			: str,
	}

	def __init__(self, value, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.value = value

	@property
	def is_present(self):
		return self.value is not None

	def describe(self):
		return "%s=\"%s\"" % (self.name, self.value)

	def acquire(self, driver):
		self.target.logInfo("%s = %s" % (self.name, self.value))
		return True

	def release(self, driver):
		return True

	@classmethod
	def createDefaultInstance(klass, node, resourceName):
		return ConcreteStringValuedResource(node, resourceName)

class ResourceAddressIPv4(StringValuedResource):
	name = "ipv4_address"

	def __init__(self, *args, **kwargs):
		super().__init__(None, *args, **kwargs)
		self.value = self.target.ipv4_addr

class ResourceAddressIPv6(StringValuedResource):
	name = "ipv6_address"

	def __init__(self, *args, **kwargs):
		super().__init__(None, *args, **kwargs)
		self.value = self.target.ipv6_addr

class ConcreteStringValuedResource(StringValuedResource):
	def __init__(self, target, name, value = None):
		self.name = name
		super().__init__(value, target)

	def acquire(self, driver):
		return True

class PackageBackedResource(Resource):
	package = None

	def __init__(self, *args, **kwargs):
		assert('package' in self.__class__.attributes)
		super().__init__(*args, **kwargs)

	# Default implementation for PackageBackedResource.acquire
	def acquire(self, driver):
		print("acquire %s; package %s" % (self, self.package))
		if self.detect():
			return True

		if not self.tryInstallPackage("resource %s not present" % self):
			return False

		if self.detect():
			return True

		self.target.logError("resource %s not present" % self)
		return False

	# Default implementation for PackageBackedResource.release
	def release(self, driver):
		return True

	def tryInstallPackage(self, errmsg):
		node = self.target

		if not self.package:
			node.logError(errmsg)
			return False

		susetest.say("%s, trying to install package %s" % (errmsg, self.package))
		if not self.installPackage(node, self.package):
			node.logError("Failed to install %s on %s" % (self.package, node.name))
			return False

		if not self.package:
			node.logError(errmsg)
			return False

		return True

	def installPackage(self, node, package):
		# for now, only zypper, sorry
		st = node.run("zypper in -y %s" % package, user = "root")
		return bool(st)

class UserResource(Resource):
	resource_type = "user"

	attributes = {
		'password'		: str,
	}

	password = None
	encrypted_password = None

	def __init__(self, *args, **kwargs):
		assert(self.is_valid_user_class())

		super().__init__(*args, **kwargs)

		self._uid = None
		self._gid = None
		self._groups = None
		self._home = None
		self._forced = False

	@classmethod
	def is_valid_user_class(klass):
		return bool(getattr(klass, 'login', None))

	@property
	def is_present(self):
		return self.login is not None

	def describe(self):
		return "user(%s)" % self.login

	@classmethod
	def createDefaultInstance(klass, node, resourceName):
		return ConcreteUserResource(node, resourceName)

	def acquire(self, driver):
		if self.uid is not None:
			self.target.logInfo("found user %s; uid=%s" % (self.login, self.uid))
			return True

		cmd = self._build_useradd()
		if not self.target.runOrFail(cmd, user = "root"):
			self.target.logFailure("useradd %s failed" % self.login)
			return False

		self.target.logInfo("created user %s; uid=%s" % (self.login, self.uid))
		return True

	def release(self, driver):
		return True

	def forcePassword(self):
		if self._forced:
			return True

		encrypted = self.encrypt_password()
		if not encrypted:
			self.target.logFailure("cannot force password - no password set")
			return False

		cmd = "sed -i 's|^root:[^:]*|root:%s|' /etc/shadow" % encrypted
		if not self.target.runOrFail(cmd, user = "root"):
			return False

		self.target.logInfo("forced password for user %s" % self.login)
		self._forced = True
		return True

	@property
	def uid(self):
		if self._uid is None:
			self._uid = self._run_and_capture("id -u")
		return self._uid

	@property
	def gid(self):
		if self._gid is None:
			self._gid = self._run_and_capture("id -g")
		return self._gid

	@property
	def groups(self):
		if self._groups is None:
			res = self._run_and_capture("id -G")
			if res is not None:
				self._groups = res.split()
		return self._groups

	@property
	def home(self):
		if self._home is None:
			self._home = self._run_and_capture("echo $HOME")
		return self._home

	def encrypt_password(self):
		if not self.encrypted_password and self.password is not None:
			import crypt

			self.encrypted_password = crypt.crypt(self.password, crypt.METHOD_SHA256)
		return self.encrypted_password

	def _build_useradd(self):
		useradd = ["useradd", "--create-home"]

		encrypted = self.encrypt_password()
		if encrypted:
			useradd.append("--password")
			useradd.append("'%s'" % encrypted)
		useradd.append(self.login)

		return " ".join(useradd)

	def _run_and_capture(self, cmd):
		status = self.target.run(cmd, quiet = True, user = self.login, stdout = bytearray())
		if not status:
			return None

		for line in status.stdoutString.split("\n"):
			rv = line.strip()
			if rv:
				return rv

		return None

class TestUserResource(UserResource):
	name = "test-user"
	login = "testuser"
	password  = "test"
	# encrypted_password = "$5$yWwV1dmWR7IqeEqm$sjrbgv7HiNp/19Nzlac5L5dxySAqLW9iqgZQDjpc8V7"

	def acquire(self, driver):
		node = self.target

		# If the SUT configuration specifies a test user, use that
		# login, otherwise use our class default.
		if node.test_user is not None:
			self.login = node.test_user

		if not super().acquire(driver):
			return False

		node.test_user = self.login
		return True

class RootUserResource(UserResource):
	name = "root-user"
	login = "root"
	password  = "guessme"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._uid = 0
		self._gid = 0
		self._home = "/root"

class ConcreteUserResource(UserResource):
	def __init__(self, target, name):
		self.name = name
		self.login = name

		super().__init__(target)

class ExecutableResource(Resource):
	resource_type = "executable"

	attributes = {
		'executable'		: str,
		'selinux_label_domain'	: str,
		'selinux_process_domain': str,
		'selinux_test_interactive' : bool,
		'selinux_test_command'	: str,
		'interactive'		: bool,
		'package'		: str,
	}

	# Derived classes can specify an executable name;
	# if omitted, we will just use klass.name
	executable = None

	# Package from which the executable can be installed
	package = None

	# selinux_label_domain: if specified, this is
	#	the domain part of the executable's label
	#	(eg sshd_exec_t, passwd_exec_t, etc)
	# selinux_process_domain: if specified, this
	#	is the domain part of the process
	#	context when executing the application
	# interactive
	#	if True, SELinux testing assumes that the command
	#	is interactive and starts it accordingly.
	#	Note, SELinux label testing currently does
	#	not work for non-interactive commands.
	selinux_label_domain = None
	selinux_process_domain = None
	selinux_test_interactive = False
	selinux_test_command = None
	interactive = False

	PATH = "/sbin:/usr/sbin:/bin:/usr/bin"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.path = None
		self._default_user = None

	@property
	def is_present(self):
		return True

	def describe(self):
		return "executable(%s)" % self.name

	@classmethod
	def createDefaultInstance(klass, node, resourceName):
		return ConcreteExecutableResource(node, resourceName)

	def acquire(self, driver):
		executable = self.executable or self.name
		node = self.target

		if self.locateBinary(node, executable):
			return True

		if self.package:
			if not self.installPackage(node, self.package):
				node.logError("Unable to install package %s" % self.package)
				return False

			if self.locateBinary(node, executable):
				return True

		node.logInfo("Unable to find %s in PATH=%s" % (executable, self.PATH))
		return False

	def locateBinary(self, node, executable):
		# Caveat: type -p does not follow symlinks. If the user needs the realpath,
		# (like, for instance, SELinux label checking) they need to chase symlink
		# themselves.
		#cmd = '_path=$(type -p "%s"); test -n "$_path" && realpath "$_path"'
		cmd = 'type -p "%s"'

		node.logInfo("Locating binary file for command `%s'" % executable)
		st = node.run(cmd % executable, environ = { "PATH": self.PATH }, stdout = bytearray())
		if st and st.stdout:
			path = st.stdoutString.strip()
			if path:
				node.logInfo("Located executable %s at %s" % (executable, path))
				self.path = path
				return True

		return False

	def installPackage(self, node, package):
		# for now, only zypper, sorry
		st = node.run("zypper in -y %s" % package)
		return bool(st)

	def release(self, driver):
		return True

	def run(self, *args, **kwargs):
		assert(self.path)

		if self._default_user and 'user' not in kwargs:
			kwargs['user'] = self._default_user

		return self.target.run("%s %s" % (self.path, " ".join(args)), **kwargs)

	def runOrFail(self, *args, **kwargs):
		assert(self.path)

		if self._default_user and 'user' not in kwargs:
			kwargs['user'] = self._default_user

		return self.target.runOrFail("%s %s" % (self.path, " ".join(args)), **kwargs)

class ConcreteExecutableResource(ExecutableResource):
	def __init__(self, target, name, executable = None):
		self.name = name
		self.executable = executable

		super().__init__(target)

class ServiceResource(Resource):
	resource_type = "service"

	attributes = {
		'daemon_path'		: str,
		'systemd_unit'		: str,
		'systemd_activate'	: list,
		'package'		: str,
	}

	systemctl_path = "/usr/bin/systemctl"
	systemd_activate = []
	package = None

	def __init__(self, *args, **kwargs):
		assert(self.is_valid_service_class())

		super().__init__(*args, **kwargs)

	@classmethod
	def is_valid_service_class(klass):
		if not hasattr(klass, "daemon_path") or not hasattr(klass, "systemd_unit"):
			return False

		if not klass.daemon_path or not klass.systemd_unit:
			return False

		if not getattr(klass, "systemd_activate", None):
			klass.systemd_activate = [klass.systemd_unit]

		return True


	@property
	def is_present(self):
		return True

	def describe(self):
		return "service(%s)" % self.name

	def acquire(self, driver):
		node = self.target

		if not node.is_systemd:
			raise NotImplementedError("Unable to start service %s: SUT does not use systemd" % self.name)

		if not self.allUnitsPresent(node):
			if not self.package:
				node.logError("Missing unit(s) for service %s" % self.name)
				return False

			susetest.say("Missing unit(s) for service %s, trying to install package %s" % (self.name, self.package))
			if not self.installPackage(node, self.package):
				node.logError("Failed to install %s on %s" % (self.package, node.name))
				return False

			if not self.package:
				node.logError("Missing unit(s) for service %s" % self.name)
				return False

		for unit in self.systemd_activate:
			node.logInfo("activating service %s" % (unit))
			if not self.systemctl("enable", unit) or not self.systemctl("start", unit):
				return False

		return True

	def release(self, driver):
		node = self.target

		if not node.is_systemd:
			raise NotImplementedError("Unable to stop service %s: SUT does not use systemd" % self.name)

		for unit in self.systemd_activate:
			node.logInfo("deactivating service %s" % (unit))
			if not self.systemctl("stop", unit) or not self.systemctl("disable", unit):
				return False

		return True

	def start(self):
		return self.systemctlForAllUnits("start")

	def restart(self):
		return self.systemctlForAllUnits("restart")

	def reload(self):
		return self.systemctlForAllUnits("reload")

	def stop(self):
		return self.systemctlForAllUnits("stop")

	def allUnitsPresent(self, node):
		for unit in self.systemd_activate:
			if not node.run("systemctl show --property UnitFileState %s" % unit, quiet = True):
				return False
		return True

	def installPackage(self, node, package):
		# for now, only zypper, sorry
		st = node.run("zypper in -y %s" % package)
		return bool(st)

	def systemctlForAllUnits(self, verb):
		for unit in self.systemd_activate:
			if not self.systemctl(verb, unit):
				return False

		return True

	def systemctl(self, verb, unit):
		cmd = "%s %s %s" % (self.systemctl_path, verb, unit)
		return self.target.runOrFail(cmd)

	@property
	def pid(self):
		if not self.is_active:
			return None

		status = self.systemctl("show --property MainPID", self.systemd_unit)

		if not(status) or len(status.stdout) == 0:
			return None

		for line in status.stdoutString.split("\n"):
			if line.startswith("MainPID="):
				pid = line[8:]
				if pid.isdecimal():
					return pid

		return None

	@property
	def user(self):
		pid = self.pid

		if pid is None:
			return None

		status = self.target.run("/bin/ps hup " + pid);
		if not(status) or len(status.stdout) == 0:
			self.target.logFailure("ps did not find %s process" % self.name);
			return None

		# the first column of the ps output is the user name
		return status.stdoutString.split(None, 1)[0]

class FileResource(PackageBackedResource):
	resource_type = "file"

	attributes = {
		'path'			: str,
		'format'		: str,
		'package'		: str,
	}

	path = None
	format = None

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def describe(self):
		return "file(%s) = \"%s\"" % (self.name, self.path)

	@property
	def is_present(self):
		return bool(self.path)

	# inherit default acquire/release methods from PackageBackedResource
	# acquire will call our .detect() to see if the file is already
	# present. If not, it will try to install the package named by
	# the resource definition

	def detect(self):
		st = self.target.run("test -a '%s'" % self.path, user = "root")
		return bool(st)

	@classmethod
	def createDefaultInstance(klass, node, resourceName):
		return ConcreteFileResource(node, resourceName)

class ConcreteFileResource(FileResource):
	def __init__(self, target, name):
		self.name = name
		super().__init__(target)

# Interface for message filters
class MessageFilter:
	# Analyze the message (of class Message above)
	# Implementations are free to invoke node.logInfo, node.logFailure etc.
	def match(self, msg, node):
		pass


class JournalResource(Resource):
	resource_type = "journal"
	attributes = {}

	name = "journal"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self._filters = []

	@property
	def is_present(self):
		return True

	def describe(self):
		return "journal"

	class Message:
		def __init__(self, timestamp, transport, application, message):
			self.timestamp = timestamp
			self.transport = transport
			self.application = application
			self.message = message

	def addFilter(self, filter):
		self._filters.append(filter)

	def acquire(self, driver):
		node = self.target

		# We should really make this a systemd unit
		import twopence

		self.target.logInfo("starting journal processor")
		self.target._run("twopence_journal --mode server --background", quiet = True)

		driver.addPostTestHook(self.processMessages)

		# For now, just flush any messages that accumulated since boot
		# We may want to create a test special case that looks at any
		# policy violations during system boot (and that's TBD), but
		# we should not do this for every test case.
		return self.flushMessages()
		# return self.processMessages(quiet = True)

	def release(self, driver):
		raise NotImplementedError()

	def flushMessages(self):
		self.target.run("twopence_journal >/dev/null", quiet = True)
		return True

	def processMessages(self, quiet = False):
		import twopence

		self.target.logInfo("querying journal processor")
		cmd = twopence.Command("twopence_journal", stdout = bytearray(), quiet = True)
		st = self.target._run(cmd)

		processed = []
		for line in st.stdout.decode("utf-8").split('\n'):
			if not line:
				continue

			args = line.split('|')
			m = self.Message(*args)

			if m.transport == 'stdout' and m.application.startswith("twopence_test"):
				continue

			processed.append(line)

			for filt in self._filters:
				filt.match(m, self.target)

		if processed and not quiet:
			self.target.logInfo("Received %d journal messages" % len(processed))

			# Print the messages themselves w/o prefixing them with the node name
			# This makes it easier to cut and paste them into bug reports
			journal = self.target.journal
			journal.info("== Messages begin ==")
			for line in processed:
				journal.info("%s" % line)
			journal.info("== Messages end ==")

		return bool(st)

##################################################################
# Manage all resources.
# This is a bit convoluted, and involves several classes that
# are needed to keep track.
#
# We distinguish between resource type, resource class and resource
# instances.
#
# A resource type would be "executable", "user", etc. For each of
# these, we define a python class (ExecutableResource, ...) above.
#
# A resource class is a subclass of any of these base classes.
# For example, there may be a resource class for user "root".
#
# A resource instance represents the actual root user on an
# actual system under test. A resource instance can be claimed
# and released, or queried for specific attributes.
##################################################################

##################################################################
# Global resource inventory
##################################################################
class ResourceInventory:
	# After class initiazation, this holds a dict mapping
	# strings ("executable") to resource types (ExecutableResource)
	_res_type_by_name = None

	def __init__(self):
		# Define resource types string, user, executable etc.
		self.__class__.classinit()

		self.globalRegistry = globalResourceRegistry()

		# Find all Resource classes defined in this module
		self.globalRegistry.findResources(globals())

		# If required, add more resource modules like this:
		# self.globalRegistry.findResources(susetest.othermodule.__dict__)

		self.nodeRegistry = {}

		self.resources = []

	@classmethod
	def classinit(klass):
		if klass._res_type_by_name is not None:
			return

		klass._res_type_by_name = {}
		klass.defineResourceType(StringValuedResource)
		klass.defineResourceType(ExecutableResource)
		klass.defineResourceType(UserResource)
		klass.defineResourceType(ServiceResource)
		klass.defineResourceType(FileResource)
		klass.defineResourceType(JournalResource)

	@classmethod
	def defineResourceType(klass, base_class):
		klass._res_type_by_name[base_class.resource_type] = base_class

	def __contains__(self, res):
		obsolete()
		for rover in self.resources:
			if res.target == rover.target and res.name == rover.name:
				return True
		return False

	def getNodeRegistry(self, node, create = False):
		registry = self.nodeRegistry.get(node.name)
		if registry is None and create:
			registry = ResourceRegistry()
			self.nodeRegistry[node.name] = registry
		return registry

	def getResource(self, node, resourceType, resourceName, create = False):
		if type(resourceType) == str:
			if not resourceType in self._res_type_by_name:
				raise ValueError("%s: unknown resource type %s" % (self.__class__.__name__, resourceType))
			resourceType = self._res_type_by_name[resourceType]

		for res in self.resources:
			if resourceType and not isinstance(res, resourceType):
				continue

			if res.target == node and res.name == resourceName:
				return res

		if not create:
			return None

		resourceKlass = None

		# Look at the node registry first
		registry = self.nodeRegistry.get(node.name)
		if registry:
			resourceKlass = registry.getResourceClass(resourceType, resourceName)

		# Finally, check the global registry
		if resourceKlass is None:
			resourceKlass = self.globalRegistry.getResourceClass(resourceType, resourceName)

		if resourceKlass is not None:
			res = resourceKlass(node)
		elif resourceType is not None:
			# Fallback for resource classes that can be configured via file
			res = resourceType.createDefaultInstance(node, resourceName)
		else:
			res = None

		if res is None:
			raise KeyError("Unknown %s resource \"%s\"" % (resourceType.resource_type, resourceName))


		self.resources.append(res)
		node.addResource(res)

		# susetest.say("%s: created a %s resource" % (node.name, resourceName))
		return res

class ResourceAssertion:
	def __init__(self, res, state, mandatory, temporary = False):
		self.resource = res
		self.state = state
		self.mandatory = mandatory
		self.temporary = temporary

		if state == Resource.STATE_ACTIVE:
			self.verb = "activate"
			self.fn = res.acquire
		elif state == Resource.STATE_INACTIVE:
			self.verb = "deactivate"
			self.fn = res.release
		else:
			raise ValueError("%s: unexpected state %d in assertion for resource %s" % (
					res.target.name, state, res.name))

	def __str__(self):
		return "%s(%s %s)" % (self.__class__.__name__, self.verb, self.resource)

	def perform(self, driver):
		res = self.resource
		node = res.target

		if not res.is_present:
			if self.mandatory:
				node.logError("mandatory resource %s not present" % res.name)
				return False

			node.logInfo("optional resource %s not present" % res.name)
			return True

		if res.state == self.state:
			return True

		susetest.say("about to %s resource %s" % (self.verb, res))
		ok = self.fn(driver)

		if ok:
			res.state = self.state
		else:
			node.logError("unable to %s resource %s" % (self.verb, res.name))

		return ok

##################################################################
# Global registry of resource types
#
# self._classes is a dict of lists, so that we can define
# different resources with the same name (eg executable rpcbind
# as well as service rpcbind).
##################################################################
class ResourceRegistry:
	_global_registry = None

	def __init__(self):
		self._classes = {}

	def getResourceClass(self, res_type, res_name):
		found = None
		for klass in self._classes.get(res_name, []):
			if res_type and not issubclass(klass, res_type):
				continue
			if found is not None:
				raise KeyError("Cannot resolve ambiguous resource name %s: %s (%s) vs %s (%s)" % (
						res_name,
						found.resource_type, found,
						klass.resource_type, klass))

			found = klass

		return found

	def defineResourceClass(self, klass, verbose = False):
		if verbose:
			susetest.say("Define %s resource %s = %s" % (klass.resource_type, klass.name, klass.__name__))
			if hasattr(klass, 'attributes'):
				for attr_name in klass.attributes:
					value = getattr(klass, attr_name)
					print("  %s = %s" % (attr_name, value))

		if klass.name not in self._classes:
			self._classes[klass.name] = []

		self._classes[klass.name].append(klass)

	def findResources(self, ctx, verbose = False):
		for klass in self._find_classes(ctx, Resource, "name"):
			self.defineResourceClass(klass, verbose)

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

def globalResourceRegistry():
	if ResourceRegistry._global_registry is None:
		ResourceRegistry._global_registry = ResourceRegistry()
	return ResourceRegistry._global_registry

##################################################################
# Resource loader - load OS specific resource definitions
# from one or more config files.
##################################################################
class ResourceLoader:
	class ResourceDescription:
		def __init__(self, name, klass, file, override = False):
			self.name = name
			self.klass = klass
			self.file = file
			self.override = override
			self.attrs = {}

		def setAttribute(self, name, value):
			self.attrs[name] = value

		def update(self, other):
			assert(isinstance(other, self.__class__))

			# If override is set, to not accept any updates
			# from more generic resource files.
			if not self.override:
				self.attrs.update(other.attrs)
				self.override = other.override

		@property
		def type(self):
			return self.klass.__name__

	class ResourceDescriptionSet:
		def __init__(self):
			self._resources = {}

		@property
		def resources(self):
			return self._resources.values()

		def __bool__(self):
			return bool(self._resources)

		def getResourceDescriptor(self, name):
			return self._resources.get(name)

		def createResourceDescriptor(self, name, klass, origin_file):
			key = '%s:%s' % (klass.resource_type, name)
			desc = self._resources.get(key)
			if desc is None:
				desc = ResourceLoader.ResourceDescription(name, klass, origin_file)
				self._resources[key] = desc
			else:
				assert(desc.klass == klass)
			return desc

		def update(self, other):
			for key, desc in other._resources.items():
				mine = self.getResourceDescriptor(key)
				if mine is None:
					self._resources[key] = desc
					continue

				if mine.klass != desc.klass:
					raise ResourceLoader.BadResource(desc, "conflicting definitions (type %s vs %s)" % (
							desc.type, mine.type))

				mine.update(desc)

	class BadResource(Exception):
		def __init__(self, desc, *args):
			msg = "bad resource %s (defined in %s)" % (desc.name, desc.file)
			if args:
				msg += ": "

			super().__init__(msg + " ".join(args))

	def __init__(self):
		self.resourceGroups = {}

	def getResourceGroup(self, name):
		name = name.lower()

		found = self.resourceGroups.get(name)
		if found is None:
			found = self.loadResourceGroup(name)
			self.resourceGroups[name] = found
		return found

	def loadResourceGroup(self, name):
		# FIXME: hardcoded bad
		# We should move paths.py from twopence-provision to twopence
		default_paths = [
			"~/.twopence/config",
			"/etc/twopence",
		]

		descGroup = self.ResourceDescriptionSet()
		for path in default_paths:
			path = os.path.expanduser(path)
			path = os.path.join(path, "resource.d", name + ".conf")
			# print("Trying to load %s" % path)
			if os.path.isfile(path):
				group = self.load(descGroup, path)

		return descGroup

	def load(self, descGroup, path):
		config = curly.Config(path)
		tree = config.tree()

		for name, klass in ResourceInventory._res_type_by_name.items():
			# print("load %s %s" % (name, klass))
			self.findResourceType(path, tree, descGroup, name, klass)

		# print("Loaded %s" % path)

	def findResourceType(self, origin_file, tree, descGroup, type, klass):
		if not hasattr(klass, 'attributes'):
			print("%s: please define valid attributes for class %s" % (self.__class__.__name__, klass.__name__))
			raise NotImplementedError()

		for name in tree.get_children(type):
			desc = descGroup.createResourceDescriptor(name, klass, origin_file)
			self.buildResourceDescription(desc, tree.get_child(type, name))
			# print("  %s %s" % (type, name))

	def buildResourceDescription(self, desc, config):
		klass = desc.klass
		for name, type in klass.attributes.items():
			config_name = name.replace('_', '-')
			value = config.get_value(config_name)
			# print("%s = %s" % (config_name, value))

			if not value:
				continue

			if type == str:
				pass
			elif type == bool:
				if value.lower() in ('on', 'yes', 'true', '1'):
					value = True
				elif value.lower() in ('off', 'no', 'false', '0'):
					value = False
				else:
					raise ResourceLoader.BadResource(desc, "bad value for attribute %s: expected a boolean value not \"%s\"" % (
								config_name, value))
			elif type == list:
				value = config.get_values(config_name)
			else:
				raise NotImplementedError("cannot set resource attr %s of type %s" % (name, type))

			desc.setAttribute(name, value)

		# Check for spelling mistakes or unknown attributes in the config file
		for config_name in config.get_attributes():
			attr_name = config_name.replace('-', '_')

			if attr_name == 'override':
				value = config.get_value(config_name)
				desc.override = value.lower() in ('on', 'yes', 'true', '1')
				continue

			if attr_name not in klass.attributes:
				raise ResourceLoader.BadResource(desc, "unknown attribute %s (%s is not a class attribute of %s)" % (
								config_name, attr_name, klass.__name__))

	# This iterates over all resource descriptions and adds
	# corresponding resources to a ResourceRegistry
	def realize(self, group, registry, verbose = False):
		for desc in group.resources:
			klass = desc.klass
			new_class_name = "Userdef%s_%s" % (klass.__name__, desc.name)
			new_klass = type(new_class_name, (klass, ), desc.attrs)
			new_klass.name = desc.name

			registry.defineResourceClass(new_klass, verbose = verbose)

##################################################################
# Keep track of desired state of resources
##################################################################
class ResourceManager:
	def __init__(self, driver):
		self.driver = driver

		self.inventory = ResourceInventory()
		self.loader = ResourceLoader()

		self._assertions = []
		self._cleanups = {}

		self._plugged = True

	def loadOSResources(self, node, vendor, osclass, release):
		# Find the resource definitions for vendor, osclass, and release(s)
		# The collapse these into one set of resource definitions.
		# This allows you to define the generic info on say sudo
		# in one file, and the selinux specific information in another one.
		group = self.buildResourceChain(vendor, osclass, release)

		# Create the resources defined by this one in the node's
		# resource registry.
		# This is not really pretty; we should probably do this
		# per OS rather than per node.
		registry = self.inventory.getNodeRegistry(node, create = True)
		self.loader.realize(group, registry)

	def buildResourceChain(self, vendor, osclass, release):
		# Given an OS vendor and release, create a list of names,
		# from most specific to least specific:
		#	leap-15.3
		#	leap-15
		#	leap
		#	suse
		# This is not quite optimal yet; instead, we should probably
		# have something more explicit (like a statement in the
		# platform definition), so that we can avoid duplicating
		# information between SLES and Leap, for instance.
		#
		# Also, it's probably more natural to have a sort of
		# progression from one version to the next of the same
		# OS, rather that from a generic "Leap-15" to "Leap-15.4"
		names = []
		while True:
			names.append(release)
			m = re.match("(.*)\.[0-9]+", release)
			if m:
				release = m.group(1)
				continue

			m = re.match("(.*)-[0-9]+", release)
			if m:
				names.append(m.group(1))
			break
		names.append(osclass)
		names.append(vendor)

		result = ResourceLoader.ResourceDescriptionSet()
		for name in names:
			group = self.loader.getResourceGroup(name)
			if group:
				result.update(group)

		if not result:
			print("Did not find any resources for OS %s." % release)
			print("If this is intentional, please create an empty file ~/.twopence/config/resource.d/%s.conf" % (release,))
			raise ValueError()

		return result

	def getResource(self, *args, **kwargs):
		return self.inventory.getResource(*args, **kwargs)

	@property
	def pending(self):
		return bool(self._assertions)

	@property
	def pendingCleanups(self):
		return bool(self._cleanups)

	def acquire(self, res, mandatory, **kwargs):
		self.requestState(res, Resource.STATE_ACTIVE, mandatory, **kwargs)

	def release(self, res, mandatory, **kwargs):
		self.requestState(res, Resource.STATE_INACTIVE, mandatory, **kwargs)

	def requestState(self, res, state, mandatory, defer = False):
		assertion = ResourceAssertion(res, state, mandatory)

		# If we're outside a test group, we do not evaluate the assertion right away
		# but defer it until we do the beginGroup().
		#
		# Else evaluate them right away.
		if self._plugged or defer:
			self._assertions.append(assertion)
		else:
			assertion.perform(self.driver)

	def plug(self):
		self._plugged = True

	def unplug(self):
		self._plugged = False
		if self._assertions:
			self.performDeferredChanges()

	def performDeferredChanges(self):
		if self._plugged:
			susetest.say("%s: refusing to perform deferred resource changes while plugged" % self.__class__.__name__)
			return True

		cool = True

		while cool and self._assertions:
			deferred = self._assertions
			self._assertions = []

			if False:
				if deferred:
					susetest.say("performing %d deferred resource changes" % len(deferred))
					for assertion in deferred:
						susetest.say("  %s" % assertion)

			self._plugged = True

			for assertion in deferred:
				if assertion.temporary:
					self.requestCleanup(res)

				if not assertion.perform(self.driver):
					cool = False

			self._plugged = False

		return cool

	def requestCleanup(self, res):
		if res in self._cleanups:
			return

		assertion = ResourceAssertion(res, res.state, mandatory = False)
		self._cleanups[res] = assertion

	def cleanup(self):
		cleanups = self._cleanups.values()
		self.zapCleanups()

		for assertion in cleanups:
			# self._perform_resource_assertion(assertion)
			susetest.say("Ignoring cleanup of %s" % assertion)

	def zapPending(self):
		susetest.say("zapping pending assertions")
		self._assertions = []

	def zapCleanups(self):
		self._cleanups = {}
