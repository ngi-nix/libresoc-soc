"""MMU Pipeline Data structures

Covers MFMMU and MTMMU for MMU MMUs (dsisr, dar), and DCBZ and TLBIE.

Interestingly none of the MMU instructions use RA, they all use RB.
except dcbz which uses (RA|0)

Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=491
* https://libre-soc.org/3d_gpu/architecture/regfile/
"""

from soc.fu.pipe_data import FUBaseData
from soc.fu.mmu.mmu_input_record import CompMMUOpSubset
from soc.fu.alu.pipe_data import CommonPipeSpec


class MMUInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),        # RA
               ('INT', 'rb', '0:63'),        # RB
               ('SPR', 'spr1', '0:63'),      # MMU (slow)
               ]   
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a = self.ra
        self.b = self.rb


class MMUOutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('SPR', 'spr1', '0:63'),     # MMU (slow)
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)


class MMUPipeSpec(CommonPipeSpec):
    regspec = (MMUInputData.regspec, MMUOutputData.regspec)
    opsubsetkls = CompMMUOpSubset
