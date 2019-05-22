from nmigen import Elaboratable, Signal, Module, Const
from nmigen.cli import main


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
            with m.Case(0):
                m.d.comb += self.o.eq(add.o)
            with m.Case(1):
                m.d.comb += self.o.eq(sub.o)
            with m.Case(2):
                m.d.comb += self.o.eq(mul.o)
            with m.Case(3):
                m.d.comb += self.o.eq(shf.o)
        return m


if __name__ == "__main__":
    alu = ALU(width=16)
    main(alu, ports=[alu.op, alu.a, alu.b, alu.o])
