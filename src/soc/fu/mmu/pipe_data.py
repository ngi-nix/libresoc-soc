"""MMU Pipeline Data structures

Covers MFMMU and MTMMU for MMU MMUs (dsisr, dar), and DCBZ and TLBIE.

Note: RB is *redirected* (in the decoder CSV files) to the field that
happens, here, to be named "ra"!  yes wonderfully confusing.  similar
thing goes on with shift_rot.

Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=491
* https://libre-soc.org/3d_gpu/architecture/regfile/
"""

from soc.fu.pipe_data import IntegerData
from soc.fu.mmu.mmu_input_record import CompMMUOpSubset
from soc.fu.alu.pipe_data import CommonPipeSpec


class MMUInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),        # RA
               ('SPR', 'spr1', '0:63'),      # MMU (slow)
               ('FAST', 'fast1', '0:63'),    # MMU (fast: LR, CTR etc)
               ]   
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a = self.ra


class MMUOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('SPR', 'spr1', '0:63'),     # MMU (slow)
               ('FAST', 'fast1', '0:63'),   # MMU (fast: LR, CTR etc)
               ]
    def __init__(self, pspec):
        super().__init__(pspec, True)


class MMUPipeSpec(CommonPipeSpec):
    regspec = (MMUInputData.regspec, MMUOutputData.regspec)
    opsubsetkls = CompMMUOpSubset
