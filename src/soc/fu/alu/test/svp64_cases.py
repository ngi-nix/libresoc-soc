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
