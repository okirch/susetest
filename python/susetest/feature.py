##################################################################
#
# Generic feature handling
#
# A "feature" describes a property of an OS image, or
# an aspect of testing.
#
# For example, the 'selinux' feature indicates that the
# SUT was provisioned with SELinux support enabled.
# Another example (not yet implemented) would be 'fips'
# which indicates that the SUT is running with fips enabled.
#
# In order to handle features, define a subclass of Feature
# and implement the activate() method.
#
# In addition, feature implementations can handle domain specific
# parameters. For example, the selinux feature supports a
# paramter called selinux-user, which can be used to change
# how the default test user is mapped to a SELinux user/role.
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
import susetest

class Feature(object):
	def __init__(self):
		pass

	@staticmethod
	def isSupportedFeature(name):
		return name in ('selinux', 'systemd', 'dnf', 'zypper')

	@staticmethod
	def createFeature(name):
		if name == 'selinux':
			from .selinux import SELinux

			return SELinux()

		if name == 'systemd':
			from .servicemgr import ServiceManagerSystemd

			return ServiceManagerSystemd()

		if name == 'zypper':
			from .packagemgr import PackageManagerZypper

			return PackageManagerZypper()

		if name == 'dnf':
			from .packagemgr import PackageManagerDNF

			return PackageManagerDNF()

		if name in ('container', 'twopence', 'twopence-tcp',):
			return DummyFeature(name)

		# raise ValueError("Feature %s not yet implemented" % name)
		return UnsupportedFeature(name)

	@property
	def requiresActivation(self):
		return True

	def activate(self, driver, node):
		raise NotImplementedError()

class UnsupportedFeature(Feature):
	def __init__(self, name):
		self.name = name

	def activate(self, driver, node):
		susetest.say(f"Running node {node.name} with unsupported feature {self.name}")

class DummyFeature(Feature):
	def __init__(self, name):
		self.name = name

	@property
	def requiresActivation(self):
		return False
