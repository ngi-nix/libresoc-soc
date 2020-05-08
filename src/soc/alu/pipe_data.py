from nmigen import Signal, Const
from nmutil.dynamicpipe import SimpleHandshakeRedir
from soc.alu.alu_input_record import CompALUOpSubset


class ALUInitialData:

    def __init__(self, pspec):
        self.op = CompALUOpSubset()
        self.a = Signal(64, reset_less=True)
        self.b = Signal(64, reset_less=True)

    def __iter__(self):
        yield from self.op
        yield self.a
        yield self.b

    def eq(self, i):
        return [self.op.eq(i.op),
                self.a.eq(i.a), self.b.eq(i.b)]




class ALUPipeSpec:
    def __init__(self):
        self.pipekls = SimpleHandshakeRedir
