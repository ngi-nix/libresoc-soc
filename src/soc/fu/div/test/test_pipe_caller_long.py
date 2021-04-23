import unittest

from soc.fu.div.test.helper import DivTestHelper
from soc.fu.div.pipe_data import DivPipeKind

from openpower.test.div.long_div_cases import DivTestLong


class TestPipeLong(DivTestHelper):
    def test_div_pipe_core(self):
        self.run_all(DivTestLong().test_data,
                     DivPipeKind.DivPipeCore, "div_pipe_caller_long")

    def test_fsm_div_core(self):
        self.run_all(DivTestLong().test_data,
                     DivPipeKind.FSMDivCore, "div_pipe_caller_long")

    def test_sim_only(self):
        self.run_all(DivTestLong().test_data,
                     DivPipeKind.SimOnly, "div_pipe_caller_long")


if __name__ == "__main__":
    unittest.main()
