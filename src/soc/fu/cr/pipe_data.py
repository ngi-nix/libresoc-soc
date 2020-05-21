from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class CRInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('CR', 'full_cr', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.full_cr = Signal(32, reset_less=True) # CR in
        self.cr_a = Signal(4, reset_less=True)
        self.cr_b = Signal(4, reset_less=True)
        self.cr_c = Signal(4, reset_less=True) # The output cr bits

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.full_cr
        yield self.cr_a
        yield self.cr_b
        yield self.cr_c

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a),
                      self.full_cr.eq(i.full_cr),
                      self.cr_a.eq(i.cr_a),
                      self.cr_b.eq(i.cr_b),
                      self.cr_c.eq(i.cr_c)]
                      

class CROutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True) # RA
        self.full_cr = Signal(32, reset_less=True, name="cr_out") # CR in
        self.cr_o = Signal(4, reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.full_cr
        yield self.cr_o

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.full_cr.eq(i.full_cr),
                      self.cr_o.eq(i.cr_o)]

# TODO: replace CompALUOpSubset with CompCROpSubset
class CRPipeSpec(CommonPipeSpec):
    regspec = (CRInputData.regspec, CROutputData.regspec)
    opsubsetkls = CompALUOpSubset
