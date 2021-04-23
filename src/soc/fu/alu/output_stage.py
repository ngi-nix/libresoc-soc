# This stage is intended to handle the gating of carry and overflow
# out, summary overflow generation, and updating the condition
# register
from nmigen import (Module, Signal, Cat, Repl)
from soc.fu.alu.pipe_data import ALUInputData, ALUOutputData
from soc.fu.common_output_stage import CommonOutputStage
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp


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
        xer_so_o, xer_ov_o = self.o.xer_so, self.o.xer_ov

        # copy overflow and sticky-overflow.  indicate to CompALU if they
        # are actually required (oe enabled/set) otherwise the CompALU
        # can (will) ignore them.
        oe = Signal(reset_less=True)
        comb += oe.eq(op.oe.oe & op.oe.ok)
        with m.If(oe):
            # XXX see https://bugs.libre-soc.org/show_bug.cgi?id=319#c5
            comb += xer_so_o.data.eq(xer_so_i[0] | xer_ov_i[0]) # SO
            comb += xer_so_o.ok.eq(1)
            comb += xer_ov_o.data.eq(xer_ov_i)
            comb += xer_ov_o.ok.eq(1) # OV/32 is to be set

        return m
