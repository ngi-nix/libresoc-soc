# This stage is intended to adjust the input data before sending it to
# the acutal ALU. Things like handling inverting the input, carry_in
# generation for subtraction, and handling of immediates should happen
# here
from soc.fu.common_input_stage import CommonInputStage
from soc.fu.shift_rot.pipe_data import ShiftRotInputData


class ShiftRotInputStage(CommonInputStage):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ShiftRotInputData(self.pspec)

    def ospec(self):
        return ShiftRotInputData(self.pspec)

    def elaborate(self, platform):
        m = super().elaborate(platform) # handles A, carry and sticky overflow
        comb = m.d.comb

        # operand rs
        comb += self.o.rs.eq(self.i.rs)

        return m
