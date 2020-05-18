# This stage is intended to adjust the input data before sending it to
# the acutal ALU. Things like handling inverting the input, carry_in
# generation for subtraction, and handling of immediates should happen
# here
from nmigen import (Module, Signal, Cat, Const, Mux, Repl, signed,
                    unsigned)
from nmutil.pipemodbase import PipeModBase
from soc.decoder.power_enums import InternalOp
from soc.shift_rot.pipe_data import ShiftRotInputData
from soc.decoder.power_enums import CryIn


class ShiftRotInputStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ShiftRotInputData(self.pspec)

    def ospec(self):
        return ShiftRotInputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        ##### operand A #####

        # operand a to be as-is or inverted
        a = Signal.like(self.i.ra)

        with m.If(self.i.ctx.op.invert_a):
            comb += a.eq(~self.i.ra)
        with m.Else():
            comb += a.eq(self.i.ra)

        comb += self.o.ra.eq(a)
        comb += self.o.rb.eq(self.i.rb)
        comb += self.o.rs.eq(self.i.rs)


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
