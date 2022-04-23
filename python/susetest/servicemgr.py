##################################################################
#
# Service Managers
#
# Copyright (C) 2022 SUSE Linux GmbH
#
# These classes help manage service resources.
# They provide an abstraction layer from the actual OS implementation
# of how to manage service.
#
# Nowadays, virtually every OS uses systemd, which makes this a
# kind of useless exercise.
#
##################################################################

import susetest

from .feature import Feature

class ServiceManager(Feature):
	pass

class ServiceManagerSystemd(ServiceManager):
	name = "systemd"
	systemctl_path = "/usr/bin/systemctl"

	def start(self, service):
		return self.systemctlForAllUnits("start", service)

	def restart(self, service):
		return self.systemctlForAllUnits("restart", service)

	def reload(self, service):
		return self.systemctlForAllUnits("reload", service)

	def stop(self, service):
		return self.systemctlForAllUnits("stop", service)

	def running(self, service):
		return self.systemctlForAllUnits("status", service)

	def checkUnitStatus(self, service):
		if not service.systemd_activate:
			return None

		loaded = True
		active = True
		running = True

		node = service.target
		for unit in service.systemd_activate:
			st = node.run(f"systemctl show --property UnitFileState,ActiveState,SubState,LoadState {unit}", quiet = True)
			if not st:
				node.logInfo(f"systemctl show {unit} failed: {st.message}")
				return None

			for line in st.stdoutString.split('\n'):
				if "=" not in line:
					continue
				(key, value) = line.split("=", maxsplit = 1)
				if key == "UnitFileState" and not value:
					node.logInfo(f"Unit file {unit} is missing")
					return None
				elif key == "LoadState" and value != "loaded":
					loaded = False
				elif key == "ActiveState" and value != "active":
					active = False
				elif key == "SubState" and value != "running":
					running = False

		if running:
			return "running"
		if active:
			return "enabled"
		if loaded:
			return "disabled"
		return "need-reload"

	# Called via PackageBackedResource.acquire -> ServiceResource.detect
	def tryToActivate(self, service):
		node = service.target

		state = self.checkUnitStatus(service)

		node.logInfo(f"Service {service.name} state={state}")
		if state == "need-reload":
			self.systemctl(node, "reload-daemon", "")
			state = self.checkUnitStatus(service)

		if not state:
			# Units missing
			return False

		if state == "running":
			return True

		if state != "enabled":
			for unit in service.systemd_activate:
				node.logInfo(f"enabling service {unit}")
				if not self.systemctl(node, "enable", unit):
					return False

		for unit in service.systemd_activate:
			node.logInfo(f"activating service {unit}")
			if not self.systemctl(node, "start", unit):
				return False

		return True

	def tryToDeactivate(self, service):
		node = service.target
		for unit in service.systemd_activate:
			node.logInfo(f"deactivating service {unit}")
			if not self.systemctl(node, "stop", unit) or not self.systemctl(node, "disable", unit):
				return False

		return True

	def systemctlForAllUnits(self, verb, service):
		node = service.target
		for unit in service.systemd_activate:
			if not self.systemctl(node, verb, unit):
				return False

		return True

	def systemctl(self, node, verb, unit):
		cmd = "%s %s %s" % (self.systemctl_path, verb, unit)
		return node.runOrFail(cmd)

	def getServicePID(self, service):
		if not service.is_active:
			return None

		status = self.systemctl(service.target, "show --property MainPID", service.systemd_unit)

		if not(status) or len(status.stdout) == 0:
			return None

		for line in status.stdoutString.split("\n"):
			if line.startswith("MainPID="):
				pid = line[8:]
				if pid.isdecimal():
					return pid

		return None

	def getServiceUser(self, service):
		pid = service.pid

		if pid is None:
			return None

		node = service.target

		status = node.run("/bin/ps hup " + pid);
		if not(status) or len(status.stdout) == 0:
			node.logInfo("ps did not find %s process" % service.name);
			return None

		# the first column of the ps output is the user name
		return status.stdoutString.split(None, 1)[0]

