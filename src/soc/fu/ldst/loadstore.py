"""LoadStore1 FSM.

based on microwatt loadstore1.vhdl, but conforming to PortInterface.
unlike loadstore1.vhdl this does *not* deal with actual Load/Store
ops: that job is handled by LDSTCompUnit, which talks to LoadStore1
by way of PortInterface.  PortInterface is where things need extending,
such as adding dcbz support, etc.

this module basically handles "pure" load / store operations, and
its first job is to ask the D-Cache for the data.  if that fails,
the second task (if virtual memory is enabled) is to ask the MMU
to perform a TLB, then to go *back* to the cache and ask again.

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=465

"""

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
    ACK_WAIT = 1   # waiting for ack from dcache
    MMU_LOOKUP = 2 # waiting for MMU to look up translation
    TLBIE_WAIT = 3 # waiting for MMU to finish doing a tlbie
    COMPLETE = 4   # extra cycle to complete an operation


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

    def set_wr_addr(self, m, addr, mask, misalign):
        m.d.comb += self.load.eq(0) # store operation

        m.d.comb += self.d_in.load.eq(0)
        m.d.comb += self.byte_sel.eq(mask)
        m.d.comb += self.addr.eq(addr)
        m.d.comb += self.align_intr.eq(misalign)
        # option to disable the cache entirely for write
        if self.disable_cache:
            m.d.comb += self.nc.eq(1)
        return None

    def set_rd_addr(self, m, addr, mask, misalign):
        m.d.comb += self.d_valid.eq(1)
        m.d.comb += self.d_in.valid.eq(self.d_validblip)
        m.d.comb += self.load.eq(1) # load operation
        m.d.comb += self.d_in.load.eq(1)
        m.d.comb += self.byte_sel.eq(mask)
        m.d.comb += self.align_intr.eq(misalign)
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
        m.d.comb += self.store_data.eq(data)
        #m.d.sync += self.d_in.byte_sel.eq(wen) # this might not be needed
        st_ok = self.done # TODO indicates write data is valid
        return st_ok

    def get_rd_data(self, m):
        ld_ok = self.done     # indicates read data is valid
        data = self.load_data # actual read data
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
        comb, sync = m.d.comb, m.d.sync

        # create dcache module
        m.submodules.dcache = dcache = self.dcache

        # temp vars
        d_in, d_out, l_out, dbus = self.d_in, self.d_out, self.l_out, self.dbus

        # create a blip (single pulse) on valid read/write request
        # this can be over-ridden in the FSM to get dcache to re-run
        # a request when MMU_LOOKUP completes
        m.d.comb += self.d_validblip.eq(rising_edge(m, self.d_valid))

        # fsm skeleton
        with m.Switch(self.state):
            with m.Case(State.IDLE):
                with m.If(self.d_validblip):
                    sync += self.state.eq(State.ACK_WAIT)

            with m.Case(State.ACK_WAIT): # waiting for completion
                with m.If(d_out.error):
                    with m.If(d_out.cache_paradox):
                        sync += self.derror.eq(1)
                        sync += self.state.eq(State.IDLE)
                        sync += self.dsisr[63 - 38].eq(~self.load)
                        # XXX there is no architected bit for this
                        # (probably should be a machine check in fact)
                        sync += self.dsisr[63 - 35].eq(d_out.cache_paradox)

                    with m.Else():
                        # Look up the translation for TLB miss
                        # and also for permission error and RC error
                        # in case the PTE has been updated.
                        sync += self.mmureq.eq(1)
                        sync += self.state.eq(State.MMU_LOOKUP)
                with m.If(d_out.valid):
                    m.d.comb += self.done.eq(1)
                    sync += self.state.eq(State.IDLE)
                    with m.If(self.load):
                        m.d.comb += self.load_data.eq(d_out.data)

            with m.Case(State.MMU_LOOKUP):
                with m.If(l_out.done):
                    with m.If(~self.instr_fault):
                        # retry the request now that the MMU has
                        # installed a TLB entry
                        m.d.comb += self.d_validblip.eq(1) # re-run dcache req
                        sync += self.state.eq(State.ACK_WAIT)
                with m.If(l_out.err):
                    sync += self.dsisr[63 - 33].eq(l_out.invalid)
                    sync += self.dsisr[63 - 36].eq(l_out.perm_error)
                    sync += self.dsisr[63 - 38].eq(self.load)
                    sync += self.dsisr[63 - 44].eq(l_out.badtree)
                    sync += self.dsisr[63 - 45].eq(l_out.rc_error)

                '''
                if m_in.done = '1' then # actually l_out.done
                    if r.instr_fault = '0' then
                        # retry the request now that the MMU has
                        # installed a TLB entry
                        v.state := ACK_WAIT;
                    end if;
                end if;
                if m_in.err = '1' then # actually l_out.err
                    dsisr(63 - 33) := m_in.invalid;
                    dsisr(63 - 36) := m_in.perm_error;
                    dsisr(63 - 38) := not r.load;
                    dsisr(63 - 44) := m_in.badtree;
                    dsisr(63 - 45) := m_in.rc_error;
                end if;
                '''
                pass

            with m.Case(State.TLBIE_WAIT):
                pass
            with m.Case(State.COMPLETE):
                pass

        # happened, alignment, instr_fault, invalid.
        # note that all of these flow through - eventually to the TRAP
        # pipeline, via PowerDecoder2.
        exc = self.pi.exc_o
        comb += exc.happened.eq(d_out.error | l_out.err | self.align_intr)
        comb += exc.invalid.eq(l_out.invalid)
        comb += exc.alignment.eq(self.align_intr)

        # badtree, perm_error, rc_error, segment_fault
        comb += exc.badtree.eq(l_out.badtree)
        comb += exc.perm_error.eq(l_out.perm_error)
        comb += exc.rc_error.eq(l_out.rc_error)
        comb += exc.segment_fault.eq(l_out.segerr)

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

        # write out d data only when flag set
        with m.If(self.d_w_valid):
            m.d.sync += d_in.data.eq(self.store_data)
        with m.Else():
            m.d.sync += d_in.data.eq(0)

        # this must move into the FSM, conditionally noticing that
        # the "blip" comes from self.d_validblip.
        # task 1: look up in dcache
        # task 2: if dcache fails, look up in MMU.
        # do **NOT** confuse the two.
        m.d.comb += d_in.load.eq(self.load)
        m.d.comb += d_in.byte_sel.eq(self.byte_sel)
        m.d.comb += d_in.addr.eq(self.addr)
        m.d.comb += d_in.nc.eq(self.nc)

        # XXX these should be possible to remove but for some reason
        # cannot be... yet. TODO, investigate
        m.d.comb += self.done.eq(d_out.valid)
        m.d.comb += self.load_data.eq(d_out.data)

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

