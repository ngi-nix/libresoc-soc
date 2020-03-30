import unittest
def exts(value, bits):
    sign = 1 << (bits - 1)
    return (value * (sign - 1)) - (value * sign)

def EXTS64(value):
    return exts(value, 64) & ((1<<64)-1)

def ROTL64(value, bits):
    mask = (1 << 64) - 1
    bits = bits & 63
    return ((value << bits) | (value >> (64-bits))) & mask

def mask(x, y):
    if x < y:
        x = 64-x
        y = 63-y
        mask_a = ((1<<x) - 1) & ((1<<64) - 1)
        mask_b = ((1<<y) - 1) & ((1<<64) - 1)
    else:
        x = 64-x
        y = 63-y
        mask_a = ((1<<x) - 1) & ((1<<64) - 1)
        mask_b = (~((1<<y) - 1)) & ((1<<64) - 1)
    return mask_a ^ mask_b


class HelperTests(unittest.TestCase):
    def test_mask(self):
        # Verified using rlwinm, rldicl, rldicr in qemu
        # rlwinm reg, 0, 5, 15
        self.assertHex(mask(5+32, 15+32), 0x7ff0000)
        # rlwinm reg, 0, 15, 5
        self.assertHex(mask(15+32, 5+32), 0xfffffffffc01ffff)
        self.assertHex(mask(30+32, 2+32), 0xffffffffe0000003)
        # rldicl reg, 0, 37
        self.assertHex(mask(37, 63), 0x7ffffff)
        self.assertHex(mask(10, 63), 0x3fffffffffffff)
        self.assertHex(mask(58, 63), 0x3f)
        # rldicr reg, 0, 37
        self.assertHex(mask(0, 37), 0xfffffffffc000000)
        self.assertHex(mask(0, 10), 0xffe0000000000000)
        self.assertHex(mask(0, 58), 0xffffffffffffffe0)
    def assertHex(self, a, b):
        msg = "{:x} != {:x}".format(a, b)
        return self.assertEqual(a, b, msg)

if __name__ == '__main__':
    unittest.main()
