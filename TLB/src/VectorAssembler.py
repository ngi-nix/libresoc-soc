from nmigen import Array, Module, Signal
from nmigen.cli import main 

class VectorAssembler():
    """ Vector Assembler

        The purpose of this module is to take a generic number of inputs
        and cleanly combine them into one vector. While this is very much
        possible through raw code it may result in a very unfortunate sight
        in a yosys graph. Thus this class was born! No more will ugly loops
        exist in my graphs! Get outta here ya goddam Lochness Monster.
    """
    def __init__(self, width):
        """ Arguments:
            * width: (bit count) The desiered size of the output vector

        """
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
