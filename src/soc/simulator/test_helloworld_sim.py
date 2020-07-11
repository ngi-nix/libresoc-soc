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
from soc.config.endian import bigendian


class HelloTestCases(FHDLTestCase):
    test_data = []

    def __init__(self, name="div"):
        super().__init__(name)
        self.test_name = name

    def test_microwatt_helloworld(self):
        lst = ["addis     1,0,0",
                "ori     1,1,0",
                "rldicr  1,1,32,31",
                "oris    1,1,0",
                "ori     1,1,7936",
                "addis     12,0,0",
                "ori     12,12,0",
                "rldicr  12,12,32,31",
                "oris    12,12,0",
                "ori     12,12,4116",
                "mtspr   9, 12",     # mtctr r12
                "bcctrl  20,0,0", # bctrl
                ]
        self.run_tst_program(Program(lst, bigendian),
                             [1,12], extra_break_addr=0x1014)

    def run_tst_program(self, prog, initial_regs=None, initial_sprs=None,
                                    initial_mem=None, extra_break_addr=None):
        initial_regs = [0] * 32
        tc = TestCase(prog, self.test_name, initial_regs, initial_sprs, 0,
                                            initial_mem, 0,
                                            extra_break_addr=extra_break_addr)
        self.test_data.append(tc)


class HelloDecoderTestCase(DecoderBase, HelloTestCases):
    pass


if __name__ == "__main__":
    unittest.main()
