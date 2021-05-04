from soc.fu.ldst.ldst_input_record import CompLDSTOpSubset
from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from openpower.exceptions import LDSTException

# XXX NOTE: neither of these are actually used at present other than regspecs
# TODO: make use of them in LDSTCompUnit (somehow)

class LDSTInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'), # RA
               ('INT', 'rb', '0:63'), # RB/immediate
               ('INT', 'rc', '0:63'), # RC
               # XXX TODO, later ('XER', 'xer_so', '32') # XER bit 32: SO
               ]
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.rs = self.rc


class LDSTOutputData(FUBaseData):
    # these need to tie up with LDSTCompUnit.get_out index numbers
    # LDSTCompUnit is unusual in that it's non-standard to RegSpecAPI
    regspec = [('INT', 'o', '0:63'),   # RT
               ('INT', 'o1', '0:63'),  # RA (effective address, update mode)
               # TODO, later ('CR', 'cr_a', '0:3'),
               # TODO, later ('XER', 'xer_so', '32')
                ]
    def __init__(self, pspec):
        super().__init__(pspec, True, LDSTException)
        # convenience
        self.cr0, self.ea = self.cr_a, self.o1


class LDSTPipeSpec(CommonPipeSpec):
    regspec = (LDSTInputData.regspec, LDSTOutputData.regspec)
    opsubsetkls = CompLDSTOpSubset
