from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class LogicalInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'rb', '0:63'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.xer_ca

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.xer_ca.eq(i.xer_ca) ]


class LogicalOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr0', '0:3'),
               ('XER', 'xer_ca', '34,45'),
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True, name="stage_o")
        self.cr0 = Data(4, name="cr0")
        self.xer_ca = Data(2, name="xer_co") # bit0: ca, bit1: ca32
        self.xer_so = Data(1, name="xer_so")

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.xer_ca
        yield self.cr0
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.xer_ca.eq(i.xer_ca),
                      self.cr0.eq(i.cr0),
                      self.xer_so.eq(i.xer_so)]


class LogicalPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, LogicalOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
