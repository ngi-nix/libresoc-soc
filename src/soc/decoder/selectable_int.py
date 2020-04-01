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

            value = (self.value >> key) & 1
            return SelectableInt(value, 1)
        elif isinstance(key, slice):
            assert key.step is None or key.step == 1
            assert key.start < key.stop
            assert key.start >= 0
            assert key.stop <= self.bits

            bits = key.stop - key.start
            mask = (1 << bits) - 1
            value = (self.value >> key.start) & mask
            return SelectableInt(value, bits)
    
    def __eq__(self, other):
        if isinstance(other, SelectableInt):
            return other.value == self.value and other.bits == self.bits
        if isinstance(other, int):
            return other == self.value
        assert False

    def __repr__(self):
        return "SelectableInt(value={:x}, bits={})".format(self.value, self.bits)


class SelectableIntTestCase(unittest.TestCase):
    def test_add(self):
        a = SelectableInt(5, 8)
        b = SelectableInt(9, 8)
        c = a + b
        assert c.value == a.value + b.value
        assert c.bits == a.bits

    def test_select(self):
        a = SelectableInt(0xa5, 8)
        assert a[0] == 1
        assert a[0:1] == 1
        assert a[0:4] == 5
        assert a[4:8] == 10


if __name__ == "__main__":
    unittest.main()
