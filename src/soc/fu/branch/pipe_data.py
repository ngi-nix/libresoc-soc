"""
    Optional Register allocation listed below.  mandatory input
    (CompBROpSubset, CIA) not included.

    * CR is Condition Register (not an SPR)
    * SPR1 and SPR2 are all from the SPR regfile.  2 ports are needed

    insn       CR  SPR2  SPR1
    ----       --  ----  ----
    op_b       xx  xx     xx
    op_ba      xx  xx     xx
    op_bl      xx  xx     xx
    op_bla     xx  xx     xx
    op_bc      CR, xx,    CTR
    op_bca     CR, xx,    CTR
    op_bcl     CR, xx,    CTR
    op_bcla    CR, xx,    CTR
    op_bclr    CR, LR,    CTR
    op_bclrl   CR, LR,    CTR
    op_bcctr   CR, xx,    CTR
    op_bcctrl  CR, xx,    CTR
    op_bctar   CR, TAR,   CTR
    op_bctarl  CR, TAR,   CTR
"""

from soc.fu.pipe_data import FUBaseData, CommonPipeSpec
from soc.fu.branch.br_input_record import CompBROpSubset # TODO: replace


class BranchInputData(FUBaseData):
    # Note: for OP_BCREG, SPR1 will either be CTR, LR, or TAR
    # this involves the *decode* unit selecting the register, based
    # on detecting the operand being bcctr, bclr or bctar
    regspec = [('FAST', 'fast1', '0:63'), # see table above, SPR1
               ('FAST', 'fast2', '0:63'), # see table above, SPR2
               ('CR', 'cr_a', '0:3'),    # Condition Register(s) CR0-7
               ]
    def __init__(self, pspec):
        super().__init__(pspec, False)

        # convenience variables.  not all of these are used at once
        self.ctr = self.fast1
        self.lr = self.tar = self.fast2
        self.cr = self.cr_a


class BranchOutputData(FUBaseData):
    regspec = [('FAST', 'fast1', '0:63'),
               ('FAST', 'fast2', '0:63'),
               ('STATE', 'nia', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec, True)

        # convenience variables.
        self.ctr = self.fast1
        self.lr = self.tar = self.fast2


class BranchPipeSpec(CommonPipeSpec):
    regspec = (BranchInputData.regspec, BranchOutputData.regspec)
    opsubsetkls = CompBROpSubset
