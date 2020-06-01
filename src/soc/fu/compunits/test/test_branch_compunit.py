import unittest
from soc.decoder.power_enums import (XER_bits, Function)

# XXX bad practice: use of global variables
from soc.fu.branch.test.test_pipe_caller import BranchTestCase
from soc.fu.branch.test.test_pipe_caller import test_data

from soc.fu.compunits.compunits import BranchFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner


"""
    def assert_outputs(self, branch, dec2, sim, prev_nia, code):
        branch_taken = yield branch.n.data_o.nia.ok
        sim_branch_taken = prev_nia != sim.pc.CIA
        self.assertEqual(branch_taken, sim_branch_taken, code)
        if branch_taken:
            branch_addr = yield branch.n.data_o.nia.data
            self.assertEqual(branch_addr, sim.pc.CIA.value, code)

        lk = yield dec2.e.lk
        branch_lk = yield branch.n.data_o.lr.ok
        self.assertEqual(lk, branch_lk, code)
        if lk:
            branch_lr = yield branch.n.data_o.lr.data
            self.assertEqual(sim.spr['LR'], branch_lr, code)
"""


class BranchTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, BranchFunctionUnit, self,
                         Function.BRANCH)

    def get_cu_inputs(self, dec2, sim):
        """naming (res) must conform to BranchFunctionUnit input regspec
        """
        res = {}
        full_reg = yield dec2.e.read_cr_whole

        # CIA (PC)
        res['cia'] = sim.pc.CIA.value
        # CR A
        cr1_en = yield dec2.e.read_cr1.ok
        if cr1_en:
            cr1_sel = yield dec2.e.read_cr1.data
            res['cr_a'] = sim.crl[cr1_sel].get_range().value

        # SPR1
        cr1_en = yield dec2.e.read_spr1.ok
        res['spr1'] = sim.spr['CTR'].value

        # RB (or immediate)
        reg2_ok = yield dec2.e.read_reg2.ok
        if reg2_ok:
            data2 = yield dec2.e.read_reg2.data
            res['b'] = sim.gpr(data2).value

        print ("get inputs", res)
        return res

    def check_cu_outputs(self, res, dec2, sim, code):
        """naming (res) must conform to BranchFunctionUnit output regspec
        """

        print ("check extra output", repr(code), res)

        # full Branch
        whole_reg = yield dec2.e.write_cr_whole
        cr_en = yield dec2.e.write_cr.ok
        if whole_reg:
            full_cr = res['full_cr']
            expected_cr = sim.cr.get_range().value
            print(f"expected cr {expected_cr:x}, actual: {full_cr:x}")
            self.assertEqual(expected_cr, full_cr, code)

        # part-Branch
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
    suite.addTest(BranchTestRunner(test_data))

    runner = unittest.TextTestRunner()
    runner.run(suite)
