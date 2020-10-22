from nmigen import Elaboratable, Module, Signal, Record, Cat, Const, Mux
from nmigen.utils import log2_int
from nmigen.lib.fifo import SyncFIFO

from soc.minerva.cache import L1Cache
from soc.minerva.wishbone import make_wb_layout, WishboneArbiter, Cycle
from soc.bus.wb_downconvert import WishboneDownConvert

from copy import deepcopy

__all__ = ["LoadStoreUnitInterface", "BareLoadStoreUnit",
           "CachedLoadStoreUnit"]


class LoadStoreUnitInterface:
    def __init__(self, pspec):
        self.pspec = pspec
        self.pspecslave = pspec
        if (hasattr(pspec, "dmem_test_depth") and
                     isinstance(pspec.wb_data_wid, int) and
                    pspec.wb_data_wid != pspec.reg_wid):
            self.dbus = Record(make_wb_layout(pspec), name="int_dbus")
            pspecslave = deepcopy(pspec)
            pspecslave.reg_wid = pspec.wb_data_wid
            mask_ratio = (pspec.reg_wid // pspec.wb_data_wid)
            pspecslave.mask_wid = pspec.mask_wid // mask_ratio
            self.pspecslave = pspecslave
            self.slavebus = Record(make_wb_layout(pspecslave), name="dbus")
            self.needs_cvt = True
        else:
            self.needs_cvt = False
            self.dbus = self.slavebus = Record(make_wb_layout(pspec))

        # detect whether the wishbone bus is enabled / disabled
        if (hasattr(pspec, "wb_dcache_en") and
                     isinstance(pspec.wb_dcache_en, Signal)):
            self.jtag_en = pspec.wb_dcache_en
        else:
            self.jtag_en = Const(1, 1) # permanently on

        print(self.dbus.sel.shape())
        self.mask_wid = mask_wid = pspec.mask_wid
        self.addr_wid = addr_wid = pspec.addr_wid
        self.data_wid = data_wid = pspec.reg_wid
        print("loadstoreunit addr mask data", addr_wid, mask_wid, data_wid)
        self.adr_lsbs = log2_int(mask_wid)  # LSBs of addr covered by mask
        badwid = addr_wid-self.adr_lsbs    # TODO: is this correct?

        # INPUTS
        self.x_addr_i = Signal(addr_wid)    # address used for loads/stores
        self.x_mask_i = Signal(mask_wid)    # Mask of which bytes to write
        self.x_ld_i = Signal()              # set to do a memory load
        self.x_st_i = Signal()              # set to do a memory store
        self.x_st_data_i = Signal(data_wid)  # The data to write when storing

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

        self.m_ld_data_o = Signal(data_wid)  # Data returned from memory read
        # Data validity is NOT indicated by m_valid_i or x_valid_i as
        # those are inputs. I believe it is valid on the next cycle
        # after raising m_load where busy is low

        self.m_load_err_o = Signal()      # if there was an error when loading
        self.m_store_err_o = Signal()     # if there was an error when storing
        # The address of the load/store error
        self.m_badaddr_o = Signal(badwid)

    def __iter__(self):
        yield self.x_addr_i
        yield self.x_mask_i
        yield self.x_ld_i
        yield self.x_st_i
        yield self.x_st_data_i

        yield self.x_stall_i
        yield self.x_valid_i
        yield self.m_stall_i
        yield self.m_valid_i
        yield self.x_busy_o
        yield self.m_busy_o
        yield self.m_ld_data_o
        yield self.m_load_err_o
        yield self.m_store_err_o
        yield self.m_badaddr_o
        for sig in self.slavebus.fields.values():
            yield sig

    def ports(self):
        return list(self)


class BareLoadStoreUnit(LoadStoreUnitInterface, Elaboratable):
    def elaborate(self, platform):
        m = Module()

        if self.needs_cvt:
            self.cvt = WishboneDownConvert(self.dbus, self.slavebus)
            m.submodules.cvt = self.cvt

        with m.If(self.jtag_en): # for safety, JTAG can completely disable WB

            with m.If(self.dbus.cyc):
                with m.If(self.dbus.ack | self.dbus.err | ~self.m_valid_i):
                    m.d.sync += [
                        self.dbus.cyc.eq(0),
                        self.dbus.stb.eq(0),
                        self.dbus.sel.eq(0),
                        self.m_ld_data_o.eq(self.dbus.dat_r)
                    ]
            with m.Elif((self.x_ld_i | self.x_st_i) &
                        self.x_valid_i & ~self.x_stall_i):
                m.d.sync += [
                    self.dbus.cyc.eq(1),
                    self.dbus.stb.eq(1),
                    self.dbus.adr.eq(self.x_addr_i[self.adr_lsbs:]),
                    self.dbus.sel.eq(self.x_mask_i),
                    self.dbus.we.eq(self.x_st_i),
                    self.dbus.dat_w.eq(self.x_st_data_i)
                ]
            with m.Else():
                m.d.sync += [
                    self.dbus.adr.eq(0),
                    self.dbus.sel.eq(0),
                    self.dbus.we.eq(0),
                    self.dbus.sel.eq(0),
                    self.dbus.dat_w.eq(0),
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
    def __init__(self, pspec):
        super().__init__(pspec)

        self.dcache_args = psiec.dcache_args

        self.x_fence_i = Signal()
        self.x_flush = Signal()
        self.m_load = Signal()
        self.m_store = Signal()

    def elaborate(self, platform):
        m = Module()

        dcache = m.submodules.dcache = L1Cache(*self.dcache_args)

        x_dcache_select = Signal()
        # Test whether the target address is inside the L1 cache region.
        # We use bit masks in order to avoid carry chains from arithmetic
        # comparisons. This restricts the region boundaries to powers of 2.
        with m.Switch(self.x_addr_i[self.adr_lsbs:]):
            def addr_below(limit):
                assert limit in range(1, 2**30 + 1)
                range_bits = log2_int(limit)
                const_bits = 30 - range_bits
                return "{}{}".format("0" * const_bits, "-" * range_bits)

            if dcache.base >= (1 << self.adr_lsbs):
                with m.Case(addr_below(dcache.base >> self.adr_lsbs)):
                    m.d.comb += x_dcache_select.eq(0)
            with m.Case(addr_below(dcache.limit >> self.adr_lsbs)):
                m.d.comb += x_dcache_select.eq(1)
            with m.Default():
                m.d.comb += x_dcache_select.eq(0)

        m_dcache_select = Signal()
        m_addr = Signal.like(self.x_addr_i)

        with m.If(~self.x_stall_i):
            m.d.sync += [
                m_dcache_select.eq(x_dcache_select),
                m_addr.eq(self.x_addr_i),
            ]

        m.d.comb += [
            dcache.s1_addr.eq(self.x_addr_i[self.adr_lsbs:]),
            dcache.s1_flush.eq(self.x_flush),
            dcache.s1_stall.eq(self.x_stall_i),
            dcache.s1_valid.eq(self.x_valid_i & x_dcache_select),
            dcache.s2_addr.eq(m_addr[self.adr_lsbs:]),
            dcache.s2_re.eq(self.m_load),
            dcache.s2_evict.eq(self.m_store),
            dcache.s2_valid.eq(self.m_valid_i & m_dcache_select)
        ]

        wrbuf_w_data = Record([("addr", self.addr_wid-self.adr_lsbs),
                               ("mask", self.mask_wid),
                               ("data", self.data_wid)])
        wrbuf_r_data = Record.like(wrbuf_w_data)
        wrbuf = m.submodules.wrbuf = SyncFIFO(width=len(wrbuf_w_data),
                                              depth=dcache.nwords)
        m.d.comb += [
            wrbuf.w_data.eq(wrbuf_w_data),
            wrbuf_w_data.addr.eq(self.x_addr_i[self.adr_lsbs:]),
            wrbuf_w_data.mask.eq(self.x_mask_i),
            wrbuf_w_data.data.eq(self.x_st_data_i),
            wrbuf.w_en.eq(self.x_st_i & self.x_valid_i &
                          x_dcache_select & ~self.x_stall_i),
            wrbuf_r_data.eq(wrbuf.r_data),
        ]

        dba = WishboneArbiter(self.pspec)
        m.submodules.dbus_arbiter = dba
        m.d.comb += dba.bus.connect(self.dbus)

        wrbuf_port = dbus_arbiter.port(priority=0)
        m.d.comb += [
            wrbuf_port.cyc.eq(wrbuf.r_rdy),
            wrbuf_port.we.eq(Const(1)),
        ]
        with m.If(wrbuf_port.stb):
            with m.If(wrbuf_port.ack | wrbuf_port.err):
                m.d.sync += wrbuf_port.stb.eq(0)
                m.d.comb += wrbuf.r_en.eq(1)
        with m.Elif(wrbuf.r_rdy):
            m.d.sync += [
                wrbuf_port.stb.eq(1),
                wrbuf_port.adr.eq(wrbuf_r_data.addr),
                wrbuf_port.sel.eq(wrbuf_r_data.mask),
                wrbuf_port.dat_w.eq(wrbuf_r_data.data)
            ]

        dcache_port = dba.port(priority=1)
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

        bare_port = dba.port(priority=2)
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
                bare_port.adr.eq(self.x_addr_i[self.adr_lsbs:]),
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

        with m.If(self.m_flush):
            m.d.comb += self.m_busy_o.eq(~dcache.s2_flush_ack)
        with m.If(self.m_load_err_o | self.m_store_err_o):
            m.d.comb += self.m_busy_o.eq(0)
        with m.Elif(m_dcache_select):
            m.d.comb += [
                self.m_busy_o.eq(dcache.s2_miss),
                self.m_ld_data_o.eq(dcache.s2_rdata)
            ]
        with m.Else():
            m.d.comb += [
                self.m_busy_o.eq(bare_port.cyc),
                self.m_ld_data_o.eq(bare_rdata)
            ]

        return m
