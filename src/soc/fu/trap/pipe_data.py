from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.trap.trap_input_record import CompTrapOpSubset


class TrapInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),  # RA
               ('INT', 'rb', '0:63'),  # RB/immediate
               ('FAST', 'fast1', '0:63'), # SRR0
               ('FAST', 'fast2', '0:63'), # SRR1
               ('FAST', 'cia', '0:63'),  # Program counter (current)
               ('FAST', 'msr', '0:63')]  # MSR
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.srr0, self.srr1 = self.fast1, self.fast2
        self.a, self.b = self.ra, self.rb


class TrapOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),     # RA
               ('FAST', 'fast1', '0:63'), # SRR0 SPR
               ('FAST', 'fast2', '0:63'), # SRR1 SPR
               ('FAST', 'nia', '0:63'),  # NIA (Next PC)
               ('FAST', 'msr', '0:63')]  # MSR
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.srr0, self.srr1 = self.fast1, self.fast2



class TrapPipeSpec(CommonPipeSpec):
    regspec = (TrapInputData.regspec, TrapOutputData.regspec)
    opsubsetkls = CompTrapOpSubset
