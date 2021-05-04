from soc.fu.shift_rot.sr_input_record import CompSROpSubset
from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUOutputData


class ShiftRotInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),      # RA
               ('INT', 'rb', '0:63'),      # RB
               ('INT', 'rc', '0:63'),      # RS
               ('XER', 'xer_so', '32'), # XER bit 32: SO
               ('XER', 'xer_ca', '34,45')] # XER bit 34/45: CA/CA32
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b, self.rs = self.ra, self.rb, self.rc


# input to shiftrot final stage (common output)
class ShiftRotOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_so', '32'),    # bit0: so
               ('XER', 'xer_ca', '34,45'), # XER bit 34/45: CA/CA32
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


# output from shiftrot final stage (common output) - note that XER.so
# is *not* included (the only reason it's in the input is because of CR0)
class ShiftRotOutputDataFinal(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ca', '34,45'), # XER bit 34/45: CA/CA32
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, ShiftRotOutputDataFinal.regspec)
    opsubsetkls = CompSROpSubset
