import unittest
from soc.fu.mul.test.helper import MulTestHelper
from openpower.simulator.program import Program
from soc.config.endian import bigendian
from soc.fu.test.common import (TestAccumulatorBase)
import random


class MulTestCases2Arg(TestAccumulatorBase):
    def case_all(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            # use "with" so as to close the files used
            with Program(l, bigendian) as prog:
                for ra in test_values:
                    for rb in test_values:
                        initial_regs = [0] * 32
                        initial_regs[1] = ra
                        initial_regs[2] = rb
                        self.add_case(prog, initial_regs)

    def case_all_rb_randint(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            # use "with" so as to close the files used
            with Program(l, bigendian) as prog:
                for ra in test_values:
                    initial_regs = [0] * 32
                    initial_regs[1] = ra
                    initial_regs[2] = random.randint(0, (1 << 64)-1)
                    self.add_case(prog, initial_regs)

    def case_all_rb_close_to_ov(self):
        instrs = ["mulhw",
                  "mulhw.", "mullw",
                  "mullw.", "mullwo",
                  "mullwo.", "mulhwu",
                  "mulhwu.", "mulld",
                  "mulld.", "mulldo",
                  "mulldo.", "mulhd",
                  "mulhd.", "mulhdu",
                  "mulhdu."]

        test_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for instr in instrs:
            l = [f"{instr} 3, 1, 2"]
            # use "with" so as to close the files used
            with Program(l, bigendian) as prog:
                for i in range(20):
                    x = 0x7fffffff + random.randint((-1 << 31), (1 << 31) - 1)
                    ra = random.randint(0, (1 << 32)-1)
                    rb = x // ra

                    initial_regs = [0] * 32
                    initial_regs[1] = ra
                    initial_regs[2] = rb
                    self.add_case(prog, initial_regs)

    def case_mulli(self):

        imm_values = [-32768, -32767, -32766, -2, -1, 0, 1, 2, 32766, 32767]

        ra_values = [
            0x0,
            0x1,
            0x2,
            0xFFFF_FFFF_FFFF_FFFF,
            0xFFFF_FFFF_FFFF_FFFE,
            0x7FFF_FFFF_FFFF_FFFF,
            0x8000_0000_0000_0000,
            0x1234_5678_0000_0000,
            0x1234_5678_8000_0000,
            0x1234_5678_FFFF_FFFF,
            0x1234_5678_7FFF_FFFF,
            0xffffffff,
            0x7fffffff,
            0x80000000,
            0xfffffffe,
            0xfffffffd
        ]

        for i in range(20):
            imm_values.append(random.randint(-1 << 15, (1 << 15) - 1))

        for i in range(14):
            ra_values.append(random.randint(0, (1 << 64) - 1))

        for imm in imm_values:
            l = [f"mulli 0, 1, {imm}"]
            # use "with" so as to close the files used
            with Program(l, bigendian) as prog:
                for ra in ra_values:
                    initial_regs = [0] * 32
                    initial_regs[1] = ra
                    self.add_case(prog, initial_regs)


MUL_3_ARG_TEST_VALUES = [
    0x0,
    0x1,
    0x2,
    0xFFFF_FFFF_FFFF_FFFF,
    0xFFFF_FFFF_FFFF_FFFE,
    0x7FFF_FFFF_FFFF_FFFF,
    0x8000_0000_0000_0000,
    0x1234_5678_0000_0000,
    0x1234_5678_8000_0000,
    0x1234_5678_FFFF_FFFF,
    0x1234_5678_7FFF_FFFF,
    0xffffffff,
    0x7fffffff,
    0x80000000,
    0xfffffffe,
    0xfffffffd
]


class MulTestCases3Arg(TestAccumulatorBase):
    def __init__(self, subtest_index):
        self.subtest_index = subtest_index
        super().__init__()

    def case_all(self):
        instrs = ["maddhd", "maddhdu", "maddld"]

        for instr in instrs:
            l = [f"{instr} 1, 2, 3, 4"]
            ra = MUL_3_ARG_TEST_VALUES[self.subtest_index]
            for rb in MUL_3_ARG_TEST_VALUES:
                for rc in MUL_3_ARG_TEST_VALUES:
                    initial_regs = [0] * 32
                    initial_regs[2] = ra
                    initial_regs[3] = rb
                    initial_regs[4] = rc
                    # use "with" so as to close the files used
                    with Program(l, bigendian) as prog:
                        self.add_case(prog, initial_regs)


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
