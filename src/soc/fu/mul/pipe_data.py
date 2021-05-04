from soc.fu.mul.mul_input_record import CompMULOpSubset
from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from soc.fu.div.pipe_data import DivInputData, DivMulOutputData
from nmigen import Signal


class MulIntermediateData(DivInputData):
    def __init__(self, pspec):
        super().__init__(pspec)

        self.neg_res = Signal(reset_less=True)
        self.neg_res32 = Signal(reset_less=True)
        self.data.append(self.neg_res)
        self.data.append(self.neg_res32)


class MulOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:128'),
               ('XER', 'xer_so', '32')] # XER bit 32: SO
    def __init__(self, pspec):
        super().__init__(pspec, False) # still input style

        self.neg_res = Signal(reset_less=True)
        self.neg_res32 = Signal(reset_less=True)
        self.data.append(self.neg_res)
        self.data.append(self.neg_res32)


class MulPipeSpec(CommonPipeSpec):
    regspec = (DivInputData.regspec, DivMulOutputData.regspec)
    opsubsetkls = CompMULOpSubset
