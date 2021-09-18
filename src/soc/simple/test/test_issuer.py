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

# test with ALU data and Logical data
from openpower.test.alu.alu_cases import ALUTestCase
from openpower.test.div.div_cases import DivTestCases
from openpower.test.logical.logical_cases import LogicalTestCase
from openpower.test.shift_rot.shift_rot_cases import ShiftRotTestCase
from openpower.test.cr.cr_cases import CRTestCase
from openpower.test.branch.branch_cases import BranchTestCase
from soc.fu.spr.test.test_pipe_caller import SPRTestCase
from openpower.test.ldst.ldst_cases import LDSTTestCase
from openpower.simulator.test_sim import (GeneralTestCases, AttnTestCase)
from openpower.simulator.test_helloworld_sim import HelloTestCases


if __name__ == "__main__":
    svp64 = True
    if len(sys.argv) == 2:
        if sys.argv[1] == 'nosvp64':
            svp64 = False
        sys.argv.pop()

    # allow list of testing to be selected by command-line
    testing = sys.argv[1:]
    sys.argv = sys.argv[:1]

    if not testing:
        testing = ['general', 'ldst', 'cr', 'shiftrot', 'logical', 'alu',
                   'branch', 'div']

    print ("SVP64 test mode enabled", svp64, testing)

    unittest.main(exit=False)
    suite = unittest.TestSuite()

    # dictionary  of data for tests
    tests = {'hello': HelloTestCases.test_data,
             'div': DivTestCases().test_data,
             'attn': AttnTestCase.test_data,
             'general': GeneralTestCases.test_data,
             'ldst': LDSTTestCase().test_data,
             'cr': CRTestCase().test_data,
             'shiftrot': ShiftRotTestCase().test_data,
             'logical': LogicalTestCase().test_data,
             'alu': ALUTestCase().test_data,
             'branch': BranchTestCase().test_data,
             'spr': SPRTestCase().test_data
            }

    # walk through all tests, those requested get added
    for tname, data in tests.items():
        if tname in testing:
            suite.addTest(TestRunner(data, svp64=svp64))

    runner = unittest.TextTestRunner()
    runner.run(suite)
