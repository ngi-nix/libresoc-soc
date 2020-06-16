"""Popcount: a successive (cascading) sum-reduction algorithm for counting bits

starting from single-bit adds and reducing down to one final answer:
the total number of bits set to "1" in the input.

unfortunately there is a bit of a "trick" going on which you have to
watch out for: whilst the first list added to pc is a single entry (the
input, a), subsequent rows in the cascade are arrays of partial results,
yet it turns out that referring to them using the exact same start/end
slicing is perfect.  this comes down to nmigen's transparent use of
python features to make Signals iterable.
"""

from nmigen import (Elaboratable, Module, Signal, Cat, Const)


def array_of(count, bitwidth):
    res = []
    for i in range(count):
        res.append(Signal(bitwidth, reset_less=True,
                          name=f"pop_{bitwidth}_{i}"))
    return res


class Popcount(Elaboratable):
    def __init__(self):
        self.a = Signal(64, reset_less=True)
        self.b = Signal(64, reset_less=True)
        self.data_len = Signal(64, reset_less=True)
        self.o = Signal(64, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        a, b, data_len, o = self.a, self.b, self.data_len, self.o

        # starting from a, perform successive addition-reductions
        # creating arrays big enough to store the sum, each time
        pc = [a]
        # QTY32 2-bit (to take 2x 1-bit sums) etc.
        work = [(32, 2), (16, 3), (8, 4), (4, 5), (2, 6), (1, 7)]
        for l, bw in work: # l=number of add-reductions, bw=bitwidth
            pc.append(array_of(l, bw))
        pc8 = pc[3]     # array of 8 8-bit counts (popcntb)
        pc32 = pc[5]    # array of 2 32-bit counts (popcntw)
        popcnt = pc[-1]  # array of 1 64-bit count (popcntd)
        # cascade-tree of adds
        for idx, (l, bw) in enumerate(work):
            for i in range(l):
                stt, end = i*2, i*2+1
                src, dst = pc[idx], pc[idx+1]
                comb += dst[i].eq(Cat(src[stt], Const(0, 1)) +
                                  Cat(src[end], Const(0, 1)))
        # decode operation length (1-hot)
        with m.If(data_len == 1):
            # popcntb - pack 8x 4-bit answers into 8x 8-bit output fields
            for i in range(8):
                comb += o[i*8:(i+1)*8].eq(pc8[i])
        with m.Elif(data_len == 4):
            # popcntw - pack 2x 5-bit answers into 2x 32-bit output fields
            for i in range(2):
                comb += o[i*32:(i+1)*32].eq(pc32[i])
        with m.Else():
            # popcntd - put 1x 6-bit answer into 64-bit output
            comb += o.eq(popcnt[0])

        return m
