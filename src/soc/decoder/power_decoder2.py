"""Power ISA Decoder second stage

based on Anton Blanchard microwatt decode2.vhdl

"""
from nmigen import Module, Elaboratable, Signal, Mux, Const
from nmigen.cli import rtlil

from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_enums import (InternalOp, CryIn, Function,
                                     LdstLen, In1Sel, In2Sel, In3Sel,
                                     OutSel, SPR, RC)


class DecodeA(Elaboratable):
    """DecodeA from instruction

    decodes register RA, whether immediate-zero, implicit and
    explicit CSRs
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, name="reg_a")
        self.immz_out = Signal(reset_less=True)
        self.spr_out = Data(10, "spr_a")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register A field
        ra = Signal(5, reset_less=True)
        comb += ra.eq(self.dec.RA[0:-1])
        with m.If((self.sel_in == In1Sel.RA) |
                  ((self.sel_in == In1Sel.RA_OR_ZERO) &
                   (ra != Const(0, 5)))):
            comb += self.reg_out.data.eq(ra)
            comb += self.reg_out.ok.eq(1)

        # zero immediate requested
        with m.If((self.sel_in == In1Sel.RA_OR_ZERO) &
                  (self.reg_out.data == Const(0, 5))):
            comb += self.immz_out.eq(1)

        # decode SPR1 based on instruction type
        op = self.dec.op
        # BC or BCREG: potential implicit register (CTR)
        with m.If((op.internal_op == InternalOp.OP_BC) |
                  (op.internal_op == InternalOp.OP_BCREG)):
            with m.If(~self.dec.BO[2]): # 3.0B p38 BO2=0, use CTR reg
                comb += self.spr_out.data.eq(SPR.CTR) # constant: CTR
                comb += self.spr_out.ok.eq(1)
        # MFSPR or MTSPR: move-from / move-to SPRs
        with m.If((op.internal_op == InternalOp.OP_MFSPR) |
                  (op.internal_op == InternalOp.OP_MTSPR)):
            comb += self.spr_out.data.eq(self.dec.SPR[0:-1]) # SPR field, XFX
            comb += self.spr_out.ok.eq(1)

        return m

class Data:

    def __init__(self, width, name):

        self.data = Signal(width, name=name, reset_less=True)
        self.ok = Signal(name="%s_ok" % name, reset_less=True)

    def eq(self, rhs):
        return [self.data.eq(rhs.data),
                self.ok.eq(rhs.ok)]

    def ports(self):
        return [self.data, self.ok]


class DecodeB(Elaboratable):
    """DecodeB from instruction

    decodes register RB, different forms of immediate (signed, unsigned),
    and implicit SPRs
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In2Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, "reg_b")
        self.imm_out = Data(64, "imm_b")
        self.spr_out = Data(10, "spr_b")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register B field
        with m.Switch(self.sel_in):
            with m.Case(In2Sel.RB):
                comb += self.reg_out.data.eq(self.dec.RB[0:-1])
                comb += self.reg_out.ok.eq(1)
            with m.Case(In2Sel.CONST_UI):
                comb += self.imm_out.data.eq(self.dec.UI[0:-1])
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI): # TODO: sign-extend here?
                comb += self.imm_out.data.eq(self.dec.SI[0:-1])
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_UI_HI):
                comb += self.imm_out.data.eq(self.dec.UI[0:-1]<<16)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI_HI): # TODO: sign-extend here?
                comb += self.imm_out.data.eq(self.dec.SI[0:-1]<<16)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_LI):
                comb += self.imm_out.data.eq(self.dec.LI[0:-1]<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_BD):
                comb += self.imm_out.data.eq(self.dec.BD[0:-1]<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_DS):
                comb += self.imm_out.data.eq(self.dec.DS[0:-1]<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_M1):
                comb += self.imm_out.data.eq(~Const(0, 64)) # all 1s
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH):
                comb += self.imm_out.data.eq(self.dec.sh[0:-1])
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH32):
                comb += self.imm_out.data.eq(self.dec.SH32[0:-1])
                comb += self.imm_out.ok.eq(1)

        # decode SPR2 based on instruction type
        op = self.dec.op
        # BCREG implicitly uses CTR or LR for 2nd reg
        with m.If(op.internal_op == InternalOp.OP_BCREG):
            with m.If(self.dec.FormXL.XO[9]): # 3.0B p38 top bit of XO
                comb += self.spr_out.data.eq(SPR.CTR)
            with m.Else():
                comb += self.spr_out.data.eq(SPR.LR)
            comb += self.spr_out.ok.eq(1)

        return m


class DecodeC(Elaboratable):
    """DecodeC from instruction

    decodes register RC
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In3Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, "reg_c")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register C field
        with m.If(self.sel_in == In3Sel.RS):
            comb += self.reg_out.data.eq(self.dec.RS[0:-1])
            comb += self.reg_out.ok.eq(1)

        return m


class DecodeOut(Elaboratable):
    """DecodeOut from instruction

    decodes output register RA, RT or SPR
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(OutSel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, "reg_o")
        self.spr_out = Data(10, "spr_o")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register out field
        with m.Switch(self.sel_in):
            with m.Case(OutSel.RT):
                comb += self.reg_out.data.eq(self.dec.RT[0:-1])
                comb += self.reg_out.ok.eq(1)
            with m.Case(OutSel.RA):
                comb += self.reg_out.data.eq(self.dec.RA[0:-1])
                comb += self.reg_out.ok.eq(1)
            with m.Case(OutSel.SPR):
                comb += self.spr_out.data.eq(self.dec.SPR[0:-1]) # from XFX
                comb += self.spr_out.ok.eq(1)

        return m


class DecodeRC(Elaboratable):
    """DecodeRc from instruction

    decodes Record bit Rc
    """
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(RC, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.rc_out = Data(1, "rc")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Record bit out field
        with m.Switch(self.sel_in):
            with m.Case(RC.RC):
                comb += self.rc_out.data.eq(self.dec.Rc[0:-1])
                comb += self.rc_out.ok.eq(1)
            with m.Case(RC.ONE):
                comb += self.rc_out.data.eq(1)
                comb += self.rc_out.ok.eq(1)
            with m.Case(RC.NONE):
                comb += self.rc_out.data.eq(0)
                comb += self.rc_out.ok.eq(1)

        return m

class DecodeCR(Elaboratable):
    """DecodeRc from instruction

    decodes Record bit Rc
    """
    def __init__(self, dec):
        self.dec = dec
        self.cr_out = Data(3, "cr")
        self.insn_in = Signal(32, reset_less=True)
        self.sel_in = Signal(1, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Record bit out field
        with m.If(self.sel_in):
            comb += self.cr_out.data.eq(self.dec.BF[0:-1])

        comb += self.cr_out.ok.eq(self.sel_in)
        return m


class DecodeOE(Elaboratable):
    """DecodeOE from instruction

    decodes OE field: uses RC decode detection which might not be good

    -- For now, use "rc" in the decode table to decide whether oe exists.
    -- This is not entirely correct architecturally: For mulhd and
    -- mulhdu, the OE field is reserved. It remains to be seen what an
    -- actual POWER9 does if we set it on those instructions, for now we
    -- test that further down when assigning to the multiplier oe input.
    """
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(RC, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.oe_out = Data(1, "oe")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select OE bit out field
        with m.Switch(self.sel_in):
            with m.Case(RC.RC):
                comb += self.oe_out.data.eq(self.dec.OE[0:-1])
                comb += self.oe_out.ok.eq(1)

        return m


class XerBits:
    def __init__(self):
        self.ca = Signal(reset_less=True)
        self.ca32 = Signal(reset_less=True)
        self.ov = Signal(reset_less=True)
        self.ov32 = Signal(reset_less=True)
        self.so = Signal(reset_less=True)

    def ports(self):
        return [self.ca, self.ca32, self.ov, self.ov32, self.so, ]


class Decode2ToExecute1Type:

    def __init__(self):

        self.valid = Signal(reset_less=True)
        self.insn_type = Signal(InternalOp, reset_less=True)
        self.nia = Signal(64, reset_less=True)
        self.write_reg = Data(5, name="rego")
        self.read_reg1 = Data(5, name="reg1")
        self.read_reg2 = Data(5, name="reg2")
        self.read_reg3 = Data(5, name="reg3")
        self.imm_data = Data(64, name="imm")
        self.write_spr = Data(10, name="spro")
        self.read_spr1 = Data(10, name="spr1")
        self.read_spr2 = Data(10, name="spr2")
        self.cr_sel    = Data(3, name="cr_sel")
        #self.read_data1 = Signal(64, reset_less=True)
        #self.read_data2 = Signal(64, reset_less=True)
        #self.read_data3 = Signal(64, reset_less=True)
        #self.cr = Signal(32, reset_less=True) # NO: this is from the CR SPR
        #self.xerc = XerBits() # NO: this is from the XER SPR
        self.lk = Signal(reset_less=True)
        self.rc = Data(1, "rc")
        self.oe = Data(1, "oe")
        self.invert_a = Signal(reset_less=True)
        self.invert_out = Signal(reset_less=True)
        self.input_carry = Signal(CryIn, reset_less=True)
        self.output_carry = Signal(reset_less=True)
        self.input_cr = Signal(reset_less=True)
        self.output_cr = Signal(reset_less=True)
        self.is_32bit = Signal(reset_less=True)
        self.is_signed = Signal(reset_less=True)
        self.insn = Signal(32, reset_less=True)
        self.data_len = Signal(4, reset_less=True) # bytes
        self.byte_reverse  = Signal(reset_less=True)
        self.sign_extend  = Signal(reset_less=True)# do we need this?
        self.update  = Signal(reset_less=True) # is this an update instruction?

    def ports(self):
        return [self.valid, self.insn_type, self.nia,
                #self.read_data1, self.read_data2, self.read_data3,
                #self.cr,
                self.lk,
                self.invert_a, self.invert_out,
                self.input_carry, self.output_carry,
                self.input_cr, self.output_cr,
                self.is_32bit, self.is_signed,
                self.insn,
                self.data_len, self.byte_reverse , self.sign_extend ,
                self.update] + \
                self.oe.ports() + \
                self.rc.ports() + \
                self.write_spr.ports() + \
                self.read_spr1.ports() + \
                self.read_spr2.ports() + \
                self.write_reg.ports() + \
                self.read_reg1.ports() + \
                self.read_reg2.ports() + \
                self.read_reg3.ports() + \
                self.imm_data.ports()
                # + self.xerc.ports()

class PowerDecode2(Elaboratable):

    def __init__(self, dec):

        self.dec = dec
        self.e = Decode2ToExecute1Type()

    def ports(self):
        return self.dec.ports() + self.e.ports()

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # set up submodule decoders
        m.submodules.dec = self.dec
        m.submodules.dec_a = dec_a = DecodeA(self.dec)
        m.submodules.dec_b = dec_b = DecodeB(self.dec)
        m.submodules.dec_c = dec_c = DecodeC(self.dec)
        m.submodules.dec_o = dec_o = DecodeOut(self.dec)
        m.submodules.dec_rc = dec_rc = DecodeRC(self.dec)
        m.submodules.dec_oe = dec_oe = DecodeOE(self.dec)
        m.submodules.dec_cr = dec_cr = DecodeCR(self.dec)

        # copy instruction through...
        for i in [self.e.insn, dec_a.insn_in, dec_b.insn_in,
                  dec_c.insn_in, dec_o.insn_in, dec_rc.insn_in,
                  dec_oe.insn_in, dec_cr.insn_in]:
            comb += i.eq(self.dec.opcode_in)

        # ...and subdecoders' input fields
        comb += dec_a.sel_in.eq(self.dec.op.in1_sel)
        comb += dec_b.sel_in.eq(self.dec.op.in2_sel)
        comb += dec_c.sel_in.eq(self.dec.op.in3_sel)
        comb += dec_o.sel_in.eq(self.dec.op.out_sel)
        comb += dec_rc.sel_in.eq(self.dec.op.rc_sel)
        comb += dec_oe.sel_in.eq(self.dec.op.rc_sel) # XXX should be OE sel
        comb += dec_cr.sel_in.eq(self.dec.op.cr_out)

        # decode LD/ST length
        with m.Switch(self.dec.op.ldst_len):
            with m.Case(LdstLen.is1B):
                comb += self.e.data_len.eq(1)
            with m.Case(LdstLen.is2B):
                comb += self.e.data_len.eq(2)
            with m.Case(LdstLen.is4B):
                comb += self.e.data_len.eq(4)
            with m.Case(LdstLen.is8B):
                comb += self.e.data_len.eq(8)

        #comb += self.e.nia.eq(self.dec.nia) # XXX TODO
        itype = Mux(self.dec.op.function_unit == Function.NONE,
                    InternalOp.OP_ILLEGAL,
                    self.dec.op.internal_op)
        comb += self.e.insn_type.eq(itype)

        # registers a, b, c and out
        comb += self.e.read_reg1.eq(dec_a.reg_out)
        comb += self.e.read_reg2.eq(dec_b.reg_out)
        comb += self.e.read_reg3.eq(dec_c.reg_out)
        comb += self.e.write_reg.eq(dec_o.reg_out)
        comb += self.e.imm_data.eq(dec_b.imm_out)

        # rc and oe out
        comb += self.e.rc.eq(dec_rc.rc_out)
        comb += self.e.oe.eq(dec_oe.oe_out)

        # SPRs out
        comb += self.e.read_spr1.eq(dec_a.spr_out)
        comb += self.e.read_spr2.eq(dec_b.spr_out)
        comb += self.e.write_spr.eq(dec_o.spr_out)

        # decoded/selected instruction flags
        comb += self.e.invert_a.eq(self.dec.op.inv_a)
        comb += self.e.invert_out.eq(self.dec.op.inv_out)
        comb += self.e.input_carry.eq(self.dec.op.cry_in)
        comb += self.e.output_carry.eq(self.dec.op.cry_out)
        comb += self.e.is_32bit.eq(self.dec.op.is_32b)
        comb += self.e.is_signed.eq(self.dec.op.sgn)
        with m.If(self.dec.op.lk):
            comb += self.e.lk.eq(self.dec.LK[0:-1]) # XXX TODO: accessor

        comb += self.e.byte_reverse.eq(self.dec.op.br)
        comb += self.e.sign_extend.eq(self.dec.op.sgn_ext)
        comb += self.e.update.eq(self.dec.op.upd)

        comb += self.e.input_cr.eq(self.dec.op.cr_in)
        comb += self.e.output_cr.eq(self.dec.op.cr_out)

        comb += self.e.cr_sel.eq(dec_cr.cr_out)

        return m


if __name__ == '__main__':
    pdecode = create_pdecode()
    dec2 = PowerDecode2(pdecode)
    vl = rtlil.convert(dec2, ports=dec2.ports() + pdecode.ports())
    with open("dec2.il", "w") as f:
        f.write(vl)

