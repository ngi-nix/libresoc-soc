from nmigen import Signal, Const, Cat
from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data


class ALUInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'b', '0:63'),
               ('XER', 'xer_so', '32'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.xer_so = Signal(reset_less=True) # XER bit 32: SO
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.xer_ca
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.xer_ca.eq(i.xer_ca),
                      self.xer_so.eq(i.xer_so)]


class ALUOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr0', '0:3'),
               ('XER', 'xer_ca', '34,45'),
               ('XER', 'xer_ov', '33,44'),
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="stage_o")
        self.cr0 = Data(4, name="cr0")
        self.xer_ca = Data(2, name="xer_co") # bit0: ca, bit1: ca32
        self.xer_ov = Data(2, name="xer_ov") # bit0: ov, bit1: ov32
        self.xer_so = Data(1, name="xer_so")

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.xer_ca
        yield self.cr0
        yield self.xer_ov
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.xer_ca.eq(i.xer_ca),
                      self.cr0.eq(i.cr0),
                      self.xer_ov.eq(i.xer_ov), self.xer_so.eq(i.xer_so)]


class ALUPipeSpec(CommonPipeSpec):
    regspec = (ALUInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompALUOpSubset
    def rdflags(self, e): # in order of regspec
        reg1_ok = e.read_reg1.ok # RA
        reg2_ok = e.read_reg2.ok # RB
        return Cat(reg1_ok, reg2_ok, 1, 1) # RA RB CA SO
