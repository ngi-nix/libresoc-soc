from nmigen import Signal, Const
from ieee754.fpcommon.getop import FPPipeContext
from soc.fu.pipe_data import IntegerData
from soc.decoder.power_decoder2 import Data
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset # TODO: replace


class TrapInputData(IntegerData):
    regspec = [('INT', 'ra', '0:63'),
               ('INT', 'rb', '0:63'),
               ('FAST', 'spr1', '0:63'),
               ('FAST', 'cia', '0:63'),
               ('FAST', 'msr', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.ra = Signal(64, reset_less=True)  # RA
        self.rb = Signal(64, reset_less=True)  # RB/immediate
        self.spr1 = Data(64, name="spr1") # SRR0
        self.cia = Signal(64, reset_less=True)  # Program counter
        self.msr = Signal(64, reset_less=True)  # MSR
        # convenience
        self.srr0, self.a, self.b = self.spr1, self.ra, self.rb

    def __iter__(self):
        yield from super().__iter__()
        yield self.ra
        yield self.rb
        yield self.spr1
        yield self.cia
        yield self.msr

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.ra.eq(i.ra), self.rb.eq(i.rb), self.spr1.eq(i.spr1),
                      self.cia.eq(i.cia), self.msr.eq(i.msr)]


class TrapOutputData(IntegerData):
    regspec = [('INT', 'o', '0:63'),
               ('FAST', 'spr1', '0:63'),
               ('FAST', 'spr2', '0:63'),
               ('FAST', 'nia', '0:63'),
               ('FAST', 'msr', '0:63')]
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Data(64, name="o")       # RA
        self.spr1 = Data(64, name="spr1") # SRR0 SPR
        self.spr2 = Data(64, name="spr2") # SRR1 SPR
        self.nia = Data(64, name="nia") # NIA (Next PC)
        self.msr = Data(64, name="msr") # MSR
        # convenience
        self.srr0, self.srr1 = self.spr1, self.spr2

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.nia
        yield self.msr
        yield self.spr1
        yield self.spr2

    def eq(self, i):
        lst = super().eq(i)
        return lst + [ self.o.eq(i.o), self.nia.eq(i.nia), self.msr.eq(i.msr),
                      self.spr1.eq(i.spr1), self.spr2.eq(i.spr2)]


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
