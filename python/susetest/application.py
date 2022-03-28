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

	def reload(self):
		return self.serviceManager.reload(self.serviceResource)

	def restart(self):
		return self.serviceManager.restart(self.serviceResource)

class ManagedContainer:
	def __init__(self, target):
		self.target = target
		self.containerManager = target.containerManager

	def reload(self):
		return self.restart()

	def restart(self):
		targetSpec = self.containerManager.restart()
		assert(targetSpec)
		self.target.reconnect(targetSpec)
		twopence.info(f"Reconnected to SUT at {targetSpec}")

		# FIXME: we may want to perform a NO-OP call to the SUT just to be sure.
		return True

class Application:
	id = None

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

		if self.target.serviceManager and self.service_name:
			resource = self.target.requireService(self.service_name)
			if resource is None:
				raise ValueError(f"Application {self.id} specifies unknown service {self.service_name}")

			self.manager = ManagedService(self.target.serviceManager, resource)
		elif self.target.containerManager:
			self.manager = ManagedContainer(self.target)
		else:
			raise ValueError(f"Application {self.id}: no idea how we can manage applications running on {target.name}")

	def reload(self):
		if self.manager is None:
			self.target.logError(f"don't know how to reload application {self.id}")

		return self.manager.reload()

	def restart(self):
		if self.manager is None:
			self.target.logError(f"don't know how to restart application {self.id}")

		return self.manager.restart()
