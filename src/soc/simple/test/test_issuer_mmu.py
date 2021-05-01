"""simple core test, runs instructions from a TestMemory

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git

import unittest
import sys

# here is the logic which takes test cases and "executes" them.
# in this instance (TestRunner) its job is to instantiate both
# a Libre-SOC nmigen-based HDL instance and an ISACaller python
# simulator.  it's also responsible for performing the single
# step and comparison.
from soc.simple.test.test_runner import TestRunner

# test with MMU
from openpower.test.mmu.mmu_cases import MMUTestCase
from openpower.test.mmu.mmu_rom_cases import MMUTestCaseROM, default_mem
from openpower.test.ldst.ldst_cases import LDSTTestCase
#from openpower.simulator.test_sim import (GeneralTestCases, AttnTestCase)

if __name__ == "__main__":
    svp64 = True
    if len(sys.argv) == 2:
        if sys.argv[1] == 'nosvp64':
            svp64 = False
        sys.argv.pop()

    print ("SVP64 test mode enabled", svp64)

    unittest.main(exit=False)
    suite = unittest.TestSuite()
    #suite.addTest(TestRunner(GeneralTestCases.test_data, svp64=svp64,
    #                          microwatt_mmu=True))
    #suite.addTest(TestRunner(MMUTestCase().test_data, svp64=svp64,
    #                          microwatt_mmu=True))

    # without ROM set
    #suite.addTest(TestRunner(MMUTestCaseROM().test_data, svp64=svp64,
    #                          microwatt_mmu=True))

    # LD/ST tests should all still work
    suite.addTest(TestRunner(LDSTTestCase().test_data, svp64=svp64,
                              microwatt_mmu=True))

    runner = unittest.TextTestRunner()
    runner.run(suite)
