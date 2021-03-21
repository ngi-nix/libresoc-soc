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
from soc.consts import SVP64CROffs
from copy import deepcopy

class DecoderTestCase(FHDLTestCase):

    def _check_regs(self, sim, expected):
        for i in range(32):
            self.assertEqual(sim.gpr(i), SelectableInt(expected[i], 64))

    def test_setvl_1(self):
        lst = SVP64Asm(["setvl 1, 0, 9, 1, 1",
                        ])
        lst = list(lst)

        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, svstate=svstate)
            print ("SVSTATE after", bin(sim.svstate.spr.asint()))
            print ("        vl", bin(sim.svstate.vl.asint(True)))
            print ("        mvl", bin(sim.svstate.maxvl.asint(True)))
            self.assertEqual(sim.svstate.vl.asint(True), 10)
            self.assertEqual(sim.svstate.maxvl.asint(True), 10)
            self.assertEqual(sim.svstate.maxvl.asint(True), 10)
            print("      gpr1", sim.gpr(1))
            self.assertEqual(sim.gpr(1), SelectableInt(10, 64))


    def test_sv_add(self):
        # sets VL=2 then adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111
        isa = SVP64Asm(["setvl 3, 0, 1, 1, 1",
                        'sv.add 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223

        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[1] = 0x5555
        expected_regs[2] = 0x3334
        expected_regs[3] = 2       # setvl places copy of VL here

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs)
            self._check_regs(sim, expected_regs)

    def run_tst_program(self, prog, initial_regs=None,
                              svstate=None):
        if initial_regs is None:
            initial_regs = [0] * 32
        simulator = run_tst(prog, initial_regs, svstate=svstate)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()

