import unittest
from soc.fu.mul.test.helper import MulTestHelper
from openpower.simulator.program import Program
from openpower.endian import bigendian
from openpower.test.common import TestAccumulatorBase, skip_case

import random


class MulTestCases2Arg(TestAccumulatorBase):
    def case_0_mullw(self):
        lst = [f"mullw 3, 1, 2"]
        initial_regs = [0] * 32
        #initial_regs[1] = 0xffffffffffffffff
        #initial_regs[2] = 0xffffffffffffffff
        initial_regs[1] = 0x2ffffffff
        initial_regs[2] = 0x2
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_1_mullwo_(self):
        lst = [f"mullwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x3b34b06f
        initial_regs[2] = 0xfdeba998
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_2_mullwo(self):
        lst = [f"mullwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffffa988  # -5678
        initial_regs[2] = 0xffffffffffffedcc  # -1234
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_3_mullw(self):
        lst = ["mullw 3, 1, 2",
               "mullw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x6
        initial_regs[2] = 0xe
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_4_mullw_rand(self):
        for i in range(40):
            lst = ["mullw 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_4_mullw_nonrand(self):
        for i in range(40):
            lst = ["mullw 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = i+1
            initial_regs[2] = i+20
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_mulhw__regression_1(self):
        lst = ["mulhw. 3, 1, 2"
               ]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7745b36eca6646fa
        initial_regs[2] = 0x47dfba3a63834ba2
        self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mul_lh(self):
        insns = ["mulhw", "mulhw.", "mulhwu", "mulhwu."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mullw(self):
        insns = ["mullw", "mullw.", "mullwo", "mullwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mulld(self):
        insns = ["mulld", "mulld.", "mulldo", "mulldo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_rand_mulhd(self):
        insns = ["mulhd", "mulhd."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = random.randint(0, (1 << 64)-1)
            initial_regs[2] = random.randint(0, (1 << 64)-1)
            self.add_case(Program(lst, bigendian), initial_regs)

    def case_0_mullhw_regression(self):
        lst = [f"mulhwu 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x4000000000000000
        initial_regs[2] = 0x0000000000000002
        self.add_case(Program(lst, bigendian), initial_regs)


class MulTestCases3Arg(TestAccumulatorBase):
    # TODO add test case for these 3 operand cases (madd
    # needs to be implemented)
    # "maddhd","maddhdu","maddld"
    @skip_case("madd not implemented")
    def case_maddld(self):
        lst = ["maddld 1, 2, 3, 4"]
        initial_regs = [0] * 32
        initial_regs[2] = 0x3
        initial_regs[3] = 0x4
        initial_regs[4] = 0x5
        self.add_case(Program(lst, bigendian), initial_regs)


class TestPipe(MulTestHelper):
    def test_mul_pipe_2_arg(self):
        self.run_all(MulTestCases2Arg().test_data, "mul_pipe_caller_2_arg",
                     has_third_input=False)

    def test_mul_pipe_3_arg(self):
        self.run_all(MulTestCases3Arg().test_data, "mul_pipe_caller_3_arg",
                     has_third_input=True)


if __name__ == "__main__":
    unittest.main()
