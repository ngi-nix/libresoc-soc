# This stage is intended to do most of the work of executing the ALU
# instructions. This would be like the additions, logical operations,
# and shifting, as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal, Cat, Repl, Mux)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp
from soc.alu.maskgen import MaskGen
from soc.alu.rotl import ROTL


class ALUMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUOutputData(self.pspec) # TODO: ALUIntermediateData

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        is_32bit = Signal(reset_less=True)
        comb += is_32bit.eq(self.i.ctx.op.is_32bit)

        add_output = Signal(self.i.a.width + 1, reset_less=True)
        comb += add_output.eq(self.i.a + self.i.b + self.i.carry_in)

        # Signals for rotates and shifts
        rotl_out = Signal.like(self.i.a)
        mask = Signal.like(self.i.a)
        m.submodules.maskgen = maskgen = MaskGen(64)
        m.submodules.rotl = rotl = ROTL(64)
        m.submodules.rotl32 = rotl32 = ROTL(32)
        rotate_amt = Signal.like(rotl.b)

        comb += [
            rotl.a.eq(self.i.a),
            rotl.b.eq(rotate_amt),
            rotl32.a.eq(self.i.a[0:32]),
            rotl32.b.eq(rotate_amt)]

        with m.If(is_32bit):
            comb += rotl_out.eq(Cat(rotl32.o, Repl(0, 32)))
        with m.Else():
            comb += rotl_out.eq(rotl.o)
            


        with m.Switch(self.i.ctx.op.insn_type):
            with m.Case(InternalOp.OP_ADD):
                comb += self.o.o.eq(add_output[0:64])
                comb += self.o.carry_out.eq(add_output[64])
            with m.Case(InternalOp.OP_AND):
                comb += self.o.o.eq(self.i.a & self.i.b)
            with m.Case(InternalOp.OP_OR):
                comb += self.o.o.eq(self.i.a | self.i.b)
            with m.Case(InternalOp.OP_XOR):
                comb += self.o.o.eq(self.i.a ^ self.i.b)
            with m.Case(InternalOp.OP_SHL):
                comb += maskgen.mb.eq(Mux(is_32bit, 32, 0))
                comb += maskgen.me.eq(63-self.i.b[0:6])
                comb += rotate_amt.eq(self.i.b[0:6])
                with m.If(is_32bit):
                    with m.If(self.i.b[5]):
                        comb += mask.eq(0)
                    with m.Else():
                        comb += mask.eq(maskgen.o)
                with m.Else():
                    with m.If(self.i.b[6]):
                        comb += mask.eq(0)
                    with m.Else():
                        comb += mask.eq(maskgen.o)
                comb += self.o.o.eq(rotl_out & mask)
            with m.Case(InternalOp.OP_SHR):
                comb += maskgen.mb.eq(Mux(is_32bit, 32, 0) + self.i.b[0:6])
                comb += maskgen.me.eq(63)
                comb += rotate_amt.eq(64-self.i.b[0:6])
                with m.If(is_32bit):
                    with m.If(self.i.b[5]):
                        comb += mask.eq(0)
                    with m.Else():
                        comb += mask.eq(maskgen.o)
                with m.Else():
                    with m.If(self.i.b[6]):
                        comb += mask.eq(0)
                    with m.Else():
                        comb += mask.eq(maskgen.o)
                comb += self.o.o.eq(rotl_out & mask)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
