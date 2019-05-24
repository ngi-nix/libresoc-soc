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
        with m.Switch(self.op):
            for i, mod in enumerate([add, sub, mul, shf]):
                with m.Case(i):
                    m.d.comb += self.o.eq(mod.o)
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
        with m.Switch(self.op):
            for i, mod in enumerate([bgt, blt, beq, bne]):
                with m.Case(i):
                    m.d.comb += self.o.eq(mod.o)
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

