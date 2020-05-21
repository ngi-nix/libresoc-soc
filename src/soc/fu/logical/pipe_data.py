from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class LogicalInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'rb', '0:63'),
               ('XER', 'xer_so', '32'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.xer_so = Signal(reset_less=True)    # XER bit 32: SO
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


class LogicalPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
