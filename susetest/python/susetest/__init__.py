##################################################################
#
# Python classes for susetest
#
# Copyright (C) 2014-2021 SUSE Linux GmbH
#
##################################################################

import suselog
import twopence
import time
import re
import sys
import os

from .target import Target
from .config import Config

# This class is needed for break a whole testsuite, exit without run all tests. Wanted in some scenarios.
# Otherwise we can use susetest.finish(journal) to continue after  failed tests, 
class SlenkinsError(Exception):
	def __init__(self, code):
		self.code = code

	def __str__(self):
		return repr(self.code)

# Same for basiliqa
class BasiliqaError(Exception):
	def __init__(self, code):
		self.code = code

	def __str__(self):
		return repr(self.code)

# finish the junit report.
def finish(journal):
	journal.writeReport()
	if (journal.num_failed() + journal.num_errors()):
			sys.exit(1)
	sys.exit(0)
