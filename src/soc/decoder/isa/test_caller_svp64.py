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

    def test_sv_add(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111
        isa = SVP64Asm(['sv.add 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[1] = 0x5555
        expected_regs[2] = 0x3334

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_add_2(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       r1 is scalar so ENDS EARLY
        isa = SVP64Asm(['sv.add 1, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[1] = 0x5555

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_add_3(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       2 = 5 + 10  => 0x5432 = 0x4321+0x1111
        isa = SVP64Asm(['sv.add 1.v, 5, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[1] = 0x5555
        expected_regs[2] = 0x5432

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_add_cr(self):
        # adds when Rc=1:                               TODO CRs higher up
        #       1 = 5 + 9   => 0 = -1+1                 CR0=0b100
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111   CR1=0b010
        isa = SVP64Asm(['sv.add. 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0xffffffffffffffff
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x1
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[1] = 0
        expected_regs[2] = 0x3334

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            # XXX TODO, these need to move to higher range (offset)
            cr0_idx = SVP64CROffs.CR0
            cr1_idx = SVP64CROffs.CR1
            CR0 = sim.crl[cr0_idx].get_range().value
            CR1 = sim.crl[cr1_idx].get_range().value
            print ("CR0", CR0)
            print ("CR1", CR1)
            self._check_regs(sim, expected_regs)
            self.assertEqual(CR0, SelectableInt(2, 4))
            self.assertEqual(CR1, SelectableInt(4, 4))

    def run_tst_program(self, prog, initial_regs=[0] * 32,
                              svstate=None):
        simulator = run_tst(prog, initial_regs, svstate=svstate)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
