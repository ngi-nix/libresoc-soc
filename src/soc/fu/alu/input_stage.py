# This stage is intended to adjust the input data before sending it to
# the actual ALU. Things like handling inverting the input, xer_ca
# generation for subtraction, and handling of immediates should happen
# in the base class (CommonInputStage.elaborate).
from soc.fu.common_input_stage import CommonInputStage
from soc.fu.alu.pipe_data import ALUInputData


class ALUInputStage(CommonInputStage):
    def __init__(self, pspec):
        super().__init__(pspec, "input")

    def ispec(self):
        return ALUInputData(self.pspec)

    def ospec(self):
        return ALUInputData(self.pspec)

    def elaborate(self, platform):
        m = super().elaborate(platform) # covers A-invert, carry, and SO.
        comb = m.d.comb
        ctx = self.i.ctx

        # operand b
        comb += self.o.b.eq(self.i.b)

        return m
