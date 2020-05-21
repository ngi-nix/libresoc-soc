from ieee754.fpcommon.getop import FPPipeContext
from nmutil.dynamicpipe import SimpleHandshakeRedir


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

# hmmm there has to be a better way than this
def get_rec_width(rec):
    recwidth = 0
    # Setup random inputs for dut.op
    for p in rec.ports():
        width = p.width
        recwidth += width
    return recwidth


class CommonPipeSpec:
    def __init__(self, id_wid):
        self.pipekls = SimpleHandshakeRedir
        self.id_wid = id_wid
        self.opkls = lambda _: self.opsubsetkls(name="op")
        self.op_wid = get_rec_width(self.opkls(None)) # hmm..
        self.stage = None
