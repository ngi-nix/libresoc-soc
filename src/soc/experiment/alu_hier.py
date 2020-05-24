"""*Experimental* ALU: based on nmigen alu_hier.py, includes branch-compare ALU

This ALU is *deliberately* designed to add in (unnecessary) delays into
different operations so as to be able to test the 6600-style matrices
and the CompUnits.  Countdown timers wait for (defined) periods before
indicating that the output is valid

A "real" integer ALU would place the answers onto the output bus after
only one cycle (sync)
"""

from nmigen import Elaboratable, Signal, Module, Const, Mux, Array
from nmigen.hdl.rec import Record, Layout
from nmigen.cli import main
from nmigen.cli import verilog, rtlil
from nmigen.compat.sim import run_simulation

from soc.decoder.power_enums import InternalOp, Function, CryIn

from soc.fu.alu.alu_input_record import CompALUOpSubset
from soc.fu.cr.cr_input_record import CompCROpSubset

import operator




class Adder(Elaboratable):
    def __init__(self, width):
        self.invert_a = Signal()
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)

    def elaborate(self, platform):
        m = Module()
        with m.If(self.invert_a):
            m.d.comb += self.o.eq((~self.a) + self.b)
        with m.Else():
            m.d.comb += self.o.eq(self.a + self.b)
        return m


class Subtractor(Elaboratable):
    def __init__(self, width):
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.eq(self.a - self.b)
        return m


class Multiplier(Elaboratable):
    def __init__(self, width):
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.eq(self.a * self.b)
        return m


class Shifter(Elaboratable):
    def __init__(self, width):
        self.width = width
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)

    def elaborate(self, platform):
        m = Module()
        btrunc = Signal(self.width)
        m.d.comb += btrunc.eq(self.b & Const((1<<self.width)-1))
        m.d.comb += self.o.eq(self.a >> btrunc)
        return m

class Dummy:
    pass

class DummyALU(Elaboratable):
    def __init__(self, width):
        self.p = Dummy() # make look like nmutil pipeline API
        self.p.data_i = Dummy()
        self.p.data_i.ctx = Dummy()
        self.n = Dummy() # make look like nmutil pipeline API
        self.n.data_o = Dummy()
        self.p.valid_i = Signal()
        self.p.ready_o = Signal()
        self.n.ready_i = Signal()
        self.n.valid_o = Signal()
        self.counter   = Signal(4)
        self.op  = CompCROpSubset()
        i = []
        i.append(Signal(width, name="i1"))
        i.append(Signal(width, name="i2"))
        self.i = Array(i)
        self.a, self.b = i[0], i[1]
        self.out = Array([Signal(width)])
        self.o = self.out[0]
        self.width = width
        # more "look like nmutil pipeline API"
        self.p.data_i.ctx.op = self.op
        self.p.data_i.a = self.a
        self.p.data_i.b = self.b
        self.n.data_o.o = self.o

    def elaborate(self, platform):
        m = Module()

        go_now = Signal(reset_less=True) # testing no-delay ALU

        with m.If(self.p.valid_i):
            # input is valid. next check, if we already said "ready" or not
            with m.If(~self.p.ready_o):
                # we didn't say "ready" yet, so say so and initialise
                m.d.sync += self.p.ready_o.eq(1)

                m.d.sync += self.o.eq(self.i.a)
                m.d.comb += go_now.eq(1)
                m.d.sync += self.counter.eq(1)

        with m.Else():
            # input says no longer valid, so drop ready as well.
            # a "proper" ALU would have had to sync in the opcode and a/b ops
            m.d.sync += self.p.ready_o.eq(0)

        # ok so the counter's running: when it gets to 1, fire the output
        with m.If((self.counter == 1) | go_now):
            # set the output as valid if the recipient is ready for it
            m.d.sync += self.n.valid_o.eq(1)
        with m.If(self.n.ready_i & self.n.valid_o):
            m.d.sync += self.n.valid_o.eq(0)
            # recipient said it was ready: reset back to known-good.
            m.d.sync += self.counter.eq(0) # reset the counter
            m.d.sync += self.o.eq(0) # clear the output for tidiness sake

        # countdown to 1 (transition from 1 to 0 only on acknowledgement)
        with m.If(self.counter > 1):
            m.d.sync += self.counter.eq(self.counter - 1)

        return m

    def __iter__(self):
        yield from self.op.ports()
        yield self.a
        yield self.b
        yield self.o

    def ports(self):
        return list(self)


class ALU(Elaboratable):
    def __init__(self, width):
        self.p = Dummy() # make look like nmutil pipeline API
        self.p.data_i = Dummy()
        self.p.data_i.ctx = Dummy()
        self.n = Dummy() # make look like nmutil pipeline API
        self.n.data_o = Dummy()
        self.p.valid_i = Signal()
        self.p.ready_o = Signal()
        self.n.ready_i = Signal()
        self.n.valid_o = Signal()
        self.counter   = Signal(4)
        self.op  = CompALUOpSubset()
        i = []
        i.append(Signal(width, name="i1"))
        i.append(Signal(width, name="i2"))
        self.i = Array(i)
        self.a, self.b = i[0], i[1]
        self.out = Array([Signal(width)])
        self.o = self.out[0]
        self.width = width
        # more "look like nmutil pipeline API"
        self.p.data_i.ctx.op = self.op
        self.p.data_i.a = self.a
        self.p.data_i.b = self.b
        self.n.data_o.o = self.o

    def elaborate(self, platform):
        m = Module()
        add = Adder(self.width)
        mul = Multiplier(self.width)
        shf = Shifter(self.width)

        m.submodules.add = add
        m.submodules.mul = mul
        m.submodules.shf = shf

        # really should not activate absolutely all ALU inputs like this
        for mod in [add, mul, shf]:
            m.d.comb += [
                mod.a.eq(self.a),
                mod.b.eq(self.b),
            ]

        # pass invert (and carry later)
        m.d.comb += add.invert_a.eq(self.op.invert_a)

        go_now = Signal(reset_less=True) # testing no-delay ALU

        with m.If(self.p.valid_i):
            # input is valid. next check, if we already said "ready" or not
            with m.If(~self.p.ready_o):
                # we didn't say "ready" yet, so say so and initialise
                m.d.sync += self.p.ready_o.eq(1)

                # as this is a "fake" pipeline, just grab the output right now
                with m.If(self.op.insn_type == InternalOp.OP_ADD):
                    m.d.sync += self.o.eq(add.o)
                with m.Elif(self.op.insn_type == InternalOp.OP_MUL_L64):
                    m.d.sync += self.o.eq(mul.o)
                with m.Elif(self.op.insn_type == InternalOp.OP_SHR):
                    m.d.sync += self.o.eq(shf.o)
                # TODO: SUB

                # NOTE: all of these are fake, just something to test

                # MUL, to take 5 instructions
                with m.If(self.op.insn_type == InternalOp.OP_MUL_L64):
                    m.d.sync += self.counter.eq(5)
                # SHIFT to take 7
                with m.Elif(self.op.insn_type == InternalOp.OP_SHR):
                    m.d.sync += self.counter.eq(7)
                # ADD/SUB to take 2, straight away
                with m.If(self.op.insn_type == InternalOp.OP_ADD):
                    m.d.sync += self.counter.eq(3)
                # others to take 1, straight away
                with m.Else():
                    m.d.comb += go_now.eq(1)
                    m.d.sync += self.counter.eq(1)

        with m.Else():
            # input says no longer valid, so drop ready as well.
            # a "proper" ALU would have had to sync in the opcode and a/b ops
            m.d.sync += self.p.ready_o.eq(0)

        # ok so the counter's running: when it gets to 1, fire the output
        with m.If((self.counter == 1) | go_now):
            # set the output as valid if the recipient is ready for it
            m.d.sync += self.n.valid_o.eq(1)
        with m.If(self.n.ready_i & self.n.valid_o):
            m.d.sync += self.n.valid_o.eq(0)
            # recipient said it was ready: reset back to known-good.
            m.d.sync += self.counter.eq(0) # reset the counter
            m.d.sync += self.o.eq(0) # clear the output for tidiness sake

        # countdown to 1 (transition from 1 to 0 only on acknowledgement)
        with m.If(self.counter > 1):
            m.d.sync += self.counter.eq(self.counter - 1)

        return m

    def __iter__(self):
        yield from self.op.ports()
        yield self.a
        yield self.b
        yield self.o

    def ports(self):
        return list(self)


class BranchOp(Elaboratable):
    def __init__(self, width, op):
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)
        self.op = op

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.o.eq(Mux(self.op(self.a, self.b), 1, 0))
        return m


class BranchALU(Elaboratable):
    def __init__(self, width):
        self.p.valid_i = Signal()
        self.p.ready_o = Signal()
        self.n.ready_i = Signal()
        self.n.valid_o = Signal()
        self.counter   = Signal(4)
        self.op  = Signal(2)
        i = []
        i.append(Signal(width, name="i1"))
        i.append(Signal(width, name="i2"))
        self.i = Array(i)
        self.a, self.b = i[0], i[1]
        self.out = Array([Signal(width)])
        self.o = self.out[0]
        self.width = width

    def elaborate(self, platform):
        m = Module()
        bgt = BranchOp(self.width, operator.gt)
        blt = BranchOp(self.width, operator.lt)
        beq = BranchOp(self.width, operator.eq)
        bne = BranchOp(self.width, operator.ne)

        m.submodules.bgt = bgt
        m.submodules.blt = blt
        m.submodules.beq = beq
        m.submodules.bne = bne
        for mod in [bgt, blt, beq, bne]:
            m.d.comb += [
                mod.a.eq(self.a),
                mod.b.eq(self.b),
            ]

        go_now = Signal(reset_less=True) # testing no-delay ALU
        with m.If(self.p.valid_i):
            # input is valid. next check, if we already said "ready" or not
            with m.If(~self.p.ready_o):
                # we didn't say "ready" yet, so say so and initialise
                m.d.sync += self.p.ready_o.eq(1)

                # as this is a "fake" pipeline, just grab the output right now
                with m.Switch(self.op):
                    for i, mod in enumerate([bgt, blt, beq, bne]):
                        with m.Case(i):
                            m.d.sync += self.o.eq(mod.o)
                m.d.sync += self.counter.eq(5) # branch to take 5 cycles (fake)
                #m.d.comb += go_now.eq(1)
        with m.Else():
            # input says no longer valid, so drop ready as well.
            # a "proper" ALU would have had to sync in the opcode and a/b ops
            m.d.sync += self.p.ready_o.eq(0)

        # ok so the counter's running: when it gets to 1, fire the output
        with m.If((self.counter == 1) | go_now):
            # set the output as valid if the recipient is ready for it
            m.d.sync += self.n.valid_o.eq(1)
        with m.If(self.n.ready_i & self.n.valid_o):
            m.d.sync += self.n.valid_o.eq(0)
            # recipient said it was ready: reset back to known-good.
            m.d.sync += self.counter.eq(0) # reset the counter
            m.d.sync += self.o.eq(0) # clear the output for tidiness sake

        # countdown to 1 (transition from 1 to 0 only on acknowledgement)
        with m.If(self.counter > 1):
            m.d.sync += self.counter.eq(self.counter - 1)

        return m

    def __iter__(self):
        yield self.op
        yield self.a
        yield self.b
        yield self.o

    def ports(self):
        return list(self)

def run_op(dut, a, b, op, inv_a=0):
    yield dut.a.eq(a)
    yield dut.b.eq(b)
    yield dut.op.insn_type.eq(op)
    yield dut.op.invert_a.eq(inv_a)
    yield dut.n.ready_i.eq(0)
    yield dut.p.valid_i.eq(1)
    yield
    while True:
        yield
        dut.n.valid_o = yield dut.n.valid_o
        if dut.n.valid_o:
            break
    yield

    result = yield dut.o
    yield dut.p.valid_i.eq(0)
    yield dut.n.ready_i.eq(0)
    yield

    return result


def alu_sim(dut):
    result = yield from run_op(dut, 5, 3, InternalOp.OP_ADD)
    print ("alu_sim add", result)
    assert (result == 8)

    result = yield from run_op(dut, 2, 3, InternalOp.OP_MUL_L64)
    print ("alu_sim mul", result)
    assert (result == 6)

    result = yield from run_op(dut, 5, 3, InternalOp.OP_ADD, inv_a=1)
    print ("alu_sim add-inv", result)
    assert (result == 65533)


def test_alu():
    alu = ALU(width=16)
    run_simulation(alu, alu_sim(alu), vcd_name='test_alusim.vcd')

    vl = rtlil.convert(alu, ports=alu.ports())
    with open("test_alu.il", "w") as f:
        f.write(vl)


if __name__ == "__main__":
    test_alu()

    alu = BranchALU(width=16)
    vl = rtlil.convert(alu, ports=alu.ports())
    with open("test_branch_alu.il", "w") as f:
        f.write(vl)

