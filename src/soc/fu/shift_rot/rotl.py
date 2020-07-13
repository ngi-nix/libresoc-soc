from nmigen import (Elaboratable, Signal, Module, Cat)
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
        # trick to do double-concatenation of a then left shift.
        # synth tools know to turn this pattern into a barrel-shifter
        comb += self.o.eq(Cat(self.a, self.a).bit_select(self.width - self.b,
                                                         len(self.a)))
        return m
