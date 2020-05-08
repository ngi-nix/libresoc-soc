# This stage is intended to adjust the input data before sending it to
# the acutal ALU. Things like handling inverting the input, carry_in
# generation for subtraction, and handling of immediates should happen
# here
from nmigen import (Module, Signal, Cat, Const, Mux, Repl, signed,
                    unsigned)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData


class ALUInputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUInputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb


        a = Signal.like(self.i.a)

        with m.If(self.i.ctx.op.invert_a):
            comb += a.eq(~self.i.a)
        with m.Else():
            comb += a.eq(self.i.a)

        comb += self.o.a.eq(a)

        # If there's an immediate, set the B operand to that
        with m.If(self.i.ctx.op.imm_data.imm_ok):
            comb += self.o.b.eq(self.i.ctx.op.imm_data.imm)
        with m.Else():
            comb += self.o.b.eq(self.i.b)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
