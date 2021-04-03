from soc.fu.test.common import (TestAccumulatorBase, skip_case)
from soc.config.endian import bigendian
from soc.simulator.program import Program
from soc.decoder.isa.caller import SVP64State
from soc.sv.trans.svp64 import SVP64Asm


class SVP64ALUTestCase(TestAccumulatorBase):

    def case_1_sv_add(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        #       2 = 6 + 10  => 0x3334 = 0x2223 + 0x1111
        isa = SVP64Asm(['sv.add 1.v, 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2  # VL
        svstate.maxvl[0:7] = 2  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_2_sv_add_scalar(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        isa = SVP64Asm(['sv.add 1, 5, 9'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[5] = 0x4321
        svstate = SVP64State()
        # SVSTATE (in this case, VL=1, so everything works as in v3.0B)
        svstate.vl[0:7] = 1  # VL
        svstate.maxvl[0:7] = 1  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    # This case helps checking the encoding of the Extra field
    # It was built so the v3.0b registers are: 3, 2, 1
    # and the Extra field is: 101.110.111
    # The expected SVP64 register numbers are: 13, 10, 7
    # Any mistake in decoding will probably give a different answer
    def case_3_sv_check_extra(self):
        # adds:
        #       13 = 10 + 7   => 0x4242 = 0x1230 + 0x3012
        isa = SVP64Asm(['sv.add 13.v, 10.v, 7.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[7] = 0x3012
        initial_regs[10] = 0x1230
        svstate = SVP64State()
        # SVSTATE (in this case, VL=1, so everything works as in v3.0B)
        svstate.vl[0:7] = 1  # VL
        svstate.maxvl[0:7] = 1  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_4_sv_add_(self):
        # adds when Rc=1:                               TODO CRs higher up
        #       1 = 5 + 9   => 0 = -1+1                 CR0=0b100
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111   CR1=0b010

        isa = SVP64Asm(['sv.add. 1.v, 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0xffffffffffffffff
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x1
        initial_regs[6] = 0x2223

        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2  # VL
        svstate.maxvl[0:7] = 2  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_5_sv_check_vl_0(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        isa = SVP64Asm([
            'sv.add 13.v, 10.v, 7.v',  # skipped, because VL == 0
            'add 1, 5, 9'
        ])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[5] = 0x4321
        initial_regs[7] = 0x3012
        initial_regs[10] = 0x1230
        svstate = SVP64State()
        # SVSTATE (in this case, VL=0, so vector instructions are skipped)
        svstate.vl[0:7] = 0  # VL
        svstate.maxvl[0:7] = 0  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    # checks that SRCSTEP was reset properly after an SV instruction
    def case_6_sv_add_multiple(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        #       2 = 6 + 10  => 0x3334 = 0x2223 + 0x1111
        #       3 = 7 + 11  => 0x4242 = 0x3012 + 0x1230
        #      13 = 10 + 7  => 0x2341 = 0x1111 + 0x1230
        #      14 = 11 + 8  => 0x3012 = 0x3012 + 0x0000
        #      15 = 12 + 9  => 0x1234 = 0x0000 + 0x1234
        isa = SVP64Asm([
            'sv.add 1.v, 5.v, 9.v',
            'sv.add 13.v, 10.v, 7.v'
        ])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[11] = 0x3012
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        initial_regs[7] = 0x1230
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_7_sv_add_2(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        #       r1 is scalar so ENDS EARLY
        isa = SVP64Asm(['sv.add 1, 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2  # VL
        svstate.maxvl[0:7] = 2  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))
        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_8_sv_add_3(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       2 = 5 + 10  => 0x5432 = 0x4321+0x1111
        isa = SVP64Asm(['sv.add 1.v, 5, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2  # VL
        svstate.maxvl[0:7] = 2  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))
        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_9_sv_extsw_intpred(self):
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

        # expected results:
        # r5 = 0x0                   dest r3 is 0b10: skip
        # r6 = 0xffff_ffff_ffff_ff91 2nd bit of r3 is 1
        isa = SVP64Asm(['sv.extsb/sm=~r3/dm=r3 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b10   # predicate mask
        initial_regs[9] = 0x91   # source ~r3 is 0b01 so this will be used
        initial_regs[10] = 0x90  # this gets skipped
        # SVSTATE (in this case, VL=2)
        svstate = SVP64State()
        svstate.vl[0:7] = 2  # VL
        svstate.maxvl[0:7] = 2  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_10_intpred_vcompress(self):
        #   reg num        0 1 2 3 4 5 6 7 8 9 10 11
        #   src r3=0b101                     Y  N  Y
        #                                    |     |
        #                            +-------+     |
        #                            | +-----------+
        #                            | |
        #   dest always              Y Y Y

        # expected results:
        # r5 = 0xffff_ffff_ffff_ff90 (from r9)
        # r6 = 0xffff_ffff_ffff_ff92 (from r11)
        # r7 = 0x0 (VL loop runs out before we can use it)
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

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_11_intpred_vexpand(self):
        #   reg num        0 1 2 3 4 5 6 7 8 9 10 11
        #   src always                       Y  Y  Y
        #                                    |  |
        #                            +-------+  |
        #                            |   +------+
        #                            |   |
        #   dest r3=0b101            Y N Y

        # expected results:
        # r5 = 0xffff_ffff_ffff_ff90 1st bit of r3 is 1
        # r6 = 0x0                   skip
        # r7 = 0xffff_ffff_ffff_ff91 3nd bit of r3 is 1
        isa = SVP64Asm(['sv.extsb/dm=r3 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b101  # predicate mask
        initial_regs[9] = 0x90   # source is "always", so this will be used
        initial_regs[10] = 0x91  # likewise
        initial_regs[11] = 0x92  # the VL loop runs out before we can use it
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    def case_12_sv_twinpred(self):
        #   reg num        0 1 2 3 4 5 6 7 8 9 10 11
        #   src r3=0b101                     Y  N  Y
        #                                    |
        #                              +-----+
        #                              |
        #   dest ~r3=0b010           N Y N

        # expected results:
        # r5 = 0x0                   dest ~r3 is 0b010: skip
        # r6 = 0xffff_ffff_ffff_ff90 2nd bit of ~r3 is 1
        # r7 = 0x0                   dest ~r3 is 0b010: skip
        isa = SVP64Asm(['sv.extsb/sm=r3/dm=~r3 5.v, 9.v'])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[3] = 0b101  # predicate mask
        initial_regs[9] = 0x90   # source r3 is 0b101 so this will be used
        initial_regs[10] = 0x91  # this gets skipped
        initial_regs[11] = 0x92  # VL loop runs out before we can use it
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    # checks integer predication.
    def case_13_sv_predicated_add(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321 + 0x1234
        #       2 = 0 (skipped)
        #       3 = 7 + 11  => 0x4242 = 0x3012 + 0x1230
        #
        #      13 = 0 (skipped)
        #      14 = 11 + 8  => 0xB063 = 0x3012 + 0x8051
        #      15 = 0 (skipped)
        isa = SVP64Asm([
            'sv.add/m=r30 1.v, 5.v, 9.v',
            'sv.add/m=~r30 13.v, 10.v, 7.v'
        ])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[30] = 0b101  # predicate mask
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[11] = 0x3012
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        initial_regs[7] = 0x1230
        initial_regs[8] = 0x8051
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)

    # checks an instruction with no effect (all mask bits are zeros)
    def case_14_intpred_all_zeros_all_ones(self):
        # adds:
        #       1 = 0 (skipped)
        #       2 = 0 (skipped)
        #       3 = 0 (skipped)
        #
        #      13 = 10 + 7  => 0x2341 = 0x1111 + 0x1230
        #      14 = 11 + 8  => 0xB063 = 0x3012 + 0x8051
        #      15 = 12 + 9  => 0x7736 = 0x6502 + 0x1234
        isa = SVP64Asm([
            'sv.add/m=r30 1.v, 5.v, 9.v',
            'sv.add/m=~r30 13.v, 10.v, 7.v'
        ])
        lst = list(isa)
        print("listing", lst)

        # initial values in GPR regfile
        initial_regs = [0] * 32
        initial_regs[30] = 0  # predicate mask
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[11] = 0x3012
        initial_regs[12] = 0x6502
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        initial_regs[7] = 0x1230
        initial_regs[8] = 0x8051
        # SVSTATE (in this case, VL=3)
        svstate = SVP64State()
        svstate.vl[0:7] = 3  # VL
        svstate.maxvl[0:7] = 3  # MAXVL
        print("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)
