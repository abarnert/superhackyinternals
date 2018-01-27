# superhackyinternals
Some ctypes wrappers to explore the CPython internal representations from inside

You really don't want to use anything here, except for learning purposes.

If you do, keep in mind that we're dealing with interpreter internals that can
change between versions, or even compile-time configuration settings.

`PyObject` and `PyVarObject` should be safe unless you compiled Python with
`_PyObject_HEAD_EXTRA` trace debugging, but `PyLongObject` can be wrong if
you're using 15-bit rather than 30-bit digits, and `PyUnicodeObject`, you'll
need to completely change everything to go back to Python 3.2 or 2.7 or 
something.

## Integers

An `int` is basically just an array of 30-bit digits, which is pretty easy
to understand.

Here's a clever use of looking at the raw digits of an int:

    _TABLE16 = [0] * (2**16)
    for i in range(len(_TABLE16)):
        _TABLE16[i] = (i & 1) + _TABLE16[i >> 1]
    def popcount(n):
        raw = PyLongObject.from_address(id(n))
        digits = ctypes.addressof(raw.ob_digit)
        digits16 = (ctypes.c_uint16 * (abs(raw.ob_size)*2)).from_address(digits)
        return sum(_TABLE16[digit] for digit in digits16)

Of course by "clever" I mean not just confusing, but also slow. Not deadly
slow of course, but slower than `bin(n).count('1')`, and even slower than
looping over `total += _TABLE16[n&0xffff]; n>>=16`. If you `numpy` it 
with `frombuffer` and `sum(_TABLE16[array])` it does get marginally faster
than the latter, but still slower than the former. Using the famous
bit-twiddling tricks that you still find online is slower than a 16-bit
lookup table on most modern systems, but feel free to try that too. Anyway,
if you really need speed here, you'd want to use `gmpy`, not `numpy`, and
at that point, just use its native `int` to `mpz` constructor, or, better, 
just work in `mpz` objects in the first place.

An even more clever (read: bad) use of accessing the raw digits of an int is 
redefining numbers. This won't crash anything as long as you stay away from 
the small ints (as of 3.7, I believe they can't be configured to go over 
`2**9==512`), but obviously it gets a bit confusing.

    >>> x = 1000
    >>> PyLongObject.from_address(id(x)).digits()[0] += 1
    >>> print(1000)
    1001

Of course the number `1000` from a different module may be 1001, or may
still be 1000, and even in the interactive prompt, it may revert to 1000
once the last reference goes away. (But look at `sys.getrefcount(1000)`,
or of course the `ob_refcount` directly, and you may be surprised,
especially if you're using `IPython`.)

## Strings

Byte strings (`bytes`, `bytearray`) are pretty easy. The former just has
the bytes embedded in the struct (but with an extra null terminator); the
latter has a pointer to a buffer, and an extra pointer to within that 
buffer and an extra length to handle slack on both sides. (To get slack
on the left, delete some initial elements.)

Unicode strings are a lot more complicated. There are four different ways 
of storing them. You may have heard of the clever 1-byte/2-byte/4-byte
thing--but together, they consitute just one of those four ways. Pure ASCII 
strings (as opposed to only pure Latin-1, meaning there's no need for a 
UTF-8 cache) use a slightly format. Strings created by legacy C API 
functions use a whole different way of storing things, plus another whole 
different one while the creator is still building them and hasn't marked 
them ready yet.

Of course `ctypes` isn't great at handling things where you may be 
dealing with either a pointer to or an array of any of four types, some 
of which `ctypes` considers string types and others not. So be careful
with things like the `get_buffer` function; they may not return what you
expected.

Overall, the best use of `PyUnicodeObject` is probably crashing your
interpreter, but see the included test code for all the fun stuff you can 
do.

Also see the `stringy.py` script for a combination of `pythonapi` and
`internals` code to screw with strings in a way that's simple from the
C API but normally not doable from inside Python.

## Other types

As examples, I think these types cover everything you'd need to figure
out any other type later ("you" here meaning "me in the future, the next
time I've forgotten how strings work under the covers...).

The only other builtin with interestingly complicated internals I can
think of is `dict`.

There are some types with key attributes that are immutable from within 
the language. In many cases, it's easier to just `pythonapi` the C API 
functions (e.g., with `frame`, `cell`, `function`, `code`, etc.), but 
there are a few things that are immutable even from the C API (e.g., 
monkeypatching the slots of a builtin `type`), and you can hack them up
the same way as `int` and `str`.
