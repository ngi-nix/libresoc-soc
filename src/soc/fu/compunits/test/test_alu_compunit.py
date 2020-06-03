import unittest
from soc.decoder.power_enums import (XER_bits, Function)

# XXX bad practice: use of global variables
from soc.fu.alu.test.test_pipe_caller import ALUTestCase # creates the tests
from soc.fu.alu.test.test_pipe_caller import test_data # imports the data

from soc.fu.compunits.compunits import ALUFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner

from soc.decoder.power_enums import CryIn


class ALUTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, ALUFunctionUnit, self,
                         Function.ALU)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to ALUFunctionUnit input regspec
        """
        res = {}

        # RA (or RC)
        reg1_ok = yield dec2.e.read_reg1.ok
        if reg1_ok:
            data1 = yield dec2.e.read_reg1.data
            res['ra'] = sim.gpr(data1).value

        # RB (or immediate)
        reg2_ok = yield dec2.e.read_reg2.ok
        if reg2_ok:
            data2 = yield dec2.e.read_reg2.data
            res['rb'] = sim.gpr(data2).value

        # XER.ca
        cry_in = yield dec2.e.input_carry
        if cry_in == CryIn.CA.value:
            carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            res['xer_ca'] = carry | (carry32<<1)

        # XER.so
        oe = yield dec2.e.oe.data[0] & dec2.e.oe.ok
        if oe:
            so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
            res['xer_so'] = so

        return res

    def check_cu_outputs(self, res, dec2, sim, code):
        """naming (res) must conform to ALUFunctionUnit output regspec
        """

        # RT
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_reg.data
            expected = sim.gpr(write_reg_idx).value
            cu_out = res['o']
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

        # XER.ca
        cry_out = yield dec2.e.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            xer_ca = res['xer_ca']
            real_carry = xer_ca & 0b1 # XXX CO not CO32
            self.assertEqual(expected_carry, real_carry, code)
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            real_carry32 = bool(xer_ca & 0b10) # XXX CO32
            self.assertEqual(expected_carry32, real_carry32, code)

        # TODO: XER.ov and XER.so
        oe = yield dec2.e.oe.data
        if oe:
            xer_ov = res['xer_ov']
            xer_so = res['xer_so']


if __name__ == "__main__":
    unittest.main(exit=False)
    suite = unittest.TestSuite()
    suite.addTest(ALUTestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
