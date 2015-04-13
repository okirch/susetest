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
static PyObject *	Config_node(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_network(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_child(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_children(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_get(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_buildAttrs(susetest_node_config_t *tgt);
static void		ConfigGroup_dealloc(susetest_Config *self);
static PyObject *	ConfigGroup_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		ConfigGroup_init(susetest_Config *self, PyObject *args, PyObject *kwds);
static void		ConfigGroup_set(susetest_Config *, const char *, susetest_node_config_t *, PyObject *);
static PyObject *	ConfigGroup_getattr(susetest_Config *self, char *name);


/*
 * Define the python bindings of class "Config"
 */
static PyMethodDef susetest_ConfigMethods[] = {
      {	"node", (PyCFunction) Config_node, METH_VARARGS | METH_KEYWORDS,
	"Obtain the configuration for the node with the given nickname",
      },
      {	"network", (PyCFunction) Config_network, METH_VARARGS | METH_KEYWORDS,
	"Obtain the configuration for the network with the given name",
      },
      {	"target", (PyCFunction) Config_target, METH_VARARGS | METH_KEYWORDS,
	"Obtain a handle for the target with the given nickname"
      },
      {	"children", (PyCFunction) Config_children, METH_VARARGS | METH_KEYWORDS,
	"Obtain all children with the given type",
      },
      {	"child", (PyCFunction) Config_child, METH_VARARGS | METH_KEYWORDS,
	"Obtain the configuration group with the given type and name",
      },
      {	"value", (PyCFunction) Config_get, METH_VARARGS | METH_KEYWORDS,
	"Query global string attribute"
      },
      {	"get", (PyCFunction) Config_get, METH_VARARGS | METH_KEYWORDS,
	"Query global string attribute"
      },
      {	NULL }
};

PyTypeObject susetest_ConfigType = {
	PyObject_HEAD_INIT(NULL)

	.tp_name	= "susetestimpl.Config",
	.tp_basicsize	= sizeof(susetest_Config),
	.tp_flags	= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_doc		= "Config object for twopence based tests",

	.tp_methods	= susetest_ConfigMethods,
	.tp_init	= (initproc) Config_init,
	.tp_new		= Config_new,
	.tp_dealloc	= (destructor) Config_dealloc,
};

/*
 * Define the python bindings of class "ConfigGroup"
 */
static PyMethodDef susetest_ConfigGroupMethods[] = {
	{ "children", (PyCFunction) Config_children, METH_VARARGS | METH_KEYWORDS,
	  "Obtain all children with the given type",
	},
	{ "child", (PyCFunction) Config_child, METH_VARARGS | METH_KEYWORDS,
	  "Obtain the configuration group with the given type and name",
	},
	{ "get", (PyCFunction) Config_get, METH_VARARGS | METH_KEYWORDS,
	  "Query global string attribute"
	},
	{ NULL }
};

PyTypeObject susetest_ConfigGroupType = {
	PyObject_HEAD_INIT(NULL)

	.tp_name	= "susetestimpl.ConfigGroup",
	.tp_basicsize	= sizeof(susetest_Config),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "ConfigGroup object for twopence based tests",

	.tp_methods	= susetest_ConfigGroupMethods,
	.tp_init	= (initproc) ConfigGroup_init,
	.tp_new		= ConfigGroup_new,
	.tp_dealloc	= (destructor) ConfigGroup_dealloc,

	.tp_getattr	= (getattrfunc) ConfigGroup_getattr,
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
	self->parentObject = NULL;
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
	drop_string(&self->name);
	if (self->config)
		susetest_config_free(self->config);
	self->config = NULL;
	drop_object(&self->parentObject);
}

int
Config_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &susetest_ConfigType);
}

static PyObject *
Config_get(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"attrname",
		NULL
	};
	char *name = NULL;
	const char *value;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &name))
		return NULL;

	value = susetest_config_get_attr(self->config, name);
	if (value != NULL)
		return PyString_FromString(value);

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
Config_childCommon(susetest_Config *self, const char *type, const char *name)
{
	susetest_config_t *child;
	PyObject *args, *result = NULL;

	if (self->config == NULL) {
		PyErr_SetString(PyExc_ValueError, "configuration object is empty");
		return NULL;
	}

	child = susetest_config_get_child(self->config, type, name);
	if (child == NULL) {
		PyErr_Format(PyExc_AttributeError, "Unknown %s \"%s\"", type, name);
		return NULL;
	}

	args = PyTuple_New(0);
	result = susetest_callType(&susetest_ConfigGroupType, args, NULL);
	Py_DECREF(args);

	if (result != NULL)
		ConfigGroup_set((susetest_Config *) result, name, child, (PyObject *) self);

	return result;
}

static PyObject *
Config_childTyped(susetest_Config *self, const char *type, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"name",
		NULL
	};
	char *name = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &name))
		return NULL;

	return Config_childCommon(self, type, name);
}

static PyObject *
Config_node(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return Config_childTyped(self, "node", args, kwds);
}

static PyObject *
Config_network(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return Config_childTyped(self, "network", args, kwds);
}

static PyObject *
Config_child(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"type",
		"name",
		NULL
	};
	char *type = NULL, *name = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "ss", kwlist, &type, &name))
		return NULL;

	return Config_childCommon(self, type, name);
}

static PyObject *
Config_children(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"type",
		NULL
	};
	char *type = NULL;
	const char **names;
	PyObject *result = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &type))
		return NULL;

	if (self->config == NULL) {
		PyErr_SetString(PyExc_ValueError, "configuration object is empty");
		return NULL;
	}

	names = susetest_config_get_children(self->config, type);
	if (names == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "failed to get child names for configuration object");
	} else {
		unsigned int n;

		result = PyList_New(0);
		for (n = 0; names[n]; ++n) {
			PyObject *childObject;

			childObject = Config_childCommon(self, type, names[n]);
			PyList_Append(result, childObject);
			Py_DECREF(childObject);
		}
		free(names);
	}

	return result;
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
	static int warned = 0;

	if (!warned) {
		fprintf(stderr, "Config.target() method obsolete, please use Config.get('target') instead\n");
		warned = 1;
	}

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

		PyTuple_SET_ITEM(args, 0, PyString_FromString(target_spec));
		PyTuple_SET_ITEM(args, 1, attrs = Config_buildAttrs(node_conf));
		PyTuple_SET_ITEM(args, 2, PyString_FromString(name));

		result = susetest_callType((PyTypeObject *) target_type, args, NULL);

		Py_DECREF(args);
	}

	return result;
}

PyObject *
Config_buildAttrs(susetest_node_config_t *tgt)
{
	PyObject *dict = PyDict_New();
	const char **names;
	unsigned int i;
	
	names = susetest_node_config_attr_names(tgt);
	if (names == NULL)
		return dict; /* no attributes: return empty dict */

	for (i = 0; names[i]; ++i) {
		const char *value;

		value = susetest_node_config_get_attr(tgt, names[i]);
		if (value != NULL)
			PyDict_SetItemString(dict, names[i], PyString_FromString(value));
	}
	return dict;
}

PyObject *
ConfigGroup_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	susetest_Config *self;

	self = (susetest_Config *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->config = NULL;
	self->parentObject = NULL;
	return (PyObject *) self;
}

int
ConfigGroup_init(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist))
		return -1;
	return 0;
}

void
ConfigGroup_set(susetest_Config *self, const char *name, susetest_node_config_t *node_conf, PyObject *parent)
{
	assign_string(&self->name, name);
	assign_object(&self->parentObject, parent);
	self->config = node_conf;
}

void
ConfigGroup_dealloc(susetest_Config *self)
{
	drop_string(&self->name);
	drop_object(&self->parentObject);
	self->config = NULL;
}

static PyObject *
ConfigGroup_getattr(susetest_Config *self, char *name)
{
	if (!strcmp(name, "name")) {
		if (self->name == NULL)
			goto return_none;
		return PyString_FromString(self->name);
	}

	if (!strcmp(name, "target")) {
		const char *value = susetest_node_config_get_target(self->config);

		if (value == NULL)
			goto return_none;
		return PyString_FromString(value);
	}

	if (!strcmp(name, "attrs")) {
		if (self->config == NULL)
			goto return_none;
		return Config_buildAttrs(self->config);
	}

	if (!strcmp(name, "container")) {
		if (self->parentObject == NULL)
			goto return_none;
		Py_INCREF(self->parentObject);
		return self->parentObject;
	}

	return Py_FindMethod(susetest_ConfigGroupMethods, (PyObject *) self, name);

return_none:
	Py_INCREF(Py_None);
	return Py_None;
}
