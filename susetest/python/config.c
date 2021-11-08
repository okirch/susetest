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

extern PyTypeObject susetest_ConfigNodeType;

static void		Config_dealloc(susetest_Config *self);
static PyObject *	Config_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		Config_init(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_name(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_workspace(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_report(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_nodes(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_networks(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_tree(susetest_Config *self, PyObject *args, PyObject *kwds);
static PyObject *	Config_save(susetest_Config *self, PyObject *args, PyObject *kwds);

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

      /* Access to low-level config functions */
      {	"tree", (PyCFunction) Config_tree, METH_VARARGS | METH_KEYWORDS,
	"Get the config tree"
      },
      {	"save", (PyCFunction) Config_save, METH_VARARGS | METH_KEYWORDS,
	"Save configuration to file"
      },

      /* Interface stuff */
      {	NULL }
};

PyTypeObject susetest_ConfigType = {
	PyVarObject_HEAD_INIT(NULL, 0)

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
	PyObject *arg_object = NULL;
	char *filename = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|O", kwlist, &arg_object))
		return -1;

	if (arg_object == Py_None || arg_object == NULL) {
		/* create an empty Config object */
		self->config_root = susetest_config_new();
		self->config = self->config_root;
	} else {
		filename = PyUnicode_AsUTF8(arg_object);
		if (filename == NULL)
			return -1;

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
			self->name = (char *) susetest_config_name(self->config);
		} else {
			self->config = self->config_root;
		}

		/* printf("Using curly config file %s\n", filename); */
	}

	return 0;
}

/*
 * Destructor: clean any state inside the Config object
 */
static void
Config_dealloc(susetest_Config *self)
{
	// printf("Destroying %p\n", self);
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
__get_single_string_arg(PyObject *args, PyObject *kwds, const char *arg_name, const char **string_arg_p)
{
	char *kwlist[] = {
		(char *) arg_name,
		NULL
	};

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, string_arg_p))
		return false;

	return true;
}

static PyObject *
__to_string(const char *value)
{
	if (value != NULL)
		return PyUnicode_FromString(value);

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
__to_string_list(const char * const*values)
{
	PyObject *result;

	result = PyList_New(0);
	while (values && *values)
		PyList_Append(result, PyUnicode_FromString(*values++));

	return result;
}

static PyObject *
__toplevel_string_attr(susetest_Config *self, PyObject *args, PyObject *kwds, const char *attrname)
{
	if (!__check_void_args(args, kwds))
		return NULL;

	return __to_string(susetest_config_get_attr(self->config, attrname));
}

static PyObject *
__get_children(susetest_config_t *config, const char *type)
{
	const char **values;
	PyObject *result;

	values = susetest_config_get_children(config, type);
	if (values == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "failed to get child names for configuration object");
		return NULL;
	}

	result = __to_string_list(values);
	free(values);

	return result;
}

static PyObject *
__get_attr_names(susetest_config_t *config)
{
	const char **values;
	PyObject *result;

	values = susetest_config_get_attr_names(config);
	if (values == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "failed to get attribute names for configuration object");
		return NULL;
	}

	result = __to_string_list(values);
	free(values);

	return result;
}

static PyObject *
__toplevel_name_list(susetest_Config *self, PyObject *args, PyObject *kwds, const char *type)
{
	if (!__check_void_args(args, kwds))
		return NULL;

	return __get_children(self->config, type);
}

static PyObject *
__firstlevel_string_attr(susetest_Config *self, PyObject *args, PyObject *kwds, const char *type, const char *attrname)
{
	const char *name;
	susetest_config_t *child;

	if (!__get_single_string_arg(args, kwds, "name", &name))
		return NULL;

	child = susetest_config_get_child(self->config, type, name);
	if (child == NULL) {
		PyErr_Format(PyExc_AttributeError, "Unknown %s \"%s\"", type, name);
		return NULL;
	}

	return __to_string(susetest_config_get_attr(child, attrname));
}

static PyObject *
Config_name(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	return __to_string(self->name);
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


static PyObject *
Config_tree(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	PyObject *tuple;
	PyObject *nodeObj;

	if (!__check_void_args(args, kwds))
		return NULL;

	tuple = PyTuple_New(1);

	PyTuple_SetItem(tuple, 0, (PyObject *) self);
	Py_INCREF(self);

	nodeObj = susetest_callType(&susetest_ConfigNodeType, tuple, NULL);

	Py_DECREF(tuple);
	return nodeObj;
}

static PyObject *
Config_save(susetest_Config *self, PyObject *args, PyObject *kwds)
{
	const char *filename;

	if (!__get_single_string_arg(args, kwds, "filename", &filename))
		return NULL;

	if (susetest_config_write(self->config_root, filename) < 0) {
		PyErr_Format(PyExc_OSError, "unable to write config file %s", filename);
		return NULL;
	}

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *	ConfigNode_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static int		ConfigNode_init(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static void		ConfigNode_dealloc(susetest_ConfigNode *self);
static PyObject *	ConfigNode_getattro(susetest_ConfigNode *self, PyObject *name);
static PyObject *	ConfigNode_new(PyTypeObject *type, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_name(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_type(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_get_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_add_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_drop_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_get_children(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_get_attributes(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_get_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_set_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_unset_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);
static PyObject *	ConfigNode_get_values(susetest_ConfigNode *self, PyObject *args, PyObject *kwds);

/*
 * Define the python bindings of class "Config"
 */
static PyMethodDef susetest_ConfigNodeMethods[] = {
      /* Top-level attributes */
      { "name", (PyCFunction) ConfigNode_name, METH_VARARGS | METH_KEYWORDS,
	"Get the node name"
      },
      { "type", (PyCFunction) ConfigNode_type, METH_VARARGS | METH_KEYWORDS,
	"Get the node type"
      },
      { "get_child", (PyCFunction) ConfigNode_get_child, METH_VARARGS | METH_KEYWORDS,
	"Find the child node with given type and name",
      },
      { "add_child", (PyCFunction) ConfigNode_add_child, METH_VARARGS | METH_KEYWORDS,
	"Add a child node with given type and name",
      },
      { "drop_child", (PyCFunction) ConfigNode_drop_child, METH_VARARGS | METH_KEYWORDS,
	"Drop the given child",
      },
      { "get_children", (PyCFunction) ConfigNode_get_children, METH_VARARGS | METH_KEYWORDS,
	"Get all child nodes with given type",
      },
      { "get_attributes", (PyCFunction) ConfigNode_get_attributes, METH_VARARGS | METH_KEYWORDS,
	"Get the names of all attributes of this node",
      },
      { "get_value", (PyCFunction) ConfigNode_get_value, METH_VARARGS | METH_KEYWORDS,
	"Get the value of the named attribute as a single string"
      },
      { "set_value", (PyCFunction) ConfigNode_set_value, METH_VARARGS | METH_KEYWORDS,
	"Set the value of the named attribute"
      },
      { "drop", (PyCFunction) ConfigNode_unset_value, METH_VARARGS | METH_KEYWORDS,
	"Drop the named attribute"
      },
      { "get_values", (PyCFunction) ConfigNode_get_values, METH_VARARGS | METH_KEYWORDS,
	"Get the value of the named attribute as list of strings"
      },

      {	NULL }
};

PyTypeObject susetest_ConfigNodeType = {
	PyVarObject_HEAD_INIT(NULL, 0)

	.tp_name	= "curly.ConfigNode",
	.tp_basicsize	= sizeof(susetest_ConfigNode),
	.tp_flags	= Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
	.tp_doc		= "Config object for twopence based tests",

	.tp_methods	= susetest_ConfigNodeMethods,
	.tp_init	= (initproc) ConfigNode_init,
	.tp_new		= ConfigNode_new,
	.tp_dealloc	= (destructor) ConfigNode_dealloc,
	.tp_getattro	= (getattrofunc) ConfigNode_getattro,
};

/*
 * Constructor: allocate empty Config object, and set its members.
 */
static PyObject *
ConfigNode_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	susetest_ConfigNode *self;

	self = (susetest_ConfigNode *) type->tp_alloc(type, 0);
	if (self == NULL)
		return NULL;

	/* init members */
	self->config_object = NULL;
	self->node = NULL;

	return (PyObject *)self;
}

static inline void
__ConfigNode_attach(susetest_ConfigNode *self, PyObject *config_object, susetest_config_t *node)
{
	assert(self->config_object == NULL);

	self->node = node;
	self->config_object = config_object;
	Py_INCREF(config_object);

	// printf("ConfigNode %p references %p count=%ld\n", self, config_object, config_object->ob_refcnt);
}

static inline void
__ConfigNode_detach(susetest_ConfigNode *self)
{
	if (self->config_object) {
		// printf("ConfigNode %p releases %p count=%ld\n", self, self->config_object, self->config_object->ob_refcnt);
		Py_DECREF(self->config_object);
	}
	self->config_object = NULL;
}

/*
 * Initialize the status object
 */
static int
ConfigNode_init(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {
		"config",
		NULL
	};
	PyObject *config_object = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "|O", kwlist, &config_object))
		return -1;

	if (config_object && !Config_Check(config_object)) {
		PyErr_SetString(PyExc_RuntimeError, "config argument must be an instance of susetest.Config");
		return -1;
	}

	if (config_object)
		__ConfigNode_attach(self, config_object, ((susetest_Config *) config_object)->config_root);

	return 0;
}

/*
 * Destructor: clean any state inside the Config object
 */
static void
ConfigNode_dealloc(susetest_ConfigNode *self)
{
	__ConfigNode_detach(self);
}

int
ConfigNode_Check(PyObject *self)
{
	return PyType_IsSubtype(Py_TYPE(self), &susetest_ConfigNodeType);
}

static PyObject *
ConfigNode_getattro(susetest_ConfigNode *self, PyObject *nameo)
{
	if (self->node) {
		const char *name = PyUnicode_AsUTF8(nameo);
		const char *const *values;

		if (name == NULL)
			return NULL;

		values = susetest_config_get_attr_list(self->node, name);
		if (values) {
			if (values[0] == NULL || values[1] == NULL)
				return __to_string(values[0]);

			return __to_string_list(values);
		}
	}

	return PyObject_GenericGetAttr((PyObject *) self, nameo);
}

static bool
__check_node(susetest_ConfigNode *self)
{
	if (self->node == NULL) {
		PyErr_SetString(PyExc_RuntimeError, "ConfigNode object does not refer to any config data");
		return false;
	}

	return true;
}

static bool
__check_call(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	return __check_void_args(args, kwds) && __check_node(self);
}

static PyObject *
__wrap_node(susetest_config_t *node, susetest_ConfigNode *parent)
{
	PyObject *result;

	result = susetest_callType(&susetest_ConfigNodeType, NULL, NULL);
	if (result == NULL)
		return NULL;

	if (!ConfigNode_Check(result)) {
		PyErr_SetString(PyExc_RuntimeError, "cannot create ConfigNode object");
		result = NULL;
	} else {
		__ConfigNode_attach((susetest_ConfigNode *) result, parent->config_object, node);
	}

	return (PyObject *) result;
}

static PyObject *
ConfigNode_type(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	if (!__check_call(self, args, kwds))
		return NULL;

	return __to_string(susetest_config_type(self->node));
}

static PyObject *
ConfigNode_name(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	if (!__check_call(self, args, kwds))
		return NULL;

	return __to_string(susetest_config_name(self->node));
}

static PyObject *
ConfigNode_get_children(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	const char *type;

	if (!__get_single_string_arg(args, kwds, "type", &type))
		return NULL;

	if (!__check_node(self))
		return NULL;

	return __get_children(self->node, type);
}

static PyObject *
ConfigNode_get_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	char *kwlist[] = {
		"type",
		"name",
		NULL
	};
	const char *name, *type;
	susetest_config_t *child;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "ss", kwlist, &type, &name))
		return NULL;

	if (!__check_node(self))
		return NULL;

	child = susetest_config_get_child(self->node, type, name);
	if (child == NULL) {
		Py_INCREF(Py_None);
		return Py_None;
	}

	return __wrap_node(child, self);
}

extern susetest_config_t *      susetest_config_add_child(susetest_config_t *cfg, const char *type, const char *name);

static PyObject *
ConfigNode_add_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	char *kwlist[] = {
		"type",
		"name",
		NULL
	};
	const char *name, *type;
	susetest_config_t *child;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "ss", kwlist, &type, &name))
		return NULL;

	if (!__check_node(self))
		return NULL;

	child = susetest_config_add_child(self->node, type, name);
	if (child == NULL) {
		PyErr_Format(PyExc_SystemError, "Unable to create a %s node name \"%s\"", type, name);
		return NULL;
	}

	return __wrap_node(child, self);
}

static PyObject *
ConfigNode_drop_child(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	char *kwlist[] = {
		"child",
		NULL
	};
	PyObject *childObject;
	unsigned int count;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "O", kwlist, &childObject))
		return NULL;

	if (!__check_node(self))
		return NULL;

	if (!ConfigNode_Check(childObject)) {
		PyErr_SetString(PyExc_ValueError, "Argument is not a ConfigNode instance");
		return NULL;
	}

	count = susetest_config_drop_child(self->node, ((susetest_ConfigNode *) childObject)->node);
	return PyLong_FromUnsignedLong(count);
}

static PyObject *
ConfigNode_get_attributes(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	if (!__check_call(self, args, kwds))
		return NULL;

	return __get_attr_names(self->node);
}

static PyObject *
ConfigNode_get_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	const char *name;

	if (!__get_single_string_arg(args, kwds, "name", &name))
		return NULL;

	if (!__check_node(self))
		return NULL;

	return __to_string(susetest_config_get_attr(self->node, name));
}

static PyObject *
ConfigNode_set_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	char *kwlist[] = {
		"name",
		"value",
		NULL
	};
	const char *name;
	PyObject *valueObj = NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "sO", kwlist, &name, &valueObj))
		return NULL;

	if (!__check_node(self))
		return NULL;

	if (PyUnicode_Check(valueObj)) {
		susetest_config_set_attr(self->node, name, PyUnicode_AsUTF8(valueObj));
	} else if (valueObj == Py_None) {
		susetest_config_set_attr(self->node, name, NULL);
	} else {
		PyErr_SetString(PyExc_ValueError, "cannot handle values of this type");
		return NULL;
	}

	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
ConfigNode_unset_value(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	const char *name;

	if (!__get_single_string_arg(args, kwds, "name", &name))
		return NULL;

	if (!__check_node(self))
		return NULL;

	susetest_config_set_attr(self->node, name, NULL);
	Py_INCREF(Py_None);
	return Py_None;
}

static PyObject *
ConfigNode_get_values(susetest_ConfigNode *self, PyObject *args, PyObject *kwds)
{
	const char *name;

	if (!__get_single_string_arg(args, kwds, "name", &name))
		return NULL;

	if (!__check_node(self))
		return NULL;

	return __to_string_list(susetest_config_get_attr_list(self->node, name));
}

