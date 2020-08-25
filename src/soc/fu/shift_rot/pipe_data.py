from soc.fu.shift_rot.sr_input_record import CompSROpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUOutputData


class ShiftRotInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),      # RA
               ('INT', 'rb', '0:63'),      # RB
               ('INT', 'rc', '0:63'),      # RS
               ('XER', 'xer_so', '32'), # XER bit 32: SO
               ('XER', 'xer_ca', '34,45')] # XER bit 34/45: CA/CA32
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b, self.rs = self.ra, self.rb, self.rc


# sigh although ShiftRot never changes xer_ov it is just easier
# right now to have it.  also SO never gets changed, although it
# is an input (to create CR).  really need something similar to
# MulOutputData which has xer_so yet derives from LogicalOutputData
class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompSROpSubset
