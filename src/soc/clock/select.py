"""Clock selection.
"""

from nmigen import (Module, Array, Signal, Mux, Elaboratable, ClockSignal,
                    ResetSignal)
from nmigen.cli import rtlil


class ClockSelect(Elaboratable):
    def __init__(self):

        self.clk_sel_i = Signal() # clock source selection
        self.clk_24_i = Signal(reset_less=True) # 24 mhz external incoming
        self.pll_clk_i = Signal(reset_less=True)  # PLL input
        self.core_clk_o = Signal(reset_less=True) # main core clock (selectable)

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # set up system, zero and one clocks
        comb += self.core_clk_o.eq(Mux(self.clk_sel_i,
                                       self.pll_clk_i, self.clk_24_i))

        return m

    def ports(self):
        return [self.clk_24_i, self.pll_18_o, self.clk_sel_i, self.core_clk_o]


if __name__ == '__main__':
    dut = ClockSelect()

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_clk_sel.il", "w") as f:
        f.write(vl)

