#!/usr/bin/python3
##################################################################
#
# Run a test, including the provisioning and teardown of all nodes
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################

import twopence
import argparse
import os
import sys
import curly
import readline
import atexit
from .logger import LogParser
from .results import ResultsVector, ResultsMatrix
from twopence import logger, info, debug, error

class AbortedTestcase(Exception):
	pass

class ContinueTestcase(Exception):
	pass

class FinishTestcase(Exception):
	pass

class InteractiveCommand(object):
	def __init__(self, name, description, func):
		self.name = name
		self.description = description.strip()
		self.func = func

	def getCompletion(self, tokens, nth):
		return None

class ScheduleControlCommandBase(InteractiveCommand):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def perform(self, testcase, *args):
		changed = testcase.controlTests(self.name, args)
		if changed:
			print()
			print("Changes in test schedule:")
			for s in changed:
				print(s)

	def getCompletion(self, testcase, tokens, nth):
		name = tokens[-1]

		completions = []
		if '.' not in name:
			schedule = testcase.scheduledGroups
			# remove the trailing * from the group name
			schedule = map(lambda s: s.rstrip('*'), schedule)
		else:
			if name.endswith('.'):
				completions.append(name + '*')
			schedule = testcase.scheduledTests

		for possibleCompletion in schedule:
			if possibleCompletion.startswith(name):
				completions.append(possibleCompletion)

		if nth < len(completions):
			return completions[nth]
		return None

class Interaction(object):
	def __init__(self, testcase, message):
		self.testcase = testcase
		self.message = message
		self.commands = {}

		for name in dir(self):
			attr = getattr(self, name, None)
			if not attr:
				continue

			if not callable(attr):
				continue

			# If it's a subclass of Command, instantiate it and
			# add it right away. This is the only way we can
			# do per-command completion of arguments
			if type(attr) == type(self.__class__) and \
			   issubclass(attr, InteractiveCommand):
				cmd = attr()
				self.commands[cmd.name] = cmd
				continue

			doc = attr.__doc__
			try:
				(name, description) = doc.split(":", maxsplit = 1)
			except:
				continue
			self.addCommand(name, description, attr)

	def addCommand(self, name, description, func):
		cmd = InteractiveCommand(name, description, func)
		self.commands[name] = cmd

	def getCommand(self, name):
		return self.commands.get(name)

	def getCompletion(self, text, nth = 0):
		if type(nth) != int:
			return None

		index = 0
		for cmd in self.commands.values():
			if cmd.name.startswith(text):
				if index >= nth:
					return cmd
				index += 1

		return None

	def cont(self, testcase, *args):
		'''continue: proceed to next step'''
		raise ContinueTestcase()

	def finish(self, testcase, *args):
		'''finish: finish the test case non-interactively'''
		raise FinishTestcase()

	def help(self, testcase, *args):
		'''help: display help message'''

		for (name, cmd) in sorted(self.commands.items()):
			print("%-20s %s" % (name, cmd.description))

	def abort(self, testcase, *args):
		'''abort: abort this test case'''
		raise AbortedTestcase()

	def schedule(self, testcase, *args):
		'''schedule: display the test schedule'''
		if not testcase.schedule:
			print("This test script does not seem to define any tests")
			return

		for s in testcase.schedule:
			print(s)

	class OnlyCommand(ScheduleControlCommandBase):
		def __init__(self):
			super().__init__("only", "execute just the matching test cases, none other", self.perform)

	class SkipCommand(ScheduleControlCommandBase):
		def __init__(self):
			super().__init__("skip", "skip matching test cases", self.perform)

class InteractionPreProvisioning(Interaction):
	pass

class InteractionPostProvisioning(Interaction):
	def status(self, testcase, *args):
		'''status: display the status of provisioned cluster'''
		testcase.displayClusterStatus()

	class SSHCommand(InteractiveCommand):
		def __init__(self):
			super().__init__("ssh", "connect to a node", self.perform)

		def getCompletion(self, testcase, tokens, nth):
			if len(tokens) != 1:
				return None

			name = tokens[0]

			if nth == 0:
				for match in testcase._nodes:
					if match.startswith(name):
						return match

			return None

		def perform(self, testcase, *args):
			'''ssh: connect to a node'''
			if len(args) != 1:
				print("usage: ssh NODE")
				return

			name = args[0]
			print("Trying to connect to node %s" % name)

			# Using nsenter messes with the tty in a way that python's
			# input() function has a hard time recovering from.
			# Things end in tears and a nasty SIGTTOU.
			# So instead, we use a pty to insulate our tty from
			# whatever happens in nsenter.
			testcase.runProvisioner("login", name, usePty = True)

class InteractionPostTestRun(InteractionPostProvisioning):
	def rerun(self, testcase, *args):
		'''rerun: re-run the test script'''
		testcase.runScript(rerun = True)


class Console:
	BANNER = '''
Welcome to the susetest shell. For an overview of commands, please enter 'help'.
Type 'continue' or Ctrl-D to exit interactive shell and proceed.
'''
	def __init__(self):
		self.histfile = os.path.join(os.path.expanduser("~"), ".twopence/history")

		try:
			readline.read_history_file(self.histfile)
			self.h_len = readline.get_current_history_length()
		except FileNotFoundError:
			open(self.histfile, 'wb').close()
			self.h_len = 0

		readline.parse_and_bind("tab: complete")
		readline.set_completer(self.complete)

		atexit.register(self.save)

		self.banner = False
		self.interactions = None

	def save(self):
		new_h_len = readline.get_current_history_length()
		readline.set_history_length(1000)
		readline.append_history_file(new_h_len - self.h_len, self.histfile)

	def interact(self, interaction):
		if not self.banner:
			print(self.BANNER)
			self.banner = True

		print(interaction.message)

		self.interactions = interaction
		while True:
			try:
				response = input("> ")
			except EOFError:
				print("<Ctrl-d>")
				break

			response = response.strip()
			w = response.split()
			if not w:
				continue

			name = w.pop(0)

			if name == 'continue':
				break

			cmd = interaction.getCommand(name)
			if not cmd:
				cmd = interaction.getCompletion(name)
			if not cmd:
				print("Unknown command `%s'" % name)
				continue

			# Invoke the command
			cmd.func(interaction.testcase, *w)
		self.interactions = None

	def complete(self, text, nth):
		if not self.interactions:
			return None

		linebuf = readline.get_line_buffer()
		tokens = linebuf.split()

		if not tokens:
			return None

		# We've actually completed a word, and we do not want to
		# do completion of the last word but the next argument (which is
		# empty so far).
		if linebuf.endswith(' '):
			tokens.append('')

		name = tokens.pop(0)
		if not tokens:
			cmd = self.interactions.getCompletion(name, nth)
		else:
			cmd = self.interactions.getCompletion(name)

		if cmd is None:
			return None

		if not tokens:
			return cmd.name

		testcase = self.interactions.testcase
		return cmd.getCompletion(testcase, tokens, nth)

class TestThing:
	def __init__(self, name):
		self.info = None
		self.name = name

	@property
	def description(self):
		return f"{self.type_string} {self.name}"

	def validateCompatibility(self, features):
		if not self.info:
			error(f"Cannot validate compatibility of {self.description}: no info object")
			return False

		if not self.info.validateFeatureCompatibility(features, msgfunc = info):
			info(f"Skipping incompatible {self.description}")
			return False

		return True

class Context:
	class Options:
		def __init__(self, args):
			self.backend = args.backend
			self.dryrun = args.dry_run
			self.debug = args.debug
			self.debug_schema = args.debug_schema
			self.quiet = args.quiet

			# default value None here means: let the backend decide
			self.update_images = self.evalTriStateOption(args, "--update-images", None)
			self.clobber = self.evalTriStateOption(args, "--clobber", True)

		def evalTriStateOption(self, args, name, defValue):
			name = name.lstrip("-").replace("-", "_")
			if getattr(args, name):
				return True
			if getattr(args, "no_" + name):
				return False
			return defValue

	@staticmethod
	def makeToplevel(args, roles):
		testrun = args.testrun
		workspace = args.workspace
		logspace = args.logspace

		if workspace is None:
			workspace = os.path.expanduser("~/susetest/work")
		if logspace is None:
			logspace = os.path.expanduser("~/susetest/logs")

		if testrun:
			workspace = os.path.join(workspace, testrun)
			logspace = os.path.join(logspace, testrun)

		options = Context.Options(args)

		return Context(testrun, workspace, logspace, roles, args.parameter, options)

	def __init__(self, testrun, workspace, logspace, roles, parameters, options, results = None):
		self.testrun = testrun
		self.workspace = workspace
		self.logspace = logspace
		self.options = options
		self.results = results
		self.roles = roles

		self.parameters = []
		if parameters:
			self.parameters += parameters

	def getPlatformFeatures(self, platform):
		import twopence.provision

		return twopence.provision.queryPlatformFeatures(platform) or set()

	def validateMatrix(self, matrix):
		# print(f"### CHECKING FEATURE COMPAT of {matrix.description} vs {self.platformFeatures}")
		for role in self.roles.values():
			if not matrix.validateCompatibility(role.resolution.features):
				return False

		return True

	def createSubContext(self, extra_path, extra_parameters = []):
		if self.results:
			assert(isinstance(self.results, ResultsMatrix))
			column_name = extra_path[-1]
			results = self.results.createColumn(column_name, extra_parameters)
		else:
			results = None

		return Context(self.testrun,
			workspace = os.path.join(self.workspace, *extra_path),
			logspace = os.path.join(self.logspace, *extra_path),
			roles = self.roles,
			parameters = self.parameters + extra_parameters,
			options = self.options,
			results = results)

	def mergeTestReport(self, testReport):
		if self.results is not None:
			for group in testReport.groups:
				for test in group.tests:
					self.results.add(test.id, test.status, test.description)

			self.results.save()

	def createWorkspaceFor(self, name):
		return self._makedir(os.path.join(self.workspace, name))

	def createLogspaceFor(self, name):
		return self._makedir(os.path.join(self.logspace, name))

	def createTestrunConfig(self):
		path = os.path.join(self.workspace, "testrun.conf")
		info("Creating %s" % path)

		config = curly.Config()
		tree = config.tree()

		tree.set_value("backend", self.options.backend)

		for role in self.roles.values():
			node = tree.add_child("role", role.name)

			if role.resolution:
				if role.resolution.isApplication:
					node.set_value("application", role.resolution.name)
				else:
					node.set_value("platform", role.resolution.name)

			if role.repositories:
				node.set_value("repositories", role.repositories)
			if role.provisionOptions:
				node.set_value("build", list(role.provisionOptions))

		if self.parameters:
			child = tree.add_child("parameters")
			for paramString in self.parameters:
				words = paramString.split('=', maxsplit = 1)
				if len(words) != 2:
					raise ValueError("argument to --parameter must be in the form name=value, not \"%s\"" % s)

				child.set_value(*words)

		config.save(path)

		info("Contents of %s:" % path)
		with open(path) as f:
			for l in f.readlines():
				info("    %s" % l.rstrip())

		return path

	def attachResults(self, results):
		results.attachToLogspace(self.logspace, clobber = self.options.clobber)
		self.results = results

		# This records our command line in the results.xml file
		# so that the HTML renderer can display it later.
		results.invocation = " ".join(sys.argv)

	def _makedir(self, path):
		if not os.path.isdir(path):
			os.makedirs(path)
		return path

class Testcase(TestThing):
	type_string = "test case"

	STAGE_LARVAL		= "larval"
	STAGE_INITIALIZED	= "initialized"
	STAGE_PROVISIONED	= "provisioned"
	STAGE_TEST_COMPLETE	= "complete"
	STAGE_DESTROYED		= "destroyed"

	def __init__(self, name, context):
		super().__init__(name)

		self.workspace = context.createWorkspaceFor(name)
		self.logspace = context.createLogspaceFor(name)
		self.options = context.options

		self.isCompatible = True

		self.testConfigPath = None
		self.testScriptPath = None
		self.testReportPath = None

		self.stage = self.STAGE_LARVAL
		self._nodes = []
		self._schedule = None

		self._control = None

	@property
	def is_larval(self):
		return self.stage == self.STAGE_LARVAL

	@property
	def is_initialized(self):
		return self.stage == self.STAGE_INITIALIZED

	@property
	def is_provisioned(self):
		return self.stage == self.STAGE_PROVISIONED

	@property
	def is_test_complete(self):
		return self.stage == self.STAGE_TEST_COMPLETE

	@property
	def is_destroyed(self):
		return self.stage == self.STAGE_DESTROYED

	@property
	def schedule(self):
		if self._schedule is None:
			self.updateTestSchedule()
		return self._schedule

	@property
	def scheduledGroups(self):
		for s in self.schedule:
			if s.type == 'GROUP':
				yield s.name

	@property
	def scheduledTests(self):
		for s in self.schedule:
			if s.type == 'TEST':
				yield s.name

	def validate(self):
		info = twopence.TestBase().findTestCase(self.name)
		if info is None:
			error(f"could not find {self.description}")
			return False

		self.info = info
		self.testConfigPath = info.config
		self.testScriptPath = info.script

		# parse testcase.conf and extract the list of node names
		testConfig = info.open()
		self._nodes = [node.name for node in testConfig.nodes]

		return True

	def perform(self, testrunConfig, console = None):
		self.console = console

		self.initializeWorkspace(testrunConfig)

		self.interactPreProvisioned()
		self.provisionCluster()

		self.interactPostProvisioned()
		self.runScript()

		self.interactPostTestrun()
		self.validateResult()

		self.destroyCluster()

	def initializeWorkspace(self, testrunConfig):
		if not self.is_larval:
			return

		info("Initializing workspace")
		self.runProvisioner(
			"init",
			"--logspace", self.logspace,
			"--config", testrunConfig,
			"--config", self.testConfigPath)

		assert(self._nodes)

		self.stage = self.STAGE_INITIALIZED

	def provisionCluster(self):
		if not self.is_initialized:
			return

		info("Provisioning test nodes")
		argv = ["create"]
		if self.context.update_images is True:
			argv.append("--update-images")
		if self.context.update_images is False:
			argv.append("--no-update-images")

		if self.runProvisioner(*argv) != 0:
			info("Failed to provision cluster")
			return

		self.stage = self.STAGE_PROVISIONED

	def controlTests(self, verb, names):
		if len(names) == 1:
			wot = names[0]
			if verb == 'skip' and wot == "none" or \
			   verb == 'only' and wot == "all":
				self._control = None
				return self.updateTestSchedule()

		self._control = [verb, names]
		return self.updateTestSchedule()

	def displayClusterStatus(self):
		self.runProvisioner("status")

	def buildScriptInvocation(self):
		argv = [self.testScriptPath]

		# This is hard-coded, and we "just know" where it is.
		# If this ever changes, use
		#  twopence provision --workspace BLAH show status-file
		# to obtain the name of that file
		statusFile = os.path.join(self.workspace, "status.conf")
		argv += ["--config", statusFile]

		if self._control:
			verb, names = self._control
			for name in names:
				argv += [f"--{verb}", name]

		return argv

	class ScheduledTest:
		def __init__(self, type, name, skip, description = None):
			self.type = type
			self.name = name
			self.skip = bool(skip)
			self.description = description

		def __str__(self):
			skipped = ""
			if self.skip:
				skipped = ", SKIP"
			if self.type == 'GROUP':
				return f"Group {self.name:24}{skipped}"
			return f"  {self.name:30}{self.description}{skipped}"

		def __eq__(self, other):
			return self.type == other.type and \
			       self.name == other.name and \
			       self.skip == other.skip

	def updateTestSchedule(self):
		argv = self.buildScriptInvocation()
		argv.append('schedule')

		schedule = []
		with os.popen(" ".join(argv)) as f:
			for line in f.readlines():
				words = line.strip().split(':', maxsplit = 3)
				schedule.append(self.ScheduledTest(*words))

		changed = []
		if self._schedule:
			for old, new in zip(self._schedule, schedule):
				if old != new:
					changed.append(new)

		self._schedule = schedule
		return changed

	def runScript(self, rerun = False):
		if rerun and self.is_test_complete:
			pass
		elif not self.is_provisioned:
			info("unable to run script; nodes not yet provisioned")
			return

		info("Executing test script")
		argv = self.buildScriptInvocation()

		if self.runCommand(*argv) != 0:
			info("Test script return non-zero exit status")

			# FIXME: record failure; we should also return non-zero
			# exit status in this case

		self.stage = self.STAGE_TEST_COMPLETE

	def validateResult(self):
		if not self.is_test_complete:
			return

		if self.options.dryrun:
			return

		# at a minimum, we should try to load the junit results and check if they're
		# valid.
		# Additional things to do:
		# -	implement useful behavior on test failures, like offering ssh
		#	access; suspending and saving the SUTs; etc.
		# -	compare test results against a list of expected failures,
		#	and actively call out regressions (and improvements)
		# -	aggregate test results and store them in a database
		info("Validating test result")

		reportPath = os.path.join(self.logspace, "junit-results.xml")
		if not os.path.isfile(reportPath):
			error("cannot find test report document at {reportPath}")
			return

		self.testReportPath = reportPath

	def destroyCluster(self):
		# in any but the larval state, we have cleanup to do
		if self.is_larval:
			return

		info("Destroying test nodes")
		self.runProvisioner("destroy", "--zap")

		self.stage = self.STAGE_DESTROYED

	def runProvisioner(self, *args, **kwargs):
		return self.runCommand("twopence", "provision", "--workspace", self.workspace, *args, **kwargs)

	class PtyCommand:
		def __init__(self, argv):
			self.argv = argv
			self.winszChanged = True

		def execute(self):
			import pty

			r = pty.spawn(self.argv, self.readFromMaster)
			return r

		def updateWindowSize(self, masterFd, terminalFd):
			import fcntl
			import termios
			import struct

			data = bytearray(8)
			fcntl.ioctl(terminalFd, termios.TIOCGWINSZ, data)
			fcntl.ioctl(masterFd, termios.TIOCSWINSZ, data)

		def readFromMaster(self, fd):
			if self.winszChanged:
				self.updateWindowSize(fd, 0)
				self.winszChanged = False
			return os.read(fd, 1024)

	def runCommand(self, cmd, *args, usePty = False):
		argv = [cmd]
		if self.options.debug:
			argv.append("--debug")
		if self.options.debug_schema:
			argv.append("--debug-schema")

		argv += args

		# info("Executing command:")
		cmd = " ".join(argv)
		print("    " + cmd)

		if usePty:
			cmd = self.PtyCommand(argv)
			return cmd.execute()

		if self.options.dryrun:
			return 0

		if self.options.quiet:
			cmd += " >/dev/null 2>&1"

		return os.system(cmd)

	def interact(self, interaction):
		console = self.console
		if not console:
			return

		try:
			console.interact(interaction)
		except ContinueTestcase:
			pass
		except FinishTestcase:
			self.console = None
			pass

	def interactPreProvisioned(self):
		msg = "Ready to provision %s" % self.name
		self.interact(InteractionPreProvisioning(self, msg))

	def interactPostProvisioned(self):
		msg = "Provisioned %s, ready to execute" % self.name
		self.interact(InteractionPostProvisioning(self, msg))

	def interactPostTestrun(self):
		msg = "Test run %s complete, ready to destroy cluster" % self.name
		self.interact(InteractionPostTestRun(self, msg))

	def inspect(self):
		if self.runCommand(self.testScriptPath, "info") != 0:
			info("Test script return non-zero exit status")

class Testsuite(TestThing):
	type_string = "test suite"

	def __init__(self, name):
		super().__init__(name)
		self.testcases = None

		self.info = twopence.TestBase().findTestSuite(name)

	def validate(self):
		if self.testcases is not None:
			return True

		if not self.info or not self.info.validate():
			error(f"Cannot find {self.description}")
			return False

		self.testcases = self.info.open().testcases

		info(f"Loaded test suite {self.name}")
		if not self.testcases:
			error(f"{self.description} does not define any test cases")
			return False

		info("    consisting of " + ", ".join(self.testcases))
		return True

class TestMatrixColumn(TestThing):
	type_string = "test matrix column"

	def __init__(self, name, matrix_name, config):
		self.name = name
		self.matrix_name = matrix_name

		self.config = config
		self.parameters = config.parameters

	def parametersAsDict(self):
		result = {}
		for paramString in self.parameters:
			words = paramString.split('=', maxsplit = 1)
			if len(words) != 2:
				raise ValueError("argument to --parameter must be in the form name=value, not \"%s\"" % s)

			key, value = words
			result[key] = value

		return result

	def buildContext(self, context):
		info(f"Processing next column of test matrix {self.matrix_name}: {self.name}")
		return context.createSubContext(
				extra_path = [self.matrix_name, self.name],
				extra_parameters = self.parameters)

class Testmatrix(TestThing):
	type_string = "test matrix"

	def __init__(self, name, args):
		super().__init__(name)
		self.args = args
		self.columns = None

		self.info = twopence.TestBase().findTestMatrix(name)

	def validate(self):
		if self.columns is not None:
			return True

		if not self.info.validate():
			error(f"Cannot find test matrix {self.name}")
			return False

		self.load()

		info(f"Loaded {self.description} from {self.info.path}")
		if not self.columns:
			error(f"test matrix {self.name} does not define any columns")
			return False

		info(f"Test matrix {self.name} defines these columns")
		for column in self.columns:
			print(f"    {column.name}")
			for param in column.parameters:
				print(f"        {param}")

		return True

	def load(self):
		self.columns = []

		config = self.info.open()
		for columnConfig in config.columns:
			column = TestMatrixColumn(columnConfig.name, self.name, columnConfig)
			self.columns.append(column)

		# The name attribute is useful for later stages that don't know which matrix
		# the test run was based on
		name = config.name
		if name is None:
			raise ValueError(f"{self.info.path} does not define a name attribute")
		if name != self.name:
			raise ValueError(f"{self.info.path} specifies name = {name} (expected {self.name}")

class Pipeline:
	def __init__(self, context):
		self.context = context

		self.testcases = []
		self.valid = True

	def addTestcases(self, names):
		for name in names:
			if name not in self.testcases:
				self.testcases.append(name)

	def addTestsuites(self, names):
		for name in names:
			suite = Testsuite(name)
			if not suite.validate():
				self.valid = False
				continue

			self.addTestcases(suite.testcases)

	def start(self, context = None):
		if context is None:
			context = self.context

		testcases = []

		for name in self.testcases:
			test = Testcase(name, context)

			if not test.validate():
				self.valid = False

			for role in context.roles.values():
				if role.resolution and \
				   not test.validateCompatibility(role.resolution.features):
					test.isCompatible = False

			testcases.append(test)

		if not self.valid:
			error("Detected one or more invalid test cases")
			return None

		if not testcases:
			error("No test cases defined")
			return None

		if not any(_.isCompatible for _ in testcases):
			error("All test cases are incompatible with the base platform")
			return None

		return testcases

class Runner:
	MODE_TESTS = 0
	MODE_SUITES = 1

	class RoleSettings:
		def __init__(self, name, platform = None, application = None, os = None, buildOptions = None):
			self.name = name
			self.platform = platform
			self.application = application
			self.os = os

			self.buildOptions = set()
			if buildOptions is not None:
				self.buildOptions.update(buildOptions)

			self.resolution = None
			self.repositories = []
			self.provisionOptions = set()

		def setApplication(self, application):
			if self.application is not None and self.application != application:
				raise ValueError(f"Conflicting settings of application for role {self.name}: {self.application} vs {application}")
			self.application = application

		def setOS(self, os):
			if self.os is not None and self.os != os:
				raise ValueError(f"Conflicting settings of OS for role {self.name}: {self.os} vs {os}")
			self.os = os

		def addBuildOption(self, name):
			self.buildOptions.add(name)

		def setResolution(self, platform):
			self.resolution = platform
			self.provisionOptions = self.buildOptions.difference(platform.applied_build_options)

	def __init__(self, mode = MODE_TESTS):
		self.mode = mode

		parser = self.build_arg_parser()
		args = parser.parse_args()

		if args.debug:
			twopence.logger.enableLogLevel('debug')

		self.valid = False
		self._roles = {}
		self.matrix = None

		self.setBackend(args.backend)

		self.definePlatforms(args)

		self.context = Context.makeToplevel(args, self._roles)

		self.pipeline = Pipeline(self.context)
		if self.mode == self.MODE_TESTS:
			self.pipeline.addTestcases(args.testcase)
		elif self.mode == self.MODE_SUITES:
			self.pipeline.addTestsuites(args.testsuite)
		else:
			raise ValueError(f"invalid mode {self.mode}")

		if args.matrix:
			self.matrix = Testmatrix(args.matrix, args)

		self.console = None
		if args.interactive:
			self.console = Console()

	@property
	def backend(self):
		return self._backend.name

	def setBackend(self, name):
		import twopence.provision

		self._backend = twopence.provision.createBackend(name)

	@property
	def roles(self):
		return self._roles.values()

	def createRoleSettings(self, roleName, **kwargs):
		if roleName not in self._roles:
			role = self.RoleSettings(roleName, **kwargs)

			# We want to run a test - so always make sure twopence is configured.
			# If we're using vagrant, we also want to enable twopence-tcp
			role.buildOptions.update(self._backend.twopenceBuildOptions)
			role.repositories += self._backend.twopenceRepositories

			self._roles[roleName] = role
		return self._roles[roleName]

	def definePlatforms(self, args):
		def processRoleOptions(what, list):
			for option in list:
				if '=' not in option:
					error(f"Cannot handle --{what} \"{option}\" - option must be in the form \"ROLE=NAME\"")
					raise ValueError(f"Bad --{what} argument")

				name, value = option.split('=', maxsplit = 1)

				role = self.createRoleSettings(name)
				yield role, value

		defaultRole = self.createRoleSettings('default', platform = args.platform, application = args.application, os = args.os, buildOptions = set(args.feature))
		for role, name in processRoleOptions('role-os', args.role_os):
			role.setOS(name)

		for role, name in processRoleOptions('role-application', args.role_application):
			role.setApplication(name)

		for role, name in processRoleOptions('role-platform', args.role_platform):
			role.setPlatform(name)

		for role, name in processRoleOptions('role-feature', args.role_feature):
			role.addBuildOption(name)

		for role in self.roles:
			if role.platform and role.os:
				raise ValueError(f"You cannot specify both --role-os and --role-platform")
			if role.platform is None:
				if role.os or role.application:
					pass
				else:
					role.platform = defaultRole.platform
					if role.platform:
						continue

					role.application = defaultRole.application
					role.os = defaultRole.os

			role.buildOptions.update(defaultRole.buildOptions)

			if not self.resolvePlatform(role, args.gold_only):
				raise ValueError(f"Could not identify a platform for role {role.name}")

		printedHeader = False
		for role in self.roles:
			if role.resolution is None:
				continue

			if not printedHeader:
				print("Platform settings for role(s):")
				printedHeader = True

			print(f"{role.name:20} platform {role.resolution.name:40} build {role.provisionOptions}")

	# Returns False iff the role specified platforms hints, but we were not able to resolve them.
	def resolvePlatform(self, role, goldenImagesOnly):
		import twopence.provision

		if role.platform:
			role.setResolution(twopence.provision.getPlatform(role.platform))
			return True

		requestedOS = role.os
		wantedBuildOptions = role.buildOptions

		bestMatch = None
		bestScore = -1

		if role.application:
			if wantedBuildOptions:
				raise ValueError("Use of application images not compatible with any build options")

			debug(f"Role {role.name}: finding best application {role.application} for {requestedOS or 'any OS'}")
			found = list(twopence.provision.locateApplicationsForOS(role.application, requestedOS, self.backend))
		elif requestedOS:
			debug(f"Role {role.name}: finding best platform for OS {requestedOS} with build options {wantedBuildOptions}")
			found = list(twopence.provision.locatePlatformsForOS(requestedOS, self.backend))
		else:
			return True

		for platform in found:
			if not platform.applied_build_options.issubset(wantedBuildOptions):
				continue

			if goldenImagesOnly and platform.built_from:
				debug(f"{platform.name} is not a golden image, ignored")
				continue

			# scoring:
			#  1 points if the platform has twopence installed
			#  2 points for every other feature that is present
			score = 2 * len(platform.applied_build_options)
			if 'twopence' in platform.applied_build_options:
				score -= 1

			debug(f"  {platform.name} matches {requestedOS} and {self.backend}. built with {platform.applied_build_options}, score={score}")
			if score >= bestScore:
				bestMatch = platform
				bestScore = score

		if bestMatch is None:
			error(f"Could not find a platform for OS {requestedOS}")
			return None

		lacking = wantedBuildOptions.difference(bestMatch.applied_build_options)
		if not lacking:
			info(f"Role {role.name}: {bestMatch.name} is the perfect match for OS {requestedOS} with build options {wantedBuildOptions}")
		else:
			info(f"Role {role.name}: {bestMatch.name} is a good match for OS {requestedOS} with build options {wantedBuildOptions}")
			info(f"The only build option(s) missing: " + ", ".join(lacking))

		role.setResolution(bestMatch)
		return bestMatch

	@property
	def workspace(self):
		return self.context.workspace

	@property
	def logspace(self):
		return self.context.logspace

	def validate(self):
		if not self.valid:
			self.valid = self._validate()

		return self.valid

	def _validate(self):
		valid = True

		if not self._roles:
			error("no platforms specified; please specify one using --platform or --os")
			valid = False

		if os.path.exists(self.workspace) and not os.path.isdir(self.workspace):
			error("workspace {self.workspace} exists, but is not a directory")
			valid = False
		if os.path.exists(self.logspace) and not os.path.isdir(self.logspace):
			error("logspace {self.logspace} exists, but is not a directory")
			valid = False

		return valid

	def perform(self):
		if not self.validate():
			print("Fatal: refusing to run any tests due to above error(s)")
			exit(1)

		if not self.matrix:
			self.context.attachResults(ResultsVector())
			self._perform(self.context)
		else:
			matrix = self.matrix

			if not matrix.validate() or not self.context.validateMatrix(matrix):
				error(f"Matrix is not compatible with requested platform(s)")
				print("Fatal: refusing to run any tests due to above error(s)")
				exit(1)

			self.context.attachResults(ResultsMatrix(matrix.name))
			for column in matrix.columns:
				context = column.buildContext(self.context)
				if not self._perform(context):
					info("Aborting test matrix")
					break

	def _perform(self, context):
		testcases = self.pipeline.start(context)
		if testcases is None:
			print("Fatal: refusing to run any tests due to above error(s)")
			exit(1)

		okayToContinue = True

		testrunConfig = context.createTestrunConfig()
		for test in testcases:
			if not test.isCompatible:
				info(f"Skipping {test.description} because it's not compatible with the plaform's feature set")
				# FIXME: generate a test report that says all tests we skipped
				continue

			info("About to perform %s" % test.name)
			info(f" Workspace is {test.workspace}")
			info(f" Logspace is {test.logspace}")
			try:
				test.perform(testrunConfig, self.console)
			except AbortedTestcase:
				print("Test %s was aborted, trying to clean up" % test.name)
				test.destroyCluster()
				okayToContinue = False
				break

			if test.testReportPath:
				info(f"Test report can be found in {test.testReportPath}")

				report = LogParser(test.testReportPath)
				context.mergeTestReport(report)

		os.remove(testrunConfig)
		return okayToContinue

	def build_arg_parser(self):
		import argparse

		parser = argparse.ArgumentParser(description = 'Provision and run tests.')
		parser.add_argument('--backend',
			help = 'specify provisioning backend (vagrant, podman, ... - defaults to vagrant)')
		parser.add_argument('--platform',
			help = 'specify the OS platform to use for all nodes and roles')
		parser.add_argument('--application',
			help = 'specify the application to deploy to all nodes')
		parser.add_argument('--os',
			help = 'specify the OS to use for all nodes and roles')
		parser.add_argument('--testrun',
			help = 'the testrun this test case is part of')
		parser.add_argument('--workspace',
			help = 'the directory to use as workspace')
		parser.add_argument('--logspace',
			help = 'the directory to use as logspace')
		parser.add_argument('--clobber', default = False, action = 'store_true',
			help = 'Clobber existing test results (default)')
		parser.add_argument('--no-clobber', default = False, action = 'store_true',
			help = 'Do not clobber existing test results (error out of results exist)')
		parser.add_argument('--parameter', action = 'append',
			help = 'Parameters to be passed to the test suite, in name=value format')
		parser.add_argument('--matrix',
			help = 'Name of a test matrix to be applied to the test cases')
		parser.add_argument('--dry-run', default = False, action = 'store_true',
			help = 'Do not run any commands, just show what would be done')
		parser.add_argument('--debug', default = False, action = 'store_true',
			help = 'Enable debugging output from the provisioner')
		parser.add_argument('--debug-schema', default = False, action = 'store_true',
			help = 'Enable schema debugging output from the provisioner')
		parser.add_argument('--quiet', default = False, action = 'store_true',
			help = 'Do not show output of provisioning and test script')
		parser.add_argument('--feature', default = [], action = 'append',
			help = 'Specify features you want the deployed image to provide')
		parser.add_argument('--interactive', default = False, action = 'store_true',
			help = 'Run tests interactively, stopping after each step.')

		parser.add_argument('--role-platform', default = [], action = 'append',
			help = 'specify the OS platform to use for a specific role')
		parser.add_argument('--role-os', default = [], action = 'append',
			help = 'specify the OS to use for a specific role')
		parser.add_argument('--role-feature', default = [], action = 'append',
			help = 'specify features you want the deployed image to provide for a specific role')
		parser.add_argument('--role-application', default = [], action = 'append',
			help = 'specify the application to deploy to for a specific role')

		parser.add_argument('--gold-only', default = False, action = 'store_true',
			help = 'Ignore silver images and only use golden images')
		parser.add_argument('--update-images', default = False, action = 'store_true',
			help = 'For backends that support an upstream image registry, always try to use the latest version available')
		parser.add_argument('--no-update-images', default = False, action = 'store_true',
			help = 'Do not try to use the latest version available')

		if self.mode == self.MODE_TESTS:
			parser.add_argument('testcase', metavar='TESTCASE', nargs='+',
				help = 'name of the test cases to run')
		elif self.mode == self.MODE_SUITES:
			parser.add_argument('testsuite', metavar='TESTSUITE', nargs='+',
				help = 'name of the test suites to run')

		return parser

class Inspector:
	def __init__(self):
		parser = self.build_arg_parser()
		args = parser.parse_args()

		self.testcases = []
		for name in args.testcase:
			test = Testcase(name, workspace = None)
			test.validate()
			self.testcases.append(test)

	def perform(self):
		info("Inspecting test cases")
		for test in self.testcases:
			test.inspect()

	def build_arg_parser(self):
		import argparse

		parser = argparse.ArgumentParser(description = 'Inspect tests.')
		parser.add_argument('testcase', metavar='TESTCASE', nargs='+',
			help = 'name of the test cases to inspect')
		return parser
