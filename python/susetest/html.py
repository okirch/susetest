##################################################################
#
# Render test reports and accumulated results as HTML.
#
# Copyright (C) 2022 SUSE Linux GmbH
#
##################################################################

from .logger import *
from .results import Renderer, ResultsMatrix

html_preamble = '''
<html>
<style>
table, th, td {
  border: 1px solid;
}
table.params {
  width: 30em;
}
th, td {
  padding: 2px;
  padding-left: 4px;
  padding-right: 4px;
  vertical-align: top;
}
td.caption {
  font-size: larger;
  font-weight: bold;
}
font.success { color: blue; }
font.error { color: red; }
font.failure { color: red; }
font.warning { color: red; }
tr:hover {background-color: lightgreen;}
</style>

<body>
'''

html_trailer = '''
</body>
</html>
'''

class HTMLRenderer(Renderer):
	canRenderTestReports = True

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		self.lastCommand = None
		self.t0 = None

	def renderResults(self, results, filter = None, referenceMap = None):
		if self.output_directory:
			self.open("index.html")

		print = self.print
		print(html_preamble)

		print("<h1>Test Run Summary</h1>")
		if results.invocation:
			print(f"Invocation: <code>{results.invocation}</code><p>")

		if filter:
			print("Results subject to filtering. Only (partial) failures are displayed.")

		if isinstance(results, ResultsMatrix):
			values = results.asMatrixOfValues(filter)
			self.renderMatrix(values, results.parameterMatrix(), referenceMap)
		else:
			vector = results.asVectorOfValues(filter)
			self.renderVector(vector, referenceMap)

		self.print(html_trailer)

	class CellStatusRenderer:
		def __init__(self, hrefMap):
			self.hrefMap = hrefMap

		def render(self, value, rowName, colName = None):
			cell = value

			if value in ('success', 'warning', 'failure', 'error'):
				cell = f"<font class='{value}'>{cell}</font>"

			if self.hrefMap is not None:
				if colName:
					refId = f"{colName}:{rowName}"
				else:
					refId = rowName

				href = self.hrefMap.get(refId)
				if href is not None:
					cell = f"<a href=\"{href}\">{cell}</a>"

			return cell

	def renderMatrix(self, matrix, parameters, referenceMap):
		print = self.print

		print("<h2>Table of test results</h2>")
		# print("<center>")
		print("<table>")

		print(" <th>")
		for name in matrix.columns:
			print(f"  <td><a href='#col:{name}'>{name}</td>")
		print(" </th>")

		numColumns = 1 + len(matrix.columns)
		cellRenderer = self.CellStatusRenderer(referenceMap)

		currentTestName = None
		for rowName in matrix.rows:
			testName = rowName.split('.')[0]
			if testName != currentTestName:
				currentTestName = testName
				print(" <tr>")
				print(f"  <td colspan={numColumns} class='caption'>{testName}</td>")
				print(" </tr>")

			print(" <tr>")
			desc = self.describeRow(matrix, rowName)
			print(f"  <td>{desc}</td>")
			for colName in matrix.columns:
				cell = cellRenderer.render(matrix.get(rowName, colName), rowName, colName)
				print(f"  <td>{cell}</td>")
			print(" </tr>")

		print("</table>")
		# print("</center>")

		for matrixColumn in parameters.columns:
			print(f"<h2 id='col:{matrixColumn}'>Matrix parameters for column {matrixColumn}</h2>")

			print("<table class='params'>")
			print(f" <tr><th width='50%'>Parameter</td><td>Value</td></tr>")
			for paramName in parameters.rows:
				value = parameters.get(paramName, matrixColumn)
				print(f" <tr><td>{paramName}</td><td>{value}</td></tr>")
			print("</table>")

	def renderVector(self, vector, referenceMap):
		print = self.print

		print("<center><table>")

		cellRenderer = self.CellStatusRenderer(referenceMap)
		currentTestName = None
		for rowName in vector.rows:
			testName = rowName.split('.')[0]
			if testName != currentTestName:
				currentTestName = testName
				print(" <tr>")
				print(f"  <td colspan=2 class='caption'>{testName}</td>")
				print(" </tr>")

			cell = cellRenderer.render(vector.get(rowName), rowName)
			description = self.describeRow(vector, rowName)

			print(f"  <tr><td>{description}</td><td>{cell}</td>")
		print("</table></center>")

	def describeRow(self, matrix, id):
		description = matrix.getRowInfo(id)
		if description is None:
			if '__resources__.resource-acquire:' in id:
				# ids for resource mgmt look like this:
				# traceroute.__resources__.resource-acquire:client:optional:executable:traceroute
				words = id.split()[1:]
				if words[0] == "None":
					words.pop(0)
				description = " ".join(words)
			else:
				description = id
		return description

	##########################################################
	# Render junit test report as HTML
	##########################################################
	def renderTestReport(self, log):
		print = self.print

		self.lastCommand = None
		self.t0 = None

		print(html_preamble)
		print(f"<h1>Test Results</h1>")

		self.renderMetadata(log.stats, log.properties)

		for group in log.groups:
			if not group.tests:
				continue

			self.renderGroupInfo(group)
			for test in group.tests:
				self.renderTest(test)
		print(html_trailer)

	def renderGroupInfo(self, group):
		print = self.print

		print(f"<h2>Test Group {group.id}</h2>")
		self.renderMetadata(group.stats, group.properties)

	def renderMetadata(self, stats, properties):
		print = self.print

		print("<table>")

		print(f"<tr><td colspan='2'>Statistics</td></tr>")
		print(f"<tr><td>Tests run</td><td>{stats.tests}</td></tr>")
		print(f"<tr><td>  warnings</td><td>{stats.warnings or 0}</td></tr>")
		print(f"<tr><td>  failures</td><td>{stats.failures}</td></tr>")
		print(f"<tr><td>  skipped</td><td>{stats.skipped}</td></tr>")
		print(f"<tr><td>  errors</td><td>{stats.errors}</td></tr>")
		print(f"<tr><td>  disabled</td><td>{stats.disabled}</td></tr>")

		if properties:
			print(f"<tr><td colspan='2'>Properties</td></tr>")
			for key, value in properties.items():
				print(f"<tr><td>{key}</td><td>{value}</td></tr>")

		print("</table>")

	_print = print

	def renderTest(self, test):
		print = self.print

		time = float(test.time)
		if time < 0.01:
			time = "%.2f ms" % (time * 1000)
		else:
			time = "%.2f s" % time

		print(f"<h3 id='{test.id}'>Test: {test.description}</h3>")
		print("<table>")
		print(f"<tr><td colspan='3' class='caption'>Stats</td></tr>")
		print(f"<tr><td colspan='2'>Status</td><td><p class='{test.status}'>{test.status}</p></td></tr>")
		print(f"<tr><td colspan='2'>Duration</td><td>{time}</td></tr>")

		if test.log.events:
			print(f"<tr><td colspan='3' class='caption'>Event log</td></tr>")
		for event in test.log.events:
			if self.t0 is None:
				self.t0 = event.timestamp

			rts = event.timestamp - self.t0
			frac = ("%.2f" % (rts % 1)).lstrip("0")
			self.timestamp = "%02d:%02d%s" % (int(rts / 60), rts % 60, frac)

			eventType = event.eventType
			if eventType in ("info", "error", "failure", "warning"):
				self.renderMessageEvent(event)
			elif eventType == "download" or eventType == "upload":
				self.renderTransfer(event)
			elif eventType == "command":
				self.renderCommandEvent(event)
			else:
				self.renderUnknownEvent(event)
		print("</table>")

	def renderMessageEvent(self, event):
		self.renderLine(event.eventType, f"<pre>{event.text}</pre>")

	def renderCommandEvent(self, event):
		if not event.cmdline:
			# Instead of this silly href business, we could also highlight related command
			# pieces on mouse-over. Later... much much later.
			if self.lastCommand != event.id:
				self.renderLine("command",
					f"<a href='#bgnd:{event.id}'><pre>Continuation from backgrounded command</pre></a>")

			self.renderCommandParts(event)
			return

		parts = [f"{event.host}: {event.cmdline}"]
		if event.user:
			parts.append(f"user={event.user}")
		if event.timeout:
			parts.append(f"timeout={event.timeout}")

		text = "; ".join(parts)

		text = f"<pre>{text}</pre>"

		if event.id:
			text = f"<a id='bgnd:{event.id}'>{text}</a>"

		self.renderLine("command", text)
		if event.id:
			self.renderExtraMessages("command", ["(Command was backgrounded)"])
		else:
			self.renderCommandParts(event)

		self.lastCommand = event.id

	def renderCommandParts(self, event):
		if event.status:
			# For simplicity's sake, do not display anything if a foreground command exited w/ 0
			if event.id or event.status.exit_code != 0:
				self.renderCommandStatus(event.status)

		if event.chat:
			self.renderChatInfo(event.chat)

		if event.stdout:
			self.renderLine("stdout", f"<pre>{event.stdout.text}</pre>")
		if event.stderr:
			self.renderLine("stderr", f"<pre>{event.stderr.text}</pre>")

	def renderChatInfo(self, chat):
		if chat.sent:
			self.renderLine("chat", f"<pre>Sent: {chat.sent.text}</pre>")

		received = None
		if chat.received:
			received = chat.received.text

		if not (len(chat.expect) == 1 and chat.expect[0].string == received):
			for expect in chat.expect:
				self.renderLine("chat", f"<pre>Expected: {expect.string}</pre>")
		if received:
			self.renderLine("chat", f"<pre>Received: {received}</pre>")

	def renderCommandStatus(self, status):
		messages = []
		if status.message:
			messages.append(status.message)
		if status.exit_code is not None:
			messages.append(f"exit code: {status.exit_code}")
		if status.exit_signal is not None:
			messages.append(f"killed by signal {status.exit_signal}")
		self.renderExtraMessages("exit", messages)

	def renderTransfer(self, event):
		parts = [f"{event.host}: {event.eventType}ing {event.path}"]
		if event.user:
			parts.append(f"user={event.user}")
		if event.timeout:
			parts.append(f"timeout={event.timeout}")
		if event.permissions:
			parts.append(f"permissions={event.permissions}")

		text = "; ".join(parts)
		text = f"<pre>{text}</pre>"
		self.renderLine(event.eventType, text)

		if event.eventType == "upload" and event.data:
			self.renderLine("data", f"<pre>{event.data.text}</pre>")

		if event.error:
			self.renderLine("error",
				f"Transfer failed: {event.error.type} {event.error.message}")
		elif event.eventType == "download" and event.data:
			self.renderLine("data", f"<pre>{event.data.text}</pre>")

	def renderUnknownEvent(self, event):
		self.renderLine(event.eventType)

	def renderExtraMessages(self, type, messages):
		for msg in messages:
			self.renderLine(type, f"<pre>{msg}</pre>")

	def renderLine(self, *args):
		args = [self.timestamp] + list(args)
		self.timestamp = ""

		cells = list(map(lambda s: f"<td>{s}</td>", args))
		if len(cells) < 3:
			span = 4 - len(cells)
			cells[-1] = f"<td colspan='{span}'>{args[-1]}</td>"
		self.print("<tr>" + "".join(cells) + "</tr>")
