import random
import unittest

from soc.fu.div.pipe_data import DivPipeKind
from soc.fu.div.test.helper import DivTestHelper

from openpower.test.div.div_cases import DivTestCases


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
