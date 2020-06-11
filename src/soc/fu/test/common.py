"""
Bugreports:
* https://bugs.libre-soc.org/show_bug.cgi?id=361
"""

from soc.decoder.power_enums import XER_bits
from soc.regfile.util import fast_reg_to_spr # HACK!


class TestCase:
    def __init__(self, program, name, regs=None, sprs=None, cr=0, mem=None,
                       msr=0):

        self.program = program
        self.name = name

        if regs is None:
            regs = [0] * 32
        if sprs is None:
            sprs = {}
        if mem is None:
            mem = {}
        self.regs = regs
        self.sprs = sprs
        self.cr = cr
        self.mem = mem
        self.msr = msr

class ALUHelpers:

    def get_sim_fast_spr1(res, sim, dec2):
        fast1_en = yield dec2.e.read_fast1.ok
        if fast1_en:
            fast1_sel = yield dec2.e.read_fast1.data
            spr1_sel = fast_reg_to_spr(fast1_sel)
            spr1_data = sim.spr[spr1_sel].value
            res['spr1'] = spr1_data

    def get_sim_fast_spr2(res, sim, dec2):
        fast2_en = yield dec2.e.read_fast2.ok
        if fast2_en:
            fast2_sel = yield dec2.e.read_fast2.data
            spr2_sel = fast_reg_to_spr(fast2_sel)
            spr2_data = sim.spr[spr2_sel].value
            res['spr2'] = spr2_data

    def get_sim_cr_a(res, sim, dec2):
        cridx_ok = yield dec2.e.read_cr1.ok
        if cridx_ok:
            cridx = yield dec2.e.read_cr1.data
            res['cr_a'] = sim.crl[cridx].get_range().value

    def get_sim_int_ra(res, sim, dec2):
        # TODO: immediate RA zero
        reg1_ok = yield dec2.e.read_reg1.ok
        if reg1_ok:
            data1 = yield dec2.e.read_reg1.data
            res['ra'] = sim.gpr(data1).value

    def get_sim_int_rb(res, sim, dec2):
        reg2_ok = yield dec2.e.read_reg2.ok
        if reg2_ok:
            data = yield dec2.e.read_reg2.data
            res['rb'] = sim.gpr(data).value

    def get_sim_int_rc(res, sim, dec2):
        reg3_ok = yield dec2.e.read_reg3.ok
        if reg3_ok:
            data = yield dec2.e.read_reg3.data
            res['rc'] = sim.gpr(data).value

    def get_rd_sim_xer_ca(res, sim, dec2):
        cry_in = yield dec2.e.input_carry
        if cry_in:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            res['xer_ca'] = expected_carry | (expected_carry32 << 1)

    def set_int_ra(alu, dec2, inp):
        # TODO: immediate RA zero.
        if 'ra' in inp:
            yield alu.p.data_i.ra.eq(inp['ra'])
        else:
            yield alu.p.data_i.ra.eq(0)

    def set_int_rb(alu, dec2, inp):
        yield alu.p.data_i.rb.eq(0)
        if 'rb' in inp:
            yield alu.p.data_i.rb.eq(inp['rb'])
        # If there's an immediate, set the B operand to that
        imm_ok = yield dec2.e.imm_data.imm_ok
        if imm_ok:
            data2 = yield dec2.e.imm_data.imm
            yield alu.p.data_i.rb.eq(data2)

    def set_int_rc(alu, dec2, inp):
        if 'rc' in inp:
            yield alu.p.data_i.rc.eq(inp['rc'])
        else:
            yield alu.p.data_i.rc.eq(0)

    def set_xer_ca(alu, dec2, inp):
        if 'xer_ca' in inp:
            yield alu.p.data_i.xer_ca.eq(inp['xer_ca'])
            print ("extra inputs: CA/32", bin(inp['xer_ca']))

    def set_xer_so(alu, dec2, inp):
        if 'xer_so' in inp:
            so = inp['xer_so']
            print ("extra inputs: so", so)
            yield alu.p.data_i.xer_so.eq(so)

    def set_fast_cia(alu, dec2, inp):
        if 'cia' in inp:
            yield alu.p.data_i.cia.eq(inp['cia'])

    def set_fast_spr1(alu, dec2, inp):
        if 'spr1' in inp:
            yield alu.p.data_i.spr1.eq(inp['spr1'])

    def set_fast_spr2(alu, dec2, inp):
        if 'spr2' in inp:
            yield alu.p.data_i.spr2.eq(inp['spr2'])

    def set_cr_a(alu, dec2, inp):
        if 'cr_a' in inp:
            yield alu.p.data_i.cr_a.eq(inp['cr_a'])

    def set_cr_b(alu, dec2, inp):
        if 'cr_b' in inp:
            yield alu.p.data_i.cr_b.eq(inp['cr_b'])

    def set_cr_c(alu, dec2, inp):
        if 'cr_c' in inp:
            yield alu.p.data_i.cr_c.eq(inp['cr_c'])

    def set_full_cr(alu, dec2, inp):
        if 'full_cr' in inp:
            yield alu.p.data_i.full_cr.eq(inp['full_cr'])
        else:
            yield alu.p.data_i.full_cr.eq(0)

    def get_int_o(res, alu, dec2):
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            res['o'] = yield alu.n.data_o.o.data 

    def get_cr_a(res, alu, dec2):
        cridx_ok = yield dec2.e.write_cr.ok
        if cridx_ok:
            res['cr_a'] = yield alu.n.data_o.cr0.data

    def get_xer_so(res, alu, dec2):
        oe = yield dec2.e.oe.oe
        oe_ok = yield dec2.e.oe.ok
        if oe and oe_ok:
            res['xer_so'] = yield alu.n.data_o.xer_so.data[0]

    def get_xer_ov(res, alu, dec2):
        oe = yield dec2.e.oe.oe
        oe_ok = yield dec2.e.oe.ok
        if oe and oe_ok:
            res['xer_ov'] = yield alu.n.data_o.xer_ov.data

    def get_xer_ca(res, alu, dec2):
        cry_out = yield dec2.e.output_carry
        if cry_out:
            res['xer_ca'] = yield alu.n.data_o.xer_ca.data

    def get_sim_int_o(res, sim, dec2):
        out_reg_valid = yield dec2.e.write_reg.ok
        if out_reg_valid:
            write_reg_idx = yield dec2.e.write_reg.data
            res['o'] = sim.gpr(write_reg_idx).value

    def get_wr_sim_cr_a(res, sim, dec2):
        cridx_ok = yield dec2.e.write_cr.ok
        if cridx_ok:
            cridx = yield dec2.e.write_cr.data
            res['cr_a'] = sim.crl[cridx].get_range().value

    def get_wr_sim_xer_ca(res, sim, dec2):
        cry_out = yield dec2.e.output_carry
        if cry_out:
            expected_carry = 1 if sim.spr['XER'][XER_bits['CA']] else 0
            expected_carry32 = 1 if sim.spr['XER'][XER_bits['CA32']] else 0
            res['xer_ca'] = expected_carry | (expected_carry32 << 1)

    def get_sim_xer_ov(res, sim, dec2):
        oe = yield dec2.e.oe.oe
        oe_ok = yield dec2.e.oe.ok
        if oe and oe_ok:
            expected_ov = 1 if sim.spr['XER'][XER_bits['OV']] else 0
            expected_ov32 = 1 if sim.spr['XER'][XER_bits['OV32']] else 0
            res['xer_ov'] = expected_ov | (expected_ov32 << 1)

    def get_sim_xer_so(res, sim, dec2):
        oe = yield dec2.e.oe.oe
        oe_ok = yield dec2.e.oe.ok
        if oe and oe_ok:
            res['xer_so'] = 1 if sim.spr['XER'][XER_bits['SO']] else 0

    def check_int_o(dut, res, sim_o, msg):
        if 'o' in res:
            expected = sim_o['o']
            alu_out = res['o']
            print(f"expected {expected:x}, actual: {alu_out:x}")
            dut.assertEqual(expected, alu_out, msg)

    def check_cr_a(dut, res, sim_o, msg):
        if 'cr_a' in res:
            cr_expected = sim_o['cr_a']
            cr_actual = res['cr_a']
            print ("CR", cr_expected, cr_actual)
            dut.assertEqual(cr_expected, cr_actual, msg)

    def check_xer_ca(dut, res, sim_o, msg):
        if 'xer_ca' in res:
            ca_expected = sim_o['xer_ca']
            ca_actual = res['xer_ca']
            print ("CA", ca_expected, ca_actual)
            dut.assertEqual(ca_expected, ca_actual, msg)

    def check_xer_ov(dut, res, sim_o, msg):
        if 'xer_ov' in res:
            ov_expected = sim_o['xer_ov']
            ov_actual = res['xer_ov']
            print ("OV", ov_expected, ov_actual)
            dut.assertEqual(ov_expected, ov_actual, msg)

    def check_xer_so(dut, res, sim_o, msg):
        if 'xer_so' in res:
            so_expected = sim_o['xer_so']
            so_actual = res['xer_so']
            print ("SO", so_expected, so_actual)
            dut.assertEqual(so_expected, so_actual, msg)

