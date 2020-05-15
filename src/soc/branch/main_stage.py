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


def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True))
    return res


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

        branch_addr = Signal(64, reset_less=True)
        branch_taken = Signal(reset_less=True)
        comb += branch_taken.eq(0)
        

        ##########################
        # main switch for logic ops AND, OR and XOR, cmpb, parity, and popcount

        with m.Switch(op.insn_type):
            with m.Case(InternalOp.OP_B):
                li = Signal(i_fields['LI'][0:-1].shape())
                comb += li.eq(i_fields['LI'][0:-1])
                with m.If(aa):
                    comb += branch_addr.eq(Cat(Const(0, 2), li))
                    comb += branch_taken.eq(1)
                with m.Else():
                    comb += branch_addr.eq(Cat(Const(0, 2), li) + self.i.nia)
                    comb += branch_taken.eq(1)

        comb += self.o.nia_out.data.eq(branch_addr)
        comb += self.o.nia_out.ok.eq(branch_taken)


        ###### sticky overflow and context, both pass-through #####

        comb += self.o.ctx.eq(self.i.ctx)

        return m
