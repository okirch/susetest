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
}
td.caption {
  font-size: larger;
  font-weight: bold;
}
p.success { color: blue; }
p.error { color: red; }
p.failure { color: red; }
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
			if self.hrefMap is not None:
				if colName:
					refId = f"{colName}:{rowName}"
				else:
					refId = rowName

				href = self.hrefMap.get(refId)
				if href is not None:
					cell = f"<a href=\"{href}\">{cell}</a>"

			if value in ('success', 'failure', 'error'):
				cell = f"<p class='{value}'>{cell}</p>"

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

		print(html_preamble)
		print(f"<h1>Test Results</h1>")
		for group in log.groups:
			if not group.tests:
				continue

			self.renderGroupInfo(group)
			for test in group.tests:
				self.renderTest(test)
		print(html_trailer)

	def renderGroupInfo(self, group):
		print = self.print

		print(f"<h2>Test Group {group.stats.package}</h2>")
		print("<table>")

		print(f"<tr><td colspan='2'>Statistics</td></tr>")
		print(f"<tr><td>Tests run</td><td>{group.stats.tests}</td></tr>")
		print(f"<tr><td>  failures</td><td>{group.stats.failures}</td></tr>")
		print(f"<tr><td>  skipped</td><td>{group.stats.skipped}</td></tr>")
		print(f"<tr><td>  errors</td><td>{group.stats.errors}</td></tr>")
		print(f"<tr><td>  disabled</td><td>{group.stats.disabled}</td></tr>")

		if group.properties:
			print(f"<tr><td colspan='2'>Properties</td></tr>")
			for key, value in group.properties.items():
				print(f"<tr><td>{key}</td><td>{value}</td></tr>")

		print("</table>")

	def renderTest(self, test):
		print = self.print

		time = float(test.time)
		if time < 0.01:
			time = "%.2f ms" % (time * 1000)
		else:
			time = "%.2f s" % time

		print(f"<h3 id='{test.classname}'>Test: {test.description}</h3>")
		print("<table>")
		print(f"<tr><td>Status</td><td><p class='{test.status}'>{test.status}</p></td></tr>")
		print(f"<tr><td>Duration</td><td>{time}</td></tr>")
		print("</table>")

		if test.systemOut:
			print("<p>")
			print("Output:")
			print("<pre>")
			print(test.systemOut)
			print("</pre>")
