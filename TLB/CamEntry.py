from nmigen import Module, Signal

class CamEntry:
    def __init__(self, key_size, data_size):
        # Internal
        self.key = Signal(key_size)
        
        # Input
        self.write = Signal(1) # Read => 0 Write => 1
        self.key_in = Signal(key_size) # Reference key for the CAM
        self.data_in = Signal(data_size) # Data input when writing
        
        # Output
        self.match = Signal(1) # Result of the internal/input key comparison
        self.data = Signal(data_size)
        
        
    def get_fragment(self, platform=None):
        m = Module()
        with m.If(self.write == 1):
            m.d.sync += [
                self.key.eq(self.key_in),
                self.data.eq(self.data_in),
                self.match.eq(1)
            ]
        with m.Else():
            with m.If(self.key_in == self.key):
                m.d.sync += self.match.eq(0)
            with m.Else():
                m.d.sync += self.match.eq(1)
        
        return m
