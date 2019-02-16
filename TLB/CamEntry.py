from nmigen import Module, Signal
from nmigen.cli import main

class CamEntry():
    def __init__(self, key_size, data_size):
        # Internal
        key = Signal(key_size)
        
        # Input
        self.write = Signal(1) # Read => 0 Write => 1
        self.key_in = Signal(key_size) # Reference key for the CAM
        self.data_in = Signal(data_size) # Data input when writing
        
        # Output
        self.match = Signal(1) # Result of the internal/input key comparison
        self.data = Signal(data_size)
        
        
    def elabotate(self, platform):
        m = Module()
        m.d.comb += [
            If(self.write == 1,
               key.eq(self.key_in),
               self.data.eq(self.data_in)
            ).Else(
                If(self.key_in == key,
                   self.match.eq(0)
                ).Else(
                    self.match.eq(1)
                )
            )
        ]
        return m