/*
Twopence python bindings

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


#ifndef TWOPENCE_PYTHON_EXT_H
#define TWOPENCE_PYTHON_EXT_H


#include <Python.h>
#include <susetest.h>
#include <twopence.h>
#include <string.h>

typedef struct {
	PyObject_HEAD

	char *		name;
	PyObject *	parentObject;
	susetest_config_t *config;
} susetest_Config;

extern PyTypeObject	susetest_ConfigType;
extern PyTypeObject	susetest_ConfigGroupType;

extern PyObject *	susetest_importType(const char *module, const char *typeName);
extern PyObject *	susetest_callType(PyTypeObject *typeObject, PyObject *args, PyObject *kwds);

static inline void
assign_string(char **var, const char *str)
{
	if (*var == str)
		return;
	if (*var)
		free(*var);
	*var = str?  strdup(str) : NULL;
}

static inline void
drop_string(char **var)
{
	assign_string(var, NULL);
}

static inline void
assign_object(PyObject **var, PyObject *obj)
{
	if (obj) {
		Py_INCREF(obj);
	}
	if (*var) {
		Py_DECREF(*var);
	}
	*var = obj;
}

static inline void
drop_object(PyObject **var)
{
	assign_object(var, NULL);
}


#endif /* TWOPENCE_PYTHON_EXT_H */

