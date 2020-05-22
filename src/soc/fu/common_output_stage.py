# This stage is intended to handle the gating of carry out,
# and updating the condition register
from nmigen import (Module, Signal, Cat, Repl)
from nmutil.pipemodbase import PipeModBase
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class CommonOutputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "output")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op

        # op requests inversion of the output
        o = Signal.like(self.i.o)
        with m.If(op.invert_out):
            comb += o.eq(~self.i.o)
        with m.Else():
            comb += o.eq(self.i.o)

        # target register if 32-bit is only the 32 LSBs
        target = Signal(64, reset_less=True)
        with m.If(op.is_32bit):
            comb += target.eq(o[:32])
        with m.Else():
            comb += target.eq(o)

        # Handle carry_out
        comb += self.o.xer_ca.data.eq(self.i.xer_ca.data)
        comb += self.o.xer_ca.ok.eq(op.output_carry)

        # create condition register cr0 and sticky-overflow
        is_zero = Signal(reset_less=True)
        is_positive = Signal(reset_less=True)
        is_negative = Signal(reset_less=True)
        msb_test = Signal(reset_less=True) # set equal to MSB, invert if OP=CMP
        is_cmp = Signal(reset_less=True)   # true if OP=CMP
        self.so = Signal(1, reset_less=True)
        cr0 = Signal(4, reset_less=True)

        # TODO: if o[63] is XORed with "operand == OP_CMP"
        # that can be used as a test
        # see https://bugs.libre-soc.org/show_bug.cgi?id=305#c60

        comb += is_cmp.eq(op.insn_type == InternalOp.OP_CMP)
        comb += msb_test.eq(target[-1] ^ is_cmp)
        comb += is_zero.eq(target == 0)
        comb += is_positive.eq(~is_zero & ~msb_test)
        comb += is_negative.eq(~is_zero & msb_test)

        with m.If(op.insn_type != InternalOp.OP_CMPEQB):
            comb += cr0.eq(Cat(self.so, is_zero, is_positive, is_negative))
        with m.Else():
            comb += cr0.eq(self.i.cr0)

        # copy out [inverted] cr0, output, and context out
        comb += self.o.o.eq(o)
        comb += self.o.cr0.data.eq(cr0)
        comb += self.o.cr0.ok.eq(op.rc.rc & op.rc.rc_ok) # CR0 to be set
        comb += self.o.ctx.eq(self.i.ctx)

        return m
