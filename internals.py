#!/usr/bin/env python3

import ctypes
import sys

class PyObject(ctypes.Structure):
    _fields_ = (
        ('ob_refcnt', ctypes.c_ssize_t),
        ('ob_type', ctypes.c_void_p))

class PyVarObject(ctypes.Structure):
    _fields_ = (
        ('ob_refcnt', ctypes.c_ssize_t),
        ('ob_type', ctypes.c_void_p),
        ('ob_size', ctypes.c_ssize_t))

# Internal int representation is documented in longintrepr.h (because it's
# required by marshal and decimal). The only extra field on a PyLongObject
# is ob_digit, a variable-length array of c_uint32 (or c_uint16, if Python
# is compiled with PYLONG_BITS_IN_DIGIT 15 instead of 30). The ob_size
# attribute is slightly abused, with the absolute value being the digit
# count and the sign being the int's sign.
#
# Digits are stored in little-endian order; each digit is a native-endian
# unsigned int.
#
# Note that ctypes can't handle variable-length array struct fields,
# especially not those whose min length is 0 (zero has no digits, not a
# single 0 digit), so the ob_digit field isn't very useful. See
# https://stackoverflow.com/questions/7015487/ctypes-variable-length-structures
# (the answer with StructureVariableSized) for a generic solution, but
# as long as we're only accessing the digits of objects created by Python
# internally (not creating our own objects, resizing existing ones, etc.),
# the digits method is much simpler.
class PyLongObject(ctypes.Structure):
    _fields_ = (
        ('ob_refcnt', ctypes.c_ssize_t),
        ('ob_type', ctypes.c_void_p),
        ('ob_size', ctypes.c_ssize_t),
        ('ob_digit', ctypes.c_uint32 * 1))
    def digits(self):
        arr = ctypes.addressof(self.ob_digit)
        return (ctypes.c_uint32 * abs(self.ob_size)).from_address(arr)
    def value(self):
        val = sum(digit * 1<<(30*i) for i, digit in enumerate(self.digits()))
        return val * (-1 if self.ob_size < 0 else 1)

# String objects are more complicated than you'd expect in 3.4+. See
# unicodeobject.h for details, but the basic idea is that a string can
# be stored in different formats depending on the highest code point
# (and on how they're created), and may carry a UTF-8 cache. Also, to
# work with older C APIs (and sometimes with native UTF-16 APIs) there
# are legacy formats for pure ASCII and for generic wchar_t. Also,
# strings can be interned in a special dict (which does not refcount
# them; SSTATE_INTERNED_MORTAL unintern themselves on death).
class PyUnicodeObject(ctypes.Structure):
    SSTATE_NOT_INTERNED = 0
    SSTATE_INTERNED_MORTAL = 1
    SSTATE_INTERNED_IMMORTAL = 2
    PyUnicode_WCHAR_KIND = 0
    PyUnicode_1BYTE_KIND = 1
    PyUnicode_2BYTE_KIND = 2
    PyUnicode_4BYTE_KIND = 4

    class LegacyUnion(ctypes.Union):
        _fields_ = (
            ('any', ctypes.c_void_p),
            ('latin1', ctypes.POINTER(ctypes.c_uint8)), # Py_UCS1 *
            ('ucs2', ctypes.POINTER(ctypes.c_uint16)), # Py_UCS2 *
            ('ucs4', ctypes.POINTER(ctypes.c_uint32))) # Py_UCS4 *
    
    _fields_ = (
        ('ob_refcnt', ctypes.c_ssize_t),
        ('ob_type', ctypes.c_void_p),
        # Note that it's not a PyVarObject; length instead of ob_size,
        # which is the length in code points of the actual string,
        # regardless of how it's stored internally.
        ('length', ctypes.c_ssize_t),
        ('hash', ctypes.c_int64), # actually Py_hash_t == intptr_t
        ('interned', ctypes.c_uint, 2), # SSTATE_*
        ('kind', ctypes.c_uint, 3), # PyUnicode_*_KIND
        ('compact', ctypes.c_uint, 1),
        ('ascii', ctypes.c_uint, 1),
        ('ready', ctypes.c_uint, 1),
        ('padding', ctypes.c_uint, 24),
        ('wstr', ctypes.POINTER(ctypes.c_wchar)),
        # Fields after this do not exist if ascii
        ('utf8_length', ctypes.c_ssize_t),
        ('utf8', ctypes.c_char_p),
        ('wstr_length', ctypes.c_ssize_t),
        # Fields after this do not exist if compact
        ('data', LegacyUnion))

_KINDS = {
    PyUnicodeObject.PyUnicode_WCHAR_KIND: ctypes.c_wchar,
    PyUnicodeObject.PyUnicode_1BYTE_KIND: ctypes.c_uint8,
    PyUnicodeObject.PyUnicode_2BYTE_KIND: ctypes.c_uint16,
    PyUnicodeObject.PyUnicode_4BYTE_KIND: ctypes.c_uint32,
    }

# Not a method because from_address will copy the header without the data
def get_buffer(s):
    # Using the official rules from the header file, which could
    # of course be simplified.
    p = PyUnicodeObject.from_address(id(s))
    length = p.length
    t = _KINDS[p.kind]
    if p.compact and p.ascii:
        # ASCII buffer comes right after wstr
        t = ctypes.c_char
        addr = id(s) + PyUnicodeObject.utf8_length.offset
    elif p.compact and not p.ascii:
        # UCS1/2/4 buffer comes right after wstr
        addr = id(s) + PyUnicodeObject.data.offset
    elif p.kind == p.PyUnicode_WCHAR_KIND:
        # Note that this goes with wstr_length, not length!
        return p.wstr
    elif not p.compact and p.kind != p.PyUnicode_WCHAR_KIND:
        if p.kind == p.PyUnicode_1BYTE_KIND: return p.data.latin1
        elif p.kind == p.PyUnicode_2BYTE_KIND: return p.data.ucs2
        elif p.kind == p.PyUnicode_4BYTE_KIND: return p.data.ucs4
    return (t * length).from_address(addr)

n = 12448057941136394342297748548545082997815840357634948550739612798732309975923280685245876950055614362283769710705811182976142803324242407017104841062064840113262840137625582646683068904149296501029754654149991842951570880471230098259905004533869130509989042199261339990315125973721454059973605358766253998615919997174542922163484086066438120268185904663422979603026066685824578356173882166747093246377302371176167843247359636030248569148734824287739046916641832890744168385253915508446422276378715722482359321205673933317512861336054835392844676749610712462818600179225635467147870208
m = -n
z = 0
assert PyLongObject.from_address(id(n)).value() == n
assert PyLongObject.from_address(id(m)).value() == m
assert PyLongObject.from_address(id(z)).value() == 0

import numpy as np
_TABLE16 = np.zeros(2**16, dtype=np.uint8)
for i in range(len(_TABLE16)):
    _TABLE16[i] = (i & 1) + _TABLE16[i >> 1]
def popcount(n):
    raw = PyLongObject.from_address(id(n))
    digits = ctypes.addressof(raw.ob_digit)
    digits16 = (ctypes.c_uint16 * (abs(raw.ob_size)*2)).from_address(digits)
    array = np.frombuffer(digits16, dtype=np.uint16)
    return np.sum(_TABLE16[array])
def popcount_fast(n):
    i = id(n)
    ob_size = ctypes.c_ssize_t.from_address(i+16)
    digits16 = (ctypes.c_uint16 * (abs(ob_size.value)*2)).from_address(i+24)
    array = np.frombuffer(digits16, dtype=np.uint16)
    return np.sum(_TABLE16[array])

# Now we get dangerous, or at least Intercalish. Doing this with a small int
# can be even more dangerous, so stay above 2**9.
x = 1000
PyLongObject.from_address(id(x)).digits()[0] += 1
print(x)
print(1000)

# Calling sys.intern probably isn't necessary here, as compiled constants
# in a script/module/interactive line get interned, but it doesn't hurt.
a = sys.intern('abcd')
p = PyUnicodeObject.from_address(id(a))
assert p.length == 4
assert p.kind == p.PyUnicode_1BYTE_KIND
assert p.interned == p.SSTATE_INTERNED_MORTAL
assert p.compact
assert p.ascii
assert bytes(get_buffer(a)) == b'abcd'

b = ''.join(('a', 'b', 'c', 'd'))
p = PyUnicodeObject.from_address(id(b))
assert p.length == 4
assert p.kind == p.PyUnicode_1BYTE_KIND
assert p.interned == p.SSTATE_NOT_INTERNED
assert p.compact
assert bytes(get_buffer(b)) == b'abcd'

lat = '\u00e1b\u00e7d' # Latin-1, but not ASCII
p = PyUnicodeObject.from_address(id(lat))
assert p.length == 4
assert p.kind == p.PyUnicode_1BYTE_KIND
assert p.compact
assert not p.ascii
assert bytes(get_buffer(lat)) == lat.encode('latin-1')

u = sys.intern('\u00e1\u03b2\u00e7\u03b4')
p = PyUnicodeObject.from_address(id(u))
assert p.length == 4
assert p.kind == p.PyUnicode_2BYTE_KIND
assert p.interned == p.SSTATE_INTERNED_MORTAL
assert p.compact
assert ''.join(map(chr, get_buffer(u))) == u

e = '\U0001f92f'
p = PyUnicodeObject.from_address(id(e))
assert ''.join(map(chr, get_buffer(e))) == e

# There's no way to force UTF-8 caching from within Python, so...
PyUnicode_AsUTF8AndSize = ctypes.pythonapi.PyUnicode_AsUTF8AndSize
PyUnicode_AsUTF8AndSize.argtypes = (ctypes.py_object,
                                    ctypes.POINTER(ctypes.c_ssize_t))
PyUnicode_AsUTF8AndSize.restype = ctypes.c_char_p
PyUnicode_AsUTF8AndSize(e, None)
assert p.utf8_length == 4
assert p.utf8 == b'\xf0\x9f\xa4\xaf'

# There's also no way to force legacy strings from within Python, so...
PyUnicode_FromUnicode = ctypes.pythonapi.PyUnicode_FromUnicode
PyUnicode_FromUnicode.argtypes = (ctypes.c_wchar_p, ctypes.c_ssize_t)
PyUnicode_FromUnicode.restype = ctypes.py_object
leg = PyUnicode_FromUnicode(None, 4)
# The reason we defined wstr as POINTER(wchar) instead of wchar_p is
# that assigning char by char is the main point of the field.
p = PyUnicodeObject.from_address(id(leg))
for i in range(4):
    p.wstr[i] = u[i]
# Now we have a legacy non-ready string. Although there's not much you
# can do with one of those, we can at least verify that's what it is:
assert not p.compact
assert not p.ready
assert p.kind == PyUnicodeObject.PyUnicode_WCHAR_KIND
assert p.wstr_length == 4
# To make it usable, we have to call PyUnicode_READY, which is a macro,
# but it ultimately (if valid and necessary) calls _PyUnicode_Ready.
_PyUnicode_Ready = ctypes.pythonapi._PyUnicode_Ready
_PyUnicode_Ready.argtypes = (ctypes.py_object,)
_PyUnicode_Ready.restype = ctypes.c_int
assert _PyUnicode_Ready(leg) == 0
# The result is a legacy ready string. It's probably a 2-byte kind, but
# I'm not sure we can rely on that.
assert not p.compact
assert p.ready
assert p.kind != PyUnicodeObject.PyUnicode_WCHAR_KIND
assert p.length == 4
assert p.wstr_length == 0
# Note that the buffer is now a pointer rather than an array, so we
# need to carefully truncate it at p.length
assert ''.join(map(chr, get_buffer(leg)[:p.length])) == leg
# We can still UTF-8 it and get that cached
PyUnicode_AsUTF8AndSize(leg, None)
assert p.utf8_length == 8
assert p.utf8 == u.encode('utf8')

