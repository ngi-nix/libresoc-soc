import inspect
import random
import unittest
from nmutil.formaltest import FHDLTestCase
from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay
from nmigen.cli import rtlil
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import XER_bits, Function
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA
from soc.config.endian import bigendian

from soc.fu.test.common import (TestCase, ALUHelpers)
from soc.fu.div.pipeline import DivBasePipe
from soc.fu.div.pipe_data import DivPipeSpec, DivPipeKind

from soc.fu.div.test.runner import (log_rand, get_cu_inputs,
                                    set_alu_inputs, DivRunner)


class DivTestCases(unittest.TestCase):
    test_data = []
    def __init__(self, name):
        super().__init__(name)

    def run_test_program(self, prog, initial_regs=None, initial_sprs=None):
        test_name = inspect.stack()[1][3] # name of caller of this function
        tc = TestCase(prog, test_name, initial_regs, initial_sprs)
        self.test_data.append(tc)

    def test_0_regression(self):
        for i in range(40):
            lst = ["divwo 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = 0xbc716835f32ac00c
            initial_regs[2] = 0xcdf69a7f7042db66
            with Program(lst, bigendian) as prog:
                self.run_test_program(prog, initial_regs)

    def test_1_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x10000000000000000-4
        initial_regs[2] = 0x10000000000000000-2
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_2_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffff9321
        initial_regs[2] = 0xffffffffffff7012
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_3_regression(self):
        lst = ["divwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1b8e32f2458746af
        initial_regs[2] = 0x6b8aee2ccf7d62e9
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_4_regression(self):
        lst = ["divw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_5_regression(self):
        lst = ["divw 3, 1, 2",
               "divwo. 6, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        initial_regs[4] = 0x1b8e32f2458746af
        initial_regs[5] = 0x6b8aee2ccf7d62e9
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_6_regression(self):
        # CR0 not getting set properly for this one
        # turns out that overflow is not set correctly in
        # fu/div/output_stage.py calc_overflow
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x61c1cc3b80f2a6af
        initial_regs[2] = 0x9dc66a7622c32bc0
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_7_regression(self):
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xf1791627e05e8096
        initial_regs[2] = 0xffc868bf4573da0b
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_8_regression(self):
        lst = ["divwu. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 18
        initial_regs[2] = 3
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_divw_by_zero_1(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0x0
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_divw_overflow2(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffffffffffff  # top bits don't seem to matter
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_divw_overflow3(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffff
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_divwuo_regression_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7591a398c4e32b68
        initial_regs[2] = 0x48674ab432867d69
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_divwuo_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x50
        initial_regs[2] = 0x2
        with Program(lst, bigendian) as prog:
            self.run_test_program(prog, initial_regs)

    def test_rand_divwu(self):
        insns = ["divwu", "divwu.", "divwuo", "divwuo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            with Program(lst, bigendian) as prog:
                self.run_test_program(prog, initial_regs)

    def test_rand_divw(self):
        insns = ["divw", "divw.", "divwo", "divwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            with Program(lst, bigendian) as prog:
                self.run_test_program(prog, initial_regs)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(DivRunner(DivTestCases.test_data, DivPipeKind.DivPipeCore))
    suite.addTest(DivRunner(DivTestCases.test_data, DivPipeKind.FSMDivCore))
    suite.addTest(DivRunner(DivTestCases.test_data, DivPipeKind.SimOnly))

    runner = unittest.TextTestRunner()
    runner.run(suite)

