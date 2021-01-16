from nmigen import Module, Signal
from soc.simple.test.test_issuer import TestRunner
from soc.simulator.program import Program
from soc.config.endian import bigendian
import unittest

from soc.fu.test.common import (
    TestAccumulatorBase, skip_case, TestCase, ALUHelpers)

# this test case takes about half a minute to run on my Talos II
class MMUDataPathTestCase(TestAccumulatorBase):
    # MMU on microwatt handles MTSPR, MFSPR, DCBZ and TLBIE.
    # libre-soc has own SPR unit
    # other instructions here -> must be load/store

    def case_mfspr_after_invalid_load(self):
        lst = [ 
                "tlbie 0,0,0,0,0",    # RB,RS,RIC,PRS,R
                "dcbz 1,2"
              ]

        initial_regs = [0] * 32

        #FIXME initial_sprs = {'DSISR': 0x12345678, 'DAR': 0x87654321}
        initial_sprs = {}
        self.add_case(Program(lst, bigendian),
                      initial_regs, initial_sprs)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(MMUDataPathTestCase().test_data,microwatt_mmu=True))

    runner = unittest.TextTestRunner()
    runner.run(suite)
