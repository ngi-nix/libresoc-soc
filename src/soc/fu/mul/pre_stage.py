# This stage is intended to do most of the work of executing multiply
from nmigen import (Module, Signal, Mux)
from nmutil.pipemodbase import PipeModBase
from soc.fu.alu.pipe_data import ALUInputData
from soc.fu.mul.pipe_data import MulIntermediateData
from ieee754.part.partsig import PartitionedSignal


class MulMainStage1(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "mul1")

    def ispec(self):
        return ALUInputData(self.pspec) # defines pipeline stage input format

    def ospec(self):
        return MulIntermediateData(self.pspec) # pipeline stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        a, b = self.i.a, self.i.b
        a_o, b_o, neg_res_o = self.o.a, self.o.b, self.o.neg_res

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        sign_a = Signal(reset_less=True)
        sign_b = Signal(reset_less=True)
        comb += is_32bit.eq(op.is_32bit)

        # work out if a/b are negative (check 32-bit / signed)
        comb += sign_a.eq(Mux(op.is_32bit, a[31], a[63]) & op.is_signed)
        comb += sign_b.eq(Mux(op.is_32bit, b[31], b[63]) & op.is_signed)

        # work out if result is negative sign
        comb += neg_res_o.eq(sign_a ^ sign_b)

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        comb += a_o.eq(Mux(sign_a, -a, a))
        comb += b_o.eq(Mux(sign_b, -b, b))

        ###### XER and context, both pass-through #####

        comb += self.o.xer_ca.data.eq(self.i.xer_ca)
        comb += self.o.xer_so.data.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m

