#!/usr/bin/env python3

import ctypes
import internals

# With the C API, you can easily create a UCS2 (2BYTE_KIND) string
# whos characters are all ASCII. In pseudocode:
#
#     u = PyUnicode_New(1, 65535) # creates a 2BYTE string
#     d = PyUnicode_DATA(u)
#     PyUnicode_WRITE(PyUnicode_2BYTE_KIND, d, 0, 'a')
#
# However, this isn't a valid string. The docs seem to imply that it
# is: "maxchar should be the true maximum code point to be placed in
# the string. As an approximation, it can be rounded up to the nearest
# value in the sequence 127, 255, 65535, 1114111." However, that isn't
# really a "should", but a "must". For example, because string
# equality trusts the string kind, u == 'a' will be False. This is
# probably just a bug in the C API docs wording, which may be fixed
# in 3.7.
# 
# We can't quite demonstrate this from ctypes, because the _DATA and
# _WRITE macros do a bunch of checks and ultimately do raw pointer
# arithmetic that depends on types that aren't exported, so there's
# nothing we can call. But we can use internals to do it.

PyUnicode_New = ctypes.pythonapi.PyUnicode_New
PyUnicode_New.argtypes = (ctypes.c_ssize_t, ctypes.c_uint32)
PyUnicode_New.restype = ctypes.py_object

s = PyUnicode_New(1, 65535)

# Not required: test that we really have a UCS2 string
p = internals.PyUnicodeObject.from_address(id(s))
assert p.length == 1
assert p.kind == p.PyUnicode_2BYTE_KIND

# Fill it with ASCII data
addr = id(s) + internals.PyUnicodeObject.data.offset
p = (ctypes.c_uint16 * 1).from_address(addr)
p[0] = ord('a')

# Now use it, and see that it works like a string, but not one
# that's equal to an ASCII string with the same ASCII data.
print(s)
print(s[0] == 'a') # True, because this generates a 1BYTE slice
print(s == 'a') # False, because no 2BYTE string equals any 1BYTE
