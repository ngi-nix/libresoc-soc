from nmigen import Module, Signal, Elaboratable
from nmigen.asserts import Assert, AnyConst
from nmigen.test.utils import FHDLTestCase

from soc.decoder.power_decoder import create_pdecode, PowerOp
from soc.decoder.power_enums import (In1Sel, In2Sel, In3Sel,
                                     OutSel, RC,
                                     InternalOp, SPR)
from soc.decoder.power_decoder2 import (PowerDecode2,
                                        Decode2ToExecute1Type)
import unittest

class Driver(Elaboratable):
    def __init__(self):
        self.m = None
        self.comb = None

    def elaborate(self, platform):
        self.m = Module()
        self.comb = self.m.d.comb
        instruction = Signal(32)

        self.comb += instruction.eq(AnyConst(32))

        pdecode = create_pdecode()

        self.m.submodules.pdecode2 = pdecode2 = PowerDecode2(pdecode)
        self.comb += pdecode2.dec.opcode_in.eq(instruction)

        self.test_in1(pdecode2, pdecode)
        self.test_in2()
        self.test_in3()
        self.test_out()
        self.test_rc()
        self.test_single_bits()

        return self.m

    def test_in1(self, pdecode2, pdecode):
        m = self.m
        comb = self.comb
        ra = pdecode.RA[0:-1]
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
        with m.If((op == InternalOp.OP_BC) |
                  (op == InternalOp.OP_BCREG)):
            with m.If(~pdecode.BO[2]):
                comb += Assert(pdecode2.e.read_spr1.data == SPR.CTR)
                comb += Assert(pdecode2.e.read_spr1.ok == 1)
        with m.If((op == InternalOp.OP_MFSPR) |
                  (op == InternalOp.OP_MTSPR)):
            comb += Assert(pdecode2.e.read_spr1.data ==
                           pdecode.SPR[0:-1])
            comb += Assert(pdecode2.e.read_spr1.ok == 1)

    def test_in2(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        dec = pdecode2.dec
        with m.If(dec.op.in2_sel == In2Sel.RB):
            comb += Assert(pdecode2.e.read_reg2.ok == 1)
            comb += Assert(pdecode2.e.read_reg2.data ==
                           dec.RB[0:-1])
        with m.Elif(dec.op.in2_sel == In2Sel.NONE):
            comb += Assert(pdecode2.e.imm_data.ok == 0)
            comb += Assert(pdecode2.e.read_reg2.ok == 0)
        with m.Elif(dec.op.in2_sel == In2Sel.SPR):
            comb += Assert(pdecode2.e.imm_data.ok == 0)
            comb += Assert(pdecode2.e.read_reg2.ok == 0)
            comb += Assert(pdecode2.e.read_spr2.ok == 1)
            with m.If(dec.FormXL.XO[9]):
                comb += Assert(pdecode2.e.read_spr2.data == SPR.CTR)
            with m.Else():
                comb += Assert(pdecode2.e.read_spr2.data == SPR.LR)
        with m.Else():
            comb += Assert(pdecode2.e.imm_data.ok == 1)
            with m.Switch(dec.op.in2_sel):
                with m.Case(In2Sel.CONST_UI):
                    comb += Assert(pdecode2.e.imm_data.data == dec.UI[0:-1])
                with m.Case(In2Sel.CONST_SI):
                    comb += Assert(pdecode2.e.imm_data.data == dec.SI[0:-1])
                with m.Case(In2Sel.CONST_UI_HI):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   (dec.UI[0:-1] << 4))
                with m.Case(In2Sel.CONST_SI_HI):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   (dec.SI[0:-1] << 4))
                with m.Case(In2Sel.CONST_LI):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   (dec.LI[0:-1] << 2))
                with m.Case(In2Sel.CONST_BD):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   (dec.BD[0:-1] << 2))
                with m.Case(In2Sel.CONST_DS):
                    comb += Assert(pdecode2.e.imm_data.data ==
                                   (dec.DS[0:-1] << 2))
                with m.Case(In2Sel.CONST_M1):
                    comb += Assert(pdecode2.e.imm_data.data == ~0)
                with m.Case(In2Sel.CONST_SH):
                    comb += Assert(pdecode2.e.imm_data.data == dec.sh[0:-1])
                with m.Case(In2Sel.CONST_SH32):
                    comb += Assert(pdecode2.e.imm_data.data == dec.SH32[0:-1])
                with m.Default():
                    comb += Assert(0)

    def test_in3(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        with m.If(pdecode2.dec.op.in3_sel == In3Sel.RS):
            comb += Assert(pdecode2.e.read_reg3.ok == 1)
            comb += Assert(pdecode2.e.read_reg3.data ==
                           pdecode2.dec.RS[0:-1])

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
                comb += Assert(data == dec.RT[0:-1])
            with m.If(sel == OutSel.RA):
                comb += Assert(data == dec.RA[0:-1])

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
            comb += Assert(pdecode2.e.rc.data == dec.Rc[0:-1])
            comb += Assert(pdecode2.e.oe.ok == 1)
            comb += Assert(pdecode2.e.oe.data == dec.OE[0:-1])

    def test_single_bits(self):
        m = self.m
        comb = self.comb
        pdecode2 = m.submodules.pdecode2
        dec = pdecode2.dec
        e = pdecode2.e
        comb += Assert(e.invert_a == dec.op.inv_a)
        comb += Assert(e.invert_out == dec.op.inv_out)
        comb += Assert(e.input_carry == dec.op.cry_in)
        comb += Assert(e.output_carry == dec.op.cry_out)
        comb += Assert(e.is_32bit == dec.op.is_32b)
        comb += Assert(e.is_signed == dec.op.sgn)
        with m.If(dec.op.lk):
            comb += Assert(e.lk == dec.LK[0:-1])
        comb += Assert(e.byte_reverse == dec.op.br)
        comb += Assert(e.sign_extend == dec.op.sgn_ext)
        comb += Assert(e.update == dec.op.upd)
        comb += Assert(e.input_cr == dec.op.cr_in)
        comb += Assert(e.output_cr == dec.op.cr_out)


class Decoder2TestCase(FHDLTestCase):
    def test_decoder2(self):
        module = Driver()
        self.assertFormal(module, mode="bmc", depth=4)

if __name__ == '__main__':
    unittest.main()
