/*
suselog python bindings

Copyright (C) 2014 SUSE

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 2.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License along
with this program; if not, write to the Free Software Foundation, Inc.,
51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
*/


#include <Python.h>
#include <fcntl.h>
#include <stdbool.h>
#include "suselog.h"

typedef struct {
	PyObject_HEAD

	suselog_journal_t *journal;
} suselog_Journal;

static void		Journal_dealloc(suselog_Journal *self);
static PyObject *	Journal_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		Journal_init(suselog_Journal *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_beginGroup(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_finishGroup(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_beginTest(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_info(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_success(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_skipped(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_failure(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_warning(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_error(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_fatal(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_record_stdout(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_record_stderr(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_record_buffer(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_writeReport(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_num_tests(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_num_succeeded(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_num_failed(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_num_errors(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_mergeReport(PyObject *self, PyObject *args, PyObject *kwds);

/*
 * Define the python bindings of class "Journal"
 *
 * Create objects using
 *   journal = suselog.Journal("mytest");
 *
 * Then invoke methods like this:
 *   journal.beginGroup("foobar", "This test group validates the foobar group of functions");
 *   journal.beginTest("fooInit", ...)
 *
 * Note that errors are not indicated through the return value, but through
 * exceptions.
 */
static PyMethodDef suselog_journalMethods[] = {
      {	"beginGroup", (PyCFunction) Journal_beginGroup, METH_VARARGS | METH_KEYWORDS,
	"Begin a test group"
      },
      {	"finishGroup", (PyCFunction) Journal_finishGroup, METH_VARARGS | METH_KEYWORDS,
	"Finish a test group"
      },
      {	"beginTest", (PyCFunction) Journal_beginTest, METH_VARARGS | METH_KEYWORDS,
	"Begin a test case"
      },
      {	"info", (PyCFunction) Journal_info, METH_VARARGS | METH_KEYWORDS,
	"Log an information message"
      },
      {	"success", (PyCFunction) Journal_success, METH_VARARGS | METH_KEYWORDS,
	"Report success for current test case"
      },
      {	"skipped", (PyCFunction) Journal_skipped, METH_VARARGS | METH_KEYWORDS,
	"Report that the current test case was skipped"
      },
      {	"failure", (PyCFunction) Journal_failure, METH_VARARGS | METH_KEYWORDS,
	"Report failure for current test case"
      },
      {	"warning", (PyCFunction) Journal_warning, METH_VARARGS | METH_KEYWORDS,
	"Report a warning for current test case"
      },
      {	"error", (PyCFunction) Journal_error, METH_VARARGS | METH_KEYWORDS,
	"Report an error for current test case"
      },
      {	"fatal", (PyCFunction) Journal_fatal, METH_VARARGS | METH_KEYWORDS,
	"Report a fatal error and exit",
      },
      {	"recordStdout", (PyCFunction) Journal_record_stdout, METH_VARARGS | METH_KEYWORDS,
	"Record stdout for current test",
      },
      {	"recordStderr", (PyCFunction) Journal_record_stderr, METH_VARARGS | METH_KEYWORDS,
	"Record stderr for current test",
      },
      {	"recordBuffer", (PyCFunction) Journal_record_buffer, METH_VARARGS | METH_KEYWORDS,
	"Record contents of a buffer for current test",
      },
      {	"mergeReport", (PyCFunction) Journal_mergeReport, METH_VARARGS | METH_KEYWORDS,
	"Merge another test report into this one"
      },
      {	"writeReport", (PyCFunction) Journal_writeReport, METH_VARARGS | METH_KEYWORDS,
	"Write the test report"
      },
      { "num_tests", (PyCFunction) Journal_num_tests, METH_VARARGS | METH_KEYWORDS,
	"Return the number of tests run"
      },
      { "num_succeeded", (PyCFunction) Journal_num_succeeded, METH_VARARGS | METH_KEYWORDS,
	"Return the number of succeeded tests"
      },
      { "num_failed", (PyCFunction) Journal_num_failed, METH_VARARGS | METH_KEYWORDS,
	"Return the number of failed tests"
      },
      { "num_errors", (PyCFunction) Journal_num_errors, METH_VARARGS | METH_KEYWORDS,
	"Return the number of tests with errors"
      },

      {	NULL }
};

static PyTypeObject suselog_JournalType = {
	PyObject_HEAD_INIT(NULL)

	.tp_name	= "suselog.Journal",
	.tp_basicsize	= sizeof(suselog_Journal),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "Suselog journal",

	.tp_methods	= suselog_journalMethods,
	.tp_init	= (initproc) Journal_init,
	.tp_new		= Journal_new,
	.tp_dealloc	= (destructor) Journal_dealloc,
};

/*
 * Methods belonging to the module itself.
 * None so far
 */
static PyMethodDef suselog_methods[] = {
      {	NULL }
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
# define PyMODINIT_FUNC void
#endif

static void *
suselog_Exception(const char *fmt, ...)
{
	char buffer[128];
	va_list ap;

	va_start(ap, fmt);
	snprintf(buffer, sizeof(buffer), fmt, ap);
	va_end(ap);

	PyErr_SetString(PyExc_SystemError, buffer);
	return NULL;
}


/*
 * Constructor: allocate empty Journal object, and set its members.
 */
static PyObject *
Journal_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	suselog_Journal *self;

	self = (suselog_Journal *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->journal = NULL;

	return (PyObject *)self;
}

static int
Journal_init(suselog_Journal *self, PyObject *args, PyObject *kwds)
{
	char *name, *writerId = NULL, *pathname = NULL;
	suselog_writer_t *writer = NULL;

	static char *kwlist[] = {"name", "writer", "path", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|ss", kwlist, &name, &writerId, &pathname))
		return -1; 

	if (writerId == NULL || !strcmp(writerId, "standard"))
		writer = suselog_writer_normal();
	else {
		suselog_Exception("Unknown journal writer %s", writerId);
		return -1;
	}

	self->journal = suselog_journal_new(name, writer);
	if (self->journal == NULL) {
		suselog_Exception("Unable to create log journal");
		return -1;
	}

	if (pathname)
		suselog_journal_set_pathname(self->journal, pathname);
	suselog_journal_set_color(self->journal, 1);

	return 0;
}

/*
 * Destructor: clean any state inside the Journal object
 */
static void
Journal_dealloc(suselog_Journal *self)
{
	if (self->journal)
		suselog_journal_free(self->journal);
	self->journal = NULL;
}

/*
 * Extract suselog target journal from python object.
 * This should really do a type check and throw an exception if it doesn't match
 */
static suselog_journal_t *
Journal_handle(PyObject *self)
{
	return ((suselog_Journal *) self)->journal;
}

/*
 * start a test group
 */
static PyObject *
Journal_beginGroup(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"name",
		"description",
		NULL
	};
	suselog_journal_t *journal;
	char *name = NULL, *description = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|ss", kwlist, &name, &description))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_group_begin(journal, name, description);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * finish a test group
 */
static PyObject *
Journal_finishGroup(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { NULL };
	suselog_journal_t *journal;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_group_finish(journal);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * start a test case
 */
static PyObject *
Journal_beginTest(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"tag",
		"description",
		NULL
	};
	suselog_journal_t *journal;
	PyObject *firstArgObj;
	char *firstArg = NULL, *secondArg = NULL;
	char *name = NULL, *description = NULL;

	/*
	 * Calling conventions:
	 *  (string, string)
	 *	the first argument is the tag, the second one the description
	 *  (string)
	 *	the argument is the description, the tag defaults to NULL
	 *  (None, string)
	 *	the first argument is the tag (NULL), the second one the description
	 *	Legacy use, may go away soon.
	 */
	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O|s", kwlist, &firstArgObj, &secondArg))
		return NULL;

	firstArg = NULL;
	if (firstArgObj != Py_None) {
		if (!PyString_Check(firstArgObj)) {
			PyErr_SetString(PyExc_TypeError, "Journal.beginGroup: first argument must be None or string");
			return NULL;
		}
		firstArg = PyString_AsString(firstArgObj);
	}

	if (secondArg != NULL) {
		name = firstArg;
		description = secondArg;
	} else {
		name = NULL;
		description = firstArg;
	}

	if (description == NULL) {
		PyErr_SetString(PyExc_TypeError, "Journal.beginGroup: no group description given");
		return NULL;
	}

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_test_begin(journal, name, description);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * log info message
 */
static PyObject *
Journal_info(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_info(journal, "%s", message);
	Py_INCREF(Py_None);
	return Py_None;
}


/*
 * test case succeeeded
 */
static PyObject *
Journal_success(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	if (message)
		suselog_success_msg(journal, "%s", message);
	else
		suselog_success(journal);

	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * test case was skipped
 */
static PyObject *
Journal_skipped(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	(void) message; /* ignore message for now */
	suselog_skipped(journal);

	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * test case failure
 */
static PyObject *
Journal_failure(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_failure(journal, "%s", message);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * test case error
 */
static PyObject *
Journal_error(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_error(journal, "%s", message);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * fatal error
 */
static PyObject *
Journal_fatal(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_fatal(journal, "%s", message);
	/* NOTREACHED */
	return NULL;
}

/*
 * test case warning
 */
static PyObject *
Journal_warning(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "message", NULL };
	suselog_journal_t *journal;
	char *message = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &message))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_warning(journal, "%s", message);
	Py_INCREF(Py_None);
	return Py_None;
}

/*
 * Record stdout
 */
static PyObject *
Journal_record_common(PyObject *self, PyObject *args, PyObject *kwds, void (*func)(suselog_journal_t *, const char *, size_t))
{
	static char *kwlist[] = { "buffer", NULL };
	suselog_journal_t *journal;
	PyObject *object;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O", kwlist, &object))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	if (PyString_Check(object)) {
		const char *str = PyString_AsString(object);

		if (str && *str)
			func(journal, str, strlen(str));
	} else
	if (PyByteArray_Check(object)) {
		unsigned int count = PyByteArray_Size(object);
		const char *data;

		if (count != 0) {
			data = PyByteArray_AsString(object);
			func(journal, data, count);
		}
	} else {
		PyErr_SetString(PyExc_TypeError, "first argument must be bytearray or string");
		return NULL;
	}

	Py_INCREF(Py_None);
	return Py_None;
}


static PyObject *
Journal_record_stdout(PyObject *self, PyObject *args, PyObject *kwds)
{
	return Journal_record_common(self, args, kwds, suselog_record_stdout);
}

static PyObject *
Journal_record_stderr(PyObject *self, PyObject *args, PyObject *kwds)
{
	return Journal_record_common(self, args, kwds, suselog_record_stderr);
}

static PyObject *
Journal_record_buffer(PyObject *self, PyObject *args, PyObject *kwds)
{
	return Journal_record_common(self, args, kwds, suselog_record_buffer);
}

/*
 * Merge another report into this one
 */
static PyObject *
Journal_mergeReport(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"filename",
		NULL,
	};
	const char *filename = NULL;
	suselog_journal_t *journal;
	PyObject *result;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &filename))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	result = Py_True;
	if (suselog_journal_merge(journal, filename) < 0)
		result = Py_False;

	Py_INCREF(result);
	return result;
}

/*
 * write out the report
 */
static PyObject *
Journal_writeReport(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { NULL };
	suselog_journal_t *journal;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_journal_write(journal);
	Py_INCREF(Py_None);
	return Py_None;
}

static bool
__check_void_args(PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist, NULL))
		return false;

	return true;
}


/*
 * Return statistics
 */
static const suselog_stats_t *
Journal_stats(PyObject *self, PyObject *args, PyObject *kwds)
{
	suselog_journal_t *journal;

	if (!__check_void_args(args, kwds))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	return suselog_journal_get_stats(journal);
}

static PyObject *
Journal_num_tests(PyObject *self, PyObject *args, PyObject *kwds)
{
	const suselog_stats_t *stats;

	if (!(stats = Journal_stats(self, args, kwds)))
		return NULL;

	return PyInt_FromLong(stats->num_tests);
}

static PyObject *
Journal_num_succeeded(PyObject *self, PyObject *args, PyObject *kwds)
{
	const suselog_stats_t *stats;

	if (!(stats = Journal_stats(self, args, kwds)))
		return NULL;

	return PyInt_FromLong(stats->num_succeeded);
}

static PyObject *
Journal_num_failed(PyObject *self, PyObject *args, PyObject *kwds)
{
	const suselog_stats_t *stats;

	if (!(stats = Journal_stats(self, args, kwds)))
		return NULL;

	return PyInt_FromLong(stats->num_failed);
}

static PyObject *
Journal_num_errors(PyObject *self, PyObject *args, PyObject *kwds)
{
	const suselog_stats_t *stats;

	if (!(stats = Journal_stats(self, args, kwds)))
		return NULL;

	return PyInt_FromLong(stats->num_errors);
}


static void
registerType(PyObject *m, const char *name, PyTypeObject *type)
{
	type->tp_new = PyType_GenericNew;
	if (PyType_Ready(type) < 0)
		return;

	Py_INCREF(type);
	PyModule_AddObject(m, name, (PyObject *) type);
}

PyMODINIT_FUNC
initsuselog(void) 
{
	PyObject* m;

	m = Py_InitModule3("suselog", suselog_methods, "Module for suselog based test logging");

	registerType(m, "Journal", &suselog_JournalType);
}
