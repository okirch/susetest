##################################################################
#
# Target handling for susetest, extends twopence.Target
#
# Copyright (C) 2014-2021 SUSE Linux GmbH
#
##################################################################

import suselog
import susetest
import twopence
import time
import re
import sys

from .resources import ConcreteExecutableResource, ConcreteStringValuedResource, StringValuedResource

class Target(twopence.Target):
	def __init__(self, name, node_config, logger = None, resource_manager = None):
		spec = node_config.get_value("target")
		if spec is None:
			raise ValueError("Cannot connect to node %s: config doesn't specify a target" % name)

		super(Target, self).__init__(spec, None, name)
		self.connectionDead = False

		self.node_config = node_config
		self.logger = logger
		self.resourceManager = resource_manager
		self.serviceManager = None
		self.packageManager = None

		self.defaultUser = None

		# Initialize some commonly used attributes
		self.name = name

		self.ipv4_addr = node_config.get_value("ipv4_address")
		self.ipv4_address = self.ipv4_addr
		self.ipv6_addr = node_config.get_value("ipv6_address")
		self.ipv6_address = self.ipv6_addr
		self.features = node_config.get_values("features")
		self.resource_files = node_config.get_values("resources")
		self.test_user = node_config.get_value("test-user")
		self.os_vendor = node_config.get_value("vendor")
		self.os_release = node_config.get_value("os")

		# Backward compat
		self.ipaddr = self.ipv4_addr
		self.ip6addr = self.ipv6_addr

		# external ip for cloud
		self.ipaddr_ext = node_config.get_value("ipv4_address_external")

		self._resources = {}
		self._enabled_features = []

		# OS attributes; will be populated on demand by querying the SUT
		self._family = None
		self._desktop = None
		self._build = None
		self._hostname = None


	def setServiceManager(self, serviceManager):
		susetest.say(f"Setting service manager {serviceManager.name}")
		self.serviceManager = serviceManager

	def setPackageManager(self, packageManager):
		susetest.say(f"Setting package manager {packageManager.name}")
		self.packageManager = packageManager

	# family 42.1 , 12.2 etc
	@property
	def family(self):
		if self._family is None:
			self._family = self.get_family()
		return self._family

	# boolean var, true if gnome,kde are used, else false
	@property
	def desktop(self):
		if self._desktop is None:
			self._desktop = self.get_graphical()
		return self._desktop

	# this is from cat /etc/YaST2/build
	@property
	def build(self):
		if self._build is None:
			self._build = self.get_build()
		return self._build

	# hostname (not fully qualified)
	@property
	def hostname(self):
		if self._hostname is None:
			self._hostname = self.get_hostname()
		return self._hostname

	def get_hostname(self):
		''' get hostname of the sut '''
		status = self.run("hostname", quiet=True)
		if not status:
			self.logError("cannot get os-release family")
			return None

		hostname = status.stdoutString
		return hostname.rstrip()



	def get_graphical(self):
		''' return true if gnome is enabled, false if minimal'''
		status = self.run("test -x /usr/bin/gdm", quiet=True)
		if (status.code == 0):
			graphical = True
		else :
			graphical = False
		return graphical

	def get_build(self):
		''' '''
		status = self.run("cat /etc/YaST2/build", quiet=True)
		if not status:
			self.logError("cannot get build of system")
			return None
		build = status.stdoutString
		if not build:
			self.logError("cannot get os-release strings")
			return None
		return build.rstrip()

	def get_family(self):
		''' get_family return a string : 42.1(leap), 12.2, 12.1, 11.4 for  sles etc. '''
		status = self.run("grep VERSION_ID /etc/os-release | cut -c13- | head -c -2 ", quiet=True)
		if not status:
			self.logError("cannot get os-release family")
			return None
		family = status.stdoutString
		if not family:
			self.logError("cannot get os-release strings")
			return None
		return family.rstrip()

		self.__syslogSize = -1

	def requireUser(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("user", name, mandatory = True, **stateArgs)

	def requireExecutable(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("executable", name, mandatory = True, **stateArgs)

	def requireService(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("service", name, mandatory = True, **stateArgs)

	def requireFile(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("file", name, mandatory = True, **stateArgs)

	def requirePackage(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("package", name, mandatory = True, **stateArgs)

	# known event sources: audit, journal
	def requireEvents(self, name, **stateArgs):
		return self.acquireResourceTypeAndName(name, name, mandatory = True, **stateArgs)

	def optionalUser(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("user", name, mandatory = False, **stateArgs)

	def optionalExecutable(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("executable", name, mandatory = False, **stateArgs)

	def optionalService(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("service", name, mandatory = False, **stateArgs)

	def optionalFile(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("file", name, mandatory = False, **stateArgs)

	def optionalPackage(self, name, **stateArgs):
		return self.acquireResourceTypeAndName("package", name, mandatory = False, **stateArgs)

	def defineStringResource(self, name, value, **stateArgs):
		res = self.instantiateResourceTypeAndName("string", name)

		if res.is_active:
			raise ValueError("%s: unable to redefine active string resource \"%s\"" % (self.name, name))
		res.value = value

		# We just defined it, so we should make it mandatory
		stateArgs['mandatory'] = True

		self.acquireResource(res, **stateArgs)
		return res

	def expandStringResource(self, name):
		res = self.getResource("string", name)
		if res is None:
			return None

		if not isinstance(res, StringValuedResource):
			raise ValueError("parameter \"%s\" is not a string" % name)

		return res.value

	@property
	def resources(self):
		return self._resources.values()

	def getResource(self, type, name):
		key = "%s:%s" % (type, name)
		return self._resources.get(key)

	def acquireResourceTypeAndName(self, resourceType, resourceName, **stateArgs):
		res = self.instantiateResourceTypeAndName(resourceType, resourceName)
		self.acquireResource(res, **stateArgs)
		return res

	def instantiateResourceTypeAndName(self, type, name):
		assert(self.resourceManager)

		res = self.getResource(type, name)
		if res is None:
			res = self.resourceManager.getResource(self, type, name, create = True)
			if res is None:
				raise ValueError("failed to instantiate %s resource \"%s\"" % (type, name))
			self.addResource(res)

		return res

	def acquireResource(self, res, **stateArgs):
		if 'mandatory' not in stateArgs:
			raise ValueError("cannot acquire resource %s: caller did not specify whether it's mandatory or optional" % res)

		self.resourceManager.acquire(res, **stateArgs)

	def addResource(self, resource):
		key = "%s:%s" % (resource.resource_type, resource.name)
		self._resources[key] = resource

	def getActiveResource(self, name):
		resource = self._resources.get(name)
		if resource and not resource.is_active:
			resource = None
		return resource

	def testFeature(self, feature):
		if type(feature) == str:
			return any((f.name == feature) for f in self._enabled_features)
		return feature in self._enabled_features

	def enabledFeature(self, feature):
		self._enabled_features.append(feature)

	@property
	def is_systemd(self):
		return True

	def logInfo(self, message):
		self.logger.logInfo(self.name + ": " + message)

	def _logInfo(self, message):
		self.logger.logInfo(message)

	def logFailure(self, message):
		self.logger.logFailure(self.name + ": " + message)

	def _logFailure(self, message):
		self.logger.logFailure(message)

	def logError(self, message):
		self.logger.logError(self.name + ": " + message)

	def _logError(self, message):
		self.logger.logError(message)

	def describeException(self):
		import traceback

		return traceback.format_exc(None)

	def fqdn(self):
		status = self.run("hostname -f")
		if not status:
			self.logError("cannot get fully qualified hostname")
			return None

		fqdn = status.stdoutString.strip()
		if not fqdn:
			self.logError("cannot get fully qualified hostname")
			return None

		return fqdn

	def workspaceFile(self, relativeName = None):
		path = self.config.workspace
		if relativeName:
			path = path + "/" + relativeName
		return path

	def handleException(self, operation, exc):
		self.logError("%s failed: %s" % (operation, exc))
		self._logInfo(self.describeException().strip())

		if exc.code in (twopence.OPEN_SESSION_ERROR, ):
			self.logError("this is a fatal error; all future communication on this node will fail");
			self.connectionDead = True

			# re-raise the exception
			raise exc

	# Call twopence.Target.run() to execute the
	# command for real.
	# If there's an exception, catch it and log an error.
	def _run(self, cmd, **kwargs):
		if self.connectionDead:
			self.logError("SUT is dead, not running command")
			return twopence.Status(256, bytearray(), bytearray())

		t0 = time.time()
		try:
			status = super().run(cmd, **kwargs)
		except twopence.Exception as e:
			self.handleException("command execution", e)

			t1 = time.time()
			self._logInfo("Command ran for %u seconds" % (t1 - t0))

			status = twopence.Status(256, bytearray(), bytearray())

		return status

	# Build/update twopence.Command instance using the kwargs dict provided
	def _buildCommand(self, cmd, environ = None, **kwargs):
		if not isinstance(cmd, twopence.Command):
			cmd = twopence.Command(cmd, **kwargs)
		elif kwargs is not None:
			for key, value in kwargs.items():
				setattr(cmd, key, value)

		if not(cmd.user) and self.defaultUser:
			cmd.user = self.defaultUser

		if environ:
			for name, value in environ.items():
				cmd.setenv(name, value)

		info = []
		if cmd.user:
			info.append("user=%s" % cmd.user)
		if cmd.timeout != 60:
			info.append("timeout=%d" % cmd.timeout)
		if cmd.background:
			info.append("background")

		env = cmd.environ
		if env:
			info += [("%s=\"%s\"" % kv) for kv in env]

		if info:
			info = "; " + ", ".join(info)
		else:
			info = ""

		self.logInfo(cmd.commandline + info)

		return cmd


	def run(self, cmd, fail_on_error = False, **kwargs):
		cmd = self._buildCommand(cmd, **kwargs)

		status = self._run(cmd)

		if isinstance(status, twopence.Process):
			# The command was backgrounded, and there is no status yet.
			self.logInfo("Command was backgrounded")
			if fail_on_error:
				self.logInfo("ignoring fail_on_error setting for backgrounded commands")
			return status

		if not status:
			msg = "command \"" + cmd.commandline + "\" failed: " + status.message
			if fail_on_error:
				self.logFailure(msg)
			else:
				self.logInfo(msg)

		self.logger.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.logger.recordStderr(status.stderr);

		return status

	def runOrFail(self, cmd, **kwargs):
		return self.run(cmd, fail_on_error = True, **kwargs)

	def chat(self, cmd, **kwargs):
		cmd = self._buildCommand(cmd, **kwargs)
		return super().chat(cmd)

	def runChatScript(self, cmd, chat_script, timeoutOkay = False, **kwargs):
		# if not explicitly set to False by the caller, this defaults to True
		if 'tty' not in kwargs:
			kwargs['tty'] = True

		chat = self.chat(cmd, **kwargs)

		for expect, send in chat_script:
			susetest.say("Waiting for \"%s\"" % expect)

			try:
				found = chat.expect(expect)
			except twopence.Exception as e:
				self.logFailure(f"Caught exception: {e}")
				return self._chatScriptFailed(chat, e.code)

			if not found:
				return self._chatScriptFailed(chat, twopence.CHAT_TIMEOUT_ERROR)

			self.logInfo("consumed: %s" % chat.consumed)
			self.logInfo("found prompt: \"%s\"" % chat.found)

			if True:
				import time

				time.sleep(1)

			if send is None:
				continue

			self.logInfo("Sending response \"%s\"" % send)
			chat.send(send + "\r")

		susetest.say("Done with chat script, collecting command status")
		st = chat.wait()

		self.logInfo("consumed: %s" % chat.consumed)
		return st

	def _chatScriptFailed(self, chat, errorCode):
		self.logInfo(f"consumed: {chat.consumed}")

		try:
			chat.kill(signal = "KILL")
		except: pass

		st = chat.wait()
		if st is not None:
			self.logInfo(f"command status: {st.message}")
			self.logger.recordStdout(st.stdout);
		return twopence.Status(error = errorCode)

	def runBackground(self, cmd, **kwargs):
		kwargs['background'] = 1;
		return self.run(cmd, **kwargs)

	def wait(self, cmd = None):
		if cmd:
			status = super(Target, self).wait(cmd)
		else:
			status = super(Target, self).wait()

		if status == None:
			return None

		cmd = status.command
		if not status:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" failed: " + status.message)
		else:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" finished")

		self.logger.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.logger.recordStderr(status.stderr);

		return status

	def sendfile(self, remotefile, user = None, **kwargs):
		if user is None:
			user = self.defaultUser

		self.logInfo("uploading " + remotefile)
		try:
			status = super(Target, self).sendfile(remotefile, user = user, **kwargs)
		except:
			self.logError("upload failed with exception")
			self._logInfo(self.describeException())
			return None

		if not status:
			self.logFailure("upload failed: " + status.message)

		return status

	def recvfile(self, remotefile, user = None, **kwargs):
		if user is None:
			user = self.defaultUser

		self.logInfo("downloading " + remotefile)
		try:
			status = super(Target, self).recvfile(remotefile, user = user, **kwargs)
		except:
			self.logError("download failed with exception")
			self._logInfo(self.describeException())
			return None

		if not status:
			self.logFailure("download failed: " + status.message)

		return status


	def recvbuffer(self, remoteFilename, quiet = False, user = None, **kwargs):
		if user is None:
			user = self.defaultUser

		xfer = twopence.Transfer(remoteFilename, user = user, **kwargs)

		if xfer.localfile:
			self.logError("recvbuffer: you cannot specify a localfile!")
			return None

		self.logInfo("downloading " + remoteFilename)
		try:
			status = super(Target, self).recvfile(xfer)
		except:
			self.logError("download failed with exception")
			self._logInfo(self.describeException())

			return None

		if not status:
			self.logFailure("download failed: " + status.message)
			return None

		if not quiet:
			self.logInfo("<<< --- Data: ---\n" + str(status.buffer) + "\n --- End of Data --->>>\n");
		return status.buffer

	def sendbuffer(self, remoteFilename, buffer, quiet = False, user = None, **kwargs):
		if user is None:
			user = self.defaultUser

		if type(buffer) == str:
			buffer = buffer.encode("utf-8")

		xfer = twopence.Transfer(remoteFilename, data = bytearray(buffer), user = user, **kwargs)
		if xfer.permissions < 0:
			xfer.permissions = 0

		self.logInfo("uploading data to " + remoteFilename)
		if not quiet:
			self.logInfo("<<< --- Data: ---\n" + str(xfer.data) + "\n --- End of Data --->>>\n");

		if not isinstance(xfer.data, bytearray):
			print("data is not a buffer")

		try:
			return super(Target, self).sendfile(xfer)
		except:
			self.logError("upload failed with exception")
			self._logInfo(self.describeException())

			return twopence.Status(256)

	#
	# FIXME: this function does not belong here...
	#
	def changeSysconfigVar(self, filename, var, value):
		if not isinstance(filename, str):
			self.logError("changeSysconfigVar: filename argument must be a string")
			return False

		if filename[0] != '/':
			filename = "/etc/sysconfig/" + filename;

		self.logInfo("Changing sysconfig file %s: set %s=%s" % (filename, var, value))

		data = self.recvbuffer(filename);

		result = []
		found = False
		for line in str(data).split('\n'):
			if re.match("^[# ]*" + var + "=", line):
				if found:
					continue
				line = "%s='%s'" % (var, value)
				found = True
			result.append(line)

		if not found:
			result.append("%s='%s'" % (var, value))

		data = '\n'.join(result)
		if not self.sendbuffer(filename, data):
			self.logFailure("failed to upload changed sysconfig data to %s" % filename);
			return False

		return True
