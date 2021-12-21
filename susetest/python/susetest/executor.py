#!/usr/bin/python3
##################################################################
#
# Run a test, including the provisioning and teardown of all nodes
#
# Copyright (C) 2021 SUSE Linux GmbH
#
##################################################################

import argparse
import os
import curly
import readline
import atexit

def info(msg):
	print("== %s" % msg)

class InvalidTestcase(Exception):
	pass

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
	pass

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

class Testcase:
	rootdir = "/usr/lib/twopence"

	STAGE_LARVAL		= "larval"
	STAGE_INITIALIZED	= "initialized"
	STAGE_PROVISIONED	= "provisioned"
	STAGE_TEST_COMPLETE	= "complete"
	STAGE_DESTROYED		= "destroyed"

	def __init__(self, name, workspace, logspace = None, dryrun = False, debug = False, quiet = False):
		self.name = name
		self.dryrun = dryrun
		self.debug = debug
		self.quiet = quiet
		self.workspace = workspace
		self.logspace = logspace
		self.path = os.path.join(self.rootdir, name)

		self.testConfig = None
		self.testScript = None

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
		if not os.path.isdir(self.path):
			raise InvalidTestcase("test directory %s does not exist" % self.path)

		self.testConfig = self.validateTestfile("testcase.conf")
		self.testScript = self.validateTestfile("run", executable = True)

	def validateTestfile(self, filename, executable = False):
		path = os.path.join(self.path, filename)
		if not os.path.isfile(path):
			raise InvalidTestcase("test directory %s does not contain %s" % (self.path, filename))
		if executable and not (os.stat(path).st_mode & 0o111):
			raise InvalidTestcase("%s is not executable" % path)
		return path

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
		self.runProvisioner("create")

		self.stage = self.STAGE_PROVISIONED

	def displayClusterStatus(self):
		self.runProvisioner("status")

	def runScript(self):
		if not self.is_provisioned:
			info("unable to run script; nodes not yet provisioned")
			return

		info("Executing test script")

		# This is hard-coded, and we "just know" where it is.
		# If this ever changes, use
		#  twopence provision --workspace BLAH show status-file
		# to obtain the name of that file
		statusFile = os.path.join(self.workspace, "status.conf")

		self.runCommand(self.testScript, "--config", statusFile)

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

	def destroyCluster(self):
		if not (self.is_initialized or self.is_provisioned or self.is_test_complete):
			return

		info("Destroying test nodes")
		self.runProvisioner("destroy", "--zap")

		self.stage = self.STAGE_DESTROYED

	def runProvisioner(self, *args):
		self.runCommand("twopence provision", "--workspace", self.workspace, *args)
	
	def runCommand(self, cmd, *args):
		argv = [cmd]
		if self.debug:
			argv.append("--debug")

		argv += args

		# info("Executing command:")
		cmd = " ".join(argv)
		print("    " + cmd)

		if self.dryrun:
			return

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

class Runner:
	def __init__(self):
		parser = self.build_arg_parser()
		args = parser.parse_args()

		self.valid = False
		self.platform = args.platform
		self.testrun = args.testrun
		self.workspace = args.workspace
		self.logspace = args.logspace
		self.testcases = []

		if self.workspace is None:
			self.workspace = os.path.expanduser("~/susetest/work")
		if self.logspace is None:
			self.logspace = os.path.expanduser("~/susetest/logs")

		if not os.path.isdir(self.workspace):
			os.makedirs(self.workspace)
		info("Workspace is %s" % self.workspace)

		if not os.path.isdir(self.logspace):
			os.makedirs(self.logspace)
		info("Workspace is %s" % self.logspace)

		if self.testrun:
			self.workspace = os.path.join(self.workspace, self.testrun)
			self.logspace = os.path.join(self.logspace, self.testrun)

		for name in args.testcase:
			test = Testcase(name,
					workspace = os.path.join(self.workspace, name),
					logspace = os.path.join(self.logspace, name),
					dryrun = args.dry_run,
					debug = args.debug)
			self.testcases.append(test)

		self.console = None
		if args.interactive:
			self.console = Console()

	def validate(self):
		if not self.valid:
			if not self._validate():
				print("Fatal: refusing to run any tests due to above error(s)")
				exit(1)

			self.valid = True
		return self.valid

	def _validate(self):
		valid = True

		if self.platform is None:
			print("Error: no default platform specified; please specify one using --platform")
			valid = False

		for test in self.testcases:
			try:
				test.validate()
			except InvalidTestcase as e:
				print("Error: %s" % e)
				valid = False

		if not os.path.isdir(self.workspace):
			print("Error: workspace %s does not exist, or is not a directory" % self.workspace)
			valid = False
		if not os.path.isdir(self.logspace):
			print("Error: logspace %s does not exist, or is not a directory" % self.logspace)
			valid = False

		self.valid = valid
		return valid

	def perform(self):
		self.validate()

		testrunConfig = self.createTestrunConfig()
		for test in self.testcases:
			info("About to perform %s" % test.name)
			try:
				test.perform(testrunConfig, self.console)
			except AbortedTestcase:
				print("Test %s was aborted, trying to clean up" % test.name)
				test.destroyCluster()
				break

		os.remove(testrunConfig)

	def createTestrunConfig(self):
		path = os.path.join(self.workspace, "testrun.conf")
		info("Creating %s" % path)

		config = curly.Config()
		tree = config.tree()

		node = tree.add_child("role", "default")
		node.set_value("platform", self.platform)
		node.set_value("repositories", ["testbus", ])
		config.save(path)

		info("Contents of %s:" % path)
		with open(path) as f:
			for l in f.readlines():
				print("    %s" % l.rstrip())

		return path

	def build_arg_parser(self):
		import argparse

		parser = argparse.ArgumentParser(description = 'Provision and run tests.')
		parser.add_argument('--platform',
			help = 'specify the OS platform to use for all nodes and roles')
		parser.add_argument('--testrun',
			help = 'the testrun this test case is part of')
		parser.add_argument('--workspace',
			help = 'the directory to use as workspace')
		parser.add_argument('--logspace',
			help = 'the directory to use as logspace')
		parser.add_argument('--dry-run', default = False, action = 'store_true',
			help = 'Do not run any commands, just show what would be done')
		parser.add_argument('--debug', default = False, action = 'store_true',
			help = 'Enable debugging output from the provisioner')
		parser.add_argument('--quiet', default = False, action = 'store_true',
			help = 'Do not show output of provisioning and test script')
		parser.add_argument('--interactive', default = False, action = 'store_true',
			help = 'Run tests interactively, stopping after each step.')
		parser.add_argument('testcase', metavar='TESTCASE', nargs='+',
			help = 'name of the test cases to run')

		return parser

