from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.alu.pipe_data import IntegerData


class CRInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.cr = Signal(64, reset_less=True) # CR in

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.cr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a),
                      self.cr.eq(i.cr)]

class CROutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True) # RA
        self.cr = Signal(64, reset_less=True) # CR in

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.cr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.cr.eq(i.cr)]
