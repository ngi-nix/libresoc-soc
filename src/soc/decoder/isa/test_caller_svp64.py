from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.decoder.isa.caller import ISACaller, inject
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.orderedset import OrderedSet
from soc.decoder.isa.all import ISA
from soc.decoder.isa.test_caller import Register, run_tst
from soc.sv.trans.svp64 import SVP64Asm


class DecoderTestCase(FHDLTestCase):

    def test_sv_add(self):
        isa = SVP64Asm(['sv.add 1, 2, 3'
                       ])

        lst = list(isa)
        print ("listing", lst)
        initial_regs = [0] * 32
        initial_regs[3] = 0x1234
        initial_regs[2] = 0x4321
        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs)
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def run_tst_program(self, prog, initial_regs=[0] * 32):
        simulator = run_tst(prog, initial_regs)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
