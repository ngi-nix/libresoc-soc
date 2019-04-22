from nmigen import Module, Signal
from nmigen.cli import main

size = 11

class LFSR:
    def __init__(self):

        # Output
        self.enable = Signal(1)
        self.o = Signal(size)

    def elaborate(self, platform=None):
        m = Module()

        for i in range(size):
            with m.If(self.enable):
                if i == 0:
                    zero = self.o[0]
                    one = self.o[1]
                    m.d.sync += self.o[0].eq(zero ^ one)
                if i == 3:
                    zero = self.o[0]
                    three = self.o[4]
                    m.d.sync += self.o[3].eq(zero ^ three)
                else:
                    prev = self.o[(i + 1) % size]
                    m.d.sync += self.o[i].eq(prev)
        return m

