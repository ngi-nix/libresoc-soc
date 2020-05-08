from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.alu.alu_input_record import CompALUOpSubset
from ieee754.fpcommon.getop import FPPipeContext


class IntegerData:

    def __init__(self, pspec):
        self.ctx = FPPipeContext(pspec)
        self.muxid = self.ctx.muxid

    def __iter__(self):
        yield from self.op
        yield from self.ctx

    def eq(self, i):
        return [self.op.eq(i.op), self.ctx.eq(i.ctx)]


class ALUInputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True)
        self.b = Signal(64, reset_less=True)
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


class ALUOutputData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.o = Signal(64, reset_less=True)
        self.carry_out = Signal(reset_less=True)
        self.carry_out32 = Signal(reset_less=True)
        self.cr0 = Signal(4, reset_less=True)
        self.ov = Signal(reset_less=True)
        self.ov32 = Signal(reset_less=True)
        self.so = Signal(reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.o
        yield self.carry_out
        yield self.carry_out32
        yield self.cr0
        yield self.ov
        yield self.ov32
        yield self.so

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.o.eq(i.o),
                      self.carry_out.eq(i.carry_out),
                      self.carry_out32.eq(i.carry_out32),
                      self.cr0.eq(i.cr0), self.ov.eq(i.ov),
                      self.ov32.eq(i.ov32), self.so.eq(i.so)]

class IntPipeSpec:
    def __init__(self, id_wid=2, op_wid=1):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = lambda _: CompALUOpSubset(name="op")

class ALUPipeSpec(IntPipeSpec):
    def __init__(self, id_wid, op_wid):
        super().__init__(id_wid, op_wid)
        self.pipekls = SimpleHandshakeRedir
