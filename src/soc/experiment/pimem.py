"""L0 Cache/Buffer

This first version is intended for prototyping and test purposes:
it has "direct" access to Memory.

The intention is that this version remains an integral part of the
test infrastructure, and, just as with minerva's memory arrangement,
a dynamic runtime config *selects* alternative memory arrangements
rather than *replaces and discards* this code.

Links:

* https://bugs.libre-soc.org/show_bug.cgi?id=216
* https://libre-soc.org/3d_gpu/architecture/memory_and_cache/

"""

from nmigen.compat.sim import run_simulation, Settle
from nmigen.cli import rtlil
from nmigen import Module, Signal, Mux, Elaboratable, Cat, Const
from nmutil.iocontrol import RecordObject
from nmigen.utils import log2_int

from nmutil.latch import SRLatch, latchregister
from nmutil.util import rising_edge
from openpower.decoder.power_decoder2 import Data
from soc.scoreboard.addr_match import LenExpand
from soc.experiment.mem_types import LDSTException

# for testing purposes
from soc.experiment.testmem import TestMemory
#from soc.scoreboard.addr_split import LDSTSplitter

import unittest


class PortInterface(RecordObject):
    """PortInterface

    defines the interface - the API - that the LDSTCompUnit connects
    to.  note that this is NOT a "fire-and-forget" interface.  the
    LDSTCompUnit *must* be kept appraised that the request is in
    progress, and only when it has a 100% successful completion
    can the notification be given (busy dropped).

    The interface FSM rules are as follows:

    * if busy_o is asserted, a LD/ST is in progress.  further
      requests may not be made until busy_o is deasserted.

    * only one of is_ld_i or is_st_i may be asserted.  busy_o
      will immediately be asserted and remain asserted.

    * addr.ok is to be asserted when the LD/ST address is known.
      addr.data is to be valid on the same cycle.

      addr.ok and addr.data must REMAIN asserted until busy_o
      is de-asserted.  this ensures that there is no need
      for the L0 Cache/Buffer to have an additional address latch
      (because the LDSTCompUnit already has it)

    * addr_ok_o (or exception.happened) must be waited for.  these will
      be asserted *only* for one cycle and one cycle only.

    * exception.happened will be asserted if there is no chance that the
      memory request may be fulfilled.

      busy_o is deasserted on the same cycle as exception.happened is asserted.

    * conversely: addr_ok_o must *ONLY* be asserted if there is a
      HUNDRED PERCENT guarantee that the memory request will be
      fulfilled.

    * for a LD, ld.ok will be asserted - for only one clock cycle -
      at any point in the future that is acceptable to the underlying
      Memory subsystem.  the recipient MUST latch ld.data on that cycle.

      busy_o is deasserted on the same cycle as ld.ok is asserted.

    * for a ST, st.ok may be asserted only after addr_ok_o had been
      asserted, alongside valid st.data at the same time.  st.ok
      must only be asserted for one cycle.

      the underlying Memory is REQUIRED to pick up that data and
      guarantee its delivery.  no back-acknowledgement is required.

      busy_o is deasserted on the cycle AFTER st.ok is asserted.
    """

    def __init__(self, name=None, regwid=64, addrwid=48):

        self._regwid = regwid
        self._addrwid = addrwid

        RecordObject.__init__(self, name=name)

        # distinguish op type (ld/st)
        self.is_ld_i = Signal(reset_less=True)
        self.is_st_i = Signal(reset_less=True)

        # LD/ST data length (TODO: other things may be needed)
        self.data_len = Signal(4, reset_less=True)

        # common signals
        self.busy_o = Signal(reset_less=True)     # do not use if busy
        self.go_die_i = Signal(reset_less=True)   # back to reset
        self.addr = Data(addrwid, "addr_i")            # addr/addr-ok
        # addr is valid (TLB, L1 etc.)
        self.addr_ok_o = Signal(reset_less=True)
        self.exc_o = LDSTException("exc")

        # LD/ST
        self.ld = Data(regwid, "ld_data_o")  # ok to be set by L0 Cache/Buf
        self.st = Data(regwid, "st_data_i")  # ok to be set by CompUnit

        # additional "modes"
        self.dcbz          = Signal()  # data cache block zero request
        self.nc            = Signal()  # no cacheing
        self.virt_mode     = Signal()  # virtual mode
        self.priv_mode     = Signal()  # privileged mode

        # mmu
        self.mmu_done          = Signal() # keep for now
       
        # dcache
        self.ldst_error        = Signal()
        ## Signalling ld/st error - NC cache hit, TLB miss, prot/RC failure
        self.cache_paradox     = Signal()

    def connect_port(self, inport):
        print("connect_port", self, inport)
        return [self.is_ld_i.eq(inport.is_ld_i),
                self.is_st_i.eq(inport.is_st_i),
                self.data_len.eq(inport.data_len),
                self.go_die_i.eq(inport.go_die_i),
                self.addr.data.eq(inport.addr.data),
                self.addr.ok.eq(inport.addr.ok),
                self.st.eq(inport.st),
                inport.ld.eq(self.ld),
                inport.busy_o.eq(self.busy_o),
                inport.addr_ok_o.eq(self.addr_ok_o),
                inport.exc_o.eq(self.exc_o),
                inport.mmu_done.eq(self.mmu_done),
                inport.ldst_error.eq(self.ldst_error),
                inport.cache_paradox.eq(self.cache_paradox)
                ]


class PortInterfaceBase(Elaboratable):
    """PortInterfaceBase

    Base class for PortInterface-compliant Memory read/writers
    """

    def __init__(self, regwid=64, addrwid=4):
        self.regwid = regwid
        self.addrwid = addrwid
        self.pi = PortInterface("ldst_port0", regwid, addrwid)

    @property
    def addrbits(self):
        return log2_int(self.regwid//8)

    def splitaddr(self, addr):
        """split the address into top and bottom bits of the memory granularity
        """
        return addr[:self.addrbits], addr[self.addrbits:]

    def connect_port(self, inport):
        return self.pi.connect_port(inport)

    def set_wr_addr(self, m, addr, mask): pass
    def set_rd_addr(self, m, addr, mask): pass
    def set_wr_data(self, m, data, wen): pass
    def get_rd_data(self, m): pass

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        # state-machine latches
        m.submodules.st_active = st_active = SRLatch(False, name="st_active")
        m.submodules.st_done = st_done = SRLatch(False, name="st_done")
        m.submodules.ld_active = ld_active = SRLatch(False, name="ld_active")
        m.submodules.reset_l = reset_l = SRLatch(True, name="reset")
        m.submodules.adrok_l = adrok_l = SRLatch(False, name="addr_acked")
        m.submodules.busy_l = busy_l = SRLatch(False, name="busy")
        m.submodules.cyc_l = cyc_l = SRLatch(True, name="cyc")

        self.busy_l = busy_l

        sync += st_done.s.eq(0)
        comb += st_done.r.eq(0)
        comb += st_active.r.eq(0)
        comb += ld_active.r.eq(0)
        comb += cyc_l.s.eq(0)
        comb += cyc_l.r.eq(0)
        comb += busy_l.s.eq(0)
        comb += busy_l.r.eq(0)
        sync += adrok_l.s.eq(0)
        comb += adrok_l.r.eq(0)

        # expand ld/st binary length/addr[:3] into unary bitmap
        m.submodules.lenexp = lenexp = LenExpand(4, 8)

        lds = Signal(reset_less=True)
        sts = Signal(reset_less=True)
        pi = self.pi
        comb += lds.eq(pi.is_ld_i)  # ld-req signals
        comb += sts.eq(pi.is_st_i)  # st-req signals

        # detect busy "edge"
        busy_delay = Signal()
        busy_edge = Signal()
        sync += busy_delay.eq(pi.busy_o)
        comb += busy_edge.eq(pi.busy_o & ~busy_delay)

        # activate mode: only on "edge"
        comb += ld_active.s.eq(rising_edge(m, lds))  # activate LD mode
        comb += st_active.s.eq(rising_edge(m, sts))  # activate ST mode

        # LD/ST requested activates "busy" (only if not already busy)
        with m.If(self.pi.is_ld_i | self.pi.is_st_i):
            comb += busy_l.s.eq(~busy_delay)

        # if now in "LD" mode: wait for addr_ok, then send the address out
        # to memory, acknowledge address, and send out LD data
        with m.If(ld_active.q):
            # set up LenExpander with the LD len and lower bits of addr
            lsbaddr, msbaddr = self.splitaddr(pi.addr.data)
            comb += lenexp.len_i.eq(pi.data_len)
            comb += lenexp.addr_i.eq(lsbaddr)
            with m.If(pi.addr.ok & adrok_l.qn):
                self.set_rd_addr(m, pi.addr.data, lenexp.lexp_o)
                comb += pi.addr_ok_o.eq(1)  # acknowledge addr ok
                sync += adrok_l.s.eq(1)       # and pull "ack" latch

        # if now in "ST" mode: likewise do the same but with "ST"
        # to memory, acknowledge address, and send out LD data
        with m.If(st_active.q):
            # set up LenExpander with the ST len and lower bits of addr
            lsbaddr, msbaddr = self.splitaddr(pi.addr.data)
            comb += lenexp.len_i.eq(pi.data_len)
            comb += lenexp.addr_i.eq(lsbaddr)
            with m.If(pi.addr.ok):
                self.set_wr_addr(m, pi.addr.data, lenexp.lexp_o)
                with m.If(adrok_l.qn):
                    comb += pi.addr_ok_o.eq(1)  # acknowledge addr ok
                    sync += adrok_l.s.eq(1)       # and pull "ack" latch

        # for LD mode, when addr has been "ok'd", assume that (because this
        # is a "Memory" test-class) the memory read data is valid.
        comb += reset_l.s.eq(0)
        comb += reset_l.r.eq(0)
        lddata = Signal(self.regwid, reset_less=True)
        data, ldok = self.get_rd_data(m)
        comb += lddata.eq((data & lenexp.rexp_o) >>
                          (lenexp.addr_i*8))
        with m.If(ld_active.q & adrok_l.q):
            # shift data down before pushing out.  requires masking
            # from the *byte*-expanded version of LenExpand output
            comb += pi.ld.data.eq(lddata)  # put data out
            comb += pi.ld.ok.eq(ldok)      # indicate data valid
            comb += reset_l.s.eq(ldok)     # reset mode after 1 cycle

        # for ST mode, when addr has been "ok'd", wait for incoming "ST ok"
        with m.If(st_active.q & pi.st.ok):
            # shift data up before storing.  lenexp *bit* version of mask is
            # passed straight through as byte-level "write-enable" lines.
            stdata = Signal(self.regwid, reset_less=True)
            comb += stdata.eq(pi.st.data << (lenexp.addr_i*8))
            # TODO: replace with link to LoadStoreUnitInterface.x_store_data
            # and also handle the ready/stall/busy protocol
            stok = self.set_wr_data(m, stdata, lenexp.lexp_o)
            sync += st_done.s.eq(1)     # store done trigger
        with m.If(st_done.q):
            comb += reset_l.s.eq(stok)   # reset mode after 1 cycle

        # ugly hack, due to simultaneous addr req-go acknowledge
        reset_delay = Signal(reset_less=True)
        sync += reset_delay.eq(reset_l.q)
        with m.If(reset_delay):
            comb += adrok_l.r.eq(1)     # address reset

        # after waiting one cycle (reset_l is "sync" mode), reset the port
        with m.If(reset_l.q):
            comb += ld_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += st_active.r.eq(1)   # leave the ST active for 1 cycle
            comb += reset_l.r.eq(1)     # clear reset
            comb += adrok_l.r.eq(1)     # address reset
            comb += st_done.r.eq(1)     # store done reset

        # monitor for an exception or the completion of LD.
        with m.If(self.pi.exc_o.happened):
            comb += busy_l.r.eq(1)

        # however ST needs one cycle before busy is reset
        #with m.If(self.pi.st.ok | self.pi.ld.ok):
        with m.If(reset_l.s):
            comb += cyc_l.s.eq(1)

        with m.If(cyc_l.q):
            comb += cyc_l.r.eq(1)
            comb += busy_l.r.eq(1)

        # busy latch outputs to interface
        comb += pi.busy_o.eq(busy_l.q)

        return m

    def ports(self):
        yield from self.pi.ports()


class TestMemoryPortInterface(PortInterfaceBase):
    """TestMemoryPortInterface

    This is a test class for simple verification of the LDSTCompUnit
    and for the simple core, to be able to run unit tests rapidly and
    with less other code in the way.

    Versions of this which are *compatible* (conform with PortInterface)
    will include augmented-Wishbone Bus versions, including ones that
    connect to L1, L2, MMU etc. etc. however this is the "base lowest
    possible version that complies with PortInterface".
    """

    def __init__(self, regwid=64, addrwid=4):
        super().__init__(regwid, addrwid)
        # hard-code memory addressing width to 6 bits
        self.mem = TestMemory(regwid, 5, granularity=regwid//8, init=False)

    def set_wr_addr(self, m, addr, mask):
        lsbaddr, msbaddr = self.splitaddr(addr)
        m.d.comb += self.mem.wrport.addr.eq(msbaddr)

    def set_rd_addr(self, m, addr, mask):
        lsbaddr, msbaddr = self.splitaddr(addr)
        m.d.comb += self.mem.rdport.addr.eq(msbaddr)

    def set_wr_data(self, m, data, wen):
        m.d.comb += self.mem.wrport.data.eq(data)  # write st to mem
        m.d.comb += self.mem.wrport.en.eq(wen)  # enable writes
        return Const(1, 1)

    def get_rd_data(self, m):
        return self.mem.rdport.data, Const(1, 1)

    def elaborate(self, platform):
        m = super().elaborate(platform)

        # add TestMemory as submodule
        m.submodules.mem = self.mem

        return m

    def ports(self):
        yield from super().ports()
        # TODO: memory ports
