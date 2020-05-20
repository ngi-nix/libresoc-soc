from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.fu.alu.alu_input_record import CompALUOpSubset
from ieee754.fpcommon.getop import FPPipeContext
from soc.decoder.power_decoder2 import Data

class IntegerData:

    def __init__(self, pspec):
        self.ctx = FPPipeContext(pspec)
        self.muxid = self.ctx.muxid

    def __iter__(self):
        yield from self.ctx

    def eq(self, i):
        return [self.ctx.eq(i.ctx)]

    def ports(self):
        return self.ctx.ports()


class ALUInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True) # RA
        self.b = Signal(64, reset_less=True) # RB/immediate
        self.xer_so = Signal(reset_less=True) # XER bit 32: SO
        self.xer_ca = Signal(2, reset_less=True) # XER bit 34/45: CA/CA32

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b
        yield self.xer_ca
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b),
                      self.xer_ca.eq(i.xer_ca),
                      self.xer_so.eq(i.xer_so)]

# TODO: ALUIntermediateData which does not have
# cr0, ov, ov32 in it (because they are generated as outputs by
# the final output stage, not by the intermediate stage)
# https://bugs.libre-soc.org/show_bug.cgi?id=305#c19

class ALUOutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True, name="stage_o")
        self.cr0 = Data(4, name="cr0")
        self.xer_ca = Data(2, name="xer_co") # bit0: ca, bit1: ca32
        self.xer_ov = Data(2, name="xer_ov") # bit0: ov, bit1: ov32
        self.xer_so = Data(1, name="xer_so")

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.xer_ca
        yield self.cr0
        yield self.xer_ov
        yield self.xer_so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.xer_ca.eq(i.xer_ca),
                      self.cr0.eq(i.cr0),
                      self.xer_ov.eq(i.xer_ov), self.xer_so.eq(i.xer_so)]


class IntPipeSpec:
    def __init__(self, id_wid=2, op_wid=1):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: CompALUOpSubset(name="op")
        self.stage = None


class ALUPipeSpec(IntPipeSpec):
    def __init__(self, id_wid, op_wid):
        super().__init__(id_wid, op_wid)
        self.pipekls = SimpleHandshakeRedir
