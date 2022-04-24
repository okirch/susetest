##################################################################
#
# Render test reports and accumulated results as HTML.
#
# Copyright (C) 2022 SUSE Linux GmbH
#
##################################################################

import os
import twopence
from .logger import *
from .results import Results, Renderer, ResultsMatrix

html_preamble = '''
<html>
<style>
table, th, td {
  border: 1px solid;
}
table {
  width: 62em;
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
font.improvement { color: green; }
font.regression { color: red; }
tr:hover {background-color: lightgreen;}
</style>

<script>
const showAllNames = ["imadoofus"]
const hideSuccessNames = ["skipped", "disabled", "success"]
const hideWarningNames = ["skipped", "disabled", "success", "warning"]
const onlyImprovements = ["unchanged", "regression"]
const onlyRegressions = ["unchanged", "improvement"]

function showAllRows() {
  hideRowsWithClassname(showAllNames);
}

function hideRowsWithClassname(names) {
  tables = document.getElementsByClassName("results-table");
  for (let table of tables) {
    var rowList = table.getElementsByTagName("tr");
    for (let row of rowList) {
      if (names.includes(row.className)) {
        row.style.display = "none";
      } else {
        row.style.display = "table-row";
      }
    }
  }
}

</script>

<body>
'''

html_results_radiobuttons = '''

<fieldset style="width: 60em">
<legend>Table filter</legend>
<input type='radio' id='all' name='row-filter' onclick='hideRowsWithClassname(showAllNames)' checked="checked">
 <label for='all'>Show all rows</label><br>
<input type='radio' id='success' name='row-filter' onclick='hideRowsWithClassname(hideSuccessNames)'>
 <label for='success'>Hide success rows</label><br>
<input type='radio' id='success' name='row-filter' onclick='hideRowsWithClassname(hideWarningNames)'>
 <label for='success'>Hide success/warning rows</label>
</input>
</fieldset>
<p>

'''

html_regression_radiobuttons = '''

<fieldset style="width: 60em">
<legend>Table filter</legend>
<input type='radio' id='all' name='row-filter' onclick='hideRowsWithClassname(showAllNames)' checked="checked">
 <label for='all'>Show all rows</label><br>
<input type='radio' id='success' name='row-filter' onclick='hideRowsWithClassname(onlyRegressions)'>
 <label for='success'>Show regressions</label><br>
<input type='radio' id='success' name='row-filter' onclick='hideRowsWithClassname(onlyImprovements)'>
 <label for='success'>Show improvements only</label>
</input>
</fieldset>
<p>

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
		self.hrefs = HTMLReferenceMap()

	def renderTestrun(self, testrun):
		for log, columnName in testrun.reports:
			self.renderTestReport(log, column = columnName)

		super().renderTestrun(testrun)

	def renderResults(self, results):
		if self.output_directory:
			self.open("index.html")

		print = self.print
		print(html_preamble)

		print("<h1>Test Run Summary</h1>")
		self.renderResultsMeta(results)

		if isinstance(results, ResultsMatrix):
			values = results.asMatrixOfValues()
			self.renderMatrix(values, results.parameterMatrix())
		else:
			vector = results.asVectorOfValues()
			self.renderVector(vector)

		self.print(html_trailer)

	def renderResultsMeta(self, results):
		print = self.print

		if results.invocation:
			print(f"Invocation: <code>{results.invocation}</code><p>")

		print()
		if results.roles:
			print("<p><table>")
			for role in results.roles:
				print(f"<tr><td colspan='2'>Settings for role {role.name}</td></tr>")
				for label, value in self.renderRoleAttributes(role):
					print(f"<tr><td>&nbsp;{label}</td><td>{value}</td></tr>")
			print("</table><p>")
			print()

	roleAttrs = (
		("os",			"OS"),
		("vendor",		"OS Vendor"),
		("platform",		"Platform ID"),
		("build_timestamp",	"Build time of derived image"),
		("base_platform",	"Base Platform ID"),
		("base_image",		"Base Platform Image"),
	)

	def renderRoleAttributes(self, role):
		result = []
		for attr_name, label in self.roleAttrs:
			value = getattr(role, attr_name, None)
			if value is not None:
				result.append((label, value))
		return result

	def renderMatrix(self, matrix, parameters):
		print = self.print

		print("<h2>Table of test results</h2>")
		print(html_results_radiobuttons)

		matrixDecorator = MatrixDecorator(matrix, self.hrefs)
		HTMLMatrixRenderer(self).render(matrixDecorator, tableClass = 'results-table')

		for colKey in parameters.columns:
			print(f"<h2 id='col:{colKey.id}'>Matrix parameters for column {colKey.label}</h2>")

			print("<table class='params'>")
			print(f" <tr><th width='50%'>Parameter</td><td>Value</td></tr>")
			for rowKey in parameters.rows:
				value = parameters.get(rowKey, colKey)
				print(f" <tr><td>{rowKey.label}</td><td>{value}</td></tr>")
			print("</table>")

	def renderRegressionMatrix(self, matrix):
		print = self.print

		print("<h2>Table of test regressions</h2>")
		print(html_regression_radiobuttons)

		matrixDecorator = RegressionMatrixDecorator(matrix)
		HTMLMatrixRenderer(self).render(matrixDecorator, tableClass = 'results-table')

	def renderVector(self, vector):
		print = self.print

		print("<h2>Test results</h2>")
		print(html_results_radiobuttons)

		vectorDecorator = VectorDecorator(vector, self.hrefs)
		HTMLVectorRenderer(self).render(vectorDecorator, tableClass = 'results-table')

	##########################################################
	# Render a regression analysis
	##########################################################
	def renderRegression(self, analysis):
		baselineTag = analysis.baselineTag

		htmlFilename = f"regress-{baselineTag}.html"
		self.open(htmlFilename)

		print = self.print

		print(html_preamble)
		print(f"<h1>Regression report vs {baselineTag}</h1>")

		print("<h2>Baseline metadata</h2>")
		self.renderResultsMeta(analysis.baseline)

		print("<h2>Test run metadata</h2>")
		self.renderResultsMeta(analysis.testrun)

		if analysis.documentType == "matrix":
			values = analysis.asMatrixOfValues()
			self.renderRegressionMatrix(values)
		else:
			raise NotImplementedError()

		print(html_trailer)

	##########################################################
	# Render junit test report as HTML
	##########################################################
	def renderTestReport(self, log, column = None):
		htmlFilename = f"{log.name}.html"
		if column:
			outPath = os.path.join(column, htmlFilename)
		else:
			outPath = htmlFilename
		self.open(outPath)

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
				self.hrefs.add(column, test.id, f"{outPath}#{test.id}")

		print(html_trailer)
		return outPath

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
		# FIXME: look for test.error or test.failure, which should contain a message and a type attribute
		print(f"<tr><td colspan='2'>Duration</td><td>{time}</td></tr>")

		if test.log is None:
			print("<p>No events recorded for this test</p>")
			return

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

class HTMLMatrixRenderer:
	def __init__(self, renderer):
		self.hrefs = renderer.hrefs
		self.print = renderer.print

	def render(self, matrix, tableClass = None):
		print = self.print

		if tableClass:
			print(f"<table class='{tableClass}'>")
		else:
			print("<table>")

		print(" <th>")
		for colKey in matrix.columns:
			print(f"  <td><a href='#col:{colKey.label}'>{colKey.label}</td>")
		print(" </th>")

		numColumns = 1 + matrix.columnCount

		currentTestName = None
		for rowKey in matrix.rows:
			testName = rowKey.id.split('.')[0]
			if testName != currentTestName:
				currentTestName = testName
				print(" <tr>")
				print(f"  <td colspan={numColumns} class='caption'>{testName}</td>")
				print(" </tr>")

			className = matrix.getTableRowClass(rowKey)

			print(f" <tr class='{className}'>")
			print(f"  <td>{rowKey.label}</td>")
			for colKey in matrix.columns:
				cell = matrix.getTableCell(rowKey, colKey)
				print(f"  <td>{cell}</td>")
			print(" </tr>")

		print("</table>")

class HTMLVectorRenderer:
	def __init__(self, renderer):
		self.hrefs = renderer.hrefs
		self.print = renderer.print

	def render(self, vector, tableClass = None):
		print = self.print

		if tableClass:
			print(f"<table class='{tableClass}'>")
		else:
			print("<table>")

		currentTestName = None
		for rowKey in vector.rows:
			testName = rowKey.id.split('.')[0]
			if testName != currentTestName:
				currentTestName = testName
				print(" <tr>")
				print(f"  <td colspan=2 class='caption'>{testName}</td>")
				print(" </tr>")

			status = vector.get(rowKey)
			cell = vector.getTableCell(rowKey)

			print(f"  <tr class='{status}'><td>{rowKey.label}</td><td>{cell}</td>")
		print("</table>")

class Decorator:
	def decorateStatus(self, value, tendency = None):
		cell = value or "(not run)"
		if value in ('success', 'warning', 'failure', 'error'):
			cell = f"<font class='{value}'>{cell}</font>"

		if tendency == "regression":
			cell += "<font class='regression'>&#x25BC;</font>"
		elif tendency == "improvement":
			cell += "<font class='improvement'>&#x25B2;</font>"

		return cell

class VectorDecorator(Decorator):
	def __init__(self, values, hrefs = None):
		self.values = values
		self.hrefs = hrefs

	@property
	def rows(self):
		return self.values.rows

	def getTableCell(self, rowKey):
		cell = self.decorateStatus(self.values.get(rowKey))

		if self.hrefs is not None:
			href = self.hrefs.get(None, rowKey.id)
			if href is not None:
				cell = f"<a href=\"{href}\">{cell}</a>"

		return cell

	def getRowDescription(self, id):
		return self.values.getRowInfo(id)

class MatrixDecorator(Decorator):
	def __init__(self, values, hrefs = None):
		self.values = values
		self.hrefs = hrefs

	@property
	def rows(self):
		return self.values.rows

	@property
	def columns(self):
		return self.values.columns

	@property
	def rowCount(self):
		return self.values.rowCount

	@property
	def columnCount(self):
		return self.values.columnCount

	def getTableCell(self, rowKey, colKey):
		cell = self.decorateStatus(self.values.get(rowKey, colKey))

		if self.hrefs is not None:
			href = self.hrefs.get(colKey.id, rowKey.id)
			if href is not None:
				cell = f"<a href=\"{href}\">{cell}</a>"

		return cell

	def getRowDescription(self, id):
		return self.values.getRowInfo(id)

	def getTableRowClass(self, rowKey):
		matrix = self.values
		return Results.filterMostSignficantStatus(matrix.get(rowKey, colKey) for colKey in matrix.columns)

class RegressionMatrixDecorator(MatrixDecorator):
	def getTableCell(self, rowKey, colKey):
		test = self.values.get(rowKey, colKey)
		assert(test)

		if test is not None:
			cell = self.decorateStatus(test.status, test.verdict)
		else:
			cell = self.decorateStatus("(not run)")

		if self.hrefs is not None:
			href = self.hrefs.get(colKey.id, rowKey.id)
			if href is not None:
				cell = f"<a href=\"{href}\">{cell}</a>"

		return cell

	def getRowDescription(self, id):
		return self.values.getRowInfo(id)

	def getTableRowClass(self, rowKey):
		rowVerdict = "unchanged"
		for colKey in self.values.columns:
			test = self.values.get(rowKey, colKey)
			verdict = test.verdict
			if verdict == "regression":
				return verdict
			if verdict == "improvement":
				rowVerdict = verdict

		return rowVerdict

class HTMLReferenceMap:
	def __init__(self):
		self.hrefMap = {}

	def makeId(self, colName, testId):
		if colName:
			return f"{colName}:{testId}"
		return testId

	def add(self, colName, testId, target):
		hrefId = self.makeId(colName, testId)
		self.hrefMap[hrefId] = target

	def get(self, colName, testId):
		hrefId = self.makeId(colName, testId)
		return self.hrefMap.get(hrefId)

