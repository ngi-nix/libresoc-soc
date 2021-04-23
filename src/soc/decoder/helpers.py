import unittest
from openpower.decoder.selectable_int import SelectableInt, onebit
from nmutil.divmod import trunc_divs, trunc_rems
from operator import floordiv, mod
from openpower.decoder.selectable_int import selectltu as ltu
from openpower.decoder.selectable_int import selectgtu as gtu
from openpower.decoder.selectable_int import check_extsign

trunc_div = floordiv
trunc_rem = mod
DIVS = trunc_divs
MODS = trunc_rems

"""
Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=324 - add trunc_div and trunc_rem
"""


def exts(value, bits):
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def EXTS(value):
    """ extends sign bit out from current MSB to all 256 bits
    """
    assert isinstance(value, SelectableInt)
    return SelectableInt(exts(value.value, value.bits) & ((1 << 256)-1), 256)


def EXTS64(value):
    """ extends sign bit out from current MSB to 64 bits
    """
    assert isinstance(value, SelectableInt)
    return SelectableInt(exts(value.value, value.bits) & ((1 << 64)-1), 64)


def EXTS128(value):
    """ extends sign bit out from current MSB to 128 bits
    """
    assert isinstance(value, SelectableInt)
    return SelectableInt(exts(value.value, value.bits) & ((1 << 128)-1), 128)


# signed version of MUL
def MULS(a, b):
    if isinstance(b, int):
        b = SelectableInt(b, self.bits)
    b = check_extsign(a, b)
    a_s = a.value & (1 << (a.bits-1)) != 0
    b_s = b.value & (1 << (b.bits-1)) != 0
    result = abs(a) * abs(b)
    print("MULS", result, a_s, b_s)
    if a_s == b_s:
        return result
    return -result


# XXX should this explicitly extend from 32 to 64?
def EXTZ64(value):
    if isinstance(value, SelectableInt):
        value = value.value
    return SelectableInt(value & ((1 << 32)-1), 64)


def rotl(value, bits, wordlen):
    if isinstance(bits, SelectableInt):
        bits = bits.value
    mask = (1 << wordlen) - 1
    bits = bits & (wordlen - 1)
    return ((value << bits) | (value >> (wordlen-bits))) & mask


def ROTL64(value, bits):
    return rotl(value, bits, 64)


def ROTL32(value, bits):
    if isinstance(value, SelectableInt):
        value = SelectableInt(value.value, 64)
    return rotl(value | (value << 32), bits, 64)


def MASK(x, y):
    if isinstance(x, SelectableInt):
        x = x.value
    if isinstance(y, SelectableInt):
        y = y.value
    if x < y:
        x = 64-x
        y = 63-y
        mask_a = ((1 << x) - 1) & ((1 << 64) - 1)
        mask_b = ((1 << y) - 1) & ((1 << 64) - 1)
    elif x == y:
        return 1 << (63-x)
    else:
        x = 64-x
        y = 63-y
        mask_a = ((1 << x) - 1) & ((1 << 64) - 1)
        mask_b = (~((1 << y) - 1)) & ((1 << 64) - 1)
    return mask_a ^ mask_b


def ne(a, b):
    return onebit(a != b)


def eq(a, b):
    return onebit(a == b)


def gt(a, b):
    return onebit(a > b)


def ge(a, b):
    return onebit(a >= b)


def lt(a, b):
    return onebit(a < b)


def le(a, b):
    return onebit(a <= b)


def length(a):
    return len(a)


def undefined(v):
    """ function that, for Power spec purposes, returns undefined bits of
        the same shape as the input bits.  however, for purposes of matching
        POWER9's behavior returns the input bits unchanged.  this effectively
        "marks" (tags) locations in the v3.0B spec that need to be submitted
        for clarification.
    """
    return v

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

        # li 2, 5
        # slw 1, 1, 2
        self.assertHex(MASK(32, 63-5), 0xffffffe0)

        self.assertHex(MASK(32, 33), 0xc0000000)
        self.assertHex(MASK(32, 32), 0x80000000)
        self.assertHex(MASK(33, 33), 0x40000000)

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
        value_a = SelectableInt(0xdeadbeef, 32)  # r1
        value_b = SelectableInt(0x73123456, 32)  # r2
        value_c = SelectableInt(0x80000000, 32)  # r3

        # extswsli reg, 1, 0
        self.assertHex(EXTS64(value_a), 0xffffffffdeadbeef)
        # extswsli reg, 2, 0
        self.assertHex(EXTS64(value_b), SelectableInt(value_b.value, 64))
        # extswsli reg, 3, 0
        self.assertHex(EXTS64(value_c), 0xffffffff80000000)

    def assertHex(self, a, b):
        a_val = a
        if isinstance(a, SelectableInt):
            a_val = a.value
        b_val = b
        if isinstance(b, SelectableInt):
            b_val = b.value
        msg = "{:x} != {:x}".format(a_val, b_val)
        return self.assertEqual(a, b, msg)


if __name__ == '__main__':
    print(SelectableInt.__bases__)
    unittest.main()
