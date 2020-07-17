# This stage is intended to adjust the input data before sending it to
# the actual ALU. Things like handling inverting the input, xer_ca
# generation for subtraction, and handling of immediates should happen
# in the base class (CommonInputStage.elaborate).
from soc.fu.alu.input_stage import ALUInputStage
from soc.fu.div.pipe_data import DivInputData

# simply over-ride ALUInputStage ispec / ospec


class DivMulInputStage(ALUInputStage):
    def __init__(self, pspec):
        super().__init__(pspec)

    def ispec(self): return DivInputData(self.pspec)
    def ospec(self): return DivInputData(self.pspec)
