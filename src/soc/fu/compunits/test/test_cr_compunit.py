import unittest
from soc.decoder.power_enums import (XER_bits, Function)

# XXX bad practice: use of global variables
from soc.fu.cr.test.test_pipe_caller import CRTestCase
from soc.fu.cr.test.test_pipe_caller import test_data

from soc.fu.compunits.compunits import CRFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner


class CRTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, CRFunctionUnit, self,
                         Function.CR)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to CRFunctionUnit input regspec
        """
        res = {}
        full_reg = yield dec2.e.read_cr_whole

        # full CR
        print(sim.cr.get_range().value)
        if full_reg:
            res['full_cr'] = sim.cr.get_range().value
        else:
            # CR A
            cr1_en = yield dec2.e.read_cr1.ok
            if cr1_en:
                cr1_sel = yield dec2.e.read_cr1.data
                res['cr_a'] = sim.crl[cr1_sel].get_range().value
            cr2_en = yield dec2.e.read_cr2.ok
            # CR B
            if cr2_en:
                cr2_sel = yield dec2.e.read_cr2.data
                res['cr_b'] = sim.crl[cr2_sel].get_range().value
            cr3_en = yield dec2.e.read_cr3.ok
            # CR C
            if cr3_en:
                cr3_sel = yield dec2.e.read_cr3.data
                res['cr_c'] = sim.crl[cr3_sel].get_range().value

        # RA
        reg1_ok = yield dec2.e.read_reg1.ok
        if reg1_ok:
            data1 = yield dec2.e.read_reg1.data
            res['a'] = sim.gpr(data1).value

        # RB (or immediate)
        reg2_ok = yield dec2.e.read_reg2.ok
        if reg2_ok:
            data2 = yield dec2.e.read_reg2.data
            res['b'] = sim.gpr(data2).value

        return res

    def check_cu_outputs(self, res, dec2, sim, code):
        """naming (res) must conform to CRFunctionUnit output regspec
        """

        print ("check extra output", repr(code))

        # full CR
        whole_reg = yield dec2.e.write_cr_whole
        cr_en = yield dec2.e.write_cr.ok
        if whole_reg:
            full_cr = res['full_cr']
            expected_cr = sim.cr.get_range().value
            self.assertEqual(expected_cr, full_cr, code)

        # part-CR
        if cr_en:
            cr_sel = yield dec2.e.write_cr.data
            expected_cr = sim.crl[cr_sel].get_range().value
            real_cr = res['cr']
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
    suite.addTest(CRTestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
