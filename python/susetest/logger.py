##################################################################
#
# This wraps the journal object and test logging
#
# Copyright (C) 2014-2022 SUSE Linux GmbH
#
##################################################################

import suselog
import susetest

class TestLoggerHooks:
	def __init__(self):
		self._groupBeginHooks = []
		self._groupEndHooks = []
		self._postTestHooks = []

	def addGroupBeginHook(self, fn):
		self._groupBeginHooks.append(fn)

	def addGroupEndHook(self, fn):
		self._groupEndHooks.append(fn)

	def addPostTestHook(self, fn):
		self._postTestHooks.append(fn)

	def runGroupBeginHooks(self, group):
		for fn in self._groupBeginHooks:
			fn(group)

	def runGroupEndHooks(self, group):
		for fn in self._groupEndHooks:
			fn(group)

	def runPostTestHooks(self):
		for fn in self._postTestHooks:
			fn()

class GroupLogger:
	def __init__(self, journal, hooks, name, global_resources = None):
		self._name = name
		self._journal = journal
		self._hooks = hooks

		self._currentTest = None
		self.global_resources = global_resources

		assert(not global_resources)

		self._journal.beginGroup(self._name)
		self._active = True

	def __del__(self):
		self.end()

	@property
	def active(self):
		return self._active

	def __bool__(self):
		return self._active

	@property
	def currentTest(self):
		return self._currentTest

	def end(self):
		if self._active:
			self._hooks.runGroupEndHooks(self)
			self._journal.finishGroup()
			self._active = False

	@property
	def errors(self):
		fart

	@property
	def failures(self):
		fart

	def beginTest(self, *args, **kwargs):
		self.endTest()

		test = TestLogger(self._journal, self._hooks, *args, **kwargs)
		self._currentTest = test

		return test

	def endTest(self):
		test = self._currentTest
		if test:
			# Do not clear _currentTest until after we're done with test.end()
			# The reason being that this will call postTestHooks like a journal
			# or audit log monitor, which will want to log stuff via driver.log*,
			# which relies on currentTest
			test.end()

			self._currentTest = None

class TestLogger:
	class Outcome:
		def __init__(self, noun, logfn):
			self.noun = noun
			self.log = logfn

		def __str__(self):
			return self.noun

	def __init__(self, journal, hooks, name, *args, **kwargs):
		self._journal = journal
		self._hooks = hooks

		self._journal.beginTest(name, *args, **kwargs)
		self._active = True

		self._predict = None
		self._predictionArrived = False

		self.outcomeFailure = self.Outcome("failure", self._journal.failure)
		self.outcomeError = self.Outcome("error", self._journal.error)


	def __bool__(self):
		return self._active

	def end(self):
		if not self._active:
			return

		self._hooks.runPostTestHooks()

		if self._journal.status == "running":
			if self._predict and not self._predictionArrived:
				self._journal.failure(f"*** Expected {self._predict.noun} did not arrive")
			else:
				self._journal.success()

		self._active = False

	# mark the test as being skipped
	def skip(self):
		self._journal.skipped()
		self.end()

	def logInfo(self, message):
		self._journal.info(message)

	def logOutcome(self, outcome, message):
		if self._predict is outcome:
			if not self._predictionArrived:
				self._journal.info(f"*** Encountering expected {outcome.noun} of test case")
				self._predictionArrived = True
			self._journal.info(f"Expected {outcome.noun}: {message}")
			return

		if self._predict and not self._predictionArrived:
			self._journal.info("*** Encountering unpredicted {outcome.noun} of test case (expected {self._predict.noun})")
			self._predictionArrived = True

		outcome.log(message)

	def logFailure(self, message):
		self.logOutcome(self.outcomeFailure, message)

	def logError(self, message):
		self.logOutcome(self.outcomeError, message)

	def recordStdout(self, data):
		self._journal.recordStdout(data)

	def recordStderr(self, data):
		self._journal.recordStderr(data)

	def setPredictedOutcome(self, status, reason):
		if status == 'failure':
			outcome = self.outcomeFailure
		elif status == 'error':
			outcome = self.outcomeError
		else:
			raise ValueError(f"Cannot handle unknown prediction {status}")

		if self._predict is not None and self._predict is not outcome:
			self.logError(f"Cassandra is confused: conflicting predictions {self._predict} vs {status}")
			return

		self.logInfo(f"*** Setting the predicted outcome of this test case to {status} because of {reason}")
		self._predict = outcome

class Logger:
	def __init__(self, name, path):
		susetest.say(f"Writing journal to {path}")

		self._journal = suselog.Journal(name, path = path);
		self._hooks = TestLoggerHooks()

		self._currentGroup = None

	def __del__(self):
		self.close()

	def close(self):
		if self._journal:
			self._journal.writeReport()
			self._journal.close()
			self._journal = None

	def addGroupBeginHook(self, fn):
		self._hooks.addGroupBeginHook(fn)

	def addGroupEndHook(self, fn):
		self._hooks.addGroupEndHook(fn)

	def addPostTestHook(self, fn):
		self._hooks.addPostTestHook(fn)

	@property
	def currentGroup(self):
		return self._currentGroup

	@property
	def currentTest(self):
		group = self._currentGroup
		if group:
			return group.currentTest
		return None

	def beginGroup(self, name):
		if self._currentGroup is not None:
			self.endGroup()

		group = GroupLogger(self._journal, self._hooks, name)
		self._currentGroup = group

		# We need to call the hooks from here, after setting
		# self._currentGroup
		self._hooks.runGroupBeginHooks(group)

		return group

	def endGroup(self):
		group = self._currentGroup
		if not group or not group.active:
			return None

		self._currentGroup = None
		group.end()

		return group

	def logFatal(self, message):
		susetest.say("FATAL " + message)
		self._journal.fatal(message)

	def logInfo(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logInfo outside of a test case - message will be LOST: {message}")
			return

		test.logInfo(message)

	def logFailure(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logFailure outside of a test case - message will be LOST: {message}")
			return

		test.logFailure(message)

	def logError(self, message):
		test = self.currentTest
		if not test:
			print(f"*** Calling logError outside of a test case - message will be LOST: {message}")
			return

		test.logError(message)

	def recordStdout(self, data):
		test = self.currentTest
		if not test:
			print(f"*** Calling recordStdout outside of a test case - data will be LOST: {data}")
			return

		test.recordStdout(data)

	def recordStderr(self, data):
		self._journal.recordStderr(data)
		test = self.currentTest
		if not test:
			print(f"*** Calling recordStderr outside of a test case - data will be LOST: {data}")
			return

		test.recordStderr(data)

	def addProperty(self, name, value):
		self._journal.addProperty(name, value)
