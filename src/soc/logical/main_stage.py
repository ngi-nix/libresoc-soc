# This stage is intended to do most of the work of executing the ALU
# instructions. This would be like the additions, logical operations,
# and shifting, as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
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
        # main switch-statement for handling arithmetic and logic operations

        with m.Switch(self.i.ctx.op.insn_type):
            #### and ####
            with m.Case(InternalOp.OP_AND):
                comb += self.o.o.eq(self.i.a & self.i.b)

            #### or ####
            with m.Case(InternalOp.OP_OR):
                comb += self.o.o.eq(self.i.a | self.i.b)

            #### xor ####
            with m.Case(InternalOp.OP_XOR):
                comb += self.o.o.eq(self.i.a ^ self.i.b)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
