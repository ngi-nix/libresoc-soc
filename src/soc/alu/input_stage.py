# This stage is intended to adjust the input data before sending it to
# the acutal ALU. Things like handling inverting the input, carry_in
# generation for subtraction, and handling of immediates should happen
# here
from nmigen import (Module, Signal, Cat, Const, Mux, Repl, signed,
                    unsigned)
from nmutil.pipemodbase import PipeModBase
from soc.alu.pipe_data import ALUInputData
from soc.decoder.power_enums import CryIn


class ALUInputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ALUInputData(self.pspec) # XXX TODO, change to ALUFirstInputData

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

        # TODO: remove this because it's handled by the Computational Unit?

        # If there's an immediate, set the B operand to that
        with m.If(self.i.ctx.op.imm_data.imm_ok):
            comb += self.o.b.eq(self.i.ctx.op.imm_data.imm)
        with m.Else():
            comb += self.o.b.eq(self.i.b)

        with m.Switch(self.i.ctx.op.input_carry):
            with m.Case(CryIn.ZERO):
                comb += self.o.carry_in.eq(0)
            with m.Case(CryIn.ONE):
                comb += self.o.carry_in.eq(1)
            with m.Case(CryIn.CA):
                comb += self.o.carry_in.eq(self.i.carry_in)

        comb += self.o.ctx.eq(self.i.ctx)

        return m
