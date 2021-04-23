import unittest
from openpower.decoder.power_enums import (XER_bits, Function)

from soc.fu.alu.test.test_pipe_caller import get_cu_inputs
from soc.fu.alu.test.test_pipe_caller import ALUTestCase  # creates the tests

from openpower.test.common import ALUHelpers
from soc.fu.compunits.compunits import ALUFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner
from openpower.endian import bigendian


class ALUTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, ALUFunctionUnit, self,
                         Function.ALU, bigendian)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to ALUFunctionUnit input regspec
        """
        res = yield from get_cu_inputs(dec2, sim)
        return res

    def check_cu_outputs(self, res, dec2, sim, alu, code):
        """naming (res) must conform to ALUFunctionUnit output regspec
        """

        rc = yield dec2.e.do.rc.data
        op = yield dec2.e.do.insn_type
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), cridx_ok, cridx)

        if rc:
            self.assertEqual(cridx_ok, 1, code)
            self.assertEqual(cridx, 0, code)

        sim_o = {}

        yield from ALUHelpers.get_sim_int_o(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_cr_a(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ov(sim_o, sim, alu, dec2)
        yield from ALUHelpers.get_wr_sim_xer_ca(sim_o, sim, dec2)
        yield from ALUHelpers.get_wr_sim_xer_so(sim_o, sim, alu, dec2)

        ALUHelpers.check_cr_a(self, res, sim_o, "CR%d %s" % (cridx, code))
        ALUHelpers.check_xer_ov(self, res, sim_o, code)
        ALUHelpers.check_xer_ca(self, res, sim_o, code)
        ALUHelpers.check_int_o(self, res, sim_o, code)
        ALUHelpers.check_xer_so(self, res, sim_o, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(ALUTestRunner(ALUTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
