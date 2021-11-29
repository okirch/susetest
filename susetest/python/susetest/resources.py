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
##################################################################

import susetest
import suselog
import inspect
import os
import curly
import sys

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

class StringValuedResource(Resource):
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
		self.state = Resource.STATE_ACTIVE
		return True

	def release(self, driver):
		self.state = Resource.STATE_INACTIVE

class ResourceAddressIPv4(StringValuedResource):
	name = "ipv4-address"

	def __init__(self, *args, **kwargs):
		super().__init__(None, *args, **kwargs)
		self.value = self.target.ipv4_addr

class ResourceAddressIPv6(StringValuedResource):
	name = "ipv6-address"

	def __init__(self, *args, **kwargs):
		super().__init__(None, *args, **kwargs)
		self.value = self.target.ipv6_addr

class UserResource(Resource):
	password = None
	encrypted_password = None

	def __init__(self, *args, **kwargs):
		assert(self.is_valid_user_class())

		super().__init__(*args, **kwargs)

		self._uid = None
		self._gid = None
		self._groups = None
		self._home = None

	@classmethod
	def is_valid_user_class(klass):
		return bool(getattr(klass, 'login', None))

	@property
	def is_present(self):
		return self.login is not None

	def describe(self):
		return "user(%s)" % self.login

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

	def _build_useradd(self):
		useradd = ["useradd", "--create-home"]
		if not self.encrypted_password and self.password is not None:
			import crypt

			self.encrypted_password = crypt.crypt(self.password, crypt.METHOD_SHA256)
		if self.encrypted_password:
			useradd.append("--password")
			useradd.append("'%s'" % self.encrypted_password)
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

class ExecutableResource(Resource):
	# Derived classes can specify an executable name;
	# if omitted, we will just use klass.name
	executable = None

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

	def acquire(self, driver):
		node = self.target

		executable = self.executable or self.name
		for bindir in self.PATH.split(':'):
			if not bindir:
				continue
			path = os.path.join(bindir, executable)
			if node.run("/usr/bin/test -f %s" % path):
				node.logInfo("Located executable %s at %s" % (executable, path))
				self.path = path
				return True

		node.logInfo("Unable to find %s in PATH=%s" % (executable, self.PATH))
		return False

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

class ServiceResource(Resource):
	systemctl_path = "/usr/bin/systemctl"

	systemd_activate = []

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

# Interface for message filters
class MessageFilter:
	# Analyze the message (of class Message above)
	# Implementations are free to invoke node.logInfo, node.logFailure etc.
	def match(self, msg, node):
		pass


class JournalResource(Resource):
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

		self.target.logInfo("%s: starting journal processor" % self.target.name)
		self.target._run("twopence_journal --mode server --background", quiet = True)

		driver.addPostTestHook(self.processMessages)

		return self.processMessages(quiet = True)

	def release(self, driver):
		raise NotImplementedError()

	def processMessages(self, quiet = False):
		import twopence

		self.target.logInfo("%s: querying journal processor" % self.target.name)
		cmd = twopence.Command("twopence_journal", stdout = bytearray(), quiet = True)
		st = self.target._run(cmd)

		printed = False

		for line in st.stdout.decode("utf-8").split('\n'):
			if not line:
				continue

			args = line.split('|')
			m = self.Message(*args)

			if m.transport == 'stdout' and m.application.startswith("twopence_test"):
				continue

			if not quiet:
				if not printed:
					self.target.logInfo("Received messages")
					printed = True
				self.target.logInfo("  %s" % line)

			for filt in self._filters:
				filt.match(m, self.target)

		return bool(st)

##################################################################
# Global resource inventory
##################################################################
class ResourceInventory:
	def __init__(self):
		self.registry = resourceRegistry()
		self.resources = []

	def __contains__(self, res):
		for rover in self.resources:
			if res.target == rover.target and res.name == rover.name:
				return True
		return False

	def get(self, node, type_name, create = False):
		for res in self.resources:
			if res.target == node and res.name == type_name:
				return res

		if not create:
			return None

		resourceKlass = self.registry.get(type_name)
		if resourceKlass is None:
			raise KeyError("Unknown resource type \"%s\"" % type_name)

		res = resourceKlass(node)

		self.resources.append(res)
		node.addResource(res)

		susetest.say("%s: created a %s resource" % (node.name, type_name))
		return res

	def add(self, res):
		if res in self:
			print("%s: ignoring duplicate definition of resources %s" % (res.target.name, res.name))
			return

		self.resources.append(res)

class ResourceAssertion:
	def __init__(self, res, state, mandatory, temporary = False):
		self.resource = res
		self.state = state
		self.mandatory = mandatory
		self.temporary = temporary

##################################################################
# Global registry of resource types
##################################################################
class ResourceRegistrySingleton:
	_instance = None

	def __init__(self):
		self._types = {}

		# Find all Resource classes defined in this module
		self.findResources(globals())

		# self.findResources(susetest.othermodule.__dict__)

	def get(self, name):
		return self._types.get(name)

	def defineResource(self, klass, verbose = False):
		if verbose:
			susetest.say("Define resource %s = %s" % (klass.name, klass.__name__))
		self._types[klass.name] = klass

	def findResources(self, ctx, verbose = False):
		for klass in self._find_classes(ctx, Resource, "name"):
			self.defineResource(klass, verbose)

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

def resourceRegistry():
	if ResourceRegistrySingleton._instance is None:
		ResourceRegistrySingleton._instance = ResourceRegistrySingleton()
	return ResourceRegistrySingleton._instance
