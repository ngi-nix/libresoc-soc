from nmigen import (Elaboratable, Signal, Module)
import math

class MaskGen(Elaboratable):
    def __init__(self, width):
        self.width = width
        self.shiftwidth = math.ceil(math.log2(width))
        self.mb = Signal(self.shiftwidth, reset_less=True)
        self.me = Signal(self.shiftwidth, reset_less=True)

        self.o = Signal(width, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        x = Signal.like(self.mb)
        y = Signal.like(self.mb)

        comb += x.eq(64 - self.mb)
        comb += y.eq(63 - self.me)

        mask_a = Signal.like(self.o)
        mask_b = Signal.like(self.o)

        comb += mask_a.eq((1<<x) - 1)
        comb += mask_b.eq((1<<y) - 1)

        with m.If(x > y):
            comb += self.o.eq(mask_a ^ mask_b)
        with m.Else():
            comb += self.o.eq(mask_a ^ ~mask_b)
            

        return m

    def ports(self):
        return [self.mb, self.me, self.o]
