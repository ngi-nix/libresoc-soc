import random
from soc.fu.test.common import (TestCase, TestAccumulatorBase)
from soc.config.endian import bigendian
from soc.simulator.program import Program
from soc.decoder.isa.caller import special_sprs
from soc.sv.trans.svp64 import SVP64Asm


class SVP64ALUTestCase(TestAccumulatorBase):

    def case_1_sv_add(self):
        # adds:
        #       1 = 5 + 9   => 0x5555 = 0x4321+0x1234
        #       2 = 6 + 10  => 0x3334 = 0x2223+0x1111
        isa = SVP64Asm(['sv.add 1.v, 5.v, 9.v'
                       ])
        lst = list(isa)
        print ("listing", lst)
        initial_regs = [0] * 32
        initial_regs[9] = 0x1234
        initial_regs[10] = 0x1111
        initial_regs[5] = 0x4321
        initial_regs[6] = 0x2223
        svstate = SVP64State()
        svstate.vl[0:7] = 2 # VL
        svstate.maxvl[0:7] = 2 # MAXVL
        print ("SVSTATE", bin(svstate.spr.asint()))

        self.add_case(Program(lst, bigendian), initial_regs,
                      initial_svstate=svstate)
