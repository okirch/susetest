##################################################################
#
# Base class for "Applications".
# An application is basically a python wrapper around a Linux
# service, intended to work with regular installed systems,
# as well as with containerized applications
#
##################################################################

import importlib
import susetest
import twopence
import sys

def isApplication(thing):
	# thing must be a class, and then we can check issubclass
	return type(thing) == type(Application) and issubclass(thing, Application)

# This allows to manage an application on a SUT that has systemd or some
# other type of service manager
class ManagedService:
	def __init__(self, serviceManager, serviceResource):
		self.serviceManager = serviceManager
		self.serviceResource = serviceResource

	def running(self):
		return self.serviceManager.running(self.serviceResource)

	def start(self):
		return self.serviceManager.start(self.serviceResource)

	def reload(self):
		return self.serviceManager.reload(self.serviceResource)

	def restart(self):
		return self.serviceManager.restart(self.serviceResource)

class ManagedContainer:
	def __init__(self, target, topologyConfig):
		self.target = target
		self.containerManager = target.containerManager

		self.topologyConfig = topologyConfig

	def running(self):
		# The container is running
		return True

	def start(self):
		# The container is running, so the service it provides is running, too. QED.
		pass

	def reload(self):
		return self.restart()

	def restart(self):
		targetSpec = self.containerManager.restart()
		assert(targetSpec)
		self.target.reconnect(targetSpec)
		self.target.logInfo(f"Reconnected to SUT at {targetSpec}")

		# FIXME: we may want to perform a NO-OP call to the SUT just to be sure.

		if self.topologyConfig:
			self.topologyConfig.save()
			self.target.logInfo(f"Updated {self.topologyConfig.path} to reflect container restart")

		return True

class Application:
	id = None

	def __str__(self):
		return f"application {self.id}"

	@staticmethod
	def find(name, moduleName = None):
		applicationClass = None

		lib_dir = twopence.paths.test_lib_dir

		saved_path = sys.path
		if lib_dir not in sys.path:
			sys.path = sys.path + [lib_dir]

		if moduleName is None:
			moduleName = f"farthings.application.{name}"

		mod = importlib.import_module(moduleName)
		for objName, o in mod.__dict__.items():
			if isApplication(o) and o.id == name:
				applicationClass = o
				break

		sys.path = saved_path
		return applicationClass

	def __init__(self, driver, target):
		assert(self.__class__.id)
		self.target = target

		self.manager = None

		if self.service_name is not None:
			if self.target.serviceManager:
				resource = self.target.requireService(self.service_name)
				if resource is None:
					raise ValueError(f"Application {self.id} specifies unknown service {self.service_name}")

				self.manager = ManagedService(self.target.serviceManager, resource)
			elif self.target.containerManager:
				# Pass a reference to the (parsed) status.conf. When we restart the
				# container, we also have to restart the test server, and update the
				# target setting in status.conf
				self.manager = ManagedContainer(self.target, driver.topologyStatus)
			else:
				raise ValueError(f"Application {self.id}: no idea how we can manage applications running on {target.name}")

	def start(self):
		if self.manager is None:
			self.target.logError(f"don't know how to start application {self.id}")

		return self.manager.start()

	def reload(self):
		if self.manager is None:
			self.target.logError(f"don't know how to reload application {self.id}")

		return self.manager.reload()

	def restart(self):
		if self.manager is None:
			self.target.logError(f"don't know how to restart application {self.id}")

		return self.manager.restart()

	def requireExecutable(self, name):
		res = self.target.requireExecutable(name)
		if res is None:
			raise ValueError(f"Cannot find executable {name}")

		return res

	def requireFile(self, name):
		res = self.target.requireFile(name)
		if res is None:
			raise ValueError(f"Cannot find file {name}")

		return res

	def requireUser(self, name):
		res = self.target.requireUser(name)
		if res is None:
			raise ValueError(f"Cannot find user {name}")

		if res.uid is None:
			raise ValueError(f"User {name} does not seem to exist?!")

		return res
