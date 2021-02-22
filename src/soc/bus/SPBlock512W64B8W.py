from nmigen import Elaboratable, Cat, Module, Signal, ClockSignal, Instance
from nmigen.utils import log2_int

from nmigen_soc.wishbone.bus import Interface
from nmigen.cli import rtlil

__all__ = ["SPBlock512W64B8W"]


class SPBlock512W64B8W(Elaboratable):
    """SRAM module carrying a volatile 4k memory block (implemented with
    Instance SPBlock512W64B8W).  512 rows, 64-bit, QTY 8 write-enable lines
    """

    def __init__(self, bus=None, features=None, name=None):
        self.enable = Signal(reset=1) # enable signal, defaults to 1
        if features is None:
            features = frozenset()
        if bus is None:
            bus = Interface(addr_width=9,  # 512 lines of
                            data_width=64, # 64 bit
                            granularity=8, # at 8-bit granularity
                            features=features,
                            alignment=0,
                            name=name)
        self.bus = bus
        self.granularity = bus.granularity

        n_wrport = 8
        n_bussel = self.bus.sel.width
        assert n_wrport == n_bussel, "bus enable count %d " \
                "must match memory wen count %d" % (n_wrport, n_bussel)

        assert len(self.bus.dat_r) == 64, "bus width must be 64"

    def elaborate(self, platform):
        m = Module()

        # 4k SRAM instance
        a = Signal(9)
        we = Signal()
        q = Signal(64) # output
        d = Signal(64) # input

        # create Chips4Makers 4k SRAM cell here, mark it as "black box"
        # for coriolis2 to pick up
        sram = Instance("SPBlock_512W64B8W", i_a=a, o_q=q, i_d=d,
                                             i_we=we, i_clk=ClockSignal())
        m.submodules += sram
        sram.attrs['blackbox'] = 1

        with m.If(self.enable): # in case of layout problems
            # wishbone is active if cyc and stb set
            wb_active = Signal()
            m.d.comb += wb_active.eq(self.bus.cyc & self.bus.stb)

            # generate ack (no "pipeline" mode here)
            m.d.sync += self.bus.ack.eq(wb_active)

            with m.If(wb_active):

                # address
                m.d.comb += a.eq(self.bus.adr)

                # read
                m.d.comb += self.bus.dat_r.eq(q)

                # write
                m.d.comb += d.eq(self.bus.dat_w)
                with m.If(self.bus.we):
                    m.d.comb += we.eq(self.bus.sel)

        return m


def create_ilang(dut, ports, test_name):
    vl = rtlil.convert(dut, name=test_name, ports=ports)
    with open("%s.il" % test_name, "w") as f:
        f.write(vl)

if __name__ == "__main__":
    alu = SPBlock512W64B8W()
    create_ilang(alu, [alu.bus.cyc, alu.bus.stb, alu.bus.ack,
                       alu.bus.dat_r, alu.bus.dat_w, alu.bus.adr,
                       alu.bus.we, alu.bus.sel], "SPBlock512W64B8W")
