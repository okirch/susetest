##################################################################
#
# Container Managers
#
# Copyright (C) 2022 SUSE Linux GmbH
#
# These classes help manage application containers
#
##################################################################

import susetest
import suselog

from .feature import Feature

class ContainerManager:
	def __init__(self):
		pass

	@staticmethod
	def create(config):
		from twopence.provision import Backend

		backendName = config.get_value('backend')
		backend = Backend.create(backendName)

		return backend.createApplicationManager(config)
