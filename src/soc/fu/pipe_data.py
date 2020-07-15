from nmutil.concurrentunit import PipeContext
from nmutil.dynamicpipe import SimpleHandshakeRedir
from nmigen import Signal
from soc.decoder.power_decoder2 import Data
from soc.fu.regspec import get_regspec_bitwidth


class IntegerData:

    def __init__(self, pspec, output):
        self.ctx = PipeContext(pspec) # context for ReservationStation usage
        self.muxid = self.ctx.muxid
        self.data = []
        self.is_output = output
        for i, (regfile, regname, widspec) in enumerate(self.regspec):
            wid = get_regspec_bitwidth([self.regspec], 0, i)
            if output:
                sig = Data(wid, name=regname)
            else:
                sig = Signal(wid, name=regname, reset_less=True)
            setattr(self, regname, sig)
            self.data.append(sig)

    def __iter__(self):
        yield from self.ctx
        yield from self.data

    def eq(self, i):
        eqs = [self.ctx.eq(i.ctx)]
        assert len(self.data) == len(i.data), \
               "length of %s mismatch against %s: %s %s" % \
                   (repr(self), repr(i), repr(self.data), repr(i.data))
        for j in range(len(self.data)):
            assert type(self.data[j]) == type(i.data[j]), \
                   "type mismatch in IntegerData %s %s" % \
                   (repr(self.data[j]), repr(i.data[j]))
            eqs.append(self.data[j].eq(i.data[j]))
        return eqs

    def ports(self):
        return self.ctx.ports() # TODO: include self.data


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
