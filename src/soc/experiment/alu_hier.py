"""*Experimental* ALU: based on nmigen alu_hier.py, includes branch-compare ALU

This ALU is *deliberately* designed to add in (unnecessary) delays into
different operations so as to be able to test the 6600-style matrices
and the CompUnits.  Countdown timers wait for (defined) periods before
indicating that the output is valid

A "real" integer ALU would place the answers onto the output bus after
only one cycle (sync)
"""

from nmigen import Elaboratable, Signal, Module, Const, Mux
from nmigen.cli import main
from nmigen.cli import verilog, rtlil

import operator


class Adder(Elaboratable):
    def __init__(self, width):
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)

    def elaborate(self, platform):
        m = Module()
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


class ALU(Elaboratable):
    def __init__(self, width):
        self.p_valid_i = Signal()
        self.p_ready_o = Signal()
        self.n_ready_i = Signal()
        self.n_valid_o = Signal()
        self.counter   = Signal(4)
        self.op  = Signal(2)
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)
        self.width = width

    def elaborate(self, platform):
        m = Module()
        add = Adder(self.width)
        sub = Subtractor(self.width)
        mul = Multiplier(self.width)
        shf = Shifter(self.width)

        m.submodules.add = add
        m.submodules.sub = sub
        m.submodules.mul = mul
        m.submodules.shf = shf
        for mod in [add, sub, mul, shf]:
            m.d.comb += [
                mod.a.eq(self.a),
                mod.b.eq(self.b),
            ]
        go_now = Signal(reset_less=True) # testing no-delay ALU

        with m.If(self.p_valid_i):
            # input is valid. next check, if we already said "ready" or not
            with m.If(~self.p_ready_o):
                # we didn't say "ready" yet, so say so and initialise
                m.d.sync += self.p_ready_o.eq(1)

                # as this is a "fake" pipeline, just grab the output right now
                with m.Switch(self.op):
                    for i, mod in enumerate([add, sub, mul, shf]):
                        with m.Case(i):
                            m.d.sync += self.o.eq(mod.o)
                with m.If(self.op == 2): # MUL, to take 5 instructions
                    m.d.sync += self.counter.eq(5)
                with m.Elif(self.op == 3): # SHIFT to take 7
                    m.d.sync += self.counter.eq(7)
                with m.Elif(self.op == 1): # SUB to take 1, straight away
                    m.d.sync += self.counter.eq(1)
                    m.d.comb += go_now.eq(1)
                with m.Else(): # ADD to take 2
                    m.d.sync += self.counter.eq(2)
        with m.Else():
            # input says no longer valid, so drop ready as well.
            # a "proper" ALU would have had to sync in the opcode and a/b ops
            m.d.sync += self.p_ready_o.eq(0)

        # ok so the counter's running: when it gets to 1, fire the output
        with m.If((self.counter == 1) | go_now):
            # set the output as valid if the recipient is ready for it
            m.d.sync += self.n_valid_o.eq(1)
        with m.If(self.n_ready_i & self.n_valid_o):
            m.d.sync += self.n_valid_o.eq(0)
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
        self.p_valid_i = Signal()
        self.p_ready_o = Signal()
        self.n_ready_i = Signal()
        self.n_valid_o = Signal()
        self.counter   = Signal(4)
        self.op  = Signal(2)
        self.a   = Signal(width)
        self.b   = Signal(width)
        self.o   = Signal(width)
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
        with m.If(self.p_valid_i):
            # input is valid. next check, if we already said "ready" or not
            with m.If(~self.p_ready_o):
                # we didn't say "ready" yet, so say so and initialise
                m.d.sync += self.p_ready_o.eq(1)

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
            m.d.sync += self.p_ready_o.eq(0)

        # ok so the counter's running: when it gets to 1, fire the output
        with m.If((self.counter == 1) | go_now):
            # set the output as valid if the recipient is ready for it
            m.d.sync += self.n_valid_o.eq(1)
        with m.If(self.n_ready_i & self.n_valid_o):
            m.d.sync += self.n_valid_o.eq(0)
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


if __name__ == "__main__":
    alu = ALU(width=16)
    vl = rtlil.convert(alu, ports=alu.ports())
    with open("test_alu.il", "w") as f:
        f.write(vl)

    alu = BranchALU(width=16)
    vl = rtlil.convert(alu, ports=alu.ports())
    with open("test_branch_alu.il", "w") as f:
        f.write(vl)

