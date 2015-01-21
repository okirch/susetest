/*
Twopence python bindings - class Config

Copyright (C) 2014, 2015 SUSE

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


#include "extension.h"

#include <fcntl.h>
#include <sys/wait.h>

#include "susetest.h"

static void		Config_dealloc(susetest_Config *self);
static PyObject *	Config_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		Config_init(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_target(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_buildAttrs(susetest_node_config_t *tgt);

/*
 * Define the python bindings of class "Config"
 * Normally, you do not create Config objects yourself;
 * Usually, these are created as the return value of Command.run()
 */
static PyMethodDef susetest_ConfigMethods[] = {
      {	"target", (PyCFunction) Config_target, METH_VARARGS | METH_KEYWORDS,
	"Obtain a handle for the target with the given nickname"
      },
      {	NULL }
};

PyTypeObject susetest_ConfigType = {
	PyObject_HEAD_INIT(NULL)

	.tp_name	= "susetest.Config",
	.tp_basicsize	= sizeof(susetest_Config),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "Config object for twopence based tests",

	.tp_methods	= susetest_ConfigMethods,
	.tp_init	= (initproc) Config_init,
	.tp_new		= Config_new,
	.tp_dealloc	= (destructor) Config_dealloc,
};

/*
 * Constructor: allocate empty Config object, and set its members.
 */
static PyObject *
Config_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	susetest_Config *self;

	self = (susetest_Config *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->config = NULL;

	return (PyObject *)self;
}

/*
 * Initialize the status object
 */
static int
Config_init(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"file",
		NULL
	};
	char *filename = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|s", kwlist, &filename))
		return -1;

	if (filename == NULL) {
		filename = getenv("TWOPENCE_CONFIG_PATH");
		if (filename == NULL)
			filename = "twopence.conf";
	}

	self->config = susetest_config_read(filename);
	if (self->config == NULL) {
		PyErr_Format(PyExc_SystemError, "Unable to read susetest config from file \"%s\"", filename);
		return -1;
	}

	return 0;
}

/*
 * Destructor: clean any state inside the Config object
 */
static void
Config_dealloc(susetest_Config *self)
{
	if (self->config)
		susetest_config_free(self->config);
	self->config = NULL;
}

int
Config_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &susetest_ConfigType);
}

static PyObject *
Config_target(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"name",
		NULL
	};
	char *name = NULL;
	susetest_node_config_t *node_conf;
	PyObject *result = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &name))
		return NULL;

	node_conf = susetest_config_get_node(self->config, name);
	if (node_conf == NULL) {
		PyErr_Format(PyExc_AttributeError, "Unknown target \"%s\"", name);
	} else {
		const char *target_spec = susetest_node_config_get_target(node_conf);
		PyObject *args = PyTuple_New(3);
		PyObject *attrs;
		PyObject *target_type = NULL;

		if (!(target_type = susetest_importType("twopence", "Target")))
			return NULL;

		if (!(attrs = Config_buildAttrs(node_conf)))
			return NULL;

		PyTuple_SET_ITEM(args, 0, PyString_FromString(target_spec));
		PyTuple_SET_ITEM(args, 1, attrs);
		PyTuple_SET_ITEM(args, 2, PyString_FromString(name));

		result = susetest_callType((PyTypeObject *) target_type, args, NULL);

		Py_DECREF(args);
	}

	return result;
}

PyObject *
Config_buildAttrs(susetest_node_config_t *tgt)
{
	PyObject *dict;
	const char **names;
	unsigned int i;
	
	names = susetest_node_config_attr_names(tgt);
	if (names == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "cannot build attribute name list for twopence target");
		return NULL;
	}

	dict = PyDict_New();
	for (i = 0; names[i]; ++i) {
		const char *value;

		value = susetest_node_config_get_attr(tgt, names[i]);
		if (value != NULL)
			PyDict_SetItemString(dict, names[i], PyString_FromString(value));
	}
	return dict;
}
