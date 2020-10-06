"""Clock selection.

* PLL @ 300mhz input generates a div-6 "test" output
* clock select sets the source
  - 0b000 - CLK_24 (direct)
  - 0b001 - PLL / 6
  - 0b010 - PLL / 4
  - 0b011 - PLL / 3
  - 0b100 - PLL / 2
  - 0b101 - PLL
  - 0b110 - ZERO (direct driving in combination with ONE)
  - 0b111 - ONE
* this is all assumed to be driven by the "PLL CLK".
  the CLK_24 is the default in case PLL is unstable
"""

from nmigen import (Module, Array, Signal, Mux, Elaboratable, ClockSignal,
                    ResetSignal)
from nmigen.cli import rtlil

CLK_24 = 0b000 # this is the default (clk_sel_i = 0 on reset)
PLL6 = 0b001
PLL4 = 0b010
PLL3 = 0b011
PLL2 = 0b100
PLL  = 0b101
ZERO = 0b110
ONE  = 0b111


class ClockSelect(Elaboratable):
    def __init__(self):

        self.clk_24_i = Signal() # 24 mhz external incoming
        self.pll_48_o = Signal()  # 6-divide (test signal) from PLL
        self.clk_sel_i = Signal(3) # clock source selection
        self.core_clk_o = Signal() # main core clock (selectable)
        self.rst        = Signal() # reset

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync
        m.d.comb += ResetSignal().eq(self.rst)

        # array of clocks (selectable by clk_sel_i)
        clkgen = Array([Signal(name="clk%d" % i) for i in range(8)])
        counter3 = Signal(2) # for divide-by-3

        # set up system, zero and one clocks
        comb += clkgen[CLK_24].eq(self.clk_24_i) # 1st is external 24mhz
        comb += clkgen[ZERO].eq(0) # LOW (use with ONE for direct driving)
        comb += clkgen[ONE].eq(1) # HI

        # (always) generate PLL-driven signals: /2/3/4/6
        sync += clkgen[PLL2].eq(~clkgen[PLL2]) # half PLL rate
        with m.If(clkgen[PLL2]):
            sync += clkgen[PLL4].eq(~clkgen[PLL4]) # quarter PLL rate
        with m.If(counter3 == 2):
            sync += counter3.eq(0)
            sync += clkgen[PLL3].eq(~clkgen[PLL3]) # 1/3 PLL rate
            with m.If(clkgen[PLL3]):
                sync += clkgen[PLL6].eq(~clkgen[PLL6]) # 1/6 PLL rate
        with m.Else():
            sync += counter3.eq(counter3+1)

        # select from available array of clock sources
        comb += self.core_clk_o.eq(clkgen[self.clk_sel_i])

        # 48mhz output is PLL/6
        comb += self.pll_48_o.eq(clkgen[PLL6])

        return m

    def ports(self):
        return [self.clk_24_i, self.pll_48_o, self.clk_sel_i, self.core_clk_o]


class DummyPLL(Elaboratable):
    def __init__(self):
        self.clk_24_i = Signal() # 24 mhz external incoming
        self.clk_pll_o = Signal()  # output fake PLL clock
        self.rst = Signal() # reset

    def elaborate(self, platform):
        m = Module()
        m.d.comb += self.clk_pll_o.eq(self.clk_24_i) # just pass through
        m.d.comb += ResetSignal().eq(self.rst)

        return m

    def ports(self):
        return [self.clk_24_i, self.clk_pll_o]


if __name__ == '__main__':
    dut = ClockSelect()

    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_clk_sel.il", "w") as f:
        f.write(vl)

