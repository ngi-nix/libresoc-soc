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

from nmigen import Elaboratable, Signal, Module, Cat
from nmigen.back.pysim import Simulator
from nmigen.cli import rtlil
from soc.fu.cr.cr_input_record import CompCROpSubset


class Dummy:
    pass


class Shifter(Elaboratable):
    """Simple sequential shifter

    Prev port data:
    * p.data_i.data:  value to be shifted
    * p.data_i.shift: shift amount
    *                 When zero, no shift occurs.
    *                 On POWER, range is 0 to 63 for 32-bit,
    *                 and 0 to 127 for 64-bit.
    *                 Other values wrap around.
    * p.data_i.dir:   shift direction (0 = left, 1 = right)

    Next port data:
    * n.data_o.data: shifted value
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

        # Note:
        # It is good practice to design a sequential circuit as
        # a data path and a control path.

        # Data path
        # ---------
        # The idea is to have a register that can be
        # loaded or shifted (left and right).

        # the control signals
        load = Signal()
        shift = Signal()
        # the data flow
        shift_in = Signal(self.width)
        shift_left_by_1 = Signal(self.width)
        shift_right_by_1 = Signal(self.width)
        next_shift = Signal(self.width)
        # the register
        shift_reg = Signal(self.width, reset_less=True)
        # build the data flow
        m.d.comb += [
            # connect input and output
            shift_in.eq(self.p.data_i.data),
            self.n.data_o.data.eq(shift_reg),
            # generate shifted views of the register
            shift_left_by_1.eq(Cat(0, shift_reg[:-1])),
            shift_right_by_1.eq(Cat(shift_reg[1:], 0)),
        ]
        # choose the next value of the register according to the
        # control signals
        # default is no change
        m.d.comb += next_shift.eq(shift_reg)
        with m.If(load):
            m.d.comb += next_shift.eq(shift_in)
        with m.Elif(shift):
            with m.If(self.p.data_i.dir):
                m.d.comb += next_shift.eq(shift_right_by_1)
            with m.Else():
                m.d.comb += next_shift.eq(shift_left_by_1)

        # register the next value
        m.d.sync += shift_reg.eq(next_shift)

        # TODO: Implement the control path

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
    # generate RTLIL
    # try "proc; show" in yosys to check the data path
    il = rtlil.convert(dut, ports=dut.ports())
    with open("test_shifter.il", "w") as f:
        f.write(il)
    sim = Simulator(m)
    # Todo: Implement Simulation


if __name__ == "__main__":
    test_shifter()
