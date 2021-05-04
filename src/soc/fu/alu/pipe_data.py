from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.pipe_data import FUBaseData, CommonPipeSpec


class ALUInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'), # RA
               ('INT', 'rb', '0:63'), # RB/immediate
               ('XER', 'xer_so', '32'), # XER bit 32: SO
               ('XER', 'xer_ca', '34,45')] # XER bit 34/45: CA/CA32
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


class ALUOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ca', '34,45'), # bit0: ca, bit1: ca32
               ('XER', 'xer_ov', '33,44'), # bit0: ov, bit1: ov32
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class ALUPipeSpec(CommonPipeSpec):
    regspec = (ALUInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompALUOpSubset
