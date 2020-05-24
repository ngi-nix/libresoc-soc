from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from soc.fu.spr.spr_input_record import CompSPROpSubset


class SPRInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('SPR', 'spr1', '0:63'),
               ('FAST', 'spr2', '0:63'),
               ('XER', 'xer_so', '32'),
               ('XER', 'xer_ov', '33,44'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.spr1 = Signal(64, reset_less=True) # SPR (slow)
        self.spr2 = Signal(64, reset_less=True) # SPR (fast: MSR, LR, CTR etc)
        self.xer_so = Signal(reset_less=True) # XER bit 32: SO
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32
        self.xer_ov = Signal(2, reset_less=True) # bit0: ov, bit1: ov32

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.spr1
        yield self.spr2
        yield self.xer_ca
        yield self.xer_ov
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.reg.eq(i.reg),
                      self.spr1.eq(i.spr1), self.spr2.eq(i.spr2),
                      self.xer_ca.eq(i.xer_ca),
                      self.xer_ov.eq(i.xer_ov),
                      self.xer_so.eq(i.xer_so)]


class SPROutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('SPR', 'spr1', '0:63'),
               ('FAST', 'spr2', '0:63'),
               ('XER', 'xer_so', '32'),
               ('XER', 'xer_ov', '33,44'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="rt") # RT
        self.spr1 = Data(64, name="spr1") # SPR (slow)
        self.spr2 = Data(64, name="spr2") # SPR (fast: MSR, LR, CTR etc)
        self.xer_so = Data(1, name="xer_so") # XER bit 32: SO
        self.xer_ca = Data(2, name="xer_ca") # XER bit 34/45: CA/CA32
        self.xer_ov = Data(2, name="xer_ov") # bit0: ov, bit1: ov32

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.spr1
        yield self.spr2
        yield self.xer_ca
        yield self.xer_ov
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o), self.reg.eq(i.reg),
                      self.spr1.eq(i.spr1), self.spr2.eq(i.spr2),
                      self.xer_ca.eq(i.xer_ca),
                      self.xer_ov.eq(i.xer_ov),
                      self.xer_so.eq(i.xer_so)]



class SPRPipeSpec:
    regspec = (SPRInputData.regspec, SPROutputData.regspec)
    opsubsetkls = CompSPROpSubset
    def __init__(self, id_wid, op_wid):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: self.opsubsetkls(name="op")
        self.stage = None
        self.pipekls = SimpleHandshakeRedir
