from nmigen import Elaboratable, Signal, Module, Repl, Cat, Const, Array
from nmigen.cli import main


class Bpermd(Elaboratable):
    """
    from POWERISA v3.1 p105, chaper 3

    This class does a Bit Permute on a Doubleword

    permd      RA,RS,RB

    do i = 0 to 7
        index ← (RS)[8*i:8*i+7]
        If index < 64
            then perm[i]  ← (RB)[index]
            else permi[i] ← 0
    RA ←56[0] || perm[0:7]

    Eight permuted bits are produced.  For each permutedbit i where i
    ranges from 0 to 7 and for each byte i of RS, do the following.

        If byte i of RS is less than 64, permuted bit i is set to
        the bit of RB specified by byte i of RS; otherwise
        permuted bit i is set to 0.

    The permuted bits are placed in the least-significant byte of RA,
    and the remaining bits are filled with 0s.

    Special Registers Altered:
        None

    Programming Note:

    The fact that the permuted bit is 0 if the corresponding index value
    exceeds 63 permits the permuted bits to be selected from a 128-bit
    quantity, using a single index register. For example, assume that
    the 128-bit quantity Q, from which the permuted bits are to be
    selected, is in registers r2 (high-order 64 bits of Q) and r3
    (low-order 64 bits of Q), that the index values are in register r1,
    with each byte of r1 containing a value in the range 0:127, and that
    each byte of register r4 contains the value 64. The following code
    sequence selects eight permuted bits from Q and places them into
    the low-order byteof r6.

    bpermd  r6,r1,r2 # select from high-order half of Q
    xor     r0,r1,r4 # adjust index values
    bpermd  r5,r0,r3 # select from low-order half of Q
    or      r6,r6,r5  # merge the two selections
   """

    def __init__(self, width):
        self.width = width
        self.rs = Signal(width, reset_less=True)
        self.ra = Signal(width, reset_less=True)
        self.rb = Signal(width, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        perm = Signal(self.width, reset_less=True)
        rb64 = [Signal(1, reset_less=True, name=f"rb64_{i}") for i in range(64)]
        for i in range(64):
            m.d.comb += rb64[i].eq(self.rb[63-i])
        rb64 = Array(rb64)
        for i in range(8):
            index = self.rs[8*i:8*i+8]
            idx = Signal(8, name=f"idx_{i}", reset_less=True)
            m.d.comb += idx.eq(index)
            with m.If(idx < 64):
                m.d.comb += perm[i].eq(rb64[idx])
        m.d.comb += self.ra[0:8].eq(perm)
        return m


if __name__ == "__main__":
    bperm = Bpermd(width=64)
    main(bperm, ports=[bperm.rs, bperm.ra, bperm.rb])
