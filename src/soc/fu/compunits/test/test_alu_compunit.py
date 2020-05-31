from nmigen import Module, Signal
from nmigen.back.pysim import Simulator, Delay, Settle
from nmigen.test.utils import FHDLTestCase
from nmigen.cli import rtlil
import unittest
from soc.decoder.isa.caller import ISACaller, special_sprs
from soc.decoder.power_decoder import (create_pdecode)
from soc.decoder.power_decoder2 import (PowerDecode2)
from soc.decoder.power_enums import (XER_bits, Function, InternalOp)
from soc.decoder.selectable_int import SelectableInt
from soc.simulator.program import Program
from soc.decoder.isa.all import ISA

from soc.fu.alu.test.test_pipe_caller import TestCase, ALUTestCase, test_data
from soc.fu.compunits.compunits import ALUFunctionUnit
from soc.fu.compunits.test.test_compunit import TestRunner
from soc.experiment.compalu_multi import find_ok # hack
import random

def set_cu_input(cu, idx, data):
    rdop = cu.get_in_name(idx)
    yield cu.src_i[idx].eq(data)
    while True:
        rd_rel_o = yield cu.rd.rel[idx]
        print ("rd_rel %d wait HI" % idx, rd_rel_o, rdop, hex(data))
        if rd_rel_o:
            break
        yield
    yield cu.rd.go[idx].eq(1)
    while True:
        yield
        rd_rel_o = yield cu.rd.rel[idx]
        if rd_rel_o:
            break
        print ("rd_rel %d wait HI" % idx, rd_rel_o)
        yield
    yield cu.rd.go[idx].eq(0)


def get_cu_output(cu, idx, code):
    wrmask = yield cu.wrmask
    wrop = cu.get_out_name(idx)
    wrok = cu.get_out(idx)
    fname = find_ok(wrok.fields)
    wrok = yield getattr(wrok, fname)
    print ("wr_rel mask", repr(code), idx, wrop, bin(wrmask), fname, wrok)
    assert wrmask & (1<<idx), \
            "get_cu_output '%s': mask bit %d not set\n" \
            "write-operand '%s' Data.ok likely not set (%s)" \
            % (code, idx, wrop, hex(wrok))
    while True:
        wr_relall_o = yield cu.wr.rel
        wr_rel_o = yield cu.wr.rel[idx]
        print ("wr_rel %d wait" % idx, hex(wr_relall_o), wr_rel_o)
        if wr_rel_o:
            break
        yield
    yield cu.wr.go[idx].eq(1)
    yield Settle()
    result = yield cu.dest[idx]
    yield
    yield cu.wr.go[idx].eq(0)
    print ("result", repr(code), idx, wrop, wrok, hex(result))
    return result



class ALUTestRunner(TestRunner):
    def __init__(self, test_data):
        super().__init__(test_data, ALUFunctionUnit, self)

    def get_cu_inputs(self, dec2, sim):
        # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
        # detect the immediate here (with m.If(self.i.ctx.op.imm_data.imm_ok))
        # and place it into data_i.b
        res = {}

        reg3_ok = yield dec2.e.read_reg3.ok
        reg1_ok = yield dec2.e.read_reg1.ok
        assert reg3_ok != reg1_ok
        if reg3_ok:
            data1 = yield dec2.e.read_reg3.data
            res[0] = sim.gpr(data1).value
        elif reg1_ok:
            data1 = yield dec2.e.read_reg1.data
            res[0] = sim.gpr(data1).value

        # If there's an immediate, set the B operand to that
        reg2_ok = yield dec2.e.read_reg2.ok
        if reg2_ok:
            data2 = yield dec2.e.read_reg2.data
            res[1] = sim.gpr(data2).value

        carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
        carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
        res[3] = carry | (carry32<<1)
        so = 1 if sim.spr['XER'][XER_bits['SO']] else 0
        res[2] = so

        return res

    def check_cu_outputs(self, res, dec2, sim, code):
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

        if cridx_ok:
            cr_expected = sim.crl[cridx].get_range().value
            cr_actual = res['cr0']
            print ("CR", cridx, cr_expected, cr_actual)
            self.assertEqual(cr_expected, cr_actual, "CR%d %s" % (cridx, code))

        cry_out = yield dec2.e.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            xer_ca = res['xer_ca']
            real_carry = xer_ca & 0b1 # XXX CO not CO32
            self.assertEqual(expected_carry, real_carry, code)
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            real_carry32 = bool(xer_ca & 0b10) # XXX CO32
            self.assertEqual(expected_carry32, real_carry32, code)

        # TODO
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
