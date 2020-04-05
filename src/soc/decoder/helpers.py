import unittest
from soc.decoder.selectable_int import SelectableInt


def exts(value, bits):
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def EXTS(value):
    """ extends sign bit out from current MSB to all 256 bits
    """
    assert isinstance(value, SelectableInt)
    return exts(value.value, value.bits)

def EXTS64(value):
    """ extends sign bit out from current MSB to 64 bits
    """
    assert isinstance(value, SelectableInt)
    return SelectableInt(exts(value.value, value.bits) & ((1 << 64)-1), 64)


# XXX should this explicitly extend from 32 to 64?
def EXTZ64(value):
    if isinstance(value, SelectableInt):
        value = value.value
    return SelectableInt(value & ((1<<32)-1), 64)


def rotl(value, bits, wordlen):
    mask = (1 << wordlen) - 1
    bits = bits & (wordlen - 1)
    return ((value << bits) | (value >> (wordlen-bits))) & mask


def ROTL64(value, bits):
    return rotl(value, bits, 64)


def ROTL32(value, bits):
    return rotl(value, bits, 32)


def MASK(x, y):
    if x < y:
        x = 64-x
        y = 63-y
        mask_a = ((1 << x) - 1) & ((1 << 64) - 1)
        mask_b = ((1 << y) - 1) & ((1 << 64) - 1)
    else:
        x = 64-x
        y = 63-y
        mask_a = ((1 << x) - 1) & ((1 << 64) - 1)
        mask_b = (~((1 << y) - 1)) & ((1 << 64) - 1)
    return mask_a ^ mask_b


# For these tests I tried to find power instructions that would let me
# isolate each of these helper operations. So for instance, when I was
# testing the MASK() function, I chose rlwinm and rldicl because if I
# set the shift equal to 0 and passed in a value of all ones, the
# result I got would be exactly the same as the output of MASK()

class HelperTests(unittest.TestCase):
    def test_MASK(self):
        # Verified using rlwinm, rldicl, rldicr in qemu
        # li 1, -1
        # rlwinm reg, 1, 0, 5, 15
        self.assertHex(MASK(5+32, 15+32), 0x7ff0000)
        # rlwinm reg, 1, 0, 15, 5
        self.assertHex(MASK(15+32, 5+32), 0xfffffffffc01ffff)
        self.assertHex(MASK(30+32, 2+32), 0xffffffffe0000003)
        # rldicl reg, 1, 0, 37
        self.assertHex(MASK(37, 63), 0x7ffffff)
        self.assertHex(MASK(10, 63), 0x3fffffffffffff)
        self.assertHex(MASK(58, 63), 0x3f)
        # rldicr reg, 1, 0, 37
        self.assertHex(MASK(0, 37), 0xfffffffffc000000)
        self.assertHex(MASK(0, 10), 0xffe0000000000000)
        self.assertHex(MASK(0, 58), 0xffffffffffffffe0)

    def test_ROTL64(self):
        # r1 = 0xdeadbeef12345678
        value = 0xdeadbeef12345678

        # rldicl reg, 1, 10, 0
        self.assertHex(ROTL64(value, 10), 0xb6fbbc48d159e37a)
        # rldicl reg, 1, 35, 0
        self.assertHex(ROTL64(value, 35), 0x91a2b3c6f56df778)
        self.assertHex(ROTL64(value, 58), 0xe37ab6fbbc48d159)
        self.assertHex(ROTL64(value, 22), 0xbbc48d159e37ab6f)

    def test_ROTL32(self):
        # r1 = 0xdeadbeef
        value = 0xdeadbeef

        # rlwinm reg, 1, 10, 0, 31
        self.assertHex(ROTL32(value, 10), 0xb6fbbf7a)
        # rlwinm reg, 1, 17, 0, 31
        self.assertHex(ROTL32(value, 17), 0x7ddfbd5b)
        self.assertHex(ROTL32(value, 25), 0xdfbd5b7d)
        self.assertHex(ROTL32(value, 30), 0xf7ab6fbb)

    def test_EXTS64(self):
        value_a = 0xdeadbeef  # r1
        value_b = 0x73123456  # r2
        value_c = 0x80000000  # r3

        # extswsli reg, 1, 0
        self.assertHex(EXTS64(value_a), 0xffffffffdeadbeef)
        # extswsli reg, 2, 0
        self.assertHex(EXTS64(value_b), value_b)
        # extswsli reg, 3, 0
        self.assertHex(EXTS64(value_c), 0xffffffff80000000)

    def assertHex(self, a, b):
        msg = "{:x} != {:x}".format(a, b)
        return self.assertEqual(a, b, msg)


if __name__ == '__main__':
    unittest.main()
