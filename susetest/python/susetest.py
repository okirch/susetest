##################################################################
#
# Python classes for susetest
#
# These classes refer back to some C code in susetestimpl
#
##################################################################
import susetestimpl
import suselog
import twopence
import re

ifcfg_template = '''
BOOTPROTO="static"
STARTMODE="auto"
IPADDR="@IPADDR@"
'''

class Config(susetestimpl.Config):
	def __init__(self, name, **kwargs):
		super(Config, self).__init__(**kwargs)

		self.name = name

		reportPath = self.value("report")
		if not reportPath:
			reportPath = "report.xml"
		self.journal = suselog.Journal(name, path = reportPath);

class Target(twopence.Target):
	def __init__(self, config):
		super(Target, self).__init__(config.get('target'), config.attrs, config.name)

		self.config = config
		self.journal = config.container.journal

		self.defaultUser = None

		# Initialize some commonly used attributes
		self.name = config.name
		self.ipaddr = config.get('ipv4_addr')
		if not self.ipaddr:
			self.ipaddr = config.get('ipaddr')
		self.ip6addr = None

	def logInfo(self, message):
		self.journal.info(self.name + ": " + message)

	def logFailure(self, message):
		self.journal.failure(self.name + ": " + message)

	def logError(self, message):
		self.journal.error(self.name + ": " + message)

	def configureOtherNetworks(self):
		result = True

		iflist = self.config.children("interface")
		for interface in iflist:
			ifname = interface.name

			if ifname == "eth0":
				continue

			self.journal.beginTest(None, "Try to bring up interface " + ifname)

			ifcfg = self._buildIfconfig(interface)
			if not self.sendbuffer("/etc/sysconfig/network/ifcfg-" + ifname, ifcfg, user = 'root'):
				self.logError("failed to upload interface config for " + ifname)
				result = False
				continue

			if not self.run("ifup " + ifname, user = 'root'):
				self.logError("failed to bring up interface " + ifname)
				result = False
				continue

		return result

	def _buildIfconfig(self, interface):
		global ifcfg_template

		if_ipaddr = interface.get('ipv4_addr')
		if not if_ipaddr:
			print "%s: no ipv4 addr for interface %s" % (self.name, interface.name)
			return None

		subnet = None
		netname = interface.get('network')
		if netname:
			network = self.config.container.network(netname)
			if network:
				subnet = network.get('subnet')

		prefixlen = 0
		if not subnet:
			print "%s: no subnet info for interface %s (network %s)" % (self.name, interface.name, netname)
		else:
			m = re.match(".*/([0-9]*)", subnet)
			if m:
				prefixlen = m.group(1)
		if not prefixlen:
			print "Assuming 24 bit prefix"
			prefixlen = 24

		if_ipaddr = if_ipaddr + "/" + str(prefixlen)

		self.logInfo("%s: using IP address %s" % (interface.name, if_ipaddr))
		ifcfg = re.sub('@IPADDR@', if_ipaddr, ifcfg_template)
		return ifcfg

	def fqdn(self):
		status = self.run("hostname -f")
		if not status:
			self.logError("cannot get fully qualified hostname")
			return None

		fqdn = str(status.stdout).strip()
		if not fqdn:
			self.logError("cannot get fully qualified hostname")
			return None

		return fqdn

	def run(self, cmd, **kwargs):
		fail_on_error = 0
		if isinstance(kwargs, dict) and kwargs.has_key('fail_on_error'):
			fail_on_error = kwargs['fail_on_error']
			del kwargs['fail_on_error']


		if not isinstance(cmd, twopence.Command):
			cmd = twopence.Command(cmd, **kwargs)
		if kwargs is not None:
			for key, value in kwargs.iteritems():
				if key == "suppressOutput" and value:
					# argh, crappy interface - we need to fix this pronto
					cmd.suppressOutput()
				else:
					setattr(cmd, key, value)

		if not(cmd.user) and self.defaultUser:
			cmd.user = self.defaultUser

		self.journal.info(self.name + ": " + cmd.commandline)

		# FIXME: we should catch commands that have the background
		# flag set. Right now, we can't because the attribute
		# isn't implemented in the python twopence extension yet.

		# Call twopence.Target.run() to execute the
		# command for real.
		# If there's an exception, catch it and log an error.
		try:
			status = super(Target, self).run(cmd)
		except:
			self.logError("command execution failed with exception")
		        status = twopence.Status(256, bytearray(), bytearray())

		if status == None or isinstance(status, bool):
			# The command was backgrounded, and there is no status
			# yet.
			self.logInfo("Command was backgrounded")
			if fail_in_error:
				self.logInfo("ignoring fail_on_error setting for backgrounded commands")
			return True

		if not status:
			msg = "command \"" + cmd.commandline + "\" failed: " + status.message
			if fail_on_error:
				self.logFailure(msg)
			else:
				self.logInfo(msg)

		self.journal.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.journal.recordStderr(status.stderr);

		return status

	def runOrFail(self, cmd, **kwargs):
		kwargs['fail_on_error'] = 1;
		return self.run(cmd, **kwargs)

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

		if not status:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" failed: " + status.message)
		else:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" finished")

		self.journal.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.journal.recordStderr(status.stderr);

		return status

	def recvbuffer(self, remoteFilename, **kwargs):
		xfer = twopence.Transfer(remoteFilename, **kwargs)
		if self.defaultUser:
			xfer.user = self.defaultUser

		if xfer.localfile:
			self.logError("recvbuffer: you cannot specify a localfile!")
			return None

		self.logInfo("downloading " + remoteFilename)
		status = self.recvfile(xfer)
		if not status:
			self.logFailure("download failed: " + status.message)
			return None

		self.logInfo("<<< --- Data: ---\n" + str(status.buffer) + "\n --- End of Data --->>>\n");
		return status.buffer

	def sendbuffer(self, remoteFilename, buffer, **kwargs):
		xfer = twopence.Transfer(remoteFilename, data = bytearray(buffer), **kwargs)
		if self.defaultUser:
			xfer.user = self.defaultUser

		self.logInfo("uploading data to " + remoteFilename)
		self.logInfo("<<< --- Data: ---\n" + str(xfer.data) + "\n --- End of Data --->>>\n");
		return self.sendfile(xfer)

	def addHostEntry(self, addr, fqdn):
		alias = fqdn.split('.')[0]
		if alias != fqdn:
			line = "%s %s %s" % (addr, fqdn, alias)
		else:
			line = "%s %s" % (addr, fqdn)

		self.logInfo("downloading /etc/hosts")
		status = self.recvfile("/etc/hosts");
		if not status:
			self.logError("unable to download hosts file");
			return False;

		if line in str(status.buffer).split('\n'):
			self.logInfo("requested line already in hosts file, nothing to be done")
			return True

		buffer = status.buffer + "\n" + line + "\n"
		if not self.sendfile("/etc/hosts", data = buffer, user = "root"):
			self.logError("unable to upload modified hosts file");
			return False

		self.run("rcnscd reload", user = "root")

		return True

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
