"""SVP64 Prefix Decoder 

"""

from nmigen import Module, Elaboratable, Signal, Mux, Const, Cat
from nmigen.cli import rtlil
from nmutil.util import sel

from soc.consts import SVP64P

# SVP64 Prefix fields: see https://libre-soc.org/openpower/sv/svp64/
# identifies if an instruction is a SVP64-encoded prefix, and extracts
# the 24-bit SVP64 context (RM) if it is
class SVP64PrefixDecoder(Elaboratable):

    def __init__(self):
        self.opcode_in = Signal(32, reset_less=True)
        self.raw_opcode_in = Signal.like(self.opcode_in, reset_less=True)
        self.is_svp64_mode = Signal(1, reset_less=True)
        self.svp64_rm = Signal(24, reset_less=True)
        self.bigendian = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        opcode_in = self.opcode_in
        comb = m.d.comb
        # sigh copied this from TopPowerDecoder
        # raw opcode in assumed to be in LE order: byte-reverse it to get BE
        raw_le = self.raw_opcode_in
        l = []
        for i in range(0, 32, 8):
            l.append(raw_le[i:i+8])
        l.reverse()
        raw_be = Cat(*l)
        comb += opcode_in.eq(Mux(self.bigendian, raw_be, raw_le))

        # start identifying if the incoming opcode is SVP64 prefix)
        major = sel(m, opcode_in, SVP64P.OPC)
        ident = sel(m, opcode_in, SVP64P.SVP64_7_9)

        comb += self.is_svp64_mode.eq(
            (major == Const(1, 6)) &   # EXT01
            (ident == Const(0b11, 2))  # identifier bits
        )

        with m.If(self.is_svp64_mode):
            # now grab the 24-bit ReMap context bits,
            rm = sel(m, opcode_in, SVP64P.RM)
            comb += self.svp64_rm.eq(rm)

        return m

    def ports(self):
        return [self.opcode_in, self.raw_opcode_in, self.is_svp64_mode,
                self.svp64_rm, self.bigendian]


if __name__ == '__main__':
    svp64 = SVP64PrefixDecoder()
    vl = rtlil.convert(svp64, ports=svp64.ports())
    with open("svp64_prefix_dec.il", "w") as f:
        f.write(vl)
