# This stage is intended to prepare the multiplication operands

from nmigen import (Module, Signal, Mux)
from nmutil.pipemodbase import PipeModBase
from soc.fu.div.pipe_data import DivInputData
from soc.fu.mul.pipe_data import MulIntermediateData
from ieee754.part.partsig import PartitionedSignal
from nmutil.util import eq32

class MulMainStage1(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "mul1")

    def ispec(self):
        return DivInputData(self.pspec) # defines pipeline stage input format

    def ospec(self):
        return MulIntermediateData(self.pspec) # pipeline stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        a, b, op = self.i.a, self.i.b, self.i.ctx.op
        a_o, b_o, neg_res_o = self.o.a, self.o.b, self.o.neg_res
        neg_res_o, neg_res32_o = self.o.neg_res, self.o.neg_res32

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        sign_a = Signal(reset_less=True)
        sign_b = Signal(reset_less=True)
        sign32_a = Signal(reset_less=True)
        sign32_b = Signal(reset_less=True)
        comb += is_32bit.eq(op.is_32bit)

        # work out if a/b are negative (check 32-bit / signed)
        comb += sign_a.eq(Mux(op.is_32bit, a[31], a[63]) & op.is_signed)
        comb += sign_b.eq(Mux(op.is_32bit, b[31], b[63]) & op.is_signed)
        comb += sign32_a.eq(a[31] & op.is_signed)
        comb += sign32_b.eq(b[31] & op.is_signed)

        # work out if result is negative sign
        comb += neg_res_o.eq(sign_a ^ sign_b)
        comb += neg_res32_o.eq(sign32_a ^ sign32_b) # pass through for OV32

        # negation of a 64-bit value produces the same lower 32-bit
        # result as negation of just the lower 32-bits, so we don't
        # need to do anything special before negating
        abs_a = Signal(64, reset_less=True)
        abs_b = Signal(64, reset_less=True)
        comb += abs_a.eq(Mux(sign_a, -a, a))
        comb += abs_b.eq(Mux(sign_b, -b, b))

        # set up 32/64 bit inputs
        comb += eq32(is_32bit, a_o, abs_a)
        comb += eq32(is_32bit, b_o, abs_b)

        ###### XER and context, both pass-through #####

        comb += self.o.xer_so.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m

