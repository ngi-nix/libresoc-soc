# This stage is intended to do most of the work of analysing the multiply result
"""
bugreports/links:
* https://libre-soc.org/openpower/isa/fixedarith/
* https://bugs.libre-soc.org/show_bug.cgi?id=432
* https://bugs.libre-soc.org/show_bug.cgi?id=323
"""

from nmigen import (Module, Signal, Cat, Repl, Mux, signed)
from nmutil.pipemodbase import PipeModBase
from soc.fu.div.pipe_data import DivMulOutputData
from soc.fu.mul.pipe_data import MulOutputData
from ieee754.part.partsig import PartitionedSignal
from openpower.decoder.power_enums import MicrOp


class MulMainStage3(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "mul3")

    def ispec(self):
        return MulOutputData(self.pspec) # pipeline stage output format

    def ospec(self):
        return DivMulOutputData(self.pspec) # defines stage output format

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # convenience variables
        o, cr0 = self.o.o, self.o.cr0
        ov_o, o_i, op = self.o.xer_ov, self.i.o, self.i.ctx.op

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        comb += is_32bit.eq(op.is_32bit)

        # check negate: select signed/unsigned
        mul_o = Signal(o_i.width, reset_less=True)
        comb += mul_o.eq(Mux(self.i.neg_res, -o_i, o_i))

        # OP_MUL_nnn - select hi32/hi64/lo64 from result
        with m.Switch(op.insn_type):
            # hi-32 replicated twice
            with m.Case(MicrOp.OP_MUL_H32):
                comb += o.data.eq(Repl(mul_o[32:64], 2))
                comb += o.ok.eq(1)
            # hi-64 
            with m.Case(MicrOp.OP_MUL_H64):
                comb += o.data.eq(mul_o[64:128])
                comb += o.ok.eq(1)
            # lo-64 - overflow
            with m.Case(MicrOp.OP_MUL_L64):
                # take the low 64 bits of the mul
                comb += o.data.eq(mul_o[0:64])
                comb += o.ok.eq(1)

                # compute overflow 32/64
                mul_ov = Signal(reset_less=True)
                with m.If(is_32bit):
                    # here we're checking that the top 32 bits is the
                    # sign-extended version of the bottom 32 bits.
                    m31 = mul_o[31:64] # yes really bits 31 to 63 (incl)
                    comb += mul_ov.eq(m31.bool() & ~m31.all())
                with m.Else():
                    # here we're checking that the top 64 bits is the
                    # sign-extended version of the bottom 64 bits.
                    m63 = mul_o[63:128] # yes really bits 63 to 127 (incl)
                    comb += mul_ov.eq(m63.bool() & ~m63.all())

                # 32-bit (ov[1]) and 64-bit (ov[0]) overflow - both same
                comb += ov_o.data.eq(Repl(mul_ov, 2)) # sets OV _and_ OV32
                comb += ov_o.ok.eq(1)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.eq(self.i.xer_so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m

