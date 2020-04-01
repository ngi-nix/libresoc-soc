import unittest


class SelectableInt:
    def __init__(self, value, bits):
        self.value = value
        self.bits = bits

    def __add__(self, b):
        assert b.bits == self.bits
        return SelectableInt(self.value + b.value, self.bits)

    def __getitem__(self, key):
        if isinstance(key, int):
            assert key < self.bits
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

            bits = stop - start
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

            bits = stop - start
            if isinstance(value, SelectableInt):
                assert value.bits == bits
                value = value.value
            mask = ((1 << bits) - 1) << start
            value = value << start
            self.value = (self.value & ~mask) | (value & mask)

    def __eq__(self, other):
        if isinstance(other, SelectableInt):
            return other.value == self.value and other.bits == self.bits
        if isinstance(other, int):
            return other == self.value
        assert False

    def __repr__(self):
        return "SelectableInt(value={:x}, bits={})".format(self.value,
                                                           self.bits)


class SelectableIntTestCase(unittest.TestCase):
    def test_add(self):
        a = SelectableInt(5, 8)
        b = SelectableInt(9, 8)
        c = a + b
        assert c.value == a.value + b.value
        assert c.bits == a.bits

    def test_get(self):
        a = SelectableInt(0xa2, 8)
        # These should be big endian
        assert a[7] == 0
        assert a[0:4] == 10
        assert a[4:8] == 2

    def test_set(self):
        a = SelectableInt(0x5, 8)
        a[7] = SelectableInt(0, 1)
        self.assertEqual(a, 4)
        a[4:8] = 9
        self.assertEqual(a, 9)
        a[0:4] = 3
        self.assertEqual(a, 0x39)
        a[0:4] = a[4:8]
        self.assertEqual(a, 0x99)


if __name__ == "__main__":
    unittest.main()
