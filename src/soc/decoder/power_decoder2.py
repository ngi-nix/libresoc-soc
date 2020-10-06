"""Power ISA Decoder second stage

based on Anton Blanchard microwatt decode2.vhdl

Note: OP_TRAP is used for exceptions and interrupts (micro-code style) by
over-riding the internal opcode when an exception is needed.
"""

from nmigen import Module, Elaboratable, Signal, Mux, Const, Cat, Repl, Record
from nmigen.cli import rtlil
from soc.regfile.regfiles import XERRegs

from nmutil.picker import PriorityPicker
from nmutil.iocontrol import RecordObject
from nmutil.extend import exts

from soc.experiment.mem_types import LDSTException

from soc.decoder.power_regspec_map import regspec_decode_read
from soc.decoder.power_regspec_map import regspec_decode_write
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_enums import (MicrOp, CryIn, Function,
                                     CRInSel, CROutSel,
                                     LdstLen, In1Sel, In2Sel, In3Sel,
                                     OutSel, SPR, RC, LDSTMode)
from soc.decoder.decode2execute1 import Decode2ToExecute1Type, Data
from soc.consts import MSR

from soc.regfile.regfiles import FastRegs
from soc.consts import TT
from soc.config.state import CoreState
from soc.regfile.util import spr_to_fast


def decode_spr_num(spr):
    return Cat(spr[5:10], spr[0:5])


def instr_is_priv(m, op, insn):
    """determines if the instruction is privileged or not
    """
    comb = m.d.comb
    is_priv_insn = Signal(reset_less=True)
    with m.Switch(op):
        with m.Case(MicrOp.OP_ATTN, MicrOp.OP_MFMSR, MicrOp.OP_MTMSRD,
                    MicrOp.OP_MTMSR, MicrOp.OP_RFID):
            comb += is_priv_insn.eq(1)
        # XXX TODO
        #with m.Case(MicrOp.OP_TLBIE) : comb += is_priv_insn.eq(1)
        with m.Case(MicrOp.OP_MFSPR, MicrOp.OP_MTSPR):
            with m.If(insn[20]):  # field XFX.spr[-1] i think
                comb += is_priv_insn.eq(1)
    return is_priv_insn


class SPRMap(Elaboratable):
    """SPRMap: maps POWER9 SPR numbers to internal enum values, fast and slow
    """

    def __init__(self):
        self.spr_i = Signal(10, reset_less=True)
        self.spr_o = Data(SPR, name="spr_o")
        self.fast_o = Data(3, name="fast_o")

    def elaborate(self, platform):
        m = Module()
        with m.Switch(self.spr_i):
            for i, x in enumerate(SPR):
                with m.Case(x.value):
                    m.d.comb += self.spr_o.data.eq(i)
                    m.d.comb += self.spr_o.ok.eq(1)
            for x, v in spr_to_fast.items():
                with m.Case(x.value):
                    m.d.comb += self.fast_o.data.eq(v)
                    m.d.comb += self.fast_o.ok.eq(1)
        return m


class DecodeA(Elaboratable):
    """DecodeA from instruction

    decodes register RA, implicit and explicit CSRs
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.insn_in = Signal(32, reset_less=True)
        self.reg_out = Data(5, name="reg_a")
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

        # some Logic/ALU ops have RS as the 3rd arg, but no "RA".
        with m.If(self.sel_in == In1Sel.RS):
            comb += self.reg_out.data.eq(self.dec.RS)
            comb += self.reg_out.ok.eq(1)

        # decode Fast-SPR based on instruction type
        op = self.dec.op
        with m.Switch(op.internal_op):

            # BC or BCREG: implicit register (CTR) NOTE: same in DecodeOut
            with m.Case(MicrOp.OP_BC):
                with m.If(~self.dec.BO[2]):  # 3.0B p38 BO2=0, use CTR reg
                    # constant: CTR
                    comb += self.fast_out.data.eq(FastRegs.CTR)
                    comb += self.fast_out.ok.eq(1)
            with m.Case(MicrOp.OP_BCREG):
                xo9 = self.dec.FormXL.XO[9]  # 3.0B p38 top bit of XO
                xo5 = self.dec.FormXL.XO[5]  # 3.0B p38
                with m.If(xo9 & ~xo5):
                    # constant: CTR
                    comb += self.fast_out.data.eq(FastRegs.CTR)
                    comb += self.fast_out.ok.eq(1)

            # MFSPR move from SPRs
            with m.Case(MicrOp.OP_MFSPR):
                spr = Signal(10, reset_less=True)
                comb += spr.eq(decode_spr_num(self.dec.SPR))  # from XFX
                comb += sprmap.spr_i.eq(spr)
                comb += self.spr_out.eq(sprmap.spr_o)
                comb += self.fast_out.eq(sprmap.fast_o)

        return m


class DecodeAImm(Elaboratable):
    """DecodeA immediate from instruction

    decodes register RA, whether immediate-zero, implicit and
    explicit CSRs
    """

    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In1Sel, reset_less=True)
        self.immz_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # zero immediate requested
        ra = Signal(5, reset_less=True)
        comb += ra.eq(self.dec.RA)
        with m.If((self.sel_in == In1Sel.RA_OR_ZERO) & (ra == Const(0, 5))):
            comb += self.immz_out.eq(1)

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
                # for M-Form shiftrot
                comb += self.reg_out.data.eq(self.dec.RS)
                comb += self.reg_out.ok.eq(1)

        # decode SPR2 based on instruction type
        op = self.dec.op
        # BCREG implicitly uses LR or TAR for 2nd reg
        # CTR however is already in fast_spr1 *not* 2.
        with m.If(op.internal_op == MicrOp.OP_BCREG):
            xo9 = self.dec.FormXL.XO[9]  # 3.0B p38 top bit of XO
            xo5 = self.dec.FormXL.XO[5]  # 3.0B p38
            with m.If(~xo9):
                comb += self.fast_out.data.eq(FastRegs.LR)
                comb += self.fast_out.ok.eq(1)
            with m.Elif(xo5):
                comb += self.fast_out.data.eq(FastRegs.TAR)
                comb += self.fast_out.ok.eq(1)

        return m


class DecodeBImm(Elaboratable):
    """DecodeB immediate from instruction
    """
    def __init__(self, dec):
        self.dec = dec
        self.sel_in = Signal(In2Sel, reset_less=True)
        self.imm_out = Data(64, "imm_b")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # select Register B Immediate
        with m.Switch(self.sel_in):
            with m.Case(In2Sel.CONST_UI): # unsigned
                comb += self.imm_out.data.eq(self.dec.UI)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI):  # sign-extended 16-bit
                si = Signal(16, reset_less=True)
                comb += si.eq(self.dec.SI)
                comb += self.imm_out.data.eq(exts(si, 16, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SI_HI):  # sign-extended 16+16=32 bit
                si_hi = Signal(32, reset_less=True)
                comb += si_hi.eq(self.dec.SI << 16)
                comb += self.imm_out.data.eq(exts(si_hi, 32, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_UI_HI): # unsigned
                ui = Signal(16, reset_less=True)
                comb += ui.eq(self.dec.UI)
                comb += self.imm_out.data.eq(ui << 16)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_LI): # sign-extend 24+2=26 bit
                li = Signal(26, reset_less=True)
                comb += li.eq(self.dec.LI << 2)
                comb += self.imm_out.data.eq(exts(li, 26, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_BD): # sign-extend (14+2)=16 bit
                bd = Signal(16, reset_less=True)
                comb += bd.eq(self.dec.BD << 2)
                comb += self.imm_out.data.eq(exts(bd, 16, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_DS): # sign-extended (14+2=16) bit
                ds = Signal(16, reset_less=True)
                comb += ds.eq(self.dec.DS << 2)
                comb += self.imm_out.data.eq(exts(ds, 16, 64))
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_M1): # signed (-1)
                comb += self.imm_out.data.eq(~Const(0, 64))  # all 1s
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH): # unsigned - for shift
                comb += self.imm_out.data.eq(self.dec.sh)
                comb += self.imm_out.ok.eq(1)
            with m.Case(In2Sel.CONST_SH32): # unsigned - for shift
                comb += self.imm_out.data.eq(self.dec.SH32)
                comb += self.imm_out.ok.eq(1)

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
                # for M-Form shiftrot
                comb += self.reg_out.data.eq(self.dec.RB)
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
                comb += spr.eq(decode_spr_num(self.dec.SPR))  # from XFX
                # MFSPR move to SPRs - needs mapping
                with m.If(op.internal_op == MicrOp.OP_MTSPR):
                    comb += sprmap.spr_i.eq(spr)
                    comb += self.spr_out.eq(sprmap.spr_o)
                    comb += self.fast_out.eq(sprmap.fast_o)

        with m.Switch(op.internal_op):

            # BC or BCREG: implicit register (CTR) NOTE: same in DecodeA
            with m.Case(MicrOp.OP_BC, MicrOp.OP_BCREG):
                with m.If(~self.dec.BO[2]):  # 3.0B p38 BO2=0, use CTR reg
                    # constant: CTR
                    comb += self.fast_out.data.eq(FastRegs.CTR)
                    comb += self.fast_out.ok.eq(1)

            # RFID 1st spr (fast)
            with m.Case(MicrOp.OP_RFID):
                comb += self.fast_out.data.eq(FastRegs.SRR0)  # constant: SRR0
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

        if hasattr(self.dec.op, "upd"):
            # update mode LD/ST uses read-reg A also as an output
            with m.If(self.dec.op.upd == LDSTMode.update):
                comb += self.reg_out.eq(self.dec.RA)
                comb += self.reg_out.ok.eq(1)

        # B, BC or BCREG: potential implicit register (LR) output
        # these give bl, bcl, bclrl, etc.
        op = self.dec.op
        with m.Switch(op.internal_op):

            # BC* implicit register (LR)
            with m.Case(MicrOp.OP_BC, MicrOp.OP_B, MicrOp.OP_BCREG):
                with m.If(self.lk):  # "link" mode
                    comb += self.fast_out.data.eq(FastRegs.LR)  # constant: LR
                    comb += self.fast_out.ok.eq(1)

            # RFID 2nd spr (fast)
            with m.Case(MicrOp.OP_RFID):
                comb += self.fast_out.data.eq(FastRegs.SRR1)  # constant: SRR1
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

        with m.Switch(op.internal_op):

            # mulhw, mulhwu, mulhd, mulhdu - these *ignore* OE
            # also rotate
            # XXX ARGH! ignoring OE causes incompatibility with microwatt
            # http://lists.libre-soc.org/pipermail/libre-soc-dev/2020-August/000302.html
            with m.Case(MicrOp.OP_MUL_H64, MicrOp.OP_MUL_H32,
                        MicrOp.OP_EXTS, MicrOp.OP_CNTZ,
                        MicrOp.OP_SHL, MicrOp.OP_SHR, MicrOp.OP_RLC,
                        MicrOp.OP_LOAD, MicrOp.OP_STORE,
                        MicrOp.OP_RLCL, MicrOp.OP_RLCR,
                        MicrOp.OP_EXTSWSLI):
                pass

            # all other ops decode OE field
            with m.Default():
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
        self.whole_reg = Data(8,  "cr_fxm")

    def elaborate(self, platform):
        m = Module()
        m.submodules.ppick = ppick = PriorityPicker(8, reverse_i=True,
                                                       reverse_o=True)

        comb = m.d.comb
        op = self.dec.op

        comb += self.cr_bitfield.ok.eq(0)
        comb += self.cr_bitfield_b.ok.eq(0)
        comb += self.whole_reg.ok.eq(0)
        with m.Switch(self.sel_in):
            with m.Case(CRInSel.NONE):
                pass  # No bitfield activated
            with m.Case(CRInSel.CR0):
                comb += self.cr_bitfield.data.eq(0) # CR0 (MSB0 numbering)
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
                comb += self.whole_reg.ok.eq(1)
                move_one = Signal(reset_less=True)
                comb += move_one.eq(self.insn_in[20]) # MSB0 bit 11
                with m.If((op.internal_op == MicrOp.OP_MFCR) & move_one):
                    # must one-hot the FXM field
                    comb += ppick.i.eq(self.dec.FXM)
                    comb += self.whole_reg.data.eq(ppick.o)
                with m.Else():
                    # otherwise use all of it
                    comb += self.whole_reg.data.eq(0xff)

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
        self.whole_reg = Data(8,  "cr_fxm")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.dec.op
        m.submodules.ppick = ppick = PriorityPicker(8, reverse_i=True,
                                                       reverse_o=True)

        comb += self.cr_bitfield.ok.eq(0)
        comb += self.whole_reg.ok.eq(0)
        with m.Switch(self.sel_in):
            with m.Case(CROutSel.NONE):
                pass  # No bitfield activated
            with m.Case(CROutSel.CR0):
                comb += self.cr_bitfield.data.eq(0) # CR0 (MSB0 numbering)
                comb += self.cr_bitfield.ok.eq(self.rc_in)  # only when RC=1
            with m.Case(CROutSel.BF):
                comb += self.cr_bitfield.data.eq(self.dec.FormX.BF)
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CROutSel.BT):
                comb += self.cr_bitfield.data.eq(self.dec.FormXL.BT[2:5])
                comb += self.cr_bitfield.ok.eq(1)
            with m.Case(CROutSel.WHOLE_REG):
                comb += self.whole_reg.ok.eq(1)
                move_one = Signal(reset_less=True)
                comb += move_one.eq(self.insn_in[20])
                with m.If((op.internal_op == MicrOp.OP_MTCRF)):
                    with m.If(move_one):
                        # must one-hot the FXM field
                        comb += ppick.i.eq(self.dec.FXM)
                        with m.If(ppick.en_o):
                            comb += self.whole_reg.data.eq(ppick.o)
                        with m.Else():
                            comb += self.whole_reg.data.eq(0b00000001) # CR7
                    with m.Else():
                        comb += self.whole_reg.data.eq(self.dec.FXM)
                with m.Else():
                    # otherwise use all of it
                    comb += self.whole_reg.data.eq(0xff)

        return m

# dictionary of Input Record field names that, if they exist,
# will need a corresponding CSV Decoder file column (actually, PowerOp)
# to be decoded (this includes the single bit names)
record_names = {'insn_type': 'internal_op',
                'fn_unit': 'function_unit',
                'rc': 'rc_sel',
                'oe': 'rc_sel',
                'zero_a': 'in1_sel',
                'imm_data': 'in2_sel',
                'invert_in': 'inv_a',
                'invert_out': 'inv_out',
                'rc': 'cr_out',
                'oe': 'cr_in',
                'output_carry': 'cry_out',
                'input_carry': 'cry_in',
                'is_32bit': 'is_32b',
                'is_signed': 'sgn',
                'lk': 'lk',
                'data_len': 'ldst_len',
                'byte_reverse': 'br',
                'sign_extend': 'sgn_ext',
                'ldst_mode': 'upd',
                }


class PowerDecodeSubset(Elaboratable):
    """PowerDecodeSubset: dynamic subset decoder
    """
    def __init__(self, dec, opkls=None, fn_name=None, final=False, state=None):

        self.final = final
        self.opkls = opkls
        self.fn_name = fn_name
        self.e = Decode2ToExecute1Type(name=self.fn_name, opkls=self.opkls)
        col_subset = self.get_col_subset(self.e.do)

        # create decoder if one not already given
        if dec is None:
            dec = create_pdecode(name=fn_name, col_subset=col_subset,
                                      row_subset=self.rowsubsetfn)
        self.dec = dec

        # state information needed by the Decoder
        if state is None:
            state = CoreState("dec2")
        self.state = state

    def get_col_subset(self, do):
        subset = {'cr_in', 'cr_out', 'rc_sel'} # needed, non-optional
        for k, v in record_names.items():
            if hasattr(do, k):
                subset.add(v)
        print ("get_col_subset", self.fn_name, do.fields, subset)
        return subset

    def rowsubsetfn(self, opcode, row):
        return row['unit'] == self.fn_name

    def ports(self):
        return self.dec.ports() + self.e.ports()

    def needs_field(self, field, op_field):
        if self.final:
            do = self.e.do
        else:
            do = self.e_tmp.do
        return hasattr(do, field) and self.op_get(op_field) is not None

    def do_copy(self, field, val, final=False):
        if final or self.final:
            do = self.e.do
        else:
            do = self.e_tmp.do
        if hasattr(do, field) and val is not None:
            return getattr(do, field).eq(val)
        return []

    def op_get(self, op_field):
        return getattr(self.dec.op, op_field, None)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        state = self.state
        e_out, op, do_out = self.e, self.dec.op, self.e.do
        msr, cia = state.msr, state.pc

        # fill in for a normal instruction (not an exception)
        # copy over if non-exception, non-privileged etc. is detected
        if self.final:
            e = self.e
        else:
            if self.fn_name is None:
                name = "tmp"
            else:
                name = self.fn_name + "tmp"
            self.e_tmp = e = Decode2ToExecute1Type(name=name, opkls=self.opkls)
        do = e.do

        # set up submodule decoders
        m.submodules.dec = self.dec
        m.submodules.dec_rc = dec_rc = DecodeRC(self.dec)
        m.submodules.dec_oe = dec_oe = DecodeOE(self.dec)
        m.submodules.dec_cr_in = self.dec_cr_in = DecodeCRIn(self.dec)
        m.submodules.dec_cr_out = self.dec_cr_out = DecodeCROut(self.dec)

        # copy instruction through...
        for i in [do.insn,
                  dec_rc.insn_in, dec_oe.insn_in,
                  self.dec_cr_in.insn_in, self.dec_cr_out.insn_in]:
            comb += i.eq(self.dec.opcode_in)

        # ...and subdecoders' input fields
        comb += dec_rc.sel_in.eq(op.rc_sel)
        comb += dec_oe.sel_in.eq(op.rc_sel)  # XXX should be OE sel
        comb += self.dec_cr_in.sel_in.eq(op.cr_in)
        comb += self.dec_cr_out.sel_in.eq(op.cr_out)
        comb += self.dec_cr_out.rc_in.eq(dec_rc.rc_out.data)

        # copy "state" over
        comb += self.do_copy("msr", msr)
        comb += self.do_copy("cia", cia)

        # set up instruction, pick fn unit
        # no op: defaults to OP_ILLEGAL
        comb += self.do_copy("insn_type", self.op_get("internal_op"))
        comb += self.do_copy("fn_unit", self.op_get("function_unit"))

        # immediates
        if self.needs_field("zero_a", "in1_sel"):
            m.submodules.dec_ai = dec_ai = DecodeAImm(self.dec)
            comb += dec_ai.sel_in.eq(op.in1_sel)
            comb += self.do_copy("zero_a", dec_ai.immz_out)  # RA==0 detected
        if self.needs_field("imm_data", "in2_sel"):
            m.submodules.dec_bi = dec_bi = DecodeBImm(self.dec)
            comb += dec_bi.sel_in.eq(op.in2_sel)
            comb += self.do_copy("imm_data", dec_bi.imm_out) # imm in RB

        # rc and oe out
        comb += self.do_copy("rc", dec_rc.rc_out)
        comb += self.do_copy("oe", dec_oe.oe_out)

        # CR in/out
        comb += self.do_copy("read_cr_whole", self.dec_cr_in.whole_reg)
        comb += self.do_copy("write_cr_whole", self.dec_cr_out.whole_reg)
        comb += self.do_copy("write_cr0", self.dec_cr_out.cr_bitfield.ok)

        comb += self.do_copy("input_cr", self.op_get("cr_in"))   # CR in
        comb += self.do_copy("output_cr", self.op_get("cr_out"))  # CR out

        # decoded/selected instruction flags
        comb += self.do_copy("data_len", self.op_get("ldst_len"))
        comb += self.do_copy("invert_in", self.op_get("inv_a"))
        comb += self.do_copy("invert_out", self.op_get("inv_out"))
        comb += self.do_copy("input_carry", self.op_get("cry_in"))
        comb += self.do_copy("output_carry", self.op_get("cry_out"))
        comb += self.do_copy("is_32bit", self.op_get("is_32b"))
        comb += self.do_copy("is_signed", self.op_get("sgn"))
        lk = self.op_get("lk")
        if lk is not None:
            with m.If(lk):
                comb += self.do_copy("lk", self.dec.LK)  # XXX TODO: accessor

        comb += self.do_copy("byte_reverse", self.op_get("br"))
        comb += self.do_copy("sign_extend", self.op_get("sgn_ext"))
        comb += self.do_copy("ldst_mode", self.op_get("upd"))  # LD/ST mode

        return m


class PowerDecode2(PowerDecodeSubset):
    """PowerDecode2: the main instruction decoder.

    whilst PowerDecode is responsible for decoding the actual opcode, this
    module encapsulates further specialist, sparse information and
    expansion of fields that is inconvenient to have in the CSV files.
    for example: the encoding of the immediates, which are detected
    and expanded out to their full value from an annotated (enum)
    representation.

    implicit register usage is also set up, here.  for example: OP_BC
    requires implicitly reading CTR, OP_RFID requires implicitly writing
    to SRR1 and so on.

    in addition, PowerDecoder2 is responsible for detecting whether
    instructions are illegal (or privileged) or not, and instead of
    just leaving at that, *replacing* the instruction to execute with
    a suitable alternative (trap).

    LDSTExceptions are done the cycle _after_ they're detected (after
    they come out of LDSTCompUnit).  basically despite the instruction
    being decoded, the results of the decode are completely ignored
    and "exception.happened" used to set the "actual" instruction to
    "OP_TRAP".  the LDSTException data structure gets filled in,
    in the CompTrapOpSubset and that's what it fills in SRR.

    to make this work, TestIssuer must notice "exception.happened"
    after the (failed) LD/ST and copies the LDSTException info from
    the output, into here (PowerDecoder2).  without incrementing PC.
    """

    def __init__(self, dec, opkls=None, fn_name=None, final=False, state=None):
        super().__init__(dec, opkls, fn_name, final, state)
        self.exc = LDSTException("dec2_exc")

    def get_col_subset(self, opkls):
        subset = super().get_col_subset(opkls)
        subset.add("in1_sel")
        subset.add("asmcode")
        subset.add("in2_sel")
        subset.add("in3_sel")
        subset.add("out_sel")
        subset.add("lk")
        subset.add("internal_op")
        subset.add("form")
        return subset

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        state = self.state
        e_out, op, do_out = self.e, self.dec.op, self.e.do
        dec_spr, msr, cia, ext_irq = state.dec, state.msr, state.pc, state.eint
        e = self.e_tmp
        do = e.do

        # fill in for a normal instruction (not an exception)
        # copy over if non-exception, non-privileged etc. is detected

        # set up submodule decoders
        m.submodules.dec_a = dec_a = DecodeA(self.dec)
        m.submodules.dec_b = dec_b = DecodeB(self.dec)
        m.submodules.dec_c = dec_c = DecodeC(self.dec)
        m.submodules.dec_o = dec_o = DecodeOut(self.dec)
        m.submodules.dec_o2 = dec_o2 = DecodeOut2(self.dec)

        # copy instruction through...
        for i in [do.insn, dec_a.insn_in, dec_b.insn_in,
                  dec_c.insn_in, dec_o.insn_in, dec_o2.insn_in]:
            comb += i.eq(self.dec.opcode_in)

        # ...and subdecoders' input fields
        comb += dec_a.sel_in.eq(op.in1_sel)
        comb += dec_b.sel_in.eq(op.in2_sel)
        comb += dec_c.sel_in.eq(op.in3_sel)
        comb += dec_o.sel_in.eq(op.out_sel)
        comb += dec_o2.sel_in.eq(op.out_sel)
        if hasattr(do, "lk"):
            comb += dec_o2.lk.eq(do.lk)

        # registers a, b, c and out and out2 (LD/ST EA)
        comb += e.read_reg1.eq(dec_a.reg_out)
        comb += e.read_reg2.eq(dec_b.reg_out)
        comb += e.read_reg3.eq(dec_c.reg_out)
        comb += e.write_reg.eq(dec_o.reg_out)
        comb += e.write_ea.eq(dec_o2.reg_out)

        # SPRs out
        comb += e.read_spr1.eq(dec_a.spr_out)
        comb += e.write_spr.eq(dec_o.spr_out)

        # Fast regs out
        comb += e.read_fast1.eq(dec_a.fast_out)
        comb += e.read_fast2.eq(dec_b.fast_out)
        comb += e.write_fast1.eq(dec_o.fast_out)
        comb += e.write_fast2.eq(dec_o2.fast_out)

        # condition registers (CR)
        comb += e.read_cr1.eq(self.dec_cr_in.cr_bitfield)
        comb += e.read_cr2.eq(self.dec_cr_in.cr_bitfield_b)
        comb += e.read_cr3.eq(self.dec_cr_in.cr_bitfield_o)
        comb += e.write_cr.eq(self.dec_cr_out.cr_bitfield)

        # sigh this is exactly the sort of thing for which the
        # decoder is designed to not need.  MTSPR, MFSPR and others need
        # access to the XER bits.  however setting e.oe is not appropriate
        with m.If(op.internal_op == MicrOp.OP_MFSPR):
            comb += e.xer_in.eq(0b111) # SO, CA, OV
        with m.If(op.internal_op == MicrOp.OP_CMP):
            comb += e.xer_in.eq(1<<XERRegs.SO) # SO
        with m.If(op.internal_op == MicrOp.OP_MTSPR):
            comb += e.xer_out.eq(1)

        # set the trapaddr to 0x700 for a td/tw/tdi/twi operation
        with m.If(op.internal_op == MicrOp.OP_TRAP):
            # *DO NOT* call self.trap here.  that would reset absolutely
            # everything including destroying read of RA and RB.
            comb += self.do_copy("trapaddr", 0x70) # strip first nibble

        ####################
        # ok so the instruction's been decoded, blah blah, however
        # now we need to determine if it's actually going to go ahead...
        # *or* if in fact it's a privileged operation, whether there's
        # an external interrupt, etc. etc.  this is a simple priority
        # if-elif-elif sequence.  decrement takes highest priority,
        # EINT next highest, privileged operation third.

        # check if instruction is privileged
        is_priv_insn = instr_is_priv(m, op.internal_op, e.do.insn)

        # different IRQ conditions
        ext_irq_ok = Signal()
        dec_irq_ok = Signal()
        priv_ok = Signal()
        illeg_ok = Signal()
        exc = self.exc

        comb += ext_irq_ok.eq(ext_irq & msr[MSR.EE]) # v3.0B p944 (MSR.EE)
        comb += dec_irq_ok.eq(dec_spr[63] & msr[MSR.EE]) # 6.5.11 p1076
        comb += priv_ok.eq(is_priv_insn & msr[MSR.PR])
        comb += illeg_ok.eq(op.internal_op == MicrOp.OP_ILLEGAL)

        # LD/ST exceptions.  TestIssuer copies the exception info at us
        # after a failed LD/ST.
        with m.If(exc.happened):
            with m.If(exc.alignment):
                self.trap(m, TT.MEMEXC, 0x600)
            with m.Elif(exc.instr_fault):
                with m.If(exc.segment_fault):
                    self.trap(m, TT.MEMEXC, 0x480)
                with m.Else():
                    # TODO
                    #srr1(63 - 33) <= exc.invalid;
                    #srr1(63 - 35) <= exc.perm_error; -- noexec fault
                    #srr1(63 - 44) <= exc.badtree;
                    #srr1(63 - 45) <= exc.rc_error;
                    self.trap(m, TT.MEMEXC, 0x400)
            with m.Else():
                with m.If(exc.segment_fault):
                    self.trap(m, TT.MEMEXC, 0x380)
                with m.Else():
                    self.trap(m, TT.MEMEXC, 0x300)

        # decrement counter (v3.0B p1099): TODO 32-bit version (MSR.LPCR)
        with m.Elif(dec_irq_ok):
            self.trap(m, TT.DEC, 0x900)   # v3.0B 6.5 p1065

        # external interrupt? only if MSR.EE set
        with m.Elif(ext_irq_ok):
            self.trap(m, TT.EINT, 0x500)

        # privileged instruction trap
        with m.Elif(priv_ok):
            self.trap(m, TT.PRIV, 0x700)

        # illegal instruction must redirect to trap. this is done by
        # *overwriting* the decoded instruction and starting again.
        # (note: the same goes for interrupts and for privileged operations,
        # just with different trapaddr and traptype)
        with m.Elif(illeg_ok):
            # illegal instruction trap
            self.trap(m, TT.ILLEG, 0x700)

        # no exception, just copy things to the output
        with m.Else():
            comb += e_out.eq(e)

        ####################
        # follow-up after trap/irq to set up SRR0/1

        # trap: (note e.insn_type so this includes OP_ILLEGAL) set up fast regs
        # Note: OP_SC could actually be modified to just be a trap
        with m.If((do_out.insn_type == MicrOp.OP_TRAP) |
                  (do_out.insn_type == MicrOp.OP_SC)):
            # TRAP write fast1 = SRR0
            comb += e_out.write_fast1.data.eq(FastRegs.SRR0)  # constant: SRR0
            comb += e_out.write_fast1.ok.eq(1)
            # TRAP write fast2 = SRR1
            comb += e_out.write_fast2.data.eq(FastRegs.SRR1)  # constant: SRR1
            comb += e_out.write_fast2.ok.eq(1)

        # RFID: needs to read SRR0/1
        with m.If(do_out.insn_type == MicrOp.OP_RFID):
            # TRAP read fast1 = SRR0
            comb += e_out.read_fast1.data.eq(FastRegs.SRR0)  # constant: SRR0
            comb += e_out.read_fast1.ok.eq(1)
            # TRAP read fast2 = SRR1
            comb += e_out.read_fast2.data.eq(FastRegs.SRR1)  # constant: SRR1
            comb += e_out.read_fast2.ok.eq(1)

        # annoying simulator bug
        if hasattr(e_out, "asmcode") and hasattr(self.dec.op, "asmcode"):
            comb += e_out.asmcode.eq(self.dec.op.asmcode)

        return m

    def trap(self, m, traptype, trapaddr):
        """trap: this basically "rewrites" the decoded instruction as a trap
        """
        comb = m.d.comb
        op, e = self.dec.op, self.e
        comb += e.eq(0)  # reset eeeeeverything

        # start again
        comb += self.do_copy("insn", self.dec.opcode_in, True)
        comb += self.do_copy("insn_type", MicrOp.OP_TRAP, True)
        comb += self.do_copy("fn_unit", Function.TRAP, True)
        comb += self.do_copy("trapaddr", trapaddr >> 4, True) # bottom 4 bits
        comb += self.do_copy("traptype", traptype, True)  # request type
        comb += self.do_copy("msr", self.state.msr, True) # copy of MSR "state"
        comb += self.do_copy("cia", self.state.pc, True)  # copy of PC "state"


def get_rdflags(e, cu):
    rdl = []
    for idx in range(cu.n_src):
        regfile, regname, _ = cu.get_in_spec(idx)
        rdflag, read = regspec_decode_read(e, regfile, regname)
        rdl.append(rdflag)
    print("rdflags", rdl)
    return Cat(*rdl)


if __name__ == '__main__':
    pdecode = create_pdecode()
    dec2 = PowerDecode2(pdecode)
    vl = rtlil.convert(dec2, ports=dec2.ports() + pdecode.ports())
    with open("dec2.il", "w") as f:
        f.write(vl)
