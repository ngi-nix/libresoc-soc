from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.alu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data


class TrapInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True)  # RA
        self.b = Signal(64, reset_less=True)  # RB/immediate
        self.cia = Signal(64, reset_less=True)  # Program counter
        self.msr = Signal(64, reset_less=True)  # MSR

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.cia
        yield self.msr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.cia.eq(i.nia), self.msr.eq(i.msr)]


class TrapOutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.nia = Data(64, name="nia") # NIA (Next PC)
        self.msr = Signal(64, reset_less=True) # MSR
        self.srr0 = Data(64, name="srr0") # SRR0 SPR
        self.srr1 = Data(64, name="srr1") # SRR1 SPR

    def __iter__(self):
        yield from super().__iter__()
        yield self.nia
        yield self.msr
        yield self.srr0
        yield self.srr1

    def eq(self, i):
        lst = super().eq(i)
        return lst + [ self.nia.eq(i.nia), self.msr.eq(i.msr),
                      self.srr0.eq(i.srr0), self.srr1.eq(i.srr1)]
