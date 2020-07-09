"""Simple example of a FSM-based ALU

This demonstrates a design that follows the valid/ready protocol of the
ALU, but with a FSM implementation, instead of a pipeline.  It is also
intended to comply with both the CompALU API and the nmutil Pipeline API
(Liskov Substitution Principle)

The basic rules are:

1) p.ready_o is asserted on the initial ("Idle") state, otherwise it keeps low.
2) n.valid_o is asserted on the final ("Done") state, otherwise it keeps low.
3) The FSM stays in the Idle state while p.valid_i is low, otherwise
   it accepts the input data and moves on.
4) The FSM stays in the Done state while n.ready_i is low, otherwise
   it releases the output data and goes back to the Idle state.

"""

from nmigen import Elaboratable, Signal, Module
from nmigen.back.pysim import Simulator
from soc.fu.cr.cr_input_record import CompCROpSubset


class Dummy:
    pass


class Shifter(Elaboratable):
    """Simple sequential shifter

    Prev port data:
    * p.data_i.data:  Value to be shifted
    * p.data_i.shift: Shift amount
    * p.data_i.dir:   Shift direction

    Next port data:
    * n.data_o: Shifted value
    """
    class PrevData:
        def __init__(self, width):
            self.data = Signal(width, name="p_data_i")
            self.shift = Signal(width, name="p_shift_i")
            self.dir = Signal(name="p_dir_i")
            self.ctx = Dummy() # comply with CompALU API

        def _get_data(self):
            return [self.data, self.shift]

    class NextData:
        def __init__(self, width):
            self.data = Signal(width, name="n_data_o")

        def _get_data(self):
            return [self.data]

    class PrevPort:
        def __init__(self, width):
            self.data_i = Shifter.PrevData(width)
            self.valid_i = Signal(name="p_valid_i")
            self.ready_o = Signal(name="p_ready_o")

    class NextPort:
        def __init__(self, width):
            self.data_o = Shifter.NextData(width)
            self.valid_o = Signal(name="n_valid_o")
            self.ready_i = Signal(name="n_ready_i")

    def __init__(self, width):
        self.width = width
        self.p = self.PrevPort(width)
        self.n = self.NextPort(width)

        # more pieces to make this example class comply with the CompALU API
        self.op = CompCROpSubset()
        self.p.data_i.ctx.op = self.op
        self.i = self.p.data_i._get_data()
        self.out = self.n.data_o._get_data()

    def elaborate(self, platform):
        m = Module()
        # TODO: Implement Module
        return m

    def __iter__(self):
        yield self.p.data_i.data
        yield self.p.data_i.shift
        yield self.p.data_i.dir
        yield self.p.valid_i
        yield self.p.ready_o
        yield self.n.ready_i
        yield self.n.valid_o
        yield self.n.data_o.data

    def ports(self):
        return list(self)


def test_shifter():
    m = Module()
    m.submodules.shf = dut = Shifter(8)
    print("Shifter port names:")
    for port in dut:
        print("-", port.name)
    sim = Simulator(m)
    # Todo: Implement Simulation


if __name__ == "__main__":
    test_shifter()
