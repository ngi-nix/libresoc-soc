# This stage is intended to do most of the work of executing Logical
# instructions. This is OR, AND, XOR, POPCNT, PRTY, CMPB, BPERMD, CNTLZ
# however input and output stages also perform bit-negation on input(s)
# and output, as well as carry and overflow generation.
# This module however should not gate the carry or overflow, that's up
# to the output stage

from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from soc.logical.pipe_data import ALUInputData
from soc.alu.pipe_data import ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class LogicalMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        ##########################
        # main switch for logic ops AND, OR and XOR, parity, and popcount

        with m.Switch(self.i.ctx.op.insn_type):
            with m.Case(InternalOp.OP_AND):
                comb += self.o.o.eq(self.i.a & self.i.b)
            with m.Case(InternalOp.OP_OR):
                comb += self.o.o.eq(self.i.a | self.i.b)
            with m.Case(InternalOp.OP_XOR):
                comb += self.o.o.eq(self.i.a ^ self.i.b)
            ###### cmpb #######
            with m.Case(InternalOp.OP_CMPB):
                for i in range(8):
                    slc = slice(i*8, (i+1)*8)
                    with m.If(self.i.a[slc] == self.i.b[slc]):
                        comb += self.o.o[slc].eq(Repl(1, 8))
                    with m.Else():
                        comb += self.o.o[slc].eq(Repl(0, 8))

            ###### popcount #######
            # TODO with m.Case(InternalOp.OP_POPCNT):
            ###### parity #######
            # TODO with m.Case(InternalOp.OP_PRTY):
            ###### cntlz #######
            # TODO with m.Case(InternalOp.OP_CNTZ):
            ###### bpermd #######
            # TODO with m.Case(InternalOp.OP_BPERM): - not in microwatt

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
