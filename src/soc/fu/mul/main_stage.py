# This stage is intended to do the main work of an actual multiply

from nmigen import Module
from nmutil.pipemodbase import PipeModBase
from soc.fu.mul.pipe_data import MulIntermediateData, MulOutputData
from ieee754.part.partsig import PartitionedSignal


class MulMainStage2(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "mul2")

    def ispec(self):
        return MulIntermediateData(self.pspec) # pipeline stage input format

    def ospec(self):
        return MulOutputData(self.pspec) # pipeline stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        a, b, o = self.i.a, self.i.b, self.o.o

        # actual multiply (TODO: split into stages)
        # it's ironic that one line of code can create 15,000 gates...
        comb += o.eq(a * b)

        ###### xer and context, all pass-through #####

        comb += self.o.neg_res.eq(self.i.neg_res)
        comb += self.o.neg_res32.eq(self.i.neg_res32)
        comb += self.o.xer_so.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m

