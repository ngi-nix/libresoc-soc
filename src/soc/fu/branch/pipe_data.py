"""
    Optional Register allocation listed below.  mandatory input
    (CompBROpSubset, CIA) not included.

    * CR is Condition Register (not an SPR)
    * SPR1 and SPR2 are all from the SPR regfile.  2 ports are needed

    insn       CR  SPR1  SPR2
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

from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data
from soc.fu.alu.pipe_data import IntegerData
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class BranchInputData(IntegerData):
    regspec = [('SPR', 'spr1', '0:63'),
               ('SPR', 'spr2', '0:63'),
               ('CR', 'cr', '32'),
               ('PC', 'cia', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        # Note: for OP_BCREG, SPR1 will either be CTR, LR, or TAR
        # this involves the *decode* unit selecting the register, based
        # on detecting the operand being bcctr, bclr or bctar

        self.spr1 = Signal(64, reset_less=True) # see table above, SPR1
        self.spr2 = Signal(64, reset_less=True) # see table above, SPR2
        self.cr = Signal(32, reset_less=True)   # Condition Register(s) CR0-7
        self.cia = Signal(64, reset_less=True)  # Current Instruction Address

        # convenience variables.  not all of these are used at once
        self.ctr = self.srr0 = self.hsrr0 = self.spr2
        self.lr = self.tar = self.srr1 = self.hsrr1 = self.spr1

    def __iter__(self):
        yield from super().__iter__()
        yield self.spr1
        yield self.spr2
        yield self.cr
        yield self.cia

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.spr1.eq(i.spr1), self.spr2.eq(i.spr2),
                      self.cr.eq(i.cr), self.cia.eq(i.cia)]


class BranchOutputData(IntegerData):
    regspec = [('SPR', 'spr1', '0:63'),
               ('SPR', 'spr2', '0:63'),
               ('PC', 'nia', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.spr1 = Data(64, name="spr1")
        self.spr2 = Data(64, name="spr2")
        self.nia = Data(64, name="nia")

        # convenience variables.
        self.lr = self.tar = self.spr1
        self.ctr = self.spr2

    def __iter__(self):
        yield from super().__iter__()
        yield from self.spr1
        yield from self.spr2
        yield from self.nia

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.spr1.eq(i.spr1), self.spr2.eq(i.spr2),
                      self.nia.eq(i.nia)]


# TODO: replace CompALUOpSubset with CompBranchOpSubset
class BranchPipeSpec:
    regspec = (BranchInputData.regspec, BranchOutputData.regspec)
    opsubsetkls = CompALUOpSubset
    def __init__(self, id_wid, op_wid):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: self.opsubsetkls(name="op")
        self.stage = None
        self.pipekls = SimpleHandshakeRedir
