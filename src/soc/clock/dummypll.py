"""a Dummy PLL module to be replaced by a real one
"""

from nmigen import (Module, Signal, Elaboratable, Const, Cat)
from nmigen.cli import rtlil

class DummyPLL(Elaboratable):
    def __init__(self):
        self.clk_24_i = Signal(name="ref", reset_less=True) # external incoming
        self.sel_a0_i = Signal(name="a0", reset_less=True) # PLL selection
        self.sel_a1_i = Signal(name="a1", reset_less=True) # PLL selection
        self.clk_pll_o = Signal(name="out", reset_less=True)  # output clock
        self.pll_18_o = Signal(name="div_out_test", reset_less=True)  # test out
        self.pll_ana_o = Signal(name="vco_test_ana", reset_less=True) # analog

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.clk_pll_o.eq(self.clk_24_i) # just pass through
        # just get something, stops yosys destroying (optimising) these out
        with m.If((~self.sel_a0_i) & (~self.sel_a1_i)):
            m.d.comb += self.pll_ana_o.eq(self.clk_24_i)
            m.d.comb += self.pll_18_o.eq(~self.clk_24_i)

        #self.attrs['blackbox'] = 1

        return m

    def ports(self):
        return [self.clk_24_i, self.sel_a0_i, self.sel_a1_i, self.clk_pll_o,
                self.pll_18_o, self.pll_ana_o]


if __name__ == '__main__':
    dut = DummyPLL()

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dummy_pll.il", "w") as f:
        f.write(vl)

