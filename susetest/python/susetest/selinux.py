##################################################################
#
# Feature: selinux-alerts
#
# Copyright (C) 2021 SUSE Linux GmbH
#
# This attaches a message filter to the journal resource.
# At the end of each test case, the journal resource checks
# all log messages for kernel errors from the security
# for policy violations.
#
# The same happens when the resource is acquired, which catches
# policy violations that occurred during system startup.
#
##################################################################
from .resources import MessageFilter, ExecutableResource
import susetest
import time

# Typical SELinux message:
# audit: type=1400 audit(1637744082.879:4): \
#	avc:  denied  { write } for  \
#	pid=4429 comm="pam_tally2" name="log" dev="vda3" ino=1449455 \
#	scontext=unconfined_u:unconfined_r:useradd_t:s0 \
#	tcontext=system_u:object_r:var_log_t:s0 \
#	tclass=dir permissive=1
class SELinuxMessageFilter(MessageFilter):
	class Violation:
		def __init__(self):
			self.pid = None
			self.comm = None
			self.path = None
			self.name = None
			self.dev = None
			self.ino = None
			self.scontext = None
			self.tcontext = None
			self.tclass = None

	def __init__(self):
		self.previous = None
		self._checks = []

	def match(self, m, target):
		if m.transport != "kernel" or not m.message.startswith("audit:") or " avc: " not in  m.message:
			return

		if not self._match(m, target):
			self.previous = None

	def _match(self, m, target):
		violation = self.parseViolation(m.message)

		if violation and violation.tclass not in ('process', 'dir', 'file', 'chr_file', 'udp_socket', 'tcp_socket'):
			target.logInfo("parsed unknown SELinux violation tclass=%s (%s)" % (
					violation.tclass, dir(violation)))
			violation = None

		if violation is None:
			target.logFailure("SELinux policy violation")
			target.logInfo(m.message)
			return

		if not self.previous or self.previous.pid != violation.pid:
			rating = self.rateViolation(violation)
			if rating == "info":
				target.logInfo("SELinux policy violation (ignored)")
			else:
				target.logFailure("SELinux policy violation")
			target.logInfo("  by %s (pid=%s; context=%s)" % (
						violation.comm, violation.pid, violation.scontext))

		# ioctls will also have ioctlcmd=0xNNNN
		if violation.tclass in ('dir', 'file', 'chr_file'):
			target.logInfo("    %s access to %s %s (dev=%s; ino=%s; context=%s)" % (
						violation.op,
						violation.tclass,
						violation.path or violation.name,
						violation.dev,
						violation.ino,
						violation.tcontext))
		elif violation.tclass in ('udp_socket', 'tcp_socket', ):
			target.logInfo("    %s access to %s %s (context=%s)" % (
						violation.op,
						violation.tclass,
						violation.src,
						violation.tcontext))
		else:
			target.logInfo("    %s access to %s (context=%s)" % (
						violation.op,
						violation.tclass,
						violation.tcontext))

		self.previous = violation
		return True

	def addCheck(self, fn):
		self._checks.append(fn)

	def rateViolation(self, violation):
		for fn in self._checks:
			r = fn(violation)
			if r is not None:
				return r
		return None

	def parseViolation(self, msg):
		words = msg.split()

		if words.pop(0) != "audit:" or \
		   not words.pop(0).startswith("type=") or \
		   not words.pop(0).startswith("audit(") or \
		   words.pop(0) != "avc:" or \
		   words.pop(0) != "denied":
			return None

		operations = []
		if words.pop(0) != "{":
			return None

		while words:
			w = words.pop(0)
			if w == "}":
				break
			operations.append(w)

		if words.pop(0) != "for":
			return None

		violation = self.Violation()
		for w in words:
			assert('=' in w)
			(key, value) = w.split('=', maxsplit = 1)
			setattr(violation, key, value.strip('"'))

		violation.op = "/".join(operations)

		return violation

def pamTally2ConsideredHarmless(violation):
	if violation.comm == "pam_tally2":
		return "info"
	return None

def twopenceConsideredHarmless(violation):
	if violation.comm == "twopence_test_s":
		return "info"
	return None

# Acquire the journal monitoring resource, and install a
# message filter that checks for SELinux related kernel messages
def enableFeature(driver, node):
	resource = node.requireResource("journal", defer = True)

	filter = SELinuxMessageFilter()
	filter.addCheck(pamTally2ConsideredHarmless)
	filter.addCheck(twopenceConsideredHarmless)

	resource.addFilter(filter)
	susetest.say("%s: installed SELinux filter" % resource)

	driver.performDeferredResourceChanges()

class SELinux:
	def resourceVerifyPolicy(self, node, resourceName):
		if 'selinux' not in node.features:
			node.logInfo("Skipping SELinux test; you may want to label the test with @susetest.requires('selinux')")
			driver.skipTest()
			return

		res = node.getResource(resourceName)
		if res is None:
			node.logError("Unable to find resource %s" % resourceName)
			return

		tested = False
		if isinstance(res, ExecutableResource):
			if not res.path:
				# When defining this test case via susetest.template(), this will automatically
				# ensure that we try to claim the resource during testsuite setup.
				node.logInfo("Skipping SELinux test for %s; resource not present on SUT" % resourceName)
				return

			if res.selinux_label_domain:
				self.checkExecutableLabel(node, res)
				tested = True

			if res.selinux_process_domain:
				self.verifyExecutableProcessDomain(node, res)
				tested = True

		if not tested:
			node.logError("SELinux: don't know how to verify resource %s (type %s)" % (
					res.name, res.__class__.__name__))

	def checkExecutableLabel(self, node, res):
		print("Checking executable's domain (expecting %s)" % res.selinux_label_domain)

		expected = self.buildLabel(domain = res.selinux_label_domain)

		if not res.path:
			node.logError("Unable to get path of executable");
			return

		print("Executable is %s" % res.path)
		status = node.runOrFail("stat -Lc %%C %s" % res.path, stdout = bytearray(), quiet = True)
		if not status:
			return

		label = status.stdoutString.strip()
		if label != expected:
			node.logFailure("Unexpected SELinux label on %s" % res.path)
			node.logInfo("  expected %s" % expected)
			node.logInfo("  actual label %s" % label)
		else:
			node.logInfo("good, %s has expected SELinux label %s" % (res.path, expected));

	def verifyExecutableProcessDomain(self, node, res):
		print("Checking executable's process context (expecting %s)" % res.selinux_process_domain)

		user = node.getResource("test-user")
		if not user.uid:
			node.logError("user %s does not seem to exist" % user.login)
			return

		if not res.interactive:
			# Run a NOP invocation of the command (could also be sth like "cmd --help")
			# and tell twopence to collect the exit status when reaping the child process.
			# This information will be available through Status.process to us.
			cmdline = "%s --bogus-option-should-error >/dev/null 2>&1" % res.path
			cmd = susetest.Command(cmdline, user = user.login, exitInfo = True, quiet = True)
			st = node.run(cmd)

			process_ctx = st.process.selinux_context
		else:
			cmd = susetest.Command(res.path, timeout = 10, user = user.login, background = True)

			proc = node.chat(cmd)
			if not proc:
				node.logFailure("failed to start command \"%s\"" % cmdstring)
				return

			# Insert a minor delay to allow the the server to exec
			# the application, and have it transition to the expected context
			time.sleep(0.5)

			process_ctx = proc.selinux_context

			proc.kill("KILL")
			proc.wait()

		expected = self.buildContext(domain = res.selinux_process_domain)
		if process_ctx != expected:
			node.logFailure("command is running with wrong SELinux context");
			node.logInfo("  expected %s" % expected)
			node.logInfo("  actual context %s" % process_ctx)
			return False

		node.logInfo("good, command is running with expected SELinux context %s" % expected);
		return True

	def buildLabel(self, user = "system_u", role = "object_r", domain = "bin_t", mcs = "s0"):
		return "%s:%s:%s:%s" % (user, role, domain, mcs)

	def buildContext(self, user = "unconfined_u", role = "unconfined_r", domain = "unconfined_t", mcs = "s0"):
		return "%s:%s:%s:%s" % (user, role, domain, mcs)

def verifyExecutable(driver, nodeName, appName):
	node = driver.getTarget(nodeName)
	resource = node.requireResource(name)
