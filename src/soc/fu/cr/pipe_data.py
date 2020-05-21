from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class CRInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('CR', 'cr', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.cr = Signal(32, reset_less=True) # CR in

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.cr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a),
                      self.cr.eq(i.cr)]

class CROutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('CR', 'cr', '32')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True) # RA
        self.cr = Signal(32, reset_less=True, name="cr_out") # CR in

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.cr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.cr.eq(i.cr)]

# TODO: replace CompALUOpSubset with CompCROpSubset
class CRPipeSpec(CommonPipeSpec):
    regspec = (CRInputData.regspec, CROutputData.regspec)
    opsubsetkls = CompALUOpSubset
