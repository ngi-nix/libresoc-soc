from nmigen import Array, Module, Signal
from nmigen.lib.coding import PriorityEncoder, Decoder

class WalkingPriorityEncoder():

    def __init__(self, width):
        # Internal
        self.current = Signal(width)
        self.encoder = PriorityEncoder(width)

        # Input
        self.write = Signal(1)
        self.input = Signal(width)

        # Output
        self.match = Signal(1)
        self.output = Signal(width)

    def elaborate(self, platform=None):
        m = Module()

        m.submodules += self.encoder

        with m.If(self.write == 0):
            with m.If(self.encoder.n == 0):
                m.d.sync += [
                    self.output.eq(self.encoder.o),
                    self.match.eq(1)
                ]
                m.d.sync += self.current.eq(self.current ^ \
                                            (1 << self.encoder.o))
                m.d.sync += self.encoder.i.eq(self.current ^ \
                                              (1 << self.encoder.o))

            with m.Else():
                m.d.sync += self.match.eq(0)
                m.d.sync += self.encoder.i.eq(0)

        with m.Else():
            m.d.sync += self.encoder.i.eq(self.input)
            m.d.sync += self.current.eq(self.input)
            m.d.sync += self.encoder.i.eq(self.input)
            m.d.sync += self.match.eq(0)

        return m
