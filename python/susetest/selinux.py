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
from .resources import MessageFilter, ExecutableResource, FileResource
from .feature import Feature
import susetest
import time

# Typical SELinux message:
# audit: type=1400 audit(1637744082.879:4): \
#	avc:  denied  { write } for  \
#	pid=4429 comm="pam_tally2" name="log" dev="vda3" ino=1449455 \
#	scontext=unconfined_u:unconfined_r:useradd_t:s0 \
#	tcontext=system_u:object_r:var_log_t:s0 \
#	tclass=dir permissive=1
# or, when coming from audispd:
# audit(1637744082.879:4): \
#	avc:  denied  { write } for  \
#	... etc
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

		# Two violations are considered to originate from the same process iff the following
		# are identical
		#	process id
		#	comm (we want to catch exec() calls)
		#	scontext (we want to catch dynamic context transitions)
		def sameProcess(self, other):
			if other is None:
				return False
			return self.pid == other.pid and self.comm == other.comm and self.scontext == other.scontext

	def __init__(self):
		self.previous = None
		self._checks = []

	def match(self, m, target):
		if m.transport == "audit":
			pass
		elif m.transport != "kernel" or not m.message.startswith("audit:") or " avc: " not in  m.message:
			return

		if not self._match(m, target):
			self.previous = None

	def _match(self, m, target):
		violation = self.parseViolation(m.message)

		if violation and violation.tclass not in ('process', 'dir', 'file', 'chr_file', 'udp_socket', 'tcp_socket', 'netlink_selinux_socket'):
			target.logInfo("parsed unknown SELinux violation tclass=%s (%s)" % (
					violation.tclass, dir(violation)))
			violation = None

		if violation is None:
			target.logFailure("SELinux policy violation")
			target.logInfo(m.message)
			return

		if violation.sameProcess(self.previous):
			# This is the same process triggering another policy violation
			pass
		else:
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

		if words[0] == "audit:" and words[1].startswith("type="):
			del words[:2]

		if not words.pop(0).startswith("audit(") or \
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

class SELinux(Feature):
	name = 'selinux'

	def __init__(self):
		super().__init__()
		self.policy = 'targeted'
		self.default_seuser = 'unconfined_u'
		self.default_serole = 'unconfined_r'
		self.default_setype = 'unconfined_t'

	# Acquire the journal monitoring resource, and install a
	# message filter that checks for SELinux related kernel messages
	def enableFeature(self, driver, node):
		resource = node.requireEvents("audit", defer = True)

		filter = SELinuxMessageFilter()
		filter.addCheck(pamTally2ConsideredHarmless)
		filter.addCheck(twopenceConsideredHarmless)

		resource.addFilter(filter)
		susetest.say("%s: installed SELinux filter" % resource)

		selinuxPolicy = driver.getParameter('selinux-policy')
		if not selinuxPolicy:
			selinuxPolicy = self.policy

		selinuxUser = driver.getParameter('selinux-user')
		if not selinuxUser:
			selinuxUser = driver.getParameter('selinux-testuser')

		if selinuxUser:
			self.updateSEUser(node, selinuxPolicy, selinuxUser)

			# setting the role is a bit of a hack.
			# The default role for a user is policy dependent,
			# and it's just a convention of the current policies
			# that the default role for foobar_u is foobar_r
			self.default_seuser = selinuxUser
			self.default_serole = selinuxUser.replace('_u', '_r')
			self.default_setype = selinuxUser.replace('_u', '_t')

		driver.performDeferredResourceChanges()

	def updateSEUser(self, node, selinuxPolicy, selinuxUser):
		linuxUser = node.test_user

		if linuxUser is None:
			user = node.requireUser("test-user")
			if not user:
				raise ValueError("Cannot determine default Linux user")
			linuxUser = user.login

		node.logInfo("Updating user %s to use SELinux user/role %s" % (linuxUser, selinuxUser))

		path = "/etc/selinux/%s/seusers" % selinuxPolicy
		node.logInfo("Editing %s" % path)
		content = node.recvbuffer(path, user = 'root')
		if not content:
			node.logError("Unable to define %s as SELinux user %s" % (linuxUser, selinuxUser))
			return False

		replace = "%s:%s:s0-s0:c0.c1023" % (linuxUser, selinuxUser)
		result = []

		for line in content.decode('utf-8').split('\n'):
			line = line.strip()
			if line == replace:
				node.logInfo("seusers entry for %s already present" % linuxUser)
				return True

			if line.startswith(linuxUser + ":"):
				line = replace
				replace = None
			result.append(line)

		if replace:
			result.append(replace)

		content = ('\n'.join(result) + '\n').encode('utf-8')
		st = node.sendbuffer(path, content, user = 'root')
		if not st:
			node.logError("Unable to overwrite %s: %s" % (path, st.message))
			return False

		return True

	def resourceVerifyPolicy(self, node, resourceType, resourceName):
		if 'selinux' not in node.features:
			node.logInfo("Skipping SELinux test; you may want to label the test with @susetest.requires('selinux')")
			driver.skipTest()
			return

		res = node.acquireResourceTypeAndName(resourceType, resourceName, mandatory = False)
		if res is None:
			node.logInfo("Unable to find %s resource %s - skipping this test" % (resourceType, resourceName))
			driver.skipTest()
			return

		tested = False
		if isinstance(res, ExecutableResource):
			if not res.path:
				# When defining this test case via susetest.template(), this will automatically
				# ensure that we try to claim the resource during testsuite setup.
				node.logInfo("Skipping SELinux test for %s; resource not present on SUT" % res)
				return

			if res.selinux_label_domain:
				self.checkExecutableLabel(node, res)
				tested = True

			if res.selinux_process_domain:
				self.verifyExecutableProcessDomain(node, res)
				tested = True
		elif isinstance(res, FileResource):
			if not res.path:
				# When defining this test case via susetest.template(), this will automatically
				# ensure that we try to claim the resource during testsuite setup.
				node.logInfo("Skipping SELinux test for %s; resource not present on SUT" % res)
				return

			if res.selinux_label_domain:
				self.checkFileLabel(node, res)
				tested = True

		if not tested:
			node.logError("SELinux: don't know how to verify resource %s (type %s)" % (
					res.name, res.__class__.__name__))

	def checkExecutableLabel(self, node, res):
		expected = self.buildLabel(domain = res.selinux_label_domain)
		return self.checkLabel(node, res.path, expected)

	def checkFileLabel(self, node, res):
		expected = self.buildLabel(domain = res.selinux_label_domain)
		return self.checkLabel(node, res.path, expected)

	def checkLabel(self, node, path, expected_label):
		print("Checking label of %s (expecting %s)" % (path, expected_label))
		if not path:
			node.logError("Unable to get path of resource");
			return

		print("Resource path is %s" % path)
		status = node.runOrFail("stat -Lc %%C %s" % path, stdout = bytearray(), quiet = True)
		if not status:
			return

		label = status.stdoutString.strip()
		if label != expected_label:
			node.logFailure("Unexpected SELinux label on %s" % path)
			node.logInfo("  expected label %s" % expected_label)
			node.logInfo("  actual label   %s" % label)
		else:
			node.logInfo("good, %s has expected SELinux label %s" % (path, expected_label));

	def verifyExecutableProcessDomain(self, node, res):
		print("Checking executable's process context (expecting %s)" % res.selinux_process_domain)

		if res.selinux_test_service:
			return self.verifyExecutableProcessDomainService(node, res)
		else:
			return self.verifyExecutableProcessDomainCommand(node, res)

	def verifyExecutableProcessDomainService(self, node, res):
		node.logInfo("  to verify the context, we need to inspect service %s" % res.selinux_test_service)
		service = node.requireService(res.selinux_test_service)
		if not service:
			node.logError("Unable to find/activate service %s" % res.selinux_test_service)
			return None

		pid = service.pid
		if not pid:
			node.logError("Unable to get pid for service %s" % res.selinux_test_service)
			return None

		content = node.recvbuffer("/proc/%s/attr/current" % pid, user = "root")

		# For some odd reason, the kernel will return a NUL terminated string
		# when reading from /proc/PID/attr/current
		content = content.strip(b'\0')

		if not content:
			node.logError("Unable to get SELinux process domain for PID %s" % pid)
			return None

		process_ctx = content.decode('utf-8')
		process_ctx = ":".join(process_ctx.split(':')[:3])

		expected = self.checkContext(process_ctx,
					user = 'system_u',
					role = 'system_r',
					type = res.selinux_process_domain)
		if expected:
			node.logFailure("Service %s is running with wrong SELinux context" % service.name);
			node.logInfo("  expected %s" % expected)
			node.logInfo("  actual context %s" % process_ctx)
			return False

		node.logInfo("good, service is running with expected SELinux context %s" % process_ctx);
		return True

	def verifyExecutableProcessDomainCommand(self, node, res):
		user = node.getResource("user", "test-user")
		if not user.uid:
			node.logError("user %s does not seem to exist" % user.login)
			return

		cmdline = res.selinux_test_command

		if not (res.interactive or res.selinux_test_interactive):
			# Run a NOP invocation of the command (could also be sth like "cmd --help")
			# and tell twopence to collect the exit status when reaping the child process.
			# This information will be available through Status.process to us.
			if not cmdline:
				cmdline = "%s --bogus-option-should-error >/dev/null 2>&1" % res.path
			cmd = susetest.Command(cmdline, user = user.login, exitInfo = True, quiet = True)
			st = node.run(cmd)

			process_ctx = st.process.selinux_context
			if process_ctx is None:
				node.logFailure("unable to find process context for exited command: %s" % cmdline)
				return
		else:
			if not cmdline:
				cmdline = res.path
			cmd = susetest.Command(cmdline, timeout = 10, user = user.login, background = True)

			proc = node.chat(cmd)
			if not proc:
				node.logFailure("failed to start command \"%s\"" % cmdstring)
				return

			# Insert a minor delay to allow the the server to exec
			# the application, and have it transition to the expected context
			time.sleep(0.5)

			process_ctx = proc.selinux_context

			if process_ctx is None:
				node.logFailure("unable to find process context for exited command: %s" % cmdline)
				return

			proc.kill("KILL")
			proc.wait()

		expected = self.checkContext(process_ctx, type = res.selinux_process_domain)
		if expected:
			node.logFailure("command is running with wrong SELinux context");
			node.logInfo("  expected %s" % expected)
			node.logInfo("  actual context %s" % process_ctx)
			return False

		node.logInfo("good, command is running with expected SELinux context %s" % process_ctx);
		return True

	def buildLabel(self, user = "system_u", role = "object_r", domain = "bin_t", sensitivity = "s0"):
		return "%s:%s:%s:%s" % (user, role, domain, sensitivity)

	def buildContext(self, user = None, role = None, type = None, sensitivity = "s0"):
		if user is None:
			user = self.default_seuser
		if role is None:
			role = self.default_serole
		if type is None:
			type = self.default_setype

		return "%s:%s:%s:%s" % (user, role, type, sensitivity)

	# Returns the expected context if there's a conflict, None otherwise
	def checkContext(self, context, user = None, role = None, type = None, sensitivity = None, categories = None):
		if user is None:
			user = self.default_seuser
		if role is None:
			role = self.default_serole
		if type is None:
			type = self.default_setype

		actual = context.split(":")
		expect = [user, role, type]
		for a, b in zip(expect, actual):
			if a != b:
				return ":".join(expect)

		return None