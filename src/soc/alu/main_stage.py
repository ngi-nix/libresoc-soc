# This stage is intended to do most of the work of executing the Arithmetic
# instructions. This would be like the additions, compares, and sign-extension
# as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData, ALUOutputData
from ieee754.part.partsig import PartitionedSignal
from soc.decoder.power_enums import InternalOp


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
        carry_out, o = self.o.carry_out, self.o.o

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        sign_bit = Signal(reset_less=True)
        comb += is_32bit.eq(self.i.ctx.op.is_32bit)
        comb += sign_bit.eq(Mux(is_32bit, self.i.a[31], self.i.a[63]))



        # little trick: do the add using only one add (not 2)
        add_a = Signal(self.i.a.width + 2, reset_less=True)
        add_b = Signal(self.i.a.width + 2, reset_less=True)
        add_output = Signal(self.i.a.width + 2, reset_less=True)
        with m.If((self.i.ctx.op.insn_type == InternalOp.OP_ADD) |
                  (self.i.ctx.op.insn_type == InternalOp.OP_CMP)):
            # in bit 0, 1+carry_in creates carry into bit 1 and above
            comb += add_a.eq(Cat(self.i.carry_in, self.i.a, Const(0, 1)))
            comb += add_b.eq(Cat(Const(1, 1), self.i.b, Const(0, 1)))
            comb += add_output.eq(add_a + add_b)

        ##########################
        # main switch-statement for handling arithmetic operations

        with m.Switch(self.i.ctx.op.insn_type):
            #### CMP, CMPL ####
            with m.Case(InternalOp.OP_CMP):
                comb += o.eq(add_output[1:-1])

            #### add ####
            with m.Case(InternalOp.OP_ADD):
                # bit 0 is not part of the result, top bit is the carry-out
                comb += o.eq(add_output[1:-1])
                comb += carry_out.eq(add_output[-1])

            #### exts (sign-extend) ####
            with m.Case(InternalOp.OP_EXTS):
                with m.If(self.i.ctx.op.data_len == 1):
                    comb += o.eq(Cat(self.i.a[0:8], Repl(self.i.a[7], 64-8)))
                with m.If(self.i.ctx.op.data_len == 2):
                    comb += o.eq(Cat(self.i.a[0:16], Repl(self.i.a[15], 64-16)))
                with m.If(self.i.ctx.op.data_len == 4):
                    comb += o.eq(Cat(self.i.a[0:32], Repl(self.i.a[31], 64-32)))

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
