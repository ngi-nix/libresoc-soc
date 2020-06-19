from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, InternalOp,
                                     In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, LdstLen, CryIn,
                                     single_bit_flags, Form, SPR,
                                     get_signal_name, get_csv)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.simulator.qemu import run_program
from soc.decoder.isa.all import ISA
from soc.fu.test.common import TestCase
from soc.simulator.test_sim import DecoderBase



class DivTestCases(FHDLTestCase):
    test_data = []

    def __init__(self, name="general"):
        super().__init__(name)
        self.test_name = name

    def test_0_divw(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "divw  3, 1, 2",
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def test_1_divw_byzero(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x0",
               "divw  3, 1, 2",
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def test_2_moduw(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "moduw  3, 1, 2",
               ]
        with Program(lst) as program:
            self.run_tst_program(program, [1, 2, 3])

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None,
                                    initial_mem=None):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs, 0,
                                            initial_mem, 0)
        self.test_data.append(tc)


class DecoderTestCase(DecoderBase, DivTestCases):
    pass


if __name__ == "__main__":
    unittest.main()
