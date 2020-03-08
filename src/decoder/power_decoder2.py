"""Power ISA Decoder second stage

based on Anton Blanchard microwatt decode2.vhdl

"""
from nmigen import Module, Elaboratable, Signal
from power_enums import (InternalOp, CryIn,
                         In1Sel, In2Sel, In3Sel, OutSel, SPR)

class DecodeA(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.ispr1_in = Signal(10, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)
        self.spr_out = Signal(10, reset_less=True)
        self.sprok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register A field
        comb += self.reg_out.eq(self.dec.RA)
        with m.If((self.sel_in == In1Sel.RA) |
                  ((self.sel_in == In1Sel.RA_OR_ZERO) & (ra == Const(0, 5))):
            comb += self.regok_out.eq(1)

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


class DecodeB(Elaboratable):
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.ispr1_in = Signal(10, reset_less=True)
        self.reg_out = Signal(5, reset_less=True)
        self.regok_out = Signal(reset_less=True)
        self.spr_out = Signal(10, reset_less=True)
        self.sprok_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register B field
        comb += self.reg_out.eq(self.dec.RB)
        with m.If((self.sel_in == In1Sel.RB) |
                  ((self.sel_in == In1Sel.RB_OR_ZERO) & (ra == Const(0, 5))):
            comb += self.regok_out.eq(1)

        # decode SPR2 based on instruction type
        op = self.dec.op
        with m.If(op.internal_op == InternalOP.OP_BCREG):
            with m.If(self.dec.FormXL.XO[10]): # 3.0B p38 top bit of XO
                self.spr_out.eq(SPR.CTR)
            with m.Else():
                self.spr_out.eq(SPR.LR)
            self.sprok_out.eq(1)


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

