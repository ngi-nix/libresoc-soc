from nmigen import Module, Signal
#from nmigen.back.pysim import Simulator, Delay, Settle
from nmutil.formaltest import FHDLTestCase
import unittest
from soc.decoder.isa.caller import ISACaller
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.simulator.program import Program
from soc.decoder.isa.caller import ISACaller, inject, RADIX
from soc.decoder.selectable_int import SelectableInt
from soc.decoder.orderedset import OrderedSet
from soc.decoder.isa.all import ISA
from soc.decoder.isa.test_caller import run_tst

testmem = {

           0x10000:    # PARTITION_TABLE_2 (not implemented yet)
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
           0x800000000100000b,

           0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
           0x8000000000040009,
           0x40000:     # RADIX_SECOND_LEVEL
                        # V = 1 L = 1 SW = 0 RPN = 0
                        # R = 1 C = 1 ATT = 0 EAA 0x7
           0xc000000000000187,

           0x1000000:   # PROCESS_TABLE_3
                        # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
           0x40000000000300ad,
          }

class DecoderTestCase(FHDLTestCase):

    def test_load_store(self):
        lst = ["addi 1, 0, 0x0010",
               "addi 2, 0, 0x1234",
               "stw 2, 0(1)",
               "lwz 3, 0(1)"]
        with Program(lst, bigendian=False) as program:
            sim = self.run_tst_program(program)
            print(sim.gpr(1))
            self.assertEqual(sim.gpr(3), SelectableInt(0x1234, 64))

    def run_tst_program(self, prog, initial_regs=[0] * 32):
        simulator = run_tst(prog, initial_regs,mmu=True,mem=testmem)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
