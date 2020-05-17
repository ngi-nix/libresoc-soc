"""
    Optional Register allocation listed below.  mandatory input
    (CompBROpSubset, CIA) not included.

    * CR is Condition Register (not an SPR)
    * SPR1, SPR2 and SPR3 are all from the SPR regfile.  3 ports are needed

    insn       CR  SPR1  SPR2    SPR3
    ----       --  ----  ----    ----
    op_b       xx  xx     xx     xx
    op_ba      xx  xx     xx     xx
    op_bl      xx  xx     xx     xx
    op_bla     xx  xx     xx     xx
    op_bc      CR, xx,    CTR    xx
    op_bca     CR, xx,    CTR    xx
    op_bcl     CR, xx,    CTR    xx
    op_bcla    CR, xx,    CTR    xx
    op_bclr    CR, LR,    CTR    xx
    op_bclrl   CR, LR,    CTR    xx
    op_bcctr   CR, xx,    CTR    xx
    op_bcctrl  CR, xx,    CTR    xx
    op_bctar   CR, TAR,   CTR,   xx
    op_bctarl  CR, TAR,   CTR,   xx

    op_sc      xx  xx     xx     MSR
    op_scv     xx  LR,    SRR1,  MSR
    op_rfscv   xx  LR,    CTR,   MSR
    op_rfid    xx  SRR0,  SRR1,  MSR
    op_hrfid   xx  HSRR0, HSRR1, MSR
"""

from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data
from soc.alu.pipe_data import IntegerData


class BranchInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        # Note: for OP_BCREG, SPR1 will either be CTR, LR, or TAR
        # this involves the *decode* unit selecting the register, based
        # on detecting the operand being bcctr, bclr or bctar

        self.spr1 = Signal(64, reset_less=True) # see table above, SPR1
        self.spr2 = Signal(64, reset_less=True) # see table above, SPR2
        self.spr3 = Signal(64, reset_less=True) # see table above, SPR3
        self.cr = Signal(32, reset_less=True)   # Condition Register(s) CR0-7
        self.cia = Signal(64, reset_less=True)  # Current Instruction Address

        # convenience variables.  not all of these are used at once
        self.ctr = self.srr0 = self.hsrr0 = self.spr2
        self.lr = self.tar = self.srr1 = self.hsrr1 = self.spr1
        self.msr = self.spr3

    def __iter__(self):
        yield from super().__iter__()
        yield self.spr1
        yield self.spr2
        yield self.spr3
        yield self.cr
        yield self.cia

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.spr1.eq(i.spr1), self.spr2.eq(i.spr2),
                      self.spr3.eq(i.spr3),
                      self.cr.eq(i.cr), self.cia.eq(i.cia)]


class BranchOutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.lr = Data(64, name="lr")
        self.spr = Data(64, name="spr")
        self.nia_out = Data(64, name="nia_out")

        # convenience variables.
        self.ctr = self.spr

    def __iter__(self):
        yield from super().__iter__()
        yield from self.lr
        yield from self.spr
        yield from self.nia_out

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.lr.eq(i.lr), self.spr.eq(i.spr),
                      self.nia_out.eq(i.nia_out)]
