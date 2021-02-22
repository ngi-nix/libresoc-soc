"""simple core test, runs instructions from a TestMemory

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git

import unittest
from soc.simple.test.test_runner import TestRunner

# test with ALU data and Logical data
from soc.fu.alu.test.test_pipe_caller import ALUTestCase
from soc.fu.div.test.test_pipe_caller import DivTestCases
from soc.fu.logical.test.test_pipe_caller import LogicalTestCase
from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from soc.fu.cr.test.test_pipe_caller import CRTestCase
# from soc.fu.branch.test.test_pipe_caller import BranchTestCase
# from soc.fu.spr.test.test_pipe_caller import SPRTestCase
from soc.fu.ldst.test.test_pipe_caller import LDSTTestCase
from soc.simulator.test_sim import (GeneralTestCases, AttnTestCase)
# from soc.simulator.test_helloworld_sim import HelloTestCases


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    # suite.addTest(TestRunner(HelloTestCases.test_data))
    #suite.addTest(TestRunner(DivTestCases().test_data))
    # suite.addTest(TestRunner(AttnTestCase.test_data))
    #suite.addTest(TestRunner(GeneralTestCases.test_data))
    #suite.addTest(TestRunner(LDSTTestCase().test_data))
    #suite.addTest(TestRunner(CRTestCase().test_data))
    #suite.addTest(TestRunner(ShiftRotTestCase().test_data))
    suite.addTest(TestRunner(LogicalTestCase().test_data))
    #suite.addTest(TestRunner(ALUTestCase().test_data))
    # suite.addTest(TestRunner(BranchTestCase.test_data))
    # suite.addTest(TestRunner(SPRTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
