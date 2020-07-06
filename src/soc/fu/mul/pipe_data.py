from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUOutputData, ALUInputData
from nmigen import Signal


class MulIntermediateData(ALUInputData):
    def __init__(self, pspec):
        super().__init__(pspec)

        self.neg_res = Signal(reset_less=True)
        self.neg_res32 = Signal(reset_less=True)
        self.data.append(self.neg_res)
        self.data.append(self.neg_res32)


class MulOutputData(IntegerData):
    regspec = [('INT', 'o', '0:128'),
               ('XER', 'xer_so', '32'), # XER bit 32: SO
               ('XER', 'xer_ca', '34,45')] # XER bit 34/45: CA/CA32
    def __init__(self, pspec):
        super().__init__(pspec, False) # still input style

        self.neg_res = Signal(reset_less=True)
        self.neg_res32 = Signal(reset_less=True)
        self.data.append(self.neg_res)
        self.data.append(self.neg_res32)


class MulPipeSpec(CommonPipeSpec):
    regspec = (ALUInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompALUOpSubset
