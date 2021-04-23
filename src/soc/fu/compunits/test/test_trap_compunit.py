import unittest
from openpower.decoder.power_enums import (XER_bits, Function)

from soc.fu.trap.test.test_pipe_caller import get_cu_inputs
from soc.fu.trap.test.test_pipe_caller import TrapTestCase  # creates the tests

from openpower.test.common import ALUHelpers
from soc.fu.compunits.compunits import TrapFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner
from openpower.endian import bigendian


class TrapTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, TrapFunctionUnit, self,
                         Function.TRAP, bigendian)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to TrapFunctionUnit input regspec
        """
        res = yield from get_cu_inputs(dec2, sim)
        return res

    def check_cu_outputs(self, res, dec2, sim, alu, code):
        """naming (res) must conform to TrapFunctionUnit output regspec
        """

        sim_o = {}

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr1(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_fast_spr2(sim_o, sim, dec2)
        ALUHelpers.get_sim_nia(sim_o, sim, dec2)
        ALUHelpers.get_sim_msr(sim_o, sim, dec2)

        print("sim output", sim_o)

        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_fast_spr1(self, res, sim_o, code)
        ALUHelpers.check_fast_spr2(self, res, sim_o, code)
        ALUHelpers.check_nia(self, res, sim_o, code)
        ALUHelpers.check_msr(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(TrapTestRunner(TrapTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
