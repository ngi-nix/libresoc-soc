from nmutil.concurrentunit import PipeContext
from nmutil.dynamicpipe import SimpleHandshakeRedir
from nmigen import Signal
from openpower.decoder.power_decoder2 import Data
from soc.fu.regspec import get_regspec_bitwidth


class FUBaseData:
    """FUBaseData: base class for all pipeline data structures

    see README.md for explanation of parameters and purpose.

    note the mode parameter - output.  XXXInputData specs must
    have this set to "False", and XXXOutputData specs (and anything
    that creates intermediary outputs which propagate through a
    pipeline *to* output) must have it set to "True".
    """

    def __init__(self, pspec, output, exc_kls=None):
        self.ctx = PipeContext(pspec) # context for ReservationStation usage
        self.muxid = self.ctx.muxid
        self.data = []
        self.is_output = output
        # take regspec and create data attributes (in or out)
        # TODO: use widspec to create reduced bit mapping.
        for i, (regfile, regname, widspec) in enumerate(self.regspec):
            wid = get_regspec_bitwidth([self.regspec], 0, i)
            if output:
                sig = Data(wid, name=regname)
            else:
                sig = Signal(wid, name=regname, reset_less=True)
            setattr(self, regname, sig)
            self.data.append(sig)
        # optional exception type
        if exc_kls is not None:
            name = "exc_o" if output else "exc_i"
            self.exception = exc_kls(name=name)

    def __iter__(self):
        yield from self.ctx
        yield from self.data
        if hasattr(self, "exception"):
            yield from self.exception.ports()

    def eq(self, i):
        eqs = [self.ctx.eq(i.ctx)]
        assert len(self.data) == len(i.data), \
               "length of %s mismatch against %s: %s %s" % \
                   (repr(self), repr(i), repr(self.data), repr(i.data))
        for j in range(len(self.data)):
            assert type(self.data[j]) == type(i.data[j]), \
                   "type mismatch in FUBaseData %s %s" % \
                   (repr(self.data[j]), repr(i.data[j]))
            eqs.append(self.data[j].eq(i.data[j]))
        if hasattr(self, "exception"):
            eqs.append(self.exception.eq(i.exception))
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
    """CommonPipeSpec: base class for all pipeline specifications
    see README.md for explanation of members.
    """
    def __init__(self, id_wid):
        self.pipekls = SimpleHandshakeRedir
        self.id_wid = id_wid
        self.opkls = lambda _: self.opsubsetkls()
        self.op_wid = get_rec_width(self.opkls(None)) # hmm..
        self.stage = None
