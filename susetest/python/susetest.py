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
		super(Target, self).__init__(config.target, config.attrs, config.name)

		self.config = config
		self.journal = config.container.journal

		self.defaultUser = None

		# Initialize some commonly used attributes
		self.name = config.name
		self.ipaddr = config.attrs['ipaddr']

	def logInfo(self, message):
		self.journal.info(self.name + ": " + message)

	def logFailure(self, message):
		self.journal.failure(self.name + ": " + message)

	def logError(self, message):
		self.journal.error(self.name + ": " + message)

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
		if not isinstance(cmd, twopence.Command):
			cmd = twopence.Command(cmd)

		self.journal.info(self.name + ": " + cmd.commandline)

		if not(cmd.user) and self.defaultUser:
			cmd.user = self.defaultUser

		if kwargs is not None:
			for key, value in kwargs.iteritems():
				setattr(cmd, key, value)

		status = super(Target, self).run(cmd)
		if not status:
			self.journal.info("command failed: " + status.message)

		self.journal.recordStdout(status.stdout);
		if status.stdout != status.stderr:
			self.journal.recordStderr(status.stderr);

		return status

	def sendbuffer(self, remoteFilename, buffer, **kwargs):

		xfer = twopence.Transfer(remoteFilename, data = bytearray(buffer))
		xfer.user = self.defaultUser

		if kwargs is not None:
			for key, value in kwargs.iteritems():
				setattr(xfer, key, value)

		self.logInfo("uploading data to " + remoteFilename)
		self.journal.info("<<< --- Data: ---\n" + str(xfer.data) + "\n --- End of Data --->>>\n");
		return self.sendfile(xfer)
