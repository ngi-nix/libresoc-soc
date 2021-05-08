from nmigen import (Elaboratable, Module, Signal, Shape, unsigned, Cat, Mux,
                    Record, Memory,
                    Const)
from nmutil.util import rising_edge
from enum import Enum, unique

from soc.experiment.dcache import DCache
from soc.experiment.pimem import PortInterfaceBase
from soc.experiment.mem_types import LoadStore1ToMMUType
from soc.experiment.mem_types import MMUToLoadStore1Type

from soc.minerva.wishbone import make_wb_layout
from soc.bus.sram import SRAM


@unique
class State(Enum):
    IDLE = 0       # ready for instruction
    SECOND_REQ = 1 # send 2nd request of unaligned xfer
    ACK_WAIT = 2   # waiting for ack from dcache
    MMU_LOOKUP = 3 # waiting for MMU to look up translation
    TLBIE_WAIT = 4 # waiting for MMU to finish doing a tlbie
    FINISH_LFS = 5 # write back converted SP data for lfs*
    COMPLETE = 6   # extra cycle to complete an operation


# glue logic for microwatt mmu and dcache
class LoadStore1(PortInterfaceBase):
    def __init__(self, pspec):
        self.pspec = pspec
        self.disable_cache = (hasattr(pspec, "disable_cache") and
                              pspec.disable_cache == True)
        regwid = pspec.reg_wid
        addrwid = pspec.addr_wid

        super().__init__(regwid, addrwid)
        self.dcache = DCache()
        self.d_in  = self.dcache.d_in
        self.d_out = self.dcache.d_out
        self.l_in  = LoadStore1ToMMUType()
        self.l_out = MMUToLoadStore1Type()
        # TODO microwatt
        self.mmureq = Signal()
        self.derror = Signal()

        # TODO, convert dcache wb_in/wb_out to "standard" nmigen Wishbone bus
        self.dbus = Record(make_wb_layout(pspec))

        # for creating a single clock blip to DCache
        self.d_valid = Signal()
        self.d_w_data = Signal(64) # XXX
        self.d_w_valid = Signal()
        self.d_validblip = Signal()

        # DSISR and DAR cached values.  note that the MMU FSM is where
        # these are accessed by OP_MTSPR/OP_MFSPR, on behalf of LoadStore1.
        # by contrast microwatt has the spr set/get done *in* loadstore1.vhdl
        self.dsisr = Signal(64)
        self.dar = Signal(64)

        # state info for LD/ST
        self.done          = Signal()
        # latch most of the input request
        self.load          = Signal()
        self.tlbie         = Signal()
        self.dcbz          = Signal()
        self.addr          = Signal(64)
        self.store_data    = Signal(64)
        self.load_data     = Signal(64)
        self.byte_sel      = Signal(8)
        self.update        = Signal()
        #self.xerc         : xer_common_t;
        #self.reserve       = Signal()
        #self.atomic        = Signal()
        #self.atomic_last   = Signal()
        #self.rc            = Signal()
        self.nc            = Signal()              # non-cacheable access
        self.virt_mode     = Signal()
        self.priv_mode     = Signal()
        self.state        = Signal(State)
        self.instr_fault   = Signal()
        self.align_intr    = Signal()
        self.busy          = Signal()
        self.wait_dcache   = Signal()
        self.wait_mmu      = Signal()
        #self.mode_32bit    = Signal()
        self.wr_sel        = Signal(2)
        self.interrupt     = Signal()
        #self.intr_vec     : integer range 0 to 16#fff#;
        #self.nia           = Signal(64)
        #self.srr1          = Signal(16)

    def set_wr_addr(self, m, addr, mask):
        m.d.comb += self.load.eq(0) # store operation

        m.d.comb += self.d_in.load.eq(0)
        m.d.comb += self.byte_sel.eq(mask)
        m.d.comb += self.addr.eq(addr)
        # option to disable the cache entirely for write
        if self.disable_cache:
            m.d.comb += self.nc.eq(1)
        return None

    def set_rd_addr(self, m, addr, mask):
        m.d.comb += self.d_valid.eq(1)
        m.d.comb += self.d_in.valid.eq(self.d_validblip)
        m.d.comb += self.load.eq(1) # load operation
        m.d.comb += self.d_in.load.eq(1)
        m.d.comb += self.byte_sel.eq(mask)
        m.d.comb += self.addr.eq(addr)
        # BAD HACK! disable cacheing on LD when address is 0xCxxx_xxxx
        # this is for peripherals. same thing done in Microwatt loadstore1.vhdl
        with m.If(addr[28:] == Const(0xc, 4)):
            m.d.comb += self.nc.eq(1)
        # option to disable the cache entirely for read
        if self.disable_cache:
            m.d.comb += self.nc.eq(1)
        return None #FIXME return value

    def set_wr_data(self, m, data, wen):
        # do the "blip" on write data
        m.d.comb += self.d_valid.eq(1)
        m.d.comb += self.d_in.valid.eq(self.d_validblip)
        # put data into comb which is picked up in main elaborate()
        m.d.comb += self.d_w_valid.eq(1)
        m.d.comb += self.d_w_data.eq(data)
        #m.d.sync += self.d_in.byte_sel.eq(wen) # this might not be needed
        st_ok = self.done # TODO indicates write data is valid
        #st_ok = Const(1, 1)
        return st_ok

    def get_rd_data(self, m):
        ld_ok = self.done      # indicates read data is valid
        data = self.d_out.data # actual read data
        return data, ld_ok

    """
    if d_in.error = '1' then
                if d_in.cache_paradox = '1' then
                    -- signal an interrupt straight away
                    exception := '1';
                    dsisr(63 - 38) := not r2.req.load;
                    -- XXX there is no architected bit for this
                    -- (probably should be a machine check in fact)
                    dsisr(63 - 35) := d_in.cache_paradox;
                else
                    -- Look up the translation for TLB miss
                    -- and also for permission error and RC error
                    -- in case the PTE has been updated.
                    mmureq := '1';
                    v.state := MMU_LOOKUP;
                    v.stage1_en := '0';
                end if;
            end if;
    """

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb

        # create dcache module
        m.submodules.dcache = dcache = self.dcache

        # temp vars
        d_out, l_out, dbus = self.d_out, self.l_out, self.dbus

        with m.If(d_out.error):
            with m.If(d_out.cache_paradox):
                comb += self.derror.eq(1)
                """
                sync += self.dsisr[63 - 38].eq(~r2.req.load)
                #    -- XXX there is no architected bit for this
                #    -- (probably should be a machine check in fact)
                sync += self.dsisr[63 - 35].eq(d_in.cache_paradox)
                """
            with m.Else():
                # Look up the translation for TLB miss
                # and also for permission error and RC error
                # in case the PTE has been updated.
                comb += self.mmureq.eq(1)
                # v.state := MMU_LOOKUP;
                # v.stage1_en := '0';

        exc = self.pi.exc_o

        #happened, alignment, instr_fault, invalid,
        comb += exc.happened.eq(d_out.error | l_out.err)
        comb += exc.invalid.eq(l_out.invalid)

        #badtree, perm_error, rc_error, segment_fault
        comb += exc.badtree.eq(l_out.badtree)
        comb += exc.perm_error.eq(l_out.perm_error)
        comb += exc.rc_error.eq(l_out.rc_error)
        comb += exc.segment_fault.eq(l_out.segerr)

        # TODO connect those signals somewhere
        #print(d_out.valid)         -> no error
        #print(d_out.store_done)    -> no error
        #print(d_out.cache_paradox) -> ?
        #print(l_out.done)          -> no error

        # TODO some exceptions set SPRs

        # TODO, connect dcache wb_in/wb_out to "standard" nmigen Wishbone bus
        comb += dbus.adr.eq(dcache.wb_out.adr)
        comb += dbus.dat_w.eq(dcache.wb_out.dat)
        comb += dbus.sel.eq(dcache.wb_out.sel)
        comb += dbus.cyc.eq(dcache.wb_out.cyc)
        comb += dbus.stb.eq(dcache.wb_out.stb)
        comb += dbus.we.eq(dcache.wb_out.we)

        comb += dcache.wb_in.dat.eq(dbus.dat_r)
        comb += dcache.wb_in.ack.eq(dbus.ack)
        if hasattr(dbus, "stall"):
            comb += dcache.wb_in.stall.eq(dbus.stall)

        # create a blip (single pulse) on valid read/write request
        m.d.comb += self.d_validblip.eq(rising_edge(m, self.d_valid))

        # write out d data only when flag set
        with m.If(self.d_w_valid):
            m.d.sync += self.d_in.data.eq(self.d_w_data)
        with m.Else():
            m.d.sync += self.d_in.data.eq(0)

        m.d.comb += self.d_in.load.eq(self.load)
        m.d.comb += self.d_in.byte_sel.eq(self.byte_sel)
        m.d.comb += self.d_in.addr.eq(self.addr)
        m.d.comb += self.d_in.nc.eq(self.nc)
        m.d.comb += self.done.eq(self.d_out.valid)

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports


class TestSRAMLoadStore1(LoadStore1):
    def __init__(self, pspec):
        super().__init__(pspec)
        pspec = self.pspec
        # small 32-entry Memory
        if (hasattr(pspec, "dmem_test_depth") and
                isinstance(pspec.dmem_test_depth, int)):
            depth = pspec.dmem_test_depth
        else:
            depth = 32
        print("TestSRAMBareLoadStoreUnit depth", depth)

        self.mem = Memory(width=pspec.reg_wid, depth=depth)

    def elaborate(self, platform):
        m = super().elaborate(platform)
        comb = m.d.comb
        m.submodules.sram = sram = SRAM(memory=self.mem, granularity=8,
                                        features={'cti', 'bte', 'err'})
        dbus = self.dbus

        # directly connect the wishbone bus of LoadStoreUnitInterface to SRAM
        # note: SRAM is a target (slave), dbus is initiator (master)
        fanouts = ['dat_w', 'sel', 'cyc', 'stb', 'we', 'cti', 'bte']
        fanins = ['dat_r', 'ack', 'err']
        for fanout in fanouts:
            print("fanout", fanout, getattr(sram.bus, fanout).shape(),
                  getattr(dbus, fanout).shape())
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
            comb += getattr(sram.bus, fanout).eq(getattr(dbus, fanout))
        for fanin in fanins:
            comb += getattr(dbus, fanin).eq(getattr(sram.bus, fanin))
        # connect address
        comb += sram.bus.adr.eq(dbus.adr)

        return m

