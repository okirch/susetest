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
import inspect
import os
import curly
import sys
import re
import crypt
import functools
import twopence
from twopence.schema import *
from .files import FileFormatRegistry

class Expectation(NamedConfigurable):
	status = "undefined"

	def __init__(self, conditionalName, config = None):
		super().__init__(conditionalName)
		self.conditional = None
		self.reason = None
		self.origin = None

		if config:
			self.configure(config)

	@property
	def conditionalName(self):
		return self.name

	def __str__(self):
		return f"predicted outcome = {self.status} because of {self.reason}"

	@property
	def longdesc(self):
		desc = f"conditional({self.name})"
		if self.origin:
			desc += " defined in {self.origin}"
		return desc

	def applies(self, context):
		assert(self.conditional)
		return self.conditional.eval(context)

	def configure(self, config):
		self.origin = config.origin
		self.settings = config
		self.conditional = ResourceConditional.fromConfig(config)
		self.reason = config.get_value("reason")

	@classmethod
	def fromConditional(klass, other):
		result = klass(other.name)
		result.reason = other.reason
		result.conditional = other.conditional
		return result

class ExpectedFailure(Expectation):
	status = "failure"

class ExpectedError(Expectation):
	status = "error"

##################################################################
# Resource base class
##################################################################
class Resource(NamedConfigurable):
	static_resource = False

	STATE_INACTIVE = 0
	STATE_ACTIVE = 1

	schema = []

	def __init__(self, name):
		super().__init__(name)

		self.target = None
		self.state = Resource.STATE_INACTIVE

	@property
	def is_valid(self):
		return True

	@property
	def is_present(self):
		return True

	@property
	def is_active(self):
		return self.state == Resource.STATE_ACTIVE

	def __str__(self):
		result = self.describe()
		if self.target:
			result += " on " + self.target.name
		return result

	def describe(self):
		return self.name

	@property
	def predictions(self):
		return []

	def predictOutcome(self, driver, variables):
		predictions = self.predictions

		if predictions:
			context = TargetEvalContext(driver, self.target, variables)
			for prediction in predictions:
				if prediction.applies(context):
					return prediction

		return None

class StringValuedResource(Resource):
	resource_type = "string"

	schema = [
		StringAttributeSchema("value"),
	]

	def __init__(self, *args, value = None, **kwargs):
		super().__init__(*args, **kwargs)
		self.value = value
		self.state = Resource.STATE_ACTIVE

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

class SubsystemResource(Resource):
	resource_type = "subsystem"

	schema = [
		ListAttributeSchema("packages"),
	]

	@property
	def is_present(self):
		return bool(self.packages)

	def acquire(self, driver):
		okay = True
		for package in self.packages:
			pkg = self.target.requirePackage(package)
			if not pkg:
				okay = False

		return okay

	def release(self, driver):
		return True

class PackageResource(Resource):
	resource_type = "package"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	@property
	def package(self):
		return self.name

	@property
	def is_present(self):
		return True

	def acquire(self, driver):
		# print("acquire %s; package %s" % (self, self.package))
		node = self.target

		if not self.package:
			node.logFailure(f"{self} does not define package name?!")
			return False

		packageManager = self.target.packageManager
		if packageManager is None:
			node.logInfo(f"Cannot install {self.package}: {node.name} does not have a package manager")
			return False

		if packageManager.checkPackage(node, self.package):
			node.logInfo(f"Package {self.package} already installed on {node.name}")
			return True

		susetest.say(f"Trying to install package {self.package}")
		if not packageManager.installPackage(node, self.package):
			node.logError(f"Failed to install {self.package} on {node.name}")
			return False

		return True

	# Default implementation for PackageBackedResource.release
	def release(self, driver):
		return True

class PackageBackedResource(Resource):
	package = None

	schema = [
		StringAttributeSchema("package"),
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	# Default implementation for PackageBackedResource.acquire
	def acquire(self, driver):
		# print("acquire %s; package %s" % (self, self.package))
		if self.detect():
			return True

		if self.package is not None:
			resource = self.target.optionalPackage(self.package)
			if resource is None or not resource.is_active:
				self.target.logInfo(f"resource {self} supposedly backed by package {self.package} - but this package is not defined, or could not be installed")
				return False

			if self.detect():
				return True

		# self.target.logInfo("resource %s not present" % self)
		return False

	# Default implementation for PackageBackedResource.release
	def release(self, driver):
		return True

class UserResource(Resource):
	resource_type = "user"

	schema = [
		StringAttributeSchema("login"),
		StringAttributeSchema("password"),
		StringAttributeSchema("encrypted-password"),
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self._uid = None
		self._gid = None
		self._groups = None
		self._home = None
		self._forced = False

	@property
	def is_valid(self):
		return bool(self.login)

	@property
	def is_present(self):
		return self.login is not None

	def describe(self):
		return "user(%s)" % self.login

	def acquire(self, driver):
		if self.uid is not None:
			self.target.logInfo("found user %s; uid=%s" % (self.login, self.uid))
			return True

		useradd = self.target.optionalExecutable("useradd")
		if useradd is None or not useradd.is_active:
			if self.createUserFallback(driver):
				return True
			self.target.logInfo(f"cannot provision {self} - cannot find useradd executable")
			return False

		options = self._build_useradd()
		if not useradd.runOrFail(options, user = "root"):
			self.target.logFailure(f"useradd {self.login} failed")
			return False

		self.target.logInfo("created user %s; uid=%s" % (self.login, self.uid))
		return True

	def release(self, driver):
		return True

	def forcePassword(self):
		if self._forced:
			return True

		if not self.overwritePassword():
			return False

		self._forced = True
		return True

	def overwritePassword(self, cryptAlgo = None):
		encrypted = self.encrypt_password(cryptAlgo)
		if not encrypted:
			self.target.logFailure("cannot force password - no password set")
			return False

		login = self.login

		cmd = f"sed -i 's|^{login}:[^:]*|{login}:{encrypted}|' /etc/shadow"
		if not self.target.runOrFail(cmd, user = "root"):
			return False

		self.target.logInfo(f"changed password for user {login}")
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

	def encrypt_password(self, algorithm = None):
		if algorithm is None:
			algorithm = crypt.METHOD_SHA256

		if self.password is not None:
			self.encrypted_password = crypt.crypt(self.password, algorithm)
		return self.encrypted_password

	def _build_useradd(self):
		useradd = ["--create-home"]

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

	# It's really starting to look like we should wrap this stuff in a new
	# UserManager class
	def createUserFallback(self, driver, minUid = 1000):
		passwd = self.target.optionalFile("system-passwd")
		if not passwd or not passwd.is_active:
			return False

		editor = passwd.createEditor()

		usedUids = set()
		for e in editor.entries():
			print(e)
			usedUids.add(e.uid)

		self._uid = None
		while minUid < 6666:
			if str(minUid) not in usedUids:
				self._uid = str(minUid)
				break
			minUid += 1

		if not self._uid:
			self.target.logInfo("Did not find a free uid for {self.login}")
			return False

		self._gid = self.findGID("users")
		if self._gid is None:
			self._gid = "10000"

		self._home = f"/home/{self.login}"

		e = editor.makeEntry(name = self.login, passwd = "x",
					uid = self._uid, gid = self._gid,
					homedir = self._home,
					shell = "/bin/bash");
		editor.addOrReplaceEntry(e)
		editor.commit()

		self.target.run(f"mkdir -p {self._home}")
		self.target.run(f"chown {self._uid}:{self._gid} {self._home}")

		return True

	def findGID(self, groupName):
		group = self.target.optionalFile("system-group")
		if not group or not group.is_active:
			return False

		editor = group.createReader()
		e = editor.lookupEntry(name = "users")
		if e is not None:
			return e.gid

class ExecutableResource(PackageBackedResource):
	resource_type = "executable"

	# executable: resource descriptions can specify an
	#	executable name; if omitted, we will just use
	#	klass.name
	# selinux_label_domain: if specified, this is
	#	the domain part of the executable's label
	#	(eg sshd_exec_t, passwd_exec_t, etc)
	# selinux_process_domain: if specified, this
	#	is the domain part of the process
	#	context when executing the application
	# selinux_test_service
	#	If set, test the process domain by looking
	#	at the (main process of) the indicated
	#	service.
	#	Note that the string is not an actual
	#	systemd unit file, but refers to the name of
	#	a service resource.
	# selinux_test_interactive (was: interactive)
	#	if True, SELinux testing assumes that the command
	#	is interactive and starts it accordingly.
	#	Note, SELinux label testing currently does
	#	not work for non-interactive commands.
	schema = [
		StringAttributeSchema("executable"),
		StringAttributeSchema("selinux-label-domain"),
		StringAttributeSchema("selinux-process-domain"),
		BooleanAttributeSchema("selinux-test-interactive"),
		StringAttributeSchema("selinux-test-service"),
		StringAttributeSchema("selinux-test-command"),
		BooleanAttributeSchema("interactive"),

		ListAttributeSchema("_expected_failures_by_name", key = "expected-failure"),
		ListAttributeSchema("_expected_errors_by_name", key = "expected-error"),

		ListNodeSchema("_expected_failures", key = "expected-failure", itemClass = ExpectedFailure),
		ListNodeSchema("_expected_errors", key = "expected-error", itemClass = ExpectedError),
	]

	PATH = "/sbin:/usr/sbin:/bin:/usr/bin"

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.path = None
		self._default_user = None

	def configure(self, config):
		super().configure(config)

	def describe(self):
		return "executable(%s)" % self.name

	@property
	def predictions(self):
		return self._expected_failures + self._expected_errors

	def acquire(self, driver):
		if super().acquire(driver):
			return True

		self.target.logInfo(f"Unable to find {self} in PATH={self.PATH}")
		return False

	def detect(self):
		executable = self.executable or self.name

		return self.locateBinary(self.target, executable)

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

class ServiceResource(PackageBackedResource):
	resource_type = "service"

	schema = [
		StringAttributeSchema("daemon-path"),
		StringAttributeSchema("executable"),
		StringAttributeSchema("systemd-unit"),
		ListAttributeSchema("systemd-activate"),
	]

	@property
	def is_valid(self):
		if not self.daemon_path and not self.executable:
			return False

		if not self.systemd_unit:
			return False

		if not systemd_activate:
			self.systemd_activate = [self.systemd_unit]

		return True


	def describe(self):
		return "service(%s)" % self.name

	@property
	def serviceManager(self):
		serviceManager = self.target.serviceManager
		if serviceManager is None:
			raise NotImplementedError(f"{self.name}: node {self.target.name} does not have a service manager")
		return serviceManager

	# Called from PackageBackedResource.acquire
	def detect(self):
		return self.serviceManager.tryToActivate(self)

	# We inherit PackageBackedResource.acquire(), which calls .detect() to
	# check whether the resource in the desired state (active)
	def release(self, driver):
		return self.serviceManager.tryToDeactivate(self)

	def start(self):
		return self.serviceManager.start(self)

	def restart(self):
		return self.serviceManager.restart(self)

	def reload(self):
		return self.serviceManager.reload(self)

	def stop(self):
		return self.serviceManager.stop(self)

	def running(self):
		return self.serviceManager.running(self)

	@property
	def pid(self):
		return self.serviceManager.getServicePID(self)

	@property
	def user(self):
		return self.serviceManager.getServiceUser(self)

class PathResource(PackageBackedResource):
	schema = [
		StringAttributeSchema("path"),
		StringAttributeSchema("volume"),
		StringAttributeSchema("selinux-label-domain"),
		StringAttributeSchema("dac-user"),
		StringAttributeSchema("dac-group"),
		StringAttributeSchema("dac-permissions"),
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.host_path = None

	def describe(self):
		if self.volume:
			return f"{self.resource_type}({self.name}) = {self.path} at volume {self.volume}"
		return f"{self.resource_type}({self.name}) = {self.path}"

	@property
	def is_present(self):
		return bool(self.path)

	# Container applications frequently expect their configuration to reside on
	# a separate volume that is mounted into the container.
	# In this case, they will copy info on the file resources into status.conf,
	# looking somewhat like this:
	#	 file "nginx.conf" {
	#            volume        "config";
	#            path          "nginx.conf";
	#        }
	# Chase these references and set the resource's .path attribute to the path
	# of the file *inside* the container.
	# If the volume is visible from the host (as will be the case with bind mounts),
	# set the .host_path as well.
	def resolveVolumeReference(self):
		if self.volume is None:
			return True

		if self.package:
			twopence.info(f"{self}: ignoring package for files residing on runtime volume {self.volume}")
			self.package = None

		volume = self.target.requireVolume(self.volume)
		if not volume:
			twopence.error("did not find resource {self.volume}")
			return False

		orig_path = self.path
		path = orig_path.lstrip('/')

		self.path = os.path.join(volume.mountpoint, path)
		twopence.debug(f"Resolved file path {orig_path}@volume({self.volume}) => {self.path}")

		if volume.host_path:
			self.host_path = os.path.join(volume.host_path, path)
			twopence.debug(f"  host path = {self.host_path}")

		return True

	# this is the namedtuple type that the stat() method returns
	xstat = functools.namedtuple('stat', ['user', 'group', 'permissions'])

	def stat(self):
		assert(self.path)

		cmd = f"stat -c 'user=%U group=%G permissions=%03a' {self.path}"
		st = self.target.run(cmd, user = 'root')
		if not st:
			self.logFailure(f"cannot stat {self.path}: {st.message}")
			return None

		kwargs = dict([s.split('=') for s in st.stdoutString.split()])
		return self.xstat(**kwargs)

class DirectoryResource(PathResource):
	resource_type = "directory"

	# inherit default acquire/release methods from PackageBackedResource
	# acquire will call our .detect() to see if the file is already
	# present. If not, it will try to install the package named by
	# the resource definition
	def detect(self):
		if self.volume and self.resolveVolumeReference():
			self.volume = None

		st = self.target.run("test -d '%s'" % self.path, user = "root")
		return bool(st)

class FileResource(PathResource):
	resource_type = "file"

	schema = [
		StringAttributeSchema("format"),
	]

	# inherit default acquire/release methods from PackageBackedResource
	# acquire will call our .detect() to see if the file is already
	# present. If not, it will try to install the package named by
	# the resource definition

	def detect(self):
		if self.volume and self.resolveVolumeReference():
			self.volume = None

		st = self.target.run("test -f '%s'" % self.path, user = "root")
		return bool(st)

	# FUTURE: implement a backup() method that copies the file to .bak,
	# and register a cleanup function that restores the original file at
	# the end of a test case/test group

	# FileEditors provide a facility to modify structured files,
	# by iterating/looking up/adding/removing/replacing entries
	def createEditor(self):
		editor = self.createReader()
		editor.beginRewrite()
		return editor

	def createReader(self):
		if self.path is None:
			raise ValueError(f"{self}: unable to create editor - no file path")
		if self.format is None:
			raise ValueError(f"{self}: unable to create editor - undefined format")

		# If the resource is also visible from the host side, create an editor that
		# edits the file directly. This allows us to modify the configuration even when
		# the application container is down (and which is more in line with how this is
		# actually expected to happen).
		if self.host_path:
			editor = FileFormatRegistry.createHostEditor(self.target, self.format, self.host_path)
		else:
			editor = FileFormatRegistry.createEditor(self.target, self.format, self.path)

		if not editor:
			raise ValueError(f"{self}: unable to create editor - no editor for format {self.format}")

		return editor

# Interface for message filters
class MessageFilter:
	# Analyze the message (of class Message above)
	# Implementations are free to invoke node.logInfo, node.logFailure etc.
	def match(self, msg, node):
		pass

class LogResource(Resource):
	static_resource = True

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self._filters = []

	def describe(self):
		return self.__class__.name

	class Message:
		def __init__(self, timestamp, transport, application, message):
			self.timestamp = timestamp
			self.transport = transport
			self.application = application
			self.message = message

	def addFilter(self, filter):
		self._filters.append(filter)

	def filterMessage(self, m):
		for filt in self._filters:
			filt.match(m, self.target)

class AuditResource(LogResource):
	resource_type = "audit"
	name = "audit"

	def acquire(self, driver):
		node = self.target
		self.mon = node.monitor("audit", self.handleAuditMessage)

		driver.addPostTestHook(self.auditSettle)
		return True

	def handleAuditMessage(self, seq, type, formatted):
		# print(f"handleAuditMessage({type}, {formatted}")
		if type.lower() != "avc":
			return

		# On CentOS8, the binary audit messages we receive via audispd seem to be
		# somewhat redundant, in that the formatted message start with
		#  type=TYPE msg=.... rest of message ...
		# If we detect this, we strip off the redundant gunk
		rhel_weird_prefix = f"type={type} msg=";
		if formatted.startswith(rhel_weird_prefix):
			formatted = formatted[len(rhel_weird_prefix):]

		m = self.Message(None, "audit", None, formatted)
		try:
			self.filterMessage(m)
		except Exception as e:
			self.target.logError(f"Caught exception in handleAuditMessage: {e}")

	# If we ever find that we're not catching some audit messages, we need to
	# implement a mechanism to flush out all pending messages on the SUT.
	# One such approach could be to implement a SETTLE operation on the
	# pending twopence transaction, which triggers an AUDIT_TEST message
	# and waits for that message to appear in the message stream from
	# audispd
	def auditSettle(self):
		# self.target.logInfo("audit settle")
		self.mon.settle(timeout = 5)

class JournalResource(LogResource):
	resource_type = "journal"
	name = "journal"

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

			self.filterMessage(m)
			processed.append(line)

		if processed and not quiet:
			self.target.logInfo("Received %d journal messages" % len(processed))

			# Print the messages themselves w/o prefixing them with the node name
			# This makes it easier to cut and paste them into bug reports
			logger = self.target.logger
			logger.logInfo("== Messages begin ==")
			for line in processed:
				logger.logInfo(line)
			logger.logInfo("== Messages end ==")

		return bool(st)

##################################################################
# ApplicationResources define stuff that the provisioner
# would like to tell us about
##################################################################
class ApplicationResource(Resource):
	@property
	def is_present(self):
		return True

	def acquire(self, driver):
		return True

	def release(self, driver):
		return True

class ApplicationVolumeResource(ApplicationResource):
	resource_type = "volume"

	schema = [
		StringAttributeSchema("mountpoint"),
		StringAttributeSchema("fstype"),
		StringAttributeSchema("host-path"),
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.mountpoint = None
		self.fstype = None

	def describe(self):
		return "volume(%s)" % self.name

class ApplicationPortResource(ApplicationResource):
	resource_type = "port"

	schema = [
		StringAttributeSchema("internal-port"),
		StringAttributeSchema("protocol"),
	]

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.port = None
		self.protocol = None
		self.expose = None

	def describe(self):
		return "port(%s)" % self.name

##################################################################
# APIResources let you attach behavior to a platform definition.
# Currently, the only use case we have is in specifying
# certain management APIs.
##################################################################
class APIResource(Resource):
	schema = [
		StringAttributeSchema("class-id"),
		StringAttributeSchema("module"),
	]

	def acquire(self, driver):
		return True

	def release(self, driver):
		return True

class ApplicationManagerResource(APIResource):
	resource_type = "application-manager"

	def describe(self):
		values = [self.name]
		if self.class_id:
			values.append(f"class={self.class_id}")
		if self.module:
			values.append(f"module={self.module}")
		return f"application-manager({', '.join(values)})"

	def acquire(self, driver):
		target = self.target
		if target.getApplication(self.name):
			# it already has an application of this name
			return True

		if not self.class_id:
			target.logInfo(f"Cannot attach application {self.name}: no class-id specified")
			return False

		# Find the class
		applicationClass = susetest.Application.find(self.class_id, moduleName = self.module)
		if applicationClass is None:
			target.logInfo(f"Unable to find application class {self.class_id}")
			return False

		# Create instance
		application = applicationClass(driver, target)

		if not target.attachApplication(self.name, application):
			target.logInfo(f"Unable to attach {application} as {self.name}")
			return False

		target.logInfo(f"Attached {application} as {self.name}")
		return True

	def release(self, driver):
		return True

##################################################################
# Classes that describe the high level structure of a
# resource file
##################################################################
class ResourceSettings(ConfigOpaque):
	origin = None

	def __str__(self):
		return f"{self.__class__.__name__}({self.name})"

	@property
	def longdesc(self):
		desc = str(self)
		if self.origin:
			desc += f" from {self.origin}"
		return desc

	@property
	def isPackageBacked(self):
		return issubclass(self.resourceClass, PackageBackedResource)

	def setBackingPackage(self, packageName):
		currentValue = self.get_value("package")
		if currentValue and currentValue != packageName:
			raise BadResource(f"{self.longdesc}: conflicting package names {currentValue} vs {packageName}")

		self.set_value("package", packageName)

	def configure(self, data):
		self.origin = data.origin
		super().configure(data)

def wrapKlass(klass):
	new_class_name = f"{klass.__name__}Settings"
	new_klass = type(new_class_name, (ResourceSettings, ), {'resourceClass': klass})

	return new_klass

# Given a resource class like ExecutableResource, create the schema for a dict of
# these resources.
# The dict will be attached to its container as _executables, and will accept config file
# entries of the form "executable foobar {... }". These will be converted to an instance
# of type ExecutableResourceSettings.
#
# To allow for easier handling, we also attach the original ExecutableResource class as
# _resourceKlass, and the newly created ExecutableResourceSettings as _settingsKlass
def makeResourceDict(resoureKlass, settingsKlass = None):
	resourceTypeName = resoureKlass.resource_type
	if settingsKlass is None:
		settingsKlass = wrapKlass(resoureKlass)

	settingsKlass.resource_type = resoureKlass.resource_type

	dictSchema = DictNodeSchema(f"_{resourceTypeName}s", key = resourceTypeName, itemClass = settingsKlass)
	dictSchema._resourceKlass = resoureKlass
	dictSchema._settingsKlass = settingsKlass

	return dictSchema

class ResourceCollection(NamedConfigurable):
	resource_type = "collection"

	schema = [
		makeResourceDict(StringValuedResource),
		makeResourceDict(ExecutableResource),
		makeResourceDict(UserResource),
		makeResourceDict(ServiceResource),
		makeResourceDict(FileResource),
		makeResourceDict(DirectoryResource),
		makeResourceDict(JournalResource),
		makeResourceDict(AuditResource),
#		makeResourceDict(PackageResource),
		makeResourceDict(SubsystemResource),
		makeResourceDict(ApplicationVolumeResource),
		makeResourceDict(ApplicationPortResource),
		makeResourceDict(ApplicationManagerResource),
	]

	_initializedDictAccessors = set()

	def __init__(self, *args, **argv):
		super().__init__(*args, **argv)

		self.initializedDictAccessors()

		self._resourcesByType = {}
		for child in self._nodes.values():
			resourceKlass = getattr(child, "_resourceKlass", None)
			if resourceKlass is None:
				continue

			nodeDict = child.getObjectMember(self)
			self._resourcesByType[child.key] = nodeDict

	def __str__(self):
		return f"{self.__class__.__name__}({self.name})"

	@classmethod
	def initializedDictAccessors(klass):
		if klass in ResourceCollection._initializedDictAccessors:
			return
		ResourceCollection._initializedDictAccessors.add(klass)

		for item in klass.schema:
			if not isinstance(item, DictNodeSchema):
				continue

			settingsKlass = getattr(item, "_settingsKlass", None)
			if not settingsKlass:
				continue

			# I hate copy'n'paste coding, so let's make it easier for me
			# and more complicated for anyone debugging this:
			# for a resource type named "package", create a property
			# named "packages" that returns self._packages.values()
			dictIteratorName = f"{item.key}s"
			setattr(klass, dictIteratorName, property(item.dictValuesGetter))

			# print(f"Defined {klass.__name__}.{dictIteratorName}; returns list of {settingsKlass.__name__}")

	@property
	def allResources(self):
		return functools.reduce(lambda a, b: a + b,
				[list(dictNode.values()) for dictNode in self._resourcesByType.values()],
				[])

	def addResourceSettings(self, resInfo):
		typeDict = self._resourcesByType[resInfo.resource_type]
		typeDict.mergeItem(resInfo)

class PackageResourceSettings(ResourceCollection):
	resource_type = "package"

	def mergeNoOverride(self, other):
		pass

class ResourceContext(ResourceCollection):
	resource_type = "context"

	schema = [
		makeResourceDict(PackageResource, PackageResourceSettings),
		DictNodeSchema("_conditionals", "conditional", Expectation),
	]

	@property
	def conditionals(self):
		return self._conditionals.values()

	# A package is a collection of resources. We want all resources
	# defined by it to refer back to the containing package by name,
	# so that we can later automatically install the package if they're
	# absent from the SUT.
	def resolvePackages(self):
		# print(self.name)
		for pkg in self.packages:
			# print(pkg)
			for resInfo in pkg.allResources:
				if resInfo.isPackageBacked:
					# print(f"  {resInfo} package = {pkg.name}")
					resInfo.setBackingPackage(pkg.name)

				self.addResourceSettings(resInfo)

	def merge(self, other):
		assert(isinstance(other, ResourceContext))

		for key, nodeDict in other._resourcesByType.items():
			self._resourcesByType[key].merge(nodeDict)

		# We could also do just a simple dict.update() and be done with it.
		# For robustness, we make sure the user does not define multiple conditionals
		# with the same name in different files.
		for cond in other.conditionals:
			have = self._conditionals.get(cond.name)
			if have is not None:
				raise BadConditional(f"{cond.name} from {cond.origin}: duplicate definition of resource conditional (also defined in {have.origin})")

			self._conditionals.add(cond)


	def createResource(self, node, resourceType, resourceName):
		# Given a name like "executable", retrieve the ExecutableResource class
		typeDict = self._resourcesByType.get(resourceType)
		if typeDict is None:
			raise ValueError(f"Undefined resource type {resourceType}")

		resourceKlass = typeDict.item_class.resourceClass

		# Instantiante the resource...
		res = resourceKlass(resourceName)

		# ... and apply the resource definitions from file
		settings = typeDict.get(resourceName)
		if settings:
			res.configure(settings)
			if False:
				print(f"configured resource {res}")
				res.publishToPath("/dev/stdout")

		# Now see if the resource references any conditionals
		self.resolveConditionals(res)

		res.target = node

		print(f"Returning {res}")
		assert(isinstance(res, Resource))
		return res

	def resolveConditionals(self, res):
		if isinstance(res, ExecutableResource):
			for name in res._expected_failures_by_name:
				cond = self._conditionals.get(name)
				if cond is None:
					raise BadConditional(f"{cond.longdesc}: {res} references unknown conditional {name}")
				res._expected_failures.append(ExpectedFailure.fromConditional(cond))
			for name in res._expected_errors_by_name:
				cond = self._conditionals.get(name)
				if cond is None:
					raise BadConditional(f"{cond.longdesc}: {res} references unknown conditional {name}")
				res._expected_errors.append(ExpectedError.fromConditional(cond))

##################################################################
# Global resource inventory
##################################################################
class ResourceInventory:
	def __init__(self):
		self.resources = []

	def findResource(self, node, resourceType, resourceName):
		for res in self.resources:
			if res.target == node \
			   and res.resource_type == resourceType \
			   and res.name == resourceName:
				return res

	def addResource(self, res):
		self.resources.append(res)

##################################################################
# Conditionals - a boolean expression
##################################################################
class ResourceConditional:
	class Equal:
		def __init__(self, name, value):
			self.name = name
			self.value = value

		def dump(self):
			return f"{self.name} == {self.value}"

		def eval(self, context):
			return context.testValue(self.name, self.value)

	class OneOf:
		def __init__(self, name, values):
			self.name = name
			self.values = [_.lower() for _ in values]

		def dump(self):
			return f"{self.name} in {self.values}"

		def eval(self, context):
			return context.testValues(self.name, self.values)

	class FeatureTest:
		def __init__(self, name):
			self.name = name

		def dump(self):
			return f"feature({self.name})"

		def eval(self, context):
			return context.testFeature(self.name)

	class ParameterTest:
		def __init__(self, name, values):
			self.name = name
			self.values = values

		def dump(self):
			return f"parameter({self.name}) in {self.values}"

		def eval(self, context):
			return context.testParameter(self.name, self.values)

	class AndOr:
		def __init__(self, clauses = None):
			self.clauses = clauses or []

		def add(self, term):
			self.clauses.append(term)

		def _dump(self):
			return (term.dump() for term in self.clauses)

		def eval_all(self, context):
			return (term.eval(context) for term in self.clauses)

	class AND(AndOr):
		def dump(self):
			return " AND ".join(self._dump())

		def eval(self, context):
			return all(self.eval_all(context))

	class OR(AndOr):
		def dump(self):
			terms = (f"({t}" for t in self._dump())
			return " OR ".join(terms)

		def eval(self, context):
			return any(self.eval_all(context))

	class NOT:
		def __init__(self, term):
			self.term = term

		def dump(self):
			return f"NOT ({self.term.dump()})"

		def eval(self, context):
			return not self.term.eval(context)

	@staticmethod
	def fromConfig(node, termClass = AND):
		term = termClass()
		for attr in node.attributes:
			if attr.name == 'reason':
				# This is handled in the caller
				pass
			elif attr.name == 'feature':
				term.add(ResourceConditional.FeatureTest(attr.value))
			elif attr.name == 'parameter':
				test = ResourceConditional.resourceConditionalBuildParameterTest(attr.values)
				if test is None:
					raise BadConditional(f"{node.name} from {node.origin}: unable to parse parameter test")

				term.add(test)
			else:
				# all other tests refer to user supplied variables
				test = ResourceConditional.OneOf(attr.name, attr.values)
				term.add(test)

		for child in node:
			if child.type == 'or':
				term.add(ResourceConditional.fromConfig(child, ResourceConditional.OR))
			elif child.type == 'not':
				test = ResourceConditional.fromConfig(child)
				term.add(ResourceConditional.NOT(test))
			else:
				raise BadConditional(f"{node.name} from {node.origin}: don't know how to handle conditional {child.type}")

		# print("Parsed conditional %s: %s" % (node.name, term.dump()))
		return term

	@staticmethod
	def resourceConditionalBuildParameterTest(kvpairs):
		param = None
		values = []
		for kv in kvpairs:
			if '=' not in kv:
				return None
			key, value = kv.split('=', maxsplit = 1)
			if param is None:
				param = key
			elif param != key:
				return None

			values.append(value)
		return ResourceConditional.ParameterTest(param, values)

class TargetEvalContext:
	def __init__(self, driver, target, variables = {}):
		self.driver = driver
		self.target = target
		self.variables = variables

	def testFeature(self, name):
		# print(f"   testFeature({name})")
		return self.target.testFeature(name)

	def testParameter(self, name, values):
		actual = self.driver.getParameter(name)

		# print(f"   testParameter({name}={actual}, values={values})")
		if actual is None:
			return False

		return actual in values

	def testValues(self, name, values):
		actual = self.variables.get(name).lower()

		# print(f"   testParameter({name}={actual}, values={values})")
		if name is None:
			return False

		return actual in values

class BadResource(Exception):
	pass

class BadConditional(Exception):
	pass

##################################################################
# Resource loader - load OS specific resource definitions
# from one or more config files.
##################################################################
class ResourceLoader:
	def __init__(self):
		self.namedConditionals = {}

	def getResourceGroup(self, name, file_must_exist):
		name = name.lower()

		default_paths = [
			twopence.user_config_dir,
			twopence.global_config_dir,
		]

		context = ResourceContext(name)
		found = False

		for path in default_paths:
			path = os.path.expanduser(path)
			path = os.path.join(path, "resource.d", name + ".conf")
			# print("Trying to load %s" % path)
			if os.path.isfile(path):
				context.configureFromPath(path)
				found = True

		if file_must_exist and not found:
			raise KeyError(f"Unable to find {name}.conf")

		context.resolvePackages()

		return context

##################################################################
# Keep track of desired state of resources
##################################################################
class ResourceManager:
	def __init__(self, driver):
		self.driver = driver

		self.inventory = ResourceInventory()
		self.loader = ResourceLoader()
		self.resourceContexts = {}

		self._plugged = True

	def plug(self):
		self._plugged = True

	def unplug(self):
		self._plugged = False

	def getNodeResourceContext(self, target):
		context = self.resourceContexts.get(target.name)
		if context is None:
			context = ResourceContext(target.name)
			self.resourceContexts[target.name] = context
		return context

	def loadPlatformResources(self, target, filenames):
		# Load resource definitions from the given list of resource files.
		# Then collapse these into one set of resource definitions.
		# This allows you to define the generic info on say sudo
		# in one file, and the selinux specific information in another one.
		nodeContext = self.getNodeResourceContext(target)
		for name in filenames:
			context = self.loader.getResourceGroup(name, file_must_exist = True)
			if context:
				nodeContext.merge(context)

	def getResource(self, node, resourceType, resourceName, create = False):
		res = self.inventory.findResource(node, resourceType, resourceName)
		if res is None and create:
			nodeContext = self.getNodeResourceContext(node)
			res = nodeContext.createResource(node, resourceType, resourceName)

			self.inventory.addResource(res)
			node.addResource(res)

		return res

	# given a list of resources, return those that are of a given type
	def filterResources(self, resourceType, resourceList):
		for res in resourceList:
			if res.resource_type == resourceType:
				yield res

	class ResourceAction:
		def __init__(self, state, verb):
			self.state = state
			self.verb = verb

		def perform(self, driver, res, mandatory):
			if mandatory:
				desc = f"{self.verb} mandatory resource {res}"
			else:
				desc = f"{self.verb} optional resource {res}"

			if not res.is_present:
				return self.resourceTransitionFailed(res, f"unable to {desc}: resource not present", mandatory)

			if res.state == self.state:
				return True

			susetest.say(f"about to {desc}")

			change_fn = getattr(res, self.verb)
			ok = change_fn(driver)

			if ok:
				# move to target state
				res.state = self.state
			else:
				ok = self.resourceTransitionFailed(res, f"unable to {desc}", mandatory)

			return ok

		def resourceTransitionFailed(self, res, msg, mandatory):
			if mandatory:
				res.target.logError(msg)
				return False

			res.target.logInfo(msg)
			return True

	_actionAcquire = ResourceAction(Resource.STATE_ACTIVE, "acquire")
	_actionRelease = ResourceAction(Resource.STATE_INACTIVE, "release")

	def acquire(self, res, mandatory, **kwargs):
		return self._actionAcquire.perform(self.driver, res, mandatory, **kwargs)

	def release(self, res, mandatory, **kwargs):
		return self._actionRelease.perform(self.driver, res, mandatory, **kwargs)

##################################################################
# This must happen at the very end of the file:
##################################################################
Schema.initializeAll(globals())

