from nmigen import Module, Signal, Elaboratable, Cat, Repl
from nmigen.asserts import Assert, AnyConst
from nmutil.formaltest import FHDLTestCase

from openpower.decoder.power_decoder import create_pdecode, PowerOp
from openpower.decoder.power_enums import (In1Sel, In2Sel, In3Sel,
                                     OutSel, RC, Form,
                                     MicrOp, SPR)
from openpower.decoder.power_decoder2 import (PowerDecode2,
                                        Decode2ToExecute1Type)
import unittest

class Driver(Elaboratable):
    def __init__(self):
        self.m = None
        self.comb = None
        self.instruction = None

    def elaborate(self, platform):
        self.m = Module()
        self.comb = self.m.d.comb
        self.instruction = Signal(32)

        self.comb += self.instruction.eq(AnyConst(32))

        pdecode = create_pdecode()

        self.m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        self.comb += pdecode2.dec.bigendian.eq(1) # XXX TODO: bigendian=0
        self.comb += pdecode2.dec.raw_opcode_in.eq(self.instruction)

        self.test_in1(pdecode2, pdecode)
        self.test_in2()
        self.test_in2_fields()
        self.test_in3()
        self.test_out()
        self.test_rc()
        self.test_single_bits()

        return self.m

    def test_in1(self, pdecode2, pdecode):
        m = self.m
        comb = self.comb
        ra = self.instr_bits(11, 15)
        with m.If(pdecode.op.in1_sel == In1Sel.RA):
            comb += Assert(pdecode2.e.read_reg1.data == ra)
            comb += Assert(pdecode2.e.read_reg1.ok == 1)
        with m.If(pdecode.op.in1_sel == In1Sel.RA_OR_ZERO):
            with m.If(ra == 0):
                comb += Assert(pdecode2.e.read_reg1.ok == 0)
            with m.Else():
                comb += Assert(pdecode2.e.read_reg1.data == ra)
                comb += Assert(pdecode2.e.read_reg1.ok == 1)
                op = pdecode.op.internal_op
        with m.If((op == MicrOp.OP_BC) |
                  (op == MicrOp.OP_BCREG)):
            with m.If(~self.instr_bits(8)):
                comb += Assert(pdecode2.e.read_spr1.data == SPR.CTR)
                comb += Assert(pdecode2.e.read_spr1.ok == 1)
        with m.If((op == MicrOp.OP_MFSPR) |
                  (op == MicrOp.OP_MTSPR)):
            comb += Assert(pdecode2.e.read_spr1.data == self.instr_bits(11, 20))
            comb += Assert(pdecode2.e.read_spr1.ok == 1)

    def test_in2(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        dec = pdecode2.dec
        with m.If(dec.op.in2_sel == In2Sel.RB):
            comb += Assert(pdecode2.e.read_reg2.ok == 1)
            comb += Assert(pdecode2.e.read_reg2.data == dec.RB)
        with m.Elif(dec.op.in2_sel == In2Sel.NONE):
            comb += Assert(pdecode2.e.imm_data.ok == 0)
            comb += Assert(pdecode2.e.read_reg2.ok == 0)
        with m.Elif(dec.op.in2_sel == In2Sel.SPR):
            comb += Assert(pdecode2.e.imm_data.ok == 0)
            comb += Assert(pdecode2.e.read_reg2.ok == 0)
            comb += Assert(pdecode2.e.read_spr2.ok == 1)
            with m.If(dec.fields.FormXL.XO[9]):
                comb += Assert(pdecode2.e.read_spr2.data == SPR.CTR)
            with m.Else():
                comb += Assert(pdecode2.e.read_spr2.data == SPR.LR)
        with m.Else():
            comb += Assert(pdecode2.e.imm_data.ok == 1)
            with m.Switch(dec.op.in2_sel):
                with m.Case(In2Sel.CONST_UI):
                    comb += Assert(pdecode2.e.imm_data.data == dec.UI)
                with m.Case(In2Sel.CONST_SI):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   self.exts(dec.SI, 16, 64))
                with m.Case(In2Sel.CONST_UI_HI):
                    comb += Assert(pdecode2.e.imm_data.data == (dec.UI << 16))
                with m.Case(In2Sel.CONST_SI_HI):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   self.exts(dec.SI << 16, 32, 64))
                with m.Case(In2Sel.CONST_LI):
                    comb += Assert(pdecode2.e.imm_data.data == (dec.LI << 2))
                with m.Case(In2Sel.CONST_BD):
                    comb += Assert(pdecode2.e.imm_data.data == (dec.BD << 2))
                with m.Case(In2Sel.CONST_DS):
                    comb += Assert(pdecode2.e.imm_data.data == (dec.DS << 2))
                with m.Case(In2Sel.CONST_M1):
                    comb += Assert(pdecode2.e.imm_data.data == ~0)
                with m.Case(In2Sel.CONST_SH):
                    comb += Assert(pdecode2.e.imm_data.data == dec.sh)
                with m.Case(In2Sel.CONST_SH32):
                    comb += Assert(pdecode2.e.imm_data.data == dec.SH32)
                with m.Default():
                    comb += Assert(0)

    def exts(self, exts_data, width, fullwidth):
        exts_data = exts_data[0:width]
        topbit = exts_data[-1]
        signbits = Repl(topbit, fullwidth-width)
        return Cat(exts_data, signbits)

    def test_in2_fields(self):
        m = self.m
        comb = self.comb
        dec = m.submodules.pdecode2.dec

        comb += Assert(dec.RB == self.instr_bits(16, 20))
        comb += Assert(dec.UI == self.instr_bits(16, 31))
        comb += Assert(dec.SI == self.instr_bits(16, 31))
        comb += Assert(dec.LI == self.instr_bits(6, 29))
        comb += Assert(dec.BD == self.instr_bits(16, 29))
        comb += Assert(dec.DS == self.instr_bits(16, 29))
        comb += Assert(dec.sh == Cat(self.instr_bits(16, 20),
                                           self.instr_bits(30)))
        comb += Assert(dec.SH32 == self.instr_bits(16, 20))

    def test_in3(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        with m.If(pdecode2.dec.op.in3_sel == In3Sel.RS):
            comb += Assert(pdecode2.e.read_reg3.ok == 1)
            comb += Assert(pdecode2.e.read_reg3.data == self.instr_bits(6,10))

    def test_out(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        sel = pdecode2.dec.op.out_sel
        dec = pdecode2.dec
        with m.If(sel == OutSel.SPR):
            comb += Assert(pdecode2.e.write_spr.ok == 1)
            comb += Assert(pdecode2.e.write_reg.ok == 0)
        with m.Elif(sel == OutSel.NONE):
            comb += Assert(pdecode2.e.write_spr.ok == 0)
            comb += Assert(pdecode2.e.write_reg.ok == 0)
        with m.Else():
            comb += Assert(pdecode2.e.write_spr.ok == 0)
            comb += Assert(pdecode2.e.write_reg.ok == 1)
            data = pdecode2.e.write_reg.data
            with m.If(sel == OutSel.RT):
                comb += Assert(data == self.instr_bits(6, 10))
            with m.If(sel == OutSel.RA):
                comb += Assert(data == self.instr_bits(11, 15))

    def test_rc(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        sel = pdecode2.dec.op.rc_sel
        dec = pdecode2.dec
        comb += Assert(pdecode2.e.rc.ok == 1)
        with m.If(sel == RC.NONE):
            comb += Assert(pdecode2.e.rc.data == 0)
        with m.If(sel == RC.ONE):
            comb += Assert(pdecode2.e.rc.data == 1)
        with m.If(sel == RC.RC):
            comb += Assert(pdecode2.e.rc.data == dec.Rc)
            comb += Assert(pdecode2.e.oe.ok == 1)
            comb += Assert(pdecode2.e.oe.data == dec.OE)

    def test_single_bits(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        dec = pdecode2.dec
        e = pdecode2.e
        comb += Assert(e.invert_in == dec.op.inv_a)
        comb += Assert(e.invert_out == dec.op.inv_out)
        comb += Assert(e.input_carry == dec.op.cry_in)
        comb += Assert(e.output_carry == dec.op.cry_out)
        comb += Assert(e.is_32bit == dec.op.is_32b)
        comb += Assert(e.is_signed == dec.op.sgn)
        with m.If(dec.op.lk):
            comb += Assert(e.lk == self.instr_bits(31))
        comb += Assert(e.byte_reverse == dec.op.br)
        comb += Assert(e.sign_extend == dec.op.sgn_ext)
        comb += Assert(e.update == dec.op.upd)
        comb += Assert(e.input_cr == dec.op.cr_in)
        comb += Assert(e.output_cr == dec.op.cr_out)

    def instr_bits(self, start, end=None):
        if not end:
            end = start
        return self.instruction[::-1][start:end+1][::-1]


class Decoder2TestCase(FHDLTestCase):
    def test_decoder2(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)

if __name__ == '__main__':
    unittest.main()
