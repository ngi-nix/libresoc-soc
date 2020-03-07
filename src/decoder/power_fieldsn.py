from collections import OrderedDict
from power_fields import DecodeFields, BitRange
from nmigen import Module, Elaboratable, Signal, Cat
from nmigen.cli import rtlil

class SignalBitRange(BitRange):
    def __init__(self, signal):
        BitRange.__init__(self)
        self.signal = signal

    def __getitem__(self, subs):
        # *sigh* field numberings are bit-inverted.  PowerISA 3.0B section 1.3.2
        width = self.signal.shape()[0]
        print (dir(self))
        print (self.items())
        if isinstance(subs, slice):
            res = []
            print (subs)
            start, stop, step = subs.start, subs.stop, subs.step
            if step is None:
                step = 1
            if start is None:
                start = 0
            if stop is None:
                stop = -1
            if start < 0:
                start = len(self) - start - 1
            if stop < 0:
                stop = len(self) - stop - 1
            print ("range", start, stop, step)
            for t in range(start, stop, step):
                k = OrderedDict.__getitem__(self, t)
                print ("t", t, k)
                res.append(self.signal[width-k-1])
            return Cat(*res)
        else:
            k = OrderedDict.__getitem__(self, subs)
            return self.signal[width-k-1]

        print ("translated", subs, translated)


class SigDecode(Elaboratable):

    def __init__(self, width):
        self.opcode_in = Signal(width, reset_less=False)
        self.df = DecodeFields(SignalBitRange, [self.opcode_in])
        self.df.create_specs()
        self.x_s = Signal(len(self.df.FormX.S), reset_less=True)
        self.x_sh = Signal(len(self.df.FormX.SH), reset_less=True)
        self.dq_xs_s = Signal(len(self.df.FormDQ.SX_S), reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        comb += self.x_s.eq(self.df.FormX.S[0])
        comb += self.x_sh.eq(self.df.FormX.SH[0:-1])
        comb += self.dq_xs_s.eq(self.df.FormDQ.SX_S[0:-1])
        return m

    def ports(self):
        return [self.opcode_in, self.x_s, self.x_sh]

def create_sigdecode():
    s = SigDecode(32)
    return s

if __name__ == '__main__':
    sigdecode = create_sigdecode()
    vl = rtlil.convert(sigdecode, ports=sigdecode.ports())
    with open("decoder.il", "w") as f:
        f.write(vl)

