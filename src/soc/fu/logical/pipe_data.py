from nmigen import Signal, Const, Cat
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class LogicalInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'), # RA
               ('INT', 'rb', '0:63'), # RB/immediate
               ]
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a, self.b = self.ra, self.rb


class LogicalOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ca', '34,45'), # bit0: ca, bit1: ca32
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.cr0 = self.cr_a


class LogicalPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, LogicalOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
