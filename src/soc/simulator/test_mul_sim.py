from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
import unittest
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_enums import (Function, MicrOp,
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
from soc.config.endian import bigendian



class MulTestCases(FHDLTestCase):
    test_data = []

    def __init__(self, name="div"):
        super().__init__(name)
        self.test_name = name

    def tst_mullw(self):
        lst = ["addi 1, 0, 0x5678",
               "addi 2, 0, 0x1234",
               "mullw 3, 1, 2"]
        self.run_tst_program(Program(lst, bigendian), [3])

    def test_mullwo(self):
        lst = ["addi 1, 0, 0x5678",
               "neg 1, 1",
               "addi 2, 0, 0x1234",
               "neg 2, 2",
               "mullwo 3, 1, 2"]
        self.run_tst_program(Program(lst, bigendian), [3])

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None,
                                    initial_mem=None):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs, 0,
                                            initial_mem, 0)
        self.test_data.append(tc)


class MulDecoderTestCase(DecoderBase, MulTestCases):
    pass


if __name__ == "__main__":
    unittest.main()
