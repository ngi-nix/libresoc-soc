from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData, CommonPipeSpec
from soc.fu.alu.pipe_data import ALUOutputData
from nmutil.dynamicpipe import SimpleHandshakeRedir


class ShiftRotInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'rs', '0:63'),
               ('INT', 'rb', '0:63'),
               ('XER', 'xer_ca', '34,45')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.rs = Signal(64, reset_less=True) # RS
        self.rb = Signal(64, reset_less=True) # RB/immediate
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.rs
        yield self.rb
        yield self.xer_ca

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.rs.eq(i.rs), self.a.eq(i.a),
                      self.rb.eq(i.rb),
                      self.xer_ca.eq(i.xer_ca) ]


# TODO: replace CompALUOpSubset with CompShiftRotOpSubset
class ShiftRotPipeSpec(CommonPipeSpec):
    regspec = (ShiftRotInputData.regspec, ALUOutputData.regspec)
    opsubsetkls = CompALUOpSubset
