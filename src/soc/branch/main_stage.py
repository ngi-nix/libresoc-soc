# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const, Array)
from nmutil.pipemodbase import PipeModBase
from soc.branch.pipe_data import BranchInputData, BranchOutputData
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange

def br_ext(bd):
    return Cat(Const(0, 2), bd, Repl(bd[-1], 64-(bd.width + 2)))


class BranchMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return BranchInputData(self.pspec)

    def ospec(self):
        return BranchOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        lk = op.lk # see PowerDecode2 as to why this is done
        nia_out, lr = self.o.nia_out, self.o.lr

        # obtain relevant instruction fields
        i_fields = self.fields.instrs['I']
        aa = Signal(i_fields['AA'][0:-1].shape())
        comb += aa.eq(i_fields['AA'][0:-1])

        br_imm_addr = Signal(64, reset_less=True)
        br_addr = Signal(64, reset_less=True)
        br_taken = Signal(reset_less=True)

        # Handle absolute or relative branches
        with m.If(aa):
            comb += br_addr.eq(br_imm_addr)
        with m.Else():
            comb += br_addr.eq(br_imm_addr + self.i.cia)

        # fields for conditional branches (BO and BI are same for BC and BCREG)
        # NOTE: here, BO and BI we would like be treated as CR regfile
        # selectors (similar to RA, RB, RS, RT).  see comment here:
        # https://bugs.libre-soc.org/show_bug.cgi?id=313#c2
        b_fields = self.fields.instrs['B']
        bo = Signal(b_fields['BO'][0:-1].shape())
        bi = Signal(b_fields['BI'][0:-1].shape())
        comb += bo.eq(b_fields['BO'][0:-1])
        comb += bi.eq(b_fields['BI'][0:-1])

        # The bit of CR selected by BI
        cr_bit = Signal(reset_less=True)
        comb += cr_bit.eq((self.i.cr & (1<<(31-bi))) != 0)

        # Whether the conditional branch should be taken
        bc_taken = Signal(reset_less=True)
        with m.If(bo[2]):
            comb += bc_taken.eq((cr_bit == bo[3]) | bo[4])
        with m.Else():
            # Yes, the CTR only counts 32 bits
            ctr = Signal(64, reset_less=True)
            comb += ctr.eq(self.i.ctr - 1)
            comb += self.o.spr.data.eq(ctr)
            comb += self.o.spr.ok.eq(1)
            ctr_eq_zero = Signal(reset_less=True)
            comb += ctr_eq_zero.eq(ctr == 0)
            with m.If(bo[3:5] == 0b00):
                comb += bc_taken.eq(~cr_bit & (ctr_eq_zero == bo[1]))
            with m.Elif(bo[3:5] == 0b01):
                comb += bc_taken.eq(cr_bit & (ctr_eq_zero == bo[1]))
            with m.Elif(bo[4] == 1):
                comb += bc_taken.eq(ctr_eq_zero == bo[1])

        ### Main Switch Statement ###
        with m.Switch(op.insn_type):
            #### branch ####
            with m.Case(InternalOp.OP_B):
                li = Signal(i_fields['LI'][0:-1].shape())
                comb += li.eq(i_fields['LI'][0:-1])
                comb += br_imm_addr.eq(br_ext(li))
                comb += br_taken.eq(1)
            #### branch conditional ####
            with m.Case(InternalOp.OP_BC):
                bd = Signal(b_fields['BD'][0:-1].shape())
                comb += bd.eq(b_fields['BD'][0:-1])
                comb += br_imm_addr.eq(br_ext(bd))
                comb += br_taken.eq(bc_taken)
            #### branch conditional reg ####
            with m.Case(InternalOp.OP_BCREG):
                comb += br_imm_addr.eq(self.i.spr1) # SPR1 is set by decode unit
                comb += br_taken.eq(bc_taken)

        ###### output next instruction address #####

        comb += nia_out.data.eq(br_addr)
        comb += nia_out.ok.eq(br_taken)

        ###### link register - only activate on operations marked as "lk" #####

        with m.If(lk):
            # ctx.op.lk is the AND of the insn LK field *and* whether the
            # op is to "listen" to the link field
            comb += lr.data.eq(self.i.cia + 4)
            comb += lr.ok.eq(1)

        ###### and context #####
        comb += self.o.ctx.eq(self.i.ctx)

        return m
