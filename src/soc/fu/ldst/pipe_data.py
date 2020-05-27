from nmigen import Signal, Const
from soc.fu.alu.alu_input_record import CompLDSTOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data


class LDSTInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'b', '0:63'),
               ('INT', 'c', '0:63'),
               ('XER', 'xer_so', '32')]
               ]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.c = Signal(64, reset_less=True) # RC
        self.xer_so = Signal(reset_less=True) # XER bit 32: SO

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.c
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b), self.c.eq(i.c),
                      self.xer_so.eq(i.xer_so)]


class LDSTOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('INT', 'ea', '0:63'),
               ('CR', 'cr0', '0:3'),
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="stage_o")
        self.ea = Data(64, name="ea")
        self.cr0 = Data(4, name="cr0")
        self.xer_so = Data(1, name="xer_so")

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.ea
        yield self.xer_ca
        yield self.cr0
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.ea.eq(i.ea),
                      self.cr0.eq(i.cr0),
                      self.xer_so.eq(i.xer_so)]


class LDSTPipeSpec(CommonPipeSpec):
    regspec = (LDSTInputData.regspec, LDSTOutputData.regspec)
    opsubsetkls = CompLDSTOpSubset
