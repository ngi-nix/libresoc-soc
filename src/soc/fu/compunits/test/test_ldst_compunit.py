import unittest
from soc.decoder.power_enums import (XER_bits, Function)

from soc.fu.ldst.test.test_pipe_caller import LDSTTestCase, get_cu_inputs

from soc.fu.compunits.compunits import LDSTFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner


class LDSTTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, LDSTFunctionUnit, self,
                         Function.LOGICAL)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to LDSTFunctionUnit input regspec
        """
        res = yield from get_cu_inputs(dec2, sim)
        return res

    def check_cu_outputs(self, res, dec2, sim, code):
        """naming (res) must conform to LDSTFunctionUnit output regspec
        """

        # RT
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_reg.data
            expected = sim.gpr(write_reg_idx).value
            cu_out = res['o']
            print(f"expected {expected:x}, actual: {cu_out:x}")
            self.assertEqual(expected, cu_out, code)

        # RA
        out_reg_valid = yield dec2.e.write_ea.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_ea.data
            expected = sim.gpr(write_reg_idx).value
            cu_out = res['o1']
            print(f"expected {expected:x}, actual: {cu_out:x}")
            self.assertEqual(expected, cu_out, code)

        rc = yield dec2.e.rc.data
        op = yield dec2.e.insn_type
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print ("check extra output", repr(code), cridx_ok, cridx)

        if rc:
            self.assertEqual(cridx_ok, 1, code)
            self.assertEqual(cridx, 0, code)

        # CR (CR0-7)
        if cridx_ok:
            cr_expected = sim.crl[cridx].get_range().value
            cr_actual = res['cr_a']
            print ("CR", cridx, cr_expected, cr_actual)
            self.assertEqual(cr_expected, cr_actual, "CR%d %s" % (cridx, code))

        # XER.so
        return
        oe = yield dec2.e.oe
        if oe:
            expected_so = 1 if sim.spr['XER'][XER_bits['so']] else 0
            xer_so = res['xer_so']
            self.assertEqual(expected_so, xer_so, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(LDSTTestRunner(LDSTTestCase.test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
