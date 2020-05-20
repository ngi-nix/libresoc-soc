# This stage is intended to do most of the work of executing the Arithmetic
# instructions. This would be like the additions, compares, and sign-extension
# as well as carry and overflow generation. This module
# however should not gate the carry or overflow, that's up to the
# output stage
from nmigen import (Module, Signal, Cat, Repl, Mux, Const)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts
from soc.fu.alu.pipe_data import ALUInputData, ALUOutputData
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
        carry_out, o, cr0 = self.o.xer_co, self.o.o, self.o.cr0
        a, b, op = self.i.a, self.i.b, self.i.ctx.op

        # check if op is 32-bit, and get sign bit from operand a
        is_32bit = Signal(reset_less=True)
        sign_bit = Signal(reset_less=True)
        comb += is_32bit.eq(op.is_32bit)
        comb += sign_bit.eq(Mux(is_32bit, a[31], a[63]))

        # little trick: do the add using only one add (not 2)
        add_a = Signal(a.width + 2, reset_less=True)
        add_b = Signal(a.width + 2, reset_less=True)
        add_output = Signal(a.width + 2, reset_less=True)
        with m.If((op.insn_type == InternalOp.OP_ADD) |
                  (op.insn_type == InternalOp.OP_CMP)):
            # in bit 0, 1+carry_in creates carry into bit 1 and above
            comb += add_a.eq(Cat(self.i.carry_in, a, Const(0, 1)))
            comb += add_b.eq(Cat(Const(1, 1), b, Const(0, 1)))
            comb += add_output.eq(add_a + add_b)

        ##########################
        # main switch-statement for handling arithmetic operations

        with m.Switch(op.insn_type):
            #### CMP, CMPL ####
            with m.Case(InternalOp.OP_CMP):
                # this is supposed to be inverted (b-a, not a-b)
                # however we have a trick: instead of adding either 2x 64-bit
                # MUXes to invert a and b, or messing with a 64-bit output,
                # swap +ve and -ve test in the *output* stage using an XOR gate
                comb += o.eq(add_output[1:-1])

            #### add ####
            with m.Case(InternalOp.OP_ADD):
                # bit 0 is not part of the result, top bit is the carry-out
                comb += o.eq(add_output[1:-1])
                comb += carry_out.data[0].eq(add_output[-1]) # XER.CO

                # XXX no!  wrongggg, see microwatt OP_ADD code
                # https://bugs.libre-soc.org/show_bug.cgi?id=319#c5
                comb += carry_out.data[1].eq(add_output[-1]) # XER.CO32

            #### exts (sign-extend) ####
            with m.Case(InternalOp.OP_EXTS):
                with m.If(op.data_len == 1):
                    comb += o.eq(exts(a, 8, 64))
                with m.If(op.data_len == 2):
                    comb += o.eq(exts(a, 16, 64))
                with m.If(op.data_len == 4):
                    comb += o.eq(exts(a, 32, 64))

            #### cmpeqb ####
            with m.Case(InternalOp.OP_CMPEQB):
                eqs = Signal(8, reset_less=True)
                src1 = Signal(8, reset_less=True)
                comb += src1.eq(a[0:8])
                for i in range(8):
                    comb += eqs[i].eq(src1 == b[8*i:8*(i+1)])
                comb += cr0.data.eq(Cat(Const(0, 2), eqs.any(), Const(0, 1)))

        ###### sticky overflow and context, both pass-through #####

        comb += self.o.xer_so.data.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
