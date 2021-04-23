import unittest
from soc.fu.mul.test.helper import MulTestHelper
from openpower.test.mul.long_mul_cases import (MulTestCases2Arg,
                                               MulTestCases3Arg)


class TestPipeLong(MulTestHelper):
    def test_mul_pipe_2_arg(self):
        self.run_all(MulTestCases2Arg().test_data, "mul_pipe_caller_long_2_arg",
                     has_third_input=False)

    def helper_3_arg(self, subtest_index):
        self.run_all(MulTestCases3Arg(subtest_index).test_data,
                     f"mul_pipe_caller_long_3_arg_{subtest_index}",
                     has_third_input=True)

    # split out as separate functions so some test
    # runners can test them all in parallel
    def test_mul_pipe_3_arg_0(self):
        self.helper_3_arg(0)

    def test_mul_pipe_3_arg_1(self):
        self.helper_3_arg(1)

    def test_mul_pipe_3_arg_2(self):
        self.helper_3_arg(2)

    def test_mul_pipe_3_arg_3(self):
        self.helper_3_arg(3)

    def test_mul_pipe_3_arg_4(self):
        self.helper_3_arg(4)

    def test_mul_pipe_3_arg_5(self):
        self.helper_3_arg(5)

    def test_mul_pipe_3_arg_6(self):
        self.helper_3_arg(6)

    def test_mul_pipe_3_arg_7(self):
        self.helper_3_arg(7)

    def test_mul_pipe_3_arg_8(self):
        self.helper_3_arg(8)

    def test_mul_pipe_3_arg_9(self):
        self.helper_3_arg(9)

    def test_mul_pipe_3_arg_10(self):
        self.helper_3_arg(10)

    def test_mul_pipe_3_arg_11(self):
        self.helper_3_arg(11)

    def test_mul_pipe_3_arg_12(self):
        self.helper_3_arg(12)

    def test_mul_pipe_3_arg_13(self):
        self.helper_3_arg(13)

    def test_mul_pipe_3_arg_14(self):
        self.helper_3_arg(14)

    def test_mul_pipe_3_arg_15(self):
        self.helper_3_arg(15)

    def test_all_values_covered(self):
        count = len(MUL_3_ARG_TEST_VALUES)
        for i in range(count):
            getattr(self, f"test_mul_pipe_3_arg_{i}")
        with self.assertRaises(AttributeError):
            getattr(self, f"test_mul_pipe_3_arg_{count}")


if __name__ == "__main__":
    unittest.main()
