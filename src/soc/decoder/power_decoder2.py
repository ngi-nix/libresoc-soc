"""Power ISA Decoder second stage

based on Anton Blanchard microwatt decode2.vhdl

Note: OP_TRAP is used for exceptions and interrupts (micro-code style) by
over-riding the internal opcode when an exception is needed.
"""

from nmigen import Module, Elaboratable, Signal, Mux, Const, Cat, Repl, Record
from nmigen.cli import rtlil

from nmutil.iocontrol import RecordObject
from nmutil.extend import exts

from soc.decoder.power_regspec_map import regspec_decode_read
from soc.decoder.power_regspec_map import regspec_decode_write
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_enums import (InternalOp, CryIn, Function,
                                     CRInSel, CROutSel,
                                     LdstLen, In1Sel, In2Sel, In3Sel,
                                     OutSel, SPR, RC)
from soc.decoder.decode2execute1 import Decode2ToExecute1Type, Data

from soc.regfile.regfiles import FastRegs

# see traptype (and trap main_stage.py)

TT_FP = 1<<0
TT_PRIV = 1<<1
TT_TRAP = 1<<2
TT_ADDR = 1<<3
TT_ILLEG = 1<<4

def decode_spr_num(spr):
    return Cat(spr[5:10], spr[0:5])


def instr_is_priv(m, op, insn):
    """determines if the instruction is privileged or not
    """
    comb = m.d.comb
    Signal = is_priv_insn(reset_less=True)
    with m.Switch(op):
        with m.Case(InternalOp.OP_ATTN)  : comb += is_priv_insn.eq(1)
        with m.Case(InternalOp.OP_MFMSR) : comb += is_priv_insn.eq(1)
        with m.Case(InternalOp.OP_MTMSRD): comb += is_priv_insn.eq(1)
        with m.Case(InternalOp.OP_MTMSR): comb += is_priv_insn.eq(1)
        with m.Case(InternalOp.OP_RFID)  : comb += is_priv_insn.eq(1)
        with m.Case(InternalOp.OP_TLBIE) : comb += is_priv_insn.eq(1)
    with m.If(op == OP_MFSPR | op == OP_MTSPR):
        with m.If(insn[20]): # field XFX.spr[-1] i think
            comb += is_priv_insn.eq(1)
    return is_priv_insn


class SPRMap(Elaboratable):
    """SPRMap: maps POWER9 SPR numbers to internal enum values
    """
    def __init__(self):
        self.spr_i = Signal(10, reset_less=True)
        self.spr_o = Signal(SPR, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        with m.Switch(self.spr_i):
            for i, x in enumerate(SPR):
                with m.Case(x.value):
                    m.d.comb += self.spr_o.eq(i)
        return m


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
        self.spr_out = Data(SPR, "spr_a")
        self.fast_out = Data(3, "fast_a")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.sprmap = sprmap = SPRMap()

        # select Register A field
        ra = Signal(5, reset_less=True)
        comb += ra.eq(self.dec.RA)
        with m.If((self.sel_in == In1Sel.RA) |
                  ((self.sel_in == In1Sel.RA_OR_ZERO) &
                   (ra != Const(0, 5)))):
            comb += self.reg_out.data.eq(ra)
            comb += self.reg_out.ok.eq(1)

        # zero immediate requested
        with m.If((self.sel_in == In1Sel.RA_OR_ZERO) &
                  (self.reg_out.data == Const(0, 5))):
            comb += self.immz_out.eq(1)

        # some Logic/ALU ops have RS as the 3rd arg, but no "RA".
        with m.If(self.sel_in == In1Sel.RS):
            comb += self.reg_out.data.eq(self.dec.RS)
            comb += self.reg_out.ok.eq(1)

        # decode Fast-SPR based on instruction type
        op = self.dec.op
        # BC or BCREG: potential implicit register (CTR) NOTE: same in DecodeOut
        with m.If(op.internal_op == InternalOp.OP_BC):
            with m.If(~self.dec.BO[2]): # 3.0B p38 BO2=0, use CTR reg
                comb += self.fast_out.data.eq(FastRegs.CTR) # constant: CTR
                comb += self.fast_out.ok.eq(1)
        with m.Elif(op.internal_op == InternalOp.OP_BCREG):
            xo9 = self.dec.FormXL.XO[9] # 3.0B p38 top bit of XO
            xo5 = self.dec.FormXL.XO[5] # 3.0B p38
            with m.If(xo9 & ~xo5):
                comb += self.fast_out.data.eq(FastRegs.CTR) # constant: CTR
                comb += self.fast_out.ok.eq(1)

        # MFSPR move from SPRs
        with m.If(op.internal_op == InternalOp.OP_MFSPR):
            spr = Signal(10, reset_less=True)
            comb += spr.eq(decode_spr_num(self.dec.SPR)) # from XFX
            with m.Switch(spr):
                # fast SPRs
                with m.Case(SPR.CTR.value):
                    comb += self.fast_out.data.eq(FastRegs.CTR)
                    comb += self.fast_out.ok.eq(1)
                with m.Case(SPR.LR.value):
                    comb += self.fast_out.data.eq(FastRegs.LR)
                    comb += self.fast_out.ok.eq(1)
                with m.Case(SPR.TAR.value):
                    comb += self.fast_out.data.eq(FastRegs.TAR)
                    comb += self.fast_out.ok.eq(1)
                with m.Case(SPR.SRR0.value):
                    comb += self.fast_out.data.eq(FastRegs.SRR0)
                    comb += self.fast_out.ok.eq(1)
                with m.Case(SPR.SRR1.value):
                    comb += self.fast_out.data.eq(FastRegs.SRR1)
                    comb += self.fast_out.ok.eq(1)
                with m.Case(SPR.XER.value):
                    pass # do nothing
                # XXX TODO: map to internal SPR numbers
                # XXX TODO: dec and tb not to go through mapping.
                with m.Default():
                    comb += sprmap.spr_i.eq(spr)
                    comb += self.spr_out.data.eq(sprmap.spr_o)
                    comb += self.spr_out.ok.eq(1)


        return m


class DecodeB(Elaboratable):
    """DecodeB from instruction

    decodes register RB, different forms of immediate (signed, unsigned),
    and implicit SPRs.  register B is basically "lane 2" into the CompUnits.
    by industry-standard convention, "lane 2" is where fully-decoded
    immediates are muxed in.
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In2Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, "reg_b")
        self.imm_out = Data(64, "imm_b")
        self.fast_out = Data(3, "fast_b")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register B field
        with m.Switch(self.sel_in):
            with m.Case(In2Sel.RB):
                comb += self.reg_out.data.eq(self.dec.RB)
                comb += self.reg_out.ok.eq(1)
            with m.Case(In2Sel.RS):
                comb += self.reg_out.data.eq(self.dec.RS) # for M-Form shiftrot
                comb += self.reg_out.ok.eq(1)
            with m.Case(In2Sel.CONST_UI):
                comb += self.imm_out.data.eq(self.dec.UI)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI): # TODO: sign-extend here?
                comb += self.imm_out.data.eq(
                    exts(self.dec.SI, 16, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_UI_HI):
                comb += self.imm_out.data.eq(self.dec.UI<<16)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI_HI): # TODO: sign-extend here?
                comb += self.imm_out.data.eq(self.dec.SI<<16)
                comb += self.imm_out.data.eq(
                    exts(self.dec.SI << 16, 32, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_LI):
                comb += self.imm_out.data.eq(self.dec.LI<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_BD):
                comb += self.imm_out.data.eq(self.dec.BD<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_DS):
                comb += self.imm_out.data.eq(self.dec.DS<<2)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_M1):
                comb += self.imm_out.data.eq(~Const(0, 64)) # all 1s
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH):
                comb += self.imm_out.data.eq(self.dec.sh)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH32):
                comb += self.imm_out.data.eq(self.dec.SH32)
                comb += self.imm_out.ok.eq(1)

        # decode SPR2 based on instruction type
        op = self.dec.op
        # BCREG implicitly uses LR or TAR for 2nd reg
        # CTR however is already in fast_spr1 *not* 2.
        with m.If(op.internal_op == InternalOp.OP_BCREG):
            xo9 = self.dec.FormXL.XO[9] # 3.0B p38 top bit of XO
            xo5 = self.dec.FormXL.XO[5] # 3.0B p38
            with m.If(~xo9):
                comb += self.fast_out.data.eq(FastRegs.LR)
                comb += self.fast_out.ok.eq(1)
            with m.Elif(xo5):
                comb += self.fast_out.data.eq(FastRegs.TAR)
                comb += self.fast_out.ok.eq(1)

        return m


class DecodeC(Elaboratable):
    """DecodeC from instruction

    decodes register RC.  this is "lane 3" into some CompUnits (not many)
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
        with m.Switch(self.sel_in):
            with m.Case(In3Sel.RB):
                comb += self.reg_out.data.eq(self.dec.RB) # for M-Form shiftrot
                comb += self.reg_out.ok.eq(1)
            with m.Case(In3Sel.RS):
                comb += self.reg_out.data.eq(self.dec.RS)
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
        self.spr_out = Data(SPR, "spr_o")
        self.fast_out = Data(3, "fast_o")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.sprmap = sprmap = SPRMap()
        op = self.dec.op

        # select Register out field
        with m.Switch(self.sel_in):
            with m.Case(OutSel.RT):
                comb += self.reg_out.data.eq(self.dec.RT)
                comb += self.reg_out.ok.eq(1)
            with m.Case(OutSel.RA):
                comb += self.reg_out.data.eq(self.dec.RA)
                comb += self.reg_out.ok.eq(1)
            with m.Case(OutSel.SPR):
                spr = Signal(10, reset_less=True)
                comb += spr.eq(decode_spr_num(self.dec.SPR)) # from XFX
                # TODO MTSPR 1st spr (fast)
                with m.If(op.internal_op == InternalOp.OP_MTSPR):
                    with m.Switch(spr):
                        # fast SPRs
                        with m.Case(SPR.CTR.value):
                            comb += self.fast_out.data.eq(FastRegs.CTR)
                            comb += self.fast_out.ok.eq(1)
                        with m.Case(SPR.LR.value):
                            comb += self.fast_out.data.eq(FastRegs.LR)
                            comb += self.fast_out.ok.eq(1)
                        with m.Case(SPR.TAR.value):
                            comb += self.fast_out.data.eq(FastRegs.TAR)
                            comb += self.fast_out.ok.eq(1)
                        with m.Case(SPR.SRR0.value):
                            comb += self.fast_out.data.eq(FastRegs.SRR0)
                            comb += self.fast_out.ok.eq(1)
                        with m.Case(SPR.SRR1.value):
                            comb += self.fast_out.data.eq(FastRegs.SRR1)
                            comb += self.fast_out.ok.eq(1)
                        with m.Case(SPR.XER.value):
                            pass # do nothing
                        # XXX TODO: map to internal SPR numbers
                        # XXX TODO: dec and tb not to go through mapping.
                        with m.Default():
                            comb += sprmap.spr_i.eq(spr)
                            comb += self.spr_out.data.eq(sprmap.spr_o)
                            comb += self.spr_out.ok.eq(1)

        # BC or BCREG: potential implicit register (CTR) NOTE: same in DecodeA
        op = self.dec.op
        with m.If((op.internal_op == InternalOp.OP_BC) |
                  (op.internal_op == InternalOp.OP_BCREG)):
            with m.If(~self.dec.BO[2]): # 3.0B p38 BO2=0, use CTR reg
                comb += self.fast_out.data.eq(FastRegs.CTR) # constant: CTR
                comb += self.fast_out.ok.eq(1)

        # RFID 1st spr (fast)
        with m.If(op.internal_op == InternalOp.OP_RFID):
            comb += self.fast_out.data.eq(FastRegs.SRR0) # constant: SRR0
            comb += self.fast_out.ok.eq(1)

        return m


class DecodeOut2(Elaboratable):
    """DecodeOut2 from instruction

    decodes output registers
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(OutSel, reset_less=True)
        self.lk = Signal(reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, "reg_o")
        self.fast_out = Data(3, "fast_o")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # update mode LD/ST uses read-reg A also as an output
        with m.If(self.dec.op.upd):
            comb += self.reg_out.eq(self.dec.RA)
            comb += self.reg_out.ok.eq(1)

        # B, BC or BCREG: potential implicit register (LR) output
        # these give bl, bcl, bclrl, etc.
        op = self.dec.op
        with m.If((op.internal_op == InternalOp.OP_BC) |
                  (op.internal_op == InternalOp.OP_B) |
                  (op.internal_op == InternalOp.OP_BCREG)):
            with m.If(self.lk): # "link" mode
                comb += self.fast_out.data.eq(FastRegs.LR) # constant: LR
                comb += self.fast_out.ok.eq(1)

        # RFID 2nd spr (fast)
        with m.If(op.internal_op == InternalOp.OP_RFID):
                comb += self.fast_out.data.eq(FastRegs.SRR1) # constant: SRR1
                comb += self.fast_out.ok.eq(1)

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
                comb += self.rc_out.data.eq(self.dec.Rc)
                comb += self.rc_out.ok.eq(1)
            with m.Case(RC.ONE):
                comb += self.rc_out.data.eq(1)
                comb += self.rc_out.ok.eq(1)
            with m.Case(RC.NONE):
                comb += self.rc_out.data.eq(0)
                comb += self.rc_out.ok.eq(1)

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
        op = self.dec.op

        with m.If((op.internal_op == InternalOp.OP_MUL_H64) |
                  (op.internal_op == InternalOp.OP_MUL_H32)):
            # mulhw, mulhwu, mulhd, mulhdu - these *ignore* OE
            pass
        with m.Else():
            # select OE bit out field
            with m.Switch(self.sel_in):
                with m.Case(RC.RC):
                    comb += self.oe_out.data.eq(self.dec.OE)
                    comb += self.oe_out.ok.eq(1)

        return m

class DecodeCRIn(Elaboratable):
    """Decodes input CR from instruction

    CR indices - insn fields - (not the data *in* the CR) require only 3
    bits because they refer to CR0-CR7
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(CRInSel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.cr_bitfield = Data(3, "cr_bitfield")
        self.cr_bitfield_b = Data(3, "cr_bitfield_b")
        self.cr_bitfield_o = Data(3, "cr_bitfield_o")
        self.whole_reg = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        comb += self.cr_bitfield.ok.eq(0)
        comb += self.cr_bitfield_b.ok.eq(0)
        comb += self.whole_reg.eq(0)
        with m.Switch(self.sel_in):
            with m.Case(CRInSel.NONE):
                pass # No bitfield activated
            with m.Case(CRInSel.CR0):
                comb += self.cr_bitfield.data.eq(0)
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CRInSel.BI):
                comb += self.cr_bitfield.data.eq(self.dec.BI[2:5])
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CRInSel.BFA):
                comb += self.cr_bitfield.data.eq(self.dec.FormX.BFA)
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CRInSel.BA_BB):
                comb += self.cr_bitfield.data.eq(self.dec.BA[2:5])
                comb += self.cr_bitfield.ok.eq(1)
                comb += self.cr_bitfield_b.data.eq(self.dec.BB[2:5])
                comb += self.cr_bitfield_b.ok.eq(1)
                comb += self.cr_bitfield_o.data.eq(self.dec.BT[2:5])
                comb += self.cr_bitfield_o.ok.eq(1)
            with m.Case(CRInSel.BC):
                comb += self.cr_bitfield.data.eq(self.dec.BC[2:5])
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CRInSel.WHOLE_REG):
                comb += self.whole_reg.eq(1)

        return m


class DecodeCROut(Elaboratable):
    """Decodes input CR from instruction

    CR indices - insn fields - (not the data *in* the CR) require only 3
    bits because they refer to CR0-CR7
    """

    def __init__(self, dec):
        self.dec = dec
        self.rc_in = Signal(reset_less=True)
        self.sel_in = Signal(CROutSel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.cr_bitfield = Data(3, "cr_bitfield")
        self.whole_reg = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        comb += self.cr_bitfield.ok.eq(0)
        comb += self.whole_reg.eq(0)
        with m.Switch(self.sel_in):
            with m.Case(CROutSel.NONE):
                pass # No bitfield activated
            with m.Case(CROutSel.CR0):
                comb += self.cr_bitfield.data.eq(0)
                comb += self.cr_bitfield.ok.eq(self.rc_in) # only when RC=1
            with m.Case(CROutSel.BF):
                comb += self.cr_bitfield.data.eq(self.dec.FormX.BF)
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CROutSel.BT):
                comb += self.cr_bitfield.data.eq(self.dec.FormXL.BT[2:5])
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CROutSel.WHOLE_REG):
                comb += self.whole_reg.eq(1)

        return m


class XerBits:
    def __init__(self):
        self.ca = Signal(2, reset_less=True)
        self.ov = Signal(2, reset_less=True)
        self.so = Signal(reset_less=True)

    def ports(self):
        return [self.ca, self.ov, self.so]


class PowerDecode2(Elaboratable):

    def __init__(self, dec):

        self.dec = dec
        self.e = Decode2ToExecute1Type()
        self.valid = Signal() # sync signal

    def ports(self):
        return self.dec.ports() + self.e.ports()

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        e, op, do = self.e, self.dec.op, self.e.do

        # set up submodule decoders
        m.submodules.dec = self.dec
        m.submodules.dec_a = dec_a = DecodeA(self.dec)
        m.submodules.dec_b = dec_b = DecodeB(self.dec)
        m.submodules.dec_c = dec_c = DecodeC(self.dec)
        m.submodules.dec_o = dec_o = DecodeOut(self.dec)
        m.submodules.dec_o2 = dec_o2 = DecodeOut2(self.dec)
        m.submodules.dec_rc = dec_rc = DecodeRC(self.dec)
        m.submodules.dec_oe = dec_oe = DecodeOE(self.dec)
        m.submodules.dec_cr_in = dec_cr_in = DecodeCRIn(self.dec)
        m.submodules.dec_cr_out = dec_cr_out = DecodeCROut(self.dec)

        # copy instruction through...
        for i in [do.insn, dec_a.insn_in, dec_b.insn_in,
                  dec_c.insn_in, dec_o.insn_in, dec_o2.insn_in, dec_rc.insn_in,
                  dec_oe.insn_in, dec_cr_in.insn_in, dec_cr_out.insn_in]:
            comb += i.eq(self.dec.opcode_in)

        # ...and subdecoders' input fields
        comb += dec_a.sel_in.eq(op.in1_sel)
        comb += dec_b.sel_in.eq(op.in2_sel)
        comb += dec_c.sel_in.eq(op.in3_sel)
        comb += dec_o.sel_in.eq(op.out_sel)
        comb += dec_o2.sel_in.eq(op.out_sel)
        comb += dec_o2.lk.eq(do.lk)
        comb += dec_rc.sel_in.eq(op.rc_sel)
        comb += dec_oe.sel_in.eq(op.rc_sel) # XXX should be OE sel
        comb += dec_cr_in.sel_in.eq(op.cr_in)
        comb += dec_cr_out.sel_in.eq(op.cr_out)
        comb += dec_cr_out.rc_in.eq(dec_rc.rc_out.data)

        # set up instruction, pick fn unit
        comb += e.nia.eq(0)    # XXX TODO (or remove? not sure yet)
        comb += do.insn_type.eq(op.internal_op) # no op: defaults to OP_ILLEGAL
        comb += do.fn_unit.eq(op.function_unit)

        # registers a, b, c and out and out2 (LD/ST EA)
        comb += e.read_reg1.eq(dec_a.reg_out)
        comb += e.read_reg2.eq(dec_b.reg_out)
        comb += e.read_reg3.eq(dec_c.reg_out)
        comb += e.write_reg.eq(dec_o.reg_out)
        comb += e.write_ea.eq(dec_o2.reg_out)
        comb += do.imm_data.eq(dec_b.imm_out) # immediate in RB (usually)
        comb += do.zero_a.eq(dec_a.immz_out)  # RA==0 detected

        # rc and oe out
        comb += do.rc.eq(dec_rc.rc_out)
        comb += do.oe.eq(dec_oe.oe_out)

        # SPRs out
        comb += e.read_spr1.eq(dec_a.spr_out)
        comb += e.write_spr.eq(dec_o.spr_out)

        # Fast regs out
        comb += e.read_fast1.eq(dec_a.fast_out)
        comb += e.read_fast2.eq(dec_b.fast_out)
        comb += e.write_fast1.eq(dec_o.fast_out)
        comb += e.write_fast2.eq(dec_o2.fast_out)

        # condition registers (CR)
        comb += e.read_cr1.eq(dec_cr_in.cr_bitfield)
        comb += e.read_cr2.eq(dec_cr_in.cr_bitfield_b)
        comb += e.read_cr3.eq(dec_cr_in.cr_bitfield_o)
        comb += e.write_cr.eq(dec_cr_out.cr_bitfield)

        comb += do.read_cr_whole.eq(dec_cr_in.whole_reg)
        comb += do.write_cr_whole.eq(dec_cr_out.whole_reg)
        comb += do.write_cr0.eq(dec_cr_out.cr_bitfield.ok)

        # decoded/selected instruction flags
        comb += do.data_len.eq(op.ldst_len)
        comb += do.invert_a.eq(op.inv_a)
        comb += do.invert_out.eq(op.inv_out)
        comb += do.input_carry.eq(op.cry_in)   # carry comes in
        comb += do.output_carry.eq(op.cry_out) # carry goes out
        comb += do.is_32bit.eq(op.is_32b)
        comb += do.is_signed.eq(op.sgn)
        with m.If(op.lk):
            comb += do.lk.eq(self.dec.LK) # XXX TODO: accessor

        comb += do.byte_reverse.eq(op.br)
        comb += do.sign_extend.eq(op.sgn_ext)
        comb += do.ldst_mode.eq(op.upd) # LD/ST mode (update, cache-inhibit)

        # These should be removed eventually
        comb += do.input_cr.eq(op.cr_in)   # condition reg comes in
        comb += do.output_cr.eq(op.cr_out) # condition reg goes in

        # sigh this is exactly the sort of thing for which the
        # decoder is designed to not need.  MTSPR, MFSPR and others need
        # access to the XER bits.  however setting e.oe is not appropriate
        with m.If(op.internal_op == InternalOp.OP_MFSPR):
            comb += e.xer_in.eq(1)
        with m.If(op.internal_op == InternalOp.OP_MTSPR):
            comb += e.xer_out.eq(1)

        # set the trapaddr to 0x700 for a td/tw/tdi/twi operation
        with m.If(op.internal_op == InternalOp.OP_TRAP):
            comb += do.trapaddr.eq(0x70)    # addr=0x700 (strip first nibble)

        # illegal instruction must redirect to trap. this is done by
        # *overwriting* the decoded instruction and starting again.
        # (note: the same goes for interrupts and for privileged operations,
        # just with different trapaddr and traptype)
        with m.If(op.internal_op == InternalOp.OP_ILLEGAL):
            # illegal instruction trap
            self.trap(m, TT_ILLEG, 0x700)

        # trap: (note e.insn_type so this includes OP_ILLEGAL) set up fast regs
        # Note: OP_SC could actually be modified to just be a trap
        with m.If((do.insn_type == InternalOp.OP_TRAP) |
                  (do.insn_type == InternalOp.OP_SC)):
            # TRAP write fast1 = SRR0
            comb += e.write_fast1.data.eq(FastRegs.SRR0) # constant: SRR0
            comb += e.write_fast1.ok.eq(1)
            # TRAP write fast2 = SRR1
            comb += e.write_fast2.data.eq(FastRegs.SRR1) # constant: SRR1
            comb += e.write_fast2.ok.eq(1)

        # RFID: needs to read SRR0/1
        with m.If(do.insn_type == InternalOp.OP_RFID):
            # TRAP read fast1 = SRR0
            comb += e.read_fast1.data.eq(FastRegs.SRR0) # constant: SRR0
            comb += e.read_fast1.ok.eq(1)
            # TRAP read fast2 = SRR1
            comb += e.read_fast2.data.eq(FastRegs.SRR1) # constant: SRR1
            comb += e.read_fast2.ok.eq(1)

        return m

        # TODO: get msr, then can do privileged instruction
        with m.If(instr_is_priv(m, op.internal_op, e.insn) & msr[MSR_PR]):
            # privileged instruction trap
            self.trap(m, TT_PRIV, 0x700)
        return m

    def trap(self, m, traptype, trapaddr):
        """trap: this basically "rewrites" the decoded instruction as a trap
        """
        comb = m.d.comb
        e, op, do = self.e, self.dec.op, self.e.do
        comb += e.eq(0) # reset eeeeeverything
        # start again
        comb += do.insn.eq(self.dec.opcode_in)
        comb += do.insn_type.eq(InternalOp.OP_TRAP)
        comb += do.fn_unit.eq(Function.TRAP)
        comb += do.trapaddr.eq(trapaddr >> 4) # cut bottom 4 bits
        comb += do.traptype.eq(traptype) # request type

    def regspecmap_read(self, regfile, regname):
        """regspecmap_read: provides PowerDecode2 with an encoding relationship
        to Function Unit port regfiles (read-enable, read regnum, write regnum)
        regfile and regname arguments are fields 1 and 2 from a given regspec.
        """
        return regspec_decode_read(self.e, regfile, regname)

    def regspecmap_write(self, regfile, regname):
        """regspecmap_write: provides PowerDecode2 with an encoding relationship
        to Function Unit port regfiles (write port, write regnum)
        regfile and regname arguments are fields 1 and 2 from a given regspec.
        """
        return regspec_decode_write(self.e, regfile, regname)

    def rdflags(self, cu):
        rdl = []
        for idx in range(cu.n_src):
            regfile, regname, _ = cu.get_in_spec(idx)
            rdflag, read = self.regspecmap_read(regfile, regname)
            rdl.append(rdflag)
        print ("rdflags", rdl)
        return Cat(*rdl)


if __name__ == '__main__':
    pdecode = create_pdecode()
    dec2 = PowerDecode2(pdecode)
    vl = rtlil.convert(dec2, ports=dec2.ports() + pdecode.ports())
    with open("dec2.il", "w") as f:
        f.write(vl)

