import unittest
from openpower.decoder.power_enums import (XER_bits, Function)

# XXX bad practice: use of global variables
from soc.fu.shift_rot.test.test_pipe_caller import get_cu_inputs
from soc.fu.shift_rot.test.test_pipe_caller import ShiftRotTestCase
from openpower.endian import bigendian

from soc.fu.compunits.compunits import ShiftRotFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner


class ShiftRotTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, ShiftRotFunctionUnit, self,
                         Function.SHIFT_ROT, bigendian)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to ShiftRotFunctionUnit input regspec
        """
        res = yield from get_cu_inputs(dec2, sim)
        return res

    def check_cu_outputs(self, res, dec2, sim, alu, code):
        """naming (res) must conform to ShiftRotFunctionUnit output regspec
        """

        print("outputs", repr(code), res)

        # RT
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_reg.data
            expected = sim.gpr(write_reg_idx).value
            cu_out = res['o']
            print(f"expected {expected:x}, actual: {cu_out:x}")
            self.assertEqual(expected, cu_out, code)

        rc = yield dec2.e.do.rc.data
        rc_ok = yield dec2.e.do.rc.ok
        op = yield dec2.e.do.insn_type
        cridx_ok = yield dec2.e.write_cr.ok
        cridx = yield dec2.e.write_cr.data

        print("check extra output", repr(code), "cr", cridx_ok, cridx,
                                    "rc", rc, rc_ok)

        if rc and rc_ok:
            self.assertEqual(cridx_ok, 1, code)
            self.assertEqual(cridx, 0, code)

        # CR (CR0-7)
        if cridx_ok and rc and rc_ok:
            cr_expected = sim.crl[cridx].get_range().value
            cr_actual = res['cr_a']
            print("CR", cridx, cr_expected, cr_actual)
            self.assertEqual(cr_expected, cr_actual, "CR%d %s" % (cridx, code))

        # XER.ca
        cry_out = yield dec2.e.do.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            xer_ca = res['xer_ca']
            real_carry = xer_ca & 0b1  # XXX CO not CO32
            self.assertEqual(expected_carry, real_carry, code)
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            real_carry32 = bool(xer_ca & 0b10)  # XXX CO32
            self.assertEqual(expected_carry32, real_carry32, code)


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(ShiftRotTestRunner(ShiftRotTestCase().test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
