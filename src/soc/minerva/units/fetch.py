from nmigen import Elaboratable, Module, Signal, Record, Const, Mux
from nmigen.utils import log2_int

from soc.minerva.cache import L1Cache
from soc.minerva.wishbone import make_wb_layout, WishboneArbiter, Cycle


__all__ = ["FetchUnitInterface", "BareFetchUnit", "CachedFetchUnit"]


class FetchUnitInterface:
    def __init__(self, addr_wid=32, data_wid=32):
        self.addr_wid = addr_wid
        self.data_wid = data_wid
        self.adr_lsbs = log2_int(data_wid//8)
        self.ibus = Record(make_wb_layout(addr_wid, data_wid//8, data_wid))
        bad_wid = addr_wid - self.adr_lsbs # TODO: is this correct?

        # inputs: address to fetch PC, and valid/stall signalling
        self.a_pc_i = Signal(addr_wid)
        self.a_stall_i = Signal()
        self.a_valid_i = Signal()
        self.f_stall_i = Signal()
        self.f_valid_i = Signal()

        # outputs: instruction (or error), and busy indicators
        self.a_busy_o = Signal()
        self.f_busy_o = Signal()
        self.f_instr_o = Signal(data_wid)
        self.f_fetch_err_o = Signal()
        self.f_badaddr_o = Signal(bad_wid)


class BareFetchUnit(FetchUnitInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        ibus_rdata = Signal.like(self.ibus.dat_r)
        with m.If(self.ibus.cyc):
            with m.If(self.ibus.ack | self.ibus.err | ~self.f_valid_i):
                m.d.sync += [
                    self.ibus.cyc.eq(0),
                    self.ibus.stb.eq(0),
                    ibus_rdata.eq(self.ibus.dat_r)
                ]
        with m.Elif(self.a_valid_i & ~self.a_stall_i):
            m.d.sync += [
                self.ibus.adr.eq(self.a_pc_i[self.adr_lsbs:]),
                self.ibus.cyc.eq(1),
                self.ibus.stb.eq(1)
            ]

        with m.If(self.ibus.cyc & self.ibus.err):
            m.d.sync += [
                self.f_fetch_err_o.eq(1),
                self.f_badaddr_o.eq(self.ibus.adr)
            ]
        with m.Elif(~self.f_stall_i):
            m.d.sync += self.f_fetch_err_o.eq(0)

        m.d.comb += self.a_busy_o.eq(self.ibus.cyc)

        with m.If(self.f_fetch_err_o):
            m.d.comb += [
                self.f_busy_o.eq(0),
                self.f_instr_o.eq(0x0)
            ]
        with m.Else():
            m.d.comb += [
                self.f_busy_o.eq(self.ibus.cyc),
                self.f_instr_o.eq(ibus_rdata)
            ]

        return m


class CachedFetchUnit(FetchUnitInterface, Elaboratable):
    def __init__(self, *icache_args, addr_wid=32, data_wid=32):
        super().__init__(addr_wid=addr_wid, data_wid=data_wid)

        self.icache_args = icache_args

        self.a_flush = Signal()
        self.f_pc = Signal(addr_wid)

    def elaborate(self, platform):
        m = Module()

        icache = m.submodules.icache = L1Cache(*self.icache_args)

        a_icache_select = Signal()
        f_icache_select = Signal()

        m.d.comb += a_icache_select.eq((self.a_pc_i >= icache.base) &
                                        (self.a_pc_i < icache.limit))
        with m.If(~self.a_stall_i):
            m.d.sync += f_icache_select.eq(a_icache_select)

        m.d.comb += [
            icache.s1_addr.eq(self.a_pc_i[self.adr_lsbs:]),
            icache.s1_flush.eq(self.a_flush),
            icache.s1_stall.eq(self.a_stall_i),
            icache.s1_valid.eq(self.a_valid_i & a_icache_select),
            icache.s2_addr.eq(self.f_pc[self.adr_lsbs:]),
            icache.s2_re.eq(Const(1)),
            icache.s2_evict.eq(Const(0)),
            icache.s2_valid.eq(self.f_valid_i & f_icache_select)
        ]

        iba = WishboneArbiter(self.addr_wid, self.adr_lsbs, self.data_wid)
        m.submodules.ibus_arbiter = iba
        m.d.comb += iba.bus.connect(self.ibus)

        icache_port = iba.port(priority=0)
        cti = Mux(icache.bus_last, Cycle.END, Cycle.INCREMENT
        m.d.comb += [
            icache_port.cyc.eq(icache.bus_re),
            icache_port.stb.eq(icache.bus_re),
            icache_port.adr.eq(icache.bus_addr),
            icache_port.cti.eq(cti),
            icache_port.bte.eq(Const(log2_int(icache.nwords) - 1)),
            icache.bus_valid.eq(icache_port.ack),
            icache.bus_error.eq(icache_port.err),
            icache.bus_rdata.eq(icache_port.dat_r)
        ]

        bare_port = iba.port(priority=1)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err | ~self.f_valid_i):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif(~a_icache_select & self.a_valid_i & ~self.a_stall_i):
            m.d.sync += [
                bare_port.cyc.eq(1),
                bare_port.stb.eq(1),
                bare_port.adr.eq(self.a_pc_i[self.adr_lsbs:])
            ]

        with m.If(self.ibus.cyc & self.ibus.err):
            m.d.sync += [
                self.f_fetch_err_o.eq(1),
                self.f_badaddr_o.eq(self.ibus.adr)
            ]
        with m.Elif(~self.f_stall_i):
            m.d.sync += self.f_fetch_err_o.eq(0)

        with m.If(a_icache_select):
            m.d.comb += self.a_busy_o.eq(0)
        with m.Else():
            m.d.comb += self.a_busy_o.eq(bare_port.cyc)

        with m.If(self.f_fetch_err_o):
            m.d.comb += [
                self.f_busy_o.eq(0),
                self.f_instr_o.eq(0x0)
            ]
        with m.Elif(f_icache_select):
            m.d.comb += [
                self.f_busy_o.eq(icache.s2_re & icache.s2_miss),
                self.f_instr_o.eq(icache.s2_rdata)
            ]
        with m.Else():
            m.d.comb += [
                self.f_busy_o.eq(bare_port.cyc),
                self.f_instr_o.eq(bare_rdata)
            ]

        return m
