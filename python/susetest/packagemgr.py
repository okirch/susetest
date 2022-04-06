##################################################################
#
# Package Managers
#
# Copyright (C) 2022 SUSE Linux GmbH
#
# These classes help manage package resources.
# They provide an abstraction layer from the actual OS implementation,
# such as dnf, zypper etc.
#
##################################################################

import susetest

from .feature import Feature

class PackageManager(Feature):
	def __init__(self):
		pass

	def activate(self, driver, node):
		node.setPackageManager(self)

	def run(self, node, cmd, **kwargs):
		st = node.run(cmd, user = "root", **kwargs)
		if not st:
			node.logInfo(f"{cmd} failed: {st.message}")
		return bool(st)

class PackageManagerRPM(PackageManager):
	def __init__(self):
		pass

	def checkPackage(self, node, packageName):
		return self.run(node, f"rpm -q {packageName}")

class PackageManagerZypper(PackageManagerRPM):
	name = "zypper"

	def installPackage(self, node, packageName):
		return self.run(node, f"zypper install -y {packageName}", timeout = 120)

class PackageManagerDNF(PackageManagerRPM):
	name = "dnf"

	def installPackage(self, node, packageName):
		return self.run(node, f"dnf -y install {packageName}", timeout = 120)
