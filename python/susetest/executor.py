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

class Interaction(object):
	class Command(object):
		def __init__(self, name, description, func):
			self.name = name
			self.description = description.strip()
			self.func = func

		def getCompletion(self, tokens, nth):
			return None

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
			   attr != self.Command and \
			   issubclass(attr, self.Command):
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
		cmd = self.Command(name, description, func)
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

	def inspect(self, testcase, *args):
		'''inspect: display information on the test case'''
		testcase.inspect()

	def finish(self, testcase, *args):
		'''finish: finish the test case non-interactively'''
		raise FinishTestcase()

	def help(self, testcase, *args):
		'''help: display help message'''

		for (name, cmd) in self.commands.items():
			print("%-20s %s" % (name, cmd.description))

	def abort(self, testcase, *args):
		'''abort: abort this test case'''
		raise AbortedTestcase()

class InteractionPreProvisioning(Interaction):
	pass

class InteractionPostProvisioning(Interaction):
	def status(self, testcase, *args):
		'''status: display the status of provisioned cluster'''
		testcase.displayClusterStatus()

	class SSHCommand(Interaction.Command):
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
			testcase.runProvisioner("login", name)

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
	def __init__(self, workspace, logspace, parent = None,
			parameters = [],
			dryrun = False, debug = False, quiet = False, clobber = False,
			roles = {},
			results = None):

		self.workspace = workspace
		self.logspace = logspace
		self.results = results

		if parent:
			self.roles = parent.roles

			self.dryrun = parent.dryrun
			self.debug = parent.debug
			self.quiet = parent.quiet
			self.clobber = parent.clobber
		else:
			self.roles = roles
			self.dryrun = dryrun
			self.debug = debug
			self.quiet = quiet
			self.clobber = clobber

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

		return Context(
			parent = self,
			workspace = os.path.join(self.workspace, *extra_path),
			logspace = os.path.join(self.logspace, *extra_path),
			results = results,
			parameters = self.parameters + extra_parameters)

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

	def attachResults(self, results):
		results.attachToLogspace(self.logspace, clobber = self.clobber)
		self.results = results

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
		self.dryrun = context.dryrun
		self.debug = context.debug
		self.quiet = context.quiet

		self.isCompatible = True

		self.testConfig = None
		self.testScript = None
		self.testReport = None

		self.stage = self.STAGE_LARVAL
		self._nodes = []

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

	def validate(self):
		info = twopence.TestBase().findTestCase(self.name)
		if info is None:
			error(f"could not find {self.description}")
			return False

		self.info = info
		self.testConfig = info.config
		self.testScript = info.script
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
			"--config", self.testConfig)

		config = curly.Config(self.testConfig)
		tree = config.tree()
		self._nodes = []
		for name in tree.get_children("node"):
			self._nodes.append(name)

		self.stage = self.STAGE_INITIALIZED

	def provisionCluster(self):
		if not self.is_initialized:
			return

		info("Provisioning test nodes")
		if self.runProvisioner("create") != 0:
			info("Failed to provision cluster")
			return

		self.stage = self.STAGE_PROVISIONED

	def displayClusterStatus(self):
		self.runProvisioner("status")

	def runScript(self, rerun = False):
		if rerun and self.is_test_complete:
			pass
		elif not self.is_provisioned:
			info("unable to run script; nodes not yet provisioned")
			return

		info("Executing test script")

		# This is hard-coded, and we "just know" where it is.
		# If this ever changes, use
		#  twopence provision --workspace BLAH show status-file
		# to obtain the name of that file
		statusFile = os.path.join(self.workspace, "status.conf")

		if self.runCommand(self.testScript, "--config", statusFile) != 0:
			info("Test script return non-zero exit status")

			# FIXME: record failure; we should also return non-zero
			# exit status in this case

		self.stage = self.STAGE_TEST_COMPLETE

	def validateResult(self):
		if not self.is_test_complete:
			return

		if self.dryrun:
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
			print("Error: cannot find test report document at %s" % reportPath);
			return

		self.testReport = reportPath

	def destroyCluster(self):
		# in any but the larval state, we have cleanup to do
		if self.is_larval:
			return

		info("Destroying test nodes")
		self.runProvisioner("destroy", "--zap")

		self.stage = self.STAGE_DESTROYED

	def runProvisioner(self, *args):
		return self.runCommand("twopence provision", "--workspace", self.workspace, *args)

	def runCommand(self, cmd, *args):
		argv = [cmd]
		if self.debug:
			argv.append("--debug")

		argv += args

		# info("Executing command:")
		cmd = " ".join(argv)
		print("    " + cmd)

		if self.dryrun:
			return 0

		if self.quiet:
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
		if self.runCommand(self.testScript, "info") != 0:
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

		self.testcases = self.info.open().get_values("testcases")

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
		self.parameters = config.get_values("parameters")

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

		self.columns = self.load()

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
		result = []

		config = self.info.open()
		for child in config:
			if child.type != 'column':
				continue

			column = TestMatrixColumn(child.name, self.name, child)
			result.append(column)

		# The name attribute is useful for later stages that don't know which matrix
		# the test run was based on
		name = config.get_value("name")
		if name is None:
			raise ValueError(f"{self.info.path} does not define a name attribute")
		if name != self.name:
			raise ValueError(f"{self.info.path} specifies name = {name} (expected {self.name}")

		return result

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
				if not test.validateCompatibility(role.resolution.features):
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
		def __init__(self, name, platform = None, os = None, buildOptions = None):
			self.name = name
			self.platform = platform
			self.os = os

			self.buildOptions = set()
			if buildOptions is not None:
				self.buildOptions.update(buildOptions)

			self.resolution = None
			self.repositories = []
			self.provisionOptions = set()

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
		self.buildTestContext(args)

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

			# We want to run a test - so always make sure twopene is configured.
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

		defaultRole = self.createRoleSettings('default', platform = args.platform, os = args.os, buildOptions = set(args.feature))
		for role, name in processRoleOptions('role-os', args.role_os):
			role.setOS(name)

		for role, name in processRoleOptions('role-platform', args.role_platform):
			role.setPlatform(name)

		for role, name in processRoleOptions('role-feature', args.role_feature):
			role.addBuildOption(name)

		for role in self.roles:
			if role.platform and role.os:
				raise ValueError(f"You cannot specify both --role-os and --role-platform")
			if role.platform is None:
				if role.os is None:
					role.platform = defaultRole.platform
					if role.platform:
						continue
					role.os = defaultRole.os
					if role.os is None:
						raise ValueError(f"Unable to determine platform for role \"{role.name}\"")

			role.buildOptions.update(defaultRole.buildOptions)
			self.resolvePlatform(role)
			if role.resolution is None:
				raise ValueError(f"Could not identify a platform for role {role.name}")

		print("Platform settings for role(s):")
		for role in self.roles:
			print(f"{role.name:20} platform {role.resolution.name:40} build {role.provisionOptions}")

	def resolvePlatform(self, role):
		import twopence.provision

		if role.platform:
			role.setResolution(twopence.provision.getPlatform(role.platform))
			return

		requestedOS = role.os
		wantedBuildOptions = role.buildOptions

		bestMatch = None
		bestScore = -1

		debug(f"Role {role.name}: finding best platform for OS {requestedOS} with build options {wantedBuildOptions}")
		for platform in twopence.provision.locatePlatformsForOS(requestedOS, self.backend):
			if not platform.applied_build_options.issubset(wantedBuildOptions):
				continue

			# scoring:
			#  1 points if the platform has twopence installed
			#  2 points for every other feature that is present
			score = 2 * len(platform.applied_build_options)
			if 'twopence' in platform.applied_build_options:
				score -= 1

			debug(f"  {platform.name} matches {requestedOS} and {self.backend}. built with {platform.applied_build_options}, score={score}")
			if score > bestScore:
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

	def buildTestContext(self, args):
		self.testrun = args.testrun
		self.workspace = args.workspace
		self.logspace = args.logspace

		if self.workspace is None:
			self.workspace = os.path.expanduser("~/susetest/work")
		if self.logspace is None:
			self.logspace = os.path.expanduser("~/susetest/logs")

		if self.testrun:
			self.workspace = os.path.join(self.workspace, self.testrun)
			self.logspace = os.path.join(self.logspace, self.testrun)

		self.context = Context(self.workspace, self.logspace,
				roles = self._roles,
				parameters = args.parameter,
				dryrun = args.dry_run,
				debug = args.debug,
				clobber = args.clobber)

		return

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

		testrunConfig = self.createTestrunConfig(context)
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

			if test.testReport:
				info(f"Test report can be found in {test.testReport}")

				report = LogParser(test.testReport)
				context.mergeTestReport(report)

		os.remove(testrunConfig)
		return okayToContinue

	# could be moved to Context
	def createTestrunConfig(self, context):
		path = os.path.join(self.workspace, "testrun.conf")
		info("Creating %s" % path)

		config = curly.Config()
		tree = config.tree()

		tree.set_value("backend", self.backend)

		for role in context.roles.values():
			node = tree.add_child("role", role.name)
			node.set_value("platform", role.resolution.name)
			if role.repositories:
				node.set_value("repositories", role.repositories)
			if role.provisionOptions:
				node.set_value("build", list(role.provisionOptions))

		if context.parameters:
			child = tree.add_child("parameters")
			for paramString in context.parameters:
				words = paramString.split('=', maxsplit = 1)
				if len(words) != 2:
					raise ValueError("argument to --parameter must be in the form name=value, not \"%s\"" % s)

				child.set_value(*words)

		config.save(path)

		info("Contents of %s:" % path)
		with open(path) as f:
			for l in f.readlines():
				print("    %s" % l.rstrip())

		return path

	def build_arg_parser(self):
		import argparse

		parser = argparse.ArgumentParser(description = 'Provision and run tests.')
		parser.add_argument('--backend',
			help = 'specify provisioning backend (vagrant, podman, ... - defaults to vagrant)')
		parser.add_argument('--platform',
			help = 'specify the OS platform to use for all nodes and roles')
		parser.add_argument('--os',
			help = 'specify the OS to use for all nodes and roles')
		parser.add_argument('--testrun',
			help = 'the testrun this test case is part of')
		parser.add_argument('--workspace',
			help = 'the directory to use as workspace')
		parser.add_argument('--logspace',
			help = 'the directory to use as logspace')
		parser.add_argument('--clobber', default = False, action = 'store_true',
			help = 'Clobber existing test results')
		parser.add_argument('--parameter', action = 'append',
			help = 'Parameters to be passed to the test suite, in name=value format')
		parser.add_argument('--matrix',
			help = 'Name of a test matrix to be applied to the test cases')
		parser.add_argument('--dry-run', default = False, action = 'store_true',
			help = 'Do not run any commands, just show what would be done')
		parser.add_argument('--debug', default = False, action = 'store_true',
			help = 'Enable debugging output from the provisioner')
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
			help = 'Specify features you want the deployed image to provide for a specific role')

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
