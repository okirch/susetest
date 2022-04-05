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
from .logger import ResultsMatrixWriter, ResultsVectorWriter, ResultsParser


def info(msg):
	print("== %s" % msg)

class FrequentWriter:
	def __init__(self, object, writerClass, path):
		self.object = object
		self.writerClass = writerClass
		self.path = path

		if self.path is None:
			raise ValueError("Cannot save results; path not set")

	def sync(self):
		writer = self.writerClass()
		self.object.serialize(writer)
		writer.save(self.path)

		info(f"Updated {self.path}")

class ResultsCollection:
	def __init__(self, name = None, writerClass = None):
		self._name = name
		self._saver = None
		self._writerClass = writerClass
		self.invocation = None

	def attachToLogspace(self, logspace, clobber = False):
		path = os.path.join(logspace, "results.xml")
		if not clobber and os.path.exists(path):
			raise ValueError(f"Refusing to overwrite existing {path}")

		# whenver results.save() is called, write the results
		# vector to the file
		self.setPath(path)

	def setPath(self, path):
		if self._writerClass:
			self._saver = FrequentWriter(self, self._writerClass, path)

	def save(self):
		if self._saver:
			self._saver.sync()

	def serialize(self, writer):
		if self.invocation:
			writer.setInvocation(self.invocation)

	def deserialize(self, reader):
		self.invocation = reader.invocation

class ResultsVector(ResultsCollection):
	class TestResult:
		def __init__(self, id, status, description):
			self.id = id
			self.status = status
			self.description = description

	def __init__(self, name = None):
		super().__init__(name, writerClass = ResultsVectorWriter)
		self._parameters = {}
		self._results = {}

	@property
	def name(self):
		return self._name

	@property
	def parameters(self):
		return self._parameters

	@property
	def results(self):
		return sorted(self._results.values(), key = lambda r: r.id)

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
		self._results[result.id] = result

	def asVectorOfValues(self, filter):
		vector = VectorOfValues(default_value = "(not run)")
		for test in self.results:
			vector.set(test.id, test.status)
			vector.setRowInfo(test.id, test.description)

		if filter:
			filter.apply(vector)
		return vector

class ResultsMatrix(ResultsCollection):
	def __init__(self, name = None):
		super().__init__(name, writerClass = ResultsMatrixWriter)
		self._columns = []

	@property
	def columns(self):
		return self._columns

	def serialize(self, writer):
		writer.setName(self._name)
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

		# inherit the FrequentWriter
		column._saver = self._saver

		info(f"Created results vector for matrix column {name}")
		return column

	def _createColumn(self, name = None):
		for column in self._columns:
			if column.name == name:
				return column

		column = ResultsVector(name)
		self._columns.append(column)
		return column

	def asMatrixOfValues(self, filter):
		matrix = MatrixOfValues([c.name for c in self._columns], default_value = "(not run)")
		for column in self._columns:
			for test in column.results:
				matrix.set(test.id, column.name, test.status)
				matrix.setRowInfo(test.id, test.description)

		if filter:
			filter.apply(matrix)
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
		self._rowNames = set()
		self._rowInfo = {}
		self._default_value = default_value

		self._hiddenRows = set()

	def set(self, row, value):
		self._values[row] = value
		self._rowNames.add(row)

	def get(self, row):
		return self._values.get(row) or self._default_value

	def setRowInfo(self, row, info):
		self._rowInfo[row] = info

	def getRowInfo(self, row):
		return self._rowInfo.get(row) or "-"

	@property
	def rows(self):
		return sorted(self._rowNames)

	def hideCellsWithValue(self, value):
		hide = set()

		for row in self.rows:
			if self.get(row) == value:
				hide.add(row)

		self._rowNames.difference_update(hide)
		self._hiddenRows.update(hide)

class MatrixOfValues:
	def __init__(self, columnNames = [], default_value = "-"):
		self._values = {}
		self._columnNames = columnNames or []
		self._rowNames = set()
		self._rowInfo = {}
		self._default_value = default_value

		self._hiddenRows = set()

	def set(self, row, col, value):
		self._values[f"{row},{col}"] = value
		if col not in self._columnNames:
			self._columnNames.append(col)
		self._rowNames.add(row)

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
		return sorted(self._rowNames)

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

	def hideRowsWithValue(self, value):
		def rowHasUniformValue(value, rowValues):
			return all(cell == value for cell in rowValues)
			return len(set(values)) == 1

		hide = set()
		for row in self.rows:
			if self.rowHasUniformValue(row, value):
				hide.add(row)

		self._rowNames.difference_update(hide)
		self._hiddenRows.update(hide)

class ResultFilter:
	def __init__(self, hide = []):
		self.hide = hide

	def apply(self, values):
		if isinstance(values, MatrixOfValues):
			for status in self.hide:
				values.hideRowsWithValue(status)
		else: # VectorOfValues
			for status in self.hide:
				values.hideCellsWithValue(status)

class Renderer:
	canRenderTestReports = False

	def __init__(self, output_directory = None):
		self.output_directory = output_directory
		self.print = print

	def open(self, filename):
		if self.output_directory is None:
			return False

		path = os.path.join(self.output_directory, filename)

		info(f"Writing {path}")
		dirname = os.path.dirname(path)
		if not os.path.isdir(dirname):
			os.makedirs(dirname, 0o755)

		destfile = open(path, "w")
		self.print = lambda msg = '', **kwargs: print(msg, file = destfile, **kwargs)

	@staticmethod
	def factory(format, output_directory = None):
		if format == 'text':
			return TextRenderer(output_directory)
		elif format == 'html':
			from .html import HTMLRenderer

			return HTMLRenderer(output_directory)

		raise ValueError(f"Cannot create renderer for unknown format {format}")

class TextRenderer(Renderer):
	def renderResults(self, results, filter = None, referenceMap = None):
		if isinstance(results, ResultsMatrix):
			values = results.asMatrixOfValues(filter)
			self.renderMatrix(values, results.parameterMatrix())
		else:
			vector = results.asVectorOfValues(filter)
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

class Tabulator:
	def __init__(self):
		parser = self.build_arg_parser()
		args = parser.parse_args()

		self.logspace = args.logspace
		if self.logspace is None:
			self.logspace = os.path.expanduser("~/susetest/logs")
		if args.testrun:
			self.logspace = os.path.join(self.logspace, args.testrun)

		self.terse = args.terse

		self.renderer = Renderer.factory(args.format, args.output_directory)

	def perform(self):
		path = os.path.join(self.logspace, "results.xml")
		if os.path.exists(path):
			results = self.loadResults(path)
		else:
			results = self.scanResults()

		filter = None
		if self.terse:
			if isinstance(results, ResultsMatrix):
				filter = ResultFilter(["success", "skipped", "disabled"])
			else:
				filter = ResultFilter(["success", "disabled"])

		hrefMap = {}
		if self.renderer.canRenderTestReports:
			if isinstance(results, ResultsMatrix):
				for col in results.columns:
					path = os.path.join(self.logspace, results._name, col.name)
					for name, log in self.scanDirectory(path).items():
						outpath = os.path.join(results._name, col.name, f"{name}.html")
						# print(f"render {path}/{name}: {log} -> {outpath}")
						self.renderer.open(outpath)
						self.renderer.renderTestReport(log)
						for group in log.groups:
							for test in group.tests:
								refId = f"{col.name}:{test.id}"
								testId = test.id
								hrefMap[refId] = f"{outpath}#{testId}"
			else:
				for name, log in self.scanDirectory(self.logspace).items():
					outpath = os.path.join(f"{name}.html")
					# print(f"render {path}/{name}: {log} -> {outpath}")
					self.renderer.open(outpath)
					self.renderer.renderTestReport(log)
					for group in log.groups:
						for test in group.tests:
							testId = test.id
							hrefMap[test.id] = f"{outpath}#{testId}"

		self.renderer.renderResults(results, filter = filter, referenceMap = hrefMap)

	def loadResults(self, path):
		info(f"Loading results from {path}")
		io = ResultsParser(path)
		if io is None:
			raise ValueError(f"Could not open {path}")

		if io.type == "matrix":
			results = ResultsMatrix()
		else:
			results = ResultsVector()

		results.deserialize(io)

		return results

	def scanResults(self):
		info("Scanning logspace")
		result = self.scanSuite()
		if result is None:
			result = self.scanMatrix()

		if result is None:
			raise ValueError(f"No test cases found in {self.logspace}")
		return result

	def scanSuite(self):
		testcases = self.scanDirectory(self.logspace)
		if not testscases:
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

	def build_arg_parser(self):
		import argparse

		parser = argparse.ArgumentParser(description = 'Tabulate test results.')
		parser.add_argument('--terse', action = 'store_true',
			help = 'Make the output more terse by focusing on failures')
		parser.add_argument('--logspace',
			help = 'The directory to use as logspace')
		parser.add_argument('--testrun',
			help = 'Name of the test run')
		parser.add_argument('--format', default = 'text',
			help = 'Select output format (text, html - default: text)')
		parser.add_argument('--output-directory', metavar = 'PATH',
			help = 'Create output file(s) in the specified directory')
		return parser
