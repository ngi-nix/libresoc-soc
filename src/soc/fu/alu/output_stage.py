# This stage is intended to handle the gating of carry and overflow
# out, summary overflow generation, and updating the condition
# register
from nmigen import (Module, Signal, Cat, Repl)
from soc.fu.alu.pipe_data import ALUInputData, ALUOutputData
from soc.fu.common_output_stage import CommonOutputStage
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class ALUOutputStage(CommonOutputStage):

    def ispec(self):
        return ALUOutputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        op = self.i.ctx.op
        xer_so_i, xer_ov_i = self.i.xer_so.data, self.i.xer_ov.data

        # XXX see https://bugs.libre-soc.org/show_bug.cgi?id=319#c5
        comb += self.so.eq(xer_so_i[0] | xer_ov_i[0]) # SO

        # copy overflow and sticky-overflow.  indicate to CompALU if they
        # are actually required (oe enabled/set) otherwise the CompALU
        # can (will) ignore them.
        comb += self.o.xer_so.data.eq(self.so)
        comb += self.o.xer_so.ok.eq(op.oe.oe & op.oe.oe_ok)
        comb += self.o.xer_ov.data.eq(xer_ov_i)
        comb += self.o.xer_ov.ok.eq(op.oe.oe & op.oe.oe_ok) # OV/32 is to be set

        return m
