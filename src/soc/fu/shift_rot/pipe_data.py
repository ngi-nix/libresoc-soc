from soc.fu.shift_rot.sr_input_record import CompSROpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.logical.pipe_data import LogicalOutputData


class ShiftRotInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),      # RA
               ('INT', 'rb', '0:63'),      # RB
               ('INT', 'rc', '0:63'),      # RS
               ('XER', 'xer_ca', '34,45')] # XER bit 34/45: CA/CA32
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.rs = self.ra, self.rc


class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, LogicalOutputData.regspec)
    opsubsetkls = CompSROpSubset
