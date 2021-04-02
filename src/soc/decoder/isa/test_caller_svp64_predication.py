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

    def tst_sv_load_store(self):
        lst = SVP64Asm(["addi 1, 0, 0x0010",
                        "addi 2, 0, 0x0008",
                        "addi 5, 0, 0x1234",
                        "addi 6, 0, 0x1235",
                        "sv.stw 5.v, 0(1.v)",
                        "sv.lwz 9.v, 0(1.v)"])
        lst = list(lst)

        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, svstate=svstate)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(9), SelectableInt(0x1234, 64))
            self.assertEqual(sim.gpr(10), SelectableInt(0x1235, 64))

    def test_sv_extsw_intpred(self):
        # extsb, integer twin-pred mask: source is ~r3 (0b01), dest r3 (0b10)
        # works as follows, where any zeros indicate "skip element"
        #       - sources are 9 and 10
        #       - dests are 5 and 6
        #       - source mask says "pick first element from source (5)
        #       - dest mask says "pick *second* element from dest (10)
        #
        # therefore the operation that's carried out is:
        #       GPR(10) = extsb(GPR(5))
        #
        # this is a type of back-to-back VREDUCE and VEXPAND but it applies
        # to *operations*, not just MVs like in traditional Vector ISAs
        # ascii graphic:
        #
        #   reg num        0 1 2 3 4 5 6 7 8 9 10
        #   src ~r3=0b01                     Y N
        #                                    |
        #                              +-----+
        #                              |
        #   dest r3=0b10             N Y

        isa = SVP64Asm(['sv.extsb/sm=~r3/dm=r3 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b10   # predicate mask
        initial_regs[9] = 0x91   # source ~r3 is 0b01 so this will be used
        initial_regs[10] = 0x90  # this gets skipped
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[5] = 0x0                   # dest r3 is 0b10: skip
        expected_regs[6] = 0xffff_ffff_ffff_ff91 # 2nd bit of r3 is 1

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_extsw_intpred_dz(self):
        # extsb, integer twin-pred mask: dest is r3 (0b01), zeroing on dest
        isa = SVP64Asm(['sv.extsb/dm=r3/dz 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b01   # predicate mask (dest)
        initial_regs[5] = 0xfeed # going to be overwritten
        initial_regs[6] = 0xbeef # going to be overwritten (with zero)
        initial_regs[9] = 0x91   # dest r3 is 0b01 so this will be used
        initial_regs[10] = 0x90  # this gets read but the output gets zero'd
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[5] = 0xffff_ffff_ffff_ff91 # dest r3 is 0b01: store
        expected_regs[6] = 0                     # 2nd bit of r3 is 1: zero

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_add_intpred(self):
        # adds, integer predicated mask r3=0b10
        #       1 = 5 + 9   => not to be touched (skipped)
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111
        isa = SVP64Asm(['sv.add/m=r3 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[1] = 0xbeef   # not to be altered
        initial_regs[3] = 0b10   # predicate mask
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
        expected_regs[1] = 0xbeef
        expected_regs[2] = 0x3334

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def test_sv_add_cr_pred(self):
        # adds, CR predicated mask CR4.eq = 1, CR5.eq = 0, invert (ne)
        #       1 = 5 + 9   => not to be touched (skipped)
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111
        isa = SVP64Asm(['sv.add/m=ne 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[1] = 0xbeef   # not to be altered
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
        expected_regs[1] = 0xbeef
        expected_regs[2] = 0x3334

        # set up CR predicate - CR4.eq=0 and CR5.eq=1
        cr = (0b0010) << ((7-4)*4) # CR5.eq (we hope)

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate,
                                       initial_cr=cr)
            self._check_regs(sim, expected_regs)

    def tst_sv_add_2(self):
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

    def tst_sv_add_3(self):
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

    def tst_sv_add_vl_0(self):
        # adds:
        #       none because VL is zer0
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
        # SVSTATE (in this case, VL=0)
        svstate = SVP64State()
        svstate.vl[0:7] = 0 # VL
        svstate.maxvl[0:7] = 0 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)

        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def tst_sv_add_cr(self):
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

    def test_intpred_vcompress(self):
        #   reg num        0 1 2 3 4 5 6 7 8 9 10 11
        #   src r3=0b101                     Y  N  Y
        #                                    |     |
        #                            +-------+     |
        #                            | +-----------+
        #                            | |
        #   dest always              Y Y Y

        isa = SVP64Asm(['sv.extsb/sm=r3 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b101  # predicate mask
        initial_regs[9] = 0x90   # source r3 is 0b101 so this will be used
        initial_regs[10] = 0x91  # this gets skipped
        initial_regs[11] = 0x92  # source r3 is 0b101 so this will be used
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))
        # copy before running
        expected_regs = deepcopy(initial_regs)
        expected_regs[5] = 0xffff_ffff_ffff_ff90  # (from r9)
        expected_regs[6] = 0xffff_ffff_ffff_ff92  # (from r11)
        expected_regs[7] = 0x0  # (VL loop runs out before we can use it)
        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program, initial_regs, svstate)
            self._check_regs(sim, expected_regs)

    def run_tst_program(self, prog, initial_regs=None,
                              svstate=None,
                              initial_cr=0):
        if initial_regs is None:
            initial_regs = [0] * 32
        simulator = run_tst(prog, initial_regs, svstate=svstate,
                            initial_cr=initial_cr)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
