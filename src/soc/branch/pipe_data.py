from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data


class IntegerData:

    def __init__(self, pspec):
        self.ctx = FPPipeContext(pspec)
        self.muxid = self.ctx.muxid

    def __iter__(self):
        yield from self.ctx

    def eq(self, i):
        return [self.ctx.eq(i.ctx)]


class BranchInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        # We need both lr and spr for bclr and bcctrl. Bclr can read
        # from both ctr and lr, and bcctrl can write to both ctr and
        # lr.
        self.lr = Signal(64, reset_less=True)
        self.spr = Signal(64, reset_less=True)
        self.cr = Signal(32, reset_less=True)
        self.nia = Signal(64, reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.lr
        yield self.spr
        yield self.cr
        yield self.nia

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.lr.eq(i.lr), self.spr.eq(i.lr),
                      self.cr.eq(i.cr), self.nia.eq(i.nia)]


class BranchOutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.lr = Data(64, name="lr")
        self.spr = Data(64, name="spr")
        self.nia_out = Data(64, name="nia_out")

    def __iter__(self):
        yield from super().__iter__()
        yield from self.lr
        yield from self.spr
        yield from self.nia_out

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.lr.eq(i.lr), self.spr.eq(i.spr),
                      self.nia_out.eq(i.nia_out)]
