from nmigen import Signal, Const, Cat
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from soc.fu.alu.pipe_data import ALUOutputData, CommonPipeSpec
from soc.fu.logical.logical_input_record import CompLogicalOpSubset


class LogicalInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),
               ('INT', 'rb', '0:63'),
               ]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.ra = Signal(64, reset_less=True) # RA
        self.rb = Signal(64, reset_less=True) # RB/immediate
        # convenience
        self.a, self.b = self.ra, self.rb

    def __iter__(self):
        yield from super().__iter__()
        yield self.ra
        yield self.rb

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.ra.eq(i.ra), self.rb.eq(i.rb),
                       ]


class LogicalOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr_a', '0:3'),
               ('XER', 'xer_ca', '34,45'),
               ]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="stage_o")  # RT
        self.cr_a = Data(4, name="cr_a")
        self.xer_ca = Data(2, name="xer_co") # bit0: ca, bit1: ca32
        # convenience
        self.cr0 = self.cr_a

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.xer_ca
        yield self.cr_a

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.xer_ca.eq(i.xer_ca),
                      self.cr_a.eq(i.cr_a),
                      ]


class LogicalPipeSpec(CommonPipeSpec):
    regspec = (LogicalInputData.regspec, LogicalOutputData.regspec)
    opsubsetkls = CompLogicalOpSubset
