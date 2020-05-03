from nmigen import Module, Signal, Elaboratable
from nmigen.lib.coding import Encoder, PriorityEncoder


class AddressEncoder(Elaboratable):
    """Address Encoder

       The purpose of this module is to take in a vector and
       encode the bits that are one hot into an address. This module
       combines both nmigen's Encoder and PriorityEncoder and will state
       whether the input line has a single bit hot, multiple bits hot,
       or no bits hot. The output line will always have the lowest value
       address output.

       Usage:
       The output is valid when either single or multiple match is high.
       Otherwise output is 0.
    """

    def __init__(self, width):
        """ Arguments:
            * width: The desired length of the input vector
        """
        # Internal
        self.encoder = Encoder(width)
        self.p_encoder = PriorityEncoder(width)

        # Input
        self.i = Signal(width)

        # Output
        self.single_match = Signal(1)
        self.multiple_match = Signal(1)
        self.o = Signal(range(width))

    def elaborate(self, platform=None):
        m = Module()

        # Add internal submodules
        m.submodules.encoder = self.encoder
        m.submodules.p_encoder = self.p_encoder

        m.d.comb += [
            self.encoder.i.eq(self.i),
            self.p_encoder.i.eq(self.i)
        ]

        # Steps:
        # 1. check if the input vector is non-zero
        # 2. if non-zero, check if single match or multiple match
        # 3. set output line to be lowest value address output

        # If the priority encoder recieves an input of 0
        # If n is 1 then the output is not valid
        with m.If(self.p_encoder.n):
            m.d.comb += [
                self.single_match.eq(0),
                self.multiple_match.eq(0),
                self.o.eq(0)
            ]
        # If the priority encoder recieves an input > 0
        with m.Else():
            # Multiple Match if encoder n is invalid
            with m.If(self.encoder.n):
                m.d.comb += [
                    self.single_match.eq(0),
                    self.multiple_match.eq(1)
                ]
            # Single Match if encoder n is valid
            with m.Else():
                m.d.comb += [
                    self.single_match.eq(1),
                    self.multiple_match.eq(0)
                ]
            # Always set output based on priority encoder output
            m.d.comb += self.o.eq(self.p_encoder.o)
        return m
