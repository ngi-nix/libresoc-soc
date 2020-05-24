from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class TrapInputData(IntegerData):
    regspec = [('INT', 'a', '0:63'),
               ('INT', 'b', '0:63'),
               ('PC', 'cia', '0:63'),
               ('MSR', 'msr', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True)  # RA
        self.b = Signal(64, reset_less=True)  # RB/immediate
        self.cia = Signal(64, reset_less=True)  # Program counter
        self.msr = Signal(64, reset_less=True)  # MSR

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.cia
        yield self.msr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.cia.eq(i.cia), self.msr.eq(i.msr)]


class TrapOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('SPR', 'srr0', '0:63'),
               ('SPR', 'srr1', '0:63'),
               ('PC', 'nia', '0:63'),
               ('MSR', 'msr', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="o")       # RA
        self.srr0 = Data(64, name="srr0") # SRR0 SPR
        self.srr1 = Data(64, name="srr1") # SRR1 SPR
        self.nia = Data(64, name="nia") # NIA (Next PC)
        self.msr = Data(64, name="msr") # MSR

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.nia
        yield self.msr
        yield self.srr0
        yield self.srr1

    def eq(self, i):
        lst = super().eq(i)
        return lst + [ self.o.eq(i.o), self.nia.eq(i.nia), self.msr.eq(i.msr),
                      self.srr0.eq(i.srr0), self.srr1.eq(i.srr1)]


# TODO: replace CompALUOpSubset with CompTrapOpSubset
class TrapPipeSpec:
    regspec = (TrapInputData.regspec, TrapOutputData.regspec)
    opsubsetkls = CompALUOpSubset
    def __init__(self, id_wid, op_wid):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: self.opsubsetkls(name="op")
        self.stage = None
        self.pipekls = SimpleHandshakeRedir
