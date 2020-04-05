import unittest
from copy import copy

def check_extsign(a, b):
    if b.bits != 256:
        return b
    return SelectableInt(b.value, a.bits)


class SelectableInt:
    def __init__(self, value, bits):
        mask = (1 << bits) - 1
        self.value = value & mask
        self.bits = bits

    def __add__(self, b):
        if isinstance(b, int):
            b = SelectableInt(b, self.bits)
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value + b.value, self.bits)

    def __sub__(self, b):
        if isinstance(b, int):
            b = SelectableInt(b, self.bits)
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value - b.value, self.bits)

    def __mul__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value * b.value, self.bits)

    def __div__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value / b.value, self.bits)

    def __mod__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value % b.value, self.bits)

    def __or__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value | b.value, self.bits)

    def __and__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value & b.value, self.bits)

    def __xor__(self, b):
        b = check_extsign(self, b)
        assert b.bits == self.bits
        return SelectableInt(self.value ^ b.value, self.bits)

    def __invert__(self):
        return SelectableInt(~self.value, self.bits)

    def __neg__(self):
        return SelectableInt(~self.value + 1, self.bits)

    def __getitem__(self, key):
        if isinstance(key, int):
            assert key < self.bits, "key %d accessing %d" % (key, self.bits)
            assert key >= 0
            key = self.bits - (key + 1)

            value = (self.value >> key) & 1
            return SelectableInt(value, 1)
        elif isinstance(key, slice):
            assert key.step is None or key.step == 1
            assert key.start < key.stop
            assert key.start >= 0
            assert key.stop <= self.bits

            stop = self.bits - key.start
            start = self.bits - key.stop

            bits = stop - start + 1
            mask = (1 << bits) - 1
            value = (self.value >> start) & mask
            return SelectableInt(value, bits)

    def __setitem__(self, key, value):
        if isinstance(key, int):
            assert key < self.bits
            assert key >= 0
            key = self.bits - (key + 1)
            if isinstance(value, SelectableInt):
                assert value.bits == 1
                value = value.value

            value = value << key
            mask = 1 << key
            self.value = (self.value & ~mask) | (value & mask)
        elif isinstance(key, slice):
            assert key.step is None or key.step == 1
            assert key.start < key.stop
            assert key.start >= 0
            assert key.stop <= self.bits

            stop = self.bits - key.start
            start = self.bits - key.stop

            bits = stop - start + 1
            if isinstance(value, SelectableInt):
                assert value.bits == bits, "%d into %d" % (value.bits, bits)
                value = value.value
            mask = ((1 << bits) - 1) << start
            value = value << start
            self.value = (self.value & ~mask) | (value & mask)

    def __ge__(self, other):
        if isinstance(other, SelectableInt):
            other = check_extsign(self, other)
            assert other.bits == self.bits
            other = other.value
        if isinstance(other, int):
            return other >= self.value
        assert False

    def __le__(self, other):
        if isinstance(other, SelectableInt):
            other = check_extsign(self, other)
            assert other.bits == self.bits
            other = other.value
        if isinstance(other, int):
            return onebit(other <= self.value)
        assert False

    def __gt__(self, other):
        if isinstance(other, SelectableInt):
            other = check_extsign(self, other)
            assert other.bits == self.bits
            other = other.value
        if isinstance(other, int):
            return onebit(other > self.value)
        assert False

    def __lt__(self, other):
        if isinstance(other, SelectableInt):
            other = check_extsign(self, other)
            assert other.bits == self.bits
            other = other.value
        if isinstance(other, int):
            return onebit(other < self.value)
        assert False

    def __eq__(self, other):
        if isinstance(other, SelectableInt):
            other = check_extsign(self, other)
            assert other.bits == self.bits
            other = other.value
        if isinstance(other, int):
            return onebit(other == self.value)
        assert False

    def narrow(self, bits):
        assert bits <= self.bits
        return SelectableInt(self.value, bits)

    def __bool__(self):
        return self.value != 0

    def __repr__(self):
        return "SelectableInt(value=0x{:x}, bits={})".format(self.value,
                                                           self.bits)

def onebit(bit):
    return SelectableInt(1 if bit else 0, 1)

def selectltu(lhs, rhs):
    """ less-than (unsigned)
    """
    if isinstance(rhs, SelectableInt):
        rhs = rhs.value
    return onebit(lhs.value < rhs)

def selectgtu(lhs, rhs):
    """ greater-than (unsigned)
    """
    if isinstance(rhs, SelectableInt):
        rhs = rhs.value
    return onebit(lhs.value > rhs)


# XXX this probably isn't needed...
def selectassign(lhs, idx, rhs):
    if isinstance(idx, tuple):
        if len(idx) == 2:
            lower, upper = idx
            step = None
        else:
            lower, upper, step = idx
        toidx = range(lower, upper, step)
        fromidx = range(0, upper-lower, step) # XXX eurgh...
    else:
        toidx = [idx]
        fromidx = [0]
    for t, f in zip(toidx, fromidx):
        lhs[t] = rhs[f]


def selectconcat(*args, repeat=1):
    if repeat != 1 and len(args) == 1 and isinstance(args[0], int):
        args = [SelectableInt(args[0], 1)]
    if repeat != 1: # multiplies the incoming arguments
        tmp = []
        for i in range(repeat):
            tmp += args
        args = tmp
    res = copy(args[0])
    for i in args[1:]:
        assert isinstance(i, SelectableInt), "can only concat SIs, sorry"
        res.bits += i.bits
        res.value = (res.value << i.bits) | i.value
    print ("concat", repeat, res)
    return res


class SelectableIntTestCase(unittest.TestCase):
    def test_arith(self):
        a = SelectableInt(5, 8)
        b = SelectableInt(9, 8)
        c = a + b
        d = a - b
        e = a * b
        f = -a
        self.assertEqual(c.value, a.value + b.value)
        self.assertEqual(d.value, (a.value - b.value) & 0xFF)
        self.assertEqual(e.value, (a.value * b.value) & 0xFF)
        self.assertEqual(f.value, (-a.value) & 0xFF)
        self.assertEqual(c.bits, a.bits)
        self.assertEqual(d.bits, a.bits)
        self.assertEqual(e.bits, a.bits)

    def test_logic(self):
        a = SelectableInt(0x0F, 8)
        b = SelectableInt(0xA5, 8)
        c = a & b
        d = a | b
        e = a ^ b
        f = ~a
        self.assertEqual(c.value, a.value & b.value)
        self.assertEqual(d.value, a.value | b.value)
        self.assertEqual(e.value, a.value ^ b.value)
        self.assertEqual(f.value, 0xF0)

    def test_get(self):
        a = SelectableInt(0xa2, 8)
        # These should be big endian
        self.assertEqual(a[7], 0)
        self.assertEqual(a[0:4], 10)
        self.assertEqual(a[4:8], 2)

    def test_set(self):
        a = SelectableInt(0x5, 8)
        a[7] = SelectableInt(0, 1)
        self.assertEqual(a, 4)
        a[4:8] = 9
        self.assertEqual(a, 9)
        a[0:4] = 3
        self.assertEqual(a, 0x39)
        a[0:4] = a[4:8]
        self.assertEqual(a, 0x199)

    def test_concat(self):
        a = SelectableInt(0x1, 1)
        c = selectconcat(a, repeat=8)
        self.assertEqual(c, 0xff)
        self.assertEqual(c.bits, 8)
        a = SelectableInt(0x0, 1)
        c = selectconcat(a, repeat=8)
        self.assertEqual(c, 0x00)
        self.assertEqual(c.bits, 8)

    def test_repr(self):
        for i in range(65536):
            a = SelectableInt(i, 16)
            b = eval(repr(a))
            self.assertEqual(a, b)

if __name__ == "__main__":
    unittest.main()
