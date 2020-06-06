from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class TrapInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),  # RA
               ('INT', 'rb', '0:63'),  # RB/immediate
               ('FAST', 'spr1', '0:63'), # SRR0
               ('FAST', 'cia', '0:63'),  # Program counter (current)
               ('FAST', 'msr', '0:63')]  # MSR
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.srr0, self.a, self.b = self.spr1, self.ra, self.rb


class TrapOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),     # RA
               ('FAST', 'spr1', '0:63'), # SRR0 SPR
               ('FAST', 'spr2', '0:63'), # SRR1 SPR
               ('FAST', 'nia', '0:63'),  # NIA (Next PC)
               ('FAST', 'msr', '0:63')]  # MSR
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.srr0, self.srr1 = self.spr1, self.spr2



# TODO: replace CompALUOpSubset with CompTrapOpSubset
class TrapPipeSpec:
    regspec = (TrapInputData.regspec, TrapOutputData.regspec)
    opsubsetkls = CompALUOpSubset
    def __init__(self, id_wid, op_wid):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: self.opsubsetkls(name="op")
        self.stage = None
        self.pipekls = SimpleHandshakeRedir
