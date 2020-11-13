"""a Dummy PLL module to be replaced by a real one
"""

from nmigen import (Module, Signal, Elaboratable, Const)
from nmigen.cli import rtlil

class DummyPLL(Elaboratable):
    def __init__(self):
        self.clk_24_i = Signal(reset_less=True) # 24 mhz external incoming
        self.clk_sel_i = Signal(2, reset_less=True) # PLL selection
        self.clk_pll_o = Signal(reset_less=True)  # output fake PLL clock
        self.pll_18_o = Signal(reset_less=True)  # 16-divide from PLL
        self.pll_lck_o = Signal(reset_less=True)  # output fake PLL "lock"

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.clk_pll_o.eq(self.clk_24_i) # just pass through
        # just get something, stops yosys destroying (optimising) these out
        m.d.comb += self.pll_18_o.eq(self.clk_24_i)
        with m.If(self.clk_sel_i == Const(0, 2)):
            m.d.comb += self.pll_lck_o.eq(self.clk_24_i)

        return m

    def ports(self):
        return [self.clk_24_i, self.clk_sel_i, self.clk_pll_o,
                self.pll_18_o, self.clk_lck_o]


if __name__ == '__main__':
    dut = ClockSelect()

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dummy_pll.il", "w") as f:
        f.write(vl)

