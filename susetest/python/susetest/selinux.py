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
from susetest.resource import MessageFilter

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

	def match(self, m, target):
		if m.transport != "kernel" or not m.message.startswith("audit:") or " avc: " not in  m.message:
			return

		if not self._match(m, target):
			self.previous = None

	def _match(self, m, target):
		violation = self.parseViolation(m.message)

		if violation and violation.tclass not in ('dir', 'file', 'udp_socket'):
			target.logInfo("parsed unknown SELinux violation tclass=%s (%s)" % (
					violation.tclass, dir(violation)))
			violation = None

		if violation is None:
			target.logFailure("SELinux policy violation")
			target.logInfo(m.message)
			return

		if not self.previous or self.previous.pid != violation.pid:
			target.logFailure("SELinux policy violation")
			target.logInfo("SELinux policy violation by %s (pid=%s; context=%s)" % (
						violation.comm, violation.pid, violation.scontext))

		if violation.tclass in ('dir', 'file'):
			target.logInfo("    %s access to %s %s (dev=%s; ino=%s; context=%s)" % (
						violation.op,
						violation.tclass,
						violation.path or violation.name,
						violation.dev,
						violation.ino,
						violation.tcontext))
		elif violation.tclass in ('udp_socket', ):
			target.logInfo("    %s access to %s %s (context=%s)" % (
						violation.op,
						violation.tclass,
						violation.src,
						violation.tcontext))

		self.previous = violation
		return True

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

# Acquire the journal monitoring resource, and install a
# message filter that checks for SELinux related kernel messages
def enableFeature(driver, node):
	for resource in driver._requireResourceForNodes("journal", [node]):
		resource.addFilter(SELinuxMessageFilter())
