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

           0x1000: # data to be read
           0x1337,

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

prtbl = 0x1000000

class DecoderTestCase(FHDLTestCase):

    def test_load_store(self):
        lst = [#"addi 1, 0, 0x1000",
               #"addi 2, 0, 0x1234",
               #"stw 2, 0(1)",
               "lwz 3, 0(1)"
               ]
        with Program(lst, bigendian=False) as program:
            initial_regs=[0] * 32
            initial_regs[1] = 0x1000
            initial_regs[2] = 0x1234
            sim = self.run_tst_program(program,initial_regs=initial_regs)
            #dump registers into file
            #f = open("/tmp/debug.txt","w")
            #for i in range(1,12):
            #    l = "r"+str(i)+" = "+str(sim.gpr(i))+"\n"
            #    f.write(l)
            self.assertEqual(sim.gpr(3), SelectableInt(0x1337, 64))

    def run_tst_program(self, prog, initial_regs=[0] * 32):
        # set up dummy minimal ISACaller
        spr = {'DSISR': SelectableInt(0, 64),
               'DAR': SelectableInt(0, 64),
               'PIDR': SelectableInt(0, 64),
               'PRTBL': SelectableInt(prtbl, 64)
        }

        simulator = run_tst(prog, initial_regs, mmu=True, mem=testmem,
                    initial_sprs=spr)
        simulator.gpr.dump()
        return simulator


if __name__ == "__main__":
    unittest.main()
