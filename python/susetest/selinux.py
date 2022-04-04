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
from .resources import MessageFilter, ExecutableResource, FileResource, PackageResource, SubsystemResource, ServiceResource
from .feature import Feature
import susetest
import twopence
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
			self.permissive = None
			self.src = None

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

	selinux_socket_classes = ('socket', 'tcp_socket', 'udp_socket', 'rawip_socket', 'netlink_selinux_socket', 'unix_stream_socket', 'unix_dgram_socket',)
	selinux_file_classes = ('file', 'dir', 'fd', 'lnk_file', 'chr_file', 'blk_file', 'sock_file', 'fifo_file',)
	selinux_ipc_classes = ('sem', 'msg', 'msgq', 'shm', 'ipc',)
	selinx_known_classes = selinux_socket_classes + selinux_file_classes + selinux_ipc_classes + (
			'process', 'security', 'capability', 'filesystem',
		)

	def _match(self, m, target):
		violation = self.parseViolation(m.message)

		if violation and violation.tclass not in self.selinx_known_classes:
			target.logInfo("parsed unknown SELinux violation tclass=%s (%s)" % (
					violation.tclass, dir(violation)))
			violation = None

		if violation is None:
			target.logInfo("SELinux policy violation (unable to parse)")
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
				target.logInfo("SELinux policy violation")
			target.logInfo("  by %s (pid=%s; context=%s; permissive=%s)" % (
						violation.comm, violation.pid, violation.scontext, violation.permissive))

		# ioctls will also have ioctlcmd=0xNNNN
		if violation.tclass in self.selinux_file_classes:
			target.logInfo("    %s access to %s %s (dev=%s; ino=%s; context=%s)" % (
						violation.op,
						violation.tclass,
						violation.path or violation.name,
						violation.dev,
						violation.ino,
						violation.tcontext))
		elif violation.tclass in self.selinux_socket_classes:
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
	if violation.comm == "twopence_test_s" and violation.permissive == "1":
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
		self._filters = []

		self.verifiedResources = set()

	# Acquire the journal monitoring resource, and install a
	# message filter that checks for SELinux related kernel messages
	def activate(self, driver, node):
		resource = node.requireEvents("audit", defer = True)

		filter = SELinuxMessageFilter()
		filter.addCheck(pamTally2ConsideredHarmless)
		filter.addCheck(twopenceConsideredHarmless)
		self._filters.append(filter)

		resource.addFilter(filter)
		susetest.say("%s: installed SELinux filter" % resource)

		selinuxPolicy = driver.getParameter('selinux-policy')
		if not selinuxPolicy:
			selinuxPolicy = self.policy

		selinuxUser = driver.getParameter('selinux-user')
		if not selinuxUser:
			selinuxUser = driver.getParameter('selinux-testuser')
			if selinuxUser:
				twopence.warning("Your configuration uses obsolete parameter \"selinux-testuser\". Please use selinux-user instead")
				driver.setParameter('selinux-user', selinuxUser)

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

		if node.run(f"grep -q '^{linuxUser}:{selinuxUser}:' /etc/selinux/{selinuxPolicy}/seusers", quiet = True):
			node.logInfo(f"User {linuxUser} already mapped to SELinux user {selinuxUser}")
			return True

		node.logInfo("Updating user %s to use SELinux user/role %s" % (linuxUser, selinuxUser))
		semanage = node.optionalExecutable("semanage")
		if semanage is None:
			node.logInfo("semanage not found, doing it manually")
			return
			self.updateSEUserManually(node, linuxUser, selinuxPolicy, selinuxUser)

		st = semanage.run(f"login --add -s {selinuxUser} {linuxUser}")
		if not st:
			node.logError(f"Unable to define {linuxUser} as SELinux user {selinuxUser}: {st.message}")
			return False

		return True

	def updateSEUserManually(self, node, linuxUser, selinuxPolicy, selinuxUser):
		path = "/etc/selinux/%s/seusers" % selinuxPolicy
		node.logInfo("Editing %s" % path)
		content = node.recvbuffer(path, user = 'root')
		if not content:
			node.logError(f"Unable to define {linuxUser} as SELinux user {selinuxUser}")
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

	def addMessageFilter(self, fn):
		for filter in self._filters:
			filter.addCheck(fn)

	def resourceVerifyPolicy(self, driver, node, resourceType, resourceName):
		if 'selinux' not in node.features:
			node.logInfo("Skipping SELinux test; you may want to label the test with @susetest.requires('selinux')")
			driver.skipTest()
			return

		res = node.acquireResourceTypeAndName(resourceType, resourceName, mandatory = False)
		if res is None:
			node.logInfo("Unable to find %s resource %s - skipping this test" % (resourceType, resourceName))
			driver.skipTest()
			return

		self.resourceVerifyPolicyImpl(driver, node, res)

	def resourceVerifyPolicyImpl(self, driver, node, res):
		# Avoid verifying the same resource twice
		# (which could happen with services, for instance)
		if res in self.verifiedResources:
			return
		self.verifiedResources.add(res)

		tested = False
		if isinstance(res, ExecutableResource):
			if not res.path:
				# When defining this test case via susetest.template(), this will automatically
				# ensure that we try to claim the resource during testsuite setup.
				node.logInfo("Skipping SELinux test for %s; resource not present on SUT" % res)
				return

			label = res.selinux_label_domain
			if label is None:
				# default label. Should be configurable on a per-policy basis.
				label = "bin_t";

			self.checkExecutableLabel(node, res, label)
			tested = True

			if res.selinux_process_domain:
				self.verifyExecutableProcessDomain(driver, node, res)
				tested = True
		elif isinstance(res, FileResource):
			if not res.path:
				# When defining this test case via susetest.template(), this will automatically
				# ensure that we try to claim the resource during testsuite setup.
				node.logInfo("Skipping SELinux test for %s; resource not present on SUT" % res)
				return

			label = res.selinux_label_domain
			if label is None:
				path = res.path
				if path.startswith("/etc"):
					label = "etc_t"
				elif path.startswith("/tmp"):
					label = "tmp_t"
				elif path.startswith("/var"):
					label = "var_t"
				elif path.startswith("/usr"):
					label = "usr_t"

			if label:
				self.checkFileLabel(node, res, label)
				tested = True
		elif isinstance(res, ServiceResource):
			self.verifyService(node, res)
			tested = True
		elif isinstance(res, SubsystemResource):
			susetest.say(f"\n### SELinux: verifying subsystem {res.name} ###")
			for package in res.packages:
				self.resourceVerifyPolicy(driver, node, "package", package)
				tested = True
		elif isinstance(res, PackageResource):
			susetest.say(f"\n*** SELinux: verifying package {res.name} ***")
			# First, verify services, then everything else
			ordered = []
			for desc in res.children:
				if desc.klass == ServiceResource:
					ordered.insert(0, desc)
				else:
					ordered.append(desc)

			for desc in ordered:
				childResource = node.acquireResourceTypeAndName(desc.klass.resource_type, desc.name, mandatory = True)
				self.resourceVerifyPolicyImpl(driver, node, childResource)
				tested = True

		if not tested:
			node.logError("SELinux: don't know how to verify resource %s (type %s)" % (
					res.name, res.__class__.__name__))

	def checkExecutableLabel(self, node, res, given_domain):
		expected = self.buildLabel(domain = given_domain)
		return self.checkLabel(node, res.path, expected)

	def checkFileLabel(self, node, res, given_domain):
		expected = self.buildLabel(domain = given_domain)
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

	def verifyExecutableProcessDomain(self, driver, node, res):
		if self.default_setype == 'unconfined_t':
			node.logInfo("Not checking executable's process context for unconfined user")
			return True

		node.logInfo(f"Checking executable's process context (expecting {res.selinux_process_domain})")
		if res.selinux_test_service:
			return self.verifyExecutableProcessDomainService(driver, node, res)
		else:
			return self.verifyExecutableProcessDomainCommand(driver, node, res)

	def verifyExecutableProcessDomainService(self, driver, node, res):
		node.logInfo("  to verify the context, we need to inspect service %s" % res.selinux_test_service)
		service = node.requireService(res.selinux_test_service)
		if not service:
			node.logError("Unable to find/activate service %s" % res.selinux_test_service)
			return None

		# Do not check service again
		self.verifiedResources.add(service)

		return self.verifyService(node, service, res)

	def verifyService(self, node, service, executable = None):
		pid = service.pid
		if not pid:
			node.logError("Unable to get pid for service %s" % service.name)
			return None

		print(f"service {service.name} uses executable {service.executable}")
		if executable is None:
			if service.executable is None:
				node.logError(f"Service {service.name} does not specify an executable; cannot test SELinux process label")
				return None

			executable = node.requireExecutable(service.executable)
			if executable is None:
				return None

			# Do not check executable again
			self.verifiedResources.add(executable)

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
					type = executable.selinux_process_domain)
		if expected:
			node.logFailure("Service %s is running with wrong SELinux context" % service.name);
			node.logInfo("  expected %s" % expected)
			node.logInfo("  actual context %s" % process_ctx)
			return False

		node.logInfo("good, service is running with expected SELinux context %s" % process_ctx);
		return True

	def verifyExecutableProcessDomainCommand(self, driver, node, res):
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
			cmd = susetest.Command(cmdline, timeout = 10, user = user.login, background = True, tty = True)

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

		# Check if the resource says that the command is expected to fail for our
		# seuser. That's a roundabout way of saying that SELinux will not allow the
		# transition to the expected process domain.
		prediction = res.predictOutcome(driver, {})
		expected_type = res.selinux_process_domain
		if prediction and prediction.status != 'success':
			expected_type = None

		expected = self.checkContext(process_ctx, type = expected_type)
		if expected:
			node.logFailure(f"Command \"{cmdline}\" is running with wrong SELinux context");
			node.logInfo(f"  expected {expected}")
			node.logInfo(f"  actual context {process_ctx}")
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
