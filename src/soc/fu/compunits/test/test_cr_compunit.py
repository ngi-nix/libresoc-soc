import unittest
from openpower.decoder.power_enums import (XER_bits, Function)

# XXX bad practice: use of global variables
from soc.fu.cr.test.test_pipe_caller import get_cu_inputs
from soc.fu.cr.test.test_pipe_caller import CRTestCase

from soc.fu.compunits.compunits import CRFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner
from openpower.util import mask_extend
from openpower.endian import bigendian


class CRTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, CRFunctionUnit, self,
                         Function.CR, bigendian)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to CRFunctionUnit input regspec
        """
        res = yield from get_cu_inputs(dec2, sim)
        return res

    def check_cu_outputs(self, res, dec2, sim, alu, code):
        """naming (res) must conform to CRFunctionUnit output regspec
        """

        print("check extra output", repr(code), res)

        # full CR
        whole_reg_ok = yield dec2.e.do.write_cr_whole.ok
        whole_reg_data = yield dec2.e.do.write_cr_whole.data
        full_cr_mask = mask_extend(whole_reg_data, 8, 4)

        cr_en = yield dec2.e.write_cr.ok
        if whole_reg_ok:
            full_cr = res['full_cr']
            expected_cr = sim.cr.value
            print("CR whole: expected %x, actual: %x mask: %x" % \
                (expected_cr, full_cr, full_cr_mask))
            self.assertEqual(expected_cr & full_cr_mask,
                             full_cr & full_cr_mask, code)

        # part-CR
        if cr_en:
            cr_sel = yield dec2.e.write_cr.data
            expected_cr = sim.crl[cr_sel].get_range().value
            real_cr = res['cr_a']
            self.assertEqual(expected_cr, real_cr, code)

        # RT
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            alu_out = res['o']
            write_reg_idx = yield dec2.e.write_reg.data
            expected = sim.gpr(write_reg_idx).value
            print(f"expected {expected:x}, actual: {alu_out:x}")
            self.assertEqual(expected, alu_out, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(CRTestRunner(CRTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
