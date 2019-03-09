from nmigen import Array, Module, Signal
from nmigen.cli import main 

class VectorAssembler():
    def __init__(self, width):
        # Internal
        self.width = width
        
        # Input
        self.input = Array(Signal(1) for index in range(width))
        
        # Output
        self.o = Signal(width)
        
    def elaborate(self, platform=None):
        m = Module()
        for index in range(self.width):
            m.d.comb += self.o[index].eq(self.input[index])
            
        return m