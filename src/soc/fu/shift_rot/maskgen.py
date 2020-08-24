from nmigen import (Elaboratable, Signal, Module)
import math
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

class MaskGen(Elaboratable):
    """MaskGen - create a diff mask

    example: x=5 --> a=0b11111
             y=3 --> b=0b00111
             o:        0b11000
             x=2 --> a=0b00011
             y=4 --> b=0b01111
             o:        0b10011
    """
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
