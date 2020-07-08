# This stage is intended to do most of the work of analysing the multiply result

from nmigen import (Module, Signal, Cat, Repl, Mux, signed)
from nmutil.pipemodbase import PipeModBase
from soc.fu.alu.pipe_data import ALUOutputData
from soc.fu.mul.pipe_data import MulOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


class MulMainStage3(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "mul3")

    def ispec(self):
        return MulOutputData(self.pspec) # pipeline stage output format

    def ospec(self):
        return ALUOutputData(self.pspec) # defines pipeline stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        cry_o, o, cr0 = self.o.xer_ca, self.o.o, self.o.cr0
        ov_o = self.o.xer_ov
        o_i, cry_i, op = self.i.o, self.i.xer_ca, self.i.ctx.op

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        comb += is_32bit.eq(op.is_32bit)

        # check negate: select signed/unsigned
        mul_o = Signal(o_i.width, reset_less=True)
        comb += mul_o.eq(Mux(self.i.neg_res, -o_i, o_i))
        comb += o.ok.eq(1)

        # OP_MUL_nnn - select hi32/hi64/lo64 from result
        with m.Switch(op.insn_type):
            # hi-32 replicated twice
            with m.Case(InternalOp.OP_MUL_H32):
                comb += o.data.eq(Repl(mul_o[32:64], 2))
            # hi-64 
            with m.Case(InternalOp.OP_MUL_H64):
                comb += o.data.eq(mul_o[64:128])
            # lo-64 - overflow
            with m.Default():
                comb += o.data.eq(mul_o[0:64])

                # compute overflow
                mul_ov = Signal(reset_less=True)
                with m.If(is_32bit):
                    m32 = mul_o[32:64]
                    comb += mul_ov.eq(m32.bool() & ~m32.all())
                with m.Else():
                    m64 = mul_o[64:128]
                    comb += mul_ov.eq(m64.bool() & ~m64.all())

                # 32-bit (ov[1]) and 64-bit (ov[0]) overflow
                ov = Signal(2, reset_less=True)
                comb += ov[0].eq(mul_ov)
                comb += ov[1].eq(mul_ov)
                comb += ov_o.data.eq(ov)
                comb += ov_o.ok.eq(1)

        # https://bugs.libre-soc.org/show_bug.cgi?id=319#c5
        ca = Signal(2, reset_less=True)
        comb += ca[0].eq(mul_o[-1])                      # XER.CA - XXX more?
        comb += ca[1].eq(mul_o[32] ^ (self.i.neg_res32)) # XER.CA32
        comb += cry_o.data.eq(ca)
        comb += cry_o.ok.eq(1)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m

