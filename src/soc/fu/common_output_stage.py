# This stage is intended to handle the gating of carry out,
# and updating the condition register
from nmigen import (Module, Signal, Cat, Const)
from nmutil.pipemodbase import PipeModBase
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp


class CommonOutputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "output")

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        # ok so there are two different ways this goes:
        # (1) something involving XER ov in which case so gets modified
        #     and that means we need the modified version of so in CR0
        # (2) something that does *not* have XER ov, in which case so
        #     has been pass-through just to get it into CR0
        # in case (1) we don't *have* an xer_so output so put xer_so *input*
        # into CR0.
        xer_so_i = self.i.xer_so.data[0]
        if hasattr(self.o, "xer_so"):
            xer_so_o = self.o.xer_so.data[0]
            so = Signal(reset_less=True)
            oe = Signal(reset_less=True)
            comb += oe.eq(op.oe.oe & op.oe.ok)
            with m.If(oe):
                comb += so.eq(xer_so_o)
            with m.Else():
                comb += so.eq(xer_so_i)
        else:
            so = xer_so_i

        # op requests inversion of the output...
        o = Signal.like(self.i.o)
        if hasattr(op, "invert_out"): # ... optionally
            with m.If(op.invert_out):
                comb += o.eq(~self.i.o.data)
            with m.Else():
                comb += o.eq(self.i.o.data)
        else:
            comb += o.eq(self.i.o.data) # ... no inversion

        # target register if 32-bit is only the 32 LSBs
        # XXX ah.  right.  this needs to be done only if the *mode* is 32-bit
        # see https://bugs.libre-soc.org/show_bug.cgi?id=424
        target = Signal(64, reset_less=True)
        #with m.If(op.is_32bit):
        #    comb += target.eq(o[:32])
        #with m.Else():
        #    comb += target.eq(o)
        comb += target.eq(o)

        # carry-out only if actually present in this input spec
        # (note: MUL and DIV do not have it, but ALU and Logical do)
        if hasattr(self.i, "xer_ca"):
            # Handle carry_out
            comb += self.o.xer_ca.data.eq(self.i.xer_ca.data)
            comb += self.o.xer_ca.ok.eq(op.output_carry)

        # create condition register cr0 and sticky-overflow
        is_nzero = Signal(reset_less=True)
        is_positive = Signal(reset_less=True)
        is_negative = Signal(reset_less=True)
        msb_test = Signal(reset_less=True) # set equal to MSB, invert if OP=CMP
        is_cmp = Signal(reset_less=True)     # true if OP=CMP
        is_cmpeqb = Signal(reset_less=True)  # true if OP=CMPEQB
        cr0 = Signal(4, reset_less=True)

        # TODO: if o[63] is XORed with "operand == OP_CMP"
        # that can be used as a test of whether to invert the +ve/-ve test
        # see https://bugs.libre-soc.org/show_bug.cgi?id=305#c60

        comb += is_cmp.eq(op.insn_type == MicrOp.OP_CMP)
        comb += is_cmpeqb.eq(op.insn_type == MicrOp.OP_CMPEQB)

        comb += msb_test.eq(target[-1]) # 64-bit MSB
        comb += is_nzero.eq(target.bool())
        comb += is_negative.eq(msb_test)
        comb += is_positive.eq(is_nzero & ~msb_test)

        with m.If(is_cmpeqb | is_cmp):
            comb += cr0.eq(self.i.cr0.data)
        with m.Else():
            comb += cr0.eq(Cat(so, ~is_nzero, is_positive, is_negative))

        # copy out [inverted?] output, cr0, and context out
        comb += self.o.o.data.eq(o)
        comb += self.o.o.ok.eq(self.i.o.ok)
        # CR0 to be set
        comb += self.o.cr0.data.eq(cr0)
        comb += self.o.cr0.ok.eq(op.write_cr0)
        # context
        comb += self.o.ctx.eq(self.i.ctx)

        return m
