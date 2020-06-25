from nmigen import Elaboratable, Module, Signal, Record, Cat, Const, Mux
from nmigen.utils import log2_int
from nmigen.lib.fifo import SyncFIFO

from soc.minerva.cache import L1Cache
from soc.minerva.wishbone import wishbone_layout, WishboneArbiter, Cycle


__all__ = ["LoadStoreUnitInterface", "BareLoadStoreUnit",
           "CachedLoadStoreUnit"]


class LoadStoreUnitInterface:
    def __init__(self, addr_wid=32, mask_wid=4, data_wid=32):
        self.dbus = Record(wishbone_layout)
        badwid = addr_wid-log2_int(mask_wid) # TODO: is this correct?

        # INPUTS
        self.x_addr_i = Signal(addr_wid)    # address used for loads/stores
        self.x_mask_i = Signal(mask_wid)    # Mask of which bytes to write
        self.x_ld_i = Signal()              # set to do a memory load
        self.x_st_i = Signal()              # set to do a memory store
        self.x_st_data_i = Signal(data_wid) # The data to write when storing

        self.x_stall_i = Signal()           # do nothing until low
        self.x_valid_i = Signal()           # Whether x pipeline stage is
                                            # currently enabled (I
                                            # think?). Set to 1 for #now
        self.m_stall_i = Signal()           # do nothing until low
        self.m_valid_i = Signal()           # Whether m pipeline stage is
                                            # currently enabled. Set
                                            # to 1 for now

        # OUTPUTS
        self.x_busy_o = Signal()            # set when the memory is busy
        self.m_busy_o = Signal()            # set when the memory is busy

        self.m_ld_data_o = Signal(data_wid) # Data returned from memory read
        # Data validity is NOT indicated by m_valid_i or x_valid_i as
        # those are inputs. I believe it is valid on the next cycle
        # after raising m_load where busy is low

        self.m_load_err_o = Signal()      # if there was an error when loading
        self.m_store_err_o = Signal()     # if there was an error when storing
        self.m_badaddr_o = Signal(badwid) # The address of the load/store error


class BareLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        with m.If(self.dbus.cyc):
            with m.If(self.dbus.ack | self.dbus.err | ~self.m_valid_i):
                m.d.sync += [
                    self.dbus.cyc.eq(0),
                    self.dbus.stb.eq(0),
                    self.m_ld_data_o.eq(self.dbus.dat_r)
                ]
        with m.Elif((self.x_ld_i | self.x_st_i) &
                     self.x_valid_i & ~self.x_stall_i):
            m.d.sync += [
                self.dbus.cyc.eq(1),
                self.dbus.stb.eq(1),
                self.dbus.adr.eq(self.x_addr_i[2:]),
                self.dbus.sel.eq(self.x_mask_i),
                self.dbus.we.eq(self.x_st_i),
                self.dbus.dat_w.eq(self.x_st_data_i)
            ]

        with m.If(self.dbus.cyc & self.dbus.err):
            m.d.sync += [
                self.m_load_err_o.eq(~self.dbus.we),
                self.m_store_err_o.eq(self.dbus.we),
                self.m_badaddr_o.eq(self.dbus.adr)
            ]
        with m.Elif(~self.m_stall_i):
            m.d.sync += [
                self.m_load_err_o.eq(0),
                self.m_store_err_o.eq(0)
            ]

        m.d.comb += self.x_busy_o.eq(self.dbus.cyc)

        with m.If(self.m_load_err_o | self.m_store_err_o):
            m.d.comb += self.m_busy_o.eq(0)
        with m.Else():
            m.d.comb += self.m_busy_o.eq(self.dbus.cyc)

        return m


class CachedLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def __init__(self, *dcache_args):
        super().__init__()

        self.dcache_args = dcache_args

        self.x_fence_i = Signal()
        self.x_flush = Signal()
        self.m_addr = Signal(32)
        self.m_load = Signal()
        self.m_store = Signal()

    def elaborate(self, platform):
        m = Module()

        dcache = m.submodules.dcache = L1Cache(*self.dcache_args)

        x_dcache_select = Signal()
        m_dcache_select = Signal()

        m.d.comb += x_dcache_select.eq((self.x_addr_i >= dcache.base) &
                                       (self.x_addr_i < dcache.limit))
        with m.If(~self.x_stall_i):
            m.d.sync += m_dcache_select.eq(x_dcache_select)

        m.d.comb += [
            dcache.s1_addr.eq(self.x_addr_i[2:]),
            dcache.s1_flush.eq(self.x_flush),
            dcache.s1_stall.eq(self.x_stall_i),
            dcache.s1_valid.eq(self.x_valid_i & x_dcache_select),
            dcache.s2_addr.eq(self.m_addr[2:]),
            dcache.s2_re.eq(self.m_load),
            dcache.s2_evict.eq(self.m_store),
            dcache.s2_valid.eq(self.m_valid_i & m_dcache_select)
        ]

        wrbuf_w_data = Record([("addr", 30), ("mask", 4), ("data", 32)])
        wrbuf_r_data = Record.like(wrbuf_w_data)
        wrbuf = m.submodules.wrbuf = SyncFIFO(width=len(wrbuf_w_data),
                                              depth=dcache.nwords)
        m.d.comb += [
            wrbuf.w_data.eq(wrbuf_w_data),
            wrbuf_w_data.addr.eq(self.x_addr_i[2:]),
            wrbuf_w_data.mask.eq(self.x_mask_i),
            wrbuf_w_data.data.eq(self.x_st_data_i),
            wrbuf.w_en.eq(self.x_st_i & self.x_valid_i &
                          x_dcache_select & ~self.x_stall_i),
            wrbuf_r_data.eq(wrbuf.r_data),
        ]

        dbus_arbiter = m.submodules.dbus_arbiter = WishboneArbiter()
        m.d.comb += dbus_arbiter.bus.connect(self.dbus)

        wrbuf_port = dbus_arbiter.port(priority=0)
        with m.If(wrbuf_port.cyc):
            with m.If(wrbuf_port.ack | wrbuf_port.err):
                m.d.sync += [
                    wrbuf_port.cyc.eq(0),
                    wrbuf_port.stb.eq(0)
                ]
                m.d.comb += wrbuf.r_en.eq(1)
        with m.Elif(wrbuf.r_rdy):
            m.d.sync += [
                wrbuf_port.cyc.eq(1),
                wrbuf_port.stb.eq(1),
                wrbuf_port.adr.eq(wrbuf_r_data.addr),
                wrbuf_port.sel.eq(wrbuf_r_data.mask),
                wrbuf_port.dat_w.eq(wrbuf_r_data.data)
            ]
        m.d.comb += wrbuf_port.we.eq(Const(1))

        dcache_port = dbus_arbiter.port(priority=1)
        cti = Mux(dcache.bus_last, Cycle.END, Cycle.INCREMENT)
        m.d.comb += [
            dcache_port.cyc.eq(dcache.bus_re),
            dcache_port.stb.eq(dcache.bus_re),
            dcache_port.adr.eq(dcache.bus_addr),
            dcache_port.cti.eq(cti),
            dcache_port.bte.eq(Const(log2_int(dcache.nwords) - 1)),
            dcache.bus_valid.eq(dcache_port.ack),
            dcache.bus_error.eq(dcache_port.err),
            dcache.bus_rdata.eq(dcache_port.dat_r)
        ]

        bare_port = dbus_arbiter.port(priority=2)
        bare_rdata = Signal.like(bare_port.dat_r)
        with m.If(bare_port.cyc):
            with m.If(bare_port.ack | bare_port.err | ~self.m_valid_i):
                m.d.sync += [
                    bare_port.cyc.eq(0),
                    bare_port.stb.eq(0),
                    bare_rdata.eq(bare_port.dat_r)
                ]
        with m.Elif((self.x_ld_i | self.x_st_i) &
                    ~x_dcache_select & self.x_valid_i & ~self.x_stall_i):
            m.d.sync += [
                bare_port.cyc.eq(1),
                bare_port.stb.eq(1),
                bare_port.adr.eq(self.x_addr_i[2:]),
                bare_port.sel.eq(self.x_mask_i),
                bare_port.we.eq(self.x_st_i),
                bare_port.dat_w.eq(self.x_st_data_i)
            ]

        with m.If(self.dbus.cyc & self.dbus.err):
            m.d.sync += [
                self.m_load_err_o.eq(~self.dbus.we),
                self.m_store_err_o.eq(self.dbus.we),
                self.m_badaddr_o.eq(self.dbus.adr)
            ]
        with m.Elif(~self.m_stall_i):
            m.d.sync += [
                self.m_load_err_o.eq(0),
                self.m_store_err_o.eq(0)
            ]

        with m.If(self.x_fence_i):
            m.d.comb += self.x_busy_o.eq(wrbuf.r_rdy)
        with m.Elif(x_dcache_select):
            m.d.comb += self.x_busy_o.eq(self.x_st_i & ~wrbuf.w_rdy)
        with m.Else():
            m.d.comb += self.x_busy_o.eq(bare_port.cyc)

        with m.If(self.m_load_err_o | self.m_store_err_o):
            m.d.comb += [
                self.m_busy_o.eq(0),
                self.m_ld_data_o.eq(0)
            ]
        with m.Elif(m_dcache_select):
            m.d.comb += [
                self.m_busy_o.eq(dcache.s2_re & dcache.s2_miss),
                self.m_ld_data_o.eq(dcache.s2_rdata)
            ]
        with m.Else():
            m.d.comb += [
                self.m_busy_o.eq(bare_port.cyc),
                self.m_ld_data_o.eq(bare_rdata)
            ]

        return m
