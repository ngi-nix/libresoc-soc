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

        i_fields = self.fields.instrs['I']
        lk = Signal(i_fields['LK'][0:-1].shape())
        comb += lk.eq(i_fields['LK'][0:-1])
        aa = Signal(i_fields['AA'][0:-1].shape())
        comb += aa.eq(i_fields['AA'][0:-1])

        br_imm_addr = Signal(64, reset_less=True)
        br_addr = Signal(64, reset_less=True)
        br_taken = Signal(reset_less=True)
        comb += br_taken.eq(0)

        # Handle absolute or relative branches
        with m.If(aa):
            comb += br_addr.eq(br_imm_addr)
        with m.Else():
            comb += br_addr.eq(br_imm_addr + self.i.cia)


        # handle conditional branches (BO and BI are same for BC and
        # BCREG)
        b_fields = self.fields.instrs['B']
        bo = Signal(b_fields['BO'][0:-1].shape())
        comb += bo.eq(b_fields['BO'][0:-1])
        bi = Signal(b_fields['BI'][0:-1].shape())
        comb += bi.eq(b_fields['BI'][0:-1])

        # The bit of CR selected by BI
        cr_bit = Signal(reset_less=True)
        comb += cr_bit.eq((self.i.cr & (1<<(31-bi))) != 0)

        # Whether the conditional branch should be taken
        bc_taken = Signal(reset_less=True)
        comb += bc_taken.eq(0)
        with m.If(bo[2]):
            comb += bc_taken.eq((cr_bit == bo[3]) | bo[4])

        ######## main switch statement ########

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_B):
                li = Signal(i_fields['LI'][0:-1].shape())
                comb += li.eq(i_fields['LI'][0:-1])
                li_sgn = li[-1]
                comb += br_imm_addr.eq(
                    Cat(Const(0, 2), li,
                        Repl(li_sgn, 64-(li.width + 2))))
                comb += br_taken.eq(1)
            with m.Case(InternalOp.OP_BC):
                bd = Signal(b_fields['BD'][0:-1].shape())
                comb += bd.eq(b_fields['BD'][0:-1])
                bd_sgn = bd[-1]

                comb += branch_imm_addr.eq(
                    Cat(Const(0, 2), bd,
                        Repl(bd_sgn, 64-(bd.width + 2))))
                comb += branch_taken.eq(bc_taken)


        comb += self.o.nia_out.data.eq(br_addr)
        comb += self.o.nia_out.ok.eq(br_taken)

        with m.If(lk):
            comb += self.o.lr.data.eq(self.i.cia + 4)

        ###### link register and context #####

        comb += self.o.ctx.eq(self.i.ctx)
        comb += self.o.lr.ok.eq(lk)

        return m
