from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.decoder.isa.caller import ISACaller, SVP64State
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
        svstate = SVP64State()
        svstate.vl[0:-1] = 2 # VL
        svstate.maxvl[0:-1] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self.assertEqual(sim.gpr(1), SelectableInt(0x5555, 64))

    def run_tst_program(self, prog, initial_regs=[0] * 32,
                              svstate=None):
        simulator = run_tst(prog, initial_regs, svstate=svstate)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
