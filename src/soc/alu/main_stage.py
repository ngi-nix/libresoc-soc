# This stage is intended to do most of the work of executing the ALU
# instructions. This would be like the additions, logical operations,
# and shifting, as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class ALUMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        add_output = Signal(self.i.a.width + 1, reset_less=True)
        comb += add_output.eq(self.i.a + self.i.b + self.i.carry_in)


        with m.Switch(self.i.ctx.op.insn_type):
            with m.Case(InternalOp.OP_ADD):
                comb += self.o.o.eq(add_output[0:64])
                comb += self.o.carry_out.eq(add_output[64])
            with m.Case(InternalOp.OP_AND):
                comb += self.o.o.eq(self.i.a & self.i.b)
            with m.Case(InternalOp.OP_OR):
                comb += self.o.o.eq(self.i.a | self.i.b)
            with m.Case(InternalOp.OP_XOR):
                comb += self.o.o.eq(self.i.a ^ self.i.b)
            with m.Case(InternalOp.OP_SHL):
                comb += self.o.o.eq(self.i.a << self.i.b)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
