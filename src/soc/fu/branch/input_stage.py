# This stage is intended to adjust the input data before sending it to
# the acutal ALU. Things like handling inverting the input, carry_in
# generation for subtraction, and handling of immediates should happen
# here
from nmigen import (Module, Signal, Cat, Const, Mux, Repl, signed,
                    unsigned)
from nmutil.pipemodbase import PipeModBase
from soc.decoder.power_enums import InternalOp
from soc.fu.alu.pipe_data import ALUInputData
from soc.decoder.power_enums import CryIn


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

        ##### operand A #####

        # operand a to be as-is or inverted
        a = Signal.like(self.i.a)

        with m.If(self.i.ctx.op.invert_a):
            comb += a.eq(~self.i.a)
        with m.Else():
            comb += a.eq(self.i.a)

        comb += self.o.a.eq(a)

        ##### operand B #####

        # TODO: see https://bugs.libre-soc.org/show_bug.cgi?id=305#c43
        # remove this, just do self.o.b.eq(self.i.b) and move the
        # immediate-detection into set_alu_inputs in the unit test
        # If there's an immediate, set the B operand to that
        comb += self.o.b.eq(self.i.b)

        ##### carry-in #####

        # either copy incoming carry or set to 1/0 as defined by op
        with m.Switch(self.i.ctx.op.input_carry):
            with m.Case(CryIn.ZERO):
                comb += self.o.carry_in.eq(0)
            with m.Case(CryIn.ONE):
                comb += self.o.carry_in.eq(1)
            with m.Case(CryIn.CA):
                comb += self.o.carry_in.eq(self.i.carry_in)

        ##### sticky overflow and context (both pass-through) #####

        comb += self.o.so.eq(self.i.so)
        comb += self.o.ctx.eq(self.i.ctx)

        return m
