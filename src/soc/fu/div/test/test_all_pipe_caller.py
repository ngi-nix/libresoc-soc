import random
import unittest
from soc.simulator.program import Program
from soc.config.endian import bigendian

from soc.fu.test.common import TestCase
from soc.fu.div.test.runner import DivRunner


class DivTestLong(unittest.TestCase):
    test_data = []
    def __init__(self, name):
        super().__init__(name)
        for n, v in self.__class__.__dict__.items():
            if n.startswith("test") and callable(v):
                self._current_test_name = n
                v(self)

    def run_test_program(self, prog, initial_regs=None, initial_sprs=None):
        tc = TestCase(prog, self._current_test_name,
                      initial_regs, initial_sprs)
        self.test_data.append(tc)

    def test_all(self):
        instrs = []
        for width in ("w", "d"):
            for sign in ("", "u"):
                for ov in ("", "o"):
                    for cnd in ("", "."):
                        instrs += ["div" + width + sign + ov + cnd,
                                   "div" + width + "e" + sign + ov + cnd]
            for sign in ("s", "u"):
                instrs += ["mod" + sign + width]
        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
        ]
        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            for ra in test_values:
                for rb in test_values:
                    initial_regs = [0] * 32
                    initial_regs[1] = ra
                    initial_regs[2] = rb
                    # use "with" so as to close the files used
                    with Program(l, bigendian) as prog:
                        self.run_test_program(prog, initial_regs)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(DivRunner(DivTestLong.test_data, DivPipeKind.DivPipeCore))
    suite.addTest(DivRunner(DivTestLong.test_data, DivPipeKind.FSMDivCore))
    suite.addTest(DivRunner(DivTestLong.test_data, DivPipeKind.SimOnly))


    runner = unittest.TextTestRunner()
    runner.run(suite)

