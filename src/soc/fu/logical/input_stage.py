# This stage is intended to adjust the input data before sending it to
# the actual Logical pipeline. Things like handling inverting the input, xer_ca
# generation for subtraction, and handling of immediates should happen
# here
from soc.fu.common_input_stage import CommonInputStage
from soc.fu.logical.pipe_data import LogicalInputData


class LogicalInputStage(CommonInputStage):
    def __init__(self, pspec):
        super().__init__(pspec, "input")
        self.invert_op = "rb" # inversion is on register b

    def ispec(self):
        return LogicalInputData(self.pspec)

    def ospec(self):
        return LogicalInputData(self.pspec)

    def elaborate(self, platform):
        m = super().elaborate(platform) # covers B-invert, carry, excludes SO
        comb = m.d.comb
        ctx = self.i.ctx

        return m
