from nmigen import Module, Signal
from soc.simple.test.test_runner_mmu_rom import TestRunner
from soc.simulator.program import Program
from soc.config.endian import bigendian
import unittest

from soc.fu.test.common import (
    TestAccumulatorBase, skip_case, TestCase, ALUHelpers)

def b(x):
    return int.from_bytes(x.to_bytes(8, byteorder='little'),
                          byteorder='big', signed=False)
default_mem = { 0x10000:    # PARTITION_TABLE_2
                       # PATB_GR=1 PRTB=0x1000 PRTS=0xb
                b(0x800000000100000b),

                0x30000:     # RADIX_ROOT_PTE
                        # V = 1 L = 0 NLB = 0x400 NLS = 9
                b(0x8000000000040009),

                0x40000:     # RADIX_SECOND_LEVEL
                        # 	   V = 1 L = 1 SW = 0 RPN = 0
                           # R = 1 C = 1 ATT = 0 EAA 0x7
                b(0xc000000000000187),

                0x1000000:   # PROCESS_TABLE_3
                       # RTS1 = 0x2 RPDB = 0x300 RTS2 = 0x5 RPDS = 13
                b(0x40000000000300ad),
            }


class MMUTestCase(TestAccumulatorBase):
    # MMU on microwatt handles MTSPR, MFSPR, DCBZ and TLBIE.
    # libre-soc has own SPR unit
    # other instructions here -> must be load/store

    def case_mmu_ldst(self):
        lst = [
                "mtspr 720, 1",
                "lhz 3, 0(1)"      # load some data
              ]

        initial_regs = [0] * 32
        
        prtbl = 0x1000000
        initial_regs[1] = prtbl
        

        initial_sprs = {}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)
class RomDBG():
    def __init__(self):
        self.rom = default_mem
        self.debug = open("/tmp/rom.log","w")
        
        # yield mmu.rin.prtbl.eq(0x1000000) # set process table -- SPR_PRTBL = 720

rom_dbg = RomDBG()

if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(MMUTestCase().test_data,rom_dbg))
    runner = unittest.TextTestRunner()
    runner.run(suite)
