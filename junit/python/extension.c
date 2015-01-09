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
static PyObject *	Journal_success(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_failure(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_warning(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_error(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_fatal(PyObject *self, PyObject *args, PyObject *kwds);
static PyObject *	Journal_writeReport(PyObject *self, PyObject *args, PyObject *kwds);

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
      {	"success", (PyCFunction) Journal_success, METH_VARARGS | METH_KEYWORDS,
	"Report success for current test case"
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
      {	"writeReport", (PyCFunction) Journal_writeReport, METH_VARARGS | METH_KEYWORDS,
	"Write the test report"
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

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|s", kwlist, &name, &description))
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
		"name",
		"description",
		NULL
	};
	suselog_journal_t *journal;
	char *name = NULL, *description = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|s", kwlist, &name, &description))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_test_begin(journal, name, description);
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
 * write out the report
 */
static PyObject *
Journal_writeReport(PyObject *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = { "pathname", NULL };
	suselog_journal_t *journal;
	char *pathname = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &pathname))
		return NULL;

	if ((journal = Journal_handle(self)) == NULL)
		return NULL;

	suselog_journal_write(journal);
	Py_INCREF(Py_None);
	return Py_None;
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
