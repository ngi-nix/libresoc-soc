import unittest
from soc.fu.mul.test.helper import MulTestHelper

from openpower.test.mul.mul_cases import (MulTestCases2Arg,
                                          MulTestCases3Arg)


class TestPipe(MulTestHelper):
    def test_mul_pipe_2_arg(self):
        self.run_all(MulTestCases2Arg().test_data, "mul_pipe_caller_2_arg",
                     has_third_input=False)

    def test_mul_pipe_3_arg(self):
        self.run_all(MulTestCases3Arg().test_data, "mul_pipe_caller_3_arg",
                     has_third_input=True)


if __name__ == "__main__":
    unittest.main()
