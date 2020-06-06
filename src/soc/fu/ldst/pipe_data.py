from nmigen import Signal, Const
from soc.fu.alu.alu_input_record import CompLDSTOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data


class LDSTInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'), # RA
               ('INT', 'rb', '0:63'), # RB/immediate
               ('INT', 'rc', '0:63'), # RC
               ('XER', 'xer_so', '32')] # XER bit 32: SO
               ]
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.rs = self.rc


class LDSTOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),   # RT
               ('INT', 'o1', '0:63'),  # RA (effective address, update mode)
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0, self.ea = self.cr_a, self.o1


class LDSTPipeSpec(CommonPipeSpec):
    regspec = (LDSTInputData.regspec, LDSTOutputData.regspec)
    opsubsetkls = CompLDSTOpSubset
