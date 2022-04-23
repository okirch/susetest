#!/usr/bin/python3
##################################################################
#
# Aggregate results from different test runs into a single
# results vector/matrix.
#
# Copyright (C) 2022 SUSE Linux GmbH
#
##################################################################

import twopence
import argparse
import os
import curly

from .logger import LogParser
from .logger import loadResultsDocument, createResultsDocument

class Results:
	validStatesOrdered = ('success', 'warning', 'failure', 'error', 'skipped', 'disabled')

	@classmethod
	def statusToSeverity(klass, status):
		try:
			return klass.validStatesOrdered.index(status)
		except:
			return None

	@classmethod
	def filterMostSignficantStatus(klass, states):
		className = None
		classPrio = -1

		for state in states:
			prio = klass.statusToSeverity(state)
			if prio is None:
				return state
			if prio > classPrio:
				className = state
				classPrio = prio

		return className or "success"

class ResultsRole:
	attrs = (
		'os',
		'vendor',
		'platform',
		'application',
		'base_platform',
		'base_image',
		'build_timestamp',
	)

	def __init__(self, name):
		self.name = name

		for attr_name in self.attrs:
			setattr(self, attr_name, None)

	def serialize(self, writer):
		for attr_name in self.attrs:
			value = getattr(self, attr_name, None)
			if value is not None:
				setattr(writer, attr_name, value)

	def deserialize(self, reader):
		for attr_name in self.attrs:
			value = getattr(reader, attr_name, None)
			if value is not None:
				setattr(self, attr_name, value)

class ResultsCollection:
	def __init__(self, name = None):
		self._name = name
		self._path = None
		self.invocation = None
		self._roles = {}

	def attachToLogspace(self, logspace, clobber = False):
		path = os.path.join(logspace, "results.xml")
		if not clobber and os.path.exists(path):
			raise ValueError(f"Refusing to overwrite existing {path}")

		self._path = path

	@property
	def roles(self):
		return self._roles.values()

	def addRole(self, name):
		role = ResultsRole(name)
		self._roles[name] = role
		return role

	def save(self):
		if not self._path:
			raise ValueError("Cannot save results; path not set")

		writer = createResultsDocument(self.documentType)
		self.serialize(writer)
		writer.save(self._path)

		twopence.info(f"Updated {self._path}")

	def serialize(self, writer):
		if self.invocation:
			writer.setInvocation(self.invocation)

		for role in self._roles.values():
			role.serialize(writer.createRole(role.name))

	def deserialize(self, reader):
		self.invocation = reader.invocation

		for roleInfo in reader.roles:
			role = self.addRole(roleInfo.name)
			role.deserialize(roleInfo)

class ResultsVector(ResultsCollection):
	documentType = "vector"

	class TestResult:
		def __init__(self, id, status, description):
			self.id = id
			self.status = status
			self.description = description

	def __init__(self, name = None):
		super().__init__(name)
		self._parameters = {}
		self._results = []

	@property
	def name(self):
		return self._name

	@property
	def parameters(self):
		return self._parameters

	@property
	def results(self):
		return self._results

	def __str__(self):
		return f"{self.__class__.__name__}({self.name})"

	def serialize(self, writer):
		super().serialize(writer)
		writer.addParameters(self._parameters)
		writer.addResults(self.results)

	def deserialize(self, reader):
		self._name = reader.name
		super().deserialize(reader)
		self._parameters = reader.parameters

		for res in reader.results:
			self.add(id = res.id, status = res.status, description = res.description)

	def setParameter(self, key, value):
		self._parameters[key] = value

	def updateParameters(self, parameters):
		self._parameters.update(parameters)

	def add(self, *args, **kwargs):
		result = self.TestResult(*args, **kwargs)
		self._results.append(result)

	def asVectorOfValues(self):
		vector = VectorOfValues(default_value = "(not run)")
		for test in self.results:
			vector.set(test.id, test.status)
			vector.setRowInfo(test.id, test.description)

		return vector

class ResultsMatrix(ResultsCollection):
	documentType = "matrix"

	def __init__(self, name = None):
		super().__init__(name)
		self._columns = []

	@property
	def columns(self):
		return self._columns

	def serialize(self, writer):
		writer.name = self._name
		super().serialize(writer)
		for column in self._columns:
			column.serialize(writer.createColumn(column.name))

	def deserialize(self, reader):
		self._name = reader.name
		super().deserialize(reader)
		for columnReader in reader.columns:
			col = self._createColumn(columnReader.name)
			col.deserialize(columnReader)

	def createColumn(self, name, parameters = []):
		column = self._createColumn(name)

		for kvpair in parameters:
			if "=" not in kvpair:
				raise ValueError(f"Invalid parameter settings {kvpair}")
			key, value = kvpair.split("=", maxsplit = 1)
			column.setParameter(key, value)

		twopence.info(f"Created results vector for matrix column {name}")
		return column

	def _createColumn(self, name = None):
		for column in self._columns:
			if column.name == name:
				return column

		column = ResultsVector(name)
		self._columns.append(column)
		return column

	def asMatrixOfValues(self):
		matrix = MatrixOfValues([c.name for c in self._columns], default_value = "(not run)")
		for column in self._columns:
			for test in column.results:
				matrix.set(test.id, column.name, test.status)
				matrix.setRowInfo(test.id, test.description)

		return matrix

	def parameterMatrix(self):
		matrix = MatrixOfValues([c.name for c in self._columns], default_value = "(not set)")
		for column in self._columns:
			pd = column.parameters
			for name, value in pd.items():
				matrix.set(name, column.name, value)
		return matrix

class VectorOfValues:
	def __init__(self, default_value = "-"):
		self._values = {}
		self._rowNames = []
		self._rowInfo = {}
		self._default_value = default_value

	def set(self, row, value):
		self._values[row] = value
		self._rowNames.append(row)

	def get(self, row):
		return self._values.get(row) or self._default_value

	def setRowInfo(self, row, info):
		self._rowInfo[row] = info

	def getRowInfo(self, row):
		return self._rowInfo.get(row) or "-"

	@property
	def rows(self):
		return self._rowNames

class MatrixOfValues:
	def __init__(self, columnNames = [], default_value = "-"):
		self._values = {}
		self._columnNames = columnNames or []
		self._rowNames = []
		self._rowInfo = {}
		self._default_value = default_value

	def set(self, row, col, value):
		self._values[f"{row},{col}"] = value
		if col not in self._columnNames:
			self._columnNames.append(col)
		if row not in self._rowNames:
			self._rowNames.append(row)

	def get(self, row, col):
		return self._values.get(f"{row},{col}") or self._default_value

	def setRowInfo(self, row, info):
		self._rowInfo[row] = info

	def getRowInfo(self, row):
		return self._rowInfo.get(row) or "-"

	def getRow(self, row):
		return (self.get(row, col) for col in self.columns)

	def getColumn(self, col):
		return (self.get(row, col) for row in self.rows)

	@property
	def rows(self):
		return self._rowNames

	@property
	def columns(self):
		return self._columnNames

	@property
	def firstColumn(self):
		return self._columnNames[0]

	def uniformStatus(self):
		values = set()
		for row in self.rows:
			for col in self.columns:
				values.add(self.get(row, col))
		return len(values) == 1

	def rowHasUniformValue(self, row, value):
		return all((self.get(row, col) == value) for col in self.columns)

class Renderer:
	def __init__(self, output_directory = None):
		self.output_directory = output_directory
		self.print = print

	def renderTestrun(self, testrun):
		self.renderResults(testrun.results)

	def open(self, filename):
		if self.output_directory is None:
			return False

		path = os.path.join(self.output_directory, filename)

		twopence.info(f"Writing {path}")
		dirname = os.path.dirname(path)
		if not os.path.isdir(dirname):
			os.makedirs(dirname, 0o755)

		destfile = open(path, "w")
		self.print = lambda msg = '', **kwargs: print(msg, file = destfile, **kwargs)

	def renderRegression(self, analysis):
		raise NotImplementedError("This output format cannot render regression reports")

	@staticmethod
	def factory(format, output_directory = None):
		if format == 'text':
			return TextRenderer(output_directory)
		elif format == 'html':
			from .html import HTMLRenderer

			return HTMLRenderer(output_directory)

		raise ValueError(f"Cannot create renderer for unknown format {format}")

class TextRenderer(Renderer):
	def renderResults(self, results):
		if isinstance(results, ResultsMatrix):
			values = results.asMatrixOfValues()
			self.renderMatrix(values, results.parameterMatrix())
		else:
			vector = results.asVectorOfValues()
			self.renderVector(vector)

	def renderMatrix(self, values, parameters):
		self.displayMatrix(values)

		self.print()
		self.print("Description of matrix columns:")
		self.displayMatrix(parameters)

		self.showTestLegend(values)
		self.print()

	def renderVector(self, vector):
		self.print()
		self.displayVector(vector)

	def showTestLegend(self, matrix):
		print = self.print

		print()
		print("Description of failed test(s):")
		for id in matrix.rows:
			description = matrix.getRowInfo(id)
			print(f"    {id:24} {description}")

	def displayMatrix(self, matrix):
		print = self.print
		empty = ""

		print()
		print(f"{empty:24}", end = "")
		for name in matrix.columns:
			print(f" {name:18}", end = "")
		print()

		for rowName in matrix.rows:
			if len(rowName) <= 24:
				print(f"{rowName:24}", end = "")
			else:
				print(f"{rowName}:")
				print(f"{empty:24}", end = "")
			for colName in matrix.columns:
				cell = matrix.get(rowName, colName)
				print(f" {cell:18}", end = "")
			print()

	def displayVector(self, vector):
		print = self.print
		for row in vector.rows:
			status = vector.get(row)
			description = vector.getRowInfo(row)

			print(f"    {row:32} {status:18} {description}")

class TestRunResults:
	def __init__(self, logspace, testrun):
		self.testrun = testrun
		self._results = None

		self.logspace = logspace
		if self.logspace is None:
			self.logspace = os.path.expanduser("~/susetest/logs")
		if testrun:
			self.logspace = os.path.join(self.logspace, testrun)

	@property
	def results(self):
		if self._results is None:
			path = os.path.join(self.logspace, "results.xml")
			if os.path.exists(path):
				self._results = self.loadResults(path)
			else:
				self._results = self.scanResults()

		return self._results

	@property
	def reports(self):
		results = self.results
		if isinstance(results, ResultsMatrix):
			for col in results.columns:
				path = os.path.join(self.logspace, results._name, col.name)
				for name, log in self.scanDirectory(path).items():
					yield log, col.name
		else:
			for name, log in self.scanDirectory(self.logspace).items():
				yield log, None

	def loadResults(self, path):
		twopence.info(f"Loading results from {path}")
		doc = loadResultsDocument(path)
		if doc is None:
			raise ValueError(f"Could not open {path}")

		if doc.type == "matrix":
			results = ResultsMatrix()
		else:
			results = ResultsVector()

		results.deserialize(doc)
		return results

	def scanResults(self):
		twopence.info("Scanning logspace")
		result = self.scanSuite()
		if result is None:
			result = self.scanMatrix()

		if result is None:
			raise ValueError(f"No test cases found in {self.logspace}")
		return result

	def scanSuite(self):
		testcases = self.scanDirectory(self.logspace)
		if not testcases:
			return

		vector = ResultsVector()
		for result in testcases.values():
			for group in result.groups:
				for test in group.tests:
					vector.add(test.id, test.status, test.description)
		return vector

	def scanMatrix(self):
		subdirs = []
		for de in os.scandir(self.logspace):
			if de.is_dir():
				subdirs.append(de)

		if len(subdirs) != 1:
			return

		de = subdirs[0]
		matrix = ResultsMatrix(de.name)

		path = de.path
		for de in os.scandir(path):
			if not de.is_dir():
				continue

			columnPath = de.path
			testcases = self.scanDirectory(de.path)
			if not testcases:
				continue

			column = matrix.createColumn(de.name)
			if matrix._name == 'selinux':
				column.setParameter('selinux-user', de.name)
			else:
				column.setParameter('value', de.name)

			for result in testcases.values():
				for group in result.groups:
					for test in group.tests:
						column.add(test.id, test.status, test.description)

		return matrix

	def scanDirectory(self, path):
		result = {}
		# print(f"scanDirectory({path})")
		for de in os.scandir(path):
			if not de.is_dir():
				# print(f"Ignoring {de.name} (not a directory)")
				continue

			reportPath = os.path.join(de.path, "junit-results.xml")
			if not os.path.isfile(reportPath):
				# print(f"Ignoring {de.path} (does not contain a test report)")
				continue

			result[de.name] = LogParser(reportPath)
		return result


class Processor:
	def __init__(self):
		parser = self.build_arg_parser()
		args = parser.parse_args()

		self.logspace = args.logspace

		output_directory = None
		if args.document_root:
			output_directory = os.path.join(args.document_root,
						args.testrun or "testrun")

		self.renderer = Renderer.factory(args.format, output_directory)

		# Process specific arguments
		self.process_args(args)

	def build_arg_parser(self):
		parser = self.create_arg_parser()

		# Add common options
		parser.add_argument('--logspace',
			help = 'The directory to use as logspace')
		parser.add_argument('--format', default = 'text',
			help = 'Select output format (text, html - default: text)')
		parser.add_argument('--document-root', metavar = 'PATH',
			help = 'Create output file(s) below the specified directory')
		return parser

	def checkRequiredArgument(self, option, value):
		if not value:
			twopence.error(f"Required argument {option} is missing")
			exit(1)

class Tabulator(Processor):
	def create_arg_parser(self):
		parser = argparse.ArgumentParser(description = 'Tabulate test results.')
		parser.add_argument('--testrun',
			help = 'Name of the test run')

		return parser

	def process_args(self, args):
		# self.checkRequiredArgument("--testrun", args.testrun)

		self.testrun = TestRunResults(self.logspace, args.testrun)

	def perform(self):
		self.renderer.renderTestrun(self.testrun)

class RegressionTest:
	# This should be somewhere global
	orderOfStates = ('success', 'warning', 'failure', 'error', 'skipped', 'disabled')

	def __init__(self, id):
		self.id = id
		self.description = None
		self.status = None
		self.baselineStatus = None
		self.verdict = None

	def regress(self, baseline, testrun):
		if baseline and testrun:
			self.description = baseline.description
			self.status = testrun.status
			self.baselineStatus = baseline.status
			self.verdict = self.renderVerdict(baseline.status, testrun.status)
		elif baseline is not None:
			self.description = baseline.description
			self.baselineStatus = baseline.status
			self.verdict = "regression"
		else:
			self.description = testrun.description
			self.verdict = "improvement"

	def renderVerdict(self, baseline, testrun):
		if baseline == testrun:
			return "unchanged"

		try:
			change = self.orderOfStates.index(baseline) - self.orderOfStates.index(testrun)
		except:
			return "undefined";

		if change < 0:
			return "regression"
		return "improvement"

class RegressionAnalysis:
	def regressInputs(self, inputs):
		self.inputs = inputs
		self.documentType = inputs.baseline.documentType
		self.baselineTag = self.inputs.baselineTag
		self.baseline = self.inputs.baseline
		self.testrun = self.inputs.testrun

		self.regress(inputs.baseline, inputs.testrun)

	# either of the two arguments may be None, indicating a missing
	# or a newly added column
	def regress(self, baseline, testrun):
		if baseline:
			baselineElements = self.elementsOf(baseline)
		else:
			baselineElements = []

		if testrun:
			testrunElements = self.elementsOf(testrun)
		else:
			testrunElements = []

		self.regressSequence(baselineElements, testrunElements)

	def regressSequence(self, baseline, testrun):
		# using a dict to map items from baseline to testrun works as long
		# as all IDs are unique. If a sloppily written test uses the same ID
		# for several different test cases, things will come apart quickly.
		testrunDict = {}
		for item in testrun:
			testrunDict[self.key(item)] = item
		processed = set()

		for baselineItem in baseline:
			name = self.key(baselineItem)

			child = self.createChild(name)

			testrunItem = testrunDict.get(name)
			child.regress(baselineItem, testrunItem)
			processed.add(testrunItem)

		for testrunItem in testrun:
			if testrunItem not in processed:
				name = self.key(testrunItem)
				child = self.createChild(name)
				child.regress(None, testrunItem)

class RegressionReport1D(RegressionAnalysis):
	def __init__(self, name = None):
		self.name = name
		self.tests = []

	def key(self, test):
		return test.id

	def elementsOf(self, column):
		return column.results

	def createChild(self, name):
		test = RegressionTest(name)
		self.tests.append(test)
		return test

class RegressionReport2D(RegressionAnalysis):
	def __init__(self):
		self.columns = []

	def key(self, column):
		return column.name

	def elementsOf(self, matrix):
		return matrix.columns

	def createChild(self, name):
		col = RegressionReport1D(name)
		self.columns.append(col)
		return col

	def asMatrixOfValues(self):
		matrix = MatrixOfValues([c.name for c in self.columns], default_value = None)
		for column in self.columns:
			for test in column.tests:
				matrix.set(test.id, column.name, test)
				matrix.setRowInfo(test.id, test.description)

		return matrix

class RegressionInputs:
	def __init__(self, baselineTag, baselineResults, testrunResults):
		self.baselineTag = baselineTag
		self.baseline = baselineResults
		self.testrun = testrunResults

class RegressionMatrix(RegressionReport2D):
	def __init__(self, inputs):
		super().__init__()

		self.regressInputs(inputs)

class RegressionVector(RegressionReport1D):
	def __init__(self, inputs):
		super().__init__()

		self.regressInputs(inputs)

class Regressor(Processor):
	def create_arg_parser(self):
		parser = argparse.ArgumentParser(description = 'Perform regression analysis between test runs')
		parser.add_argument('--baseline',
			help = 'Name of the baseline test run to compare against')
		parser.add_argument('--baseline-tag',
			help = 'Tag identifying the baseline in the generated report.')
		parser.add_argument('--testrun',
			help = 'Name of the test run')

		return parser

	def process_args(self, args):
		self.checkRequiredArgument("--baseline", args.baseline)
		# self.checkRequiredArgument("--testrun", args.testrun)

		self.baselineTag = args.baseline_tag or "baseline"

		self.baseline = TestRunResults(self.logspace, args.baseline)
		self.testrun = TestRunResults(self.logspace, args.testrun)

	def perform(self):
		baseline = self.baseline.results
		testrun = self.testrun.results
		if baseline.__class__ != testrun.__class__:
			twopence.error("Cannot compare results of different dimensions")
			twopence.error(f"Baseline is a {baseline.documentType}, while testrun is a {testrun.documentType}")
			exit(1)

		inputs = RegressionInputs(self.baselineTag, baseline, testrun)

		if isinstance(baseline, ResultsMatrix):
			analysis = RegressionMatrix(inputs)
		else:
			analysis = RegressionVector(inputs)
		self.renderer.renderRegression(analysis)

