from nmigen import Signal, Const, Cat
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.shift_rot.sr_input_record import CompSROpSubset
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.logical.pipe_data import LogicalOutputData
from nmutil.dynamicpipe import SimpleHandshakeRedir


class ShiftRotInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),
               ('INT', 'rb', '0:63'),
               ('INT', 'rc', '0:63'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.ra = Signal(64, reset_less=True) # RA
        self.rb = Signal(64, reset_less=True) # RB
        self.rc = Signal(64, reset_less=True) # RS
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32
        # convenience
        self.a, self.rs = self.ra, self.rc

    def __iter__(self):
        yield from super().__iter__()
        yield self.ra
        yield self.rb
        yield self.rc
        yield self.xer_ca

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.rc.eq(i.rc), self.ra.eq(i.ra),
                      self.rb.eq(i.rb),
                      self.xer_ca.eq(i.xer_ca) ]


class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, LogicalOutputData.regspec)
    opsubsetkls = CompSROpSubset
    def rdflags(self, e): # in order of regspec input
        reg1_ok = e.read_reg1.ok # RA
        reg2_ok = e.read_reg2.ok # RB
        reg3_ok = e.read_reg3.ok # RS
        return Cat(reg1_ok, reg2_ok, reg3_ok, 1) # RA RB RC CA
