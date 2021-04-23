"""test of SVP64 operations.

related bugs:

 * https://bugs.libre-soc.org/show_bug.cgi?id=363
"""

# NOTE: to use cxxsim, export NMIGEN_SIM_MODE=cxxsim from the shell
# Also, check out the cxxsim nmigen branch, and latest yosys from git

import unittest
from soc.simple.test.test_runner import TestRunner

# test with ALU data and Logical data
from openpower.test.alu.svp64_cases import SVP64ALUTestCase


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TestRunner(SVP64ALUTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
