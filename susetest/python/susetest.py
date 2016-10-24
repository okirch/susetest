##################################################################
#
# Python classes for susetest
#
# These classes refer back to some C code in susetestimpl
#
##################################################################
import exceptions
import suselog
import twopence
import time
import re
import sys

ifcfg_template = '''
BOOTPROTO="static"
STARTMODE="auto"
IPADDR="@IPADDR@"
'''

# This class is needed for break a whole testsuite, exit without run all tests. Wanted in some scenarios.
# Otherwise we can use susetest.finish(journal) to continue after  failed tests, 
class SlenkinsError(Exception):
                def __init__(self, code):
                        self.code = code
                def __str__(self):
                        return repr(self.code)
# Same for basiliqa
class BasiliqaError(Exception):
                def __init__(self, code):
                        self.code = code
                def __str__(self):
			return repr(self.code)

# finish the junit report.
def finish(journal):
        journal.writeReport()
        if (journal.num_failed() + journal.num_errors()):
                        sys.exit(1)
        sys.exit(0)


class ConfigWrapper():
	def __init__(self, name, data):
		self.name = name
		self.data = data

		# Set the workspace
		self.workspace = self.data.workspace()
		if not self.workspace:
			print "Oops, no workspace defined. Using current directory"
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
	try:
		import curly

		return ConfigWrapper(name, curly.Config(**kwargs));
	except:
		pass

	try:
		import testenv

		return ConfigWrapper(name, testenv.Testenv(**kwargs))
	except:
		pass
	
	raise exceptions.RuntimeError("unable to create a valid config object")
	return None


class Target(twopence.Target):
	def __init__(self, name, config):
		super(Target, self).__init__(config.target_spec(name), None, name)

		self.config = config
		self.journal = config.journal

		self.defaultUser = None

		# Initialize some commonly used attributes
		self.name = name

		self.ipv4_addr = config.ipv4_address(self.name)
		self.ipv6_addr = config.ipv6_address(self.name)
                # N/A when ipv6 is not available.
                if (self.ipv6_addr == "N/A"):
                	self.ipv6_addr = None
                
		# Backward compat
		self.ipaddr = self.ipv4_addr
		self.ip6addr = self.ipv6_addr
                # external ip for cloud
                self.ipaddr_ext = config.ipv4_ext(self.name)
  		# *** os attributes ***
		# family 42.1 , 12.2 etc 
		self.family = self.get_family()
		# boolean var, true if gnome,kde are used, else false 
		self.desktop = self.get_graphical()
		# this is from cat /etc/YaST2/build
		self.build =  self.get_build()
		# hostname (not fully qualified)
		self.hostname = self.get_hostname()
        
	def get_hostname(self):
		''' get hostname of the sut '''
                status = self.run("hostname", quiet=True)
                if not status:
                        self.logError("cannot get os-release family")
                        return None

                hostname = str(status.stdout)
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
                build = str(status.stdout)
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
                family = str(status.stdout)
                if not family:
                        self.logError("cannot get os-release strings")
                        return None
                return family.rstrip()

		self.__syslogSize = -1
	



	def logInfo(self, message):
		self.journal.info(self.name + ": " + message)

	def logFailure(self, message):
		self.journal.failure(self.name + ": " + message)

	def logError(self, message):
		self.journal.error(self.name + ": " + message)

	def describeException(self):
	        import traceback

		return traceback.format_exc(None)

	def configureOtherNetworks(self):
		result = True

		# iflist = self.config.node_interfaces(self.name)
		iflist = []

		for ifname in iflist:
			if ifname == "eth0":
				continue

			self.journal.beginTest(None, "Try to bring up interface " + ifname)

			ifcfg = self._buildIfconfig(ifname)
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

		# XXXX: Currently broken
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

	def workspaceFile(self, relativeName = None):
		path = self.config.workspace
		if relativeName:
			path = path + "/" + relativeName
		return path

	def __run(self, cmd, **kwargs):
		return super(Target, self).run(cmd, **kwargs)

	def run(self, cmd, **kwargs):
		fail_on_error = 0
		if isinstance(kwargs, dict) and kwargs.has_key('fail_on_error'):
			fail_on_error = kwargs['fail_on_error']
			del kwargs['fail_on_error']

		# Workaround for a twopence problem
		if isinstance(kwargs, dict) and kwargs.has_key('timeout'):
			if kwargs['timeout'] < 0:
				del kwargs['timeout']

		if not isinstance(cmd, twopence.Command):
			cmd = twopence.Command(cmd, **kwargs)
		elif kwargs is not None:
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
		t0 = time.time()
		try:
			status = super(Target, self).run(cmd)
		except:
			self.logError("command execution failed with exception")
			self.journal.info(self.describeException())

			t1 = time.time()
			self.journal.info("Command ran for %u seconds" % (t1 - t0))

		        status = twopence.Status(256, bytearray(), bytearray())

		if status == None or isinstance(status, bool):
			# The command was backgrounded, and there is no status
			# yet.
			self.logInfo("Command was backgrounded")
			if fail_on_error:
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

		cmd = status.command
		if not status:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" failed: " + status.message)
		else:
			self.logInfo("backgrounded command \"" + cmd.commandline + "\" finished")

		self.journal.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.journal.recordStderr(status.stderr);

		return status

	def sendfile(self, remotefile, **kwargs):
		if self.defaultUser and not kwargs.has_key('user'):
			kwargs['user'] = self.defaultUser

		self.logInfo("uploading " + remotefile)
		try:
			status = super(Target, self).sendfile(remotefile, **kwargs)
		except:
			self.logError("upload failed with exception")
			self.journal.info(self.describeException())
		        return None

		if not status:
			self.logFailure("upload failed: " + status.message)

		return status

	def recvfile(self, remotefile, **kwargs):
		if self.defaultUser and not kwargs.has_key('user'):
			kwargs['user'] = self.defaultUser

		self.logInfo("downloading " + remotefile)
		try:
			status = super(Target, self).recvfile(remotefile, **kwargs)
		except:
			self.logError("download failed with exception")
			self.journal.info(self.describeException())
		        return None

		if not status:
			self.logFailure("download failed: " + status.message)

		return status


	def recvbuffer(self, remoteFilename, **kwargs):
		if self.defaultUser and not kwargs.has_key('user'):
			kwargs['user'] = self.defaultUser

		quiet = False
		if kwargs.has_key('quiet') and kwargs['quiet']:
			quiet = kwargs['quiet']
			del kwargs['quiet']

		xfer = twopence.Transfer(remoteFilename, **kwargs)

		if xfer.localfile:
			self.logError("recvbuffer: you cannot specify a localfile!")
			return None

		self.logInfo("downloading " + remoteFilename)
		try:
			status = super(Target, self).recvfile(xfer)
		except:
			self.logError("download failed with exception")
			self.journal.info(self.describeException())

		        return None

		if not status:
			self.logFailure("download failed: " + status.message)
			return None

		if not quiet:
			self.logInfo("<<< --- Data: ---\n" + str(status.buffer) + "\n --- End of Data --->>>\n");
		return status.buffer

	def sendbuffer(self, remoteFilename, buffer, **kwargs):
		if self.defaultUser and not kwargs.has_key('user'):
			kwargs['user'] = self.defaultUser

		quiet = False
		if kwargs.has_key('quiet') and kwargs['quiet']:
			quiet = kwargs['quiet']
			del kwargs['quiet']

		xfer = twopence.Transfer(remoteFilename, data = bytearray(buffer), **kwargs)
		if xfer.permissions < 0:
			xfer.permissions = 0

		self.logInfo("uploading data to " + remoteFilename)
		if not quiet:
			self.logInfo("<<< --- Data: ---\n" + str(xfer.data) + "\n --- End of Data --->>>\n");

		if not isinstance(xfer.data, bytearray):
			print "data is not a buffer"

		try:
			return super(Target, self).sendfile(xfer)
		except:
			self.logError("upload failed with exception")
			self.journal.info(self.describeException())

		        return twopence.Status(256)

	# These functions can help you capture log messages written
	# while a test was executed.
	# Use them as
	#  server.syslogCapture()
	#  ... do stuff ...
	#  if stuffFailed:
	#	server.syslogDisplay()
	def syslogCapture(self):
		self.__syslogSize = -1
		try:
			status = server.__run("/bin/stat -c %s /var/log/messages", quiet = True)
			self.__syslogSize = int(status.stdout)
		except:
			pass

	def syslogDisplay(self):
		if self.__syslogSize < 0:
			return

		try:
			status = server.__run("dd bs=1 skip=%u if=/var/log/messages" % self.__syslogSize, quiet = True)
			if status and len(status.stdout):
				journal.info("--- begin %s log messages ---" % self.name)
				journal.recordStdout(status.stdout);
				print str(status.stdout)
				journal.info("--- end %s log messages ---" % self.name)
		except:
			pass

		self.__syslogSize = -1

	# Add a new entry to the node's hosts file.
	# if @clobber is set, all other entries containing either the hostname
	# or the IP address will be removed, so that applications do not
	# get confused by conflicting information in forward or reverse host lookups
	def addHostEntry(self, addr, fqdn, clobber = False):
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

		if clobber:
			found = False
			changed = False
			result = []
			for l in str(status.buffer).split('\n'):
				if l == line:
					result.append(l)
					found = True
					continue

				# nuke comments and split line
				n = l.find('#')
				if n >= 0:
					w = l[:n].split()
				else:
					w = l.split()

				if addr in w or alias in w or fqdn in w:
					self.logInfo("removing conflicting hosts entry \"%s\"" % l)
					changed = True
					continue

				result.append(l)

			if not found:
				result.append(line)
				changed = True

			if not changed:
				self.logInfo("requested line already in hosts file, nothing to be done")
				return True

			buffer = bytearray("\n".join(result))
		else:
			if line in str(status.buffer).split('\n'):
				self.logInfo("requested line already in hosts file, nothing to be done")
				return True

			buffer = status.buffer + "\n" + line

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
