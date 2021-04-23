import random
import unittest
from openpower.simulator.program import Program
from soc.config.endian import bigendian

from soc.fu.test.common import (TestCase, TestAccumulatorBase, skip_case)
from soc.fu.div.pipe_data import DivPipeKind

from soc.fu.div.test.helper import (log_rand, get_cu_inputs,
                                    set_alu_inputs, DivTestHelper)


class DivTestCases(TestAccumulatorBase):
    def case_divdeu_regression(self):
        lst = ["divdeu 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0x2
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divde_regression3(self):
        lst = ["divde 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x8000000000000000
        initial_regs[2] = 0xFFFFFFFFFFFFFFFF
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divwe_regression2(self):
        lst = ["divwe 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xFFFFFFFF
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divde_regression2(self):
        lst = ["divde 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0xfffffffffffffffe
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divde_regression(self):
        lst = ["divde 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[2] = 0x1
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_moduw_regression(self):
        lst = ["moduw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0xffffffffffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_modsw_regression(self):
        lst = ["modsw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffffffff
        initial_regs[2] = 0x2
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divweu_regression(self):
        # simulator is wrong, FSM and power-instruction-analyzer both correct
        lst = ["divweu 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0xffffffffffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divwe_regression(self):
        # div FU and power-instruction-analyzer both correctly return 0
        # hitting behavior undefined by Power v3.1 spec, need to adjust
        # simulator API to tell tests that the simulator's output doesn't
        # need to completely match
        lst = [f"divwe 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 1
        initial_regs[2] = 1
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divwe__regression(self):
        lst = ["divwe. 3, 1, 2"]
        initial_regs = [0] * 32
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divw_regression(self):
        # simulator is wrong, FSM and power-instruction-analyzer both correct
        lst = [f"divw 0, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[2] = 0x2
        initial_regs[1] = 0x80000000
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    # modulo
    def case_modsd_regression2(self):
        lst = [f"modsd 0, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[2] = 0xff
        initial_regs[1] = 0x7fffffffffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    # modulo
    def case_modsd_regression(self):
        lst = [f"modsd 17, 27, 0"]
        initial_regs = [0] * 32
        initial_regs[0] = 0xff
        initial_regs[27] = 0x7fffffffffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divduo_regression(self):
        lst = [f"divduo. 11, 20, 6"]
        initial_regs = [0] * 32
        # gpr: 00ff00ff00ff0080 <- r6
        # gpr: 000000000000007f <- r11
        # gpr: 7f6e5d4c3b2a1908 <- r20
        initial_regs[6] = 0x00ff00ff00ff0080
        initial_regs[20] = 0x7f6e5d4c3b2a1908
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_0_regression(self):
        for i in range(40):
            lst = ["divwo 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = 0xbc716835f32ac00c
            initial_regs[2] = 0xcdf69a7f7042db66
            with Program(lst, bigendian) as prog:
                self.add_case(prog, initial_regs)

    def case_1_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x10000000000000000-4
        initial_regs[2] = 0x10000000000000000-2
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_2_regression(self):
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffff9321
        initial_regs[2] = 0xffffffffffff7012
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_3_regression(self):
        lst = ["divwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1b8e32f2458746af
        initial_regs[2] = 0x6b8aee2ccf7d62e9
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_4_regression(self):
        lst = ["divw 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_5_regression(self):
        lst = ["divw 3, 1, 2",
               "divwo. 6, 4, 5"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1c4e6c2f3aa4a05c
        initial_regs[2] = 0xe730c2eed6cc8dd7
        initial_regs[4] = 0x1b8e32f2458746af
        initial_regs[5] = 0x6b8aee2ccf7d62e9
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_6_regression(self):
        # CR0 not getting set properly for this one
        # turns out that overflow is not set correctly in
        # fu/div/output_stage.py calc_overflow
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x61c1cc3b80f2a6af
        initial_regs[2] = 0x9dc66a7622c32bc0
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_7_regression(self):
        # https://bugs.libre-soc.org/show_bug.cgi?id=425
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xf1791627e05e8096
        initial_regs[2] = 0xffc868bf4573da0b
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_8_fsm_regression(self):  # FSM result is "36" not 6
        lst = ["divwu. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 18
        initial_regs[2] = 3
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_9_regression(self):  # CR0 fails: expected 0b10, actual 0b11
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 1
        initial_regs[2] = 0
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_10_regression(self):  # overflow fails
        lst = ["divwo 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xbc716835f32ac00c
        initial_regs[2] = 0xcdf69a7f7042db66
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_11_regression(self):
        lst = ["divwo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0xffffffffffffffff
        initial_regs[2] = 0xffffffffffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divw_by_zero_1(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x1
        initial_regs[2] = 0x0
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divw_overflow2(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffffffffffff  # top bits don't seem to matter
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divw_overflow3(self):
        lst = ["divw. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x80000000
        initial_regs[2] = 0xffffffff
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divwuo_regression_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x7591a398c4e32b68
        initial_regs[2] = 0x48674ab432867d69
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_divwuo_1(self):
        lst = ["divwuo. 3, 1, 2"]
        initial_regs = [0] * 32
        initial_regs[1] = 0x50
        initial_regs[2] = 0x2
        with Program(lst, bigendian) as prog:
            self.add_case(prog, initial_regs)

    def case_rand_divwu(self):
        insns = ["divwu", "divwu.", "divwuo", "divwuo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            with Program(lst, bigendian) as prog:
                self.add_case(prog, initial_regs)

    def case_rand_divw(self):
        insns = ["divw", "divw.", "divwo", "divwo."]
        for i in range(40):
            choice = random.choice(insns)
            lst = [f"{choice} 3, 1, 2"]
            initial_regs = [0] * 32
            initial_regs[1] = log_rand(32)
            initial_regs[2] = log_rand(32)
            with Program(lst, bigendian) as prog:
                self.add_case(prog, initial_regs)


class TestPipe(DivTestHelper):
    def test_div_pipe_core(self):
        self.run_all(DivTestCases().test_data,
                     DivPipeKind.DivPipeCore, "div_pipe_caller")

    def test_fsm_div_core(self):
        self.run_all(DivTestCases().test_data,
                     DivPipeKind.FSMDivCore, "div_pipe_caller")

    def test_sim_only(self):
        self.run_all(DivTestCases().test_data,
                     DivPipeKind.SimOnly, "div_pipe_caller")


if __name__ == "__main__":
    unittest.main()
