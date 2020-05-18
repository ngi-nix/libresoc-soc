from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.alu.alu_input_record import CompALUOpSubset
from ieee754.fpcommon.getop import FPPipeContext
from soc.alu.pipe_data import IntegerData


class ShiftRotInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.ra = Signal(64, reset_less=True) # RA
        self.rs = Signal(64, reset_less=True) # RS
        self.rb = Signal(64, reset_less=True) # RB/immediate
        self.so = Signal(reset_less=True)
        self.carry_in = Signal(reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.ra
        yield self.rs
        yield self.rb
        yield self.carry_in
        yield self.so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.rs.eq(i.rs), self.ra.eq(i.ra),
                      self.rb.eq(i.rb),
                      self.carry_in.eq(i.carry_in),
                      self.so.eq(i.so)]
