from nmigen import Elaboratable, Signal, Module, Repl, Cat, Const, Array
from nmigen.cli import main

class Bpermd(Elaboratable):
    """This class does a Bit Permute on a Doubleword

       X-form bpermd RA,RS,RB]

       Eight permuted bits are produced. For each permuted bit i where i ranges
       from 0 to 7 and for each byte i of RS, do the following. If byte i of RS
       is less than 64, permuted bit i is setto the bit of RB specified by byte
       i of RS; otherwise permuted bit i is set to 0. The  permuted  bits are
       placed in the least-significantbyte of RA, and the remaining bits are
       filled with 0s.
       Special Registers Altered: None

       Programming note:
       The fact that the permuted bit is 0 if the corresponding index value
       exceeds 63 permits the permuted bits to be selected from a 128-bit
       quantity, using a single index register. For example, assume that the
       128-bit quantity Q, from which the permuted bits are to be selected, is
       in registers r2(high-order 64 bits of Q) and r3 (low-order 64 bits of Q),
       that the index values are in register r1, with each byte of r1 containing
       a value in the range 0:127, and that each byte of register r4 contains
       the value 64. The following code sequence selects eight permuted bits
       from Q and places them into the low-order byte of r6.
    """

    def __init__(self, width):
        self.perm = Signal(width)
        self.rs   = Signal(width)
        self.ra   = Signal(width)
        self.rb   = Signal(width)

    def elaborate(self, platform):
        m = Module()
        index = Signal(8)
        signals = [ Signal(1) for i in range(64) ]
        for i,n in enumerate(signals):
            m.d.comb += n.eq(self.rb[i])
        rb64 = Array(signals)
        for i in range(0, 8):
            index = self.rs[8 * i:8 * i + 8]
            with m.If(index < 64):
                m.d.comb += self.perm[i].eq(rb64[index])
            with m.Else():
                continue
        m.d.comb += self.ra[0:8].eq(self.perm)
        return m

if __name__ == "__main__":
    bperm = Bpermd(width=64)
    main(bperm,ports=[bperm.perm, bperm.rs, bperm.ra, bperm.rb])
