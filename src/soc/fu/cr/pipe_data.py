"""
Links:
* https://libre-soc.org/3d_gpu/architecture/regfile/ section on regspecs
"""
from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.cr.cr_input_record import CompCROpSubset
from soc.decoder.power_decoder2 import Data


class CRInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),      # 64 bit range
               ('INT', 'b', '0:63'),      # 6B bit range
               ('CR', 'full_cr', '0:31'), # 32 bit range
               ('CR', 'cr_a', '0:3'),     # 4 bit range
               ('CR', 'cr_b', '0:3'),     # 4 bit range
               ('CR', 'cr_c', '0:3')]     # 4 bit range
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB
        self.full_cr = Signal(32, reset_less=True) # full CR in
        self.cr_a = Signal(4, reset_less=True)
        self.cr_b = Signal(4, reset_less=True)
        self.cr_c = Signal(4, reset_less=True) # needed for CR_OP partial update

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.full_cr
        yield self.cr_a
        yield self.cr_b
        yield self.cr_c

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a),
                      self.b.eq(i.b),
                      self.full_cr.eq(i.full_cr),
                      self.cr_a.eq(i.cr_a),
                      self.cr_b.eq(i.cr_b),
                      self.cr_c.eq(i.cr_c)]
                      

class CROutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),      # 64 bit range
               ('CR', 'full_cr', '0:31'), # 32 bit range
               ('CR', 'cr_o', '0:3')]     # 4 bit range
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True) # RA
        self.full_cr = Data(32, name="cr_out") # CR in
        self.cr_o = Data(4, name="cr_o")

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

class CRPipeSpec(CommonPipeSpec):
    regspec = (CRInputData.regspec, CROutputData.regspec)
    opsubsetkls = CompCROpSubset
