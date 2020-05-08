from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.alu.alu_input_record import CompALUOpSubset
from ieee754.fpcommon.getop import FPPipeContext


class IntegerData:

    def __init__(self, pspec):
        self.op = CompALUOpSubset()
        self.ctx = FPPipeContext(pspec)
        self.muxid = self.ctx.muxid

    def __iter__(self):
        yield from self.op
        yield from self.ctx

    def eq(self, i):
        return [self.op.eq(i.op), self.ctx.eq(i.ctx)]


class ALUInitialData(IntegerData):
    def __init__(self, pspec):
        super().__init__(pspec)
        self.a = Signal(64, reset_less=True)
        self.b = Signal(64, reset_less=True)

    def __iter__(self):
        yield from super().__iter__()
        yield self.a
        yield self.b

    def eq(self, i):
        lst = super().eq(i)
        return lst + [self.a.eq(i.a), self.b.eq(i.b)]

class IntPipeSpec:
    def __init__(self, id_wid=2, op_wid=1):
        self.id_wid = id_wid
        self.op_wid = op_wid
        self.opkls = CompALUOpSubset

class ALUPipeSpec(IntPipeSpec):
    def __init__(self, id_wid, op_wid):
        super().__init__(id_wid, op_wid)
        self.pipekls = SimpleHandshakeRedir
