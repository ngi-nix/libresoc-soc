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

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        sign_bit = Signal(reset_less=True)
        comb += is_32bit.eq(self.i.ctx.op.is_32bit)
        comb += sign_bit.eq(Mux(is_32bit, self.i.a[31], self.i.a[63]))

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

        ##########################
        # main switch-statement for handling arithmetic and logic operations

        with m.Switch(self.i.ctx.op.insn_type):
            #### add ####
            with m.Case(InternalOp.OP_ADD):
                # little trick: do the add using only one add (not 2)
                add_a = Signal(self.i.a.width + 2, reset_less=True)
                add_b = Signal(self.i.a.width + 2, reset_less=True)
                add_output = Signal(self.i.a.width + 2, reset_less=True)
                # in bit 0, 1+carry_in creates carry into bit 1 and above
                comb += add_a.eq(Cat(self.i.carry_in, a, Const(0, 1)))
                comb += add_b.eq(Cat(Const(1, 1), b, Const(0, 1)))
                comb += add_output.eq(a + b)
                # bit 0 is not part of the result, top bit is the carry-out
                comb += self.o.o.eq(add_output[1:-1])
                comb += self.o.carry_out.eq(add_output[-1])

            #### and ####
            with m.Case(InternalOp.OP_AND):
                comb += self.o.o.eq(self.i.a & self.i.b)

            #### or ####
            with m.Case(InternalOp.OP_OR):
                comb += self.o.o.eq(self.i.a | self.i.b)

            #### xor ####
            with m.Case(InternalOp.OP_XOR):
                comb += self.o.o.eq(self.i.a ^ self.i.b)

            #### shift left ####
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

            #### shift right ####
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
                with m.If(self.i.ctx.op.is_signed):
                    out = rotl_out & mask | Mux(sign_bit, ~mask, 0))
                    cout = sign_bit & ((rotl_out & mask) != 0))
                    comb += self.o.o.eq(out)
                    comb += self.o.carry_out.eq(cout)
                with m.Else():
                    comb += self.o.o.eq(rotl_out & mask)

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
