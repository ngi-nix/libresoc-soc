"""a Dummy PLL module to be replaced by a real one
"""

from nmigen import (Module, Signal, Elaboratable, Const, Cat, Instance)
from nmigen.cli import rtlil

class DummyPLL(Elaboratable):
    def __init__(self, instance):
        self.instance = instance
        self.clk_24_i = Signal(reset_less=True) # external incoming
        self.clk_sel_i = Signal(2, reset_less=True) # PLL selection
        self.clk_pll_o = Signal(reset_less=True)  # output clock
        self.pll_test_o = Signal(reset_less=True)  # test out
        self.pll_vco_o = Signal(reset_less=True) # analog

    def elaborate(self, platform):
        m = Module()

        if self.instance:
            clk_24_i = Signal(reset_less=True) # external incoming
            clk_sel_i = Signal(2, reset_less=True) # PLL selection
            clk_pll_o = Signal(reset_less=True)  # output clock
            pll_test_o = Signal(reset_less=True)  # test out
            pll_vco_o = Signal(reset_less=True) # analog
            pll = Instance("pll", i_ref=clk_24_i,
                                  i_a0=clk_sel_i[0],
                                  i_a1=clk_sel_i[1],
                                  o_out_v=clk_pll_o,
                                  o_div_out_test=pll_test_o,
                                  o_vco_test_ana=pll_vco_o,
                           )
            m.submodules['real_pll'] = pll
            #pll.attrs['blackbox'] = 1
            m.d.comb += clk_24_i.eq(self.clk_24_i)
            m.d.comb += clk_sel_i.eq(self.clk_sel_i)
            m.d.comb += self.clk_pll_o.eq(clk_pll_o)
            m.d.comb += self.pll_test_o.eq(pll_test_o)
            m.d.comb += self.pll_vco_o.eq(pll_vco_o)

        else:
            m.d.comb += self.clk_pll_o.eq(self.clk_24_i) # just pass through
            # just get something, stops yosys destroying (optimising) these out
            with m.If(self.clk_sel_i == 0):
                m.d.comb += self.pll_test_o.eq(self.clk_24_i)
                m.d.comb += self.pll_vco_o.eq(~self.clk_24_i)

        return m

    def ports(self):
        return [self.clk_24_i, self.clk_sel_i, self.clk_pll_o,
                self.pll_test_o, self.pll_vco_o]


if __name__ == '__main__':
    dut = DummyPLL()

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_dummy_pll.il", "w") as f:
        f.write(vl)

