"""SPR Pipeline Data structures

Covers MFSPR and MTSPR.  however given that the SPRs are split across
XER (which is 3 separate registers), Fast-SPR and Slow-SPR regfiles,
the data structures are slightly more involved than just "INT, SPR".

Links:
* https://bugs.libre-soc.org/show_bug.cgi?id=348
* https://libre-soc.org/openpower/isa/sprset/
* https://libre-soc.org/3d_gpu/architecture/regfile/
"""

from soc.fu.pipe_data import FUBaseData
from soc.fu.spr.spr_input_record import CompSPROpSubset
from soc.fu.alu.pipe_data import CommonPipeSpec


class SPRInputData(FUBaseData):
    regspec = [('INT', 'ra', '0:63'),        # RA
               ('SPR', 'spr1', '0:63'),      # SPR (slow)
               ('FAST', 'fast1', '0:63'),    # SPR (fast: LR, CTR etc)
               ('XER', 'xer_so', '32'),      # XER bit 32: SO
               ('XER', 'xer_ov', '33,44'),   # XER bit 34/45: CA/CA32
               ('XER', 'xer_ca', '34,45')]   # bit0: ov, bit1: ov32
    def __init__(self, pspec):
        super().__init__(pspec, False)
        # convenience
        self.a = self.ra


class SPROutputData(FUBaseData):
    regspec = [('INT', 'o', '0:63'),        # RT
               ('SPR', 'spr1', '0:63'),     # SPR (slow)
               ('FAST', 'fast1', '0:63'),   # SPR (fast: LR, CTR etc)
               ('XER', 'xer_so', '32'),     # XER bit 32: SO
               ('XER', 'xer_ov', '33,44'),  # XER bit 34/45: CA/CA32
               ('XER', 'xer_ca', '34,45')]  # bit0: ov, bit1: ov32
    def __init__(self, pspec):
        super().__init__(pspec, True)


class SPRPipeSpec(CommonPipeSpec):
    regspec = (SPRInputData.regspec, SPROutputData.regspec)
    opsubsetkls = CompSPROpSubset
