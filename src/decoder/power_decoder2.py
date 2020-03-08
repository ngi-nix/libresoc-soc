"""Power ISA Decoder second stage

based on Anton Blanchard microwatt decode2.vhdl

"""
from nmigen import Module, Elaboratable, Signal
from power_enums import (InternalOp, CryIn,
                         In1Sel, In2Sel, In3Sel, OutSel, SPR, RC)

class DecodeA(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)
        self.immz_out = Signal(reset_less=True)
        self.spr_out = Signal(10, reset_less=True)
        self.sprok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register A field
        with m.If((self.sel_in == In1Sel.RA) |
                  ((self.sel_in == In1Sel.RA_OR_ZERO) &
                   (self.reg_out != Const(0, 5)))):
            comb += self.reg_out.eq(self.dec.RA)
            comb += self.regok_out.eq(1)

        # zero immediate requested
        with m.If((self.sel_in == In1Sel.RA_OR_ZERO) &
                   (self.reg_out == Const(0, 5))):
            comb += self.immz_out.eq(1)

        # decode SPR1 based on instruction type
        op = self.dec.op
        # BC or BCREG: potential implicit register (CTR)
        with m.If(op.internal_op == InternalOP.OP_BC |
                  op.internal_op == InternalOP.OP_BCREG):
            with m.If(~self.dec.BO[2]): # 3.0B p38 BO2=0, use CTR reg
                self.spr_out.eq(SPR.CTR) # constant: CTR
                self.sprok_out.eq(1)
        # MFSPR or MTSPR: move-from / move-to SPRs
        with m.If(op.internal_op == InternalOP.OP_MFSPR |
                  op.internal_op == InternalOP.OP_MTSPR):
            self.spr_out.eq(self.dec.SPR) # decode SPR field from XFX insn
            self.sprok_out.eq(1)

        return m


class DecodeB(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In2Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)
        self.imm_out = Signal(64, reset_less=True)
        self.immok_out = Signal(reset_less=True)
        self.spr_out = Signal(10, reset_less=True)
        self.sprok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register B field
        with m.Switch(self.sel_in):
            with m.Case(In2Sel.RB):
                comb += self.reg_out.eq(self.dec.RB)
                comb += self.regok_out.eq(1)
            with m.Case(In2Sel.CONST_UI):
                comb += self.imm_out.eq(self.dec.SI)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_SI): # TODO: sign-extend here?
                comb += self.imm_out.eq(self.dec.SI)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_UI_HI):
                comb += self.imm_out.eq(self.dec.UI<<4)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_UI_SI): # TODO: sign-extend here?
                comb += self.imm_out.eq(self.dec.UI<<4)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_LI):
                comb += self.imm_out.eq(self.dec.LI<<2)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_BD):
                comb += self.imm_out.eq(self.dec.BD<<2)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_DS):
                comb += self.imm_out.eq(self.dec.DS<<2)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_M1):
                comb += self.imm_out.eq(~Const(0, 64)) # all 1s
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_SH):
                comb += self.imm_out.eq(self.dec.sh)
                comb += self.immok_out.eq(1)
            with m.Case(In2Sel.CONST_SH32):
                comb += self.imm_out.eq(self.dec.SH32)
                comb += self.immok_out.eq(1)

        # decode SPR2 based on instruction type
        op = self.dec.op
        # BCREG implicitly uses CTR or LR for 2nd reg
        with m.If(op.internal_op == InternalOP.OP_BCREG):
            with m.If(self.dec.FormXL.XO[10]): # 3.0B p38 top bit of XO
                self.spr_out.eq(SPR.CTR)
            with m.Else():
                self.spr_out.eq(SPR.LR)
            self.sprok_out.eq(1)

        return m


class DecodeC(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In3Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register C field
        with m.If(self.sel_in == In3Sel.RC):
            comb += self.reg_out.eq(self.dec.RC)
            comb += self.regok_out.eq(1)

        return m


class DecodeOut(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)
        self.spr_out = Signal(10, reset_less=True)
        self.sprok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register out field
        with m.Switch(self.sel_in):
            with m.Case(In1Sel.RT):
                comb += self.reg_out.eq(self.dec.RT)
                comb += self.regok_out.eq(1)
            with m.Case(In1Sel.RA):
                comb += self.reg_out.eq(self.dec.RA)
                comb += self.regok_out.eq(1)
              with m.Case(In1Sel.SPR):
                self.spr_out.eq(self.dec.SPR) # decode SPR field from XFX insn
                self.sprok_out.eq(1)

        return m


class DecodeRC(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(RC, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.rc_out = Signal(1, reset_less=True)
        self.rcok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Record bit out field
        with m.Switch(self.sel_in):
            with m.Case(RC.RC):
                comb += self.rc_out.eq(self.dec.Rc)
                comb += self.rcok_out.eq(1)
            with m.Case(RC.ONE):
                comb += self.rc_out.eq(1)
                comb += self.rcok_out.eq(1)
              with m.Case(RC.NONE):
                comb += self.rc_out.eq(0)
                comb += self.rcok_out.eq(1)

        return m


class DecodeOE(Elaboratable):
    """
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
        self.oe_out = Signal(1, reset_less=True)
        self.oeok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select OE bit out field
        with m.Switch(self.sel_in):
            with m.Case(RC.RC):
                comb += self.oe_out.eq(self.dec.OE)
                comb += self.oeok_out.eq(1)

        return m


class XerBits:
    def __init__(self):
        self.ca = Signal(reset_less=True)
        self.ca32 = Signal(reset_less=True)
        self.ov = Signal(reset_less=True)
        self.ov32 = Signal(reset_less=True)
        self.so = Signal(reset_less=True)


class PowerDecodeToExecute(Elaboratable):

    def __init__(self, width):

        self.valid = Signal(reset_less=True)
        self.insn_type = Signal(InternalOp, reset_less=True)
        self.nia = Signal(64, reset_less=True)
        self.write_reg = Signal(5, reset_less=True)
        self.read_reg1 = Signal(5, reset_less=True)
        self.read_reg2 = Signal(5, reset_less=True)
        self.read_data1 = Signal(64, reset_less=True)
        self.read_data2 = Signal(64, reset_less=True)
        self.read_data3 = Signal(64, reset_less=True)
        self.cr = Signal(32, reset_less=True)
        self.xerc = XerBits()
        self.lr = Signal(reset_less=True)
        self.rc = Signal(reset_less=True)
        self.oe = Signal(reset_less=True)
        self.invert_a = Signal(reset_less=True)
        self.invert_out = Signal(reset_less=True)
        self.input_carry: Signal(CryIn, reset_less=True)
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

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        return m

