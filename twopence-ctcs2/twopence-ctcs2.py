#!/usr/bin/python
#
# Helper program that lets you run ctcs2 tests through twopence
#
# Set
#  export TWOPENCE_CONFIG_PATH=./ctcs2.conf
# and run as
#  ./twopence-ctcs2.py foobar.tcf
#

import sys
import suselog
import twopence
import susetest
import argparse
import exceptions


class CTCS:
	defaultCommandUser	= 'root'
	defaultCommandTimeout	= 60

	class Command(object):
		def __init__(self):
			self.filename = None
			self.lineno = 0
			self.location = "<nowhere>"

		def setLocation(self, loc):
			self.location = loc

		def error(self, msg):
			raise exceptions.ValueError("%s: %s" % (self.location, msg))

		def skip(self):
			cmdType = type(self)
			return cmdType.__name__

	class NICommand(Command):
		def __init__(self, cmd, args):
			self.cmd = cmd;
			self.args = args

		def execute(self, ctcs):
			self.error("command \"%s\" not implemented" % self.cmd)

	class NotifyCommand(Command):
		def __init__(self, timeout, message):
			self.timeout = timeout
			self.message = message

		def execute(self, ctcs):
			class Callback:
				def __init__(self, journal, message):
					self.journal = journal
					self.message = message

				def timeout(self):
					try:
						import time

						now = time.strftime('%c')
						self.journal.info("## %s: %s ##" % (now, self.message))
					except:
						import traceback
						traceback.format_stack()

			ctcs.armNotify(self.timeout, Callback(ctcs.journal, self.message).timeout)

	class RunCommand(Command):
		def __init__(self, cmdline, condition = None, fg = True, iterations = 1, name = None):
			self.cmdline = cmdline
			self.condition = condition
			self.fg = fg
			self.iterations = iterations
			self.name = name

		def execute(self, ctcs):
			tc = ctcs.getTestCase(self.name)
			if self.fg:
				ctcs.beginTest(self.name, "Starting test %s" % self.name)
				if self.condition:
					ctcs.note("%s: evaluating conditional \"%s\"" % (self.location, self.condition))
					if not ctcs.testCondition(self.condition):
						ctcs.journal.skipped()
						return

				if not tc.arm(ctcs.sut, self.cmdline, fg = True, iterations = self.iterations):
					ctcs.error("Test case %s is already running" % self.name)
					return

				ctcs.note("%s: executing command: %s" % (self.location, ' '.join(self.cmdline)))
				st = ctcs.runTestCase(tc)
				if not st:
					ctcs.journal.failure(st.message)
				else:
					ctcs.journal.success()
			else:
				ctcs.note("Running background command %s" % self.name)
				if self.condition:
					ctcs.note("%s: evaluating conditional \"%s\"" % (self.location, self.condition))
					if not ctcs.testCondition(self.condition):
						ctcs.note("Condition not met; skipping command")
						return

				if not tc.arm(ctcs.sut, self.cmdline, fg = True, iterations = self.iterations):
					ctcs.note("Test case %s is already running" % self.name)
					return

				ctcs.note("%s: executing command: %s" % (self.location, ' '.join(self.cmdline)))
				ctcs.runTestCase(tc)

		def skip(self):
			ctcs.skipTest(self.name, "Skipping test %s" % self.name)

			cmdline = self.cmdline
			if type(cmdline) != str:
				cmdline = ' '.join(cmdline)

			return "command \"%s\" (%s)" % (self.name, cmdline)

	class TimerCommand(Command):
		def __init__(self, timeout):
			self.timeout = int(timeout)

		def execute(self, ctcs):
			ctcs.note("%s: setting timer to %u" % (self.location, self.timeout))
			ctcs.setTimer(self.timeout)

	class SetVariableCommand(Command):
		def __init__(self, var, value):
			self.var = var
			self.value = value

		def execute(self, ctcs):
			ctcs.note("%s: setting variable %s=\"%s\"" % (self.location, self.var, self.value))
			ctcs.setenv(self.var, value)

	class CleanupCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			ctcs.cleanup()

	class WaitCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			ctcs.wait()

	class ExitCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			ctcs.exit()

	class BeginLoopCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			pass

	class EndLoopCommand(Command):
		def __init__(self, begin = None):
			self.begin = begin

		def setBegin(self, dest):
			self.begin = dest

		def execute(self, ctcs):
			ctcs.goto(self.begin)

	class SyncLogCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			ctcs.setLogging(sync = True)

	class AsyncLogCommand(Command):
		def __init__(self):
			pass

		def execute(self, ctcs):
			ctcs.setLogging(sync = False)

	class ParsedLine:
		def __init__(self, filename, lineno, words):
			self.filename = filename
			self.lineno = lineno

			cmd = words.pop(0)
			if cmd == 'on':
				if len(l) == 0:
					self.error("missing keyword after \"on\"")

				cmd = "on " + l.pop(0)

			self.cmd = cmd
			self.args = words

		def location(self):
			return "%s:%u" % (self.filename, self.lineno)

		def error(self, msg):
			raise exceptions.ValueError("%s:%u: %s" % (self.filename, self.lineno, msg))

	class Parser:
		def __init__(self, filename):
			self.filename = filename
			self.lineno = 0
			self._loopBegin = None

			self.f = open(filename, "r")
			if not self.f:
				self.error("unable to open file")

		def nextLine(self):
			if not self.f:
				return None

			for line in self.f:
				self.lineno += 1
				if line[0] == '#':
					continue

				l = line.split()
				if len(l) == 0:
					continue

				return CTCS.ParsedLine(self.filename, self.lineno, l)

			self.f = None
			return None

		def error(self, parsedLine, msg):
			raise exceptions.ValueError("%s:%u: %s" % (parsedLine.filename, parsedLine.lineno, msg))

		def requireMinArgs(self, parsedLine, min):
			if len(parsedLine.args) >= min:
				return
			self.error(parsedLine, "\"%s\" requires at least %u argument%s" % (parsedLine.cmd,
						min,
						(min > 1) and "s" or ""))

		def requireArgs(self, parsedLine, exact):
			if len(parsedLine.args) == exact:
				return
			if exact == 0:
				self.error(parsedLine, "\"%s\" takes no argument%s" % parsedLine.cmd)

			self.error(parsedLine, "\"%s\" requires exactly %u argument%s" % (parsedLine.cmd,
						exact,
						(exact > 1) and "s" or ""))

		def nextCommand(self):
			parsedLine = self.nextLine()
			if not parsedLine:
				return None

			ret = self.buildCommand(parsedLine)
			if ret:
				ret.setLocation(parsedLine.location())

			return ret

		def buildCommand(self, parsedLine):
			cmd = parsedLine.cmd
			args = parsedLine.args

			# print "cmd=\"%s\", args=(\"%s\")" % (cmd, '", "'.join(args))

			if cmd == 'on event':
				self.requireMinArgs(parsedLine, 1)
				return CTCS.NICommand(cmd, args)
			elif cmd == 'on error':
				self.requireMinArgs(parsedLine, 1)
				return CTCS.NICommand(cmd, args)
			elif cmd == 'notify':
				self.requireArgs(parsedLine, 2)
				return CTCS.NotifyCommand(timeout = float(args[0]), message = args[1])
			elif cmd == 'timer':
				self.requireArgs(parsedLine, 1)
				return CTCS.TimerCommand(args[0])
			elif cmd == 'bg':
				self.requireMinArgs(parsedLine, 3)
				count = args.pop(0)
				label = args.pop(0)
				return CTCS.RunCommand(args, fg = False, iterations = count, name = label)
			elif cmd == 'bgif':
				self.requireMinArgs(parsedLine, 4)
				cond = args.pop(0)
				count = args.pop(0)
				label = args.pop(0)
				return CTCS.RunCommand(args, fg = False, condition = cond, iterations = count, name = label)
			elif cmd == 'fg':
				self.requireMinArgs(parsedLine, 3)
				count = args.pop(0)
				label = args.pop(0)
				return CTCS.RunCommand(args, fg = True, iterations = count, name = label)
			elif cmd == 'fgif':
				self.requireMinArgs(parsedLine, 4)
				cond = args.pop(0)
				count = args.pop(0)
				label = args.pop(0)
				return CTCS.RunCommand(args, fg = True, condition = cond, iterations = count, name = label)
			elif cmd == 'set':
				self.requireArgs(parsedLine, 2)
				return CTCS.SetVariableCommand(args[0], args[1])
			elif cmd == 'cleanup':
				self.requireArgs(parsedLine, 0)
				return CTCS.CleanupCommand()
			elif cmd == 'wait':
				self.requireArgs(parsedLine, 0)
				return CTCS.WaitCommand()
			elif cmd == 'synclog':
				self.requireArgs(parsedLine, 0)
				return CTCS.SyncLogCommand()
			elif cmd == 'asynclog':
				self.requireArgs(parsedLine, 0)
				return CTCS.AsyncLogCommand()
			elif cmd == 'begin':
				# The begin/loop construct in ctcs2 is fairly limited in
				# that it doesn't support nested loops.
				self.requireArgs(parsedLine, 0)
				if self._beginCommand:
					raise exceptions.ValueError("%s: begin statement without \"loop\" statement" % (
							self._beginCommand.location()))

				self._beginCommand = CTCS.BeginLoopCommand()
				return self._beginCommand
			elif cmd == 'loop':
				self.requireArgs(parsedLine, 0)
				if not self._beginCommand:
					self.error(parsedLine, "loop statement without matching \"begin\"");

				ret = CTCS.EndLoopCommand(self._beginCommand)
				self._beginCommand = None
				return ret
			elif cmd == 'exit':
				self.requireArgs(parsedLine, 0)
				return CTCS.ExitCommand()
			elif cmd == 'benchparser':
				self.requireArgs(parsedLine, 1)
				return CTCS.NICommand(cmd, args)

			self.error(parsedLine, "Unknown command \"%s\"" % cmd)

	class TestCase:
		def __init__(self, name, user = None, timeout = None):
			print "TestCase ctor; timeout=", timeout
			self.name = name
			self.user = user or CTCS.defaultCommandUser
			self.timeout = timeout or CTCS.defaultCommandTimeout
			self.command = None
			self.node = None
			self.iterations = 0
			self.elapsed = 0

		def arm(self, node, cmdline, fg, iterations):
			if self.isRunning():
				return False

			if type(cmdline) != str:
				cmdline = ' '.join(cmdline)

			command = twopence.Command(cmdline,
					background = not fg,
					timeout = self.timeout,
					user = self.user,
					# useTty = True,
					softfail = True,
					stdin = None)

			# FIXME: set RUNIN_VERBOSE

			self.node = node
			self.command = command
			self.iterations = int(iterations)

			if self.name:
				command.setenv("KEYVALUE", self.name)

			return True

		def execute(self):
			if self.iterations <= 0:
				return False

			self.command.setenv("ELAPSEDTIME", str(self.elapsed))

			self.iterations -= 1
			return self.node.run(self.command)

		def processStatus(self, st):
			if not st:
				self.success = False

			# FIXME: update elapsed

		def done(self):
			if self.iterations != 0:
				return False

			self.node = None
			return True

		def isRunning(self):
			return self.node is not None


	def __init__(self, name = "ctcs2"):
		global client, server, journal

		self.config = susetest.Config(name)
		self.journal = self.config.journal

		self.beginGroup("setup")
		self.sut = self.config.target("sut")
		self.logInfo("setup complete")
		self.finishGroup()

		self.defaultCommandTimeout = 60
		self.defaultCommandUser = 'root'

		self.script = None
		self.notifyTimer = None
		self.timer = None
		self.running = {}
		self.tests = {}

	def __del__(self):
		self.journal.writeReport()

	def beginGroup(self, tag):
		self.journal.beginGroup(tag);

	def finishGroup(self):
		self.journal.finishGroup();

	def logFailure(self, msg):
		self.journal.failure(msg)

	def logInfo(self, msg):
		self.journal.info(msg)

	def note(self, msg):
		self.logInfo(msg)

	def parse(self, filename):
		s = Script(self.sut)

		parser = CTCS.Parser(filename)
		while True:
			parsedCmd = parser.nextCommand()
			if not parsedCmd:
				break

			s.addCommand(parsedCmd)

		return s

	def run(self, script):
		self.script = script
		while True:
			cmd = script.nextCommand()

			if cmd is None:
				self.cleanup()
				break

			# When the timer expired, skip over all commands
			# all the way to the next 'wait' or 'cleanup'
			if self.timer and self.timer.state == 'expired':
				cmdType = type(cmd)
				if cmdType != CTCS.CleanupCommand and \
				   cmdType != CTCS.WaitCommand:
					msg = cmd.skip();
					if msg:
						self.note("Skipping %s" % msg)
					continue

			cmd.execute(self)

		self.cleanup()
		self.script = None

	def setTimer(self, timeout):
		self.stopTimer();
		self.timer = twopence.Timer(timeout, callback = self.timerExpired)

	def timerExpired(self):
		self.note("Timer expired; canceling all pending commands")
		self.sut.cancel_transactions()

	def stopTimer(self):
		if self.timer:
			self.timer.cancel()
			self.timer = None

	def armNotify(self, timeout, callback):
		self.stopNotify()
		self.notifyTimer = twopence.Timer(timeout, callback = callback)

	def stopNotify(self):
		if self.notifyTimer:
			self.notifyTimer.cancel()
			self.notifyTimer = None

	def testCondition(self, cmd):
		cmd = twopence.Command(cmd, background = False, stdin = None, softfail = True)

		cmd.timeout = self.defaultCommandTimeout
		cmd.user = self.defaultCommandUser
		# cmd.useTty = True

		return self.sut.run(cmd)

	def getTestCase(self, name):
		if self.tests.has_key(name):
			tc = self.tests[name]
		else:
			tc = CTCS.TestCase(name, user = self.defaultCommandUser, timeout = self.defaultCommandTimeout)
			self.tests[name] = tc

		return tc;

	def runTestCase(self, tc):
		cmd = tc.command
		self.running[cmd] = tc
		if not cmd.background:
			while not tc.done():
				st = tc.execute()
				self.commandExited(st, cmd)

			del self.running[cmd]
			return st
		else:
			tc.execute()

			# The command was backgrounded
			return cmd

	def wait(self):
		while True:
			status = self.sut.wait()
			if status is None:
				break

			cmd = status.cmd
			self.commandExited(status, cmd)

			if not self.running.has_key(cmd):
				self.error("Reaped a command we were not waiting for (%s)" % cmd.cmdline)
			elif not cmd.background:
				self.error("Reaped a foreground command (%s)" % cmd.cmdline)
			else:
				if not tc.done():
					# Another day, another iteration
					tc.execute()
				else:
					del self.running[cmd]

		self.stopNotify()
		self.stopTimer();

		if self.running.keys():
			print "Remaining tests"
			for tc in self.running.values():
				print "  ", tc.name

			fatal_internal_bug()

	def commandExited(self, status, cmd):
		self.note("Command \"%s\" exited with status %u (%s)" % (cmd.commandline, status.code, status.message))

		self.running[cmd].processStatus(status)

	def goto(self, cmd):
		self.script.goto(cmd)

	def cleanup(self):
		self.stopNotify()
		self.stopTimer();

		for tc in self.running.values():
			print "testcase %s still running" % (tc.name)
			tc.command.interrupt()

		self.wait()

	def beginTest(self, tag, msg):
		self.journal.beginTest(tag, msg)

	def skipTest(self, tag, msg):
		self.journal.beginTest(tag, msg)
		self.journal.skipped()

class Script:
	def __init__(self, node):
		self.node = node
		self._commands = []
		self._current = None
		self._pc = 0

	def addCommand(self, cmd):
		self._commands.append(cmd)

	def error(self, msg):
		if self._current:
			where = self._current.location
		else:
			where = "<somewhere>"

		raise exceptions.ValueError("%s: %s" % (where, msg))

	def nextCommand(self):
		if self._pc >= len(self._commands):
			return None

		self._current = self._commands[self._pc]
		self._pc += 1

		return self._current

	def goto(self, cmd):
		newPC = self._commands.find(cmd)
		if newPC < 0:
			self.error("goto() with invalid destination (%s)" % (cmd.location))

		self._pc = newPC

def create_argparser():
	import argparse

	parser = argparse.ArgumentParser(description='Run a ctcs2 test script')
	parser.add_argument('testfile', nargs='?',
			    help = 'specify the file containing the test script')
	parser.add_argument('--debug', action = 'count',
			    help = 'enable debug messages')
	parser.add_argument('--command-user',
			    help = 'default user for running commands')
	parser.add_argument('--command-timeout',
			    help = 'default timeout for running commands')
	return parser

args = create_argparser().parse_args()

if args.debug:
	twopence.setDebugLevel(args.debug)

ctcs = CTCS()

if args.command_user:
	ctcs.defaultCommandUser = args.command_user
if args.command_timeout:
	ctcs.defaultCommandTimeout = args.command_timeout

s = ctcs.parse(args.testfile)
ctcs.run(s)
