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
static PyObject *	Config_name(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_workspace(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_report(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_nodes(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_networks(susetest_Config *self, PyObject *args, PyObject *kwds);

static PyObject *	Config_node_target(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_node_internal_ip(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_node_external_ip(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_node_internal_ip6(susetest_Config *self, PyObject *args, PyObject *kwds);

static PyObject *	Config_network_subnet(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_network_gateway(susetest_Config *self, PyObject *args, PyObject *kwds);


/*
 * Define the python bindings of class "Config"
 */
static PyMethodDef susetest_ConfigMethods[] = {
      /* Top-level attributes */
      { "name", (PyCFunction) Config_name, METH_VARARGS | METH_KEYWORDS,
	"Get the name of the test project",
      },
      { "workspace", (PyCFunction) Config_workspace, METH_VARARGS | METH_KEYWORDS,
	"Get the workspace of the test project",
      },
      { "report", (PyCFunction) Config_report, METH_VARARGS | METH_KEYWORDS,
	"Get the report of the test project",
      },

      /* Top-level children */
      { "nodes", (PyCFunction) Config_nodes, METH_VARARGS | METH_KEYWORDS,
	"Get the nodes of the test project",
      },
      { "networks", (PyCFunction) Config_networks, METH_VARARGS | METH_KEYWORDS,
	"Get the networks of the test project",
      },

      /* Node attributes */
      {	"node_target", (PyCFunction) Config_node_target, METH_VARARGS | METH_KEYWORDS,
	"Get the node's target description"
      },
      {	"node_internal_ip", (PyCFunction) Config_node_internal_ip, METH_VARARGS | METH_KEYWORDS,
	"Get the node's internal IPv4 address"
      },
      {	"node_external_ip", (PyCFunction) Config_node_external_ip, METH_VARARGS | METH_KEYWORDS,
	"Get the node's external IPv4 address"
      },
      {	"node_internal_ip6", (PyCFunction) Config_node_internal_ip6, METH_VARARGS | METH_KEYWORDS,
	"Get the node's internal IPv6 address"
      },

      /* Network attributes */
      {	"network_subnet", (PyCFunction) Config_network_subnet, METH_VARARGS | METH_KEYWORDS,
	"Get the networks's IPv4 subnet"
      },
      {	"network_gateway", (PyCFunction) Config_network_gateway, METH_VARARGS | METH_KEYWORDS,
	"Get the networks's IPv4 gateway"
      },

      /* Interface stuff */
      {	NULL }
};

PyTypeObject susetest_ConfigType = {
	PyObject_HEAD_INIT(NULL)

	.tp_name	= "curly.Config",
	.tp_basicsize	= sizeof(susetest_Config),
	.tp_flags	= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
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
	self->name = NULL;

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

	self->config_root = susetest_config_read(filename);
	if (self->config_root == NULL) {
		PyErr_Format(PyExc_SystemError, "Unable to read susetest config from file \"%s\"", filename);
		return -1;
	}

	/* While we're transitioning from the old-style curly stuff to Eric's
	 * XML stuff, there may or may not be a testenv group between the root and
	 * the stuff we're interested in.
	 */
	self->config = susetest_config_get_child(self->config_root, "testenv", NULL);
	if (self->config != NULL) {
		self->name = susetest_config_name(self->config);
	} else {
		self->config = self->config_root;
	}

	printf("Using curly config file %s\n", filename);
	return 0;
}

/*
 * Destructor: clean any state inside the Config object
 */
static void
Config_dealloc(susetest_Config *self)
{
	/* drop_string(&self->name); */
	if (self->config_root)
		susetest_config_free(self->config_root);
	self->config_root = NULL;
	self->config = NULL;
	self->name = NULL;
}

int
Config_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &susetest_ConfigType);
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

static bool
__check_name_args(PyObject *args, PyObject *kwds, const char **name_p)
{
	static char *kwlist[] = {
		"name",
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, name_p))
		return false;

	return true;
}

static PyObject *
__toplevel_string_attr(susetest_Config *self, PyObject *args, PyObject *kwds, const char *attrname)
{
	const char *value;

	if (!__check_void_args(args, kwds))
		return NULL;

	value = susetest_config_get_attr(self->config, attrname);

	if (value != NULL)
		return PyString_FromString(value);

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
__toplevel_name_list(susetest_Config *self, PyObject *args, PyObject *kwds, const char *type)
{
	const char **values, **s;
	PyObject *result;

	if (!__check_void_args(args, kwds))
		return NULL;

	values = susetest_config_get_children(self->config, type);
	if (values == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "failed to get child names for configuration object");
		return NULL;
	}

	result = PyList_New(0);
	for (s = values; *s; ++s)
		PyList_Append(result, PyString_FromString(*s++));

	free(values);
	return result;
}

static PyObject *
__firstlevel_string_attr(susetest_Config *self, PyObject *args, PyObject *kwds, const char *type, const char *attrname)
{
	const char *name, *value;
	susetest_config_t *child;

	if (!__check_name_args(args, kwds, &name))
		return NULL;

	child = susetest_config_get_child(self->config, type, name);
	if (child == NULL) {
		PyErr_Format(PyExc_AttributeError, "Unknown %s \"%s\"", type, name);
		return NULL;
	}

	value = susetest_config_get_attr(child, attrname);

	if (value != NULL)
		return PyString_FromString(value);

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
Config_name(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	if (self->name != NULL)
		return PyString_FromString(self->name);

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
Config_workspace(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __toplevel_string_attr(self, args, kwds, "workspace");
}

static PyObject *
Config_report(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __toplevel_string_attr(self, args, kwds, "report");
}

static PyObject *
Config_nodes(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __toplevel_name_list(self, args, kwds, "node");
}

static PyObject *
Config_node_target(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __firstlevel_string_attr(self, args, kwds, "node", "target");
}

static PyObject *
Config_node_internal_ip(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __firstlevel_string_attr(self, args, kwds, "node", "ipv4_addr");
}

static PyObject *
Config_node_external_ip(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
Config_node_internal_ip6(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __firstlevel_string_attr(self, args, kwds, "node", "ipv6_addr");
}

static PyObject *
Config_networks(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __toplevel_name_list(self, args, kwds, "network");
}

static PyObject *
Config_network_subnet(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __firstlevel_string_attr(self, args, kwds, "network", "subnet");
}

static PyObject *
Config_network_gateway(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __firstlevel_string_attr(self, args, kwds, "network", "gateway");
}
