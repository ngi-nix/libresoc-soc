# This stage is intended to adjust the input data before sending it to
# the actual ALU. Things like handling inverting the input, xer_ca
# generation for subtraction, and handling of immediates should happen
# in the base class (CommonOutputStage.elaborate).
from soc.fu.alu.output_stage import ALUOutputStage
from soc.fu.div.pipe_data import DivMulOutputData

# simply over-ride ALUOutputStage ispec / ospec
class DivMulOutputStage(ALUOutputStage):
    def ispec(self): return DivMulOutputData(self.pspec)
    def ospec(self): return DivMulOutputData(self.pspec)

