from soc.fu.pipe_data import FUBaseData
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


# input (and output) for logical initial stage (common input)
class LogicalInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'), # RA
               ('INT', 'rb', '0:63'), # RB/immediate
               ('XER', 'xer_so', '32'),    # bit0: so
               ]
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


# input to logical final stage (common output)
class LogicalOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_so', '32'),    # bit0: so
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


# output from logical final stage (common output) - note that XER.so
# is *not* included (the only reason it's in the input is because of CR0)
class LogicalOutputDataFinal(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('CR', 'cr_a', '0:3'),
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class LogicalPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, LogicalOutputDataFinal.regspec)
    opsubsetkls = CompLogicalOpSubset
