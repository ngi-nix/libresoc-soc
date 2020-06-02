from nmigen import Signal, Const
from soc.fu.alu.alu_input_record import CompLDSTOpSubset
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data


class LDSTInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),
               ('INT', 'rb', '0:63'),
               ('INT', 'rc', '0:63'),
               ('XER', 'xer_so', '32')]
               ]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.ra = Signal(64, reset_less=True) # RA
        self.rb = Signal(64, reset_less=True) # RB/immediate
        self.rc = Signal(64, reset_less=True) # RC
        self.xer_so = Signal(reset_less=True) # XER bit 32: SO
        # convenience
        self.rs = self.rc

    def __iter__(self):
        yield from super().__iter__()
        yield self.ra
        yield self.rb
        yield self.rc
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.ra.eq(i.ra), self.rb.eq(i.rb), self.rc.eq(i.rc),
                      self.xer_so.eq(i.xer_so)]


class LDSTOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('INT', 'o1', '0:63'),
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_so', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="stage_o")
        self.o1 = Data(64, name="o1")
        self.cr_a = Data(4, name="cr_a")
        self.xer_so = Data(1, name="xer_so")
        # convenience
        self.cr0, self.ea = self.cr_a, self.o1

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.o1
        yield self.xer_ca
        yield self.cr_a
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.o1.eq(i.o1),
                      self.cr_a.eq(i.cr_a),
                      self.xer_so.eq(i.xer_so)]


class LDSTPipeSpec(CommonPipeSpec):
    regspec = (LDSTInputData.regspec, LDSTOutputData.regspec)
    opsubsetkls = CompLDSTOpSubset
