#!/usr/bin/python3
#
# Run a test, including the provisioning and teardown of all nodes
#

import argparse
import os
import curly

def info(msg):
	print("== %s" % msg)

class InvalidTestcase(Exception):
	pass

class Testcase:
	rootdir = "/usr/lib/twopence"

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

	def perform(self, testrunConfig):
		self.initializeWorkspace(testrunConfig)
		self.provisionCluster()
		self.runScript()
		self.validateResult()
		self.destroyCluster()

	def initializeWorkspace(self, testrunConfig):
		info("Initializing workspace")
		self.runProvisioner(
			"init",
			"--logspace", self.logspace,
			"--config", testrunConfig,
			"--config", self.testConfig)

	def provisionCluster(self):
		info("Provisioning test nodes")
		self.runProvisioner("create")

	def runScript(self):
		info("Executing test script")

		# This is hard-coded, and we "just know" where it is.
		# If this ever changes, use
		#  twopence provision --workspace BLAH show status-file
		# to obtain the name of that file
		statusFile = os.path.join(self.workspace, "status.conf")

		self.runCommand(self.testScript, "--config", statusFile)

	def validateResult(self):
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
		info("Destroying test nodes")
		self.runProvisioner("destroy", "--zap")

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
			test.perform(testrunConfig)

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
		parser.add_argument('testcase', metavar='TESTCASE', nargs='+',
			help = 'name of the test cases to run')

		return parser

