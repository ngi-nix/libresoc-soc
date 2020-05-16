from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.alu.pipe_data import IntegerData


class ALUInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.so = Signal(reset_less=True)
        self.carry_in = Signal(reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.carry_in
        yield self.so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.carry_in.eq(i.carry_in),
                      self.so.eq(i.so)]
