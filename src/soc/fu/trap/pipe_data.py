from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from soc.fu.trap.trap_input_record import CompTrapOpSubset


class TrapInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),  # RA
               ('INT', 'rb', '0:63'),  # RB/immediate
               ('FAST', 'fast1', '0:63'), # SRR0
               ('FAST', 'fast2', '0:63'), # SRR1
               ('FAST', 'fast3', '0:63'), # SVSRR0
                # note here that MSR CIA and SVSTATE are *not* read as regs:
                # they are passed in as incoming "State", via the
                # CompTrapOpSubset
               ] 
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.srr0, self.srr1, self.svsrr0 = self.fast1, self.fast2, self.fast3
        self.a, self.b = self.ra, self.rb


class TrapOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),     # RA
               ('FAST', 'fast1', '0:63'), # SRR0 SPR
               ('FAST', 'fast2', '0:63'), # SRR1 SPR
               ('FAST', 'fast3', '0:63'), # SRR2 SPR
               # ... however we *do* need to *write* MSR, NIA, SVSTATE (RFID)
               ('STATE', 'nia', '0:63'),  # NIA (Next PC)
               ('STATE', 'msr', '0:63'),  # MSR
               ('STATE', 'svstate', '0:31')]  # SVSTATE
    def __init__(self, pspec):
        super().__init__(pspec, True)
        # convenience
        self.srr0, self.srr1, self.svsrr0 = self.fast1, self.fast2, self.fast3



class TrapPipeSpec(CommonPipeSpec):
    regspec = (TrapInputData.regspec, TrapOutputData.regspec)
    opsubsetkls = CompTrapOpSubset
