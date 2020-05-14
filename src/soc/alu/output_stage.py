# This stage is intended to handle the gating of carry and overflow
# out, summary overflow generation, and updating the condition
# register
from nmigen import (Module, Signal, Cat, Repl)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class ALUOutputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "output")

    def ispec(self):
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def ospec(self):
        return ALUOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # op requests inversion of the output
        o = Signal.like(self.i.o)
        with m.If(self.i.ctx.op.invert_out):
            comb += o.eq(~self.i.o)
        with m.Else():
            comb += o.eq(self.i.o)

        # create condition register cr0 and sticky-overflow
        is_zero = Signal(reset_less=True)
        is_positive = Signal(reset_less=True)
        is_negative = Signal(reset_less=True)
        msb_test = Signal(reset_less=True) # set equal to MSB, invert if OP=CMP
        so = Signal(reset_less=True)

        # TODO: if o[63] is XORed with "operand == OP_CMP"
        # that can be used as a test
        # see https://bugs.libre-soc.org/show_bug.cgi?id=305#c60
        comb += is_zero.eq(o == 0)
        comb += is_positive.eq(~is_zero & ~o[63])
        comb += is_negative.eq(~is_zero & o[63])
        comb += so.eq(self.i.so | self.i.ov)

        comb += self.o.o.eq(o)
        comb += self.o.cr0.eq(Cat(so, is_zero, is_positive, is_negative))
        comb += self.o.so.eq(so)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
