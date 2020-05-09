from nmigen import (Elaboratable, Signal, Module)
import math

class ROTL(Elaboratable):
    def __init__(self, width):
        self.width = width
        self.shiftwidth = math.ceil(math.log2(width))
        self.a = Signal(width, reset_less=True)
        self.b = Signal(self.shiftwidth, reset_less=True)

        self.o = Signal(width, reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        shl = Signal.like(self.a)
        shr = Signal.like(self.a)

        comb += shl.eq(self.a << self.b)
        comb += shr.eq(self.a >> (self.width - self.b))

        comb += self.o.eq(shl | shr)
        return m
